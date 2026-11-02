# BESS PCS Sizing Tool (Streamlit)

A web tool for preliminary BESS PCS sizing and electrical suitability screening. It is a line-by-line Python port of the frozen Excel workbook `docs/PCS_Sizing_Tool_FINAL_FROZEN.xlsx`.

> **Preliminary screening only. This is not design approval.** Confirm all results with an AC load-flow study, vendor-certified P-Q-V-T capability data and the project single-line diagram.

## Features
- **Sign-in page:** only e-mail addresses on an allow-list (held in Streamlit secrets) can get in. An optional shared access code can be added. Users can sign out.
- **Four operating cases:** DiS-OE, DiS-UE, Cha-OE and Cha-UE.
- **Power balance:** active and reactive power from the POI through the GSU, MV collector system and MV transformers to the PCS.
- **PCS sizing:** derating, integer unit counts and simultaneous P-Q capability against vendor limits.
- **Results Summary:** PASS / FAIL / NEEDS DATA statuses, and an overall SUITABLE / NOT SUITABLE / INCOMPLETE DATA result.
- **Power Flow view:** a simplified single-line view for each case, showing P, Q, S, PF, flow direction, voltages, loading and losses.
- **Exports:** an Excel results workbook and CSV files.
- **Input sets:** save and load inputs as JSON files.
- **Tests:** regression tests check the Python engine against 20 scenarios recalculated in the Excel workbook. A UI smoke test runs in GitHub Actions.

## Repository layout
```
app.py                     Streamlit app (UI)
pcs_tool/model.py          Calculation engine (port of the PCS and Results Summary sheets)
pcs_tool/auth.py           E-mail allow-list sign-in / sign-out
pcs_tool/diagram.py        SVG power-flow view
pcs_tool/export.py         Excel / CSV / JSON export
tests/                     Regression tests against the Excel workbook, plus UI smoke tests
docs/                      Frozen reference workbook
.streamlit/config.toml     Theme
.streamlit/secrets.toml.example   Template for the access list (do not commit the real secrets.toml)
```

## Deploy on Streamlit Community Cloud
1. Push this repository to GitHub. A private repository is recommended.
2. Go to <https://share.streamlit.io>, sign in with GitHub, and choose **Create app → Deploy a public app from GitHub**.
3. Select the repository, branch `main` and main file `app.py`. Under **Advanced settings**, choose Python 3.12.
4. In **Advanced settings → Secrets**, paste:
   ```toml
   [auth]
   allowed_emails  = ["first.user@company.com", "second.user@company.com"]
   allowed_domains = []
   access_code     = ""
   ```
5. Click **Deploy**. To change who can sign in later, go to **App → Settings → Secrets**. The app picks up the new list without a redeploy.

## Run locally
```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit the e-mail list
streamlit run app.py
python -m unittest discover -s tests -v
```

## Security notes
- An e-mail allow-list controls access but does not verify identity: anyone who knows an allowed address can type it in. For stronger protection:
  - set `access_code`;
  - and/or keep the GitHub repository private and use Streamlit Cloud's **Who can view this app → Only specific people** setting;
  - or switch to Streamlit's built-in OIDC login (`st.login`) with Google or Microsoft accounts.
- Never commit `.streamlit/secrets.toml`. It is listed in `.gitignore`.

## Sign convention and key assumptions
- **Sign convention:** generator convention. P > 0 means discharge (export); Q > 0 means over-excited (MVAr supplied toward the grid).
- **Calculation method:** a sequential loss and voltage-drop calculation at one POI voltage (C43), with nominal taps and no grid impedance. It is not a converged load flow.
- **Temperature derating:** C44 = 1 assumes the PCS rating already applies at the design temperature, so temperature derating is not applied twice.
- **Vendor and SLD data (C46–C50):** may be left blank. Any check that depends on them shows NEEDS DATA and never PASS.
- **Shunt C11:** a fixed shunt connected in all four cases (+ capacitor, − reactor).
- **Cables:** cable reactance and MV cable charging are not modelled.
