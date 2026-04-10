from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import ChatRequest, ChatResponse, DailyReportResponse, PraiseResponse
from app.services.analysis import analyze_psych_signal
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

    return ChatResponse(reply=reply, scene_image_url=scene_image_url, timestamp=timestamp)


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
            "timestamp": store.now_iso(),
        },
    )

    return PraiseResponse(
        reply=reply,
        image_url=public_image_url,
        scene_image_url=scene_image_url,
        details={"filename": image_path.name, "size": image_path.stat().st_size},
    )


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
    # Reset chat history and report-related source data in one action.
    store.clear("conversations")
    store.clear("analyses")
    store.clear("reports")
    return {"ok": True}
