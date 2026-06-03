from __future__ import annotations

import json
import re
import time
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.schemas import AgentDecision, ChatMessage, TicketDraft
from app.maintenance_agent import build_agent_decision

ALLOWED_CATEGORIES = {
    "Plumbing", "Electrical", "Appliance", "HVAC", "Pest Control", "Noise Complaint",
    "Access / Lock", "Internet / Smart Home", "Common Area", "Emergency", "General", "Conversation"
}
ALLOWED_PRIORITIES = {"Emergency", "High", "Medium", "Low"}

EMERGENCY_TERMS = [
    "gas", "gas leak", "fire", "smoke", "carbon monoxide", "sparks", "spark",
    "flooding", "flood", "burst pipe", "break in", "break-in", "intruder",
    "electrical burning", "burning smell"
]

SYSTEM_PROMPT = """
You are VoiceDesk AI, a voice-first apartment maintenance service desk agent.

Your job is to reason over a resident's latest message and the prior conversation, then return one valid JSON object only.

Important behavior:
- First detect the user's intent. Do not treat every message as a maintenance report.
- If the user says thanks, okay thanks, bye, done, never mind, cancel, or indicates the conversation is complete, respond naturally and do not ask for room/location.
- If the user answers a follow-up question, use prior context to update the existing issue.
- If this is a new maintenance issue, classify it and generate a ticket draft.
- If information is missing, ask exactly one useful follow-up question.
- For emergencies such as gas smell, fire, smoke, flooding, sparks, break-in, or carbon monoxide, prioritize safety and escalation.
- Never say a real ticket was submitted. Say a ticket draft is prepared or ready for review.
- Keep spoken_response short enough to sound natural when spoken aloud.

Allowed category values:
Plumbing, Electrical, Appliance, HVAC, Pest Control, Noise Complaint, Access / Lock, Internet / Smart Home, Common Area, Emergency, General, Conversation

Allowed priority values:
Emergency, High, Medium, Low

Return JSON with exactly this shape:
{
  "intent": "maintenance_report | follow_up_answer | thanks_or_closing | greeting | cancel | clarification_question | irrelevant_input",
  "spoken_response": "natural response to speak back to the resident",
  "category": "one allowed category",
  "priority": "one allowed priority",
  "issue_type": "short issue type",
  "location": "room or area, or Not specified, or Not needed",
  "requires_follow_up": true,
  "follow_up_question": "one question or null",
  "next_action": "next action for the system",
  "safety_note": "safety note or empty string",
  "confidence": 0,
  "ticket": {
    "title": "short title",
    "category": "one allowed category",
    "issue_type": "short issue type",
    "priority": "one allowed priority",
    "location": "room or area, or Not specified, or Not needed",
    "summary": "ticket summary or reason no ticket is needed",
    "recommended_action": "maintenance action or no action required",
    "resident_guidance": "short resident guidance",
    "safety_note": "same safety note or empty string",
    "confidence": 0,
    "status": "Draft"
  }
}
""".strip()


def _ticket_id(seed: str) -> str:
    digest = hashlib.sha1((seed + datetime.utcnow().isoformat()).encode()).hexdigest()[:5].upper()
    return f"VD-{digest}"


def _history_for_prompt(history: Optional[List[ChatMessage]]) -> str:
    if not history:
        return "No prior conversation."
    compact = []
    for message in history[-8:]:
        compact.append(f"{message.role}: {message.content}")
    return "\n".join(compact)


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _coerce_category(value: Any) -> str:
    category = str(value or "General").strip()
    return category if category in ALLOWED_CATEGORIES else "General"


def _coerce_priority(value: Any) -> str:
    priority = str(value or "Medium").strip()
    return priority if priority in ALLOWED_PRIORITIES else "Medium"


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes"}


def _coerce_confidence(value: Any) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = 75
    if number <= 1:
        number = int(number * 100)
    return max(0, min(100, number))


def _has_emergency_override(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in EMERGENCY_TERMS)


def _normalize_decision(payload: Dict[str, Any], transcript: str) -> AgentDecision:
    category = _coerce_category(payload.get("category"))
    priority = _coerce_priority(payload.get("priority"))
    issue_type = str(payload.get("issue_type") or f"{category} request").strip()
    location = str(payload.get("location") or "Not specified").strip()
    confidence = _coerce_confidence(payload.get("confidence"))
    requires_follow_up = _coerce_bool(payload.get("requires_follow_up"))
    follow_up_question = payload.get("follow_up_question")
    if follow_up_question is not None:
        follow_up_question = str(follow_up_question).strip() or None

    safety_note = str(payload.get("safety_note") or "").strip()
    spoken_response = str(payload.get("spoken_response") or "I can help with that. Please share a few more details about the issue.").strip()
    next_action = str(payload.get("next_action") or "Continue conversation").strip()

    ticket_payload = payload.get("ticket") or {}
    ticket_category = _coerce_category(ticket_payload.get("category") or category)
    ticket_priority = _coerce_priority(ticket_payload.get("priority") or priority)
    ticket_confidence = _coerce_confidence(ticket_payload.get("confidence") or confidence)

    ticket = TicketDraft(
        ticket_id=str(ticket_payload.get("ticket_id") or _ticket_id(transcript)),
        title=str(ticket_payload.get("title") or f"{priority} {issue_type}").strip(),
        category=ticket_category,
        issue_type=str(ticket_payload.get("issue_type") or issue_type).strip(),
        priority=ticket_priority,
        location=str(ticket_payload.get("location") or location).strip(),
        summary=str(ticket_payload.get("summary") or f"Resident said: {transcript}").strip(),
        recommended_action=str(ticket_payload.get("recommended_action") or next_action).strip(),
        resident_guidance=str(ticket_payload.get("resident_guidance") or spoken_response).strip(),
        safety_note=str(ticket_payload.get("safety_note") or safety_note).strip(),
        confidence=ticket_confidence,
        status=str(ticket_payload.get("status") or "Draft").strip(),
    )

    return AgentDecision(
        spoken_response=spoken_response,
        category=category,
        priority=priority,
        issue_type=issue_type,
        location=location,
        requires_follow_up=requires_follow_up,
        follow_up_question=follow_up_question,
        next_action=next_action,
        safety_note=safety_note,
        confidence=confidence,
        ticket=ticket,
    )


def _apply_safety_override(decision: AgentDecision, transcript: str) -> AgentDecision:
    if not _has_emergency_override(transcript):
        return decision

    decision.category = "Emergency"
    decision.priority = "Emergency"
    decision.requires_follow_up = False
    decision.follow_up_question = None
    decision.issue_type = "Potential emergency maintenance issue"
    decision.location = decision.location if decision.location not in {"", "Not needed"} else "Not specified"
    decision.safety_note = "If there is immediate danger, leave the area if safe and contact emergency services or building management right away."
    decision.next_action = "Escalate immediately"
    decision.spoken_response = (
        "This may be an emergency. If there is immediate danger, leave the area if safe and contact emergency services or building management right away. "
        "I prepared an emergency maintenance draft with the details you shared."
    )
    decision.ticket.category = "Emergency"
    decision.ticket.priority = "Emergency"
    decision.ticket.issue_type = decision.issue_type
    decision.ticket.title = "Emergency maintenance report"
    decision.ticket.safety_note = decision.safety_note
    decision.ticket.recommended_action = "Escalate immediately through property emergency protocol."
    decision.ticket.resident_guidance = decision.safety_note
    return decision


class GroqAgentError(Exception):
    pass


class GroqReasoningAgent:
    def __init__(self) -> None:
        self.api_key = settings.groq_api_key
        self.model = settings.groq_model
        self.base_url = settings.groq_base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def decide(self, transcript: str, history: Optional[List[ChatMessage]] = None) -> tuple[AgentDecision, int, str]:
        start = time.perf_counter()
        if not self.configured:
            decision = build_agent_decision(transcript, history)
            return decision, int((time.perf_counter() - start) * 1000), "rules-fallback-no-groq-key"

        user_prompt = f"""
Latest resident message:
{transcript}

Prior conversation:
{_history_for_prompt(history)}

Reason about the intent and produce the JSON object only.
""".strip()

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_completion_tokens": 900,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
                response.raise_for_status()
                payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            raw_json = _extract_json(content)
            decision = _normalize_decision(raw_json, transcript)
            decision = _apply_safety_override(decision, transcript)
            return decision, int((time.perf_counter() - start) * 1000), f"groq:{self.model}"
        except Exception:
            decision = build_agent_decision(transcript, history)
            decision = _apply_safety_override(decision, transcript)
            return decision, int((time.perf_counter() - start) * 1000), "rules-fallback-groq-error"
