from pydantic import BaseModel, Field
from typing import List, Optional, Literal

Priority = Literal["Emergency", "High", "Medium", "Low"]
Category = Literal[
    "Plumbing", "Electrical", "Appliance", "HVAC", "Pest Control", "Noise Complaint",
    "Access / Lock", "Internet / Smart Home", "Common Area", "Emergency", "General", "Conversation"
]

class VoiceSettings(BaseModel):
    stability: float = Field(default=0.48, ge=0, le=1)
    similarity_boost: float = Field(default=0.78, ge=0, le=1)
    style: float = Field(default=0.12, ge=0, le=1)
    use_speaker_boost: bool = True

class ChatMessage(BaseModel):
    role: Literal["resident", "agent"]
    content: str

class AgentTurnRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=4000)
    voice_id: Optional[str] = None
    language_code: Optional[str] = "en"
    conversation_history: List[ChatMessage] = []
    voice_settings: VoiceSettings = VoiceSettings()

class TicketDraft(BaseModel):
    ticket_id: str
    title: str
    category: Category
    issue_type: str
    priority: Priority
    location: str
    summary: str
    recommended_action: str
    resident_guidance: str
    safety_note: str
    confidence: int
    status: str = "Draft"

class AgentDecision(BaseModel):
    spoken_response: str
    category: Category
    priority: Priority
    issue_type: str
    location: str
    requires_follow_up: bool
    follow_up_question: Optional[str] = None
    next_action: str
    safety_note: str
    confidence: int
    ticket: TicketDraft

class AgentTurnResponse(BaseModel):
    transcript: str
    agent: AgentDecision
    audio_base64: Optional[str] = None
    audio_mime_type: str = "audio/mpeg"
    metrics: dict

class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: Optional[str] = None
    model_id: str = "eleven_multilingual_v2"
    language_code: Optional[str] = "en"
    voice_settings: VoiceSettings = VoiceSettings()
