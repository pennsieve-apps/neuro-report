"""
The HTML report: one self-contained file (inline CSS, figures embedded as data: URIs, no scripts,
no external resources), readable offline and shareable as is.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from processor.figures import load_png
from processor.model import fmt

TEMPLATES = Path(__file__).parent / "templates"


def duration(s: Any) -> str:
    try:
        s = float(s)
    except (TypeError, ValueError):
        return "–"
    if s < 90:
        return f"{s:.0f} s"
    if s < 5400:
        return f"{s / 60:.1f} min"
    return f"{s / 3600:.1f} h"


def mb(v: Any) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "–"
    return f"{v / 1024:.1f} GB" if v >= 1024 else f"{v:.0f} MB"


def refs(ns: list[int]) -> str:
    """[1, 2, 3, 5] -> [1-3, 5]"""
    ns = sorted(set(int(n) for n in ns))
    if not ns:
        return ""
    parts, start, prev = [], ns[0], ns[0]
    for n in ns[1:] + [None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        parts.append(f"{start}–{prev}" if prev > start + 1 else (f"{start}, {prev}" if prev == start + 1 else f"{start}"))
        if n is not None:
            start = prev = n
    return "[" + ", ".join(parts) + "]"


def plain(v: Any) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def environment() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html", "j2"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters.update(duration=duration, mb=mb, refs=refs, plain=plain, num=fmt)
    return env


def data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def write(model: dict[str, Any], overview_png: Path | None, path: Path,
          images: dict[str, tuple[bytes, int, int]]) -> Path:
    for s in model["steps"]:
        for f in s["figures"]:
            got = images.get(f["path"])
            f["src"] = data_uri(got[0]) if got else ""
    sessions = model["sessions"]
    html = environment().get_template("report.html.j2").render(
        m=model,
        overview=data_uri(overview_png.read_bytes()) if overview_png and overview_png.exists() else "",
        has_subject=any(r.get("subject_id") for r in sessions),
        has_condition=any(r.get("condition") for r in sessions),
        has_group=any(r.get("group") for r in sessions))
    for s in model["steps"]:
        for f in s["figures"]:
            f.pop("src", None)
    path.write_text(html, encoding="utf-8")
    return path


def load_images(model: dict[str, Any]) -> dict[str, tuple[bytes, int, int]]:
    out = {}
    for s in model["steps"]:
        for f in s["figures"]:
            got = load_png(Path(f["path"]))
            if got:
                out[f["path"]] = got
    return out
