"""Tables and file exports (Excel, CSV, JSON input sets)."""
from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any

import pandas as pd

from .model import CASES, CHECK_DEFS, DERATING_ROWS, INPUT_BY_KEY, INPUTS, ROW_DEFS, Result

APP_VERSION = "1.0.0 (port of PCS_Sizing_Tool_FINAL_FROZEN.xlsx)"


def detailed_df(res: Result) -> pd.DataFrame:
    rows = []
    for name, row, unit, label in ROW_DEFS:
        if name not in res.rows:
            continue
        rows.append({"Excel row": row, "Quantity": label, **{c: res.rows[name][c] for c in CASES}, "Unit": unit})
    return pd.DataFrame(rows)


def checks_df(res: Result) -> pd.DataFrame:
    if "checks" not in res.globals:
        return pd.DataFrame()
    return pd.DataFrame([{"Excel row": r, "Check": label, **{c: res.globals["checks"][n][c] for c in CASES}} for n, r, label in CHECK_DEFS])


def summary_df(res: Result) -> pd.DataFrame:
    return pd.DataFrame([{"Check / quantity": s["label"], "Result": s["result"], "Value": s["value"], "Unit": s["unit"],
                          "Basis": s["basis"], "Notes": s["note"]} for s in res.summary])


def input_checks_df(res: Result) -> pd.DataFrame:
    return pd.DataFrame([{"Cell": r["cell"], "Parameter": r["parameter"], "Value": "(blank)" if r["value"] is None else r["value"],
                          "Unit": r["unit"], "Rule": r["rule"], "Status": r["status"]} for r in res.globals["input_checks"]])


def power_flow_df(res: Result) -> pd.DataFrame:
    if not res.rows:
        return pd.DataFrame()
    R, I = res.rows, res.inputs
    c50 = I.get("C50")
    spec = [("Grid / POI", "Voltage", lambda c: I["C43"] / 100, "pu"), ("Grid / POI", "Voltage", lambda c: I["C5"] * I["C43"] / 100, "kV"),
            ("Grid / POI", "P", lambda c: R["P_poi"][c], "MW"), ("Grid / POI", "Q", lambda c: R["Q_poi"][c], "MVAr"),
            ("Grid / POI", "S", lambda c: R["S_poi"][c], "MVA"), ("Grid / POI", "PF", lambda c: R["pf_poi"][c], "-"),
            ("GSU", "Loading", lambda c: R["gsu_loading"][c], "pu"), ("GSU", "Active loss", lambda c: R["P_gsu"][c], "MW"),
            ("GSU", "Reactive demand", lambda c: R["Q_gsu"][c], "MVAr"),
            ("MV bus", "Voltage", lambda c: R["U_mv"][c] / 100, "pu"),
            ("MV bus", "Voltage", lambda c: c50 * R["U_mv"][c] / 100 if isinstance(c50, (int, float)) else "NEEDS DATA", "kV"),
            ("MV bus", "P", lambda c: R["P_mv"][c], "MW"), ("MV bus", "Q", lambda c: R["Q_mv"][c], "MVAr"),
            ("MV bus", "S", lambda c: R["S_mv"][c], "MVA"), ("MV bus", "PF", lambda c: R["pf_mv"][c], "-"),
            ("MV bus", "Capacitor required", lambda c: R["cap_req"][c], "MVAr"), ("MV bus", "Reactor required", lambda c: R["reac_req"][c], "MVAr"),
            ("MV transformers", "Count", lambda c: R["n_mvt"][c], "Nos"), ("MV transformers", "Loading", lambda c: R["mvt_loading"][c], "pu"),
            ("MV transformers", "Active loss", lambda c: R["P_mvt"][c], "MW"), ("MV transformers", "Reactive demand", lambda c: R["Q_mvt"][c], "MVAr"),
            ("PCS terminals", "Voltage", lambda c: R["U_lv"][c] / 100, "pu"), ("PCS terminals", "Voltage", lambda c: I["C6"] / 1000 * R["U_lv"][c] / 100, "kV"),
            ("PCS terminals", "P", lambda c: R["P_pcs"][c], "MW"), ("PCS terminals", "Q", lambda c: R["Q_pcs"][c], "MVAr"),
            ("PCS terminals", "S", lambda c: R["S_pcs"][c], "MVA"), ("PCS terminals", "PF", lambda c: R["pf_pcs"][c], "-"),
            ("PCS fleet", "Installed units", lambda c: R["n_inst"][c], "Nos"), ("PCS fleet", "Derated MVA", lambda c: R["S_pcs_cap"][c], "MVA"),
            ("PCS fleet", "MVA loading", lambda c: R["S_pcs"][c] / R["S_pcs_cap"][c], "pu"),
            ("PCS fleet", "Q available (vendor-limited)", lambda c: R["Q_avail"][c] if isinstance(I.get("C46"), (int, float)) else "NEEDS DATA", "MVAr")]
    return pd.DataFrame([{"Element": e, "Quantity": q, **{c: f(c) for c in CASES}, "Unit": u} for e, q, f, u in spec])


def inputs_df(inp: dict[str, Any], derate: dict) -> pd.DataFrame:
    rows = [{"Cell": d["key"], "Group": d["group"], "Parameter": d["label"], "Value": inp.get(d["key"]), "Unit": d["unit"],
             "Type": {"req": "essential", "opt": "vendor/SLD", "ref": "reference only"}[d["kind"]]} for d in INPUTS]
    for k, label, _ in DERATING_ROWS:
        for c in CASES:
            rows.append({"Cell": "J36:M39", "Group": "Derating", "Parameter": f"{label} - {c}", "Value": derate[c][k], "Unit": "-", "Type": "essential"})
    return pd.DataFrame(rows)


def to_excel(res: Result, user: str = "") -> bytes:
    buf = io.BytesIO()
    meta = pd.DataFrame([{"Item": "Tool", "Value": "BESS PCS Sizing Tool (preliminary screening, not design approval)"},
                         {"Item": "Version", "Value": APP_VERSION}, {"Item": "Exported", "Value": datetime.now().strftime("%Y-%m-%d %H:%M")},
                         {"Item": "Exported by", "Value": user},
                         {"Item": "Overall result", "Value": next(s["result"] for s in res.summary if s["key"] == "overall")},
                         {"Item": "Sign convention", "Value": "Generator: P>0 discharge/export, Q>0 over-excited (supplied toward grid)"}])
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        meta.to_excel(xw, sheet_name="About", index=False)
        summary_df(res).to_excel(xw, sheet_name="Results Summary", index=False)
        power_flow_df(res).to_excel(xw, sheet_name="Power Flow", index=False)
        detailed_df(res).to_excel(xw, sheet_name="Detailed", index=False)
        checks_df(res).to_excel(xw, sheet_name="Design checks", index=False)
        input_checks_df(res).to_excel(xw, sheet_name="Input checks", index=False)
        inputs_df(res.inputs, res.derating).to_excel(xw, sheet_name="Inputs", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
            ws.freeze_panes = "A2"
    return buf.getvalue()


def to_json(inp: dict[str, Any], derate: dict, project: str = "") -> str:
    return json.dumps({"tool": "pcs-sizing-tool", "version": APP_VERSION, "project": project,
                       "saved": datetime.now().isoformat(timespec="seconds"), "inputs": inp, "derating": derate}, indent=2)


def from_json(text: str) -> tuple[dict[str, Any], dict, str]:
    data = json.loads(text)
    if not isinstance(data, dict) or "inputs" not in data:
        raise ValueError("Not a PCS sizing input file (missing 'inputs').")
    inp = {}
    for k, v in data["inputs"].items():
        if k not in INPUT_BY_KEY:
            continue
        if v is not None and not isinstance(v, (int, float)):
            raise ValueError(f"{k}: value must be a number or null")
        inp[k] = v
    der = data.get("derating") or {}
    return inp, der, str(data.get("project", ""))
