"""PCS sizing calculation engine.

A line-by-line port of the frozen Excel workbook ``PCS_Sizing_Tool_FINAL_FROZEN.xlsx``
(sheet ``PCS`` rows 4-78 and sheet ``Results Summary``). Each quantity carries the
Excel row it reproduces so results can be traced back to the workbook.

Sign convention (generator): P > 0 = discharge/export, Q > 0 = over-excited
(reactive power supplied toward the grid). All four operating cases are solved.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

CASES = ["DiS-OE", "DiS-UE", "Cha-OE", "Cha-UE"]
EPS = 1e-6

# --------------------------------------------------------------------------------------
# Input definitions (cell reference, label, unit, default test value, group, kind, note)
# kind: "req" = essential input, "opt" = vendor/SLD data (may be blank), "ref" = reference
# only (not used by the calculation).
# --------------------------------------------------------------------------------------
INPUTS: list[dict[str, Any]] = [
    # Grid / POI
    dict(key="C4", label="Active power at POI on HV level", unit="MW", default=100.0, group="Grid / POI", kind="req"),
    dict(key="C14", label="POI power factor", unit="-", default=0.95, group="Grid / POI", kind="req"),
    dict(key="C43", label="POI voltage used for calculation", unit="% Un", default=100.0, group="Grid / POI", kind="req",
         note="Re-run at grid-code min/max voltage"),
    dict(key="C5", label="PCC voltage", unit="kV", default=100.0, group="Grid / POI", kind="req", note="kV display only"),
    dict(key="C30", label="MV voltage tolerance +", unit="%", default=5.0, group="Grid / POI", kind="req"),
    dict(key="C31", label="MV voltage tolerance −", unit="%", default=-5.0, group="Grid / POI", kind="req"),
    # GSU
    dict(key="C23", label="GSU rating (ONAN)", unit="MVA", default=115.0, group="GSU transformer", kind="req"),
    dict(key="C28", label="GSU count", unit="Nos", default=1, group="GSU transformer", kind="req"),
    dict(key="C16", label="GSU R%", unit="%", default=0.504, group="GSU transformer", kind="req"),
    dict(key="C17", label="GSU X%", unit="%", default=10.09, group="GSU transformer", kind="req"),
    dict(key="C45", label="GSU magnetizing Q", unit="% of GSU MVA", default=1.0, group="GSU transformer", kind="req",
         note="Confirm from GSU test report"),
    # MV system
    dict(key="C12", label="Auxiliary consumption on MV level", unit="MVA", default=6.42, group="MV system & auxiliaries", kind="req"),
    dict(key="C13", label="Auxiliary consumption PF", unit="-", default=0.8, group="MV system & auxiliaries", kind="req"),
    dict(key="C11", label="Fixed MV shunt (+ capacitor / − reactor)", unit="MVAr", default=0.0, group="MV system & auxiliaries",
         kind="req", note="Connected in all four cases"),
    dict(key="C19", label="MV AC cable losses", unit="fraction", default=0.0012, group="MV system & auxiliaries", kind="req",
         note="0.0012 = 0.12 %"),
    dict(key="C20", label="AC cable loss PCS → MVT", unit="%", default=2.2, group="MV system & auxiliaries", kind="req"),
    # MV transformers
    dict(key="C33", label="MVT rating", unit="MVA", default=6.36, group="MV transformers", kind="req"),
    dict(key="C35", label="MVT R%", unit="%", default=0.75, group="MV transformers", kind="req"),
    dict(key="C36", label="MVT X%", unit="%", default=7.96, group="MV transformers", kind="req"),
    dict(key="C37", label="MVT core loss", unit="kW", default=2.4, group="MV transformers", kind="req"),
    dict(key="C40", label="Allowed per-transformer loading", unit="pu", default=0.9, group="MV transformers", kind="req"),
    dict(key="C6", label="LV (PCS terminal) voltage", unit="V", default=480.0, group="MV transformers", kind="req"),
    # PCS
    dict(key="C38", label="PCS rated apparent power @ design temp", unit="MVA", default=1.5, group="PCS", kind="req"),
    dict(key="C39", label="PCS rated real power @ design temp", unit="MW", default=1.5, group="PCS", kind="req",
         note="Must not exceed C38"),
    dict(key="C44", label="PCS rating already at design temperature? (1 = yes, 0 = no)", unit="flag", default=1, group="PCS",
         kind="req", note="Confirm with vendor - avoids double temperature derating"),
    dict(key="C27", label="Additional inverters", unit="Nos", default=0, group="PCS", kind="req"),
    # Vendor / SLD data
    dict(key="C46", label="PCS max Q per unit @ rated P (vendor)", unit="MVAr", default=None, group="Vendor / SLD data", kind="opt"),
    dict(key="C47", label="PCS AC voltage max (vendor)", unit="% Un", default=None, group="Vendor / SLD data", kind="opt"),
    dict(key="C48", label="PCS AC voltage min (vendor)", unit="% Un", default=None, group="Vendor / SLD data", kind="opt"),
    dict(key="C49", label="Number of MV transformers (SLD; blank = derive)", unit="Nos", default=None, group="Vendor / SLD data", kind="opt"),
    dict(key="C50", label="MV collector nominal voltage (SLD)", unit="kV", default=None, group="Vendor / SLD data", kind="opt",
         note="kV display only"),
    # Reference only (kept for traceability; not used in the calculation)
    dict(key="C7", label="Design temperature (max)", unit="°C", default=35.0, group="Reference only", kind="ref"),
    dict(key="C8", label="MV transformer efficiency", unit="%", default=99.7, group="Reference only", kind="ref"),
    dict(key="C9", label="MV transformer impedance", unit="%", default=8.0, group="Reference only", kind="ref"),
    dict(key="C34", label="MVT Z%", unit="%", default=8.0, group="Reference only", kind="ref"),
    dict(key="C32", label="MV X/R", unit="-", default=10.0, group="Reference only", kind="ref"),
    dict(key="C18", label="GSU impedance", unit="%", default=10.1, group="Reference only", kind="ref"),
    dict(key="C15", label="GSU X/R ratio", unit="-", default=34.0, group="Reference only", kind="ref"),
    dict(key="C10", label="AC voltage adjustment tap changer (not applied)", unit="%", default=2.5, group="Reference only", kind="ref"),
    dict(key="C21", label="PCS inverter efficiency (DC side)", unit="%", default=98.0, group="Reference only", kind="ref"),
    dict(key="C22", label="GSU efficiency", unit="%", default=99.0, group="Reference only", kind="ref"),
    dict(key="C24", label="Contingency support PF (not implemented)", unit="-", default=0.0, group="Reference only", kind="ref"),
    dict(key="C25", label="Inverter max power factor (not implemented)", unit="-", default=1.0, group="Reference only", kind="ref"),
    dict(key="C26", label="Grid frequency", unit="Hz", default=60.0, group="Reference only", kind="ref"),
]
INPUT_BY_KEY = {d["key"]: d for d in INPUTS}

DERATING_ROWS = [("temp", "Temperature S derating (J36)", 0.96), ("alt", "Altitude S derating (J37)", 0.98),
                 ("acv", "AC-voltage S derating (J38)", 0.99), ("dcv", "DC-voltage S derating (J39)", 0.97)]


def default_inputs() -> dict[str, Any]:
    return {d["key"]: d["default"] for d in INPUTS}


def default_derating() -> dict[str, dict[str, float]]:
    return {case: {k: v for k, _, v in DERATING_ROWS} for case in CASES}


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _roundup(x: float) -> int:
    """Excel ROUNDUP(x, 0): away from zero."""
    return int(math.ceil(x - 1e-12)) if x >= 0 else -int(math.ceil(-x - 1e-12))


# --------------------------------------------------------------------------------------
# Input validity (Results Summary rows 34-63)
# --------------------------------------------------------------------------------------
_RULES: list[tuple[str, str, Any, bool]] = [
    ("C4", ">0", lambda v, i: v > 0, True), ("C5", ">0", lambda v, i: v > 0, True), ("C6", ">0", lambda v, i: v > 0, True),
    ("C11", "number (+cap / −reactor)", lambda v, i: True, True), ("C12", "≥0", lambda v, i: v >= 0, True),
    ("C13", "0<PF≤1", lambda v, i: 0 < v <= 1, True), ("C14", "0<PF≤1", lambda v, i: 0 < v <= 1, True),
    ("C16", "≥0", lambda v, i: v >= 0, True), ("C17", ">0", lambda v, i: v > 0, True),
    ("C19", "0≤x<1", lambda v, i: 0 <= v < 1, True), ("C20", "0≤x<100", lambda v, i: 0 <= v < 100, True),
    ("C23", ">0", lambda v, i: v > 0, True), ("C27", "whole ≥0", lambda v, i: v >= 0 and v == int(v), True),
    ("C28", "whole ≥1", lambda v, i: v >= 1 and v == int(v), True), ("C30", ">0", lambda v, i: v > 0, True),
    ("C31", "<0", lambda v, i: v < 0, True), ("C33", ">0", lambda v, i: v > 0, True), ("C35", "≥0", lambda v, i: v >= 0, True),
    ("C36", ">0", lambda v, i: v > 0, True), ("C37", "≥0", lambda v, i: v >= 0, True), ("C38", ">0", lambda v, i: v > 0, True),
    ("C39", "0 < C39 ≤ C38 (MW ≤ MVA)", lambda v, i: _num(i.get("C38")) and 0 < v <= i["C38"], True),
    ("C40", "0<x≤2", lambda v, i: 0 < v <= 2, True), ("C43", "80–120", lambda v, i: 80 <= v <= 120, True),
    ("C44", "0 or 1", lambda v, i: v in (0, 1), True), ("C45", "≥0", lambda v, i: v >= 0, True),
    ("C46", "≥0 (vendor)", lambda v, i: v >= 0, False),
    ("C47", "> C48 (vendor)", lambda v, i: _num(i.get("C48")) and v > i["C48"], False),
    ("C49", "whole ≥1 (SLD)", lambda v, i: v >= 1 and v == int(v), False),
    ("C48", ">0 (vendor)", lambda v, i: v > 0, False),
]


def input_checks(inp: dict[str, Any], derate: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    rows = []
    for key, rule, fn, essential in _RULES:
        v = inp.get(key)
        if v is None or v == "":
            status = "INVALID" if essential else "BLANK - NEEDS DATA"
        elif not _num(v):
            status = "INVALID"
        else:
            try:
                status = "OK" if fn(v, inp) else "INVALID"
            except Exception:  # pragma: no cover - defensive
                status = "INVALID"
        rows.append(dict(cell=key, parameter=INPUT_BY_KEY[key]["label"], value=v, unit=INPUT_BY_KEY[key]["unit"],
                         rule=rule, status=status))
    vals = [derate[c][k] for c in CASES for k, _, _ in DERATING_ROWS]
    ok = all(_num(x) for x in vals) and min(vals) > 0 and max(vals) <= 1
    rows.append(dict(cell="J36:M39", parameter="Derating factors (16 values)", value=min(vals) if all(_num(x) for x in vals) else None,
                     unit="min", rule="0<k≤1", status="OK" if ok else "INVALID"))
    return rows


# --------------------------------------------------------------------------------------
# Main calculation (PCS sheet)
# --------------------------------------------------------------------------------------
@dataclass
class Result:
    inputs: dict[str, Any]
    derating: dict[str, dict[str, float]]
    rows: dict[str, dict[str, Any]] = field(default_factory=dict)   # quantity -> {case: value}
    globals: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    summary: list[dict[str, Any]] = field(default_factory=list)
    input_validity: str = "OK"
    error: str | None = None

    def get(self, name: str, case: str) -> Any:
        return self.rows[name][case]


# Ordered output rows: (name, excel row, unit, label)
ROW_DEFS = [
    ("sin_poi", 4, "-", "SinPh (POI)"), ("P_poi", 5, "MW", "P active power on HV grid"), ("pf_poi", 6, "-", "Power factor at HV level"),
    ("S_poi", 7, "MVA", "S apparent power on HV grid"), ("Q_poi", 8, "MVAr", "Q on the HV grid"),
    ("Q_gsu", 9, "MVAr", "Q demand of all HV transformers"), ("P_gsu", 10, "MW", "P losses of all HV transformers"),
    ("Ud_mv", 11, "%", "Direct-axis voltage Ud MV"), ("Uq_mv", 12, "%", "Quadrature-axis voltage Uq MV"),
    ("U_mv", 13, "% Un", "Voltage on MV level U_MV"), ("dU_mv", 14, "%", "MV voltage deviation from Un"),
    ("P_mv", 16, "MW", "P active power on MV grid"), ("pf_mv", 17, "-", "Power factor at MV level"),
    ("sin_mv", 18, "-", "SinPh (MV)"), ("S_mv", 19, "MVA", "S apparent power on MV grid"), ("Q_mv", 20, "MVAr", "Q on the MV grid"),
    ("Q_mvt", 21, "MVAr", "Q demand of all MV transformers"), ("P_mvt", 22, "MW", "P losses of all MV transformers"),
    ("Ud_lv", 23, "%", "Direct-axis voltage Ud LV"), ("Uq_lv", 24, "%", "Quadrature-axis voltage Uq LV"),
    ("U_lv", 25, "% Un", "Voltage at PCS terminals U_LV"), ("dU_lv", 26, "%", "LV voltage deviation from Un"),
    ("mvt_loading", 27, "pu", "MV transformer actual loading"),
    ("P_pcs", 29, "MW", "P required at PCS"), ("Q_pcs", 30, "MVAr", "Q required at PCS"), ("S_pcs", 31, "MVA", "S required at PCS"),
    ("pf_pcs", 32, "-", "Power factor at PCS"), ("sin_pcs", 33, "-", "SinPh (PCS)"),
    ("U_lv_V", 34, "V", "PCS terminal voltage (L-L, nominal)"), ("U_lv_ph", 35, "V", "PCS terminal voltage (L-N, nominal)"),
    ("k", 40, "-", "Overall S derating factor"), ("S_pcs_cap", 41, "MVA", "Derated S capacity PCSs (installed)"),
    ("S_mvt_np", 42, "MVA", "Nameplate S capacity MV transformers"), ("P_pcs_cap", 43, "MW", "Derated P capacity PCSs (installed)"),
    ("P_mvt_cap", 44, "MW", "Estimated P capacity MV transformers"),
    ("n_mva", 46, "Nos", "No. of inverters - derated MVA"), ("n_mva_np", 47, "Nos", "No. of inverters - nameplate MVA"),
    ("n_case", 48, "Nos", "Selected no. of inverters (case)"), ("S_pcs_np", 49, "MVA", "Installed nameplate MVA"),
    ("n_mw", 50, "Nos", "No. of inverters - derated MW"), ("n_mw_np", 51, "Nos", "No. of inverters - nameplate MW"),
    ("n_mw_sel", 52, "Nos", "Selected no. by MW"), ("P_pcs_np", 53, "MW", "Installed nameplate MW"),
    ("Q_avail", 54, "MVAr", "Q available (ideal circle; vendor cap if C46)"), ("pf_op", 55, "-", "Operating PF of inverters"),
    ("cap_req", 56, "MVAr", "Capacitor bank required @100 % U"), ("n_mvt", 60, "Nos", "No. of MV transformers"),
    ("reac_req", 61, "MVAr", "Reactor required @100 % U"), ("cap_mw_only", 62, "MVAr", "Indicative min. capacitor if sized on MW only"),
    ("n_inst", 63, "Nos", "Installed PCS count (governing)"),
]
ROW_META = {n: dict(row=r, unit=u, label=l) for n, r, u, l in ROW_DEFS}

CHECK_DEFS = [
    ("chk_s2", 65, "S² = P² + Q² at PCS terminals"), ("chk_vmv", 66, "MV bus voltage screening at C43 (nominal taps)"),
    ("chk_vpcs", 67, "PCS terminal voltage screening vs vendor window"), ("chk_mva", 68, "PCS S ≤ derated installed MVA (ideal)"),
    ("chk_pq", 69, "PCS Q ≤ vendor Q limit at this P"), ("chk_mvt", 70, "MV transformer loading ≤ C40 (SLD count C49)"),
    ("chk_noq", 71, "PCS meets Q without compensation"), ("chk_int", 72, "PCS count non-negative integer"),
]


def calculate(inp: dict[str, Any], derate: dict[str, dict[str, float]] | None = None) -> Result:
    derate = derate or default_derating()
    res = Result(inputs=dict(inp), derating=derate)
    ic = input_checks(inp, derate)
    res.globals["input_checks"] = ic
    n_invalid = sum(1 for r in ic if r["status"] == "INVALID")
    res.input_validity = "OK" if n_invalid == 0 else "INVALID INPUTS"
    res.globals["n_invalid"] = n_invalid
    try:
        _solve(res, inp, derate)
    except (ZeroDivisionError, ValueError, TypeError, KeyError) as exc:
        res.error = f"{type(exc).__name__}: {exc}"
        res.rows = {}
    _summarise(res)
    return res


def _solve(res: Result, inp: dict[str, Any], derate: dict[str, dict[str, float]]) -> None:
    g = lambda k: inp[k]  # noqa: E731  (raises KeyError/TypeError for missing values -> handled)
    C4, C14, C43, C5, C30, C31 = g("C4"), g("C14"), g("C43"), g("C5"), g("C30"), g("C31")
    C23, C28, C16, C17, C45 = g("C23"), g("C28"), g("C16"), g("C17"), g("C45")
    C12, C13, C11, C19, C20 = g("C12"), g("C13"), g("C11"), g("C19"), g("C20")
    C33, C35, C36, C37, C40, C6 = g("C33"), g("C35"), g("C36"), g("C37"), g("C40"), g("C6")
    C38, C39, C44, C27 = g("C38"), g("C39"), g("C44"), g("C27")
    C46, C47, C48, C49 = inp.get("C46"), inp.get("C47"), inp.get("C48"), inp.get("C49")
    for name, val in [("C4", C4), ("C14", C14), ("C43", C43), ("C23", C23), ("C28", C28), ("C17", C17), ("C33", C33),
                      ("C38", C38), ("C39", C39), ("C40", C40), ("C13", C13)]:
        if not _num(val):
            raise ValueError(f"{name} is blank or not a number")
    v = C43 / 100.0
    Sb = C23 * C28
    aux_p = C12 * C13
    aux_q = C12 * math.sqrt(1 - C13 ** 2)
    sgn = {"DiS-OE": (1, 1), "DiS-UE": (1, -1), "Cha-OE": (-1, 1), "Cha-UE": (-1, -1)}
    R: dict[str, dict[str, Any]] = {n: {} for n, *_ in ROW_DEFS}
    # ---- HV / GSU / MV bus (rows 4-20) - independent of MVT count
    for c in CASES:
        sp, sq = sgn[c]
        sin = sq * math.sqrt(1 - C14 ** 2)
        P = sp * C4
        pf = sq * C14
        S = abs(P) / abs(pf)
        Q = sin * S
        Qg = S ** 2 * (C17 / 100) / Sb / v ** 2 + Sb * (C45 / 100) * v ** 2
        Pg = S ** 2 * (C16 / 100) / Sb / v ** 2
        Ud = ((C16 / 100) * P + (C17 / 100) * Q) / Sb / v * 100
        Uq = ((C17 / 100) * P - (C16 / 100) * Q) / Sb / v * 100
        Umv = math.sqrt((C43 + Ud) ** 2 + Uq ** 2)
        Pmv = P + Pg + aux_p
        Qmv = Q + Qg + aux_q - C11 * (Umv / 100) ** 2
        Smv = math.sqrt(Pmv ** 2 + Qmv ** 2)
        for n, val in [("sin_poi", sin), ("P_poi", P), ("pf_poi", pf), ("S_poi", S), ("Q_poi", Q), ("Q_gsu", Qg), ("P_gsu", Pg),
                       ("Ud_mv", Ud), ("Uq_mv", Uq), ("U_mv", Umv), ("dU_mv", Umv - 100), ("P_mv", Pmv), ("Q_mv", Qmv), ("S_mv", Smv),
                       ("pf_mv", (-1 if Qmv < 0 else 1) * abs(Pmv) / Smv), ("sin_mv", Qmv / Smv)]:
            R[n][c] = val
    # ---- MV transformer count (row 60)
    n_mvt = C49 if _num(C49) else _roundup(max(R["S_mv"].values()) / (C33 * C40))
    if n_mvt <= 0:
        raise ValueError("MV transformer count must be ≥ 1")
    # ---- MVT, PCS (rows 21-35)
    for c in CASES:
        Smv, Umv, Pmv, Qmv = R["S_mv"][c], R["U_mv"][c], R["P_mv"][c], R["Q_mv"][c]
        u = Umv / 100
        Qt = Smv ** 2 * (C36 / 100) / (n_mvt * C33) / u ** 2
        Pt = Smv ** 2 * (C35 / 100) / (n_mvt * C33) / u ** 2 + C37 * n_mvt / 1000
        if Pmv >= 0:
            Ppcs = (Pmv / (1 - C19) + Pt) / (1 - C20 / 100)
        else:
            Ppcs = (Pmv * (1 - C19) + Pt) * (1 - C20 / 100)
        Qpcs = Qmv + Qt
        Spcs = math.sqrt(Ppcs ** 2 + Qpcs ** 2)
        Udl = ((C35 / 100) * Ppcs + (C36 / 100) * Qpcs) / (n_mvt * C33) / u * 100
        Uql = ((C36 / 100) * Ppcs - (C35 / 100) * Qpcs) / (n_mvt * C33) / u * 100
        Ulv = math.sqrt((Umv + Udl) ** 2 + Uql ** 2)
        d = derate[c]
        k = (1 if C44 == 1 else d["temp"]) * d["alt"] * d["acv"] * d["dcv"]
        for n, val in [("Q_mvt", Qt), ("P_mvt", Pt), ("P_pcs", Ppcs), ("Q_pcs", Qpcs), ("S_pcs", Spcs),
                       ("pf_pcs", (-1 if Qpcs < 0 else 1) * abs(Ppcs) / Spcs), ("sin_pcs", Qpcs / Spcs),
                       ("Ud_lv", Udl), ("Uq_lv", Uql), ("U_lv", Ulv), ("dU_lv", Ulv - 100), ("mvt_loading", Smv / (n_mvt * C33)),
                       ("U_lv_V", C6), ("U_lv_ph", C6 / math.sqrt(3)), ("k", k), ("n_mvt", n_mvt), ("S_mvt_np", n_mvt * C33),
                       ("n_mva", _roundup(Spcs / (C38 * k))), ("n_mva_np", _roundup(Spcs / C38)),
                       ("n_mw", _roundup(abs(Ppcs) / (C39 * k))), ("n_mw_np", _roundup(abs(Ppcs) / C39)),
                       ("pf_op", abs(Ppcs) / Spcs)]:
            R[n][c] = val
        R["n_case"][c] = max(R["n_mva"][c], R["n_mw"][c]) + C27
        R["n_mw_sel"][c] = max(R["n_mw"][c], R["n_mw_np"][c])
        R["P_mvt_cap"][c] = n_mvt * C33 * C40 * abs(Pmv) / Smv
    n_inst = max(R["n_case"].values())
    n_mw_max = max(R["n_mw"].values())
    vendor_q = _num(C46)
    for c in CASES:
        k = R["k"][c]
        Scap = n_inst * C38 * k
        R["n_inst"][c] = n_inst
        R["S_pcs_cap"][c] = Scap
        R["P_pcs_cap"][c] = n_inst * C39 * k
        R["S_pcs_np"][c] = n_inst * C38
        R["P_pcs_np"][c] = n_inst * C39
        Ppcs, Qpcs, Umv = R["P_pcs"][c], R["Q_pcs"][c], R["U_mv"][c]
        circle = math.sqrt(max(0.0, Scap ** 2 - Ppcs ** 2))
        Qav = min(circle, n_inst * C46) if vendor_q else circle
        R["Q_avail"][c] = Qav
        u2 = (Umv / 100) ** 2
        if vendor_q:
            R["cap_req"][c] = max(0.0, Qpcs - Qav) / u2 if Qpcs > 0 else 0.0
            R["reac_req"][c] = max(0.0, -Qpcs - Qav) / u2 if Qpcs < 0 else 0.0
        else:
            R["cap_req"][c] = "NEEDS DATA"
            R["reac_req"][c] = "NEEDS DATA"
        circ_mw = math.sqrt(max(0.0, (n_mw_max * C38 * k) ** 2 - Ppcs ** 2))
        q_mw = min(circ_mw, n_mw_max * C46) if vendor_q else circ_mw
        R["cap_mw_only"][c] = max(0.0, Qpcs - q_mw) / u2 if Qpcs > 0 else 0.0
    res.rows = R
    # ---- design checks (rows 65-72)
    checks: dict[str, dict[str, str]] = {n: {} for n, *_ in CHECK_DEFS}
    for c in CASES:
        P, Q, S = R["P_pcs"][c], R["Q_pcs"][c], R["S_pcs"][c]
        checks["chk_s2"][c] = "PASS" if abs(S ** 2 - P ** 2 - Q ** 2) < EPS else "FAIL"
        dmv = R["dU_mv"][c]
        checks["chk_vmv"][c] = "SCREEN OK" if C31 <= dmv <= C30 else "FAIL"
        if not (_num(C47) and _num(C48)):
            checks["chk_vpcs"][c] = "VENDOR"
        else:
            checks["chk_vpcs"][c] = "SCREEN OK" if C48 <= R["U_lv"][c] <= C47 else "FAIL"
        checks["chk_mva"][c] = "PASS" if S <= R["S_pcs_cap"][c] + EPS else "FAIL"
        checks["chk_pq"][c] = ("PASS" if abs(Q) <= R["Q_avail"][c] + EPS else "FAIL") if vendor_q else "VENDOR"
        checks["chk_mvt"][c] = ("PASS" if R["mvt_loading"][c] <= C40 + EPS else "FAIL") if _num(C49) else "NEEDS DATA"
        checks["chk_noq"][c] = ("FAIL" if R["cap_req"][c] + R["reac_req"][c] > 0 else "PASS") if vendor_q else "VENDOR"
        n = R["n_case"][c]
        checks["chk_int"][c] = "PASS" if n >= 0 and n == int(n) else "FAIL"
    res.globals["checks"] = checks
    # GSU loading
    gsu = []
    for c in CASES:
        lv = math.sqrt((R["P_poi"][c] + R["P_gsu"][c]) ** 2 + (R["Q_poi"][c] + R["Q_gsu"][c]) ** 2)
        R.setdefault("S_gsu_lv", {})[c] = lv
        gsu.append(max(R["S_poi"][c], lv) / Sb)
        R.setdefault("gsu_loading", {})[c] = max(R["S_poi"][c], lv) / Sb
    res.globals.update(n_mvt=n_mvt, n_inst=n_inst, gsu_loading=max(gsu), Sb=Sb, aux_p=aux_p, aux_q=aux_q,
                       mvt_basis="SLD (C49)" if _num(C49) else "DERIVED")
    # input consistency (rows 74-78)
    res.globals["consistency"] = [
        dict(item="GSU |Z| from R, X vs C18", value=math.hypot(C16, C17), ref=inp.get("C18"),
             status=_rel_status(math.hypot(C16, C17), inp.get("C18"), 0.02)),
        dict(item="GSU X/R from R, X vs C15", value=C17 / C16 if C16 else None, ref=inp.get("C15"),
             status=_rel_status(C17 / C16 if C16 else None, inp.get("C15"), 0.10)),
        dict(item="MVT |Z| from R, X vs C34", value=math.hypot(C35, C36), ref=inp.get("C34"),
             status=_rel_status(math.hypot(C35, C36), inp.get("C34"), 0.02)),
        dict(item="MVT X/R from R, X vs C32", value=C36 / C35 if C35 else None, ref=inp.get("C32"),
             status=_rel_status(C36 / C35 if C35 else None, inp.get("C32"), 0.10)),
        dict(item="Temperature factor applied? (C44)", value=0 if C44 == 1 else 1, ref=C44, status="VENDOR" if C44 == 1 else "CHECK"),
    ]


def _rel_status(val: Any, ref: Any, tol: float) -> str:
    if not (_num(val) and _num(ref)) or ref == 0:
        return "CHECK"
    return "PASS" if abs(val - ref) / abs(ref) <= tol else "CHECK"


# --------------------------------------------------------------------------------------
# Results Summary (sheet "Results Summary" rows 5-26)
# --------------------------------------------------------------------------------------
def _summarise(res: Result) -> None:
    ok = res.input_validity == "OK" and res.error is None and bool(res.rows)
    S: list[dict[str, Any]] = []

    def add(key, label, result, value=None, unit="-", basis="", note=""):
        S.append(dict(key=key, label=label, result=result, value=value, unit=unit, basis=basis, note=note))

    add("validity", "Input validity (essential inputs)", res.input_validity, res.globals.get("n_invalid"), "invalid",
        "Input check table", "Any INVALID → overall INCOMPLETE DATA")
    if not ok:
        for key, label, unit in [("n_inst", "PCS quantity selected (installed)", "Nos"), ("S_cap", "Installed derated PCS apparent power", "MVA"),
                                 ("P_cap", "Installed derated PCS active power", "MW"), ("S_req", "Governing PCS apparent-power requirement", "MVA"),
                                 ("P_req", "Governing PCS active-power requirement", "MW"), ("Q_sup", "Max PCS reactive supply required (OE)", "MVAr"),
                                 ("Q_abs", "Max PCS reactive absorption required (UE)", "MVAr")]:
            add(key, label, "-", None, unit)
        for key, label in STATUS_ROWS:
            add(key, label, "INCOMPLETE DATA")
        res.summary = S
        return
    R, ch, C46 = res.rows, res.globals["checks"], res.inputs.get("C46")
    vq = _num(C46)
    allv = lambda n: [R[n][c] for c in CASES]  # noqa: E731
    pmax = max(abs(x) for x in allv("P_pcs"))
    Scap, Pcap = R["S_pcs_cap"][CASES[0]], R["P_pcs_cap"][CASES[0]]
    add("n_inst", "PCS quantity selected (installed)", res.globals["n_inst"], None, "Nos", "J46:J52, J63",
        "Max of derated MVA and MW counts over 4 cases + C27")
    add("S_cap", "Installed derated PCS apparent power", Scap, None, "MVA", "J41 = J63 × C38 × J40")
    add("P_cap", "Installed derated PCS active power", Pcap, None, "MW", "J43 = J63 × C39 × J40")
    add("S_req", "Governing PCS apparent-power requirement", max(allv("S_pcs")), None, "MVA", "J31:M31")
    add("P_req", "Governing PCS active-power requirement", pmax, None, "MW", "|J29:M29|")
    add("Q_sup", "Max PCS reactive supply required (OE)", max(0.0, max(allv("Q_pcs"))), None, "MVAr", "J30:M30 (+)", "Supplied by PCS")
    add("Q_abs", "Max PCS reactive absorption required (UE)", max(0.0, -min(allv("Q_pcs"))), None, "MVAr", "J30:M30 (−)", "Absorbed by PCS")
    st_mw = "PASS" if pmax <= Pcap + EPS else "FAIL"
    add("mw", "PCS active-power capability", st_mw, pmax / Pcap, "pu", "|P| ≤ J43", "Uses entered rating/derating (C39, J36:J39, C44)")
    st_mva = "FAIL" if "FAIL" in ch["chk_mva"].values() else "PASS"
    add("mva", "PCS apparent-power (MVA) rating", st_mva, max(allv("S_pcs")) / Scap, "pu", "Row 68",
        "MVA rating only - NOT a P-Q capability check")
    pq = ch["chk_pq"].values()
    st_pq = "FAIL" if "FAIL" in pq else ("NEEDS DATA" if "VENDOR" in pq else "PASS")
    add("pq", "PCS simultaneous P–Q capability (vendor)", st_pq, None, "-", "Row 69; C46",
        "NEEDS DATA until vendor Q limit at rated P (C46) is entered. Ideal MVA circle is never used as vendor capability.")
    cap = max(allv("cap_req")) if vq else None
    reac = max(allv("reac_req")) if vq else None
    st_comp = "NEEDS DATA" if not vq else ("REQUIRED" if cap + reac > 0 else "NOT REQUIRED")
    add("comp", "Reactive compensation", st_comp, None, "-", "Rows 56, 61",
        "REQUIRED = PCS alone cannot meet Q; add compensation (C11) or PCS and re-check")
    if not vq:
        ctype = "NEEDS DATA"
    elif cap > 0 and reac > 0:
        ctype = "CAPACITOR + REACTOR"
    elif cap > 0:
        ctype = "CAPACITOR (supply MVAr)"
    elif reac > 0:
        ctype = "REACTOR (absorb MVAr)"
    else:
        ctype = "NONE"
    add("ctype", "Compensation type", ctype, None, "-", "Sign of J30 shortfall", "Capacitor for OE shortfall; reactor for UE shortfall")
    add("cap", "Capacitor requirement @ 100 % U", cap if vq else "NEEDS DATA", None, "MVAr", "J56:M56", "Referred to MV bus; shown only when C46 entered")
    add("reac", "Reactor requirement @ 100 % U", reac if vq else "NEEDS DATA", None, "MVAr", "J61:M61")
    gl = res.globals["gsu_loading"]
    st_gsu = "PASS" if gl <= 1 + EPS else "FAIL"
    add("gsu", "GSU loading (≤ 1.0 pu nameplate)", st_gsu, gl, "pu", "J5:M10, C23×C28",
        "Assumes nameplate (C23) is the allowed rating at design conditions")
    mv = ch["chk_mvt"].values()
    st_mvt = "FAIL" if "FAIL" in mv else ("NEEDS DATA" if "NEEDS DATA" in mv else "PASS")
    add("mvt", "MV transformer loading (≤ C40)", st_mvt, max(allv("mvt_loading")), "pu", "Row 70; C49",
        "NEEDS DATA until SLD transformer count C49 entered")
    st_xf = "FAIL" if "FAIL" in (st_gsu, st_mvt) else ("PASS" if st_gsu == st_mvt == "PASS" else "NEEDS DATA")
    add("xf", "Transformer capacity (overall)", st_xf, None, "-", "GSU + MVT")
    st_vmv = "FAIL" if "FAIL" in ch["chk_vmv"].values() else "SCREEN OK"
    add("vmv", "MV bus voltage screening", st_vmv, max(allv("U_mv")), "max % Un", "Row 66; C30/C31", "Single POI voltage C43, nominal taps")
    vp = ch["chk_vpcs"].values()
    st_vp = "FAIL" if "FAIL" in vp else ("NEEDS DATA" if "VENDOR" in vp else "SCREEN OK")
    add("vpcs", "PCS terminal voltage screening", st_vp, max(allv("U_lv")), "max % Un", "Row 67; C47/C48")
    st_v = "FAIL" if "FAIL" in (st_vmv, st_vp) else ("PASS (screening)" if st_vmv == st_vp == "SCREEN OK" else "LOAD-FLOW STUDY REQUIRED")
    add("volt", "Voltage compliance", st_v, None, "-", "MV + PCS screening",
        "PASS (screening) is at the entered POI voltage only; re-run C43 at the grid-code min/max and confirm by AC load flow")
    if "FAIL" in (st_mw, st_mva, st_pq, st_xf, st_v):
        overall = "NOT SUITABLE"
    elif st_mw == st_mva == st_pq == st_xf == "PASS" and st_v == "PASS (screening)":
        overall = "SUITABLE"
    else:
        overall = "INCOMPLETE DATA"
    add("overall", "OVERALL PRELIMINARY SUITABILITY", overall, None, "-", "All checks",
        "SUITABLE = passes preliminary screen only; not design approval")
    res.summary = S


STATUS_ROWS = [("mw", "PCS active-power capability"), ("mva", "PCS apparent-power (MVA) rating"),
               ("pq", "PCS simultaneous P–Q capability (vendor)"), ("comp", "Reactive compensation"), ("ctype", "Compensation type"),
               ("cap", "Capacitor requirement @ 100 % U"), ("reac", "Reactor requirement @ 100 % U"),
               ("gsu", "GSU loading (≤ 1.0 pu nameplate)"), ("mvt", "MV transformer loading (≤ C40)"),
               ("xf", "Transformer capacity (overall)"), ("vmv", "MV bus voltage screening"), ("vpcs", "PCS terminal voltage screening"),
               ("volt", "Voltage compliance"), ("overall", "OVERALL PRELIMINARY SUITABILITY")]


def summary_value(res: Result, key: str) -> Any:
    for row in res.summary:
        if row["key"] == key:
            return row["result"]
    raise KeyError(key)
