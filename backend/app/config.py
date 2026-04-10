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
