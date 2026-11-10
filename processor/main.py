"""
neuro-report: one report (HTML, PDF, JSON) of whatever systems-neuroscience steps are linked in.

Reads INPUT_DIR recursively for each step's top folder (provenance.json + summary.json), and writes
OUTPUT_DIR/neuro-report/: report.html (self-contained), report.pdf, report.json, summary.json,
provenance.json and figures/workflow_overview.png.

Exit codes: 0 ok, 1 no step output found, 2 bad parameters.
"""
from __future__ import annotations

import json
import logging
import os
import resource
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("neuro-report")
APP = "neuro-report"
PARAMETERS = ("REPORT_TITLE", "MAX_FIGURES", "DATASET_DOIS", "WRITE_PDF")
OWN_CITATIONS = ["10.1109/mcse.2007.55"]  # matplotlib (the overview diagram, the PDF fonts)


class ParameterError(ValueError):
    pass


def version() -> str:
    for p in (Path(__file__).resolve().parent.parent / "VERSION", Path("/processor/VERSION")):
        if p.exists():
            return p.read_text().strip()
    return "0.0.0"


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v == "":
        return default
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    raise ParameterError(f"{name} must be true or false, got {v!r}")


def parameters() -> dict[str, Any]:
    raw = os.environ.get("MAX_FIGURES", "").strip() or "24"
    try:
        max_figures = int(raw)
    except ValueError:
        raise ParameterError(f"MAX_FIGURES must be an integer, got {raw!r}") from None
    if max_figures < 0:
        raise ParameterError("MAX_FIGURES must be >= 0")
    return {"REPORT_TITLE": os.environ.get("REPORT_TITLE", "").strip(),
            "MAX_FIGURES": max_figures,
            "DATASET_DOIS": os.environ.get("DATASET_DOIS", "").strip(),
            "WRITE_PDF": _bool("WRITE_PDF", True)}


def _scratch() -> None:
    """HOME and TMPDIR may be set to folders that don't exist yet (Lambda): make them. Caches
    that must be written (matplotlib) go under TMPDIR."""
    for var in ("TMPDIR", "HOME"):
        d = os.environ.get(var)
        if d:
            try:
                Path(d).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
    tmp = tempfile.gettempdir()
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tmp) / "mpl"))
    os.environ.setdefault("MPLBACKEND", "Agg")
    Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)


def _peak_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / (1024 * 1024) if sys.platform == "darwin" else r / 1024, 1)


def _tool_versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as v

    out = {"python": sys.version.split()[0]}
    for pkg in ("jinja2", "reportlab", "matplotlib", "pillow"):
        try:
            out[pkg] = v(pkg)
        except PackageNotFoundError:
            pass
    return out


def run(input_dir: Path, output_dir: Path, params: dict[str, Any]) -> int:
    _scratch()
    from processor import figures as F
    from processor import model as M
    from processor import render_html, render_pdf
    from processor.inputs import find_steps

    t0 = time.time()
    started = datetime.now(timezone.utc)
    steps, sheets = find_steps(input_dir)
    if not steps:
        log.error("no step output found under %s (looked for <app>/provenance.json and summary.json)", input_dir)
        return 1
    for s in steps:
        log.info("step %-20s %-40s sessions=%d figures=%d", s.app, s.rel, len(s.summary.get("sessions") or {}),
                 len(s.summary.get("figures") or []))
    log.info("session sheets: %s", ", ".join(str(p.relative_to(input_dir)) for p in sheets) or "none")

    model = M.build(steps, sheets, input_dir, params, started, version())
    n = 0
    for s in model["steps"]:
        for f in s["figures"]:
            n += 1
            f["number"] = n

    out = output_dir / APP
    (out / "figures").mkdir(parents=True, exist_ok=True)
    overview = F.overview(model["workflows"], {s["app"] for s in model["steps"]}, model["extra_apps"],
                          out / "figures" / "workflow_overview.png")
    images = render_html.load_images(model)
    render_html.write(model, overview, out / "report.html", images)
    log.info("wrote report.html (%.1f MB, %d figures)", (out / "report.html").stat().st_size / 1e6, n)
    if params["WRITE_PDF"]:
        render_pdf.write(model, overview, out / "report.pdf", images)
        log.info("wrote report.pdf (%.1f MB)", (out / "report.pdf").stat().st_size / 1e6)

    report = json.loads(json.dumps(model, default=str))
    for s in report["steps"]:
        for f in s["figures"]:
            f["path"] = f["rel"]
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    finished = datetime.now(timezone.utc)
    summary = {
        "app": APP, "version": version(),
        "sessions": {r["session_id"]: {"steps": r["steps"], **{c: r.get(c, "") for c in ("subject_id", "condition", "group")}}
                     for r in model["sessions"]},
        "workflows": [w["name"] for w in model["workflows"]],
        "n_steps": len(model["steps"]), "n_figures": n,
        "n_references": len(model["references"]),
        "n_unknown_dois": sum(1 for r in model["references"] if not r["known"]),
        "n_input_issues": len(model["issues"]),
        "figures": [{"path": "figures/workflow_overview.png",
                     "caption": "The steps of each workflow found in this report, in pipeline order; filled boxes "
                                "are included, grey dashed boxes were not linked into the report."}],
        "tables": [{"path": "report.json", "caption": "Everything the report shows, as data."}],
        "warnings": [f"{w['step']}: {w['text']}" for w in model["warnings"]],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    provenance = {
        "app": APP, "version": version(), "variant": "", "tools": _tool_versions(),
        "parameters": params,
        "inputs": [str(Path(s.rel) / "provenance.json") for s in steps] + [str(p.relative_to(input_dir)) for p in sheets],
        "started": started.isoformat().replace("+00:00", "Z"), "finished": finished.isoformat().replace("+00:00", "Z"),
        "wall_seconds": round(time.time() - t0, 1), "peak_rss_mb": _peak_rss_mb(), "gpu": None,
        "sessions": {r["session_id"]: {"status": "ok", "seconds": 0.0} for r in model["sessions"]},
        "citations": OWN_CITATIONS,
    }
    (out / "provenance.json").write_text(json.dumps(provenance, indent=1) + "\n", encoding="utf-8")
    log.info("done: %d steps, %d sessions, %d figures, %d references (%d DOI-only), %d warnings, %d input notes, "
             "%.1f s, peak %.0f MB", len(model["steps"]), len(model["sessions"]), n, len(model["references"]),
             summary["n_unknown_dois"], len(model["warnings"]), len(model["issues"]), provenance["wall_seconds"],
             provenance["peak_rss_mb"])
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    input_dir = Path(os.environ.get("INPUT_DIR") or "/data/input")
    output_dir = Path(os.environ.get("OUTPUT_DIR") or "/data/output")
    try:
        params = parameters()
    except ParameterError as exc:
        log.error("bad parameter: %s", exc)
        return 2
    if not input_dir.is_dir():
        log.error("INPUT_DIR %s does not exist", input_dir)
        return 1
    log.info("neuro-report %s: INPUT_DIR=%s OUTPUT_DIR=%s %s", version(), input_dir, output_dir,
             " ".join(f"{k}={v!r}" for k, v in params.items()))
    return run(input_dir, output_dir, params)


if __name__ == "__main__":
    sys.exit(main())
