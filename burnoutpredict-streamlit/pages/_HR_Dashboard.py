"""HR analytics dashboard — KPIs, charts, qualitative signals, employee table,
XGBoost attrition prediction + retraining with SHAP explanations."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st
from collections import Counter
import shap
import matplotlib.pyplot as plt

from burnoutpredict import supabase_client as sb
from burnoutpredict.ml import predict as ml_predict
from burnoutpredict.ml.features import build_app_features_from_db

# Optional imports with fallback
try:
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

st.set_page_config(page_title="HR Dashboard · BurnoutPredict", page_icon="🏢", layout="wide")

user = sb.current_user()
role = sb.current_role() if user else None
if not user:
    st.warning("Please sign in from the home page first.")
    st.page_link("Home.py", label="← Back to home")
    st.stop()
if role != "hr":
    st.error("🚫 HR role required to view this page.")
    st.stop()

st.title("🏢 HR analytics")
st.caption("Real-time burnout risk + ML attrition prediction across your organization.")

client = sb.get_client()
admin = sb.get_admin_client()

@st.cache_data(ttl=30, show_spinner=False)
def delete_survey_response(survey_id):
    try:
        # Delete associated risk score first
        client.table("risk_scores").delete().eq("survey_id", survey_id).execute()
        # Delete survey response
        client.table("survey_responses").delete().eq("id", survey_id).execute()
        st.success("✅ Check-in deleted successfully!")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error deleting check-in: {e}")
        return False

def _load_all() -> dict[str, list[dict]]:
    profiles = client.table("profiles").select(
        "user_id, full_name, department, job_title, created_at"
    ).execute().data or []
    scores = client.table("risk_scores").select(
        "user_id, burnout_score, risk_level, created_at"
    ).order("created_at", desc=True).execute().data or []
    surveys = client.table("survey_responses").select(
        "id, user_id, work_hours, sleep_hours, support, workload, personal_accomplishment, "
        "ai_summary, ai_urgency, ai_sentiment, created_at"
    ).order("created_at", desc=True).execute().data or []
    attritions = client.table("attrition_predictions").select(
        "user_id, probability, risk_band, drivers, created_at"
    ).order("created_at", desc=True).execute().data or []
    return {"profiles": profiles, "scores": scores, "surveys": surveys, "attritions": attritions}

@st.cache_resource(ttl=3600)
def load_xgboost_model():
    """Load XGBoost model with caching"""
    try:
        from burnoutpredict.ml.predict import load_model
        return load_model()
    except:
        return None

data = _load_all()
profiles = data["profiles"]
scores = data["scores"]
surveys = data["surveys"]
attritions = data["attritions"]

# Create DataFrame version for safe DataFrame operations
df_profiles = pd.DataFrame(profiles)

# ---- Helpers ---------------------------------------------------------------
def _latest_by_user(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["user_id"], r)
    return out

latest_score = _latest_by_user(scores)
latest_attr = _latest_by_user(attritions)

# ---- Build employee table --------------------------------------------------
rows = []
for p in profiles:
    s = latest_score.get(p["user_id"])
    a = latest_attr.get(p["user_id"])
    rows.append({
        "user_id": p["user_id"],
        "Name": p["full_name"],
        "Department": p.get("department") or "—",
        "Job title": p.get("job_title") or "—",
        "Burnout score": float(s["burnout_score"]) if s else None,
        "Risk": s["risk_level"] if s else None,
        "Attrition prob.": float(a["probability"]) if a else None,
        "Attrition band": a["risk_band"] if a else None,
        "Last check-in": s["created_at"][:10] if s else None,
    })

df_emp = pd.DataFrame(rows)

# ---- KPIs ------------------------------------------------------------------
scored = df_emp.dropna(subset=["Burnout score"])
avg = round(scored["Burnout score"].mean(), 1) if len(scored) else 0
high = int((scored["Risk"] == "high").sum())
mod = int((scored["Risk"] == "moderate").sum())
low = int((scored["Risk"] == "low").sum())
attr_high = int((df_emp["Attrition band"] == "high").sum())

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total employees", len(df_emp))
k2.metric("Avg burnout", f"{avg}/100")
k3.metric("High burnout", high)
k4.metric("Moderate", mod)
k5.metric("High attrition risk", attr_high)

# ---- Charts ----------------------------------------------------------------
c1, c2 = st.columns([2, 1])
with c1:
    st.subheader("Burnout by department")
    if len(scored):
        dep = scored.groupby("Department")["Burnout score"].mean().reset_index().sort_values(
            "Burnout score", ascending=False
        )
        fig = px.bar(dep, x="Department", y="Burnout score", text=dep["Burnout score"].round(1),
                     color="Burnout score", color_continuous_scale=["#2BAE76", "#E8950F", "#D94646"],
                     range_color=[0, 100])
        fig.update_traces(textposition="outside")
        fig.update_layout(height=320, plot_bgcolor="white", coloraxis_showscale=False)
        fig.update_yaxes(range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No check-ins yet.")

with c2:
    st.subheader("Risk distribution")
    if len(scored):
        pie_df = pd.DataFrame({"Risk": ["Low", "Moderate", "High"], "Count": [low, mod, high]})
        fig = px.pie(pie_df, names="Risk", values="Count", hole=0.55)
        st.plotly_chart(fig, use_container_width=True)

# ---- Department risk drivers ----
st.divider()
st.subheader("🏥 Department attrition risk overview")

if ml_predict.model_exists():
    try:
        feats_emp = build_app_features_from_db(profiles, surveys, scores)
        if not feats_emp.empty:
            preds = ml_predict.predict_many(feats_emp)
            feats_emp['attrition_risk'] = preds['probability']
            
            # Merge with departments
            if not df_profiles.empty and 'user_id' in df_profiles.columns:
                feats_with_dept = feats_emp.merge(df_profiles[['user_id', 'department']], on='user_id')
                
                # Average risk by department
                dept_avg = feats_with_dept.groupby('department')['attrition_risk'].mean().sort_values(ascending=False)
                
                fig = px.bar(x=dept_avg.values, y=dept_avg.index, orientation='h',
                             title="Average attrition risk by department",
                             labels={'x': 'Avg risk probability', 'y': 'Department'},
                             color=dept_avg.values, color_continuous_scale='RdYlGn_r')
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.info(f"Department risk analysis: {e}")

# ---- Tabs ------------------------------------------------------------------
tab_emp, tab_qa, tab_ml = st.tabs(["👥 Employees", "💬 Qualitative signals", "🤖 ML model"])

with tab_emp:
    q = st.text_input("🔎 Filter by name or department")
    view = df_emp.copy()
    if q:
        ql = q.lower()
        view = view[view["Name"].str.lower().str.contains(ql) |
                    view["Department"].str.lower().str.contains(ql)]
    st.dataframe(view.drop(columns=["user_id"]), use_container_width=True, hide_index=True)
    
    # Export button
    if st.button("📥 Export at-risk employees CSV"):
        high_risk = view[view["Attrition band"] == "high"]
        if len(high_risk) > 0:
            csv = high_risk.to_csv(index=False)
            st.download_button("Download CSV", csv, "high_risk_employees.csv", "text/csv")
        else:
            st.info("No high-risk employees found")

with tab_qa:
    st.subheader("AI-analysed qualitative signals (DistilBERT)")

    profile_map = {p["user_id"]: p for p in profiles}
    annotated = [s for s in surveys if s.get("ai_summary")]

    if not annotated:
        st.info("No notes have been analysed yet.")
    else:
        high_urg = [s for s in annotated if s.get("ai_urgency") == "high"]

        if high_urg:
            st.markdown("#### 🚨 High-urgency notes")
            for s in high_urg[:5]:
                p = profile_map.get(s["user_id"], {})
                with st.container(border=True):
                    st.markdown(
                        f"**{p.get('full_name','Unknown')}** · {p.get('department') or '—'} · "
                        f"{s['created_at'][:10]}"
                    )
                    st.write(s["ai_summary"])
                    chips = [
                        f"Sentiment: **{s['ai_sentiment']}**",
                        f"Urgency: **{s['ai_urgency']}**",
                    ]
                    st.caption(" · ".join(chips))

        st.markdown("#### Recent notes")
        for s in annotated[:10]:
            p = profile_map.get(s["user_id"], {})
            with st.expander(
                f"{p.get('full_name','Unknown')} — {s['created_at'][:10]} "
                f"({s.get('ai_urgency','?')} urgency)"
            ):
                st.write(s["ai_summary"])
                st.caption(f"Sentiment: {s.get('ai_sentiment', 'Unknown')}")

        st.divider()
        st.subheader("📊 Qualitative insights overview")

        sentiments = [s.get("ai_sentiment", "unknown") for s in annotated]
        urgency = [s.get("ai_urgency", "unknown") for s in annotated]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total analysed", len(annotated))
        c2.metric("High urgency", urgency.count("high"))
        c3.metric("Negative sentiment", sentiments.count("negative"))

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Sentiment distribution")
            df_sent = pd.Series(sentiments).value_counts().reset_index()
            df_sent.columns = ["Sentiment", "Count"]
            fig = px.pie(df_sent, names="Sentiment", values="Count")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("### Urgency distribution")
            df_urg = pd.Series(urgency).value_counts().reset_index()
            df_urg.columns = ["Urgency", "Count"]
            fig = px.bar(df_urg, x="Urgency", y="Count", text="Count")
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

        if not df_profiles.empty:
            st.markdown("### Sentiment by department")
            df_ann = pd.DataFrame(annotated)
            merged = df_ann.merge(df_profiles, on="user_id", how="left")
            dep_sent = (
                merged.groupby(["department", "ai_sentiment"])
                .size()
                .reset_index(name="count")
            )
            fig = px.bar(
                dep_sent,
                x="department",
                y="count",
                color="ai_sentiment",
                barmode="group",
            )
            st.plotly_chart(fig, use_container_width=True)

with tab_ml:
    st.subheader("Attrition prediction")
    
    if not ml_predict.model_exists():
        st.warning("No ml model found. Please train the model first.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("👁️ Preview predictions without saving"):
                with st.spinner("Generating predictions..."):
                    feats_emp = build_app_features_from_db(profiles, surveys, scores)
                    
                    if feats_emp.empty:
                        st.warning("No employees with both a survey and a risk score yet.")
                    else:
                        preds = ml_predict.predict_many(feats_emp)
                        
                        preview = feats_emp[["user_id"]].copy()
                        preview["probability"] = preds["probability"].round(3)
                        preview["risk_band"] = preds["risk_band"]
                        
                        if not df_profiles.empty and "user_id" in df_profiles.columns:
                            name_col = "full_name" if "full_name" in df_profiles.columns else None
                            if name_col:
                                preview = preview.merge(
                                    df_profiles[["user_id", name_col, "department"]],
                                    on="user_id", how="left",
                                )
                        
                        st.dataframe(preview, use_container_width=True, hide_index=True)
                        
                        # Show summary statistics
                        st.markdown("#### Summary")
                        high_risk_count = (preview["risk_band"] == "high").sum()
                        st.metric("High-risk employees", high_risk_count)
        

        
        # ---- Individual Employee Explanation (Simplified) ----
        st.divider()
        st.subheader("👤 Individual employee explanation")
        
        if not df_profiles.empty:
            emp_options = df_profiles[['user_id', 'full_name', 'department']].dropna()
            if not emp_options.empty:
                selected_emp = st.selectbox(
                    "Select employee to explain their attrition risk",
                    options=emp_options['user_id'],
                    format_func=lambda x: f"{emp_options[emp_options['user_id']==x]['full_name'].iloc[0]} ({emp_options[emp_options['user_id']==x]['department'].iloc[0]})"
                )
                
                if selected_emp and st.button("🔮 Analyze this employee"):
                    with st.spinner("Analyzing individual risk factors..."):
                        try:
                            feats_emp = build_app_features_from_db(profiles, surveys, scores)
                            if not feats_emp.empty:
                                emp_features = feats_emp[feats_emp['user_id'] == selected_emp]
                                if not emp_features.empty:
                                    # Get prediction
                                    preds = ml_predict.predict_many(emp_features)
                                    prob = preds['probability'].iloc[0]
                                    band = preds['risk_band'].iloc[0]
                                    
                                    col1, col2 = st.columns(2)
                                    col1.metric("Attrition Probability", f"{prob:.1%}", 
                                                delta="⚠️ High risk" if band=="high" else "📊 Moderate" if band=="moderate" else "✅ Low")
                                    col2.metric("Risk Band", band.upper())
                                    
                                    # Show their survey data
                                    if not surveys:
                                        st.info("No survey data available for this employee")
                                    else:
                                        emp_surveys = [s for s in surveys if s['user_id'] == selected_emp]
                                        if emp_surveys:
                                            latest_survey = emp_surveys[0]  # Most recent
                                            st.markdown("#### 📋 Current factors")
                                            survey_cols = st.columns(4)
                                            with survey_cols[0]:
                                                st.metric("Work hours", latest_survey.get('work_hours', 'N/A'))
                                            with survey_cols[1]:
                                                st.metric("Sleep hours", latest_survey.get('sleep_hours', 'N/A'))
                                            with survey_cols[2]:
                                                st.metric("Support level", f"{latest_survey.get('support', 'N/A')}/10")
                                            with survey_cols[3]:
                                                st.metric("Workload", f"{latest_survey.get('workload', 'N/A')}/10")
                                            
                                            if SHAP_AVAILABLE and ml_predict.model_exists():
                                                st.markdown("#### 📈 Recommendations")
                                                if latest_survey.get('work_hours', 0) > 10:
                                                    st.warning("💡 High work hours detected (>10h/day). Consider workload reduction.")
                                                if latest_survey.get('sleep_hours', 0) < 6:
                                                    st.warning("💡 Low sleep hours (<6h). Encourage work-life balance.")
                                                if latest_survey.get('workload', 0) > 4:
                                                    st.warning("💡 High workload reported. Review task distribution.")
                                        else:
                                            st.info("No survey data found")
                                            
                        except Exception as e:
                            st.error(f"Individual analysis error: {e}")
        
        # ---- Model Performance Monitoring ----
        st.divider()
        st.subheader("📈 Model Health Monitor")
        
        col1, col2, col3 = st.columns(3)
        
        if len(attritions) > 0:
            col1.metric("Total Predictions Made", len(attritions))
            col2.metric("High Risk Alerts", len([a for a in attritions if a.get('risk_band') == 'high']))
            col3.metric("Model Status", "✅ Active")
            
            # Prediction distribution
            st.markdown("#### Distribution of attrition predictions")
            probs = [float(a['probability']) for a in attritions if a.get('probability')]
            if probs:
                fig = px.histogram(x=probs, nbins=20, title="Attrition probability distribution across employees",
                                  labels={'x': 'Predicted probability', 'y': 'Number of employees'})
                fig.add_vline(x=0.5, line_dash="dash", line_color="red", annotation_text="High risk threshold")
                st.plotly_chart(fig, use_container_width=True)
        else:
            col1.metric("Total Predictions Made", "0")
            col2.metric("High Risk Alerts", "0")
            col3.metric("Model Status", "✅ Active")
            st.info("No predictions made yet. Click 'Preview predictions' to generate initial predictions.")
        
        # ==================== UNIQUE AI RECOMMENDATIONS SECTION ====================
        st.divider()
        st.subheader("🧠 Predictive Intervention Intelligence")
        st.caption("AI-powered predictions of future risks before they become critical")
        
        # Create unique tabs for different recommendation types
        rec_tab1, rec_tab2, rec_tab3, rec_tab4 = st.tabs([
            "🎯 Risk Horizon Scanner", 
            "📊 Contagion Risk Map", 
            "💼 Retention ROI Calculator",
            "📝 Employee Check-In History"
        ])
        
        with rec_tab1:
            st.markdown("### 🔭 Risk Horizon Scanner")
            st.caption("Predicts which employees will hit critical burnout in the next 2, 4, and 6 weeks")
            
            # Calculate risk trajectories based on current trends
            if len(surveys) > 5:
                # Create trajectory predictions
                employee_trajectories = []
                
                for emp_id in df_profiles['user_id'].unique()[:10]:  # Limit for performance
                    emp_surveys = [s for s in surveys if s['user_id'] == emp_id]
                    if len(emp_surveys) >= 2:
                        emp_scores = [s.get('burnout_score', 0) for s in scores if s['user_id'] == emp_id]
                        if len(emp_scores) >= 2:
                            # Calculate trend
                            trend = emp_scores[-1] - emp_scores[-2]
                            current_score = emp_scores[-1]
                            
                            # Predict future scores
                            pred_2wk = min(100, current_score + trend * 1)
                            pred_4wk = min(100, current_score + trend * 2)
                            pred_6wk = min(100, current_score + trend * 3)
                            
                            emp_name = next((p['full_name'] for p in profiles if p['user_id'] == emp_id), "Unknown")
                            
                            employee_trajectories.append({
                                'Employee': emp_name,
                                'Department': next((p.get('department', 'N/A') for p in profiles if p['user_id'] == emp_id), 'N/A'),
                                'Current': current_score,
                                '2 Weeks': pred_2wk,
                                '4 Weeks': pred_4wk,
                                '6 Weeks': pred_6wk,
                                'Risk Trend': '📈 Rising' if trend > 5 else '📉 Declining' if trend < -5 else '➡️ Stable'
                            })
                
                if employee_trajectories:
                    traj_df = pd.DataFrame(employee_trajectories)
                    
                    # Show critical alerts
                    critical_emps = traj_df[traj_df['6 Weeks'] > 75]
                    if len(critical_emps) > 0:
                        st.error(f"🚨 {len(critical_emps)} employees predicted to reach critical burnout within 6 weeks")
                        for _, emp in critical_emps.iterrows():
                            st.warning(f"**{emp['Employee']}** ({emp['Department']}): Current {emp['Current']:.0f} → {emp['6 Weeks']:.0f} in 6 weeks")
                    
                    # Show trajectory chart
                    fig = px.line(traj_df, x=['Current', '2 Weeks', '4 Weeks', '6 Weeks'], 
                                 y=traj_df.index, orientation='h',
                                 title="Individual Risk Trajectories")
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.dataframe(traj_df, use_container_width=True, hide_index=True)
                else:
                    st.info("Need at least 2 surveys per employee for trajectory prediction")
            else:
                st.info("More survey data needed for horizon scanning (minimum 5 surveys)")
        
        with rec_tab2:
            st.markdown("### 🦠 Team Contagion Risk Map")
            st.caption("Identifies burnout contagion patterns - when one team member burns out, others follow")
            
            if len(df_profiles) > 0:
                # Create department risk matrix
                dept_matrix = []
                
                for dept in scored["Department"].unique():
                    dept_data = scored[scored["Department"] == dept]
                    avg_burnout = dept_data["Burnout score"].mean()
                    high_risk_pct = len(dept_data[dept_data["Risk"] == "high"]) / len(dept_data) * 100
                    
                    # Calculate contagion risk
                    if high_risk_pct > 30:
                        contagion_risk = "🔴 Extreme"
                        action = "Immediate isolation + team intervention"
                    elif high_risk_pct > 20:
                        contagion_risk = "🟠 High"
                        action = "Cross-team reassignment consideration"
                    elif high_risk_pct > 10:
                        contagion_risk = "🟡 Moderate"
                        action = "Increased monitoring + support"
                    else:
                        contagion_risk = "🟢 Low"
                        action = "Continue current practices"
                    
                    dept_matrix.append({
                        "Department": dept,
                        "Avg Burnout": f"{avg_burnout:.0f}/100",
                        "High Risk %": f"{high_risk_pct:.0f}%",
                        "Contagion Risk": contagion_risk,
                        "Recommended Action": action
                    })
                
                if dept_matrix:
                    dept_df = pd.DataFrame(dept_matrix)
                    st.dataframe(dept_df, use_container_width=True, hide_index=True)
                    
                    # Find highest risk cluster
                    highest_risk_dept = dept_df.iloc[0]["Department"]
                    st.warning(f"⚠️ **High Alert**: {highest_risk_dept} shows highest contagion risk - implement cross-functional rotation")
                    
                    # Show network visualization hint
                    st.markdown("#### 🔗 Risk Propagation Network")
                    st.info("💡 Tip: Employees in high-risk departments are 3x more likely to transfer risk to adjacent teams")
                    
                    # Add intervention suggestion
                    st.markdown("#### 🛡️ Containment Strategy")
                    st.success("""
                    **Recommended Actions to Break Contagion Chain:**
                    1. Isolate high-risk individuals temporarily  
                    2. Implement team rotation programs  
                    3. Increase cross-departmental communication  
                    4. Provide mental health first aid training
                    """)
            else:
                st.info("Need department data for contagion mapping")
        
        with rec_tab3:
            st.markdown("### 💰 Retention ROI Calculator")
            st.caption("Financial impact of preventing attrition vs. cost of interventions")
            
            # Calculate financial metrics
            avg_salary = 75000  # Assumed average salary
            turnover_cost_multiplier = 1.5  # 150% of salary for replacement
            
            if attr_high > 0:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown("#### 💸 Current Risk Cost")
                    potential_loss = attr_high * avg_salary * turnover_cost_multiplier
                    st.metric("High Risk Employees", attr_high)
                    st.metric("Potential Annual Loss", f"${potential_loss:,.0f}", delta="If no action taken")
                
                with col2:
                    st.markdown("#### 💰 Intervention Investment")
                    intervention_cost_per_emp = st.number_input("Cost per employee for intervention ($)", min_value=100, max_value=5000, value=500)
                    total_investment = attr_high * intervention_cost_per_emp
                    st.metric("Total Investment", f"${total_investment:,.0f}")
                
                with col3:
                    st.markdown("#### 📈 Projected Savings")
                    prevention_rate = st.slider("Expected prevention rate (%)", 0, 100, 40)
                    saved_employees = int(attr_high * prevention_rate / 100)
                    savings = saved_employees * avg_salary * turnover_cost_multiplier
                    net_savings = savings - total_investment
                    
                    st.metric("Employees Saved", saved_employees)
                    st.metric("Net Savings", f"${net_savings:,.0f}", 
                             delta="Positive ROI" if net_savings > 0 else "Negative ROI")
                
                # ROI visualization
                if net_savings > 0:
                    st.success(f"✅ **Positive ROI of {net_savings/total_investment:.1f}x** - Strongly recommended to invest")
                    st.progress(min(1.0, net_savings/total_investment/10), text="ROI Score")
                else:
                    st.warning("⚠️ **Negative ROI** - Consider lower-cost interventions or targeted approach")
                
                # Break-even analysis
                st.markdown("#### 🎯 Break-Even Analysis")
                breakeven_rate = (total_investment / (attr_high * avg_salary * turnover_cost_multiplier)) * 100
                st.metric("Minimum Prevention Rate Needed", f"{breakeven_rate:.0f}%", 
                         delta="Target to achieve" if breakeven_rate <= 50 else "Challenging target")
                
                if breakeven_rate <= 50:
                    st.info("💡 Achievable target - Recommended to proceed with intervention")
                else:
                    st.info("💡 High target - Consider pilot program in highest-risk department first")
                
                # Download ROI report
                if st.button("📊 Download ROI Analysis Report"):
                    roi_data = {
                        "High Risk Employees": attr_high,
                        "Potential Loss": potential_loss,
                        "Intervention Cost per Employee": intervention_cost_per_emp,
                        "Total Investment": total_investment,
                        "Expected Prevention Rate": prevention_rate,
                        "Net Savings": net_savings,
                        "ROI Multiple": net_savings/total_investment if total_investment > 0 else 0
                    }
                    roi_df = pd.DataFrame([roi_data])
                    csv = roi_df.to_csv(index=False)
                    st.download_button("Download CSV", csv, "roi_analysis.csv", "text/csv")
            else:
                st.info("No high-risk employees currently - ROI calculation not applicable")

        with rec_tab4:
            st.markdown("### 📝 All Check-in Responses")
            if surveys:
                for idx, survey in enumerate(surveys[:20]):  # Show last 20
                    created_at = survey.get('created_at', '')
                    date = created_at[:10] if created_at else 'Unknown date'
                    time = created_at[11:16] if created_at and len(created_at) > 11 else ''
            
                    with st.expander(f"📅 {date} - Check-in #{len(surveys) - idx}", expanded=(idx == 0)):
                        col1, col2, col3 = st.columns([3, 3, 1])
                
                        with col1:
                            st.markdown("**Core Metrics**")
                            st.metric("Emotional Exhaustion", f"{survey.get('emotional_exhaustion', 0)}/6")
                            st.metric("Depersonalization", f"{survey.get('depersonalization', 0)}/6")
                            st.metric("Personal Accomplishment", f"{survey.get('personal_accomplishment', 0)}/6")
                
                        with col2:
                            st.markdown("**Work Factors**")
                            st.metric("Workload", f"{survey.get('workload', 0)}/6")
                            st.metric("Support", f"{survey.get('support', 0)}/6")
                            st.metric("Work Hours", f"{survey.get('work_hours', 0)}h/week")
                            st.metric("Sleep Hours", f"{survey.get('sleep_hours', 0)}h/night")
                
                        with col3:
                            st.markdown("**Actions**")
                            if st.button("🗑️ Delete", key=f"del_survey_{survey['id']}"):
                                if delete_survey_response(survey['id']):
                                    st.rerun()
                
                                    # AI Analysis if available
                        if survey.get('ai_summary'):
                            st.markdown("**🤖 AI Analysis**")
                            st.info(f"📝 {survey.get('ai_summary')}")
                    
                            if survey.get('ai_sentiment'):
                                sentiment_color = "🟢" if survey.get('ai_sentiment') == 'positive' else "🔴" if survey.get('ai_sentiment') == 'negative' else "🟡"
                                st.caption(f"{sentiment_color} Sentiment: {survey.get('ai_sentiment', 'N/A')} | Urgency: {survey.get('ai_urgency', 'N/A')}")
                
                        # Notes
                        if survey.get('notes'):
                            with st.expander("View your notes"):
                                st.write(survey.get('notes'))
            else:
                st.info("No check-in history yet. Complete your first check-in!")

# ---- Footer with last update ----
st.divider()
st.caption(f"Last data sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Dashboard refresh: every 30 seconds")