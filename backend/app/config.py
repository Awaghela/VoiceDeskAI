from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_base_url: str = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    default_voice_id: str = os.getenv("ELEVENLABS_DEFAULT_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
    tts_model_id: str = os.getenv("ELEVENLABS_TTS_MODEL_ID", "eleven_multilingual_v2")
    stt_model_id: str = os.getenv("ELEVENLABS_STT_MODEL_ID", "scribe_v2")
    max_audio_mb: int = int(os.getenv("MAX_AUDIO_MB", "15"))
    environment: str = os.getenv("APP_ENV", "development")

settings = Settings()
