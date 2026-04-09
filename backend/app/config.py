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
    minimax_api_key: str = os.getenv("MINIMAX_API_KEY", "")
    minimax_base_url: str = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    minimax_model: str = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
    minimax_image_model: str = os.getenv("MINIMAX_IMAGE_MODEL", "image-01-live")
    minimax_vision_endpoint: str = os.getenv("MINIMAX_VISION_ENDPOINT", "")
    minimax_image_endpoint: str = os.getenv("MINIMAX_IMAGE_ENDPOINT", "")
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    google_vision_model: str = os.getenv("GOOGLE_VISION_MODEL", "models/gemini-2.5-flash")
    google_scene_model: str = os.getenv("GOOGLE_SCENE_MODEL", "models/gemini-2.5-flash-image")
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    dashscope_base_http_api_url: str = os.getenv("DASHSCOPE_BASE_HTTP_API_URL", "https://dashscope.aliyuncs.com/api/v1")
    dashscope_image_model: str = os.getenv("DASHSCOPE_IMAGE_MODEL", "wan2.7-image")
    dashscope_image_size: str = os.getenv("DASHSCOPE_IMAGE_SIZE", "2K")
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
