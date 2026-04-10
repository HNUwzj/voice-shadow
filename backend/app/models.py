from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    child_id: str = Field(default="default-child")
    message: str
    enable_scene: bool = True
    enable_psych_analysis: bool = True


class PsychSignal(BaseModel):
    self_esteem_risk: float = 0.0
    bullying_risk: float = 0.0
    loneliness_risk: float = 0.0
    companionship_need: float = 0.0
    mood: str = "neutral"
    evidence: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    scene_image_url: str | None = None
    assistant_audio_url: str | None = None
    timestamp: datetime


class PraiseResponse(BaseModel):
    reply: str
    image_url: str | None = None
    scene_image_url: str | None = None
    assistant_audio_url: str | None = None
    details: dict


class DailyReportResponse(BaseModel):
    child_id: str
    date: str
    total_messages: int
    risk_summary: dict
    suggestion: str
    highlights: list[str]


class VoiceEnrollResponse(BaseModel):
    voice_id: str
    status: str
    sample_audio_url: str
    request_id: str | None = None


class VoiceSynthesizeRequest(BaseModel):
    child_id: str = Field(default="default-child")
    text: str
    voice_id: str | None = None


class VoiceSynthesizeResponse(BaseModel):
    voice_id: str
    audio_url: str
    request_id: str | None = None


class VoiceItem(BaseModel):
    child_id: str
    voice_id: str
    status: str = ""
    display_name: str
    prefix: str | None = None
    sample_audio_url: str | None = None
    timestamp: str = ""


class VoiceListResponse(BaseModel):
    child_id: str
    items: list[VoiceItem]


class VoiceDeleteResponse(BaseModel):
    ok: bool
    child_id: str
    voice_id: str


class ConversationItem(BaseModel):
    child_id: str
    role: str
    content: str = ""
    message_type: str = "text"
    image_url: str | None = None
    audio_url: str | None = None
    timestamp: str = ""


class ConversationListResponse(BaseModel):
    child_id: str
    day: str
    items: list[ConversationItem]
