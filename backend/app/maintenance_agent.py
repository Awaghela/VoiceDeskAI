from __future__ import annotations
from datetime import datetime
import hashlib
import re
from typing import List, Dict, Tuple
from app.schemas import AgentDecision, TicketDraft, ChatMessage

CATEGORY_RULES: Dict[str, List[str]] = {
    "Emergency": ["gas", "fire", "smoke", "flood", "flooding", "burst", "sparks", "spark", "break in", "break-in", "carbon monoxide", "danger", "emergency"],
    "Plumbing": ["leak", "leaking", "sink", "toilet", "shower", "bath", "drain", "clog", "pipe", "water", "faucet", "overflow"],
    "Electrical": ["electric", "electrical", "outlet", "power", "breaker", "lights", "light", "socket", "wiring", "no electricity"],
    "Appliance": ["dishwasher", "washer", "dryer", "fridge", "refrigerator", "stove", "oven", "microwave", "garbage disposal", "disposal"],
    "HVAC": ["ac", "air conditioning", "heat", "heater", "heating", "thermostat", "hvac", "warm air", "cold air"],
    "Pest Control": ["pest", "roaches", "cockroach", "ants", "mice", "mouse", "rat", "bed bug", "bugs"],
    "Noise Complaint": ["noise", "loud", "party", "music", "upstairs", "neighbor", "banging"],
    "Access / Lock": ["lock", "key", "door", "access", "fob", "stuck outside", "garage gate"],
    "Internet / Smart Home": ["wifi", "internet", "router", "smart lock", "smart thermostat", "app not working"],
    "Common Area": ["hallway", "elevator", "gym", "package room", "lobby", "garage", "pool", "common area"]
}

LOCATION_RULES = {
    "Kitchen": ["kitchen", "dishwasher", "sink", "stove", "oven", "microwave", "fridge", "refrigerator", "garbage disposal"],
    "Bathroom": ["bathroom", "toilet", "shower", "tub", "bath", "vanity"],
    "Bedroom": ["bedroom", "closet"],
    "Living Room": ["living room", "window", "balcony"],
    "Laundry": ["washer", "dryer", "laundry"],
    "Entry": ["front door", "lock", "key", "fob", "entry"],
    "Common Area": ["hallway", "elevator", "lobby", "garage", "gym", "package room"]
}

EMERGENCY_TERMS = ["gas", "fire", "smoke", "carbon monoxide", "sparks", "flooding", "burst pipe", "break in", "break-in"]
HIGH_TERMS = ["active leak", "leaking", "water everywhere", "flood", "no heat", "no ac", "broken lock", "power outage", "no power", "overflow"]
LOW_TERMS = ["light bulb", "paint", "scratch", "cabinet handle", "cosmetic", "slow drain", "minor"]

TROUBLESHOOTING = {
    "Plumbing": "Avoid using the affected fixture, place a container or towel under active drips if safe, and do not attempt to remove pipes yourself.",
    "Electrical": "Avoid using the affected outlet or switch. If you see sparks, smell burning, or feel heat near wiring, step away and contact emergency support.",
    "Appliance": "Check whether the appliance is fully closed, powered on, and connected to its outlet or breaker. Stop using it if there is burning smell, leaking, or unusual noise.",
    "HVAC": "Check the thermostat mode, target temperature, and breaker if safe. Keep windows closed while testing heating or cooling.",
    "Pest Control": "Keep food sealed, avoid spraying unknown chemicals, and share where and when you saw the pests so maintenance can target the issue.",
    "Noise Complaint": "Note the time, location, and type of noise. If there is immediate safety risk, contact building security or local authorities.",
    "Access / Lock": "If you are locked out or the door cannot secure, contact building staff immediately. Do not force the lock.",
    "Internet / Smart Home": "Restart the device if safe, note any error lights or app messages, and share the device name or room.",
    "Common Area": "Share the exact location and whether anyone may be at risk so the property team can route it correctly.",
    "Emergency": "Leave the area if safe and contact emergency services or building management immediately.",
    "General": "Share the exact room, what changed, and whether the issue is getting worse."
}


CONVERSATION_CLOSING_TERMS = ["thanks", "thank you", "okay thanks", "ok thanks", "no thanks", "that's all", "that is all", "all good", "done", "bye", "goodbye", "never mind", "cancel"]
GREETING_TERMS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]

def _simple_conversation_intent(text: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9\s']", "", text.lower()).strip()
    if not normalized:
        return None
    if any(term == normalized or term in normalized for term in CONVERSATION_CLOSING_TERMS):
        return "closing"
    if any(term == normalized for term in GREETING_TERMS):
        return "greeting"
    return None

def _conversation_decision(raw: str, intent: str) -> AgentDecision:
    if intent == "greeting":
        spoken = "Hi, I’m ready to help. Please tell me what is wrong in your apartment."
        title = "Conversation greeting"
        summary = "Resident greeted the assistant. No maintenance issue has been reported yet."
        next_action = "Wait for resident issue"
    else:
        spoken = "No problem. If anything else comes up, just start a new voice report."
        title = "Conversation closed"
        summary = "Resident ended or paused the conversation. No maintenance ticket is needed."
        next_action = "No action required"
    ticket = TicketDraft(
        ticket_id=_ticket_id(raw or intent),
        title=title,
        category="Conversation",
        issue_type=title,
        priority="Low",
        location="Not needed",
        summary=summary,
        recommended_action=next_action,
        resident_guidance=spoken,
        safety_note="",
        confidence=96,
    )
    return AgentDecision(
        spoken_response=spoken,
        category="Conversation",
        priority="Low",
        issue_type=title,
        location="Not needed",
        requires_follow_up=False,
        follow_up_question=None,
        next_action=next_action,
        safety_note="",
        confidence=96,
        ticket=ticket,
    )


def _score_category(text: str) -> Tuple[str, int]:
    scores = {category: 0 for category in CATEGORY_RULES}
    for category, terms in CATEGORY_RULES.items():
        for term in terms:
            if term in text:
                scores[category] += 2 if category == "Emergency" else 1
    best = max(scores, key=scores.get)
    return (best if scores[best] > 0 else "General", scores[best])

def _detect_location(text: str) -> str:
    for location, terms in LOCATION_RULES.items():
        if any(term in text for term in terms):
            return location
    return "Not specified"

def _detect_priority(text: str, category: str) -> str:
    if any(term in text for term in EMERGENCY_TERMS) or category == "Emergency":
        return "Emergency"
    if any(term in text for term in HIGH_TERMS):
        return "High"
    if any(term in text for term in LOW_TERMS):
        return "Low"
    if category in ["Plumbing", "Electrical", "HVAC", "Access / Lock"]:
        return "High" if any(w in text for w in ["not working", "no ", "can't", "cannot", "leak"]) else "Medium"
    return "Medium"

def _issue_type(text: str, category: str) -> str:
    patterns = [
        ("dishwasher", "Dishwasher issue"), ("washer", "Washer issue"), ("dryer", "Dryer issue"),
        ("fridge", "Refrigerator issue"), ("refrigerator", "Refrigerator issue"), ("sink", "Sink issue"),
        ("toilet", "Toilet issue"), ("shower", "Shower issue"), ("ac", "Air conditioning issue"),
        ("heat", "Heating issue"), ("lock", "Lock or access issue"), ("wifi", "Internet issue"),
        ("noise", "Noise complaint"), ("gas", "Possible gas leak"), ("fire", "Fire or smoke issue")
    ]
    for key, label in patterns:
        if key in text:
            return label
    return f"{category} issue"

def _needs_followup(text: str, category: str, location: str) -> Tuple[bool, str | None]:
    if category == "Emergency":
        return False, None
    if location == "Not specified":
        return True, "Which room or area is this happening in?"
    if category == "HVAC" and not any(x in text for x in ["not turning", "warm", "cold", "noise", "leak", "thermostat"]):
        return True, "Is the system not turning on, blowing the wrong temperature, or making an unusual noise?"
    if category == "Plumbing" and not any(x in text for x in ["active", "drip", "overflow", "clog", "under", "water"]):
        return True, "Is water actively leaking, draining slowly, or completely blocked?"
    if category == "Appliance" and not any(x in text for x in ["turning on", "start", "noise", "leak", "error", "not working"]):
        return True, "What exactly is the appliance doing, not starting, making noise, leaking, or showing an error?"
    return False, None

def _ticket_id(seed: str) -> str:
    digest = hashlib.sha1((seed + datetime.utcnow().isoformat()).encode()).hexdigest()[:5].upper()
    return f"VD-{digest}"

def _clean_summary(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:240] + ("..." if len(text) > 240 else "")

def build_agent_decision(transcript: str, history: List[ChatMessage] | None = None) -> AgentDecision:
    history = history or []
    raw = transcript.strip()
    text = raw.lower()
    simple_intent = _simple_conversation_intent(text)
    if simple_intent:
        return _conversation_decision(raw, simple_intent)
    category, score = _score_category(text)
    location = _detect_location(text)
    priority = _detect_priority(text, category)
    issue_type = _issue_type(text, category)
    requires_follow_up, follow_up = _needs_followup(text, category, location)
    confidence = min(96, max(62, 62 + score * 8 + (8 if location != "Not specified" else 0)))

    safety_note = ""
    if priority == "Emergency":
        safety_note = "If there is immediate danger, leave the area if safe and contact emergency services or building management right away."
    elif priority == "High":
        safety_note = "Avoid using the affected item or area until maintenance checks it, especially if there is water, heat, sparks, or access risk."
    else:
        safety_note = "This does not sound immediately dangerous, but maintenance should still review it."

    guidance = TROUBLESHOOTING.get(category, TROUBLESHOOTING["General"])
    base_intro = f"I understand. This sounds like a {priority.lower()} priority {category.lower()} request."
    if requires_follow_up and follow_up:
        spoken = f"{base_intro} {follow_up} I’ll keep a draft ticket ready while we collect that detail."
        next_action = "Ask follow-up question before submitting ticket"
    else:
        spoken = f"{base_intro} {guidance} I prepared a structured maintenance ticket draft for the property team."
        next_action = "Review ticket draft and submit maintenance request"

    if priority == "Emergency":
        spoken = f"This may be an emergency. {safety_note} I also prepared an emergency maintenance draft with the details you shared."
        next_action = "Escalate immediately"

    summary = _clean_summary(raw)
    title = f"{priority} {issue_type}"
    recommended_action = f"Maintenance should inspect {issue_type.lower()} in {location.lower() if location != 'Not specified' else 'the reported area'} and verify the root cause."
    if priority == "Emergency":
        recommended_action = "Escalate immediately to property emergency protocol and inspect as soon as possible."

    ticket = TicketDraft(
        ticket_id=_ticket_id(raw),
        title=title,
        category=category,
        issue_type=issue_type,
        priority=priority,
        location=location,
        summary=f"Resident reported: {summary}",
        recommended_action=recommended_action,
        resident_guidance=guidance,
        safety_note=safety_note,
        confidence=confidence,
    )

    return AgentDecision(
        spoken_response=spoken,
        category=category,
        priority=priority,
        issue_type=issue_type,
        location=location,
        requires_follow_up=requires_follow_up,
        follow_up_question=follow_up,
        next_action=next_action,
        safety_note=safety_note,
        confidence=confidence,
        ticket=ticket,
    )
