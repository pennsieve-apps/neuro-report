"""
Figures: the report's own workflow overview diagram (matplotlib), and the upstream PNGs, read
once and, when wider than MAX_WIDTH_PX, downscaled so the HTML and PDF stay a sensible size.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("neuro-report")

MAX_WIDTH_PX = 1600

PRESENT = "#2563a8"
PRESENT_TEXT = "#ffffff"
ABSENT = "#e8ebef"
ABSENT_TEXT = "#6b7280"
REPORT = "#14532d"


def load_png(path: Path, max_width: int = MAX_WIDTH_PX) -> tuple[bytes, int, int] | None:
    """PNG bytes (downscaled when wider than max_width) and the pixel size; None if unreadable."""
    from PIL import Image

    try:
        with Image.open(path) as im:
            im.load()
            w, h = im.size
            if w > max_width or im.format != "PNG":
                if w > max_width:
                    h = round(h * max_width / w)
                    w = max_width
                    im = im.resize((w, h), Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format="PNG", optimize=True)
                return buf.getvalue(), w, h
        return path.read_bytes(), w, h
    except Exception as exc:  # noqa: BLE001 - a broken figure must not stop the report
        log.warning("cannot read figure %s: %s", path, exc)
        return None


def overview(workflows: list[dict[str, Any]], present: set[str], extra: list[str], path: Path) -> Path:
    """One row per detected workflow: its steps as boxes (filled when their output is in the
    report, grey when not linked), arrows in pipeline order, ending in the report."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    box_w, box_h, gap_x, gap_y = 1.55, 0.5, 0.38, 0.3
    rows = []
    for w in workflows:
        rows.append(("title", w["name"]))
        rows.append(("chain", w["chain"]))
    if extra:
        rows.append(("title", "Also linked"))
        rows.append(("extra", [list(extra)]))

    def stage_height(stage: list[str]) -> float:
        return len(stage) * box_h + (len(stage) - 1) * 0.12

    heights = []
    for kind, val in rows:
        heights.append(0.45 if kind == "title" else max(stage_height(s) for s in val) + gap_y)
    max_stages = max([len(v) + 1 for k, v in rows if k == "chain"] + [2])
    width = max_stages * box_w + (max_stages - 1) * gap_x + 0.2
    height = sum(heights) + 0.1
    fig = plt.figure(figsize=(max(width, 6.0), height), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, max(width, 6.0))
    ax.set_ylim(0, height)
    ax.axis("off")

    y = height - 0.05
    for (kind, val), hgt in zip(rows, heights):
        if kind == "title":
            ax.text(0.1, y - 0.28, val, fontsize=12, fontweight="bold", color="#111827", va="center")
            y -= hgt
            continue
        stages = list(val) + ([["neuro-report"]] if kind == "chain" else [])
        centre = y - hgt / 2 + gap_y / 2
        prev_right = None
        for i, stage in enumerate(stages):
            x0 = 0.1 + i * (box_w + gap_x)
            sh = stage_height(stage)
            top = centre + sh / 2
            for j, app in enumerate(stage):
                by = top - box_h - j * (box_h + 0.12)
                is_report = app == "neuro-report"
                on = app in present or is_report
                face = REPORT if is_report else (PRESENT if on else ABSENT)
                ax.add_patch(FancyBboxPatch((x0, by), box_w, box_h, boxstyle="round,pad=0,rounding_size=0.08",
                                            facecolor=face, edgecolor=face if on else "#9ca3af",
                                            linestyle="-" if on else (0, (3, 2)), linewidth=1.0))
                ax.text(x0 + box_w / 2, by + box_h / 2, app, ha="center", va="center", fontsize=10.5,
                        color=PRESENT_TEXT if on else ABSENT_TEXT, fontweight="bold" if on else "normal")
            if prev_right is not None:
                ax.annotate("", xy=(x0 - 0.04, centre), xytext=(prev_right + 0.04, centre),
                            arrowprops=dict(arrowstyle="-|>", color="#6b7280", lw=1.2))
            prev_right = x0 + box_w
        y -= hgt
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)
    return path
