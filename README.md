---
title: ClinicalxCRAFT
emoji: 🧬
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# ClinicalxCRAFT v2

A cohort console for clinicians who don't code SQL. Explore the TCGA **KIRC** cohort
(kidney renal clear cell carcinoma, 518 patients) by clicking — and ask it questions in
plain language, answered by an LLM agent that writes SQL for you.

This is the restructured successor to the v1 Streamlit app. Same idea, cleaner bones:

- **Static viewer, zero credentials.** The dashboard — KPIs, driver-gene and stage charts,
  the PTEN→mTOR scatter, and the per-patient specimen ledger with linked IDC imaging — is a
  single self-contained page (`web/index.html`). The cohort data is baked in. Open it and it
  works, no key, no backend.
- **Optional live agent.** A small FastAPI backend adds an "Ask" endpoint. The agent reads
  the table schema, writes read-only DuckDB SQL against the bundled cohort, and returns a
  cited answer with its reasoning trace. This is the only part that needs an LLM key.
- **Clone and run.** No OAuth, no remote warehouse, no short-lived tokens — the v1 pain
  points are gone. The data plane is a local file queried in-process with DuckDB.

## Try it

**Just want to look?** Download this repo (green **Code** button → **Download ZIP**), unzip,
and open `web/index.html` in your browser. The full dashboard — charts, filters, and the
patient-by-patient ledger — works with zero setup. The "Ask" box shows demo answers in this
mode.

**Want the live AI agent** that answers your own plain-English questions? It needs Python and
a Nebius API key — see [Run it](#run-it) below; it's three commands.

> Looking for the simplest thing to hand a colleague — one file, nothing to install? See the
> companion repo **[clinicalxcraft-viewer](https://github.com/nitchakorn/clinicalxcraft-viewer)**.

## Layout

```
clinicalxcraft-v2/
├── app/            FastAPI backend
│   ├── main.py       routes: GET / (viewer), /api/health, /api/schema, POST /api/ask
│   ├── agent.py      the synchronous investigation loop (Nebius / Nemotron)
│   ├── tools.py      4 tools: note, get_schema, run_sql (DuckDB), web_search (Wikipedia)
│   ├── dataset.py    loads data/kirc.json into in-memory DuckDB; read-only run_sql
│   ├── prompts.py    system prompt
│   └── config.py     endpoint, model, paths
├── data/
│   ├── kirc.json         baked 518-patient extract (one row per patient)
│   └── build_dataset.py  provenance / validation for the extract
└── web/
    └── index.html    the console (self-contained: inline CSS/JS + embedded data)
```

## Run it

```bash
# 1. install (a venv is recommended)
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

# 2. (optional) enable the live agent
copy .env.example .env            # then paste your Nebius Token Factory key into NEBIUS_API_KEY

# 3. start
uvicorn app.main:app --reload     # then open http://127.0.0.1:8000
```

Without a key, everything works except the live "Ask" agent — the Ask box falls back to
canned demo answers, and the pill in that panel tells you which mode you're in.

Just want to look at the dashboard? Open `web/index.html` directly in a browser — no Python
needed.

## The data

`data/kirc.json` is a pre-joined static extract of the TCGA-KIRC cohort: clinical fields,
the six KIRC driver-gene mutations (VHL, PBRM1, SETD2, BAP1, KDM5C, MTOR), RPPA protein
z-scores (PTEN, AKT, mTOR), ABSOLUTE tumor purity/ploidy, and IDC imaging viewer links. It
is de-identified public research data (TCGA) — for retrospective research and hypothesis
generation, not individual patient care. See `data/build_dataset.py` for the record shape
and how to refresh it from public NCI sources (ISB-CGC / IDC).

## The agent

Backed by Nebius Token Factory (`nvidia/nemotron-3-super-120b-a12b`), an OpenAI-compatible
endpoint. The agent gets four tools and sequences them itself: `note` (narrate its
reasoning, shown live), `get_schema` (read the one documented table), `run_sql` (query it),
and `web_search` (Wikipedia grounding). It writes SQL directly — there's one well-documented
table, so no NL-to-SQL service is needed.
