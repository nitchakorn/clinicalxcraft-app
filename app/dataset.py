"""The data plane: the bundled static KIRC extract, queried in-process with DuckDB.

This is the whole point of v2 — no CRAFT, no OAuth, no remote warehouse. The 518-patient
table lives in data/kirc.json and is loaded once into an in-memory DuckDB connection. The
agent's `run_sql` tool runs read-only SELECTs against it. Cloners need zero credentials to
run this; only the optional live agent needs an LLM key.
"""
import threading

import duckdb

from . import config

_lock = threading.Lock()
_con: duckdb.DuckDBPyConnection | None = None


def _connection() -> duckdb.DuckDBPyConnection:
    """Lazily build the in-memory connection with the `kirc` table loaded from JSON."""
    global _con
    if _con is None:
        path = str(config.DATA_PATH).replace("\\", "/")  # DuckDB wants forward slashes
        con = duckdb.connect(database=":memory:")
        con.execute(f"CREATE TABLE kirc AS SELECT * FROM read_json_auto('{path}')")
        _con = con
    return _con


# The single source of truth handed to the model via get_schema(). One documented table
# means the model can write SQL directly — no NL2SQL service needed.
SCHEMA_DOC = """Table `kirc` — one row per patient (n=518), the TCGA-KIRC cohort
(kidney renal clear cell carcinoma). This is DuckDB SQL. Read-only; SELECT/WITH only.

Columns:
- barcode       TEXT     TCGA patient barcode, e.g. 'TCGA-3Z-A93Z'
- age           INTEGER  age at diagnosis (years)
- sex           TEXT     'Male' | 'Female'
- vital         TEXT     'Alive' | 'Dead'
- stage         TEXT     'Stage I' | 'Stage II' | 'Stage III' | 'Stage IV' | 'Unstaged'
- days          DOUBLE   days to death or last follow-up (survival proxy); may be NULL
- hasImaging    BOOLEAN  true if CT + pathology imaging is linked in IDC
- genes         TEXT[]   driver genes mutated in this patient, a subset of
                         {VHL, PBRM1, SETD2, BAP1, KDM5C, MTOR}. Empty list = no driver hit.
                         Test membership with list_contains(genes, 'VHL').
                         Count drivers with len(genes).
- pten          DOUBLE   PTEN RPPA protein z-score (may be NULL)
- akt           DOUBLE   AKT_pS473 RPPA protein z-score (may be NULL)
- mtorProtein   DOUBLE   MTOR_pS2448 RPPA protein z-score (may be NULL)
- purity        DOUBLE   ABSOLUTE tumor purity, 0-1 (may be NULL)
- ploidy        DOUBLE   ABSOLUTE ploidy (may be NULL)
- doublings     INTEGER  whole-genome doublings (may be NULL)

Coverage (verify with COUNT if precision matters): 268/518 carry >=1 driver (VHL most
common); protein 451/518; purity 330/518; imaging 112/518.

Examples:
  SELECT stage, COUNT(*) FROM kirc GROUP BY stage ORDER BY stage;
  SELECT list_contains(genes,'VHL') AS vhl, AVG(mtorProtein) AS mean_mtor, COUNT(*) AS n
  FROM kirc WHERE mtorProtein IS NOT NULL GROUP BY vhl;
"""


def schema_doc() -> str:
    return SCHEMA_DOC


def count() -> int:
    with _lock:
        return _connection().execute("SELECT COUNT(*) FROM kirc").fetchone()[0]


def run_sql(sql: str, max_rows: int = config.MAX_SQL_ROWS):
    """Run one read-only query. Returns (columns, rows, truncated).

    Guardrails: a single SELECT/WITH statement only — no DDL/DML, no multiple statements.
    This is a research tool over a public de-identified extract, but there's no reason to
    let the model mutate the in-memory table.
    """
    stmt = sql.strip().rstrip(";").strip()
    lowered = stmt.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("Only read-only SELECT/WITH queries are allowed.")
    if ";" in stmt:
        raise ValueError("Only a single statement is allowed (remove any ';').")

    with _lock:
        cur = _connection().execute(stmt)
        columns = [d[0] for d in cur.description]
        fetched = cur.fetchmany(max_rows + 1)

    truncated = len(fetched) > max_rows
    rows = [list(r) for r in fetched[:max_rows]]
    return columns, rows, truncated
