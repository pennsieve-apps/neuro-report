#!/usr/bin/env python3
"""
Build the report's bundled citation table, processor/references.json, from the CITATION.cff files
of the sibling apps (and this repo's own).

Every sibling's CITATION.cff has been checked against Crossref / DataCite / PubMed by
workflow-systems-neuroscience/scripts/verify-citations.py, so the full author lists, titles,
journals and PMIDs come from already-verified records: nothing here is typed by hand. The report
resolves the DOIs each step lists in provenance.json `citations` against this table; a DOI that is
not in it is shown DOI-only with a warning, never filled in.

Run it whenever a sibling's CITATION.cff changes, then commit the result:

    python scripts/build_citations.py            # siblings next to this repo (../<app>)
    python scripts/build_citations.py --root ~/code/pennsieve

Needs: pyyaml.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent.parent
SIBLINGS = ["ephys-prep", "spike-sort", "ephys-curate", "suite2p", "ophys-traces", "ophys-activity",
            "pose-estimate", "pose-kinematics", "behavior-syllables", "neuro-align", "neuro-encoding",
            "neuro-embedding", "neuro-decoding", "nwb-inspect"]
OUT = HERE / "processor" / "references.json"


def _authors(ref: dict) -> list[dict]:
    out = []
    for a in ref.get("authors") or []:
        if a.get("name"):
            out.append({"name": str(a["name"])})
        else:
            out.append({k: str(v) for k, v in (("family", a.get("family-names")), ("given", a.get("given-names")),
                                               ("particle", a.get("name-particle"))) if v})
    return out


def _pmid(ref: dict) -> str:
    for ident in ref.get("identifiers") or []:
        desc = str(ident.get("description", "")).lower()
        val = str(ident.get("value", ""))
        if ident.get("type") == "other" and val.isdigit() and ("pubmed" in desc or not desc):
            return val
    return ""


def _record(ref: dict) -> dict:
    journal = ref.get("journal") or (ref.get("conference") or {}).get("name") or ""
    publisher = ref.get("publisher")
    if isinstance(publisher, dict):
        publisher = publisher.get("name")
    start, end = ref.get("start"), ref.get("end")
    pages = f"{start}-{end}" if start and end else str(start or "")
    return {
        "doi": str(ref.get("doi") or ""),
        "type": ref.get("type") or "generic",
        "title": str(ref.get("title") or "").strip(),
        "authors": _authors(ref),
        "journal": str(journal or ""),
        "publisher": str(publisher or ""),
        "year": ref.get("year") or (str(ref.get("date-released") or "")[:4] or None),
        "volume": str(ref.get("volume") or ""),
        "issue": str(ref.get("issue") or ""),
        "pages": pages,
        "pmid": _pmid(ref),
        "url": str(ref.get("url") or ""),
        "repository": str(ref.get("repository-code") or ""),
        "version": str(ref.get("version") or ""),
        "license": str(ref.get("license") or ""),
    }


def _score(r: dict) -> int:
    return sum(1 for k in ("journal", "volume", "pages", "pmid", "year", "issue") if r.get(k)) + len(r["authors"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=HERE.parent, help="folder holding the sibling repos")
    args = ap.parse_args()

    by_doi: dict[str, dict] = {}
    software: dict[str, list[dict]] = {}
    apps: dict[str, dict] = {}
    problems: list[str] = []
    sources = [(name, args.root / name / "CITATION.cff") for name in SIBLINGS] + [("neuro-report", HERE / "CITATION.cff")]
    for app, path in sources:
        if not path.exists():
            problems.append(f"{app}: no CITATION.cff at {path}")
            continue
        cff = yaml.safe_load(path.read_text(encoding="utf-8"))
        apps[app] = {"title": cff.get("title") or app, "repository": cff.get("repository-code") or "",
                     "license": cff.get("license") or "",
                     "authors": [a.get("name") or f"{a.get('given-names', '')} {a.get('family-names', '')}".strip()
                                 for a in cff.get("authors") or []]}
        for ref in cff.get("references") or []:
            rec = _record(ref)
            doi = rec["doi"].lower()
            if doi:
                old = by_doi.get(doi)
                if old is None:
                    rec["cited_by"] = [app]
                    by_doi[doi] = rec
                else:
                    old["cited_by"].append(app)
                    if old["title"].lower().rstrip(".") != rec["title"].lower().rstrip("."):
                        problems.append(f"{doi}: title differs between {old['cited_by'][0]} and {app}")
                    if _score(rec) > _score(old):
                        rec["cited_by"] = old["cited_by"]
                        by_doi[doi] = rec
            if rec["type"] == "software":
                # Upstream projects, for the Acknowledgements (with or without a DOI).
                entry = {"title": rec["title"], "url": rec["repository"] or rec["url"] or
                         (f"https://doi.org/{rec['doi']}" if rec["doi"] else ""), "doi": rec["doi"]}
                if entry not in software.setdefault(app, []):
                    software[app].append(entry)

    table = {"_about": "Built by scripts/build_citations.py from the sibling apps' CITATION.cff files "
                       "(verified against Crossref/DataCite/PubMed). Do not edit by hand.",
             "apps": apps, "software": software,
             "references": dict(sorted(by_doi.items()))}
    OUT.write_text(json.dumps(table, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE)}: {len(by_doi)} DOIs from {len(apps)} CITATION.cff files")
    for p in problems:
        print("WARNING:", p, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
