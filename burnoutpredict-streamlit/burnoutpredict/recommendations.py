"""Build personalised wellness recommendations based on burnout profile."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scoring import SurveyInput


def build_recommendations(level: str, top_factors: list[str], s: "SurveyInput") -> list[str]:
    tips: list[str] = []
    if level == "high":
        tips.append("Speak with HR or your manager this week — early intervention matters.")
        tips.append("Consider a short recovery break (2–3 days off) within the next 30 days.")
    elif level == "moderate":
        tips.append("Schedule a 1:1 with your manager to discuss workload re-balancing.")
    else:
        tips.append("Maintain your current routine — your indicators look healthy.")

    for f in top_factors:
        if f == "Emotional exhaustion":
            tips.append("Block 30 minutes daily for non-work recovery (walk, meditation).")
        if f == "High workload":
            tips.append("Prioritize top 3 tasks daily; defer or delegate the rest.")
        if f == "Sleep deprivation":
            tips.append(f"Aim for 7–8 hours of sleep — you reported {s.sleep_hours}h.")
        if f == "Overwork":
            tips.append(f"Cap weekly hours below 45 — you reported {s.work_hours}h.")
        if f == "Low support":
            tips.append("Reach out to a peer or your EAP — connection lowers stress.")
        if f == "Low accomplishment":
            tips.append("List 3 wins from this week; visibility of progress lifts motivation.")
        if f == "Depersonalization":
            tips.append("Reconnect with purpose: revisit a recent project that mattered.")

    seen, out = set(), []
    for t in tips:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:5]
