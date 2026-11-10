"""
Find the step outputs under INPUT_DIR.

Every app writes into one top folder named after it, holding provenance.json (with an `app`
key) and summary.json (conventions.md). Steps are found by those files, recursively and
following symlinks (INPUT_DIR entries are symlinks), wherever the ports put them: one folder per
port (`steps/<app>/...`), several links side by side, or everything merged at the root. Other
files called provenance.json (SpikeInterface writes one into every saved folder) have no `app`
key and are ignored, as is anything inside a step's top folder.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("neuro-report")

SKIP_SUFFIXES = (".zarr", ".nwb")  # folder formats: never descend into them
MAX_DEPTH = 8


@dataclass
class Step:
    app: str
    folder: Path              # the app's top folder
    rel: str                  # folder relative to INPUT_DIR, for messages
    provenance: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)   # contract problems found while reading

    @property
    def label(self) -> str:
        """`<app>` or `<app>/<label>` when the app ran more than once (LABEL level)."""
        parts = Path(self.rel).parts
        if self.app in parts:
            i = len(parts) - 1 - list(reversed(parts)).index(self.app)
            rest = parts[i + 1:]
            if rest:
                return "/".join((self.app,) + rest)
        return self.app


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError) as exc:
        log.warning("cannot read %s: %s", path, exc)
        return None


def find_steps(input_dir: Path) -> tuple[list[Step], list[Path]]:
    """Steps (one per app top folder) and candidate session sheets (sessions.csv outside any step)."""
    steps: list[Step] = []
    sheets: list[Path] = []
    seen: set[tuple[int, int]] = set()
    stack = [(input_dir, 0)]
    while stack:
        d, depth = stack.pop()
        try:
            st = d.stat()
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            continue
        if (st.st_dev, st.st_ino) in seen:
            continue
        seen.add((st.st_dev, st.st_ino))
        files = {e.name: Path(e.path) for e in entries if e.is_file()}
        prov = _read_json(files["provenance.json"]) if "provenance.json" in files else None
        summ = _read_json(files["summary.json"]) if "summary.json" in files else None
        app = (prov or {}).get("app") if isinstance((prov or {}).get("app"), str) else None
        if not app and summ and isinstance(summ.get("app"), str) and isinstance(summ.get("sessions"), dict):
            app = summ["app"]
        if app:
            if app == "neuro-report":
                continue  # a previous report linked back in
            rel = str(d.relative_to(input_dir)) if d != input_dir else "."
            step = Step(app=app, folder=d, rel=rel, provenance=prov or {}, summary=summ or {})
            if prov is None:
                step.problems.append("no provenance.json in the app's top folder")
            elif prov.get("app") != app:
                step.problems.append(f"provenance.json app is {prov.get('app')!r}, summary.json says {app!r}")
            if summ is None:
                step.problems.append("no summary.json in the app's top folder")
            if d.name != app and app not in Path(rel).parts:
                step.problems.append(f"top folder is named {d.name!r}, not after the app")
            steps.append(step)
            continue  # everything below belongs to this step
        if "sessions.csv" in files:
            sheets.append(files["sessions.csv"])
        if depth < MAX_DEPTH:
            for e in reversed(entries):
                if e.is_dir() and not e.name.startswith(".") and not e.name.endswith(SKIP_SUFFIXES):
                    stack.append((Path(e.path), depth + 1))
    steps.sort(key=lambda s: s.rel)
    return steps, sheets
