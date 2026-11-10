"""
The report as data: every section of the page and the PDF is built from this model, and
report.json is this model without the images. Nothing here interprets results beyond what the
steps wrote: numbers, captions and warnings are copied from each step's summary.json and
provenance.json; the only text the report adds is its built-in description of each known app.
"""
from __future__ import annotations

import csv
import math
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from processor import apps as A
from processor import citations as C
from processor.inputs import Step

SUMMARY_KEYS = {"app", "version", "sessions", "figures", "tables", "warnings"}
COMMON_TOOLS = {"python", "numpy", "scipy", "pandas", "matplotlib", "h5py", "hdmf", "pyarrow", "scikit-learn",
                "pillow", "numba", "jinja2", "plotly", "torch", "jax", "jaxlib", "probeinterface", "neo", "pynwb"}
INLINE_TABLE_ROWS = 15
INLINE_TABLE_COLS = 9
NESTED_ROWS = 30
NESTED_COLS = 9
DETAIL_SESSIONS = 3
# A Python format field left in a caption, e.g. '{names[0]}' or '{b - a}'.
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]{}]*\])?(?:\s*[-+*/]\s*[A-Za-z0-9_]+)*\}")


# ----------------------------------------------------------------------------- formatting

def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else float(v)
    if isinstance(v, str) and re.fullmatch(r"\s*-?\d+(\.\d+)?([eE][-+]?\d+)?\s*", v):
        return float(v)
    return None


def fmt(v: Any, kind: str = "auto") -> str:
    """A number as a person reads it: integers with thousands separators, others to 3 significant
    digits; fractions as percentages when the format says so."""
    if v is None or v == "":
        return "–"
    if isinstance(v, bool) or (kind == "bool" and str(v).lower() in ("true", "false")):
        return "yes" if (v is True or str(v).lower() == "true") else "no"
    x = _num(v)
    if kind == "text" or x is None:
        if isinstance(v, (list, tuple)):
            return ", ".join(fmt(i) for i in v) if len(v) <= 8 else f"{len(v)} values"
        if isinstance(v, float) and math.isnan(v):
            return "–"
        return str(v)
    if kind == "pct":
        return f"{x * 100:.1f} %"
    if x.is_integer() and abs(x) < 1e15 and (kind == "int" or not isinstance(v, float)):
        return f"{int(x):,}"
    ax = abs(x)
    if ax == 0:
        return "0"
    if ax >= 1000:
        return f"{x:,.0f}"
    if ax >= 0.001:
        s = f"{x:.3g}"
        return s
    return f"{x:.2e}"


def _get(d: dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _scalar(v: Any) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def _humanise(key: str) -> str:
    k = key.replace("_", " ").strip()
    return k[:1].upper() + k[1:]


# ----------------------------------------------------------------------------- per-step pieces

def _resolve(step: Step, rel: str, input_dir: Path) -> tuple[Path | None, str]:
    """A path from summary.json, relative to the app's top folder (what most apps write) or to
    the port folder above it (`<app>/...`, what some write). Returns (path, how)."""
    p = PurePosixPath(str(rel))
    if p.is_absolute() or ".." in p.parts:
        return None, "unsafe"
    cand = step.folder / p
    if cand.is_file():
        return cand, "app"
    if len(p.parts) > 1 and p.parts[0] in (step.folder.name, step.app):
        cand = step.folder.joinpath(*p.parts[1:])
        if cand.is_file():
            return cand, "port"
    return None, "missing"


def _read_csv(path: Path) -> tuple[list[str], list[list[str]], int] | None:
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    if not rows:
        return [], [], 0
    return rows[0], rows[1:INLINE_TABLE_ROWS + 1], len(rows) - 1


def _headline(app: str, sessions: dict[str, dict[str, Any]]) -> list[tuple[str, str, str]]:
    spec = A.APPS.get(app, {}).get("headline")
    if spec:
        return [h for h in spec if any(_get(s, h[1]) is not None for s in sessions.values())]
    # Unknown app: the numeric and yes/no values the sessions report, in their order.
    keys: list[str] = []
    for s in sessions.values():
        for k, v in s.items():
            if k in A.SHEET_COLUMNS or k in keys or k in ("status", "seconds"):
                continue
            if isinstance(v, bool) or (_num(v) is not None and not isinstance(v, str)):
                keys.append(k)
    return [(_humanise(k), k, "auto") for k in keys[:10]]


def _nested_table(name: str, val: Any) -> dict[str, Any] | None:
    """A dict of dicts, or a list of dicts, with scalar values: a small table."""
    rows: list[tuple[str, dict[str, Any]]] = []
    if isinstance(val, dict) and val and all(isinstance(v, dict) for v in val.values()):
        rows = [(str(k), v) for k, v in val.items()]
    elif isinstance(val, list) and val and all(isinstance(v, dict) for v in val):
        rows = [("", v) for v in val]
    else:
        return None
    cols: list[str] = []
    for _, r in rows:
        for k, v in r.items():
            if _scalar(v) and k not in cols:
                cols.append(k)
    if not cols:
        return None
    cols = cols[:NESTED_COLS]
    keyed = any(k for k, _ in rows)
    header = ([""] if keyed else []) + [_humanise(c) for c in cols]
    body = [([k] if keyed else []) + [fmt(r.get(c)) for c in cols] for k, r in rows[:NESTED_ROWS]]
    return {"name": _humanise(name), "header": header, "rows": body, "n_rows": len(rows),
            "truncated": len(rows) > NESTED_ROWS}


def _kv_line(val: dict[str, Any]) -> str | None:
    if not isinstance(val, dict) or not val or not all(_scalar(v) for v in val.values()):
        return None
    return "; ".join(f"{k}: {fmt(v)}" for k, v in val.items())


def _warnings(step: Step) -> list[str]:
    out: list[str] = []
    for w in step.summary.get("warnings") or []:
        out.append(w if isinstance(w, str) else "; ".join(f"{k}: {v}" for k, v in w.items()) if isinstance(w, dict) else str(w))
    for sid, s in (step.summary.get("sessions") or {}).items():
        if not isinstance(s, dict):
            continue
        for w in s.get("warnings") or []:
            text = w if isinstance(w, str) else str(w)
            if not any(text in o for o in out):
                out.append(f"{sid}: {text}")
        status = s.get("status")
        if status and status not in ("ok", "success"):
            out.append(f"{sid}: status {status}" + (f" ({s.get('error')})" if s.get("error") else ""))
    for sid, s in (step.provenance.get("sessions") or {}).items():
        if isinstance(s, dict) and s.get("status") not in (None, "ok", "success"):
            msg = f"{sid}: status {s.get('status')}" + (f" ({s.get('error')})" if s.get("error") else "")
            if msg not in out and not any(o.startswith(f"{sid}: status") for o in out):
                out.append(msg)
    return out


def _template(text: str, values: dict[str, Any]) -> str:
    def sub(m: re.Match) -> str:
        v = values.get(m.group(1))
        return str(v) if v not in (None, "") else m.group(0)
    out = re.sub(r"\{(\w+)\}", sub, text)
    return re.sub(r"\s*\{\w+\}", "", out)


def build_step(step: Step, input_dir: Path, max_figures: int, issues: list[dict[str, str]]) -> dict[str, Any]:
    app, summ, prov = step.app, step.summary, step.provenance
    info = A.APPS.get(app, {})
    sessions = {k: v for k, v in (summ.get("sessions") or {}).items() if isinstance(v, dict)}
    if summ and not isinstance(summ.get("sessions"), dict):
        step.problems.append("summary.json has no `sessions` object")

    def issue(msg: str) -> None:
        issues.append({"app": step.label, "folder": step.rel, "problem": msg})

    for p in step.problems:
        issue(p)
    if prov:
        for key in ("version", "tools", "parameters", "started", "finished", "wall_seconds", "peak_rss_mb",
                    "sessions", "citations"):
            if key not in prov:
                issue(f"provenance.json has no `{key}`")
        if "citations" in prov and not prov.get("citations"):
            issue("provenance.json `citations` is empty")
    if summ and prov and summ.get("version") and prov.get("version") and summ["version"] != prov["version"]:
        issue(f"summary.json version {summ['version']} differs from provenance.json version {prov['version']}")

    # Headline numbers per session.
    units = next((s.get("units") for s in sessions.values() if s.get("units")), None) or "px"
    cols = _headline(app, sessions)
    sheet = [c for c in A.SHEET_COLUMNS if any(str(s.get(c) or "").strip() for s in sessions.values())]
    header = ["Session"] + [_humanise(c).replace("Subject id", "Subject") for c in sheet] + \
             [label.replace("{units}", str(units)) for label, _, _ in cols]
    rows = []
    for sid, s in sessions.items():
        rows.append([sid] + [fmt(s.get(c), "text") for c in sheet] + [fmt(_get(s, key), kind) for _, key, kind in cols])
    for sid, s in sessions.items():
        for _, key, kind in cols:
            v = _get(s, key)
            if kind in ("int", "num", "pct") and isinstance(v, str) and _num(v) is not None:
                issue(f"summary.json sessions.{sid}.{key} is a string ({v!r}), not a number")
                break

    # Session details (nested values) for the first few sessions.
    used = {key.split(".")[0] for _, key, _ in cols}
    details = []
    for sid, s in list(sessions.items())[:DETAIL_SESSIONS]:
        lines, tables = [], []
        for k, v in s.items():
            if k in used or k in A.SHEET_COLUMNS or k == "warnings":
                continue
            t = _nested_table(k, v)
            if t:
                tables.append(t)
                continue
            line = _kv_line(v)
            if line:
                lines.append((_humanise(k), line))
        if lines or tables:
            details.append({"session": sid, "lines": lines, "tables": tables})

    # Overall values (top level of summary.json, outside the contract keys).
    overall, overall_tables = [], []
    for k, v in summ.items():
        if k in SUMMARY_KEYS:
            continue
        if _scalar(v):
            if v not in (None, ""):
                overall.append((_humanise(k), fmt(v)))
        else:
            t = _nested_table(k, v)
            if t:
                overall_tables.append(t)
            else:
                line = _kv_line(v)
                if line:
                    overall.append((_humanise(k), line))

    # Figures, in the order the step listed them, with its captions.
    figures, missing, port_relative = [], [], 0
    placeholders: dict[str, list[str]] = {}
    listed = summ.get("figures") or []
    for f in listed:
        if isinstance(f, str):
            f = {"path": f}
        if not isinstance(f, dict) or not f.get("path"):
            issue(f"figures entry is not {{path, caption}}: {f!r}")
            continue
        path, how = _resolve(step, f["path"], input_dir)
        caption = (f.get("caption") or f.get("description") or "").strip()
        if not caption:
            issue(f"figure {f['path']} has no caption")
        elif PLACEHOLDER.search(caption):
            placeholders.setdefault(", ".join(PLACEHOLDER.findall(caption)), []).append(f["path"])
        if path is None:
            missing.append(f["path"])
            issue(f"figure {f['path']} is listed but not in the output")
            continue
        if how == "port":
            port_relative += 1
        figures.append({"path": str(path), "rel": f["path"], "caption": caption})
    for ph, paths in placeholders.items():
        issue(f"{len(paths)} figure caption(s) contain an unformatted placeholder ({ph}), e.g. {paths[0]}")
    if port_relative:
        issue(f"{port_relative} figure path(s) are relative to the port folder ('{step.folder.name}/...'), "
              "most apps write them relative to the app's top folder")
    shown, omitted = figures[:max_figures], figures[max_figures:]

    # Tables the step wrote.
    tables = []
    for t in summ.get("tables") or []:
        if isinstance(t, str):
            t = {"path": t}
        if not isinstance(t, dict) or not t.get("path"):
            continue
        path, _ = _resolve(step, t["path"], input_dir)
        entry = {"rel": t["path"], "caption": (t.get("caption") or t.get("description") or "").strip(),
                 "exists": path is not None, "n_rows": None, "inline": None}
        if path is None:
            issue(f"table {t['path']} is listed but not in the output")
        elif path.suffix.lower() == ".csv":
            got = _read_csv(path)
            if got:
                head, body, n = got
                entry["n_rows"] = n
                if 0 < n <= INLINE_TABLE_ROWS and len(head) <= INLINE_TABLE_COLS:
                    entry["inline"] = {"header": head, "rows": [[fmt(c) for c in r] for r in body]}
        tables.append(entry)

    tools = prov.get("tools") or {}
    gpu = prov.get("gpu")
    gpu_text = ""
    if isinstance(gpu, dict) and gpu.get("name"):
        gpu_text = gpu["name"] + (f", peak {fmt(gpu.get('peak_vram_mb'))} MB VRAM" if gpu.get("peak_vram_mb") else "")
    elif isinstance(gpu, str) and gpu:
        gpu_text = gpu
    first = next(iter(sessions.values()), {})
    params = prov.get("parameters") or {}
    tmpl_values = {**{k.lower(): v for k, v in params.items()}, **{k: v for k, v in first.items() if _scalar(v)}}
    main_tools = [f"{k} {v}" for k, v in tools.items() if k.lower() not in COMMON_TOOLS][:4]

    return {
        "app": app, "label": step.label, "folder": step.rel, "known": app in A.APPS,
        "title": info.get("title", step.label) if step.label == app else f"{info.get('title', app)} — {step.label}",
        "about": info.get("about", ""),
        "methods": _template(info.get("methods", f"The {app} step was run"), tmpl_values),
        "version": prov.get("version") or summ.get("version") or "",
        "variant": prov.get("variant") or summ.get("variant") or "",
        "tools": tools, "main_tools": main_tools,
        "parameters": params,
        "started": prov.get("started") or "", "finished": prov.get("finished") or "",
        "wall_seconds": prov.get("wall_seconds"), "peak_rss_mb": prov.get("peak_rss_mb"), "gpu": gpu_text,
        "citations": [C.norm(d) for d in prov.get("citations") or [] if d],
        "n_sessions": len(sessions),
        "session_header": header, "session_rows": rows,
        "transpose": len(sessions) <= 3,
        "details": details, "overall": overall, "overall_tables": overall_tables,
        "figures": shown, "omitted_figures": [f["rel"] for f in omitted], "missing_figures": missing,
        "tables": tables, "warnings": _warnings(step),
        # A step may key its sessions by file (nwb-inspect) and name the session inside.
        "session_ids": list(dict.fromkeys(str(v.get("session_id")) if isinstance(v.get("session_id"), str) and v.get("session_id")
                                          else k for k, v in sessions.items())),
    }


# ----------------------------------------------------------------------------- the whole report

def _when(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _sheet_rows(sheets: list[Path]) -> list[dict[str, str]]:
    rows = []
    for s in sheets:
        try:
            with open(s, encoding="utf-8", newline="") as fh:
                rows.extend(csv.DictReader(fh))
        except (OSError, UnicodeDecodeError, csv.Error):
            continue
    return rows


def build(steps: list[Step], sheets: list[Path], input_dir: Path, params: dict[str, Any], now: datetime,
          version: str) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    built = [build_step(s, input_dir, params["MAX_FIGURES"], issues)
             for s in sorted(steps, key=lambda s: (A.order_key(s.app), s.label))]
    present = {s["app"] for s in built}
    workflows = A.detect_workflows(present)
    in_chain = {a for w in workflows for stage in w["chain"] for a in stage}
    extra = sorted((present - in_chain), key=A.order_key)

    # References: numbered in order of first citation, step by step.
    numbers: dict[str, int] = {}
    references: list[dict[str, Any]] = []
    warnings: list[str] = []

    def cite(doi: str) -> int:
        d = C.norm(doi)
        if d not in numbers:
            numbers[d] = len(references) + 1
            e = C.entry(d)
            e["n"] = numbers[d]
            references.append(e)
            if not e["known"]:
                warnings.append(f"DOI {d} is not in the report's citation table; it is listed DOI-only")
        return numbers[d]

    for s in built:
        s["refs"] = sorted({cite(d) for d in s["citations"]})

    # Datasets: the demo datasets recognised by session id, DATASET_DOIS, and dataset columns of
    # the session sheet. They are cited too.
    sheet = _sheet_rows(sheets)
    session_ids = sorted({sid for s in built for sid in s["session_ids"]} | {r.get("session_id", "") for r in sheet} - {""})
    datasets: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_dataset(doi: str, how: str, licence: str = "", paper: str | None = None, dandiset: str = "") -> None:
        d = C.norm(doi)
        if not d or d in seen:
            return
        seen.add(d)
        rec = C.lookup(d)
        e = C.entry(d)
        datasets.append({"doi": d, "url": e["url"], "known": e["known"], "title": e["title"] or d,
                         "creators": e["authors"], "year": e["year"], "licence": licence, "how": how,
                         "dandiset": dandiset, "publisher": (rec or {}).get("publisher", ""),
                         "n": cite(d), "paper": cite(paper) if paper else None})

    for d in A.demo_datasets(session_ids):
        add_dataset(d["doi"], "recognised from the session ids", d["licence"], d["paper"], d["dandiset"])
    for d in re.split(r"[\s,;]+", params.get("DATASET_DOIS") or ""):
        if d:
            add_dataset(d, "DATASET_DOIS parameter")
    for r in sheet:
        for col in ("dataset_doi", "doi"):
            if r.get(col):
                add_dataset(r[col], "session sheet")
    dandisets = sorted({str(r.get("dandiset") or "").strip() for r in sheet} - {""} - {d["dandiset"] for d in datasets})

    # Sessions across steps.
    by_session: dict[str, dict[str, Any]] = {}
    for s in built:
        for sid in s["session_ids"]:
            by_session.setdefault(sid, {"session_id": sid, "steps": []})["steps"].append(s["label"])
    meta = {r.get("session_id"): r for r in sheet if r.get("session_id")}
    for sid, row in by_session.items():
        for c in A.SHEET_COLUMNS:
            val = (meta.get(sid) or {}).get(c)
            if not val:
                for st in steps:
                    ss = st.summary.get("sessions") if isinstance(st.summary.get("sessions"), dict) else {}
                    for k, v in ss.items():
                        if isinstance(v, dict) and (k == sid or v.get("session_id") == sid) and v.get(c):
                            val = v[c]
                            break
                    if val:
                        break
            row[c] = str(val or "")

    starts = [t for t in (_when(s["started"]) for s in built) if t]
    ends = [t for t in (_when(s["finished"]) for s in built) if t]
    names = [w["name"] for w in workflows] or ["Systems neuroscience analysis"]
    for i, s in enumerate(built, 1):
        s["index"] = i
    if params.get("REPORT_TITLE"):
        title, subtitle = params["REPORT_TITLE"], " · ".join(names)
    else:
        title = "Analysis report: " + " + ".join(names)
        subtitle = "Pennsieve systems neuroscience workflows"

    all_warnings = [{"step": s["label"], "text": w} for s in built for w in s["warnings"]]
    for s in built:
        if s["missing_figures"]:
            all_warnings.append({"step": s["label"], "text": f"{len(s['missing_figures'])} figure(s) listed in "
                                 "summary.json are missing from the output and are not shown"})
    for w in warnings:
        all_warnings.append({"step": "neuro-report", "text": w})

    acknowledgements = []
    for s in built:
        sw = C.software_of(s["app"])
        if sw:
            acknowledgements.append({"app": s["app"], "software": sw})
    seen_ack: set[str] = set()
    acknowledgements = [a for a in acknowledgements if not (a["app"] in seen_ack or seen_ack.add(a["app"]))]

    apps_cited = []
    for s in built:
        info = C.app_info(s["app"])
        repo = info.get("repository") or ""
        if s["app"] not in [a["app"] for a in apps_cited]:
            apps_cited.append({"app": s["app"], "version": s["version"], "repository": repo,
                               "license": info.get("license", "")})

    return {
        "title": title, "subtitle": subtitle,
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "generated_iso": now.isoformat().replace("+00:00", "Z"),
        "run_window": [min(starts).strftime("%Y-%m-%d %H:%M UTC") if starts else "",
                       max(ends).strftime("%Y-%m-%d %H:%M UTC") if ends else ""],
        "workflows": [{"key": w["key"], "name": w["name"], "chain": w["chain"],
                       "steps": [[{"app": a, "present": a in present} for a in stage] for stage in w["chain"]]}
                      for w in workflows],
        "extra_apps": extra,
        "steps": built,
        "sessions": list(by_session.values()),
        "datasets": datasets, "dandisets": dandisets,
        "references": references,
        "warnings": all_warnings,
        "issues": issues,
        "acknowledgements": acknowledgements,
        "apps_cited": apps_cited,
        "version": version,
        "parameters": {k: v for k, v in params.items()},
    }
