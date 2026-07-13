"""Provenance / rebuild script for data/kirc.json.

The bundled kirc.json is a pre-joined static extract of the TCGA-KIRC cohort (518 patients),
originally assembled from four public source tables (clinical, somatic mutations, RPPA
protein, ABSOLUTE purity/ploidy) plus IDC imaging links. This script documents the shape
and lets you regenerate/refresh the extract from those sources.

The current kirc.json was produced by the v1 join (`join_kirc_all.py`) and copied in as-is.
To re-source from public NCI data, point the loaders below at the open-access ISB-CGC
BigQuery tables and IDC, then re-run. Kept as a stub so the provenance is in the repo, not
just in someone's memory.
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "kirc.json"

# Expected per-patient record shape (one row per patient):
FIELDS = [
    "barcode", "age", "sex", "vital", "stage", "days", "hasImaging",
    "ctViewer", "smViewer", "genes", "pten", "akt", "mtorProtein",
    "purity", "ploidy", "doublings",
]


def validate(records: list[dict]) -> None:
    assert records, "no records"
    missing = set(FIELDS) - set(records[0].keys())
    if missing:
        raise SystemExit(f"record is missing expected fields: {sorted(missing)}")
    print(f"OK — {len(records)} records, fields present: {sorted(records[0].keys())}")


if __name__ == "__main__":
    # The shipped extract is already built; this just validates it in place.
    with open(OUT, encoding="utf-8") as f:
        records = json.load(f)
    validate(records)
