"""HR Survey Management - Create, edit, and manage custom survey questions."""
from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import json
import time

from burnoutpredict import supabase_client as sb

st.set_page_config(page_title="Survey Manager · BurnoutPredict", page_icon="📝", layout="wide")

# Authentication check
user = sb.current_user()
role = sb.current_role() if user else None

if not user:
    st.warning("Please sign in from the home page first.")
    st.page_link("app.py", label="← Back to home")
    st.stop()

if role != "hr":
    st.error("🚫 HR role required to access survey management.")
    st.stop()

st.title("📝 Survey Management Studio")
st.caption("Create, edit, and manage custom survey questions for employees")

client = sb.get_client()

# Initialize session state
if 'editing_template' not in st.session_state:
    st.session_state.editing_template = None
if 'editing_question' not in st.session_state:
    st.session_state.editing_question = None
if 'editing_question_data' not in st.session_state:
    st.session_state.editing_question_data = None
if 'delete_confirm' not in st.session_state:
    st.session_state.delete_confirm = None

@st.cache_data(ttl=10)
def load_templates():
    try:
        result = client.table("survey_templates").select("*").execute()
        return result.data if result.data else []
    except Exception as e:
        st.error(f"Error loading templates: {e}")
        return []

@st.cache_data(ttl=10)
def load_questions(template_id):
    try:
        result = client.table("survey_questions").select("*").eq("template_id", template_id).order("display_order").execute()
        return result.data if result.data else []
    except Exception as e:
        st.error(f"Error loading questions: {e}")
        return []

@st.cache_data(ttl=30)
def load_employee_names():
    """Load employee names for better display"""
    try:
        profiles = client.table("profiles").select("user_id, full_name, department").execute().data or []
        return {p['user_id']: p for p in profiles}
    except Exception as e:
        return {}

def save_template(name, description, is_active):
    try:
        if st.session_state.editing_template:
            client.table("survey_templates").update({
                "name": name,
                "description": description,
                "is_active": is_active,
                "updated_at": datetime.now().isoformat()
            }).eq("id", st.session_state.editing_template).execute()
            st.success("Template updated!")
        else:
            client.table("survey_templates").insert({
                "name": name,
                "description": description,
                "is_active": is_active,
                "created_by": user.id
            }).execute()
            st.success("Template created!")
        
        st.session_state.editing_template = None
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Error saving template: {e}")

def save_question(template_id, question_data):
    try:
        if st.session_state.editing_question:
            client.table("survey_questions").update(question_data).eq("id", st.session_state.editing_question).execute()
            st.success("Question updated!")
            st.session_state.editing_question = None
            st.session_state.editing_question_data = None
        else:
            question_data["template_id"] = template_id
            client.table("survey_questions").insert(question_data).execute()
            st.success("Question added!")
        
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Error saving question: {e}")

def delete_question(question_id):
    try:
        client.table("survey_questions").delete().eq("id", question_id).execute()
        st.success("Question deleted!")
        st.cache_data.clear()
        time.sleep(0.5)
        st.rerun()
    except Exception as e:
        st.error(f"Error deleting question: {e}")

def delete_template(template_id):
    try:
        # Delete associated questions first
        client.table("survey_questions").delete().eq("template_id", template_id).execute()
        # Delete template
        client.table("survey_templates").delete().eq("id", template_id).execute()
        st.success("Template deleted!")
        st.cache_data.clear()
        time.sleep(0.5)
        st.rerun()
    except Exception as e:
        st.error(f"Error deleting template: {e}")

def delete_response(response_id):
    """Delete a custom survey response"""
    try:
        client.table("custom_survey_responses").delete().eq("id", response_id).execute()
        st.success("Response deleted successfully!")
        st.cache_data.clear()
        time.sleep(0.5)
        st.rerun()
    except Exception as e:
        st.error(f"Error deleting response: {e}")

def edit_question(question):
    st.session_state.editing_question = question['id']
    st.session_state.editing_question_data = question
    st.rerun()

def cancel_edit():
    st.session_state.editing_question = None
    st.session_state.editing_question_data = None
    st.rerun()

# Main UI
st.sidebar.header("📋 Survey Templates")

# Create Template Section
with st.sidebar.expander("➕ Create/Edit Template", expanded=st.session_state.editing_template is not None):
    if st.session_state.editing_template:
        templates = load_templates()
        template_data = next((t for t in templates if t['id'] == st.session_state.editing_template), None)
        if template_data:
            template_name = st.text_input("Template Name", value=template_data['name'])
            template_desc = st.text_area("Description", value=template_data.get('description', ''))
            template_active = st.checkbox("Active", value=template_data.get('is_active', True))
        else:
            template_name = st.text_input("Template Name")
            template_desc = st.text_area("Description")
            template_active = st.checkbox("Active", value=True)
    else:
        template_name = st.text_input("Template Name")
        template_desc = st.text_area("Description")
        template_active = st.checkbox("Active", value=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save Template", use_container_width=True):
            if template_name:
                save_template(template_name, template_desc, template_active)
            else:
                st.error("Please enter a template name")
    with col2:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.editing_template = None
            st.rerun()

# List Templates
st.sidebar.divider()
st.sidebar.subheader("Existing Templates")

templates = load_templates()
if templates:
    for template in templates:
        col1, col2, col3 = st.sidebar.columns([2, 1, 1])
        with col1:
            status = "✅" if template.get('is_active') else "⭕"
            st.markdown(f"{status} **{template['name']}**")
        with col2:
            if st.button("✏️", key=f"edit_t_{template['id']}"):
                st.session_state.editing_template = template['id']
                st.rerun()
        with col3:
            if st.button("🗑️", key=f"delete_t_{template['id']}"):
                st.session_state.delete_confirm = ("template", template['id'], template['name'])
                st.rerun()
else:
    st.sidebar.info("No templates yet. Create one!")

# Handle delete confirmation
if st.session_state.delete_confirm:
    confirm_type, confirm_id, confirm_name = st.session_state.delete_confirm
    
    if confirm_type == "template":
        st.warning(f"⚠️ Are you sure you want to delete template '{confirm_name}'? This will also delete ALL questions in this template. This action cannot be undone!")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Yes, Delete Template", key="confirm_template"):
                delete_template(confirm_id)
                st.session_state.delete_confirm = None
        with col2:
            if st.button("❌ No, Cancel", key="cancel_template"):
                st.session_state.delete_confirm = None
                st.rerun()
    elif confirm_type == "response":
        st.warning(f"⚠️ Are you sure you want to delete this response from '{confirm_name}'? This action cannot be undone!")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Yes, Delete Response", key="confirm_response"):
                delete_response(confirm_id)
                st.session_state.delete_confirm = None
        with col2:
            if st.button("❌ No, Cancel", key="cancel_response"):
                st.session_state.delete_confirm = None
                st.rerun()

# Main area - Template Management
if templates:
    selected_template = st.selectbox(
        "Select Survey Template to Edit",
        options=[(t['id'], t['name']) for t in templates],
        format_func=lambda x: f"{x[1]} {'(Active)' if next(t for t in templates if t['id']==x[0]).get('is_active') else '(Inactive)'}"
    )
    
    if selected_template:
        template_id, template_name = selected_template
        questions = load_questions(template_id)
        employee_map = load_employee_names()
        
        st.divider()
        st.subheader(f"Managing: {template_name}")
        
        # Show edit form if editing a question
        if st.session_state.editing_question and st.session_state.editing_question_data:
            st.info(f"✏️ Editing Question: {st.session_state.editing_question_data.get('question_text', '')[:50]}...")
            
            with st.container(border=True):
                edit_q = st.session_state.editing_question_data
                
                q_text = st.text_input("Question Text", value=edit_q.get('question_text', ''))
                q_type = st.selectbox("Question Type", 
                                      ["slider", "rating", "text", "multiple_choice"],
                                      index=["slider", "rating", "text", "multiple_choice"].index(edit_q.get('question_type', 'slider')))
                q_category = st.text_input("Category", value=edit_q.get('category', 'custom'))
                is_required = st.checkbox("Required", value=edit_q.get('is_required', True))
                display_order = st.number_input("Display Order", value=edit_q.get('display_order', len(questions) + 1), min_value=1)
                
                min_val = edit_q.get('min_value', 0)
                max_val = edit_q.get('max_value', 10)
                step_val = edit_q.get('step_value', 1)
                options = edit_q.get('options', '[]')
                
                if q_type == "slider":
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        min_val = st.number_input("Min Value", value=min_val or 0)
                    with col2:
                        max_val = st.number_input("Max Value", value=max_val or 10)
                    with col3:
                        step_val = st.number_input("Step", value=step_val or 1)
                    options = None
                elif q_type == "rating":
                    col1, col2 = st.columns(2)
                    with col1:
                        min_val = st.number_input("Min Value", value=min_val or 1)
                    with col2:
                        max_val = st.number_input("Max Value", value=max_val or 5)
                    step_val = None
                    options = None
                elif q_type == "multiple_choice":
                    if options and isinstance(options, str):
                        try:
                            options_list = json.loads(options)
                        except:
                            options_list = []
                    else:
                        options_list = options or []
                    options_str = st.text_area("Options (one per line)", value="\n".join(options_list))
                    options = [opt.strip() for opt in options_str.split("\n") if opt.strip()]
                    min_val = max_val = step_val = None
                else:
                    min_val = max_val = step_val = None
                    options = None
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("💾 Save Changes", use_container_width=True):
                        if q_text:
                            question_payload = {
                                "question_text": q_text,
                                "question_type": q_type,
                                "category": q_category,
                                "is_required": is_required,
                                "display_order": display_order
                            }
                            if min_val is not None:
                                question_payload["min_value"] = min_val
                            if max_val is not None:
                                question_payload["max_value"] = max_val
                            if step_val is not None:
                                question_payload["step_value"] = step_val
                            if options:
                                question_payload["options"] = json.dumps(options)
                            
                            save_question(template_id, question_payload)
                        else:
                            st.error("Please enter a question text")
                with col2:
                    if st.button("❌ Cancel Edit", use_container_width=True):
                        cancel_edit()
        
        # Add New Question Form
        if not st.session_state.editing_question:
            with st.expander("➕ Add New Question", expanded=False):
                q_text = st.text_input("Question Text")
                q_type = st.selectbox("Question Type", ["slider", "rating", "text", "multiple_choice"])
                q_category = st.text_input("Category (optional)", value="custom")
                is_required = st.checkbox("Required", value=True)
                display_order = st.number_input("Display Order", value=len(questions) + 1, min_value=1)
                
                min_val = max_val = step_val = None
                options = None
                
                if q_type == "slider":
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        min_val = st.number_input("Min Value", value=0)
                    with col2:
                        max_val = st.number_input("Max Value", value=10)
                    with col3:
                        step_val = st.number_input("Step", value=1)
                elif q_type == "rating":
                    col1, col2 = st.columns(2)
                    with col1:
                        min_val = st.number_input("Min Value", value=1)
                    with col2:
                        max_val = st.number_input("Max Value", value=5)
                elif q_type == "multiple_choice":
                    options_str = st.text_area("Options (one per line)", value="Option 1\nOption 2\nOption 3")
                    options = [opt.strip() for opt in options_str.split("\n") if opt.strip()]
                
                if st.button("💾 Save Question", use_container_width=True):
                    if q_text:
                        question_payload = {
                            "question_text": q_text,
                            "question_type": q_type,
                            "category": q_category,
                            "is_required": is_required,
                            "display_order": display_order
                        }
                        if min_val is not None:
                            question_payload["min_value"] = min_val
                        if max_val is not None:
                            question_payload["max_value"] = max_val
                        if step_val is not None:
                            question_payload["step_value"] = step_val
                        if options:
                            question_payload["options"] = json.dumps(options)
                        
                        save_question(template_id, question_payload)
                    else:
                        st.error("Please enter a question text")
        
        # Display existing questions
        if questions:
            st.divider()
            st.subheader("Current Questions")
            st.caption("📝 Click ✏️ to edit a question | 🗑️ to delete")
            
            for q in questions:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([5, 1, 1])
                    with col1:
                        st.markdown(f"**{q['display_order']}. {q['question_text']}**")
                        st.caption(f"Type: {q['question_type']} | Required: {'Yes' if q.get('is_required') else 'No'} | Category: {q.get('category', 'custom')}")
                        if q.get('question_type') == 'slider':
                            st.caption(f"Range: {q.get('min_value', 0)} - {q.get('max_value', 10)} | Step: {q.get('step_value', 1)}")
                        elif q.get('question_type') == 'multiple_choice':
                            options = json.loads(q.get('options', '[]'))
                            if options:
                                st.caption(f"Options: {', '.join(options)}")
                    with col2:
                        if st.button("✏️ Edit", key=f"edit_{q['id']}"):
                            edit_question(q)
                    with col3:
                        if st.button("🗑️ Delete", key=f"delete_{q['id']}"):
                            delete_question(q['id'])
        else:
            st.info("No questions yet. Click 'Add New Question' to start.")
        
        # Preview Survey
        if questions and not st.session_state.editing_question:
            st.divider()
            st.subheader("👁️ Preview Survey")
            if st.button("Show Preview"):
                with st.expander("Survey Preview (How employees will see it)", expanded=True):
                    for q in sorted(questions, key=lambda x: x.get('display_order', 0)):
                        st.markdown(f"**{q['display_order']}. {q['question_text']}**")
                        if q['question_type'] == "slider":
                            st.slider("", min_value=q.get('min_value', 0), max_value=q.get('max_value', 10), 
                                     value=q.get('min_value', 0), disabled=True, label_visibility="collapsed")
                        elif q['question_type'] == "rating":
                            st.select_slider("", options=list(range(q.get('min_value', 1), q.get('max_value', 5) + 1)), 
                                           disabled=True, label_visibility="collapsed")
                        elif q['question_type'] == "text":
                            st.text_area("", disabled=True, label_visibility="collapsed", placeholder="Your answer here...")
                        elif q['question_type'] == "multiple_choice":
                            options = json.loads(q.get('options', '[]'))
                            if options:
                                st.radio("", options, disabled=True, label_visibility="collapsed")
                        st.divider()
        
        # Response Analytics
        st.divider()
        st.subheader("📊 Response Analytics")
        
        try:
            responses = client.table("custom_survey_responses").select("*").eq("template_id", template_id).order("submitted_at", desc=True).execute().data or []
            
            if responses:
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Responses", len(responses))
                col2.metric("Unique Employees", len(set(r['user_id'] for r in responses)))
                if len(set(r['user_id'] for r in responses)) > 0:
                    col3.metric("Response Rate", f"{len(responses)/len(set(r['user_id'] for r in responses))*100:.0f}%")
                else:
                    col3.metric("Response Rate", "0%")
                
                # Create a user-friendly display of responses
                with st.expander("📋 View All Responses", expanded=False):
                    for idx, resp in enumerate(responses):
                        employee = employee_map.get(resp['user_id'], {})
                        employee_name = employee.get('full_name', 'Unknown Employee')
                        employee_dept = employee.get('department', 'No Department')
                        submitted_date = resp.get('submitted_at', '')
                        if submitted_date:
                            submitted_date = submitted_date[:19].replace('T', ' ')
                        
                        with st.container(border=True):
                            col1, col2 = st.columns([5, 1])
                            with col1:
                                st.markdown(f"### {idx + 1}. {employee_name}")
                                st.caption(f"🏢 {employee_dept} | 📅 {submitted_date}")
                            with col2:
                                if st.button("🗑️ Delete", key=f"del_response_{resp['id']}"):
                                    st.session_state.delete_confirm = ("response", resp['id'], employee_name)
                                    st.rerun()
                            
                            # Parse responses
                            answers = resp.get('responses', {})
                            if isinstance(answers, str):
                                try:
                                    answers = json.loads(answers)
                                except:
                                    answers = {}
                            
                            # Create a clean table of answers
                            answer_data = []
                            for q in questions:
                                question_key = f"custom_{q['id']}"
                                answer = answers.get(question_key, 'Not answered')
                                
                                # Format answer nicely
                                if q['question_type'] == 'slider' and answer and answer != 'Not answered':
                                    formatted_answer = f"⭐ {answer}/{q.get('max_value', 10)}"
                                elif q['question_type'] == 'rating' and answer and answer != 'Not answered':
                                    formatted_answer = f"★ {answer}/{q.get('max_value', 5)}"
                                else:
                                    formatted_answer = answer if answer and answer != 'Not answered' else 'Not answered'
                                
                                answer_data.append({
                                    "Question": q['question_text'],
                                    "Answer": formatted_answer
                                })
                            
                            # Display as DataFrame
                            if answer_data:
                                answer_df = pd.DataFrame(answer_data)
                                st.dataframe(answer_df, use_container_width=True, hide_index=True)
                            
                            # Add a divider between responses
                            if idx < len(responses) - 1:
                                st.divider()
                
                # Summary Statistics
                with st.expander("📈 Response Summary Statistics", expanded=False):
                    st.markdown("#### Average Scores by Question")
                    
                    summary_data = []
                    for q in questions:
                        if q['question_type'] in ['slider', 'rating']:
                            scores = []
                            for resp in responses:
                                answers = resp.get('responses', {})
                                if isinstance(answers, str):
                                    try:
                                        answers = json.loads(answers)
                                    except:
                                        answers = {}
                                answer = answers.get(f"custom_{q['id']}")
                                if answer and isinstance(answer, (int, float)):
                                    scores.append(answer)
                            
                            if scores:
                                avg_score = sum(scores) / len(scores)
                                summary_data.append({
                                    "Question": q['question_text'],
                                    "Average Score": f"{avg_score:.1f} / {q.get('max_value', 10)}",
                                    "Responses": len(scores)
                                })
                    
                    if summary_data:
                        summary_df = pd.DataFrame(summary_data)
                        st.dataframe(summary_df, use_container_width=True, hide_index=True)
                        
                        # Show distribution chart for first rating question
                        rating_questions = [q for q in questions if q['question_type'] in ['slider', 'rating']]
                        if rating_questions:
                            st.markdown("#### Response Distribution")
                            first_q = rating_questions[0]
                            scores = []
                            for resp in responses:
                                answers = resp.get('responses', {})
                                if isinstance(answers, str):
                                    try:
                                        answers = json.loads(answers)
                                    except:
                                        answers = {}
                                answer = answers.get(f"custom_{first_q['id']}")
                                if answer and isinstance(answer, (int, float)):
                                    scores.append(answer)
                            
                            if scores:
                                fig = px.histogram(x=scores, 
                                                  nbins=first_q.get('max_value', 10) - first_q.get('min_value', 0) + 1,
                                                  title=f"Distribution: {first_q['question_text'][:50]}",
                                                  labels={'x': 'Score', 'y': 'Count'})
                                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No responses yet for this survey. Responses will appear here once employees submit.")
        except Exception as e:
            st.info(f"Response analytics will appear once employees submit surveys.")

else:
    st.info("🎉 Welcome to Survey Manager! Create your first survey template using the sidebar.")
    st.markdown("""
    ### How to get started:
    1. Click **'Create/Edit Template'** in the sidebar
    2. Give your survey a name (e.g., "Q1 Engagement Survey")
    3. Add questions using the form
    4. Set the template to **Active** when ready
    5. Employees will see the questions on their check-in page
    
    ### Features:
    - ✏️ **Edit any question** by clicking the Edit button
    - 🗑️ **Delete questions** you don't need
    - 📝 **Preview** how employees will see the survey
    - 📊 **View responses** with employee names and formatted answers
    - 📈 **Summary statistics** with average scores and distributions
    - 🗑️ **Delete individual responses** from the response list
    """)

st.divider()
st.caption("💡 Tip: Only one template can be active at a time. Set a template to 'Active' for employees to see it.")