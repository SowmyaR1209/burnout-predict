"""BurnoutPredict — Streamlit entrypoint with improved UI + Forgot Password."""

from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go

from burnoutpredict import supabase_client as sb
from burnoutpredict.config import assert_configured

st.set_page_config(
    page_title="BurnoutPredict — AI-powered workplace wellness",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===== Custom CSS =====
st.markdown(
    """
    <style>
      :root {
        --primary: #1B8E8B;
        --primary-glow: #2dd4bf;
        --primary-soft: #E0F2F1;
        --bg-gradient: linear-gradient(135deg, #fdfdfd, #f4fbfa);
        --card-bg: rgba(255, 255, 255, 0.75);
        --border: rgba(0,0,0,0.08);
      }
      html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
      .stApp { background: var(--bg-gradient); background-size: 200% 200%; }
      .hero-title { font-size: 3.4rem; font-weight: 900; line-height: 1.1; }
      .hero-accent { background: linear-gradient(90deg, #1B8E8B, #2dd4bf);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
      .pill { display:inline-block; padding:6px 14px; border-radius:999px;
        background: rgba(27,142,139,0.1); color: var(--primary); font-size:0.85rem;
        font-weight:600; border: 1px solid rgba(27,142,139,0.2); }
      .feature-card { padding:1.6rem; border-radius:20px; background: var(--card-bg);
        backdrop-filter: blur(14px); border: 1px solid var(--border); transition: all 0.3s ease; }
      .feature-card:hover { transform: translateY(-8px) scale(1.02);
        box-shadow: 0 18px 40px rgba(0,0,0,0.1); }
      section[data-testid="stSidebar"] { background: linear-gradient(180deg, #ffffff, #f7fdfd); }
      .stButton>button { border-radius: 12px; font-weight: 600; border: none;
        background: linear-gradient(135deg, #1B8E8B, #2dd4bf); color: white; }
      .stButton>button:hover { transform: scale(1.03); box-shadow: 0 6px 18px rgba(27,142,139,0.3); }
      .stTextInput input { border-radius: 10px; border: 1px solid rgba(0,0,0,0.1); }
      footer { text-align:center; font-size:0.85rem; color:#6b7280; padding:1rem 0;
        border-top: 1px solid rgba(0,0,0,0.05); }
      /* Delete account button styling */
      .stButton button[kind="danger"] {
        background: linear-gradient(135deg, #dc2626, #ef4444);
      }
      .stButton button[kind="danger"]:hover {
        transform: scale(1.03);
        box-shadow: 0 6px 18px rgba(220,38,38,0.3);
      }
    </style>
    """,
    unsafe_allow_html=True,
)

assert_configured()

# Initialize session state for delete confirmation if not exists
if "show_delete_confirm" not in st.session_state:
    st.session_state.show_delete_confirm = False

# ---- Sidebar: auth + nav ----------------------------------------------------
user = sb.current_user()
role = sb.current_role() if user else None
profile = sb.current_profile() if user else None

with st.sidebar:
    st.markdown("### 🧠 BurnoutPredict")
    st.caption("AI-powered workplace wellness")
    st.divider()

    if user:
        st.markdown(f"**{(profile or {}).get('full_name', user.email)}**")
        st.caption(f"Role: `{role}` · {user.email}")
        
        # Delete Account Button with confirmation flow
        st.divider()
        if st.button("⚠️ Delete Account", use_container_width=True, type="secondary"):
            st.session_state.show_delete_confirm = True
            st.rerun()
        
        # Show confirmation dialog if flag is True
        if st.session_state.show_delete_confirm:
            st.markdown("---")
            st.error("### ⚠️ Permanent Account Deletion")
            st.warning("This action is **irreversible**. All your data will be lost forever.")
            st.caption(f"Account to delete: **{user.email}**")
            
            # Double confirmation inputs
            confirm_email = st.text_input("Confirm your email to delete account:", key="delete_confirm_email", placeholder="Enter your email")
            confirm_text = st.text_input("Type 'DELETE' to confirm:", key="delete_confirm_text", placeholder="DELETE", type="password")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state.show_delete_confirm = False
                    st.rerun()
            with col2:
                if st.button("🗑️ Yes, Permanently Delete My Account", use_container_width=True, type="primary"):
                    # Validate inputs
                    if confirm_email != user.email:
                        st.error("❌ Email confirmation does not match your account email.")
                    elif confirm_text != "DELETE":
                        st.error("❌ Please type 'DELETE' exactly to confirm account deletion.")
                    else:
                        # Attempt to delete account
                        with st.spinner("Deleting your account..."):
                            ok, msg = sb.delete_account()
                            if ok:
                                st.success("✅ Account deleted successfully. We're sorry to see you go!")
                                st.session_state.clear()
                                st.rerun()
                            else:
                                st.error(f"❌ Failed to delete account: {msg}")
                                st.session_state.show_delete_confirm = False
                                st.rerun()
        
        if st.button("Sign out", use_container_width=True):
            sb.sign_out()
            st.session_state.show_delete_confirm = False
            st.rerun()
            
        st.divider()
        st.markdown("**Navigation**")
        st.page_link("Home.py", label="🏠 Home")
        if role == "employee":
            st.page_link("pages/_Check_in.py", label="📋 Take a check-in")
            st.page_link("pages/_My_Dashboard.py", label="📊 My dashboard")
        if role == "hr":
            st.page_link("pages/_HR_Dashboard.py", label="🏢 HR dashboard")
    else:
        tab_in, tab_up = st.tabs(["Sign in", "Sign up"])
        with tab_in:
            email = st.text_input("Email", key="si_email")
            pw = st.text_input("Password", type="password", key="si_pw")
            if st.button("Sign in", use_container_width=True):
                ok, msg = sb.sign_in(email, pw)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

        with tab_up:
            full_name = st.text_input("Full name")
            email = st.text_input("Email", key="su_email")
            pw = st.text_input("Password (≥6 chars)", type="password", key="su_pw")
            role_sel = st.radio("I am a…", ["employee", "hr"], horizontal=True)
            dept = st.text_input("Department (optional)")
            title = st.text_input("Job title (optional)")
            if st.button("Create account", use_container_width=True):
                ok, msg = sb.sign_up(email, pw, full_name, role_sel, dept, title)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

# ---- Hero -------------------------------------------------------------------
col_left, col_right = st.columns([1.1, 1])

with col_left:
    st.markdown('<span class="pill">✨ AI-Powered Workplace Wellness</span>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-title">Detect employee burnout '
        '<span class="hero-accent">before</span> it costs you.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "BurnoutPredict combines MBI-aligned surveys with workload signals to give HR "
        "a transparent, explainable risk score for every employee — and personalized "
        "wellness actions."
    )
    st.write("")


with col_right:
    fig = go.Figure(data=[go.Bar(
        x=[68, 41, 52, 24],
        y=["Engineering", "Design", "Sales", "Operations"],
        orientation="h",
        marker_color=["#ef4444", "#f59e0b", "#f59cd0", "#22c55e"],
        text=[68, 41, 52, 24],
        textposition="outside",
    )])
    fig.update_layout(
        title="Org burnout index (preview)",
        xaxis=dict(range=[0, 100], title="Score"),
        height=300,
        margin=dict(l=20, r=20, t=50, b=20),
        plot_bgcolor="rgba(250,250,250,0.9)",
        paper_bgcolor="rgba(255,255,255,0.6)",
        font=dict(family="Inter", size=12),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---- How it works -----------------------------------------------------------
st.markdown("### How BurnoutPredict works")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(
        '<div class="feature-card"><h4>👥 Collect</h4>'
        "<p>Employees complete a 7-question MBI-aligned survey in under 2 minutes.</p></div>",
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        '<div class="feature-card"><h4>📈 Score</h4>'
        "<p>A transparent weighted model produces a 0–100 burnout score with risk tier, "
        "while XGBoost predicts attrition probability.</p></div>",
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        '<div class="feature-card"><h4>🚀 Act</h4>'
        "<p>HR sees department heatmaps and high-urgency qualitative signals; employees "
        "get personalized wellness tips.</p></div>",
        unsafe_allow_html=True,
    )

st.divider()

# ---- Footer -----------------------------------------------------------------
st.markdown(
    """
    <footer>
      BurnoutPredict © 2026 · AI-powered workplace wellness platform
    </footer>
    """,
    unsafe_allow_html=True,
)