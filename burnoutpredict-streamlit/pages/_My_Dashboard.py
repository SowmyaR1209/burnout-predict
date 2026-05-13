"""Employee dashboard — personal burnout tracking, history, and insights."""
from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import json

from burnoutpredict import supabase_client as sb

st.set_page_config(page_title="My Dashboard · BurnoutPredict", page_icon="📊", layout="wide")

user = sb.current_user()
role = sb.current_role() if user else None

if not user:
    st.warning("Please sign in from the home page first.")
    st.page_link("app.py", label="← Back to home")
    st.stop()

# Fetch user's profile to get full name
@st.cache_data(ttl=60)
def get_user_profile(user_id):
    client = sb.get_client()
    try:
        profile = client.table("profiles").select("full_name, department, job_title").eq("user_id", user_id).execute()
        if profile.data and len(profile.data) > 0:
            return profile.data[0]
    except Exception as e:
        st.warning(f"Could not fetch profile: {e}")
    return {"full_name": user.email.split('@')[0], "department": "", "job_title": ""}

user_profile = get_user_profile(user.id)
user_name = user_profile.get('full_name', user.email.split('@')[0])

st.title(f"📊 Welcome, {user_name}!")
st.caption("Your personal burnout tracking and insights")

client = sb.get_client()

# Load employee data
@st.cache_data(ttl=30)
def load_employee_data(user_id):
    # Load survey responses
    surveys = client.table("survey_responses").select(
        "*"
    ).eq("user_id", user_id).order("created_at", desc=True).execute().data or []
    
    # Load risk scores
    risks = client.table("risk_scores").select(
        "*"
    ).eq("user_id", user_id).order("created_at", desc=True).execute().data or []
    
    # Load custom survey responses with template info
    custom_surveys = client.table("custom_survey_responses").select(
        "*, survey_templates!left(name)"
    ).eq("user_id", user_id).order("submitted_at", desc=True).execute().data or []
    
    return surveys, risks, custom_surveys

# Delete functions
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

def delete_custom_survey_response(response_id):
    try:
        client.table("custom_survey_responses").delete().eq("id", response_id).execute()
        st.success("✅ Custom survey response deleted successfully!")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error deleting custom survey: {e}")
        return False

def delete_all_history():
    try:
        # Delete all custom survey responses
        client.table("custom_survey_responses").delete().eq("user_id", user.id).execute()
        # Get all survey ids
        surveys = client.table("survey_responses").select("id").eq("user_id", user.id).execute()
        for survey in surveys.data:
            # Delete risk scores
            client.table("risk_scores").delete().eq("survey_id", survey['id']).execute()
        # Delete all survey responses
        client.table("survey_responses").delete().eq("user_id", user.id).execute()
        st.success("✅ All history deleted successfully!")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error deleting history: {e}")
        return False

surveys, risks, custom_surveys = load_employee_data(user.id)

# Display current metrics if data exists
if risks:
    latest_risk = risks[0]
    latest_survey = surveys[0] if surveys else None
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        score = latest_risk.get('burnout_score', 0)
        st.metric("Current Burnout Score", f"{score:.0f}/100")
    
    with col2:
        risk_level = latest_risk.get('risk_level', 'unknown').upper()
        color = "🟢" if risk_level == "LOW" else "🟡" if risk_level == "MODERATE" else "🔴"
        st.metric("Risk Level", f"{color} {risk_level}")
    
    with col3:
        if latest_survey:
            st.metric("Work Hours/Week", f"{latest_survey.get('work_hours', 0)}h")
    
    with col4:
        if latest_survey:
            st.metric("Sleep Hours/Night", f"{latest_survey.get('sleep_hours', 0)}h")
    
    # Show recommendations
    recommendations = latest_risk.get('recommendations', [])
    if recommendations:
        with st.expander("💡 Personalized Recommendations", expanded=True):
            for rec in recommendations:
                st.write(f"• {rec}")
else:
    st.info("No check-in data yet. Complete your first wellness check-in to see insights!")
    if st.button("📝 Take Check-in Now"):
        st.switch_page("pages/_Employee_Checkin.py")

# ==================== HISTORY SECTION ====================
st.divider()
st.subheader("📜 Your Wellness History")

# Create tabs for different history views
history_tab1, history_tab2, history_tab3 = st.tabs([
    "📊 Burnout Over Time", 
    "📝 Check-in History", 
    "📋 Custom Survey History"
])

with history_tab1:
    st.markdown("### Burnout Score Trend Over Time")
    
    if len(risks) > 1:
        # Prepare data for chart
        history_data = []
        for risk in risks:
            created_at = risk.get('created_at', '')
            if created_at:
                date = created_at[:10]
                score = risk.get('burnout_score', 0)
                level = risk.get('risk_level', 'unknown')
                history_data.append({
                    'Date': date,
                    'Burnout Score': score,
                    'Risk Level': level
                })
        
        df_history = pd.DataFrame(history_data)
        df_history = df_history.sort_values('Date')
        
        # Create line chart
        fig = px.line(df_history, x='Date', y='Burnout Score', 
                     title="Your Burnout Score Progression",
                     markers=True,
                     color_discrete_sequence=['#FF6B6B'])
        
        # Add risk level zones
        fig.add_hrect(y0=0, y1=33, line_width=0, fillcolor="green", opacity=0.1, annotation_text="Low Risk")
        fig.add_hrect(y0=33, y1=66, line_width=0, fillcolor="yellow", opacity=0.1, annotation_text="Moderate Risk")
        fig.add_hrect(y0=66, y1=100, line_width=0, fillcolor="red", opacity=0.1, annotation_text="High Risk")
        
        fig.update_layout(height=400, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
        
        # Show statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            min_score = df_history['Burnout Score'].min()
            max_score = df_history['Burnout Score'].max()
            st.metric("Lowest Score", f"{min_score:.0f}")
        with col2:
            st.metric("Highest Score", f"{max_score:.0f}")
        with col3:
            if len(df_history) > 1:
                trend = df_history['Burnout Score'].iloc[-1] - df_history['Burnout Score'].iloc[0]
                trend_text = "↑ Increasing" if trend > 0 else "↓ Decreasing" if trend < 0 else "→ Stable"
                st.metric("Overall Trend", trend_text, delta=f"{trend:.1f}" if trend != 0 else None)
    else:
        st.info("Need at least 2 check-ins to see trends. Complete more check-ins!")

with history_tab2:
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

with history_tab3:
    st.markdown("### 📋 Custom Survey Submission History")
    
    if custom_surveys:
        for idx, survey in enumerate(custom_surveys):
            # Handle template name properly
            template_info = survey.get('survey_templates', {})
            if isinstance(template_info, dict):
                template_name = template_info.get('name', 'Custom Survey')
            else:
                template_name = 'Custom Survey'
            
            submitted_at = survey.get('submitted_at', '')
            date = submitted_at[:10] if submitted_at else 'Unknown date'
            
            with st.expander(f"📋 {template_name} - {date}", expanded=(idx == 0)):
                col1, col2 = st.columns([5, 1])
                
                with col2:
                    if st.button("🗑️ Delete", key=f"del_custom_{survey['id']}"):
                        if delete_custom_survey_response(survey['id']):
                            st.rerun()
                
                responses = survey.get('responses', {})
                if isinstance(responses, str):
                    try:
                        responses = json.loads(responses)
                    except:
                        responses = {}
                
                if responses:
                    # Get the actual questions for this template
                    template_id = survey.get('template_id')
                    question_map = {}
                    
                    if template_id:
                        try:
                            questions_data = client.table("survey_questions").select("id, question_text, question_type, min_value, max_value").eq("template_id", template_id).execute().data or []
                            for q in questions_data:
                                question_map[f"custom_{q['id']}"] = q
                        except Exception as e:
                            st.warning(f"Could not load question details: {e}")
                    
                    # Display answers with actual question text
                    for key, value in responses.items():
                        # Get question details
                        question_info = question_map.get(key, {})
                        question_text = question_info.get('question_text', key.replace('custom_', '').replace('_', ' ').title())
                        question_type = question_info.get('question_type', 'text')
                        max_value = question_info.get('max_value', 10)
                        
                        # Format the answer nicely
                        if question_type == 'slider' and isinstance(value, (int, float)):
                            formatted_answer = f"⭐ {value}/{max_value}"
                        elif question_type == 'rating' and isinstance(value, (int, float)):
                            formatted_answer = f"★ {value}/{max_value}"
                        elif value:
                            formatted_answer = str(value)
                        else:
                            formatted_answer = "Not answered"
                        
                        st.markdown(f"**{question_text}**")
                        st.write(f"Answer: {formatted_answer}")
                        st.divider()
                else:
                    st.info("No response data available")
    else:
        st.info("No custom survey submissions yet")

# Export data option
st.divider()
if surveys:
    with st.expander("📥 Export Your Data"):
        st.markdown("Download your wellness data for personal records")
        
        # Prepare export data
        export_data = []
        for survey in surveys:
            risk_score = next((r.get('burnout_score') for r in risks if r.get('survey_id') == survey.get('id')), None)
            risk_level = next((r.get('risk_level') for r in risks if r.get('survey_id') == survey.get('id')), None)
            
            export_data.append({
                'Date': survey.get('created_at', '')[:10] if survey.get('created_at') else '',
                'Burnout Score': risk_score,
                'Risk Level': risk_level,
                'Emotional Exhaustion': survey.get('emotional_exhaustion'),
                'Depersonalization': survey.get('depersonalization'),
                'Personal Accomplishment': survey.get('personal_accomplishment'),
                'Workload': survey.get('workload'),
                'Support': survey.get('support'),
                'Work Hours': survey.get('work_hours'),
                'Sleep Hours': survey.get('sleep_hours'),
                'Sentiment': survey.get('ai_sentiment'),
                'Urgency': survey.get('ai_urgency'),
                'AI Summary': survey.get('ai_summary')
            })
        
        export_df = pd.DataFrame(export_data)
        csv = export_df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"burnout_history_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

st.divider()
st.caption("💡 Your data is private. Only you and HR can see these insights.")