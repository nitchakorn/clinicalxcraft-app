"""Streamlit entrypoint for ClinicalxCRAFT — the hosted, shareable version.

Same static-data + Nebius core as the FastAPI app (app/dataset.py, app/tools.py,
app/agent.py): the agent queries the bundled kirc.json via in-process DuckDB. No CRAFT,
no OAuth — the only secret is NEBIUS_API_KEY.

Layout: the "Ask" agent sits at the top; the specimen-ledger dashboard fills the rest of
the screen as the main content.

Run locally:  streamlit run streamlit_app.py
"""
import os

import streamlit as st

# Seed the LLM key from Streamlit secrets when running on Streamlit Cloud (no shell env
# there). Locally, config.py already loads it from .env. Shell env still wins.
try:
    if "NEBIUS_API_KEY" in st.secrets:
        os.environ.setdefault("NEBIUS_API_KEY", st.secrets["NEBIUS_API_KEY"])
except Exception:
    pass

from app import agent, config
from app.tools import ToolExecutor

LEDGER_PATH = config.WEB_DIR / "kirc_ledger.html"

# (short chip label, full question)
QUICK_ASKS = [
    ("VHL → mTOR protein", "Do VHL-mutated tumors show higher mTOR protein than VHL-wildtype ones?"),
    ("Imaging by stage", "Which stage has the most patients with linked imaging?"),
    ("Mutations & stage", "Is there a relationship between driver-mutation count and pathologic stage?"),
    ("Purity by stage", "How does tumor purity differ across stage in this cohort?"),
]

st.set_page_config(page_title="ClinicalxCRAFT — KIRC Cohort Console", page_icon="🧬", layout="wide")

if "question" not in st.session_state:
    st.session_state["question"] = QUICK_ASKS[0][1]

# --- Ask (agent) — top of the page ---
st.markdown("##### 🧬 Ask ClinicalxCRAFT — explore the TCGA-KIRC cohort in plain English")
if not os.environ.get("NEBIUS_API_KEY"):
    st.info("The live agent needs a Nebius API key. Set NEBIUS_API_KEY in this app's Secrets to enable it.")

run_now = False

# quick-ask chips (clicking one fills the box and runs it)
chip_cols = st.columns(len(QUICK_ASKS))
for i, (label, q) in enumerate(QUICK_ASKS):
    if chip_cols[i].button(label, key=f"qa_{i}", use_container_width=True):
        st.session_state["question"] = q
        run_now = True

c_in, c_go = st.columns([6, 1])
question = c_in.text_input(
    "question",
    value=st.session_state["question"],
    label_visibility="collapsed",
    placeholder="Ask a question about the KIRC cohort…",
)
if c_go.button("Ask", type="primary", use_container_width=True):
    st.session_state["question"] = question
    run_now = True

if run_now:
    q = st.session_state["question"]
    executor = ToolExecutor()
    status = st.status(f"Investigating: {q}", expanded=True)

    def on_event(kind: str, detail: str) -> None:
        icon = {"note": "💭", "tool": "🔧", "status": "•"}.get(kind, "•")
        if kind == "note":
            status.markdown(f"💭 **{detail}**")
        else:
            status.write(f"{icon} {detail}")

    try:
        report = agent.run_investigation(executor, q, on_event=on_event)
        status.update(label="Investigation complete", state="complete")
        st.session_state["report"] = report
        st.session_state["sql_log"] = executor.sql_log
        st.session_state["notes"] = executor.notes
    except Exception as e:
        status.update(label="Investigation failed", state="error")
        st.exception(e)

if st.session_state.get("report"):
    st.markdown(st.session_state["report"])
    with st.expander(
        f'💭 Reasoning ({len(st.session_state.get("notes", []))} notes) · '
        f'SQL the agent wrote ({len(st.session_state.get("sql_log", []))})'
    ):
        for i, note in enumerate(st.session_state.get("notes", []), 1):
            st.markdown(f"{i}. {note}")
        for sql in st.session_state.get("sql_log", []):
            st.code(sql, language="sql")

st.divider()

# --- the specimen-ledger dashboard — the main, full-screen content ---
if LEDGER_PATH.exists():
    st.iframe(LEDGER_PATH, height=1500)
else:
    st.warning("Ledger file not found — expected web/kirc_ledger.html.")
