from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Always load backend/.env regardless of current working directory.
_DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_DOTENV_PATH, override=True)


@dataclass(slots=True)
class Settings:
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    dashscope_compatible_base_url: str = os.getenv(
        "DASHSCOPE_COMPATIBLE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    dashscope_text_model: str = os.getenv("DASHSCOPE_TEXT_MODEL", "qwen3.5-flash")
    dashscope_vision_model: str = os.getenv("DASHSCOPE_VISION_MODEL", "qwen3-vl-flash")
    dashscope_enable_thinking: bool = os.getenv("DASHSCOPE_ENABLE_THINKING", "false").lower() == "true"
    dashscope_base_http_api_url: str = os.getenv("DASHSCOPE_BASE_HTTP_API_URL", "https://dashscope.aliyuncs.com/api/v1")
    dashscope_base_websocket_api_url: str = os.getenv(
        "DASHSCOPE_BASE_WEBSOCKET_API_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
    )
    dashscope_image_model: str = os.getenv("DASHSCOPE_IMAGE_MODEL", "wan2.7-image")
    dashscope_image_size: str = os.getenv("DASHSCOPE_IMAGE_SIZE", "2K")
    dashscope_tts_model: str = os.getenv("DASHSCOPE_TTS_MODEL", "cosyvoice-v3.5-flash")
    dashscope_tts_instruction: str = os.getenv(
        "DASHSCOPE_TTS_INSTRUCTION",
        "请按正常口语平稳朗读整段文本，语气保持一致，不要重读、不要强调、不要夸张停顿。",
    )
    dashscope_tts_seed: int = int(os.getenv("DASHSCOPE_TTS_SEED", "20250410"))
    dashscope_tts_retry_attempts: int = int(os.getenv("DASHSCOPE_TTS_RETRY_ATTEMPTS", "2"))
    dashscope_tts_min_audio_bytes: int = int(os.getenv("DASHSCOPE_TTS_MIN_AUDIO_BYTES", "120000"))
    dashscope_tts_speech_rate: float = float(os.getenv("DASHSCOPE_TTS_SPEECH_RATE", "0.94"))
    dashscope_tts_pitch_rate: float = float(os.getenv("DASHSCOPE_TTS_PITCH_RATE", "0.96"))
    dashscope_tts_volume: int = int(os.getenv("DASHSCOPE_TTS_VOLUME", "55"))
    dashscope_voice_prefix: str = os.getenv("DASHSCOPE_VOICE_PREFIX", "myvoice")
    dashscope_voice_enroll_retry_attempts: int = int(os.getenv("DASHSCOPE_VOICE_ENROLL_RETRY_ATTEMPTS", "3"))
    dashscope_voice_poll_attempts: int = int(os.getenv("DASHSCOPE_VOICE_POLL_ATTEMPTS", "30"))
    dashscope_voice_poll_interval: int = int(os.getenv("DASHSCOPE_VOICE_POLL_INTERVAL", "10"))
    public_asset_base_url: str = os.getenv("PUBLIC_ASSET_BASE_URL", "")
    cpolar_auto_tunnel: bool = os.getenv("CPOLAR_AUTO_TUNNEL", "true").lower() == "true"
    cpolar_kill_existing: bool = os.getenv("CPOLAR_KILL_EXISTING", "true").lower() == "true"
    cpolar_path: str = os.getenv("CPOLAR_PATH", r"C:\Program Files\cpolar\cpolar.exe")
    cpolar_start_timeout_sec: int = int(os.getenv("CPOLAR_START_TIMEOUT_SEC", "60"))
    mock_mode: bool = os.getenv("MOCK_MODE", "true").lower() == "true"
    parent_persona: str = os.getenv(
        "PARENT_PERSONA",
        "你是孩子的爸爸或妈妈，回复要像真实家长，亲切自然、简短口语，先安抚再交流。",
    )
    data_dir: str = os.getenv("DATA_DIR", "./data")


settings = Settings()
_data_dir = Path(settings.data_dir)
if not _data_dir.is_absolute():
    settings.data_dir = str((Path(__file__).resolve().parents[1] / _data_dir).resolve())
