"""DistilBERT-powered sentiment + theme/urgency extraction for survey notes.

Replaces the original `analyze-note` Edge Function (which used Gemini via the
Lovable AI Gateway). Uses HuggingFace `transformers` locally so the app works
offline once the model is cached.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

# A small, curated keyword vocabulary for theme / urgency extraction. Keeps the
# pipeline 100 % offline and deterministic — DistilBERT handles polarity, this
# handles topic + urgency.
THEME_KEYWORDS: dict[str, list[str]] = {
    "workload":            ["overwhelmed", "too much work", "deadlines", "deadline", "pressure", "swamped", "overloaded", "back to back", "no time"],
    "management":          ["manager", "boss", "leadership", "micromanage", "unfair", "no support"],
    "team conflict":       ["conflict", "argument", "toxic", "blame", "blamed", "rude", "hostile"],
    "career growth":       ["promotion", "stuck", "growth", "career", "stagnant", "no progress"],
    "work-life balance":   ["family", "kids", "weekend", "evenings", "no balance", "personal time", "burned out at home"],
    "compensation":        ["salary", "pay", "bonus", "underpaid", "raise"],
    "health":              ["sick", "anxiety", "depressed", "depression", "panic", "insomnia", "exhausted", "tired all the time", "headaches"],
    "isolation":           ["alone", "isolated", "lonely", "no one to talk", "remote"],
}

URGENCY_KEYWORDS = {
    "high": [
        "quit", "resign", "leave", "leaving", "give up", "can't take", "cant take",
        "breakdown", "panic", "harassment", "harassed", "bullied", "discrimination",
        "suicidal", "hopeless", "i'm done", "im done",
    ],
    "moderate": [
        "burnout", "burned out", "exhausted", "overwhelmed", "depressed", "anxious",
        "demoralized", "frustrated", "unfair",
    ],
}


@lru_cache(maxsize=1)
def _sentiment_pipeline():
    """Lazy-load DistilBERT once (downloads ~250 MB on first run)."""
    from transformers import pipeline
    return pipeline(
        "sentiment-analysis",
        model="distilbert-base-uncased-finetuned-sst-2-english",
        truncation=True,
    )


def _classify_urgency(text: str) -> str:
    t = text.lower()
    if any(k in t for k in URGENCY_KEYWORDS["high"]):
        return "high"
    if any(k in t for k in URGENCY_KEYWORDS["moderate"]):
        return "moderate"
    return "low"


def _extract_themes(text: str) -> list[str]:
    t = text.lower()
    found = [theme for theme, kws in THEME_KEYWORDS.items() if any(k in t for k in kws)]
    return found[:4]


def _summarize(text: str, max_len: int = 200) -> str:
    """A simple extractive summary: first 1–2 sentences, capped."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    summary = " ".join(sentences[:2]).strip()
    if len(summary) > max_len:
        summary = summary[: max_len - 1].rstrip() + "…"
    return summary or text[:max_len]


def analyze_note(note: str) -> dict[str, Any]:
    """Return {sentiment, urgency, themes, summary}. Safe on empty input."""
    note = (note or "").strip()
    if len(note) < 3:
        return {"ai_sentiment": None, "ai_urgency": None, "ai_themes": [], "ai_summary": None}

    pipe = _sentiment_pipeline()
    out = pipe(note[:512])[0]  # DistilBERT max tokens
    label = out["label"].lower()  # "positive" / "negative"
    sentiment = "positive" if label == "positive" else "negative"

    themes = _extract_themes(note)
    urgency = _classify_urgency(note)
    # Negative sentiment automatically bumps urgency
    if sentiment == "negative" and urgency == "low":
        urgency = "moderate"
    summary = _summarize(note)

    return {
        "ai_sentiment": sentiment,
        "ai_urgency": urgency,
        "ai_themes": themes,
        "ai_summary": summary,
    }
