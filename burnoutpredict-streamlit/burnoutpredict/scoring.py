"""Transparent rule-based burnout scoring engine.

Direct port of the original `src/lib/scoring.ts` so the math stays identical
between the React app and the Streamlit edition (employees who have history in
both apps see the same scores).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RiskLevel = Literal["low", "moderate", "high"]


@dataclass
class SurveyInput:
    emotional_exhaustion: int       # 0-6
    depersonalization: int          # 0-6
    personal_accomplishment: int    # 0-6 (higher = better)
    workload: int                   # 0-6
    support: int                    # 0-6 (higher = better)
    sleep_hours: float              # hours
    work_hours: float               # hours/week


@dataclass
class RiskResult:
    burnout_score: float            # 0-100
    risk_level: RiskLevel
    top_factors: list[dict]
    recommendations: list[str]


def _clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


def compute_burnout_risk(s: SurveyInput) -> RiskResult:
    ee = (s.emotional_exhaustion / 6) * 100
    dp = (s.depersonalization / 6) * 100
    pa = ((6 - s.personal_accomplishment) / 6) * 100
    wl = (s.workload / 6) * 100
    sup = ((6 - s.support) / 6) * 100
    sleep = _clamp(((7 - s.sleep_hours) / 4) * 100, 0, 100)
    overwork = _clamp(((s.work_hours - 40) / 30) * 100, 0, 100)

    factors = [
        ("Emotional exhaustion", ee, 0.25, "How drained you feel by work"),
        ("Depersonalization",    dp, 0.15, "Detachment from work and colleagues"),
        ("Low accomplishment",   pa, 0.15, "Sense of effectiveness at work"),
        ("High workload",        wl, 0.15, "Volume and pressure of tasks"),
        ("Low support",          sup, 0.10, "Help from peers and managers"),
        ("Sleep deprivation",    sleep, 0.10, "Average nightly sleep"),
        ("Overwork",             overwork, 0.10, "Weekly working hours"),
    ]

    score = sum(v * w for _, v, w, _ in factors)
    burnout_score = round(score * 10) / 10

    if burnout_score >= 65:
        level: RiskLevel = "high"
    elif burnout_score >= 40:
        level = "moderate"
    else:
        level = "low"

    contributions = [
        {"factor": name, "contribution": round(v * w * 10) / 10, "note": note}
        for name, v, w, note in factors
    ]
    contributions.sort(key=lambda x: x["contribution"], reverse=True)
    top_factors = contributions[:3]

    from .recommendations import build_recommendations
    recs = build_recommendations(level, [f["factor"] for f in top_factors], s)

    return RiskResult(burnout_score, level, top_factors, recs)
