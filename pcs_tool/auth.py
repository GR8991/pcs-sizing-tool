"""E-mail allow-list sign-in for the Streamlit app.

Allowed users are configured in Streamlit secrets (never in the repository):

    [auth]
    allowed_emails  = ["first.user@company.com", "second.user@company.com"]
    allowed_domains = []          # optional, e.g. ["company.com"] admits every address on that domain
    access_code     = ""          # optional shared access code; when set, users must also enter it

Note: an e-mail allow-list alone does not prove identity (anyone who knows an allowed
address can type it). Set ``access_code`` for a second factor, or switch to Streamlit's
built-in OIDC login (st.login) for verified Google/Microsoft accounts.
"""
from __future__ import annotations

import hmac
import re
import time

import streamlit as st

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300

_LOGIN_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="collapsedControl"] {display: none;}
.block-container {padding-top: 4rem; max-width: 1100px;}
.pcs-hero {background: linear-gradient(135deg,#1F3864 0%,#2E5597 100%); color:#fff; border-radius:16px;
           padding:2.4rem 2.2rem; min-height:420px; box-shadow:0 10px 30px rgba(31,56,100,.25);}
.pcs-hero h1 {color:#fff; font-size:2.0rem; margin:0 0 .4rem 0; line-height:1.2;}
.pcs-hero p {color:#DCE6F5; font-size:1.0rem; margin:.2rem 0 1.2rem 0;}
.pcs-hero ul {padding-left:1.1rem; color:#EEF3FB; line-height:1.9;}
.pcs-flow {margin-top:1.4rem; font-size:.85rem; color:#BFD0EA; letter-spacing:.02em;}
.pcs-card-title {font-size:1.45rem; font-weight:700; color:#1F3864; margin-bottom:.2rem;}
.pcs-card-sub {color:#5b6577; font-size:.95rem; margin-bottom:1.2rem;}
.pcs-foot {color:#7a8496; font-size:.8rem; margin-top:1.2rem;}
</style>
"""


def _auth_config() -> tuple[set[str], set[str], str]:
    try:
        cfg = st.secrets.get("auth", {})
    except Exception:  # secrets file missing
        cfg = {}
    emails = {str(e).strip().lower() for e in cfg.get("allowed_emails", []) if str(e).strip()}
    domains = {str(d).strip().lower().lstrip("@") for d in cfg.get("allowed_domains", []) if str(d).strip()}
    code = str(cfg.get("access_code", "") or "")
    return emails, domains, code


def _is_allowed(email: str, emails: set[str], domains: set[str]) -> bool:
    email = email.strip().lower()
    return email in emails or (email.split("@")[-1] in domains if "@" in email else False)


def is_authenticated() -> bool:
    return bool(st.session_state.get("auth_email"))


def sign_out() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


def login_page() -> None:
    """Render the sign-in page. Calls st.stop() until the user is signed in."""
    if is_authenticated():
        return
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    emails, domains, code = _auth_config()
    left, gap, right = st.columns([1.15, 0.12, 1])
    with left:
        st.markdown(
            """
            <div class="pcs-hero">
              <h1>BESS PCS Sizing Tool</h1>
              <p>Preliminary PCS sizing and electrical suitability screening</p>
              <ul>
                <li>Four-quadrant P / Q balance: DiS-OE, DiS-UE, Cha-OE, Cha-UE</li>
                <li>GSU, MV collector and MV transformer losses and reactive demand</li>
                <li>PCS count, derating and simultaneous P-Q capability</li>
                <li>Reactive compensation and voltage screening</li>
                <li>Simplified power-flow view and Excel export</li>
              </ul>
              <div class="pcs-flow">GRID / POI ⇄ GSU ⇄ MV BUS ⇄ MV TRANSFORMERS ⇄ PCS ⇄ BATTERY</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown('<div class="pcs-card-title">Sign in</div>'
                    '<div class="pcs-card-sub">Use your authorised work e-mail address.</div>', unsafe_allow_html=True)
        if not emails and not domains:
            st.error("Access is not configured. An administrator must add `allowed_emails` under `[auth]` in the app secrets.")
            st.stop()
        locked_until = st.session_state.get("auth_locked_until", 0)
        if time.time() < locked_until:
            st.error(f"Too many failed attempts. Try again in {int(locked_until - time.time()) + 1} s.")
            st.stop()
        with st.form("login", clear_on_submit=False, border=True):
            email = st.text_input("Work e-mail", placeholder="name@company.com", autocomplete="email")
            entered_code = st.text_input("Access code", type="password") if code else ""
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            email_n = email.strip().lower()
            if not EMAIL_RE.match(email_n):
                st.warning("Enter a valid e-mail address.")
            elif _is_allowed(email_n, emails, domains) and (not code or hmac.compare_digest(entered_code, code)):
                st.session_state["auth_email"] = email_n
                st.session_state["auth_time"] = time.strftime("%Y-%m-%d %H:%M")
                st.session_state.pop("auth_attempts", None)
                st.rerun()
            else:
                n = st.session_state.get("auth_attempts", 0) + 1
                st.session_state["auth_attempts"] = n
                if n >= MAX_ATTEMPTS:
                    st.session_state["auth_locked_until"] = time.time() + LOCKOUT_SECONDS
                    st.session_state["auth_attempts"] = 0
                st.error("Access denied. This e-mail is not authorised" + (" or the access code is wrong." if code else "."))
        st.markdown('<div class="pcs-foot">Access is limited to approved users. Contact the tool owner to request access.<br>'
                    'Preliminary screening tool - not design approval.</div>', unsafe_allow_html=True)
    st.stop()
