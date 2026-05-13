"""Environment configuration loaded from .env or Streamlit secrets."""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

try:
    import streamlit as st  # type: ignore

    _SECRETS = dict(st.secrets) if hasattr(st, "secrets") and len(st.secrets) else {}
except Exception:
    _SECRETS = {}


def _get(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key) or _SECRETS.get(key) or default


SUPABASE_URL: str | None = _get("SUPABASE_URL")
SUPABASE_ANON_KEY: str | None = _get("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY: str | None = _get("SUPABASE_SERVICE_ROLE_KEY")


def assert_configured() -> None:
    missing = [k for k, v in {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_ANON_KEY": SUPABASE_ANON_KEY,
    }.items() if not v]
    if missing:
        import streamlit as st
        st.error(
            "❌ Missing environment variables: "
            + ", ".join(missing)
            + ". Copy `.env.example` → `.env` and fill in your Supabase credentials."
        )
        st.stop()
