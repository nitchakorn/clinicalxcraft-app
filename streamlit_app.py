"""Streamlit entrypoint for ClinicalxCRAFT — the hosted, shareable version.

Same static-data + Nebius core as the FastAPI app (app/dataset.py, app/tools.py,
app/agent.py): the agent queries the bundled kirc.json via in-process DuckDB. No CRAFT,
no OAuth — the only secret is NEBIUS_API_KEY. Deploy to Streamlit Community Cloud by
pointing it at this file; set NEBIUS_API_KEY in the app's Secrets.

Run locally:  streamlit run streamlit_app.py
"""
import os
from pathlib import Path

import streamlit as st

# Seed the LLM key from Streamlit secrets when running on Streamlit Cloud (no shell env
# there). Locally, config.py already loads it from .env. Shell env still wins.
try:
    if "NEBIUS_API_KEY" in st.secrets:
        os.environ.setdefault("NEBIUS_API_KEY", st.secrets["NEBIUS_API_KEY"])
except Exception:
    pass  # no secrets.toml locally — fine

from app import agent, config, dataset
from app.tools import ToolExecutor

LEDGER_PATH = config.WEB_DIR / "kirc_ledger.html"

QUICK_ASKS = [
    "Do VHL-mutated tumors show higher mTOR protein than VHL-wildtype ones?",
    "Which stage has the most patients with linked imaging?",
    "Is there a relationship between driver-mutation count and pathologic stage?",
    "How does tumor purity differ across stage in this cohort?",
]

st.set_page_config(page_title="ClinicalxCRAFT — KIRC Cohort Console", page_icon="🧬", layout="wide")

st.title("🧬 ClinicalxCRAFT")
st.caption(
    "Explore the TCGA-KIRC cohort (kidney renal clear cell carcinoma, 518 patients) — then "
    "ask a question in plain English. The agent writes its own SQL against the bundled cohort "
    "data, stratifies the patients, and returns a cited, caveated answer. De-identified public "
    "research data (TCGA / IDC) — for research and education, not individual patient care."
)


@st.cache_data(show_spinner=False)
def kpis():
    cols, rows, _ = dataset.run_sql(
        "SELECT COUNT(*) AS n, "
        "SUM(CASE WHEN hasImaging THEN 1 ELSE 0 END) AS imaging, "
        "SUM(CASE WHEN len(genes) > 0 THEN 1 ELSE 0 END) AS drivers, "
        "SUM(CASE WHEN vital = 'Dead' THEN 1 ELSE 0 END) AS dead "
        "FROM kirc"
    )
    return dict(zip(cols, rows[0]))


# --- KPI row ---
k = kpis()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Patients", k["n"])
c2.metric("With linked imaging", f'{k["imaging"]}', f'{round(100*k["imaging"]/k["n"])}%')
c3.metric("Driver-mutated", f'{k["drivers"]}', f'{round(100*k["drivers"]/k["n"])}%')
c4.metric("Deceased", f'{k["dead"]}', f'{round(100*k["dead"]/k["n"])}%', delta_color="inverse")

# --- specimen ledger (the original per-patient table) ---
st.subheader("Specimen ledger")
st.caption("Per-patient clinical, driver mutations, RPPA protein, purity/ploidy, and links into the IDC imaging viewers.")
if LEDGER_PATH.exists():
    st.iframe(LEDGER_PATH, height=1150)
else:
    st.warning("Ledger file not found — expected web/kirc_ledger.html.")

st.divider()

# --- ask the agent ---
st.subheader("Ask ClinicalxCRAFT")
if not os.environ.get("NEBIUS_API_KEY"):
    st.info("The live agent needs a Nebius API key. Set NEBIUS_API_KEY in this app's Secrets to enable it.")

cols = st.columns(len(QUICK_ASKS))
for i, q in enumerate(QUICK_ASKS):
    if cols[i].button(q, key=f"qa_{i}", use_container_width=True):
        st.session_state["question"] = q

question = st.text_area(
    "Ask your own question",
    value=st.session_state.get("question", QUICK_ASKS[0]),
    height=80,
)

if st.button("🔎 Investigate", type="primary"):
    executor = ToolExecutor()
    status = st.status("Investigating…", expanded=True)

    def on_event(kind: str, detail: str) -> None:
        icon = {"note": "💭", "tool": "🔧", "status": "•"}.get(kind, "•")
        if kind == "note":
            status.markdown(f"💭 **{detail}**")
        else:
            status.write(f"{icon} {detail}")

    try:
        report = agent.run_investigation(executor, question, on_event=on_event)
        status.update(label="Investigation complete", state="complete")
        st.session_state["report"] = report
        st.session_state["sql_log"] = executor.sql_log
        st.session_state["notes"] = executor.notes
    except Exception as e:
        status.update(label="Investigation failed", state="error")
        st.exception(e)

if st.session_state.get("report"):
    st.divider()
    st.subheader("Findings")
    st.markdown(st.session_state["report"])
    with st.expander(f'💭 The model\'s reasoning ({len(st.session_state.get("notes", []))} notes)'):
        for i, note in enumerate(st.session_state.get("notes", []), 1):
            st.markdown(f"{i}. {note}")
    with st.expander(f'🔍 SQL the agent wrote ({len(st.session_state.get("sql_log", []))} queries)'):
        for sql in st.session_state.get("sql_log", []):
            st.code(sql, language="sql")

st.caption("Built with the bundled static TCGA-KIRC extract · reasoning by Nebius Token Factory · no CRAFT/OAuth.")
