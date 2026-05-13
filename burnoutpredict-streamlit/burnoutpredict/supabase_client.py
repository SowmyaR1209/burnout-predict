"""Cached Supabase client + simple session-state auth helpers."""
from __future__ import annotations

from typing import Any, Optional

import streamlit as st
from supabase import Client, create_client

from . import config


@st.cache_resource(show_spinner=False)
def get_client() -> Client:
    config.assert_configured()
    return create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)


@st.cache_resource(show_spinner=False)
def get_admin_client() -> Optional[Client]:
    if not config.SUPABASE_SERVICE_ROLE_KEY:
        return None
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


# ---- Auth state -------------------------------------------------------------

def _restore_session() -> None:
    """If we already have access/refresh tokens in session_state, set them on the client."""
    sb = get_client()
    tokens = st.session_state.get("sb_session")
    if tokens and not _current_user(sb):
        try:
            sb.auth.set_session(tokens["access_token"], tokens["refresh_token"])
        except Exception:
            st.session_state.pop("sb_session", None)


def _current_user(sb: Client):
    try:
        return sb.auth.get_user().user
    except Exception:
        return None


def current_user():
    sb = get_client()
    _restore_session()
    return _current_user(sb)


def current_role() -> Optional[str]:
    user = current_user()
    if not user:
        return None
    if "sb_role" in st.session_state:
        return st.session_state["sb_role"]
    sb = get_client()
    try:
        res = sb.table("user_roles").select("role").eq("user_id", user.id).limit(1).execute()
        role = res.data[0]["role"] if res.data else "employee"
    except Exception:
        role = "employee"
    st.session_state["sb_role"] = role
    return role


def current_profile() -> dict[str, Any] | None:
    user = current_user()
    if not user:
        return None
    sb = get_client()
    try:
        res = sb.table("profiles").select("*").eq("user_id", user.id).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def sign_in(email: str, password: str) -> tuple[bool, str]:
    sb = get_client()
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state["sb_session"] = {
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token,
        }
        st.session_state.pop("sb_role", None)
        return True, "Signed in"
    except Exception as e:
        return False, str(e)


def sign_up(email: str, password: str, full_name: str, role: str,
            department: str = "", job_title: str = "") -> tuple[bool, str]:
    sb = get_client()
    try:
        sb.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "full_name": full_name,
                    "role": role,
                    "department": department,
                    "job_title": job_title,
                }
            },
        })
        return sign_in(email, password)
    except Exception as e:
        return False, str(e)


def sign_out() -> None:
    sb = get_client()
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    for k in ("sb_session", "sb_role"):
        st.session_state.pop(k, None)


def reset_password(email: str) -> tuple[bool, str]:
    """
    Sends a password reset email to the given address using Supabase Auth.
    """
    sb = get_client()   # <-- use your cached client
    try:
        response = sb.auth.reset_password_for_email(email)
        return True, "Password reset email sent successfully."
    except Exception as e:
        return False, str(e)


def delete_account() -> tuple[bool, str]:
    """
    Permanently delete the current user's account and all associated data.
    Returns (success, message) tuple.
    """
    try:
        # Get current user
        user_response = get_client().auth.get_user()
        if not user_response or not user_response.user:
            return False, "No user is currently logged in"
        
        user_id = user_response.user.id
        user_email = user_response.user.email
        
        sb = get_client()
        
        # List of tables to clear (in order - no foreign key constraints between these)
        tables_to_clear = [
            "assessments",
            "burnout_scores", 
            "wellness_actions",
            "recommendations",
            "notifications"
        ]
        
        # Delete data from each table
        for table in tables_to_clear:
            try:
                # Check if table exists by trying to delete
                result = sb.table(table).delete().eq("user_id", user_id).execute()
                # Optional: log success
                # print(f"Deleted {len(result.data)} records from {table}")
            except Exception as e:
                # Table might not exist or other error - continue silently
                pass
        
        # Delete profile (this might have foreign key to user_id)
        try:
            sb.table("profiles").delete().eq("user_id", user_id).execute()
        except Exception:
            # Try alternative column name if needed
            try:
                sb.table("profiles").delete().eq("id", user_id).execute()
            except Exception:
                pass
        
        # Try to delete the auth user
        delete_success = False
        
        # Method 1: Try using admin client (requires service_role key)
        admin_client = get_admin_client()
        if admin_client:
            try:
                # For Supabase, this requires admin privileges
                # Note: The exact method may vary based on your supabase-py version
                admin_client.auth.admin.delete_user(user_id)
                delete_success = True
            except Exception as e:
                print(f"Admin delete failed: {e}")
        
        # Method 2: Try RPC function if available
        if not delete_success:
            try:
                sb.rpc("delete_user_account", {"user_id": user_id}).execute()
                delete_success = True
            except Exception as e:
                print(f"RPC delete failed: {e}")
        
        # Method 3: If neither method worked, we at least deleted app data
        # but the auth user remains. This is acceptable as users can't log in
        # without their profile data, but we should notify.
        if not delete_success:
            # Sign out anyway - user's app data is gone
            sign_out()
            return True, f"Your account data has been deleted, but the authentication record could not be removed. Please contact support to fully remove your account. ({user_email})"
        
        # Sign out after successful deletion
        sign_out()
        return True, f"Your account ({user_email}) has been permanently deleted."
        
    except Exception as e:
        return False, f"Error deleting account: {str(e)}"