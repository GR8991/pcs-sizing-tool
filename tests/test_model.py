"""Regression tests: the Python engine must reproduce the frozen Excel workbook.

fixtures_excel.json holds 20 input scenarios recalculated in the Excel workbook
(PCS_Sizing_Tool_FINAL_FROZEN.xlsx), including missing-data, invalid-input,
charging/discharging, PF and derating cases.
Run with:  python -m unittest discover -s tests   (or pytest)
"""
import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pcs_tool.model import CASES, calculate, default_derating, default_inputs, summary_value  # noqa: E402

FIX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures_excel.json"), encoding="utf-8"))


def _close(a, b, tol=1e-6):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=tol, abs_tol=tol)
    return a == b


class TestAgainstExcel(unittest.TestCase):
    def test_all_scenarios(self):
        for fx in FIX:
            with self.subTest(scenario=fx["name"]):
                res = calculate(fx["inputs"], fx["derating"])
                summary = [r["result"] for r in res.summary]
                excel_summary = [fx["summary"][str(r)] for r in range(5, 27)]
                for i, (a, b) in enumerate(zip(summary, excel_summary)):
                    if b in (None, "-"):
                        continue
                    self.assertTrue(_close(a, b), f"summary row {i + 5}: python={a!r} excel={b!r}")
                if res.input_validity != "OK" or not res.rows:
                    continue
                for name, per_case in fx["rows"].items():
                    for c in CASES:
                        exp = per_case[c]
                        if exp is None or (isinstance(exp, str) and exp.startswith("#")):
                            continue
                        self.assertTrue(_close(res.rows[name][c], exp), f"{name}[{c}] python={res.rows[name][c]!r} excel={exp!r}")
                for name, per_case in fx["checks"].items():
                    for c in CASES:
                        self.assertEqual(res.globals["checks"][name][c], per_case[c], f"{name}[{c}]")


class TestRules(unittest.TestCase):
    def test_default_is_incomplete(self):
        res = calculate(default_inputs(), default_derating())
        self.assertEqual(summary_value(res, "overall"), "INCOMPLETE DATA")
        self.assertEqual(res.globals["n_inst"], 87)

    def test_c39_above_c38_is_invalid(self):
        inp = default_inputs() | {"C46": 0.7, "C47": 110, "C48": 90, "C49": 22, "C39": 1.8}
        res = calculate(inp, default_derating())
        self.assertEqual(res.input_validity, "INVALID INPUTS")
        self.assertEqual(summary_value(res, "overall"), "INCOMPLETE DATA")

    def test_suitable_needs_all_data(self):
        inp = default_inputs() | {"C46": 0.7, "C47": 110, "C48": 90, "C49": 22}
        self.assertEqual(summary_value(calculate(inp, default_derating()), "overall"), "SUITABLE")
        for blank in ("C46", "C47", "C49"):
            res = calculate(inp | {blank: None}, default_derating())
            self.assertNotEqual(summary_value(res, "overall"), "SUITABLE", blank)

    def test_signs_four_quadrants(self):
        res = calculate(default_inputs(), default_derating())
        P, Q = res.rows["P_poi"], res.rows["Q_poi"]
        self.assertTrue(P["DiS-OE"] > 0 and Q["DiS-OE"] > 0)
        self.assertTrue(P["DiS-UE"] > 0 and Q["DiS-UE"] < 0)
        self.assertTrue(P["Cha-OE"] < 0 and Q["Cha-OE"] > 0)
        self.assertTrue(P["Cha-UE"] < 0 and Q["Cha-UE"] < 0)

    def test_blank_essential_input_never_passes(self):
        res = calculate(default_inputs() | {"C14": None}, default_derating())
        self.assertEqual(summary_value(res, "overall"), "INCOMPLETE DATA")
        self.assertTrue(all(r["result"] in ("INCOMPLETE DATA", "-", "INVALID INPUTS") for r in res.summary))


if __name__ == "__main__":
    unittest.main()
