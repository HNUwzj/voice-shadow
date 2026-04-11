from __future__ import annotations

import asyncio
import base64
import html
import logging
import mimetypes
import os
import random
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None

try:
    import dashscope
    from dashscope.aigc.image_generation import ImageGeneration
    from dashscope.api_entities.dashscope_response import Message
    from dashscope.audio.tts_v2 import SpeechSynthesizer, VoiceEnrollmentService
except Exception:  # pragma: no cover - optional dependency
    dashscope = None
    ImageGeneration = None
    Message = None
    SpeechSynthesizer = None
    VoiceEnrollmentService = None

from app.config import settings

logger = logging.getLogger(__name__)


def _build_dashscope_requests_session() -> requests.Session:
    session = requests.Session()
    if settings.dashscope_ignore_env_proxy:
        # Some Windows environments inject HTTPS_PROXY and trigger SSLEOF for dashscope host.
        session.trust_env = False
    return session


def _extract_dashscope_image_url(rsp: Any) -> str | None:
    output = getattr(rsp, "output", None)
    if output is None and isinstance(rsp, dict):
        output = rsp.get("output")

    if output is None:
        return None

    # Newer DashScope response: output.choices[0].message.content[0].image
    choices = output.get("choices") if isinstance(output, dict) else getattr(output, "choices", None)
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        message = first_choice.get("message") if isinstance(first_choice, dict) else getattr(first_choice, "message", None)
        if message is not None:
            content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
            if isinstance(content, list) and content:
                first_content = content[0]
                if isinstance(first_content, dict):
                    image_url = first_content.get("image")
                    if isinstance(image_url, str) and image_url:
                        return image_url

    results = None
    if isinstance(output, dict):
        results = output.get("results") or output.get("images")
    else:
        results = getattr(output, "results", None) or getattr(output, "images", None)

    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            for key in ("url", "image_url", "imageUrl"):
                val = first.get(key)
                if isinstance(val, str) and val:
                    return val
        else:
            for key in ("url", "image_url", "imageUrl"):
                val = getattr(first, key, None)
                if isinstance(val, str) and val:
                    return val
    return None


def _dashscope_generate_scene_image(scene_prompt: str) -> tuple[str | None, str | None]:
    if not settings.dashscope_api_key:
        return None, "未配置 DASHSCOPE_API_KEY。"
    if dashscope is None or ImageGeneration is None or Message is None:
        return None, "缺少 dashscope 依赖。"

    dashscope.base_http_api_url = settings.dashscope_base_http_api_url
    prompt = (
        "电影感儿童绘本背景图，画面干净、无文字、主体明确。"
        f"场景要求：{scene_prompt}。"
        "构图要求：16:9，单一主焦点，细节丰富，不要抽象色块。"
    )

    try:
        message = Message(role="user", content=[{"text": prompt}])
        rsp = ImageGeneration.call(
            model=settings.dashscope_image_model,
            api_key=settings.dashscope_api_key,
            messages=[message],
            enable_sequential=False,
            n=1,
            size=settings.dashscope_image_size,
        )
        url = _extract_dashscope_image_url(rsp)
        if url:
            return url, None

        err = getattr(rsp, "message", None)
        if isinstance(err, str) and err:
            return None, err[:140]
        return None, "DashScope 未返回图片链接。"
    except Exception as exc:
        return None, str(exc)[:140]


def _classify_dashscope_error(err: Exception) -> str:
    msg = str(err).strip()
    low = msg.lower()

    if any(k in low for k in ["connection refused", "failed to establish", "proxy", "10061", "127.0.0.1:7897"]):
        return "本地代理不可用，请确认代理已开启且端口为 127.0.0.1:7897。"
    if any(k in low for k in ["ssleoferror", "unexpected eof while reading", "tlsv1 alert", "ssl"]):
        return "TLS 握手异常（可能由代理或网络中断导致），建议先关闭系统代理后重试。"
    if any(k in low for k in ["timed out", "timeout", "deadline", "readtimeout", "connecttimeout"]):
        return "网络超时，请检查网络后重试。"
    if any(k in low for k in ["api key", "invalid", "permission denied", "unauthorized", "403", "401"]):
        return "DASHSCOPE_API_KEY 无效或无权限，请到 DashScope 控制台检查 Key 和权限。"
    if any(k in low for k in ["quota", "resource exhausted", "429", "rate limit", "too many requests"]):
        return "请求配额不足或触发限流，请到 DashScope 控制台检查配额/套餐后重试。"
    if any(k in low for k in ["location", "region", "country", "not available"]):
        return "当前网络区域暂不可用 DashScope 视觉能力。"
    if not msg:
        return "未知错误。"
    return f"{msg[:140]}"


def _dashscope_action_hint() -> str:
    return (
        "排查建议："
        "1) 打开阿里云 DashScope 控制台检查 Key 状态；"
        "2) 检查模型开通情况（例如 qwen3-vl-flash）；"
        "3) 检查账单、配额与限流配置。"
    )


@contextmanager
def _dashscope_proxy_guard():
    if not settings.dashscope_ignore_env_proxy:
        yield
        return

    keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "NO_PROXY", "no_proxy"]
    prev = {k: os.environ.get(k) for k in keys}

    # Voice enrollment/synthesis often fails with SSLEOF when process-level proxy is injected.
    for k in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
        os.environ.pop(k, None)

    host = urlparse(settings.dashscope_base_http_api_url).hostname or "dashscope.aliyuncs.com"
    no_proxy_items = ["127.0.0.1", "localhost", host]
    old_no_proxy = prev.get("NO_PROXY") or prev.get("no_proxy")
    if old_no_proxy:
        no_proxy_items.append(old_no_proxy)
    merged_no_proxy = ",".join(no_proxy_items)
    os.environ["NO_PROXY"] = merged_no_proxy
    os.environ["no_proxy"] = merged_no_proxy

    try:
        yield
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextmanager
def _dashscope_tts_proxy_env():
    proxy = (settings.dashscope_tts_proxy_url or "").strip()
    if not proxy:
        yield
        return

    keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"]
    prev = {k: os.environ.get(k) for k in keys}

    os.environ["HTTP_PROXY"] = proxy
    os.environ["HTTPS_PROXY"] = proxy
    os.environ["ALL_PROXY"] = proxy
    os.environ["http_proxy"] = proxy
    os.environ["https_proxy"] = proxy
    os.environ["all_proxy"] = proxy

    no_proxy_parts = ["127.0.0.1", "localhost"]
    old_no_proxy = prev.get("NO_PROXY") or prev.get("no_proxy")
    if old_no_proxy:
        no_proxy_parts.append(old_no_proxy)
    merged_no_proxy = ",".join(no_proxy_parts)
    os.environ["NO_PROXY"] = merged_no_proxy
    os.environ["no_proxy"] = merged_no_proxy

    try:
        yield
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextmanager
def _vision_proxy_env():
    proxy = "http://127.0.0.1:7897"
    keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"]
    prev = {k: os.environ.get(k) for k in keys}

    # Force multimodal request through local proxy, while keeping localhost direct.
    os.environ["HTTP_PROXY"] = proxy
    os.environ["HTTPS_PROXY"] = proxy
    os.environ["ALL_PROXY"] = proxy

    no_proxy_parts = ["127.0.0.1", "localhost"]
    old_no_proxy = prev.get("NO_PROXY")
    if old_no_proxy:
        no_proxy_parts.append(old_no_proxy)
    os.environ["NO_PROXY"] = ",".join(no_proxy_parts)

    try:
        yield
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _image_to_data_url(image_path: Path) -> str:
    mime = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
    data = image_path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _dashscope_openai_vision_praise(image_path: Path, user_text: str) -> tuple[str | None, str | None]:
    if not settings.dashscope_api_key:
        return None, "未配置 DASHSCOPE_API_KEY。"
    if OpenAI is None:
        return None, "缺少 openai 依赖。"

    prompt = (
        "你是孩子的爸爸妈妈。"
        "请基于图片内容和孩子的话，输出2-4句中文口语化夸奖。"
        "要求具体提到画面里看到的内容，不要编造未出现的元素，不要提文件大小。"
        f"孩子的话：{user_text}"
    )

    try:
        with _vision_proxy_env():
            client = OpenAI(
                api_key=settings.dashscope_api_key,
                base_url=settings.dashscope_compatible_base_url,
            )
            image_data_url = _image_to_data_url(image_path)
            completion = client.chat.completions.create(
                model=settings.dashscope_vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                extra_body={
                    "enable_thinking": settings.dashscope_enable_thinking,
                    "thinking_budget": 8192,
                },
            )
            choices = getattr(completion, "choices", None) or []
            if choices:
                msg = getattr(choices[0], "message", None)
                text = getattr(msg, "content", None) if msg is not None else None
                if isinstance(text, str) and text.strip():
                    return text.strip(), None
    except Exception as exc:
        return None, _classify_dashscope_error(exc)
    return None, "DashScope 视觉返回空结果。"


def _dashscope_scene_caption(image_path: Path, user_text: str, praise_reply: str) -> tuple[str | None, str | None]:
    if not settings.dashscope_api_key:
        return None, "未配置 DASHSCOPE_API_KEY。"
    if OpenAI is None:
        return None, "缺少 openai 依赖。"

    prompt = (
        "You are extracting visual scene keywords for image generation. "
        "Based on the image and child text, return ONE short line in English only. "
        "Strict format: subject=<main object>;setting=<environment>;palette=<3 colors>. "
        "No extra words, no markdown. "
        f"Child text: {user_text}. "
        f"Parent praise: {praise_reply}"
    )

    try:
        with _vision_proxy_env():
            client = OpenAI(
                api_key=settings.dashscope_api_key,
                base_url=settings.dashscope_compatible_base_url,
            )
            image_data_url = _image_to_data_url(image_path)
            completion = client.chat.completions.create(
                model=settings.dashscope_vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                extra_body={
                    "enable_thinking": settings.dashscope_enable_thinking,
                    "thinking_budget": 8192,
                },
            )
            choices = getattr(completion, "choices", None) or []
            if choices:
                msg = getattr(choices[0], "message", None)
                text = getattr(msg, "content", None) if msg is not None else None
                if isinstance(text, str) and text.strip():
                    line = re.sub(r"\s+", " ", text.strip())
                    return line[:180], None
    except Exception as exc:
        return None, _classify_dashscope_error(exc)
    return None, "DashScope 视觉返回空结果。"


def _dashscope_openai_chat(messages: list[dict[str, str]], temperature: float) -> tuple[str | None, str | None]:
    if not settings.dashscope_api_key:
        return None, "未配置 DASHSCOPE_API_KEY。"
    if OpenAI is None:
        return None, "缺少 openai 依赖。"

    normalized_messages: list[dict[str, str]] = []
    for msg in messages:
        role = (msg.get("role") or "user").strip()
        content = msg.get("content", "")
        if role not in {"system", "user", "assistant"}:
            role = "user"
        normalized_messages.append({"role": role, "content": content})

    if not normalized_messages:
        return None, "对话消息为空。"

    try:
        with _vision_proxy_env():
            client = OpenAI(
                api_key=settings.dashscope_api_key,
                base_url=settings.dashscope_compatible_base_url,
            )
            completion = client.chat.completions.create(
                model=settings.dashscope_text_model,
                messages=normalized_messages,
                temperature=temperature,
                stream=True,
                extra_body={"enable_thinking": settings.dashscope_enable_thinking},
            )

            answer_parts: list[str] = []
            for chunk in completion:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue
                content = getattr(delta, "content", None)
                if isinstance(content, str) and content:
                    answer_parts.append(content)

            answer = "".join(answer_parts).strip()
            if answer:
                return answer, None
    except Exception as exc:
        return None, _classify_dashscope_error(exc)

    return None, "DashScope 文本模型返回空结果。"


def _scene_subject_spec(scene_prompt: str) -> tuple[str, str, str]:
    low = scene_prompt.lower()

    # Prioritize concrete visible objects to avoid generic landscape outputs.
    mapping = [
        (["两只狗", "两条狗", "狗", "小狗", "狗狗", "dog", "puppy"], "two playful dogs", "park lawn with warm sunlight", "golden, green, soft sky blue"),
        (["蝴蝶", "butterfly"], "a colorful butterfly", "flower field in spring", "orange, cyan, pink"),
        (["猫", "小猫", "cat", "kitten"], "a big yellow cat", "quiet neighborhood path", "honey yellow, mint green, cream"),
        (["鸟", "小鸟", "bird"], "a small bird", "tree branch in a gentle park", "leaf green, sky blue, warm beige"),
        (["兔", "兔子", "rabbit", "bunny"], "a white rabbit", "meadow near wildflowers", "green, white, peach"),
        (["鱼", "小鱼", "fish"], "a little fish", "clear stream with stones", "aqua, teal, silver"),
        (["花", "花朵", "flower"], "bright flowers", "garden path", "coral, yellow, leaf green"),
    ]

    for keys, subject, setting, palette in mapping:
        if any(k in scene_prompt for k in keys if any(ord(ch) > 127 for ch in k)) or any(k in low for k in keys if k.isascii()):
            return subject, setting, palette

    return "a child-friendly outdoor scene", "cozy neighborhood at sunset", "warm orange, soft green, gentle blue"


def _local_scene_image_url(scene_prompt: str, seed: int) -> str:
    subject, setting, palette = _scene_subject_spec(scene_prompt)
    uploads = Path(settings.data_dir) / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    output_path = uploads / f"scene_{seed}.svg"

    escaped_subject = html.escape(subject)
    escaped_setting = html.escape(setting)
    escaped_palette = html.escape(palette)
    if "dog" in subject:
        subject_shape = """
      <g transform="translate(840 520)">
        <ellipse cx="-115" cy="35" rx="94" ry="54" fill="#d69a3a"/>
        <circle cx="-190" cy="-8" r="58" fill="#e0ad4b"/>
        <path d="M-226 -48 L-252 -96 L-204 -68 Z" fill="#9d5b2f"/>
        <path d="M-166 -52 L-132 -96 L-128 -42 Z" fill="#9d5b2f"/>
        <circle cx="-210" cy="-18" r="7" fill="#1e2a2f"/>
        <circle cx="-174" cy="-18" r="7" fill="#1e2a2f"/>
        <ellipse cx="-192" cy="2" rx="14" ry="10" fill="#39251e"/>
        <path d="M-45 18 C10 -38 86 -40 130 10" fill="none" stroke="#d69a3a" stroke-width="18" stroke-linecap="round"/>
        <ellipse cx="118" cy="38" rx="78" ry="44" fill="#f2c36c"/>
        <circle cx="66" cy="4" r="44" fill="#f5cf7c"/>
        <path d="M40 -32 L24 -72 L70 -48 Z" fill="#b26835"/>
        <circle cx="54" cy="-4" r="6" fill="#1e2a2f"/>
        <ellipse cx="75" cy="10" rx="12" ry="8" fill="#39251e"/>
        <circle cx="-18" cy="80" r="42" fill="#f1f5ef"/>
        <path d="M-44 76 C-18 58 12 58 38 76" fill="none" stroke="#2d6f89" stroke-width="9" stroke-linecap="round"/>
      </g>
"""
    else:
        subject_shape = """
      <g transform="translate(840 520)">
        <ellipse cx="0" cy="24" rx="150" ry="82" fill="#f1c56f"/>
        <circle cx="-74" cy="-38" r="70" fill="#f4d07f"/>
        <circle cx="-102" cy="-48" r="8" fill="#17232a"/>
        <circle cx="-48" cy="-48" r="8" fill="#17232a"/>
        <path d="M-72 -24 C-88 4 -55 4 -72 -24" fill="#6d3d31"/>
        <path d="M104 4 C162 -58 220 -18 222 42" fill="none" stroke="#f1c56f" stroke-width="20" stroke-linecap="round"/>
      </g>
"""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#bfe8df"/>
      <stop offset="0.52" stop-color="#f7dca2"/>
      <stop offset="1" stop-color="#e7a4a0"/>
    </linearGradient>
    <radialGradient id="sun" cx="22%" cy="18%" r="38%">
      <stop offset="0" stop-color="#fff2bd" stop-opacity=".95"/>
      <stop offset="1" stop-color="#fff2bd" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1600" height="900" fill="url(#sky)"/>
  <rect width="1600" height="900" fill="url(#sun)"/>
  <path d="M0 642 C260 572 420 682 670 604 C910 530 1120 590 1600 510 L1600 900 L0 900 Z" fill="#78b978"/>
  <path d="M0 730 C300 650 545 752 790 690 C1060 620 1260 700 1600 646 L1600 900 L0 900 Z" fill="#4f9d71"/>
  <path d="M160 745 C420 690 650 710 900 665 C1080 635 1260 630 1440 654" fill="none" stroke="#eef4d9" stroke-width="18" stroke-linecap="round" opacity=".72"/>
{subject_shape}
  <metadata>subject={escaped_subject}; setting={escaped_setting}; palette={escaped_palette}</metadata>
</svg>
"""
    output_path.write_text(svg, encoding="utf-8")
    return f"/uploads/{output_path.name}"


class DashscopeClient:
    def __init__(self) -> None:
        self.mock_mode = settings.mock_mode or not settings.dashscope_api_key

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.6) -> str:
        if self.mock_mode:
            return self._mock_chat(messages)

        text, err = await asyncio.wait_for(
            asyncio.to_thread(_dashscope_openai_chat, messages, temperature),
            timeout=40,
        )
        if text:
            return text
        raise RuntimeError(f"DashScope 文本调用失败：{err or '未知错误。'}")

    async def vision_praise(self, image_path: Path, user_text: str) -> str:
        if not settings.dashscope_api_key:
            return "图片识别依赖 DashScope 视觉模型，但当前未配置 DASHSCOPE_API_KEY。" + _dashscope_action_hint()
        if OpenAI is None:
            return "图片识别依赖 openai SDK，但当前缺少 openai 依赖。" + _dashscope_action_hint()
        vision_text = None
        vision_err = None
        for attempt in range(2):
            try:
                vision_text, vision_err = await asyncio.wait_for(
                    asyncio.to_thread(_dashscope_openai_vision_praise, image_path, user_text),
                    timeout=35,
                )
                if vision_text:
                    return vision_text

                # Retry once on transient timeout-type failures.
                if vision_err and "超时" in vision_err and attempt == 0:
                    await asyncio.sleep(0.8)
                    continue
                break
            except asyncio.TimeoutError:
                if attempt == 0:
                    await asyncio.sleep(0.8)
                    continue
                return "DashScope 识图失败：网络超时（35秒，已重试1次）。" + _dashscope_action_hint()
            except Exception as exc:
                return f"DashScope 识图失败：{_classify_dashscope_error(exc)}" + _dashscope_action_hint()
        if vision_text:
            return vision_text

        return f"DashScope 识图失败：{vision_err or '未知错误。'}" + _dashscope_action_hint()

    async def scene_prompt_from_image(self, image_path: Path, user_text: str, praise_reply: str) -> str:
        # Prefer visual extraction so uploaded-image background is tied to actual picture content.
        for attempt in range(2):
            try:
                cap_text, cap_err = await asyncio.wait_for(
                    asyncio.to_thread(_dashscope_scene_caption, image_path, user_text, praise_reply),
                    timeout=30,
                )
                if cap_text:
                    return cap_text
                if cap_err and "超时" in cap_err and attempt == 0:
                    await asyncio.sleep(0.6)
                    continue
                break
            except asyncio.TimeoutError:
                if attempt == 0:
                    await asyncio.sleep(0.6)
                    continue
                break
            except Exception:
                break

        # Fallback: still include praise text to keep some semantic relation.
        merged = f"{user_text} {praise_reply}".strip()
        return merged[:140] if merged else user_text

    async def generate_scene_image(self, scene_prompt: str) -> str:
        last_error = ""
        for attempt in range(2):
            try:
                ds_url, ds_err = await asyncio.wait_for(
                    asyncio.to_thread(_dashscope_generate_scene_image, scene_prompt),
                    timeout=40,
                )
                if ds_url:
                    return ds_url
                last_error = ds_err or last_error
                if ds_err and "timeout" in ds_err.lower() and attempt == 0:
                    await asyncio.sleep(0.6)
                    continue
                break
            except asyncio.TimeoutError as exc:
                last_error = str(exc) or "timeout"
                if attempt == 0:
                    await asyncio.sleep(0.6)
                    continue
                break
            except Exception as exc:
                last_error = str(exc)
                break

        # Fallback for continuity if DashScope or the browser cannot reach remote image hosts.
        seed = random.randint(100000, 999999)
        clean_scene = (scene_prompt or "温馨儿童绘本场景").strip()
        if last_error:
            logger.warning("scene image generation fell back to local svg: %s", last_error)
        return _local_scene_image_url(clean_scene, seed)

    async def enroll_custom_voice(self, audio_url: str, prefix: str | None = None) -> tuple[str, str, str | None]:
        if not settings.dashscope_api_key:
            raise RuntimeError("未配置 DASHSCOPE_API_KEY。")
        if dashscope is None or VoiceEnrollmentService is None:
            raise RuntimeError("缺少 dashscope 依赖，无法启用语音克隆。")

        dashscope.base_websocket_api_url = settings.dashscope_base_websocket_api_url
        dashscope.base_http_api_url = settings.dashscope_base_http_api_url
        dashscope.api_key = settings.dashscope_api_key

        req_session = _build_dashscope_requests_session()
        try:
            service = VoiceEnrollmentService(session=req_session)
            with _dashscope_proxy_guard():
                voice_id = await asyncio.to_thread(
                    service.create_voice,
                    target_model=settings.dashscope_tts_model,
                    prefix=(prefix or settings.dashscope_voice_prefix),
                    url=audio_url,
                )

            request_id = None
            try:
                request_id = service.get_last_request_id()
            except Exception:
                request_id = None

            attempts = max(1, settings.dashscope_voice_poll_attempts)
            interval = max(1, settings.dashscope_voice_poll_interval)
            for _ in range(attempts):
                with _dashscope_proxy_guard():
                    info = await asyncio.to_thread(service.query_voice, voice_id=voice_id)
                status = str((info or {}).get("status", ""))
                if status == "OK":
                    return voice_id, status, request_id
                if status == "UNDEPLOYED":
                    raise RuntimeError("声纹训练失败（UNDEPLOYED），请更换清晰的人声样本重试。")
                await asyncio.sleep(interval)

            raise RuntimeError("声纹训练超时，请稍后重试。")
        finally:
            req_session.close()

    async def synthesize_with_voice(self, voice_id: str, text: str, output_path: Path) -> str | None:
        if not settings.dashscope_api_key:
            raise RuntimeError("未配置 DASHSCOPE_API_KEY。")
        if dashscope is None or SpeechSynthesizer is None:
            raise RuntimeError("缺少 dashscope 依赖，无法启用语音合成。")

        dashscope.base_websocket_api_url = settings.dashscope_base_websocket_api_url
        dashscope.base_http_api_url = settings.dashscope_base_http_api_url
        dashscope.api_key = settings.dashscope_api_key

        instruction = (settings.dashscope_tts_instruction or "").strip() or None
        retries = max(1, settings.dashscope_tts_retry_attempts)
        min_audio_bytes = max(1000, settings.dashscope_tts_min_audio_bytes)
        last_error: str | None = None

        for attempt in range(1, retries + 1):
            try:
                proxy_context = _dashscope_tts_proxy_env if settings.dashscope_tts_proxy_url else _dashscope_proxy_guard
                with proxy_context():
                    try:
                        synthesizer = SpeechSynthesizer(
                            model=settings.dashscope_tts_model,
                            voice=voice_id,
                            instruction=instruction,
                            volume=settings.dashscope_tts_volume,
                            speech_rate=settings.dashscope_tts_speech_rate,
                            pitch_rate=settings.dashscope_tts_pitch_rate,
                            seed=settings.dashscope_tts_seed,
                        )
                    except TypeError:
                        synthesizer = SpeechSynthesizer(
                            model=settings.dashscope_tts_model,
                            voice=voice_id,
                            instruction=instruction,
                            volume=settings.dashscope_tts_volume,
                            speech_rate=settings.dashscope_tts_speech_rate,
                            pitch_rate=settings.dashscope_tts_pitch_rate,
                        )
                    audio_data = await asyncio.to_thread(
                        synthesizer.call,
                        text,
                        timeout_millis=settings.dashscope_tts_timeout_millis,
                    )
                if not audio_data:
                    raise RuntimeError("模型未返回音频数据")

                audio_size = len(audio_data)
                request_id = None
                try:
                    request_id = synthesizer.get_last_request_id()
                except Exception:
                    request_id = None

                logger.info(
                    "tts synth done: voice_id=%s request_id=%s bytes=%s attempt=%s",
                    voice_id,
                    request_id,
                    audio_size,
                    attempt,
                )

                if audio_size < min_audio_bytes:
                    raise RuntimeError(f"音频过短({audio_size} bytes)，低于阈值 {min_audio_bytes}")

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(audio_data)
                return request_id
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "tts synth failed: voice_id=%s attempt=%s/%s error=%s",
                    voice_id,
                    attempt,
                    retries,
                    last_error,
                )
                if attempt < retries:
                    await asyncio.sleep(min(4.0, 1.25 * attempt))

        raise RuntimeError(f"语音合成失败：{last_error or '未知错误'}")

    def _mock_chat(self, messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"] if messages else ""
        return (
            "我在呢，听你说我很开心。"
            f"你刚刚提到‘{last[:24]}’，可以再告诉我当时最让你在意的一个细节吗？"
        )
