from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import re
import shutil
from urllib.error import URLError, HTTPError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import FastAPI, File, Form, HTTPException, Request as FastAPIRequest, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import (
    ChatRequest,
    ChatResponse,
    ConversationItem,
    ConversationListResponse,
    DailyReportResponse,
    PraiseResponse,
    VoiceDeleteResponse,
    VoiceEnrollResponse,
    VoiceListResponse,
    VoiceItem,
    VoiceSynthesizeRequest,
    VoiceSynthesizeResponse,
)
from app.services.analysis import analyze_psych_signal
from app.services.cpolar_tunnel import cpolar_tunnel_manager
from app.services.dashscope_client import DashscopeClient
from app.services.json_store import JsonStore
from app.services.reporting import build_daily_report

app = FastAPI(title="双向陪伴助手", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = JsonStore(settings.data_dir)
client = DashscopeClient()
upload_dir = Path(settings.data_dir) / "uploads"
upload_dir.mkdir(parents=True, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")

PARENT_STYLE_RULES = """
你必须像孩子的真实父母说话，不要像心理咨询师或客服。
表达规则：
1) 首句先称呼孩子：宝贝、宝宝、孩子（任选其一），语气要亲。
2) 句子简短、口语化，每次回复控制在 2-5 句。
3) 先共情，再追问一个小问题，不要连续追问。
4) 多用生活化细节和具体鼓励，少用抽象大道理。
5) 不要使用“建议你、根据你的描述、我理解你、请提供更多信息”等咨询腔。
6) 当孩子提到被欺负/霸凌时，先安抚，再给出一个可执行的小动作（例如：先告诉老师/先离开现场/先找信任的同学），语气仍要像家长。
7) 涉及第一人称时不要用“我”，统一用“爸爸妈妈”。
""".strip()


_SEE_PATTERNS = [
    r"(?:看见|看到|见到|遇到|发现)(?:了)?(?P<object>.{1,14}?)(?:[，。！？!?,]|$)",
    r"(?:路上有|路边有)(?P<object>.{1,14}?)(?:[，。！？!?,]|$)",
    r"(?:i\s+saw|i\s+met|i\s+found)\s+(?P<object>[a-zA-Z\s]{1,24}?)(?:[\.,!?]|$)",
]


def _extract_seen_object(text: str) -> str | None:
    for pattern in _SEE_PATTERNS:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        obj = m.group("object").strip()
        obj = re.sub(r"^(一只|一条|一头|一个|一位|一群)", "", obj)
        obj = re.sub(r"^(a|an|the)\s+", "", obj, flags=re.IGNORECASE)
        obj = obj.strip("，。！？!?, ")
        if obj:
            if obj.isascii():
                obj = re.sub(r"\s+", " ", obj).strip()
                if len(obj) > 32:
                    clipped = obj[:32]
                    last_space = clipped.rfind(" ")
                    obj = clipped[:last_space] if last_space > 0 else clipped
            else:
                obj = obj[:14]
            return obj
    return None


def _normalize_parent_first_person(text: str) -> str:
    # Product requirement: parent avatar should use "爸爸妈妈" instead of first-person pronouns.
    text = re.sub(r"\bI\b", "爸爸妈妈", text)
    text = text.replace("咱们", "爸爸妈妈")
    text = text.replace("我们", "爸爸妈妈")
    text = text.replace("我", "爸爸妈妈")
    return text


def _prepare_tts_text(text: str) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return ""

    # Clone voice may rush the first repeated syllables at utterance start.
    # Use a steadier vocative only for TTS while keeping on-screen text unchanged.
    clean = re.sub(r"^(宝贝|宝宝)([，,。！？!？]*)", "小宝贝，", clean)
    return clean


def _build_scene_prompt(text: str) -> str:
    obj = _extract_seen_object(text)
    if obj:
        return (
            "温馨儿童绘本插画，暖色自然光，柔和笔触，"
            f"孩子在放学路上看见{obj}，画面温暖治愈，亲子陪伴氛围"
        )
    return f"温馨儿童绘本插画，暖色自然光，柔和笔触，场景来自这句话：{text}"


def _should_update_scene(text: str) -> bool:
    # Only switch background when the child is describing seen scene/object.
    return _extract_seen_object(text) is not None


def _normalize_voice_prefix(child_id: str, prefix: str | None) -> str:
    raw = (prefix or "").strip()
    if not raw:
        raw = f"{settings.dashscope_voice_prefix}{child_id}"

    # DashScope requires prefix to be strictly english letters and numbers.
    normalized = re.sub(r"[^A-Za-z0-9]+", "", raw)
    if not normalized:
        normalized = f"voice{datetime.now().strftime('%H%M%S')}"

    if not normalized[0].isalpha():
        normalized = f"v{normalized}"

    return normalized[:10]


def _is_retryable_voice_enroll_error(message: str) -> bool:
    low = (message or "").lower()
    retry_keys = [
        "inputdownloadfailed",
        "download audio failed",
        "internalerror",
        "i/o timeout",
        "timeout",
        "temporar",
        "connection reset",
    ]
    return any(k in low for k in retry_keys)


def _probe_public_audio_url(url: str) -> str | None:
    req = UrlRequest(url, method="GET")
    try:
        with urlopen(req, timeout=8) as resp:
            status = int(getattr(resp, "status", 200))
            if 200 <= status < 300:
                return None
            return f"HTTP {status}"
    except HTTPError as exc:
        return f"HTTP {exc.code}"
    except URLError as exc:
        return f"URL 错误: {exc.reason}"
    except Exception as exc:
        return str(exc)


async def _auto_tts_reply(child_id: str, text: str) -> str | None:
    latest = store.latest_voice(child_id)
    if latest is None:
        return None
    voice_id = str(latest.get("voice_id", "")).strip()
    if not voice_id:
        return None

    output_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{child_id}_reply_tts.mp3"
    output_path = upload_dir / output_name
    tts_text = _prepare_tts_text(text)
    if not tts_text:
        return None
    try:
        await client.synthesize_with_voice(voice_id, tts_text, output_path)
        return f"/uploads/{output_name}"
    except Exception:
        return None


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "mock_mode": client.mock_mode}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    timestamp = datetime.now()
    history = store.conversation_tail(req.child_id, limit=8)

    system_prompt = f"{settings.parent_persona}\n\n{PARENT_STYLE_RULES}"
    messages = [{"role": "system", "content": system_prompt}]
    for item in history:
        messages.append({"role": item.get("role", "user"), "content": item.get("content", "")})
    messages.append({"role": "user", "content": req.message})

    try:
        reply = await client.chat(messages)
    except Exception:
        # Keep the conversation available even when upstream model or billing is unavailable.
        reply = (
            "我在呢，刚刚网络有点抖动。"
            f"你提到‘{req.message[:20]}’，这件事听起来对你很重要，愿意再多说一点吗？"
        )
    reply = _normalize_parent_first_person(reply)
    scene_image_url = None
    assistant_audio_url = await _auto_tts_reply(req.child_id, reply)

    store.append(
        "conversations",
        {
            "child_id": req.child_id,
            "role": "user",
            "content": req.message,
            "timestamp": store.now_iso(),
        },
    )
    store.append(
        "conversations",
        {
            "child_id": req.child_id,
            "role": "assistant",
            "content": reply,
            "audio_url": assistant_audio_url,
            "timestamp": store.now_iso(),
        },
    )

    if req.enable_psych_analysis:
        signal = await analyze_psych_signal(client, req.message)
        store.append(
            "analyses",
            {
                "child_id": req.child_id,
                "timestamp": store.now_iso(),
                **signal.model_dump(),
            },
        )

    if req.enable_scene and _should_update_scene(req.message):
        scene_prompt = _build_scene_prompt(req.message)
        scene_image_url = await client.generate_scene_image(scene_prompt)

    return ChatResponse(
        reply=reply,
        scene_image_url=scene_image_url,
        assistant_audio_url=assistant_audio_url,
        timestamp=timestamp,
    )


@app.post("/api/praise-image", response_model=PraiseResponse)
async def praise_image(
    image: UploadFile = File(...),
    child_id: str = Form("default-child"),
    text: str = Form("看我画的"),
) -> PraiseResponse:
    ext = Path(image.filename or "image.jpg").suffix or ".jpg"
    image_path = upload_dir / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{child_id}{ext}"
    image_path.write_bytes(await image.read())
    public_image_url = f"/uploads/{image_path.name}"

    reply = await client.vision_praise(image_path, text)
    scene_image_url = None
    assistant_audio_url = await _auto_tts_reply(child_id, reply)
    if _should_update_scene(text):
        scene_prompt = await client.scene_prompt_from_image(image_path, text, reply)
        scene_image_url = await client.generate_scene_image(scene_prompt)

    store.append(
        "conversations",
        {
            "child_id": child_id,
            "role": "user",
            "content": text,
            "message_type": "image",
            "image_url": public_image_url,
            "timestamp": store.now_iso(),
        },
    )
    store.append(
        "conversations",
        {
            "child_id": child_id,
            "role": "assistant",
            "content": reply,
            "audio_url": assistant_audio_url,
            "timestamp": store.now_iso(),
        },
    )

    return PraiseResponse(
        reply=reply,
        image_url=public_image_url,
        scene_image_url=scene_image_url,
        assistant_audio_url=assistant_audio_url,
        details={"filename": image_path.name, "size": image_path.stat().st_size},
    )


@app.post("/api/voice/enroll", response_model=VoiceEnrollResponse)
async def enroll_voice(
    request: FastAPIRequest,
    audio: UploadFile = File(...),
    child_id: str = Form("default-child"),
    prefix: str | None = Form(None),
) -> VoiceEnrollResponse:
    ext = Path(audio.filename or "voice.wav").suffix or ".wav"
    audio_path = upload_dir / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{child_id}_voice{ext}"
    audio_path.write_bytes(await audio.read())
    public_sample_url = f"/uploads/{audio_path.name}"

    display_name = (prefix or "").strip()
    safe_prefix = _normalize_voice_prefix(child_id, prefix)
    local_port = int(getattr(request.url, "port", None) or 8001)
    retries = max(1, settings.dashscope_voice_enroll_retry_attempts)

    voice_id = ""
    status = ""
    request_id = None
    audio_url_for_dashscope = ""
    last_error = ""

    for attempt in range(1, retries + 1):
        force_refresh_tunnel = (
            settings.cpolar_auto_tunnel
            and attempt > 1
            and (
                "公网样本地址不可访问" in last_error
                or "inputdownloadfailed" in last_error.lower()
                or "download audio failed" in last_error.lower()
            )
        )
        try:
            if settings.cpolar_auto_tunnel:
                base_url = await asyncio.to_thread(
                    cpolar_tunnel_manager.ensure_public_base_url,
                    local_port,
                    force_refresh_tunnel,
                )
            elif settings.public_asset_base_url.strip():
                base_url = settings.public_asset_base_url.strip().rstrip("/")
            else:
                base_url = str(request.base_url).rstrip("/")

            audio_url_for_dashscope = f"{base_url}{public_sample_url}"
            if settings.cpolar_auto_tunnel:
                probe_err = await asyncio.to_thread(_probe_public_audio_url, audio_url_for_dashscope)
                if probe_err:
                    raise RuntimeError(f"公网样本地址不可访问: {probe_err}")

            voice_id, status, request_id = await client.enroll_custom_voice(audio_url_for_dashscope, safe_prefix)
            break
        except Exception as exc:
            last_error = str(exc)
            can_retry = attempt < retries and _is_retryable_voice_enroll_error(last_error)
            if not can_retry:
                raise HTTPException(
                    status_code=400,
                    detail=f"声纹注册失败: {last_error} (audio_url={audio_url_for_dashscope})",
                ) from exc
            await asyncio.sleep(1.0)

    if not voice_id:
        raise HTTPException(status_code=400, detail=f"声纹注册失败: {last_error or '未知错误'}")

    store.append(
        "voices",
        {
            "child_id": child_id,
            "voice_id": voice_id,
            "status": status,
            "display_name": display_name or safe_prefix,
            "prefix": safe_prefix,
            "sample_audio_url": public_sample_url,
            "remote_audio_url": audio_url_for_dashscope,
            "timestamp": store.now_iso(),
        },
    )
    return VoiceEnrollResponse(
        voice_id=voice_id,
        status=status,
        sample_audio_url=public_sample_url,
        request_id=request_id,
    )


@app.post("/api/voice/synthesize", response_model=VoiceSynthesizeResponse)
async def synthesize_voice(req: VoiceSynthesizeRequest) -> VoiceSynthesizeResponse:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空。")

    voice_id = (req.voice_id or "").strip()
    if not voice_id:
        latest = store.latest_voice(req.child_id)
        if latest is None:
            raise HTTPException(status_code=400, detail="未找到可用 voice_id，请先上传样本并完成声纹注册。")
        voice_id = str(latest.get("voice_id", "")).strip()
    if not voice_id:
        raise HTTPException(status_code=400, detail="voice_id 无效，请重新注册。")

    output_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{req.child_id}_tts.mp3"
    output_path = upload_dir / output_name
    try:
        request_id = await client.synthesize_with_voice(voice_id, text, output_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"语音合成失败: {exc}") from exc

    return VoiceSynthesizeResponse(
        voice_id=voice_id,
        audio_url=f"/uploads/{output_name}",
        request_id=request_id,
    )


@app.get("/api/voice/list", response_model=VoiceListResponse)
async def list_voices(child_id: str = "default-child") -> VoiceListResponse:
    rows = store.list_voices(child_id)
    items = [
        VoiceItem(
            child_id=str(row.get("child_id", child_id)),
            voice_id=str(row.get("voice_id", "")),
            status=str(row.get("status", "")),
            display_name=(
                str(row.get("display_name", "")).strip()
                or str(row.get("prefix", "")).strip()
                or str(row.get("voice_id", "")).strip()
            ),
            prefix=(str(row.get("prefix", "")).strip() or None),
            sample_audio_url=(str(row.get("sample_audio_url", "")).strip() or None),
            timestamp=str(row.get("timestamp", "")),
        )
        for row in rows
        if str(row.get("voice_id", "")).strip()
    ]
    return VoiceListResponse(child_id=child_id, items=items)


@app.delete("/api/voice/{voice_id}", response_model=VoiceDeleteResponse)
async def delete_voice(voice_id: str, child_id: str = "default-child") -> VoiceDeleteResponse:
    clean_voice_id = voice_id.strip()
    if not clean_voice_id:
        raise HTTPException(status_code=400, detail="voice_id 不能为空。")

    deleted = store.delete_voice(child_id, clean_voice_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="未找到对应 voice_id。")

    return VoiceDeleteResponse(ok=True, child_id=child_id, voice_id=clean_voice_id)


@app.get("/api/report/daily", response_model=DailyReportResponse)
async def daily_report(child_id: str = "default-child", day: str | None = None) -> DailyReportResponse:
    day = day or datetime.now().strftime("%Y-%m-%d")
    analyses = store.query_by_child_and_date("analyses", child_id, day)
    conversations = store.query_by_child_and_date("conversations", child_id, day)

    result = build_daily_report(analyses, conversations)
    payload = {
        "child_id": child_id,
        "date": day,
        **result,
    }
    store.append("reports", payload | {"timestamp": store.now_iso()})

    return DailyReportResponse(**payload)


@app.post("/api/history/reset")
async def reset_history() -> dict:
    # Reset chat history, report data, and generated/uploaded assets in one action.
    store.clear("conversations")
    store.clear("analyses")
    store.clear("reports")

    deleted_upload_items = 0
    for item in upload_dir.iterdir():
        if item.is_file() or item.is_symlink():
            item.unlink(missing_ok=True)
            deleted_upload_items += 1
        elif item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
            deleted_upload_items += 1

    return {"ok": True, "deleted_upload_items": deleted_upload_items}


@app.get("/api/conversations/today", response_model=ConversationListResponse)
async def today_conversations(child_id: str = "default-child") -> ConversationListResponse:
    day = datetime.now().strftime("%Y-%m-%d")
    rows = store.query_by_child_and_date("conversations", child_id, day)

    rows.sort(key=lambda row: str(row.get("timestamp", "")))
    items = [
        ConversationItem(
            child_id=str(row.get("child_id", child_id)),
            role=str(row.get("role", "user")),
            content=str(row.get("content", "")),
            message_type=str(row.get("message_type", "text") or "text"),
            image_url=(str(row.get("image_url", "")).strip() or None),
            audio_url=(str(row.get("audio_url", "")).strip() or None),
            timestamp=str(row.get("timestamp", "")),
        )
        for row in rows
    ]
    return ConversationListResponse(child_id=child_id, day=day, items=items)
