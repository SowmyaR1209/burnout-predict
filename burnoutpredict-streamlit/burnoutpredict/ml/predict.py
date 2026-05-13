"""Load the trained app-feature XGBoost model and score employees."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .features import APP_FEATURE_COLUMNS, APP_FEATURE_LABELS

MODEL_PATH = Path(__file__).resolve().parent / "xgb_app.pkl"


class ModelNotTrainedError(RuntimeError):
    pass


def _load_model():
    if not MODEL_PATH.exists():
        raise ModelNotTrainedError(
            "The XGBoost model has not been trained yet. "
            "Run `python -m burnoutpredict.ml.train` once before using attrition prediction."
        )
    bundle = joblib.load(MODEL_PATH)
    return bundle["model"], bundle["feature_cols"]


def model_exists() -> bool:
    return MODEL_PATH.exists()


def predict_one(features: dict[str, float]) -> dict[str, Any]:
    df = pd.DataFrame([features])[APP_FEATURE_COLUMNS]
    return _predict_frame(df).iloc[0].to_dict()


def predict_many(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows
    return _predict_frame(rows[APP_FEATURE_COLUMNS])


def _predict_frame(df: pd.DataFrame) -> pd.DataFrame:
    model, _cols = _load_model()
    proba = model.predict_proba(df)[:, 1]
    bands = np.where(proba >= 0.6, "high", np.where(proba >= 0.35, "moderate", "low"))

    # Per-employee feature contributions for explainability.
    booster = model.get_booster()
    import xgboost as xgb
    contribs = booster.predict(xgb.DMatrix(df), pred_contribs=True)  # (n, n_features+1)

    drivers_per_row: list[list[dict]] = []
    for i in range(len(df)):
        feat_contribs = contribs[i, :-1]  # drop bias
        order = np.argsort(-feat_contribs)
        top = []
        for idx in order:
            if feat_contribs[idx] <= 0:
                continue
            col = APP_FEATURE_COLUMNS[idx]
            top.append({
                "factor": APP_FEATURE_LABELS.get(col, col),
                "contribution": round(float(feat_contribs[idx]), 3),
                "value": round(float(df.iloc[i, idx]), 2),
            })
            if len(top) >= 3:
                break
        drivers_per_row.append(top)

    out = df.copy()
    out["probability"] = np.round(proba, 3)
    out["risk_band"] = bands
    out["drivers"] = drivers_per_row
    return out
