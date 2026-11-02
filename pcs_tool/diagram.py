"""SVG single-line style power-flow view for one operating case.

Simplified representation of the sequential calculation - NOT an AC load-flow solution.
"""
from __future__ import annotations

import html
import math

from .model import Result

NAVY, ORANGE, GREY, GREEN, RED, AMBER = "#1F3864", "#C55A11", "#595959", "#548235", "#C00000", "#9C5700"


def _f(x, nd=2, unit=""):
    if isinstance(x, (int, float)) and math.isfinite(x):
        return f"{x:,.{nd}f}{(' ' + unit) if unit else ''}"
    return html.escape(str(x))


def _arrow(x, y_top, y_bot, up: bool, color: str, label: str, dash=False):
    """Vertical arrow between y_top and y_bot pointing up (toward grid) or down."""
    y1, y2 = (y_bot, y_top) if up else (y_top, y_bot)
    d = ' stroke-dasharray="6 4"' if dash else ""
    lx = x + 8
    return (f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="{color}" stroke-width="3"{d} marker-end="url(#ah-{color[1:]})"/>'
            f'<text x="{lx}" y="{(y_top + y_bot) / 2 + 4}" font-size="12" fill="{color}" font-weight="600">{html.escape(label)}</text>')


def _panel(x, y, title, lines, w=300, status=None):
    h = 22 + 17 * len(lines)
    col = {"PASS": GREEN, "SCREEN OK": GREEN, "FAIL": RED}.get(status or "", AMBER if status else NAVY)
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#F7F9FC" stroke="#C9D3E3"/>',
           f'<text x="{x + 10}" y="{y + 16}" font-size="12.5" font-weight="700" fill="{NAVY}">{html.escape(title)}</text>']
    if status:
        out.append(f'<text x="{x + w - 10}" y="{y + 16}" font-size="11" font-weight="700" text-anchor="end" fill="{col}">{html.escape(status)}</text>')
    for i, (k, v) in enumerate(lines):
        yy = y + 34 + 17 * i
        vcol = AMBER if "NEEDS DATA" in str(v) else "#222"
        out.append(f'<text x="{x + 12}" y="{yy}" font-size="11.5" fill="#444">{html.escape(k)}</text>'
                   f'<text x="{x + w - 10}" y="{yy}" font-size="11.5" text-anchor="end" fill="{vcol}" font-weight="600">{v}</text>')
    return "".join(out)


def power_flow_svg(res: Result, case: str) -> str:
    R, I, G = res.rows, res.inputs, res.globals
    c = case
    q = lambda n: R[n][c]  # noqa: E731
    c50 = I.get("C50")
    kv_mv = _f(c50 * q("U_mv") / 100, 2, "kV") if isinstance(c50, (int, float)) else "NEEDS DATA"
    W, H, X = 980, 1030, 210  # X = main vertical line
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="font-family:Segoe UI,Arial,sans-serif;background:#fff">',
         "<defs>"]
    for colr in (NAVY, ORANGE):
        s.append(f'<marker id="ah-{colr[1:]}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                 f'<path d="M0,0 L10,5 L0,10 z" fill="{colr}"/></marker>')
    s.append("</defs>")
    s.append(f'<text x="20" y="26" font-size="16" font-weight="700" fill="{NAVY}">Case {html.escape(c)} - simplified power-flow view</text>'
             f'<text x="20" y="44" font-size="11.5" fill="{RED}">Excel-equivalent sequential calculation - NOT an ETAP / AC load-flow solution. '
             'Conceptual single-line view - confirm against project SLD.</text>')
    # ---- equipment geometry
    yb = {"poi": 140, "mv": 400, "lv": 700}
    # grid source
    s.append(f'<circle cx="{X}" cy="80" r="26" fill="#E7E6E6" stroke="{GREY}" stroke-width="2"/>'
             f'<text x="{X}" y="84" font-size="12" text-anchor="middle" font-weight="700">Grid</text>')
    s.append(f'<line x1="{X}" y1="106" x2="{X}" y2="{yb["poi"]}" stroke="#000" stroke-width="2"/>')

    def bus(y, label):
        return (f'<rect x="{X - 150}" y="{y - 4}" width="300" height="8" fill="#000"/>'
                f'<text x="{X + 150}" y="{y - 10}" font-size="12" font-weight="700" text-anchor="end">{html.escape(label)}</text>')

    def xfmr(y, label):
        return (f'<circle cx="{X}" cy="{y}" r="24" fill="none" stroke="#000" stroke-width="2.4"/>'
                f'<circle cx="{X}" cy="{y + 32}" r="24" fill="none" stroke="#000" stroke-width="2.4"/>'
                f'<text x="{X - 34}" y="{y + 20}" font-size="12" text-anchor="end" font-weight="700">{html.escape(label)}</text>')

    s.append(bus(yb["poi"], "POI / HV bus"))
    s.append(f'<line x1="{X}" y1="{yb["poi"]}" x2="{X}" y2="226" stroke="#000" stroke-width="2"/>')
    s.append(xfmr(250, "GSU"))
    s.append(f'<line x1="{X}" y1="306" x2="{X}" y2="{yb["mv"]}" stroke="#000" stroke-width="2"/>')
    s.append(bus(yb["mv"], "MV collector bus"))
    # aux load branch (left)
    ax = X - 110
    s.append(f'<line x1="{ax}" y1="{yb["mv"]}" x2="{ax}" y2="{yb["mv"] + 60}" stroke="#000" stroke-width="2" marker-end="url(#ah-{NAVY[1:]})"/>'
             f'<text x="{ax}" y="{yb["mv"] + 78}" font-size="11.5" text-anchor="middle" font-weight="700">Aux load</text>'
             f'<text x="{ax}" y="{yb["mv"] + 94}" font-size="11" text-anchor="middle">{_f(G["aux_p"])} MW / {_f(G["aux_q"])} MVAr</text>')
    # shunt branch (right) only when relevant
    c11 = I.get("C11") or 0
    cap, reac = q("cap_req"), q("reac_req")
    need_txt = None
    if isinstance(cap, (int, float)) and cap > 0:
        need_txt = f"Required capacitor {_f(cap)} MVAr (supplied)"
    elif isinstance(reac, (int, float)) and reac > 0:
        need_txt = f"Required reactor {_f(reac)} MVAr (absorbed)"
    if c11 or need_txt:
        sx = X + 110
        s.append(f'<line x1="{sx}" y1="{yb["mv"]}" x2="{sx}" y2="{yb["mv"] + 44}" stroke="{ORANGE}" stroke-width="2" stroke-dasharray="5 3"/>'
                 f'<rect x="{sx - 18}" y="{yb["mv"] + 44}" width="36" height="4" fill="{ORANGE}"/>'
                 f'<rect x="{sx - 18}" y="{yb["mv"] + 54}" width="36" height="4" fill="{ORANGE}"/>')
        t1 = (f"Fixed shunt C11: {_f(c11 * (q('U_mv') / 100) ** 2)} MVAr " + ("supplied" if c11 > 0 else "absorbed")) if c11 else "No fixed shunt"
        s.append(f'<text x="{sx}" y="{yb["mv"] + 76}" font-size="11" text-anchor="middle" fill="{ORANGE}">{html.escape(t1)}</text>')
        if need_txt:
            s.append(f'<text x="{sx}" y="{yb["mv"] + 92}" font-size="11" text-anchor="middle" fill="{RED}" font-weight="700">{html.escape(need_txt)}</text>')
    s.append(f'<line x1="{X}" y1="{yb["mv"]}" x2="{X}" y2="546" stroke="#000" stroke-width="2"/>'
             f'<text x="{X + 8}" y="520" font-size="10.5" fill="{GREY}" font-style="italic">MV cables (C19)</text>')
    s.append(xfmr(570, f'MV transformers × {G["n_mvt"]}'))
    s.append(f'<line x1="{X}" y1="626" x2="{X}" y2="{yb["lv"]}" stroke="#000" stroke-width="2"/>'
             f'<text x="{X + 8}" y="676" font-size="10.5" fill="{GREY}" font-style="italic">LV cables (C20)</text>')
    s.append(bus(yb["lv"], "PCS AC terminals (LV)"))
    s.append(f'<line x1="{X}" y1="{yb["lv"]}" x2="{X}" y2="800" stroke="#000" stroke-width="2"/>')
    s.append(f'<rect x="{X - 60}" y="800" width="120" height="74" rx="6" fill="#DDEBF7" stroke="{NAVY}" stroke-width="2"/>'
             f'<line x1="{X - 60}" y1="874" x2="{X + 60}" y2="800" stroke="{NAVY}" stroke-width="1"/>'
             f'<text x="{X - 40}" y="824" font-size="16" fill="{NAVY}">~</text><text x="{X + 30}" y="864" font-size="16" fill="{NAVY}">=</text>'
             f'<text x="{X - 70}" y="842" font-size="12" text-anchor="end" font-weight="700">PCS fleet × {G["n_inst"]}</text>')
    s.append(f'<line x1="{X}" y1="874" x2="{X}" y2="930" stroke="#000" stroke-width="2"/>'
             f'<rect x="{X - 60}" y="930" width="120" height="44" rx="6" fill="#E2EFDA" stroke="{GREEN}" stroke-width="2"/>'
             f'<text x="{X}" y="950" font-size="12" text-anchor="middle" font-weight="700">Battery / DC</text>'
             f'<text x="{X}" y="966" font-size="10.5" text-anchor="middle" fill="{GREY}">not modelled</text>')

    # flow arrows (left of main line): P blue, Q orange; up = toward grid
    def flows(y_top, y_bot, P, Q):
        out = _arrow(X - 52, y_top, y_bot, P >= 0, NAVY, "")
        out += _arrow(X - 30, y_top, y_bot, Q >= 0, ORANGE, "", dash=True)
        out += (f'<text x="{X - 60}" y="{(y_top + y_bot) / 2 - 2}" font-size="11.5" text-anchor="end" fill="{NAVY}" font-weight="600">P {_f(abs(P))} MW</text>'
                f'<text x="{X - 60}" y="{(y_top + y_bot) / 2 + 14}" font-size="11.5" text-anchor="end" fill="{ORANGE}" font-weight="600">Q {_f(abs(Q))} MVAr</text>')
        return out
    s.append(flows(158, 218, q("P_poi"), q("Q_poi")))
    s.append(flows(318, 388, q("P_mv"), q("Q_mv")))
    s.append(flows(712, 790, q("P_pcs"), q("Q_pcs")))
    # ---- value panels (right)
    PX = 470
    chk = res.globals["checks"]
    pf_txt = lambda pf, qq: f"{abs(pf):.3f} {'UE' if qq < 0 else 'OE'}"  # noqa: E731
    dir_p = lambda p: "→ grid (export)" if p >= 0 else "← grid (import)"  # noqa: E731
    dir_q = lambda qq: "→ grid (supplied, OE)" if qq >= 0 else "← grid (absorbed, UE)"  # noqa: E731
    s.append(_panel(PX, 60, "Grid / POI (HV bus)", [
        ("Voltage", f"{_f(I['C43'] / 100, 3)} pu / {_f(I['C5'] * I['C43'] / 100, 2)} kV"),
        ("P", f"{_f(q('P_poi'))} MW  {dir_p(q('P_poi'))}"), ("Q", f"{_f(q('Q_poi'))} MVAr  {dir_q(q('Q_poi'))}"),
        ("S / PF", f"{_f(q('S_poi'))} MVA / {pf_txt(q('pf_poi'), q('Q_poi'))}"), ("Grid impedance / SCL", "NEEDS DATA")], w=490))
    s.append(_panel(PX, 205, "GSU transformer", [
        ("Rating", f"{_f(G['Sb'])} MVA"), ("Loading", f"{_f(R['gsu_loading'][c], 3)} pu"),
        ("Active loss", f"{_f(q('P_gsu'), 3)} MW"), ("Reactive demand (consumed)", f"{_f(q('Q_gsu'))} MVAr"), ("Tap position", "NEEDS DATA (nominal)")], w=490,
        status="PASS" if R["gsu_loading"][c] <= 1 + 1e-6 else "FAIL"))
    s.append(_panel(PX, 350, "MV collector bus", [
        ("Voltage", f"{_f(q('U_mv') / 100, 3)} pu / {kv_mv}"), ("P (collector)", f"{_f(q('P_mv'))} MW  {dir_p(q('P_mv'))}"),
        ("Q (collector)", f"{_f(q('Q_mv'))} MVAr  {dir_q(q('Q_mv'))}"), ("S / PF", f"{_f(q('S_mv'))} MVA / {pf_txt(q('pf_mv'), q('Q_mv'))}"),
        ("Capacitor / reactor required", f"{_f(cap)} / {_f(reac)} MVAr" if isinstance(cap, (int, float)) else "NEEDS DATA")], w=490,
        status=chk["chk_vmv"][c]))
    s.append(_panel(PX, 495, "MV cables + MV transformers", [
        ("Count / basis", f"{G['n_mvt']} ({G['mvt_basis']})"), ("Loading", f"{_f(q('mvt_loading'), 3)} pu"),
        ("Active loss (copper + core)", f"{_f(q('P_mvt'), 3)} MW"), ("Reactive demand (consumed)", f"{_f(q('Q_mvt'))} MVAr"),
        ("Cable reactance / charging", "NEEDS DATA")], w=490,
        status={"NEEDS DATA": "NEEDS DATA"}.get(chk["chk_mvt"][c], chk["chk_mvt"][c])))
    s.append(_panel(PX, 640, "PCS AC terminals (LV bus)", [
        ("Voltage", f"{_f(q('U_lv') / 100, 3)} pu / {_f(I['C6'] / 1000 * q('U_lv') / 100, 3)} kV"),
        ("P", f"{_f(q('P_pcs'))} MW  {'PCS exports' if q('P_pcs') >= 0 else 'PCS absorbs'}"),
        ("Q", f"{_f(q('Q_pcs'))} MVAr  {'PCS supplies' if q('Q_pcs') >= 0 else 'PCS absorbs'}"),
        ("S / PF", f"{_f(q('S_pcs'))} MVA / {pf_txt(q('pf_pcs'), q('Q_pcs'))}")], w=490,
        status={"VENDOR": "NEEDS DATA"}.get(chk["chk_vpcs"][c], chk["chk_vpcs"][c])))
    qv = _f(q("Q_avail")) + " MVAr" if isinstance(I.get("C46"), (int, float)) else "NEEDS DATA (vendor curve)"
    s.append(_panel(PX, 790, "PCS fleet", [
        ("Installed units / unit rating", f"{G['n_inst']} × {_f(I['C38'])} MVA"),
        ("Derated MVA / MW", f"{_f(q('S_pcs_cap'))} MVA / {_f(q('P_pcs_cap'))} MW"),
        ("MVA loading", f"{_f(q('S_pcs') / q('S_pcs_cap'), 3)} pu"), ("Q available (vendor-limited)", qv),
        ("Q at MVA limit (ideal, NOT vendor)", f"{_f(math.sqrt(max(0, q('S_pcs_cap') ** 2 - q('P_pcs') ** 2)))} MVAr")], w=490,
        status={"VENDOR": "NEEDS DATA"}.get(chk["chk_pq"][c], chk["chk_pq"][c])))
    # legend
    s.append(f'<g transform="translate(20,{H - 34})"><line x1="0" y1="0" x2="30" y2="0" stroke="{NAVY}" stroke-width="3"/>'
             f'<text x="36" y="4" font-size="11">P (MW) - arrow up = toward grid</text>'
             f'<line x1="250" y1="0" x2="280" y2="0" stroke="{ORANGE}" stroke-width="3" stroke-dasharray="6 4"/>'
             f'<text x="286" y="4" font-size="11">Q (MVAr) - arrow up = supplied toward grid (OE)</text>'
             f'<text x="600" y="4" font-size="11" fill="{AMBER}">NEEDS DATA = vendor/SLD input blank</text></g>')
    s.append("</svg>")
    return "".join(s)
