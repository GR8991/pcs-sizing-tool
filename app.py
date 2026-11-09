"""BESS PCS Sizing Tool - Streamlit web app.

Port of the frozen Excel workbook PCS_Sizing_Tool_FINAL_FROZEN.xlsx.
Run locally:  streamlit run app.py
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from pcs_tool import auth
from pcs_tool.diagram import power_flow_svg
from pcs_tool.export import (APP_VERSION, checks_df, detailed_df, from_json, input_checks_df, power_flow_df, summary_df,
                             to_excel, to_json)
from pcs_tool.model import (CASES, DERATING_ROWS, INPUTS, Result, calculate, default_derating, default_inputs)

st.set_page_config(page_title="BESS PCS Sizing Tool", page_icon="⚡", layout="wide")

# ----------------------------------------------------------------------------------------- auth
auth.login_page()  # stops here until the user is signed in

# ----------------------------------------------------------------------------------------- style
st.markdown(
    """
    <style>
    /* ---- sticky professional header ---- */
    .block-container {padding-top: 4rem;}
    [data-testid="stElementContainer"]:has(.pcs-header), div.element-container:has(.pcs-header)
        {position: sticky; top: 3.75rem; z-index: 990;}
    .pcs-header {height: 72px; box-sizing: border-box; display: flex; align-items: center; justify-content: space-between;
        gap: 1rem; padding: 0 1.25rem; background: linear-gradient(90deg, #14284B 0%, #1F3864 55%, #2E5597 100%);
        border-bottom: 3px solid #C55A11; border-radius: 6px; box-shadow: 0 4px 14px rgba(20, 40, 75, .22); overflow: hidden;}
    .pcs-brand {display: flex; align-items: center; gap: .85rem; min-width: 0;}
    .pcs-logo {flex: 0 0 auto; width: 42px; height: 42px; border-radius: 8px; background: rgba(255,255,255,.12);
        display: flex; align-items: center; justify-content: center;}
    .pcs-title {color: #fff; font-size: 1.35rem; font-weight: 700; letter-spacing: .01em; line-height: 1.15; white-space: nowrap;}
    .pcs-sub {color: #C9D6EC; font-size: .8rem; letter-spacing: .03em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
    .pcs-meta {display: flex; align-items: center; gap: 1.4rem; min-width: 0;}
    .pcs-meta .item {display: flex; flex-direction: column; align-items: flex-start; min-width: 0;}
    .pcs-meta .lbl {color: #9FB3D6; font-size: .66rem; text-transform: uppercase; letter-spacing: .09em;}
    .pcs-meta .val {color: #fff; font-size: .85rem; font-weight: 600; max-width: 230px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
    @media (max-width: 1100px) {.pcs-meta .opt {display: none;} .pcs-sub {display: none;}}
    /* keep the tab bar visible under the header */
    .stTabs [data-baseweb="tab-list"] {position: sticky; top: calc(3.75rem + 72px); z-index: 980; background: #fff;
        padding-top: .35rem; box-shadow: 0 1px 0 #E3E8F0;}
    .pill {display:inline-block; padding:2px 10px; border-radius:12px; font-weight:700; font-size:.82rem; white-space:nowrap;}
    .ok {background:#C6EFCE; color:#006100;} .bad {background:#FFC7CE; color:#9C0006;} .warn {background:#FFEB9C; color:#9C5700;}
    .neutral {background:#E7ECF5; color:#1F3864;}
    table.sumtab {border-collapse:collapse; width:100%; font-size:.9rem;}
    table.sumtab th {background:#1F3864; color:#fff; text-align:left; padding:6px 8px;}
    table.sumtab td {border-bottom:1px solid #E3E8F0; padding:6px 8px; vertical-align:top;}
    table.sumtab tr.overall td {background:#EEF3FB; font-weight:700;}
    .banner {background:#FFF4E5; border-left:5px solid #C55A11; padding:.6rem .9rem; border-radius:6px; font-size:.9rem; margin-bottom:.6rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

GOOD = {"PASS", "OK", "SCREEN OK", "NOT REQUIRED", "SUITABLE", "PASS (screening)", "NONE"}
BAD = {"FAIL", "NOT SUITABLE", "REQUIRED", "INVALID INPUTS", "INVALID"}


def pill(v) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{v:,.2f}" if isinstance(v, float) else f"{v:,}"
    s = html.escape(str(v))
    if v in GOOD:
        cls = "ok"
    elif v in BAD:
        cls = "bad"
    elif v in ("-", None, ""):
        return "-"
    elif any(w in str(v) for w in ("NEEDS DATA", "INCOMPLETE", "LOAD-FLOW", "CAPACITOR", "REACTOR", "VENDOR", "BLANK", "CHECK")):
        cls = "warn"
    else:
        cls = "neutral"
    return f'<span class="pill {cls}">{s}</span>'


# ----------------------------------------------------------------------------------------- state
INT_KEYS = {"C27", "C28", "C44", "C49"}


def _typed(k, v):
    """Cast to the widget's numeric type (int for counts/flags, float otherwise); None stays blank."""
    if v is None:
        return None
    if k in INT_KEYS:
        return int(round(v)) if k != "C44" else (1 if int(round(v)) == 1 else 0)
    return float(v)


def _init_state(force: bool = False) -> None:
    if force or "initialised" not in st.session_state:
        for k, v in default_inputs().items():
            st.session_state[f"in_{k}"] = _typed(k, v)
        st.session_state["derating"] = default_derating()
        st.session_state["project"] = "Illustrative test data"
        st.session_state["initialised"] = True


def _reset() -> None:
    _init_state(force=True)
    st.session_state["flash"] = ("info", "Illustrative test data restored.")


def _load_json() -> None:
    up = st.session_state.get("upload")
    if up is None:
        st.session_state["flash"] = ("warning", "Choose a JSON input file first.")
        return
    try:
        inp, der, project = from_json(up.getvalue().decode("utf-8"))
    except Exception as exc:  # show the reason, keep current inputs
        st.session_state["flash"] = ("error", f"Could not load file: {exc}")
        return
    base = default_inputs()
    for k in base:
        st.session_state[f"in_{k}"] = _typed(k, inp[k] if k in inp else base[k])
    d = default_derating()
    for c in CASES:
        for k, _, _ in DERATING_ROWS:
            try:
                d[c][k] = float(der[c][k])
            except Exception:
                pass
    st.session_state["derating"] = d
    st.session_state["project"] = project or up.name
    st.session_state["flash"] = ("success", f"Loaded input set '{st.session_state['project']}'.")


_init_state()


def current_inputs() -> dict:
    return {d["key"]: st.session_state.get(f"in_{d['key']}") for d in INPUTS}


# ----------------------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown(f"**Signed in as**  \n{st.session_state['auth_email']}")
    if st.button("Sign out", use_container_width=True):
        auth.sign_out()
    st.divider()
    st.text_input("Project / input-set name", key="project")
    st.markdown("**Input sets**")
    st.file_uploader("Load input set (JSON)", type=["json"], key="upload", label_visibility="collapsed")
    st.button("Load selected file", on_click=_load_json, use_container_width=True)
    st.button("Reset to illustrative test data", on_click=_reset, use_container_width=True)

flash = st.session_state.pop("flash", None)
if flash:
    getattr(st, flash[0])(flash[1])

# ----------------------------------------------------------------------------------------- calculate
res: Result = calculate(current_inputs(), st.session_state["derating"])
summ = {s["key"]: s for s in res.summary}
overall = summ["overall"]["result"]

with st.sidebar:
    st.divider()
    st.markdown("**Export**")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in st.session_state["project"])[:60] or "pcs"
    st.download_button("Save input set (JSON)", to_json(current_inputs(), st.session_state["derating"], st.session_state["project"]),
                       file_name=f"{safe}_inputs.json", mime="application/json", use_container_width=True)
    try:
        xlsx = to_excel(res, st.session_state["auth_email"])
    except Exception as exc:  # e.g. openpyxl missing - keep the app running, report the cause
        xlsx = None
        st.caption(f"Excel export unavailable ({type(exc).__name__}: {exc}). Check that requirements.txt is in the repo root.")
    if xlsx is not None:
        st.download_button("Results workbook (Excel)", xlsx, file_name=f"{safe}_PCS_results.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    st.download_button("Results summary (CSV)", summary_df(res).to_csv(index=False), file_name=f"{safe}_summary.csv",
                       mime="text/csv", use_container_width=True)
    if res.rows:
        st.download_button("Detailed calculation (CSV)", detailed_df(res).to_csv(index=False), file_name=f"{safe}_detailed.csv",
                           mime="text/csv", use_container_width=True)
    st.caption(f"Version {APP_VERSION}")

# ----------------------------------------------------------------------------------------- header
_LOGO = ('<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" '
         'stroke-linejoin="round"><rect x="3" y="6" width="15" height="12" rx="2"/><path d="M18 10h2v4h-2"/>'
         '<path d="M11 8.5l-2.5 4h3l-2.5 4" stroke="#F4B183"/></svg>')
st.markdown(
    f'''<div class="pcs-header">
      <div class="pcs-brand"><div class="pcs-logo">{_LOGO}</div>
        <div><div class="pcs-title">PGR_BESS PCS Sizing Tool</div>
        <div class="pcs-sub">Preliminary PCS sizing &amp; electrical suitability screening</div></div></div>
      <div class="pcs-meta">
        <div class="item opt"><span class="lbl">Project</span><span class="val">{html.escape(st.session_state["project"] or "-")}</span></div>
        <div class="item"><span class="lbl">Overall result</span>{pill(overall)}</div>
        <div class="item opt"><span class="lbl">Signed in</span><span class="val">{html.escape(st.session_state["auth_email"])}</span></div>
      </div></div>'''.replace("\n", " "),
    unsafe_allow_html=True,
)
st.markdown('<div class="banner"><b>Preliminary screening only - not design approval.</b> '
            "Results need confirmation by an AC load-flow study, vendor-certified P-Q-V-T capability and the project single-line diagram."
            + (" <b>The illustrative test data set is loaded.</b>" if current_inputs() == default_inputs() else "") + "</div>",
            unsafe_allow_html=True)
m1, m2, m3, m4, m5 = st.columns(5)
m1.markdown(f"**Overall result**<br>{pill(overall)}", unsafe_allow_html=True)
fmt = lambda k, nd=2: (f"{summ[k]['result']:,.{nd}f}" if isinstance(summ[k]["result"], (int, float)) else "-")  # noqa: E731
m2.metric("PCS units (installed)", fmt("n_inst", 0))
m3.metric("PCS S required (MVA)", fmt("S_req"))
m4.metric("Q supply required (MVAr)", fmt("Q_sup"))
m5.metric("Q absorption required (MVAr)", fmt("Q_abs"))
if res.input_validity != "OK":
    bad = [f"{r['cell']} ({r['parameter']})" for r in res.globals["input_checks"] if r["status"] == "INVALID"]
    st.error("Invalid or missing essential inputs: " + "; ".join(bad) + ". All results are INCOMPLETE DATA until corrected.")

tab_in, tab_sum, tab_pf, tab_det, tab_chk, tab_help = st.tabs(
    ["Inputs", "Results Summary", "Power Flow", "Detailed calculation", "Input & design checks", "Guide"])

# ----------------------------------------------------------------------------------------- inputs
FORMATS = {"C19": "%.4f", "C16": "%.3f", "C13": "%.3f", "C14": "%.3f", "C46": "%.3f"}
INTS = {"C27", "C28", "C49"}
with tab_in:
    st.caption("Yellow fields in the workbook = these inputs. Vendor / SLD fields may be left blank - dependent checks then show NEEDS DATA. "
               "Cell references (C4, C14 …) match the Excel PCS sheet.")
    groups: dict[str, list] = {}
    for d in INPUTS:
        groups.setdefault(d["group"], []).append(d)
    for gname, items in groups.items():
        with st.expander(gname, expanded=gname not in ("Reference only",)):
            if gname == "Reference only":
                st.caption("Kept for traceability with the workbook. Not used by the calculation.")
            cols = st.columns(3)
            for i, d in enumerate(items):
                k, key = d["key"], f"in_{d['key']}"
                label = f"{d['label']} [{d['unit']}] · {k}"
                with cols[i % 3]:
                    if k == "C44":
                        st.selectbox(label, [1, 0], key=key, help=d.get("note"),
                                     format_func=lambda x: "1 - yes, rating already at design temperature" if x == 1 else "0 - no, apply temperature derating")
                    elif k in INTS:
                        st.number_input(label, key=key, step=1, format="%d", help=d.get("note"),
                                        placeholder="blank = NEEDS DATA" if d["kind"] == "opt" else None)
                    else:
                        st.number_input(label, key=key, step=None, format=FORMATS.get(k, "%.3f"), help=d.get("note"),
                                        placeholder="blank = NEEDS DATA" if d["kind"] == "opt" else None)
    with st.expander("PCS derating factors per case (J36:M39)", expanded=True):
        st.caption("Temperature factor is ignored when C44 = 1 (rating already at design temperature). Values must be 0 < k ≤ 1.")
        der = st.session_state["derating"]
        df = pd.DataFrame({c: [der[c][k] for k, _, _ in DERATING_ROWS] for c in CASES}, index=[lbl for _, lbl, _ in DERATING_ROWS])
        edited = st.data_editor(df, key="derate_editor", use_container_width=True,
                                column_config={c: st.column_config.NumberColumn(c, format="%.3f", step=0.001) for c in CASES})
        new = {c: {k: (None if pd.isna(edited.loc[lbl, c]) else float(edited.loc[lbl, c])) for k, lbl, _ in DERATING_ROWS} for c in CASES}
        if new != der:
            st.session_state["derating"] = new
            st.rerun()

# ----------------------------------------------------------------------------------------- summary
with tab_sum:
    rows_html = []
    for s in res.summary:
        val = s["value"]
        vtxt = "" if val is None else (f"{val:,.3f}" if isinstance(val, float) else str(val))
        cls = ' class="overall"' if s["key"] == "overall" else ""
        rows_html.append(f"<tr{cls}><td>{html.escape(s['label'])}</td><td>{pill(s['result'])}</td><td>{vtxt}</td>"
                         f"<td>{html.escape(s['unit'])}</td><td>{html.escape(s['basis'])}</td><td>{html.escape(s['note'])}</td></tr>")
    st.markdown('<table class="sumtab"><tr><th>Check / quantity</th><th>Result</th><th>Value</th><th>Unit</th><th>Basis (PCS cells)</th>'
                "<th>Notes</th></tr>" + "".join(rows_html) + "</table>", unsafe_allow_html=True)
    st.caption("PASS = satisfied with entered data · SCREEN OK = within limits at the evaluated point only · FAIL = limit exceeded · "
               "NEEDS DATA = vendor/SLD input blank, no result inferred · LOAD-FLOW STUDY REQUIRED = voltage cannot be confirmed by this tool. "
               "SUITABLE means the configuration passes this preliminary screen only.")

# ----------------------------------------------------------------------------------------- power flow
with tab_pf:
    if not res.rows:
        st.warning("Power flow cannot be calculated: " + (res.error or "invalid inputs"))
    else:
        case = st.radio("Operating case", CASES, horizontal=True, key="pf_case",
                        help="DiS = discharging, Cha = charging, OE = over-excited (supplies MVAr), UE = under-excited (absorbs MVAr)")
        components.html(power_flow_svg(res, case), height=1060, scrolling=True)
        st.subheader("All four cases")
        st.dataframe(power_flow_df(res), use_container_width=True, hide_index=True, height=640,
                     column_config={c: st.column_config.Column(c) for c in CASES})

# ----------------------------------------------------------------------------------------- detailed
with tab_det:
    if res.rows:
        st.caption("Rows reproduce the Excel PCS sheet (column 'Excel row'). Generator sign convention.")
        st.dataframe(detailed_df(res), use_container_width=True, hide_index=True, height=900)
    else:
        st.warning("No results - correct the invalid inputs first.")

# ----------------------------------------------------------------------------------------- checks
with tab_chk:
    st.subheader("Input checks")
    st.dataframe(input_checks_df(res), use_container_width=True, hide_index=True)
    if res.rows:
        st.subheader("Design checks per case (PCS rows 65-72)")
        st.dataframe(checks_df(res), use_container_width=True, hide_index=True)
        st.subheader("Input consistency (PCS rows 74-78)")
        st.dataframe(pd.DataFrame(res.globals["consistency"]), use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------------------- guide
with tab_help:
    st.markdown(
        """
### Purpose
Carries the POI requirement (P at power factor) back through the GSU, MV collector system and MV transformers to the PCS terminals for
all four operating cases, sizes the PCS fleet and screens reactive capability, compensation, transformer loading and voltage.

**Not calculated:** battery energy/degradation, DC interface, short-circuit and protection, harmonics/resonance, dynamics.

### Sign convention
Generator convention at every boundary: **P > 0** = discharging (export toward grid), **Q > 0** = over-excited (MVAr supplied toward grid),
**Q < 0** = under-excited (absorbed). Transformers, cables and auxiliaries always consume Q, so they add to the PCS requirement in OE cases
and offset it in UE cases.

| Case | P | Q |
|---|---|---|
| DiS-OE | + export | + supplied |
| DiS-UE | + export | − absorbed |
| Cha-OE | − import | + supplied |
| Cha-UE | − import | − absorbed |

Key relationships: S² = P² + Q², Q = P × tan(arccos PF). PCS Q capability must be checked at simultaneous P and Q with **vendor limits** -
the ideal MVA circle is shown for reference only and is never treated as vendor capability.

### Workflow
1. Enter project inputs (Inputs tab). Keep vendor/SLD fields blank until data exists.
2. Check the Results Summary. Any INVALID input → INCOMPLETE DATA. Any FAIL → NOT SUITABLE (add compensation in C11 or PCS units and re-check).
3. Review the Power Flow tab for each case.
4. Repeat with the POI voltage (C43) at the grid-code minimum and maximum.
5. Export the results workbook and save the input set (JSON).

### Main assumptions and limitations
- Sequential loss / voltage-drop calculation at one POI voltage with nominal taps and no grid impedance - **not a converged AC load flow**.
- C44 = 1 assumes the PCS rating already applies at the design temperature (no double derating) - confirm with vendor.
- Derating factors (altitude, AC and DC voltage) are user inputs; the DC-voltage factor is applied to MVA.
- MV transformer count is derived at C40 loading unless the SLD count (C49) is entered; loading check needs C49.
- C11 is a fixed shunt connected in all four cases (+ capacitor, − reactor).
- Cable reactance and MV cable charging are not modelled.
- Results reproduce the frozen Excel workbook; 20 workbook scenarios are included as automated regression tests.
"""
    )
