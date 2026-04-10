from __future__ import annotations

import json
import re
from typing import Any

from app.models import PsychSignal
from app.services.dashscope_client import DashscopeClient


ANALYSIS_PROMPT = """
你是儿童心理风险侧写助手。请分析用户语句是否出现以下风险并输出 JSON：
- self_esteem_risk: 0-1
- bullying_risk: 0-1
- loneliness_risk: 0-1
- companionship_need: 0-1
- mood: happy|neutral|sad|angry|anxious
- evidence: 证据短语数组
只输出 JSON，不要额外文本。
""".strip()

BULLYING_KEYS = ["霸凌", "被霸凌", "欺负", "嘲笑", "打我", "骂我", "排挤", "被针对", "被孤立"]
LONELY_KEYS = ["想妈妈", "想爸爸", "一个人", "没人", "孤单", "难过", "没人陪我"]
COMPANIONSHIP_KEYS = ["陪我", "陪陪我", "别走", "你在吗", "聊聊", "和我说说话", "抱抱我", "我害怕"]
BULLYING_PATTERNS = [
    r"被.*(欺负|打|骂|排挤|针对)",
    r"同学.*(欺负|嘲笑|排挤)",
    r"他们.*(打|骂|欺负)我",
]
LONELY_PATTERNS = [
    r"(没人|没有人).*(理我|陪我)",
    r"我.*(很孤单|好孤单|好孤独)",
    r"我.*一个人",
]
COMPANIONSHIP_PATTERNS = [
    r"(陪陪我|陪我一下|陪我聊聊)",
    r"(别离开我|别走)",
    r"(你在吗|你还在吗)",
]
SELF_ESTEEM_KEYS = [
    "我不行",
    "我很笨",
    "我做不到",
    "我很差",
    "我是不是很没用",
    "我很自卑",
    "我好自卑",
    "我很没用",
    "我好没用",
    "我不配",
    "我配不上",
    "我一无是处",
    "我什么都做不好",
    "我不值得",
]
SELF_ESTEEM_PATTERNS = [
    r"我.*自卑",
    r"我.*(没用|不配|不值得)",
    r"我.*(很差|好差|真差)",
    r"我.*(做不好|做不到)",
    r"是不是.*(很差|没用|不行)",
]


def _self_esteem_pattern_hits(text: str) -> list[str]:
    hits: list[str] = []
    for pat in SELF_ESTEEM_PATTERNS:
        if re.search(pat, text):
            hits.append(f"pattern:{pat}")
    return hits


def _pattern_hits(text: str, patterns: list[str], prefix: str) -> list[str]:
    hits: list[str] = []
    for pat in patterns:
        if re.search(pat, text):
            hits.append(f"{prefix}:{pat}")
    return hits


async def analyze_psych_signal(client: DashscopeClient, text: str) -> PsychSignal:
    messages = [
        {"role": "system", "content": ANALYSIS_PROMPT},
        {"role": "user", "content": text},
    ]
    try:
        raw = await client.chat(messages, temperature=0.1)
        data: dict[str, Any] = _parse_json_from_text(raw)
        signal = PsychSignal(**data)
        return _apply_rule_guardrails(signal, text)
    except Exception:
        return _apply_rule_guardrails(heuristic_signal(text), text)


def _parse_json_from_text(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError("No JSON object found in model output")
    return json.loads(match.group(0))


def _apply_rule_guardrails(signal: PsychSignal, text: str) -> PsychSignal:
    low = text.lower()

    bully_hits = [k for k in BULLYING_KEYS if k in low]
    lonely_hits = [k for k in LONELY_KEYS if k in low]
    companionship_hits = [k for k in COMPANIONSHIP_KEYS if k in low]
    bully_hits.extend(_pattern_hits(text, BULLYING_PATTERNS, "bully"))
    lonely_hits.extend(_pattern_hits(text, LONELY_PATTERNS, "lonely"))
    companionship_hits.extend(_pattern_hits(text, COMPANIONSHIP_PATTERNS, "company"))
    self_esteem_hits = [k for k in SELF_ESTEEM_KEYS if k in low]
    self_esteem_hits.extend(_self_esteem_pattern_hits(text))

    if bully_hits and signal.bullying_risk < 0.7:
        signal.bullying_risk = 0.7
    if lonely_hits and signal.loneliness_risk < 0.45:
        signal.loneliness_risk = 0.45
    if companionship_hits and signal.companionship_need < 0.6:
        signal.companionship_need = 0.6
    if self_esteem_hits and signal.self_esteem_risk < 0.55:
        signal.self_esteem_risk = 0.55

    if bully_hits and signal.mood == "neutral":
        signal.mood = "sad"
    if self_esteem_hits and signal.mood == "neutral":
        signal.mood = "sad"
    if companionship_hits and signal.mood == "neutral":
        signal.mood = "anxious"

    merged_evidence = list(dict.fromkeys(signal.evidence + bully_hits + lonely_hits + companionship_hits + self_esteem_hits))
    signal.evidence = merged_evidence[:6]
    signal.companionship_need = max(
        signal.companionship_need,
        min(1.0, signal.loneliness_risk + 0.2 + (0.15 if companionship_hits else 0.0)),
    )
    return signal


def heuristic_signal(text: str) -> PsychSignal:
    low = text.lower()

    bully_key_hits = sum(1 for k in BULLYING_KEYS if k in low)
    lonely_key_hits = sum(1 for k in LONELY_KEYS if k in low)
    company_key_hits = sum(1 for k in COMPANIONSHIP_KEYS if k in low)
    bully_pattern_hits = len(_pattern_hits(text, BULLYING_PATTERNS, "bully"))
    lonely_pattern_hits = len(_pattern_hits(text, LONELY_PATTERNS, "lonely"))
    company_pattern_hits = len(_pattern_hits(text, COMPANIONSHIP_PATTERNS, "company"))

    loneliness = min(1.0, lonely_key_hits * 0.35 + lonely_pattern_hits * 0.3)
    bullying = min(1.0, bully_key_hits * 0.4 + bully_pattern_hits * 0.35)
    self_esteem_key_hits = sum(1 for k in SELF_ESTEEM_KEYS if k in low)
    self_esteem_pattern_hits = len(_self_esteem_pattern_hits(text))
    self_esteem = min(1.0, self_esteem_key_hits * 0.45 + self_esteem_pattern_hits * 0.35)
    companionship_need = min(1.0, loneliness + 0.2 + company_key_hits * 0.2 + company_pattern_hits * 0.2)

    mood = "neutral"
    if any(k in low for k in ["开心", "高兴", "太棒了"]):
        mood = "happy"
    if any(k in low for k in ["难过", "伤心", "害怕", "烦"]):
        mood = "sad"
    if companionship_need >= 0.65 and mood == "neutral":
        mood = "anxious"

    evidence = [k for k in LONELY_KEYS + BULLYING_KEYS + COMPANIONSHIP_KEYS + SELF_ESTEEM_KEYS if k in low]
    evidence.extend(_pattern_hits(text, BULLYING_PATTERNS, "bully"))
    evidence.extend(_pattern_hits(text, LONELY_PATTERNS, "lonely"))
    evidence.extend(_pattern_hits(text, COMPANIONSHIP_PATTERNS, "company"))
    evidence.extend(_self_esteem_pattern_hits(text))

    return PsychSignal(
        self_esteem_risk=self_esteem,
        bullying_risk=bullying,
        loneliness_risk=loneliness,
        companionship_need=companionship_need,
        mood=mood,
        evidence=evidence[:5],
    )
