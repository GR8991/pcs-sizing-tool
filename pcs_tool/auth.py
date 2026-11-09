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
from urllib.parse import quote

import streamlit as st

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300

def _bess_background_svg() -> str:
    """Original illustration of a utility-connected BESS site (sky, transmission line, substation/GSU,
    MV skids and battery containers) used as the sign-in page background. Animated dashes show power flow."""
    W, G = 1600, 760  # canvas width, ground line
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 900" preserveAspectRatio="xMidYMax slice">',
         '<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
         '<stop offset="0" stop-color="#081427"/><stop offset=".55" stop-color="#14284B"/><stop offset="1" stop-color="#2E5597"/></linearGradient>'
         '<linearGradient id="glow" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F4B183" stop-opacity=".0"/>'
         '<stop offset="1" stop-color="#F4B183" stop-opacity=".18"/></linearGradient></defs>',
         f'<rect width="{W}" height="900" fill="url(#sky)"/>',
         f'<rect y="560" width="{W}" height="200" fill="url(#glow)"/>']
    # faint stars
    for i in range(70):
        x, y, r = (i * 233) % W, (i * 97) % 470 + 10, 0.6 + (i % 3) * 0.45
        p.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#CFE0FF" opacity="{0.15 + (i % 5) * 0.08:.2f}"/>')
    # distant hills
    p.append(f'<path d="M0 690 Q 200 610 420 670 T 860 655 T 1260 640 T {W} 660 L {W} {G} L 0 {G} Z" fill="#10213F" opacity=".9"/>')

    def pylon(x, h, s=1.0):
        b, t = G, G - h
        w0, w1 = 30 * s, 7 * s
        q = [f'<g stroke="#9DB6E0" stroke-width="{1.8 * s:.1f}" fill="none" opacity=".75">',
             f'<path d="M{x - w0} {b} L{x - w1} {t} M{x + w0} {b} L{x + w1} {t}"/>']
        n = 7
        for k in range(n):
            ya, yb = b - h * k / n, b - h * (k + 1) / n
            xa, xb = w0 - (w0 - w1) * k / n, w0 - (w0 - w1) * (k + 1) / n
            q.append(f'<path d="M{x - xa:.1f} {ya:.1f} L{x + xb:.1f} {yb:.1f} M{x + xa:.1f} {ya:.1f} L{x - xb:.1f} {yb:.1f}"/>')
        for fr, aw in ((0.78, 62), (0.93, 46)):
            ya = b - h * fr
            q.append(f'<path d="M{x - aw * s:.1f} {ya:.1f} L{x + aw * s:.1f} {ya:.1f} L{x} {ya - 14 * s:.1f} Z"/>')
        q.append("</g>")
        return "".join(q), [(x - 62 * s, b - h * 0.78), (x + 62 * s, b - h * 0.78), (x - 46 * s, b - h * 0.93), (x + 46 * s, b - h * 0.93)]

    towers = [(110, 300, 1.05), (400, 250, 0.9), (640, 205, 0.75)]
    tips = []
    for x, h, sc in towers:
        g, t = pylon(x, h, sc)
        p.append(g)
        tips.append(t)
    # conductors (catenaries) between towers, plus animated power-flow dashes toward the grid (left)
    for a, b in zip(tips, tips[1:]):
        for (x1, y1), (x2, y2) in ((a[1], b[0]), (a[3], b[2])):
            mx, my = (x1 + x2) / 2, max(y1, y2) + 34
            d = f"M{x1:.1f} {y1:.1f} Q{mx:.1f} {my:.1f} {x2:.1f} {y2:.1f}"
            p.append(f'<path d="{d}" stroke="#9DB6E0" stroke-width="1.3" fill="none" opacity=".6"/>')
            p.append(f'<path d="{d}" stroke="#F4B183" stroke-width="2" fill="none" stroke-dasharray="4 26" opacity=".85">'
                     '<animate attributeName="stroke-dashoffset" from="0" to="60" dur="2.4s" repeatCount="indefinite"/></path>')
    # substation gantry + GSU transformer
    p.append('<g stroke="#9DB6E0" stroke-width="2" fill="none" opacity=".8">'
             f'<path d="M700 {G} V580 M800 {G} V580 M690 590 H810 M700 600 L800 640 M800 600 L700 640"/></g>')
    lt = tips[-1]
    p.append(f'<path d="M{lt[1][0]:.1f} {lt[1][1]:.1f} Q 690 600 700 592" stroke="#9DB6E0" stroke-width="1.3" fill="none" opacity=".6"/>')
    p.append(f'<rect x="725" y="660" width="120" height="100" rx="4" fill="#24467F" stroke="#9DB6E0" stroke-width="1.5"/>')
    for i in range(8):
        p.append(f'<rect x="{850 + i * 7}" y="672" width="4" height="80" fill="#2F5A9E" stroke="#9DB6E0" stroke-width=".6"/>')
    for i in range(3):
        bx = 745 + i * 35
        p.append(f'<rect x="{bx}" y="628" width="10" height="32" fill="#C9D6EC"/><circle cx="{bx + 5}" cy="626" r="5" fill="#C9D6EC"/>')
    p.append('<text x="785" y="718" font-family="Arial" font-size="15" font-weight="700" fill="#DCE6F5" text-anchor="middle">GSU</text>')
    # MV cable trench with power-flow dashes (containers -> substation)
    p.append(f'<path d="M915 {G - 6} H1560" stroke="#3E66A8" stroke-width="3"/>'
             f'<path d="M1560 {G - 6} H915" stroke="#F4B183" stroke-width="3" stroke-dasharray="6 22">'
             '<animate attributeName="stroke-dashoffset" from="0" to="56" dur="1.6s" repeatCount="indefinite"/></path>')
    # BESS containers with PCS/MVT skids
    x = 935
    for i in range(6):
        if i in (2, 4):  # PCS + MV transformer skid
            p.append(f'<rect x="{x}" y="706" width="54" height="48" rx="3" fill="#2B4E8A" stroke="#9DB6E0" stroke-width="1.2"/>'
                     f'<text x="{x + 27}" y="736" font-family="Arial" font-size="16" fill="#F4B183" text-anchor="middle">~/=</text>')
            x += 66
        p.append(f'<rect x="{x}" y="676" width="92" height="78" rx="3" fill="#D9E3F1" stroke="#9DB6E0" stroke-width="1.2"/>'
                 f'<rect x="{x + 18}" y="668" width="26" height="8" fill="#AFC2DE"/>'
                 f'<path d="M{x + 31} 684 V748 M{x + 61} 684 V748" stroke="#9FB2CF" stroke-width="1.4"/>'
                 f'<circle cx="{x + 82}" cy="688" r="3.2" fill="#3FBF6F"><animate attributeName="opacity" values="1;.35;1" '
                 f'dur="{2 + i * 0.3:.1f}s" repeatCount="indefinite"/></circle>')
        x += 104
    # ground and fence
    p.append(f'<rect y="{G}" width="{W}" height="140" fill="#081427"/>'
             f'<path d="M0 {G} H{W}" stroke="#3E66A8" stroke-width="2" opacity=".7"/>')
    for fx in range(890, 1600, 26):
        p.append(f'<path d="M{fx} {G} V{G - 22}" stroke="#3E66A8" stroke-width="1.2" opacity=".55"/>')
    p.append(f'<path d="M890 {G - 20} H1600" stroke="#3E66A8" stroke-width="1" opacity=".55"/>')
    p.append("</svg>")
    return "".join(p)


def _login_css() -> str:
    bg = "data:image/svg+xml;charset=utf-8," + quote(_bess_background_svg())
    return f"""
<style>
[data-testid="stSidebar"], [data-testid="collapsedControl"] {{display: none;}}
[data-testid="stAppViewContainer"], .stApp {{
    background: linear-gradient(90deg, rgba(8,20,39,.55) 0%, rgba(8,20,39,.15) 60%, rgba(8,20,39,.05) 100%),
                url("{bg}") center bottom / cover no-repeat fixed, #081427;}}
[data-testid="stHeader"] {{background: transparent;}}
[data-testid="stToolbar"] * {{color: #DCE6F5 !important;}}
.block-container {{padding-top: 4.5rem; max-width: 1100px;}}
.pcs-hero {{background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.18); color:#fff; border-radius:16px;
           padding:2.4rem 2.2rem; min-height:420px; box-shadow:0 10px 30px rgba(0,0,0,.30);
           backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);}}
.pcs-hero h1 {{color:#fff; font-size:2.0rem; margin:0 0 .4rem 0; line-height:1.2;}}
.pcs-hero p {{color:#DCE6F5; font-size:1.0rem; margin:.2rem 0 1.2rem 0;}}
.pcs-hero ul {{padding-left:1.1rem; color:#EEF3FB; line-height:1.9;}}
.pcs-flow {{margin-top:1.4rem; font-size:.85rem; color:#F4B183; letter-spacing:.04em;}}
.pcs-card-title {{font-size:1.6rem; font-weight:700; color:#FFFFFF; margin-bottom:.2rem; text-shadow:0 1px 6px rgba(0,0,0,.35);}}
.pcs-card-sub {{color:#DCE6F5; font-size:.95rem; margin-bottom:1.0rem;}}
[data-testid="stForm"] {{background:#FFFFFF; border:none !important; border-radius:14px; padding:1.4rem 1.4rem 1.2rem;
                         box-shadow:0 14px 40px rgba(0,0,0,.35);}}
[data-testid="stFormSubmitButton"] button {{background:#1F3864 !important; border:1px solid #1F3864 !important; color:#fff !important;
                                            font-weight:600; border-radius:8px;}}
[data-testid="stFormSubmitButton"] button:hover {{background:#2E5597 !important; border-color:#2E5597 !important;}}
.pcs-foot {{color:#C9D6EC; font-size:.8rem; margin-top:1.2rem;}}
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
    st.markdown(_login_css(), unsafe_allow_html=True)
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
