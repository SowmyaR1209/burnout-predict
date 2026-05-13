"""Feature engineering used by both training and prediction.

Two separate models live in this codebase:

  1.  `xgb_attrition.pkl` — trained on the IBM HR Attrition dataset
      (35 columns, 1 470 employees). Used for the "raw" benchmark accuracy.

  2.  `xgb_app.pkl` — trained on the 8 features the Streamlit app actually has
      access to per employee (burnout score + survey signals + tenure +
      overtime). This is what the HR dashboard scores live employees with.
      Both models are produced by `burnoutpredict.ml.train`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


APP_FEATURE_COLUMNS: list[str] = [
    "burnout_score",
    "work_hours",
    "sleep_hours",
    "support",
    "workload",
    "personal_accomplishment",
    "tenure_months",
    "overtime_flag",
]

APP_FEATURE_LABELS: dict[str, str] = {
    "burnout_score": "Burnout score",
    "work_hours": "Weekly work hours",
    "sleep_hours": "Sleep deprivation",
    "support": "Lack of team/manager support",
    "workload": "Workload pressure",
    "personal_accomplishment": "Sense of accomplishment",
    "tenure_months": "Tenure",
    "overtime_flag": "Frequent overtime",
}


@dataclass
class AppFeatures:
    burnout_score: float
    work_hours: float
    sleep_hours: float
    support: float
    workload: float
    personal_accomplishment: float
    tenure_months: float
    overtime_flag: int

    def to_row(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "burnout_score": self.burnout_score,
            "work_hours": self.work_hours,
            "sleep_hours": self.sleep_hours,
            "support": self.support,
            "workload": self.workload,
            "personal_accomplishment": self.personal_accomplishment,
            "tenure_months": self.tenure_months,
            "overtime_flag": self.overtime_flag,
        }])


def synthesise_app_features_from_ibm(ibm: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Map the rich IBM dataset onto our 8-feature schema so the app-shaped
    XGBoost model can be trained even before any real survey data exists.
    """
    n = len(ibm)
    # IBM "JobSatisfaction" 1-4, "EnvironmentSatisfaction" 1-4 → support 0-6
    support = (ibm["JobSatisfaction"].astype(float) + ibm["EnvironmentSatisfaction"].astype(float))
    support = ((support - 2) / 6 * 6).clip(0, 6)
    # IBM "JobInvolvement" 1-4 → personal accomplishment 0-6
    pa = ((ibm["JobInvolvement"].astype(float) - 1) / 3 * 6).clip(0, 6)
    # WorkLifeBalance 1-4 (1=bad) → workload (high = 6 = bad)
    workload = ((4 - ibm["WorkLifeBalance"].astype(float)) / 3 * 6).clip(0, 6)
    overtime_flag = (ibm["OverTime"].astype(str).str.lower() == "yes").astype(int)
    work_hours = 40 + overtime_flag * rng.normal(10, 3, n) + (workload * rng.normal(0.6, 0.3, n))
    work_hours = np.clip(work_hours, 30, 80)
    sleep_hours = np.clip(7.5 - workload * 0.25 + rng.normal(0, 0.6, n), 4, 9)
    tenure_months = (ibm["YearsAtCompany"].astype(float) * 12 + rng.uniform(0, 11, n)).clip(1, 600)
    # Synthesise a burnout score consistent with workload + support + sleep
    burnout_score = (
        workload * 6
        + (6 - support) * 4
        + (6 - pa) * 3
        + (work_hours - 40).clip(0, None) * 0.6
        + (7 - sleep_hours).clip(0, None) * 4
    )
    burnout_score = np.clip(burnout_score + rng.normal(0, 3, n), 0, 100)

    return pd.DataFrame({
        "burnout_score": burnout_score,
        "work_hours": work_hours,
        "sleep_hours": sleep_hours,
        "support": support,
        "workload": workload,
        "personal_accomplishment": pa,
        "tenure_months": tenure_months,
        "overtime_flag": overtime_flag,
    })


def build_app_features_from_db(profiles: Iterable[dict], surveys: Iterable[dict],
                               risk_scores: Iterable[dict]) -> pd.DataFrame:
    """Build one row per profile from live Supabase rows (latest survey + risk)."""
    surveys = list(surveys)
    risk_scores = list(risk_scores)
    latest_survey: dict[str, dict] = {}
    for s in sorted(surveys, key=lambda x: x.get("created_at", ""), reverse=True):
        latest_survey.setdefault(s["user_id"], s)
    latest_risk: dict[str, dict] = {}
    for r in sorted(risk_scores, key=lambda x: x.get("created_at", ""), reverse=True):
        latest_risk.setdefault(r["user_id"], r)

    rows = []
    import datetime as dt
    now = dt.datetime.utcnow()
    for p in profiles:
        s = latest_survey.get(p["user_id"])
        r = latest_risk.get(p["user_id"])
        if not s or not r:
            continue
        try:
            created = dt.datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            tenure_months = max(1, int((now - created).days / 30))
        except Exception:
            tenure_months = 12
        rows.append({
            "user_id": p["user_id"],
            "burnout_score": float(r["burnout_score"]),
            "work_hours": float(s["work_hours"]),
            "sleep_hours": float(s["sleep_hours"]),
            "support": float(s["support"]),
            "workload": float(s["workload"]),
            "personal_accomplishment": float(s["personal_accomplishment"]),
            "tenure_months": tenure_months,
            "overtime_flag": int(float(s["work_hours"]) > 50),
        })
    return pd.DataFrame(rows)
