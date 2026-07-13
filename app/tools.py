"""The model's tools, and the executor that runs them. Fully synchronous.

v2 has four tools instead of v1's nine: the CRAFT schema-discovery + NL2SQL + paging dance
collapses to a single documented table the model queries directly. `web_search` is carried
over unchanged (Wikipedia, no key). Side effects (notes, SQL log, collected rows) accumulate
on the executor for the live trace and the API response.
"""
import json
import re

import httpx

from . import dataset


def _tool(name: str, description: str, parameters: dict) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


TOOL_DEFINITIONS = [
    _tool(
        "note",
        "Record your current reasoning for the user to see live: the hypothesis you're about "
        "to test, what a result implies, or why you're pivoting. Call this BEFORE each "
        "investigative step. It does not query anything.",
        {
            "type": "object",
            "properties": {"thought": {"type": "string", "description": "Your reasoning, stated specifically."}},
            "required": ["thought"],
        },
    ),
    _tool(
        "get_schema",
        "Read the `kirc` table's columns, types, and coverage notes. Call this once before "
        "writing any SQL. Takes no arguments.",
        {"type": "object", "properties": {}},
    ),
    _tool(
        "run_sql",
        "Run a read-only DuckDB SELECT/WITH query against the `kirc` table. Returns columns "
        "and rows (values as-is; the genes column is a list). Test gene membership with "
        "list_contains(genes,'VHL'). A single statement only.",
        {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "A single read-only SELECT/WITH statement."}},
            "required": ["sql"],
        },
    ),
    _tool(
        "web_search",
        "Search Wikipedia for real-world biological/clinical background — gene function, "
        "disease mechanism, published context. Returns titles, snippets, and a summary with a "
        "source URL. Grounding only, not a substitute for the cohort's data; cite the source "
        "(title + URL) when you use a result.",
        {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to look up, e.g. 'VHL gene kidney cancer'."}},
            "required": ["query"],
        },
    ),
]


class ToolExecutor:
    """Dispatches one tool call and captures side effects. Reused across a single ask."""

    def __init__(self):
        self.notes: list[str] = []
        self.sql_log: list[str] = []
        self.collected: list[dict] = []

    def run(self, name: str, args: dict) -> str:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return f"ERROR: unknown tool '{name}'"
        try:
            return handler(args)
        except Exception as e:  # surface to the model so it can adapt
            return f"ERROR: {type(e).__name__}: {e}"

    def _tool_note(self, args: dict) -> str:
        self.notes.append(args.get("thought", ""))
        return "noted"

    def _tool_get_schema(self, args: dict) -> str:
        return dataset.schema_doc()

    def _tool_run_sql(self, args: dict) -> str:
        sql = args["sql"]
        columns, rows, truncated = dataset.run_sql(sql)
        self.sql_log.append(sql)
        self.collected.append({"sql": sql, "columns": columns, "rows": rows})
        payload = {"columns": columns, "rows": rows}
        if truncated:
            payload["note"] = f"result truncated to {len(rows)} rows; add aggregation or a LIMIT"
        return json.dumps(payload, default=str)

    def _tool_web_search(self, args: dict) -> str:
        """Wikipedia-backed grounding — no API key. Browser-shaped UA + contact per Wikimedia
        bot policy (a default UA gets 403'd)."""
        query = args["query"]
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ClinicalxCRAFT/2.0; +mailto:nitchakorn@alum.mit.edu)"
        }
        with httpx.Client(timeout=10.0, headers=headers) as client:
            resp = client.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": query, "srlimit": 5, "format": "json"},
            )
            resp.raise_for_status()
            hits = resp.json().get("query", {}).get("search", [])
            if not hits:
                return json.dumps({"query": query, "results": []})
            results = []
            for h in hits:
                title = h["title"]
                results.append(
                    {
                        "title": title,
                        "snippet": _strip_html(h.get("snippet", "")),
                        "url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
                    }
                )
            try:
                top = results[0]["title"].replace(" ", "_")
                summary = client.get("https://en.wikipedia.org/api/rest_v1/page/summary/" + top)
                if summary.status_code == 200:
                    extract = summary.json().get("extract")
                    if extract:
                        results[0]["summary"] = extract
            except Exception:
                pass
        return json.dumps({"query": query, "source": "Wikipedia", "results": results})


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def summarize_input(name: str, args: dict) -> str:
    """Short human-readable preview of a tool call for the live trace."""
    if name == "run_sql":
        sql = " ".join((args.get("sql") or "").split())
        return sql if len(sql) <= 110 else sql[:107] + "..."
    if name == "web_search":
        return args.get("query", "")
    if name == "get_schema":
        return "reading table schema"
    return ""
