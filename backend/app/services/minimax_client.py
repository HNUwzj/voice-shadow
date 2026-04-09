from __future__ import annotations

import asyncio
import base64
import os
import random
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from PIL import Image, ImageFilter, ImageStat

try:
    import dashscope
    from dashscope.aigc.image_generation import ImageGeneration
    from dashscope.api_entities.dashscope_response import Message
except Exception:  # pragma: no cover - optional dependency
    dashscope = None
    ImageGeneration = None
    Message = None

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - optional dependency
    genai = None

try:
    from google import genai as genai_new
    from google.genai import types as genai_types
except Exception:  # pragma: no cover - optional dependency
    genai_new = None
    genai_types = None

from app.config import settings


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


def _classify_gemini_error(err: Exception) -> str:
    msg = str(err).strip()
    low = msg.lower()

    if any(k in low for k in ["connection refused", "failed to establish", "proxy", "10061", "127.0.0.1:7897"]):
        return "本地代理不可用，请确认代理已开启且端口为 127.0.0.1:7897。"
    if any(k in low for k in ["timed out", "timeout", "deadline", "readtimeout", "connecttimeout"]):
        return "网络超时，请检查网络后重试。"
    if any(k in low for k in ["api key", "invalid", "permission denied", "unauthorized", "403", "401"]):
        return "API Key 无效或无权限，请到 AI Studio 检查 KEY 和项目权限。"
    if any(k in low for k in ["quota", "resource exhausted", "429", "rate limit", "too many requests"]):
        return "请求配额不足或触发限流，请到 AI Studio 检查配额/套餐后重试。"
    if any(k in low for k in ["location", "region", "country", "not available"]):
        return "当前网络区域暂不可用 Gemini 视觉能力。"
    if not msg:
        return "未知错误。"
    return f"{msg[:140]}"


def _gemini_action_hint() -> str:
    return (
        "排查建议："
        "1) 打开 https://aistudio.google.com/app/apikey 检查 KEY 是否可用；"
        "2) 打开 https://ai.google.dev/gemini-api/docs/models 查看当前可用模型；"
        "3) 打开 https://ai.google.dev/gemini-api/docs/rate-limits 检查配额与限流。"
    )


@contextmanager
def _gemini_proxy_env():
    proxy = "http://127.0.0.1:7897"
    keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"]
    prev = {k: os.environ.get(k) for k in keys}

    # Force Gemini request through local proxy, while keeping localhost direct.
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


def _gemini_vision_praise(image_path: Path, user_text: str) -> tuple[str | None, str | None]:
    if not settings.google_api_key:
        return None, "未配置 GOOGLE_API_KEY。"
    if genai is None:
        return None, "缺少 google-generativeai 依赖。"

    prompt = (
        "你是孩子的爸爸妈妈。"
        "请基于图片内容和孩子的话，输出2-4句中文口语化夸奖。"
        "要求具体提到画面里看到的内容，不要编造未出现的元素，不要提文件大小。"
        f"孩子的话：{user_text}"
    )

    candidates = [
        settings.google_vision_model,
        "models/gemini-2.5-flash",
        "models/gemini-flash-latest",
        "models/gemini-2.0-flash",
        "models/gemini-2.0-flash-001",
        "models/gemini-2.0-flash-lite-001",
        "models/gemini-2.0-flash-lite",
        "models/gemini-pro-latest",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash-latest",
        "models/gemini-1.5-flash",
    ]
    # Keep order and remove duplicates/empty values.
    seen: set[str] = set()
    model_names: list[str] = []
    for item in candidates:
        name = (item or "").strip()
        if name and name not in seen:
            seen.add(name)
            model_names.append(name)

    last_error: Exception | None = None
    try:
        with _gemini_proxy_env():
            genai.configure(api_key=settings.google_api_key)
            with Image.open(image_path) as img:
                rgb = img.convert("RGB")
                # Reduce payload size to lower request latency and timeout probability.
                rgb.thumbnail((1280, 1280))

            for model_name in model_names:
                try:
                    model = genai.GenerativeModel(model_name)
                    resp = model.generate_content([prompt, rgb], request_options={"timeout": 30})
                    text = getattr(resp, "text", "")
                    if isinstance(text, str) and text.strip():
                        return text.strip(), None
                except Exception as exc:
                    last_error = exc
                    # Try next model if this model is unsupported.
                    if "not found" in str(exc).lower() or "not supported" in str(exc).lower():
                        continue
                    break
    except Exception as exc:
        return None, _classify_gemini_error(exc)

    if last_error is not None:
        return None, _classify_gemini_error(last_error)
    return None, "Gemini 返回空结果。"

    return None, "未知错误。"


def _gemini_scene_caption(image_path: Path, user_text: str, praise_reply: str) -> tuple[str | None, str | None]:
    if not settings.google_api_key:
        return None, "未配置 GOOGLE_API_KEY。"
    if genai is None:
        return None, "缺少 google-generativeai 依赖。"

    prompt = (
        "You are extracting visual scene keywords for image generation. "
        "Based on the image and child text, return ONE short line in English only. "
        "Strict format: subject=<main object>;setting=<environment>;palette=<3 colors>. "
        "No extra words, no markdown. "
        f"Child text: {user_text}. "
        f"Parent praise: {praise_reply}"
    )

    candidates = [
        settings.google_vision_model,
        "models/gemini-2.5-flash",
        "models/gemini-flash-latest",
        "models/gemini-2.0-flash",
        "models/gemini-2.0-flash-001",
    ]
    seen: set[str] = set()
    model_names: list[str] = []
    for item in candidates:
        name = (item or "").strip()
        if name and name not in seen:
            seen.add(name)
            model_names.append(name)

    last_error: Exception | None = None
    try:
        with _gemini_proxy_env():
            genai.configure(api_key=settings.google_api_key)
            with Image.open(image_path) as img:
                rgb = img.convert("RGB")
                rgb.thumbnail((1280, 1280))

            for model_name in model_names:
                try:
                    model = genai.GenerativeModel(model_name)
                    resp = model.generate_content([prompt, rgb], request_options={"timeout": 25})
                    text = getattr(resp, "text", "")
                    if isinstance(text, str) and text.strip():
                        line = re.sub(r"\s+", " ", text.strip())
                        return line[:180], None
                except Exception as exc:
                    last_error = exc
                    if "not found" in str(exc).lower() or "not supported" in str(exc).lower():
                        continue
                    break
    except Exception as exc:
        return None, _classify_gemini_error(exc)

    if last_error is not None:
        return None, _classify_gemini_error(last_error)
    return None, "Gemini 返回空结果。"


def _extract_gemini_image_part(resp: Any) -> tuple[bytes, str] | None:
    def _extract(parts: list[Any]) -> tuple[bytes, str] | None:
        for part in parts:
            inline = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
            if not inline:
                continue
            data = getattr(inline, "data", None)
            mime = getattr(inline, "mime_type", None) or getattr(inline, "mimeType", None) or "image/png"
            if isinstance(data, bytes) and data:
                return data, mime
            if isinstance(data, bytearray) and data:
                return bytes(data), mime
            if isinstance(data, str) and data:
                try:
                    return base64.b64decode(data), mime
                except Exception:
                    continue
        return None

    top_parts = getattr(resp, "parts", None)
    if isinstance(top_parts, list):
        result = _extract(top_parts)
        if result:
            return result

    candidates = getattr(resp, "candidates", None)
    if isinstance(candidates, list):
        for cand in candidates:
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", None) if content is not None else None
            if isinstance(parts, list):
                result = _extract(parts)
                if result:
                    return result
    return None


def _gemini_generate_scene_image(scene_prompt: str) -> tuple[str | None, str | None]:
    if not settings.google_api_key:
        return None, "未配置 GOOGLE_API_KEY。"
    if genai_new is None or genai_types is None:
        return None, "缺少 google-genai 依赖。"

    prompt = (
        "Create one cinematic child-friendly background illustration with NO text. "
        "Soft natural light, storybook painting style, 16:9 composition, high detail. "
        f"Scene requirement: {scene_prompt}."
    )

    # Preferred path: official Imagen image generation models.
    image_candidates = [
        settings.google_scene_model,
        "models/imagen-4.0-fast-generate-001",
        "models/imagen-4.0-generate-001",
        "models/imagen-4.0-ultra-generate-001",
    ]

    # Fallback path: Gemini image-capable models via generate_content.
    content_candidates = [
        settings.google_scene_model,
        "models/gemini-2.5-flash-image",
        "models/gemini-3.1-flash-image-preview",
        "models/gemini-3-pro-image-preview",
    ]

    seen: set[str] = set()
    image_models: list[str] = []
    for item in image_candidates:
        name = (item or "").strip()
        if name and name not in seen:
            seen.add(name)
            image_models.append(name)

    seen_content: set[str] = set()
    content_models: list[str] = []
    for item in content_candidates:
        name = (item or "").strip()
        if name and name not in seen_content:
            seen_content.add(name)
            content_models.append(name)

    last_error: Exception | None = None
    try:
        with _gemini_proxy_env():
            client = genai_new.Client(api_key=settings.google_api_key)

            for model_name in image_models:
                try:
                    result = client.models.generate_images(
                        model=model_name,
                        prompt=prompt,
                        config={"number_of_images": 1, "output_mime_type": "image/jpeg", "aspect_ratio": "16:9"},
                    )
                    generated = getattr(result, "generated_images", None) or []
                    if generated:
                        image_obj = getattr(generated[0], "image", None)
                        image_bytes = getattr(image_obj, "image_bytes", None) if image_obj is not None else None
                        if isinstance(image_bytes, bytes) and image_bytes:
                            b64 = base64.b64encode(image_bytes).decode("ascii")
                            return f"data:image/jpeg;base64,{b64}", None
                except Exception as exc:
                    last_error = exc
                    msg = str(exc).lower()
                    if "not found" in msg or "not supported" in msg:
                        continue
                    if "paid plan" in msg or "resource_exhausted" in msg or "quota" in msg:
                        continue
                    break

            for model_name in content_models:
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
                    )
                    image_part = _extract_gemini_image_part(resp)
                    if image_part:
                        image_bytes, mime = image_part
                        b64 = base64.b64encode(image_bytes).decode("ascii")
                        return f"data:{mime};base64,{b64}", None
                except Exception as exc:
                    last_error = exc
                    msg = str(exc).lower()
                    if "not found" in msg or "not supported" in msg:
                        continue
                    break
    except Exception as exc:
        return None, _classify_gemini_error(exc)

    if last_error is not None:
        return None, _classify_gemini_error(last_error)
    return None, "Gemini 未返回图片。"


def _rgb_to_color_name(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    if r > 200 and g > 180 and b < 120:
        return "明亮的黄色"
    if r > 200 and g > 120 and b < 100:
        return "温暖的橙色"
    if g > 140 and r < 140 and b < 140:
        return "清新的绿色"
    if b > 150 and r < 140 and g < 170:
        return "干净的蓝色"
    if r > 200 and b > 180 and g < 170:
        return "柔和的粉色"
    if r > 170 and g > 170 and b > 170:
        return "明亮的浅色"
    if r < 80 and g < 80 and b < 80:
        return "沉稳的深色"
    return "丰富的综合色彩"


def _local_image_praise(image_path: Path, user_text: str) -> str:
    try:
        with Image.open(image_path) as img:
            rgb = img.convert("RGB")
            w, h = rgb.size
            stat = ImageStat.Stat(rgb)
            avg_rgb = tuple(int(v) for v in stat.mean[:3])
            brightness = sum(avg_rgb) / 3

            # Use adaptive palette to capture dominant tones.
            palette_img = rgb.resize((256, 256)).convert("P", palette=Image.Palette.ADAPTIVE, colors=4)
            palette = palette_img.getpalette() or []
            color_counts = sorted(palette_img.getcolors() or [], reverse=True)

            top_colors: list[str] = []
            for _, idx in color_counts[:3]:
                base = idx * 3
                if base + 2 < len(palette):
                    name = _rgb_to_color_name((palette[base], palette[base + 1], palette[base + 2]))
                    if name not in top_colors:
                        top_colors.append(name)
            if not top_colors:
                top_colors = [_rgb_to_color_name(avg_rgb)]

            edge_stat = ImageStat.Stat(rgb.convert("L").filter(ImageFilter.FIND_EDGES))
            edge_strength = edge_stat.mean[0]

    except Exception:
        return (
            "宝贝，图片爸爸妈妈收到了。"
            "这次自动识别没完全成功，但你愿意分享就已经很棒了。"
            "你告诉爸爸妈妈你画了什么细节，我会认真夸你。"
        )

    orientation = "横向构图" if w >= h else "纵向构图"
    light_desc = "画面很明亮" if brightness >= 165 else ("明暗层次很舒服" if brightness >= 115 else "整体用色偏沉稳")
    detail_desc = "细节线条很多" if edge_strength >= 24 else ("细节安排很整齐" if edge_strength >= 14 else "画面很干净")
    color_desc = "、".join(top_colors[:3])

    return (
        "宝贝，爸爸妈妈认真看了你的画。"
        f"我看到画面是{orientation}，主色有{color_desc}，{light_desc}。"
        f"而且{detail_desc}，能看出来你画的时候很投入。"
        f"你刚刚还说“{user_text}”，愿意分享作品这件事本身就特别棒。"
    )


def _scene_label_and_emoji(scene_prompt: str) -> tuple[str, str]:
    mapping = [
        ("大黄狗", "大黄狗", "🐕"),
        ("小狗", "小狗", "🐶"),
        ("狗", "小狗", "🐕"),
        ("蝴蝶", "蝴蝶", "🦋"),
        ("大黄猫", "大黄猫", "🐈"),
        ("小猫", "小猫", "🐱"),
        ("猫", "小猫", "🐱"),
        ("鸟", "小鸟", "🐦"),
        ("兔", "兔子", "🐰"),
        ("鱼", "小鱼", "🐟"),
        ("花", "花朵", "🌼"),
        ("树", "树林", "🌳"),
        ("天空", "天空", "☁️"),
        ("雨", "小雨", "🌧️"),
    ]
    for key, label, emoji in mapping:
        if key in scene_prompt:
            return label, emoji

    low = scene_prompt.lower()
    en_map = [
        ("dog", "dog", "🐕"),
        ("puppy", "puppy", "🐶"),
        ("cat", "cat", "🐱"),
        ("butterfly", "butterfly", "🦋"),
        ("bird", "bird", "🐦"),
        ("rabbit", "rabbit", "🐰"),
        ("fish", "fish", "🐟"),
        ("flower", "flower", "🌼"),
        ("forest", "forest", "🌳"),
        ("sky", "sky", "☁️"),
        ("rain", "rain", "🌧️"),
    ]
    for key, label, emoji in en_map:
        if key in low:
            return label, emoji

    return "温馨陪伴", "✨"


def _scene_subject_spec(scene_prompt: str) -> tuple[str, str, str]:
    low = scene_prompt.lower()

    # Prioritize concrete visible objects to avoid generic landscape outputs.
    mapping = [
        (["大黄狗", "黄狗", "dog", "puppy"], "a big yellow dog", "park lawn with warm sunlight", "golden, green, soft sky blue"),
        (["蝴蝶", "butterfly"], "a colorful butterfly", "flower field in spring", "orange, cyan, pink"),
        (["大黄猫", "小猫", "猫", "cat", "kitten"], "a big yellow cat", "quiet neighborhood path", "honey yellow, mint green, cream"),
        (["鸟", "bird"], "a small bird", "tree branch in a gentle park", "leaf green, sky blue, warm beige"),
        (["兔", "rabbit", "bunny"], "a white rabbit", "meadow near wildflowers", "green, white, peach"),
        (["鱼", "fish"], "a little fish", "clear stream with stones", "aqua, teal, silver"),
        (["花", "flower"], "bright flowers", "garden path", "coral, yellow, leaf green"),
    ]

    for keys, subject, setting, palette in mapping:
        if any(k in scene_prompt for k in keys if any(ord(ch) > 127 for ch in k)) or any(k in low for k in keys if k.isascii()):
            return subject, setting, palette

    return "a child-friendly outdoor scene", "cozy neighborhood at sunset", "warm orange, soft green, gentle blue"


def _scene_object_illustration(label: str) -> str:
    if label in {"大黄狗", "小狗", "dog", "puppy"}:
        return (
            "<g transform='translate(860,390)'>"
            "<ellipse cx='210' cy='165' rx='150' ry='76' fill='rgba(244,188,104,0.78)'/>"
            "<circle cx='84' cy='142' r='54' fill='rgba(244,188,104,0.82)'/>"
            "<polygon points='52,92 74,60 86,106' fill='rgba(224,160,82,0.9)'/>"
            "<circle cx='98' cy='138' r='6' fill='rgba(62,43,30,0.9)'/>"
            "<path d='M278 132 Q334 88 360 132' stroke='rgba(244,188,104,0.86)' stroke-width='18' fill='none' stroke-linecap='round'/>"
            "<rect x='148' y='220' width='24' height='74' rx='11' fill='rgba(234,177,96,0.9)'/>"
            "<rect x='206' y='220' width='24' height='74' rx='11' fill='rgba(234,177,96,0.9)'/>"
            "<rect x='258' y='220' width='24' height='74' rx='11' fill='rgba(234,177,96,0.9)'/>"
            "<rect x='304' y='220' width='24' height='74' rx='11' fill='rgba(234,177,96,0.9)'/>"
            "</g>"
        )

    if label in {"蝴蝶", "butterfly"}:
        return (
            "<g transform='translate(920,330)'>"
            "<ellipse cx='110' cy='120' rx='70' ry='88' fill='rgba(126,208,255,0.56)'/>"
            "<ellipse cx='198' cy='120' rx='70' ry='88' fill='rgba(255,175,220,0.56)'/>"
            "<ellipse cx='128' cy='198' rx='56' ry='64' fill='rgba(98,196,170,0.52)'/>"
            "<ellipse cx='178' cy='198' rx='56' ry='64' fill='rgba(255,212,118,0.52)'/>"
            "<rect x='148' y='98' width='14' height='132' rx='7' fill='rgba(64,54,74,0.85)'/>"
            "<path d='M155 98 Q136 58 118 42' stroke='rgba(64,54,74,0.78)' stroke-width='4' fill='none'/>"
            "<path d='M155 98 Q174 58 194 42' stroke='rgba(64,54,74,0.78)' stroke-width='4' fill='none'/>"
            "</g>"
        )

    if label in {"大黄猫", "小猫", "cat"}:
        return (
            "<g transform='translate(900,380)'>"
            "<ellipse cx='186' cy='158' rx='124' ry='72' fill='rgba(245,179,116,0.78)'/>"
            "<circle cx='94' cy='132' r='50' fill='rgba(245,179,116,0.82)'/>"
            "<polygon points='66,90 86,58 96,100' fill='rgba(225,151,89,0.9)'/>"
            "<polygon points='104,100 116,58 136,90' fill='rgba(225,151,89,0.9)'/>"
            "<path d='M276 146 Q340 122 334 198' stroke='rgba(245,179,116,0.88)' stroke-width='14' fill='none' stroke-linecap='round'/>"
            "<rect x='142' y='212' width='22' height='66' rx='10' fill='rgba(232,167,104,0.92)'/>"
            "<rect x='196' y='212' width='22' height='66' rx='10' fill='rgba(232,167,104,0.92)'/>"
            "</g>"
        )

    return (
        "<g transform='translate(980,420)'>"
        "<circle cx='110' cy='110' r='92' fill='rgba(255,255,255,0.16)'/>"
        "<circle cx='110' cy='110' r='64' fill='rgba(255,255,255,0.22)'/>"
        "</g>"
    )


def _svg_scene_data_url(scene_prompt: str) -> str:
    label, emoji = _scene_label_and_emoji(scene_prompt)
    seed = random.randint(100000, 999999)
    hue = seed % 360
    c1 = f"hsl({hue},72%,30%)"
    c2 = f"hsl({(hue + 38) % 360},58%,24%)"
    c3 = f"hsl({(hue + 86) % 360},46%,16%)"
    hill1 = f"hsl({(hue + 18) % 360},40%,30%)"
    hill2 = f"hsl({(hue + 46) % 360},35%,24%)"
    grass = f"hsl({(hue + 95) % 360},44%,24%)"
    deco = _scene_object_illustration(label)
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='700' viewBox='0 0 1200 700'>"
        "<defs>"
        f"<linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'><stop offset='0%' stop-color='{c1}'/><stop offset='50%' stop-color='{c2}'/><stop offset='100%' stop-color='{c3}'/></linearGradient>"
        "<filter id='blur32' x='-20%' y='-20%' width='140%' height='140%'><feGaussianBlur stdDeviation='18'/></filter>"
        "</defs>"
        "<rect width='1200' height='700' fill='url(#bg)'/>"
        "<circle cx='1040' cy='110' r='134' fill='rgba(255,241,183,0.26)'/>"
        "<ellipse cx='940' cy='95' rx='160' ry='56' fill='rgba(255,255,255,0.07)'/>"
        "<ellipse cx='312' cy='124' rx='130' ry='46' fill='rgba(255,255,255,0.08)'/>"
        "<ellipse cx='686' cy='136' rx='112' ry='38' fill='rgba(255,255,255,0.06)'/>"
        f"<path d='M0 430 C160 320, 350 318, 540 430 C700 514, 860 516, 1200 400 L1200 700 L0 700 Z' fill='{hill2}' opacity='0.72'/>"
        f"<path d='M0 478 C190 390, 396 396, 610 476 C760 532, 960 546, 1200 470 L1200 700 L0 700 Z' fill='{hill1}' opacity='0.78'/>"
        f"<path d='M0 540 C220 492, 450 502, 700 552 C890 590, 1030 578, 1200 545 L1200 700 L0 700 Z' fill='{grass}' opacity='0.86'/>"
        "<circle cx='1062' cy='450' r='118' fill='rgba(255,214,162,0.16)' filter='url(#blur32)'/>"
        "<circle cx='196' cy='604' r='146' fill='rgba(147,227,194,0.12)' filter='url(#blur32)'/>"
        f"{deco}"
        f"<text x='1042' y='170' font-size='48' fill='rgba(255,255,255,0.18)'>{emoji}</text>"
        "</svg>"
    )
    return f"data:image/svg+xml;charset=UTF-8,{quote(svg)}#s={seed}"


class MinimaxClient:
    def __init__(self) -> None:
        self.base_url = settings.minimax_base_url.rstrip("/")
        self.api_key = settings.minimax_api_key
        self.model = settings.minimax_model
        self.mock_mode = settings.mock_mode or not self.api_key

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.6) -> str:
        if self.mock_mode:
            return self._mock_chat(messages)

        url = f"{self.base_url}/text/chatcompletion_v2"
        minimax_messages: list[dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role not in {"system", "user", "assistant"}:
                role = "user"
            minimax_messages.append(
                {
                    "role": role,
                    "name": "设定" if role == "system" else ("MiniMax AI" if role == "assistant" else "用户"),
                    "content": content,
                }
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": minimax_messages,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"Minimax chat failed: {resp.status_code} {resp.text}") from exc
            data = resp.json()
        base_resp = data.get("base_resp") or {}
        if base_resp.get("status_code", 0) not in (0, None):
            raise RuntimeError(f"Minimax chat failed: {base_resp}")

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Minimax chat empty choices: {data}")

        message = choices[0].get("message") or {}
        return message.get("content", "我在呢，继续和我说说吧。")

    async def vision_praise(self, image_path: Path, user_text: str) -> str:
        if not settings.google_api_key:
            return "图片识别仅支持 Gemini，但当前未配置 GOOGLE_API_KEY。" + _gemini_action_hint()
        if genai is None:
            return "图片识别仅支持 Gemini，但缺少 google-generativeai 依赖。" + _gemini_action_hint()
        gemini_text = None
        gemini_err = None
        for attempt in range(2):
            try:
                gemini_text, gemini_err = await asyncio.wait_for(
                    asyncio.to_thread(_gemini_vision_praise, image_path, user_text),
                    timeout=35,
                )
                if gemini_text:
                    return gemini_text

                # Retry once on transient timeout-type failures.
                if gemini_err and "超时" in gemini_err and attempt == 0:
                    await asyncio.sleep(0.8)
                    continue
                break
            except asyncio.TimeoutError:
                if attempt == 0:
                    await asyncio.sleep(0.8)
                    continue
                return "Gemini 识图失败：网络超时（35秒，已重试1次）。" + _gemini_action_hint()
            except Exception as exc:
                return f"Gemini 识图失败：{_classify_gemini_error(exc)}" + _gemini_action_hint()
        if gemini_text:
            return gemini_text

        return f"Gemini 识图失败：{gemini_err or '未知错误。'}" + _gemini_action_hint()

    async def scene_prompt_from_image(self, image_path: Path, user_text: str, praise_reply: str) -> str:
        # Prefer Gemini visual extraction so uploaded-image background is tied to actual picture content.
        for attempt in range(2):
            try:
                cap_text, cap_err = await asyncio.wait_for(
                    asyncio.to_thread(_gemini_scene_caption, image_path, user_text, praise_reply),
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
        for attempt in range(2):
            try:
                ds_url, ds_err = await asyncio.wait_for(
                    asyncio.to_thread(_dashscope_generate_scene_image, scene_prompt),
                    timeout=40,
                )
                if ds_url:
                    return ds_url
                if ds_err and "timeout" in ds_err.lower() and attempt == 0:
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

        # Fallback for development continuity if DashScope is temporarily unavailable.
        seed = random.randint(100000, 999999)
        clean_scene = (scene_prompt or "温馨儿童绘本场景").strip()
        subject, setting, palette = _scene_subject_spec(clean_scene)
        prompt = (
            "children storybook illustration, 2d hand-painted background, "
            f"main subject: {subject}, "
            f"scene setting: {setting}, "
            f"palette: {palette}, "
            "single clear focal object, rich details, gentle depth, no text, no logo, not abstract, "
            f"extra context: {clean_scene}"
        )
        return (
            f"https://image.pollinations.ai/prompt/{quote(prompt)}"
            f"?width=1600&height=900&nologo=true&seed={seed}&model=flux"
        )

    @staticmethod
    def _extract_image_url(data: dict[str, Any]) -> str | None:
        if isinstance(data.get("image_url"), str):
            return data["image_url"]

        items = data.get("data")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                for key in ("url", "image_url", "imageUrl", "link"):
                    val = first.get(key)
                    if isinstance(val, str) and val:
                        return val
            if isinstance(first, str) and first:
                return first
        return None

    def _mock_chat(self, messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"] if messages else ""
        return (
            "我在呢，听你说我很开心。"
            f"你刚刚提到‘{last[:24]}’，可以再告诉我当时最让你在意的一个细节吗？"
        )
