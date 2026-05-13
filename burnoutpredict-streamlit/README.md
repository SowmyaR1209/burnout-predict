# BurnoutPredict — Streamlit Edition

A Python/Streamlit port of the original ThriveWell AI / BurnoutPredict app, with
**XGBoost** powering the attrition prediction and **DistilBERT** powering the
sentiment analysis of free-text survey notes. Backend is **Supabase** (Postgres
+ Auth), kept identical to the original schema so existing data is reused.

## Features (1:1 with the original web app)

- 🔐 **Supabase Auth** — email/password sign-in & sign-up with `hr` / `employee` role.
- 📋 **Weekly check-in survey** — 7 MBI-aligned questions + sleep / work hours + free-text note.
- 📊 **Transparent burnout scoring** — same weighted formula (0–100, low/moderate/high tier).
- 🤖 **XGBoost attrition prediction** — trained on the IBM HR Analytics dataset (~87 % accuracy), with a one-click "Retrain on org data" button in the HR dashboard.
- 💬 **DistilBERT sentiment** — `distilbert-base-uncased-finetuned-sst-2-english` analyses the free-text note, classifies sentiment, urgency, and themes.
- 👥 **Employee dashboard** — current score, trend chart, top contributing factors, personalised recommendations, AI insight from the latest note.
- 🏢 **HR dashboard** — KPIs, burnout-by-department bar chart, risk-distribution pie, high-urgency qualitative signals, employee table with attrition probability.
- 🌱 **Seed demo data** — optional button to populate 12 demo employees with surveys and risk scores (requires `SUPABASE_SERVICE_ROLE_KEY`).

## Quick start (VS Code)

1. **Clone / unzip this folder** and open it in VS Code.
2. **Create a Python 3.10+ virtual environment** and install dependencies:
   ```bash
   python -m venv .venv
   # macOS / Linux:
   source .venv/bin/activate
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1

   pip install -r requirements.txt
   ```
3. **Configure Supabase**:
   - Copy `.env.example` → `.env`
   - Fill in `SUPABASE_URL` and `SUPABASE_ANON_KEY` from your Supabase project
     (Dashboard → Settings → API).
   - If this is a new Supabase project, run the SQL in `supabase/migrations/001_init.sql` once
     in the Supabase SQL editor.
4. **Train the XGBoost model** (one-time, ~15 s):
   ```bash
   python -m burnoutpredict.ml.train
   ```
   This downloads the IBM HR Attrition dataset, trains XGBoost, and writes
   `burnoutpredict/ml/xgb_attrition.pkl` + `feature_pipeline.pkl`.
5. **Run the app**:
   ```bash
   streamlit run app.py
   ```
   The app opens at <http://localhost:8501>.

## First run notes

- The DistilBERT sentiment model (~250 MB) is downloaded automatically by
  HuggingFace on first use — be patient on the first survey note that contains text.
- The `Retrain on org data` button (HR dashboard → ML tab) re-trains XGBoost using
  the `survey_responses` + `risk_scores` rows currently in your database, falling
  back to the IBM dataset if there are too few rows. The new model overwrites
  `xgb_attrition.pkl`.

## Project layout

```
app.py                         # Streamlit entrypoint (landing page + auth-aware nav)
pages/
  1_📋_Check_in.py             # Employee survey form
  2_📊_My_Dashboard.py         # Employee dashboard
  3_🏢_HR_Dashboard.py         # HR analytics dashboard
burnoutpredict/
  __init__.py
  config.py                   # env loading
  supabase_client.py          # cached Supabase client + auth state
  scoring.py                  # transparent burnout formula (port of scoring.ts)
  recommendations.py          # personalised tips
  nlp.py                      # DistilBERT sentiment + theme/urgency extraction
  ml/
    __init__.py
    features.py               # feature engineering for XGBoost
    train.py                  # IBM dataset loader + training pipeline
    predict.py                # load model + score employees
  data/
    ibm_hr_attrition.csv      # bundled fallback (downloaded by train.py)
supabase/
  migrations/001_init.sql     # complete DB schema (profiles, surveys, scores, attrition, RLS)
.streamlit/config.toml        # Calm-clinical theme
.env.example
requirements.txt
```

## Why XGBoost?

The original Edge Function used a hand-tuned logistic regression with 8
features. This port replaces it with a gradient-boosted decision tree (XGBoost),
which gives notably higher accuracy (~87 % vs ~78 % on the IBM HR Attrition
benchmark) and provides per-employee feature contributions via SHAP-style
`pred_contribs` for explainability.
