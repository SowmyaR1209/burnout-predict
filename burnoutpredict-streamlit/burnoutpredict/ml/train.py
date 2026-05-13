"""Train the XGBoost attrition classifier.

Usage
-----
    python -m burnoutpredict.ml.train               # train on IBM dataset
    python -m burnoutpredict.ml.train --augment     # blend IBM + live DB rows

Two pickles are produced in `burnoutpredict/ml/`:

  * `xgb_ibm.pkl`        — trained on the full 30+ IBM features (benchmark ~87 % acc.)
  * `xgb_app.pkl`        — trained on the 8 app-available features (used by the HR dashboard)
  * `metrics.json`       — accuracy / ROC-AUC for both models

The IBM dataset is fetched from the public mirror at
https://raw.githubusercontent.com/IBM/employee-attrition-aif360/master/data/emp_attrition.csv
and cached under `burnoutpredict/data/`.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

from .features import APP_FEATURE_COLUMNS, synthesise_app_features_from_ibm

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)
IBM_CSV = DATA_DIR / "ibm_hr_attrition.csv"

IBM_URL = "https://raw.githubusercontent.com/IBM/employee-attrition-aif360/master/data/emp_attrition.csv"
# Fallback mirror (Kaggle community copy) if the primary URL changes.
IBM_FALLBACK = (
    "https://raw.githubusercontent.com/datasets-mirror/HR-Employee-Attrition/main/HR-Employee-Attrition.csv"
)


def download_ibm_dataset() -> pd.DataFrame:
    if IBM_CSV.exists():
        return pd.read_csv(IBM_CSV)
    print("📥 Downloading IBM HR Attrition dataset…")
    last_err: Exception | None = None
    for url in (IBM_URL, IBM_FALLBACK):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            IBM_CSV.write_bytes(r.content)
            return pd.read_csv(IBM_CSV)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Could not download IBM HR Attrition dataset: {last_err}")


def _train_xgb(X: pd.DataFrame, y: np.ndarray, *, label: str) -> tuple[XGBClassifier, dict]:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    pos_weight = (len(y_train) - y_train.sum()) / max(1, y_train.sum())
    model = XGBClassifier(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        scale_pos_weight=pos_weight,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)
    metrics = {
        "model": label,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "accuracy": round(float(accuracy_score(y_test, pred)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
    }
    print(f"✅ {label}: acc={metrics['accuracy']:.3f}  auc={metrics['roc_auc']:.3f}  (n={len(X)})")
    return model, metrics


def train_full_ibm(ibm: pd.DataFrame) -> tuple[XGBClassifier, dict, list[str]]:
    df = ibm.copy()
    y = (df["Attrition"].astype(str).str.lower() == "yes").astype(int).values
    df = df.drop(columns=[c for c in ["Attrition", "EmployeeNumber", "EmployeeCount", "Over18", "StandardHours"] if c in df.columns])
    # Encode categorical columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = LabelEncoder().fit_transform(df[col].astype(str))
    feature_cols = df.columns.tolist()
    model, metrics = _train_xgb(df, y, label="ibm_full")
    return model, metrics, feature_cols


def train_app_model(ibm: pd.DataFrame,
                    extra: pd.DataFrame | None = None) -> tuple[XGBClassifier, dict]:
    rng = np.random.default_rng(42)
    X_ibm = synthesise_app_features_from_ibm(ibm, rng)
    y_ibm = (ibm["Attrition"].astype(str).str.lower() == "yes").astype(int).values
    if extra is not None and len(extra) >= 30 and "attrition" in extra.columns:
        X_extra = extra[APP_FEATURE_COLUMNS]
        y_extra = extra["attrition"].astype(int).values
        X = pd.concat([X_ibm, X_extra], ignore_index=True)
        y = np.concatenate([y_ibm, y_extra])
        label = "app_blend"
    else:
        X, y, label = X_ibm, y_ibm, "app_ibm_only"
    model, metrics = _train_xgb(X[APP_FEATURE_COLUMNS], y, label=label)
    return model, metrics


def main(extra_df: pd.DataFrame | None = None) -> dict:
    ibm = download_ibm_dataset()
    print(f"Loaded IBM dataset: {ibm.shape[0]} rows × {ibm.shape[1]} columns")

    ibm_model, ibm_metrics, ibm_features = train_full_ibm(ibm)
    app_model, app_metrics = train_app_model(ibm, extra_df)

    joblib.dump({"model": ibm_model, "feature_cols": ibm_features}, ROOT / "xgb_ibm.pkl")
    joblib.dump({"model": app_model, "feature_cols": APP_FEATURE_COLUMNS}, ROOT / "xgb_app.pkl")

    metrics = {"ibm_full": ibm_metrics, "app": app_metrics}
    (ROOT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print("💾 Saved models to:", ROOT)
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--augment", action="store_true",
                        help="Pull live rows from Supabase to augment training data.")
    args = parser.parse_args()
    extra = None
    if args.augment:
        from ..supabase_client import get_admin_client
        from .features import build_app_features_from_db
        sb = get_admin_client()
        if not sb:
            print("⚠️  No SUPABASE_SERVICE_ROLE_KEY set — falling back to IBM only.")
        else:
            profiles = sb.table("profiles").select("user_id, created_at").execute().data
            surveys = sb.table("survey_responses").select(
                "user_id, work_hours, sleep_hours, support, workload, personal_accomplishment, created_at"
            ).execute().data
            scores = sb.table("risk_scores").select("user_id, burnout_score, created_at").execute().data
            extra = build_app_features_from_db(profiles, surveys, scores)
            extra["attrition"] = (extra["burnout_score"] > 65).astype(int)  # weak label
            print(f"Augmenting with {len(extra)} live rows.")
    main(extra)
