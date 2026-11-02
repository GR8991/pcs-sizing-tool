"""End-to-end UI smoke tests with Streamlit's AppTest (run in CI; skipped if Streamlit is not installed)."""
import os
import unittest

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # pragma: no cover
    AppTest = None

APP = os.path.join(os.path.dirname(__file__), "..", "app.py")


def _app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.secrets["auth"] = {"allowed_emails": ["engineer@example.com"], "allowed_domains": [], "access_code": ""}
    return at


@unittest.skipIf(AppTest is None, "streamlit not installed")
class TestApp(unittest.TestCase):
    def _login(self, email):
        at = _app().run()
        self.assertFalse(at.exception, at.exception)
        at.text_input[0].input(email)
        at.button[0].click().run()
        return at

    def test_denied(self):
        at = self._login("someone@else.com")
        self.assertFalse(at.exception)
        self.assertTrue(any("Access denied" in e.value for e in at.error))
        self.assertEqual(len(at.tabs), 0)

    def test_login_results_and_signout(self):
        at = self._login("Engineer@Example.com")
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(len(at.tabs), 6)
        md = " ".join(m.value for m in at.markdown)
        self.assertIn("INCOMPLETE DATA", md)
        self.assertIn("engineer@example.com", md)
        # enter vendor / SLD data -> SUITABLE
        for key, val in {"in_C46": 0.7, "in_C47": 110.0, "in_C48": 90.0, "in_C49": 22}.items():
            at.number_input(key=key).set_value(val)
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("pill ok\">SUITABLE<", " ".join(m.value for m in at.markdown))
        # C39 > C38 must not be SUITABLE
        at.number_input(key="in_C39").set_value(1.8)
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any("C39" in e.value for e in at.error))
        # sign out returns to the login page
        [b for b in at.button if b.label == "Sign out"][0].click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.tabs), 0)


if __name__ == "__main__":
    unittest.main()
