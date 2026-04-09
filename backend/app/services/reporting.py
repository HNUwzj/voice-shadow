from __future__ import annotations

from statistics import mean


def build_daily_report(analyses: list[dict], conversations: list[dict]) -> dict:
    if not analyses:
        return {
            "total_messages": len(conversations),
            "risk_summary": {
                "self_esteem_risk_avg": 0,
                "bullying_risk_avg": 0,
                "loneliness_risk_avg": 0,
                "companionship_need_avg": 0,
            },
            "highlights": [],
            "suggestion": "今天数据较少，建议主动发起 5-10 分钟视频通话，了解孩子近况。",
        }

    self_esteem_avg = mean(a.get("self_esteem_risk", 0) for a in analyses)
    bullying_avg = mean(a.get("bullying_risk", 0) for a in analyses)
    loneliness_avg = mean(a.get("loneliness_risk", 0) for a in analyses)
    companionship_avg = mean(a.get("companionship_need", 0) for a in analyses)

    highlights: list[str] = []
    lonely_mentions = sum(1 for a in analyses if a.get("loneliness_risk", 0) >= 0.5)
    if lonely_mentions:
        highlights.append(f"出现 {lonely_mentions} 次明显孤独信号，建议今晚主动倾听。")

    bullying_mentions = sum(1 for a in analyses if a.get("bullying_risk", 0) >= 0.5)
    if bullying_mentions:
        highlights.append(f"出现 {bullying_mentions} 次被欺凌相关风险词，建议与班主任沟通。")

    moods = [a.get("mood", "neutral") for a in analyses]
    sad_ratio = sum(1 for m in moods if m in {"sad", "anxious", "angry"}) / max(1, len(moods))
    if sad_ratio > 0.4:
        highlights.append("负向情绪占比较高，可增加肯定式回应并安排固定亲子通话。")

    suggestion = "建议保持每日固定 10 分钟高质量陪聊。"
    if bullying_avg > 0.45:
        suggestion = "建议优先确认校园人际冲突，必要时联系老师。"
    elif loneliness_avg > 0.45:
        suggestion = "建议增加高频短通话，并约定每周一次共同活动目标。"

    return {
        "total_messages": len(conversations),
        "risk_summary": {
            "self_esteem_risk_avg": round(self_esteem_avg, 3),
            "bullying_risk_avg": round(bullying_avg, 3),
            "loneliness_risk_avg": round(loneliness_avg, 3),
            "companionship_need_avg": round(companionship_avg, 3),
        },
        "highlights": highlights,
        "suggestion": suggestion,
    }
