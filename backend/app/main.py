from __future__ import annotations
import time
import os
import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import ValidationError
from app.config import settings
from app.schemas import AgentTurnRequest, AgentTurnResponse, TTSRequest, VoiceSettings, ChatMessage
from app.groq_agent import GroqReasoningAgent
from app.elevenlabs_client import ElevenLabsClient, ElevenLabsError

app = FastAPI(
    title="VoiceDesk AI",
    description="Apartment maintenance voice agent using raw STT and TTS APIs.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

el = ElevenLabsClient()
agent = GroqReasoningAgent()

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "voicedesk-ai",
        "environment": settings.environment,
        "elevenlabs_configured": bool(settings.elevenlabs_api_key),
        "groq_configured": bool(settings.groq_api_key),
        "groq_model": settings.groq_model,
        "stt_model": settings.stt_model_id,
        "tts_model": settings.tts_model_id,
    }

@app.get("/api/voices")
async def voices():
    try:
        return await el.list_voices()
    except ElevenLabsError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected voice fetch error: {exc}")

@app.post("/api/agent/respond", response_model=AgentTurnResponse)
async def agent_respond(payload: AgentTurnRequest):
    total_start = time.perf_counter()
    decision, agent_ms, reasoning_mode = await agent.decide(payload.transcript, payload.conversation_history)
    try:
        audio_b64, tts_ms, audio_bytes = await el.text_to_speech(
            decision.spoken_response,
            voice_id=payload.voice_id,
            language_code=payload.language_code,
            voice_settings=payload.voice_settings,
        )
    except ElevenLabsError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return AgentTurnResponse(
        transcript=payload.transcript,
        agent=decision,
        audio_base64=audio_b64,
        metrics={
            "stt_ms": 0,
            "agent_ms": agent_ms,
            "tts_ms": tts_ms,
            "total_ms": int((time.perf_counter() - total_start) * 1000),
            "audio_bytes": audio_bytes,
            "mode": "text-fallback",
            "reasoning": reasoning_mode,
        },
    )

@app.post("/api/agent/full-turn", response_model=AgentTurnResponse)
async def full_turn(
    audio_file: UploadFile = File(...),
    voice_id: str | None = Form(default=None),
    language_code: str = Form(default="en"),
    stability: float = Form(default=0.48),
    similarity_boost: float = Form(default=0.78),
    style: float = Form(default=0.12),
    use_speaker_boost: bool = Form(default=True),
    conversation_history_json: str = Form(default="[]"),
):
    total_start = time.perf_counter()
    try:
        transcript, stt_ms, stt_payload = await el.transcribe(audio_file)
        try:
            raw_history = json.loads(conversation_history_json or "[]")
            conversation_history = [ChatMessage(**item) for item in raw_history[-8:]]
        except Exception:
            conversation_history = []
        decision, agent_ms, reasoning_mode = await agent.decide(transcript, conversation_history)
        voice_settings = VoiceSettings(
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost,
        )
        audio_b64, tts_ms, audio_bytes = await el.text_to_speech(
            decision.spoken_response,
            voice_id=voice_id,
            language_code=language_code,
            voice_settings=voice_settings,
        )
        return AgentTurnResponse(
            transcript=transcript,
            agent=decision,
            audio_base64=audio_b64,
            metrics={
                "stt_ms": stt_ms,
                "agent_ms": agent_ms,
                "tts_ms": tts_ms,
                "total_ms": int((time.perf_counter() - total_start) * 1000),
                "audio_bytes": audio_bytes,
                "mode": "voice-full-turn",
                "reasoning": reasoning_mode,
                "stt_language": stt_payload.get("language_code"),
                "stt_language_probability": stt_payload.get("language_probability"),
            },
        )
    except (ElevenLabsError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected full-turn error: {exc}")

@app.post("/api/tts")
async def tts(payload: TTSRequest):
    try:
        audio_b64, tts_ms, audio_bytes = await el.text_to_speech(
            payload.text,
            voice_id=payload.voice_id,
            model_id=payload.model_id,
            language_code=payload.language_code,
            voice_settings=payload.voice_settings,
        )
        return {"audio_base64": audio_b64, "latency_ms": tts_ms, "audio_bytes": audio_bytes, "mime_type": "audio/mpeg"}
    except ElevenLabsError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

# Serve React build when deployed as one Railway service.
frontend_dist = os.path.abspath(os.path.join(os.getcwd(), "frontend_dist"))
assets_dir = os.path.join(frontend_dist, "assets")
if os.path.isdir(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

@app.get("/{full_path:path}")
async def serve_react_app(full_path: str):
    index_path = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Frontend build not found. Run npm run build or use dev server.")
