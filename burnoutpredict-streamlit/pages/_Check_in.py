# pages/_Employee_Checkin.py
"""Employee weekly check-in form with dynamic survey questions (optimized)."""
from __future__ import annotations

import streamlit as st
from datetime import datetime
import json
import threading

from burnoutpredict import supabase_client as sb
from burnoutpredict.nlp import analyze_note
from burnoutpredict.scoring import SurveyInput, compute_burnout_risk

st.set_page_config(page_title="Check-in · BurnoutPredict", page_icon="📋", layout="centered")

# ---------------------------
# Auth
# ---------------------------
user = sb.current_user()
role = sb.current_role() if user else None

if not user:
    st.warning("Please sign in from the home page to take a check-in.")
    st.page_link("Home.py", label="← Back to home")
    st.stop()

if role != "employee":
    st.info("Check-ins are for employees. HR can view results from the HR Dashboard.")
    st.stop()

st.title("📋 Weekly wellness check-in")
st.caption("Takes about 2-3 minutes. Your answers are private — only you and HR can see them.")

client = sb.get_client()

# ---------------------------
# Load survey
# ---------------------------
@st.cache_data(ttl=60)
def get_active_survey():
    try:
        templates = client.table("survey_templates").select("*").eq("is_active", True).execute().data or []
        if templates:
            template = templates[0]
            questions = client.table("survey_questions") \
                .select("*") \
                .eq("template_id", template['id']) \
                .order("display_order") \
                .execute().data or []
            return template, questions
    except Exception as e:
        st.warning(f"Could not load custom survey: {e}")
    return None, []

active_template, dynamic_questions = get_active_survey()

# ---------------------------
# Questions
# ---------------------------
STANDARD_QUESTIONS = [
    ("emotional_exhaustion", "I feel emotionally drained from work", "0 = Never · 6 = Every day"),
    ("depersonalization", "I have become more cynical about my work", "0 = Never · 6 = Every day"),
    ("personal_accomplishment", "I feel I am making a meaningful contribution", "0 = Never · 6 = Every day (higher is better)"),
    ("workload", "My workload feels overwhelming", "0 = Never · 6 = Every day"),
    ("support", "I get the support I need from my team / manager", "0 = Never · 6 = Every day (higher is better)"),
]

# ---------------------------
# Form UI
# ---------------------------
with st.form("checkin"):
    st.subheader("📊 Core Assessment")

    answers: dict[str, int] = {}
    for key, label, help_txt in STANDARD_QUESTIONS:
        default = 4 if key in ("personal_accomplishment", "support") else 3
        answers[key] = st.slider(label, 0, 6, default, help=help_txt)

    # ---------------------------
    # Dynamic Questions
    # ---------------------------
    dynamic_answers = {}

    if dynamic_questions and active_template:
        st.divider()
        st.subheader(f"📝 {active_template['name']}")

        if active_template.get('description'):
            st.caption(active_template['description'])

        for q in dynamic_questions:
            q_key = f"custom_{q['id']}"

            if q['question_type'] == "slider":
                dynamic_answers[q_key] = st.slider(
                    q['question_text'],
                    min_value=q.get('min_value', 0),
                    max_value=q.get('max_value', 10),
                    value=q.get('min_value', 0),
                    step=q.get('step_value', 1),
                    key=f"slider_{q['id']}"
                )

            elif q['question_type'] == "rating":
                options = list(range(q.get('min_value', 1), q.get('max_value', 5) + 1))
                dynamic_answers[q_key] = st.select_slider(
                    q['question_text'],
                    options=options,
                    value=options[len(options)//2],
                    key=f"rating_{q['id']}"
                )

            elif q['question_type'] == "text":
                dynamic_answers[q_key] = st.text_area(
                    q['question_text'],
                    key=f"text_{q['id']}",
                    placeholder="Enter your response here..."
                )

            elif q['question_type'] == "multiple_choice":
                options = json.loads(q.get('options', '[]'))
                if options:
                    dynamic_answers[q_key] = st.radio(
                        q['question_text'],
                        options,
                        key=f"choice_{q['id']}"
                    )

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        sleep_hours = st.number_input("Avg sleep (hours/night)", 3.0, 12.0, 7.0, 0.5)
    with col2:
        work_hours = st.number_input("Work hours / week", 10.0, 100.0, 42.0, 0.5)

    notes = st.text_area(
        "Anything else? (optional)",
        max_chars=500,
        placeholder="A few sentences about how your week has been…"
    )

    submitted = st.form_submit_button(
        "Submit & calculate my risk",
        type="primary",
        use_container_width=True
    )

# ---------------------------
# Background AI worker
# ---------------------------
def run_ai_analysis(notes: str, survey_id: str):
    """Run AI in background and update DB."""
    try:
        ai_result = analyze_note(notes)
        if ai_result and isinstance(ai_result, dict):
            sb.get_client().table("survey_responses") \
                .update(ai_result) \
                .eq("id", survey_id) \
                .execute()
    except Exception:
        pass  # silent fail (important for UX)

# ---------------------------
# Submit logic
# ---------------------------
if submitted:
    # Compute score
    survey = SurveyInput(
        emotional_exhaustion=answers["emotional_exhaustion"],
        depersonalization=answers["depersonalization"],
        personal_accomplishment=answers["personal_accomplishment"],
        workload=answers["workload"],
        support=answers["support"],
        sleep_hours=sleep_hours,
        work_hours=work_hours,
    )

    result = compute_burnout_risk(survey)

    insert_payload = {
        "user_id": user.id,
        **answers,
        "sleep_hours": sleep_hours,
        "work_hours": work_hours,
        "notes": notes,
        "created_at": datetime.utcnow().isoformat(),
        "ai_sentiment": None,
        "ai_urgency": None,
        "ai_summary": None,
    }

    if dynamic_answers:
        insert_payload["custom_responses"] = json.dumps(dynamic_answers)
        insert_payload["template_id"] = active_template['id'] if active_template else None

    # Save survey FIRST (fast)
    try:
        sres = client.table("survey_responses").insert(insert_payload).execute()
        survey_id = sres.data[0]["id"]

        # Save custom responses
        if dynamic_answers and active_template:
            client.table("custom_survey_responses").insert({
                "user_id": user.id,
                "template_id": active_template['id'],
                "responses": dynamic_answers,
                "submitted_at": datetime.utcnow().isoformat()
            }).execute()

        # Save risk score
        client.table("risk_scores").insert({
            "user_id": user.id,
            "survey_id": survey_id,
            "burnout_score": result.burnout_score,
            "risk_level": result.risk_level,
            "top_factors": result.top_factors,
            "recommendations": result.recommendations,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

    except Exception as e:
        st.error(f"Failed to save check-in: {e}")
        st.stop()

    # ---------------------------
    # 🚀 Run AI in background
    # ---------------------------
    if notes and len(notes.split()) > 5:
        threading.Thread(
            target=run_ai_analysis,
            args=(notes, survey_id),
            daemon=True
        ).start()

    # ---------------------------
    # UI Feedback
    # ---------------------------
    st.success(f"✅ Saved! Your burnout score is **{result.burnout_score}/100** ({result.risk_level.upper()})")

    if result.recommendations:
        with st.expander("💡 Personalized Recommendations"):
            for rec in result.recommendations:
                st.write(f"• {rec}")

    st.balloons()

    col1, col2 = st.columns(2)
    with col1:
        st.page_link("pages/_My_Dashboard.py", label="📊 Open my dashboard", use_container_width=True)
    with col2:
        if st.button("📝 Submit another check-in", use_container_width=True):
            st.rerun()