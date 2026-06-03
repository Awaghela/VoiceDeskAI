from __future__ import annotations
import base64
import time
from typing import Optional, Tuple
import httpx
from fastapi import UploadFile
from app.config import settings
from app.schemas import VoiceSettings

class ElevenLabsError(RuntimeError):
    pass

class ElevenLabsClient:
    def __init__(self) -> None:
        self.base_url = settings.elevenlabs_base_url.rstrip("/")
        self.api_key = settings.elevenlabs_api_key

    def _headers(self, content_type: Optional[str] = "application/json") -> dict:
        headers = {"xi-api-key": self.api_key}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _require_key(self) -> None:
        if not self.api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured on the server.")

    async def list_voices(self) -> dict:
        self._require_key()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.base_url}/voices", headers=self._headers(None))
        if response.status_code >= 400:
            raise ElevenLabsError(f"Voice list failed: {response.text[:400]}")
        return response.json()

    async def transcribe(self, audio: UploadFile) -> Tuple[str, int, dict]:
        self._require_key()
        started = time.perf_counter()
        raw = await audio.read()
        if not raw:
            raise ElevenLabsError("No audio was received from the browser.")
        max_bytes = settings.max_audio_mb * 1024 * 1024
        if len(raw) > max_bytes:
            raise ElevenLabsError(f"Audio is too large. Limit is {settings.max_audio_mb} MB.")

        filename = audio.filename or "resident-audio.webm"
        content_type = audio.content_type or "audio/webm"
        files = {"file": (filename, raw, content_type)}
        data = {
            "model_id": settings.stt_model_id,
            "tag_audio_events": "true",
            "diarize": "false",
        }
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.base_url}/speech-to-text",
                headers={"xi-api-key": self.api_key},
                data=data,
                files=files,
            )
        if response.status_code >= 400:
            raise ElevenLabsError(f"Speech-to-text failed: {response.text[:700]}")
        payload = response.json()
        transcript = (payload.get("text") or payload.get("transcript") or "").strip()
        if not transcript:
            raise ElevenLabsError("STT completed but no transcript text was returned.")
        return transcript, int((time.perf_counter() - started) * 1000), payload

    async def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        language_code: Optional[str] = "en",
        voice_settings: Optional[VoiceSettings] = None,
    ) -> Tuple[str, int, int]:
        self._require_key()
        started = time.perf_counter()
        selected_voice = voice_id or settings.default_voice_id
        selected_model = model_id or settings.tts_model_id
        vs = voice_settings or VoiceSettings()
        body = {
            "text": text,
            "model_id": selected_model,
            "voice_settings": {
                "stability": vs.stability,
                "similarity_boost": vs.similarity_boost,
                "style": vs.style,
                "use_speaker_boost": vs.use_speaker_boost,
            },
        }
        if language_code:
            body["language_code"] = language_code

        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.base_url}/text-to-speech/{selected_voice}?output_format=mp3_44100_128",
                headers=self._headers("application/json"),
                json=body,
            )
        if response.status_code >= 400:
            raise ElevenLabsError(f"Text-to-speech failed: {response.text[:700]}")
        audio = response.content
        audio_b64 = base64.b64encode(audio).decode("utf-8")
        return audio_b64, int((time.perf_counter() - started) * 1000), len(audio)
