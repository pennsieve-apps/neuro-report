"""
The bundled citation table (processor/references.json, built by scripts/build_citations.py from
the sibling apps' verified CITATION.cff files) and how references are written in the report.

A DOI that is not in the table is never filled in: it is listed DOI-only, with a warning.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

TABLE = Path(__file__).parent / "references.json"


@lru_cache(maxsize=1)
def table() -> dict[str, Any]:
    with open(TABLE, encoding="utf-8") as fh:
        return json.load(fh)


def norm(doi: str) -> str:
    d = str(doi or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if d.lower().startswith(prefix):
            d = d[len(prefix):]
    return d.strip().lower()


DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s\"'<>]+$")


def valid(doi: str) -> bool:
    return bool(DOI_RE.match(norm(doi)))


def doi_url(doi: str) -> str:
    """https://doi.org/<doi> for a well-formed DOI, else empty (never a link to anything else)."""
    d = norm(doi)
    return "https://doi.org/" + quote(d, safe="/:;()._-") if valid(d) else ""


def lookup(doi: str) -> dict[str, Any] | None:
    return table()["references"].get(norm(doi))


def _initials(given: str) -> str:
    parts = given.replace(".", " ").replace("-", " -").split()
    return "".join(p[0] if not p.startswith("-") else "-" + p[1:2] for p in parts if p)


def author_text(a: dict[str, str]) -> str:
    if a.get("name"):
        return a["name"]
    family = ((a.get("particle") + " ") if a.get("particle") else "") + a.get("family", "")
    ini = _initials(a.get("given", ""))
    return f"{family} {ini}".strip()


def authors_text(authors: list[dict[str, str]]) -> str:
    """The full author list, Vancouver style (Family AB, Family CD)."""
    return ", ".join(author_text(a) for a in authors)


def first_author(authors: list[dict[str, str]]) -> str:
    if not authors:
        return ""
    a = authors[0]
    name = a.get("name") or (((a.get("particle") + " ") if a.get("particle") else "") + a.get("family", ""))
    return name + (" et al." if len(authors) > 2 else (f" & {authors[1].get('name') or authors[1].get('family', '')}"
                                                         if len(authors) == 2 else ""))


def entry(doi: str) -> dict[str, Any]:
    """A reference ready to print: {doi, url, known, authors, title, where, kind, short}."""
    d = norm(doi)
    rec = lookup(d)
    url = doi_url(d)
    if rec is None:
        return {"doi": d, "url": url, "known": False, "authors": "", "title": "", "where": "", "kind": "unknown",
                "short": d, "year": ""}
    kind = rec.get("type") or "article"
    year = str(rec.get("year") or "")
    if kind == "data":
        where = "Dataset. " + (rec.get("publisher") or "") + (f" {year}" if year else "")
    elif kind == "software":
        where = "Software. " + (rec.get("publisher") or "") + (f" {year}" if year else "")
    else:
        journal = rec.get("journal") or rec.get("publisher") or ""
        vol = rec.get("volume") or ""
        pages = rec.get("pages") or ""
        if vol:
            loc = vol + (f"({rec['issue']})" if rec.get("issue") else "") + (f":{pages}" if pages else "")
        else:
            loc = pages
        where = f"{journal} {year}" + (f";{loc}" if loc else "")
    where = where.strip().rstrip(".") + "."
    if rec.get("pmid"):
        where += f" PMID {rec['pmid']}."
    return {"doi": rec.get("doi") or d, "url": url, "known": True, "authors": authors_text(rec.get("authors") or []),
            "title": rec.get("title", "").rstrip("."), "where": where.strip(), "kind": kind,
            "short": f"{first_author(rec.get('authors') or [])} {year}".strip(), "year": year}


def software_of(app: str) -> list[dict[str, str]]:
    """The upstream software an app's CITATION.cff lists (title, url), for the Acknowledgements."""
    return list(table().get("software", {}).get(app, []))


def app_info(app: str) -> dict[str, Any]:
    return dict(table().get("apps", {}).get(app, {}))
