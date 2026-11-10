#!/usr/bin/env python3
"""
Run the report on the demo workflows' real step outputs, the way the platform links them: each
step's top folder side by side in the `steps` port (symlinks), the demo's sessions.csv in the
`metadata` port. Writes <work>/<demo>/neuro-report/ (or under --out).

    python scripts/run_demos.py --data ~/code/pennsieve/workflow-systems-neuroscience/data
    python scripts/run_demos.py --data ... --demo ibl --out data/demos
"""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor import main as app  # noqa: E402

DEMOS = {
    "ibl": ["ephys-prep", "spike-sort", "ephys-curate", "neuro-align", "neuro-encoding", "neuro-embedding",
            "neuro-decoding", "nwb-inspect"],
    "ground-truth": ["ephys-prep", "spike-sort", "ephys-curate", "nwb-inspect"],
    "allen-2p": ["suite2p", "ophys-traces", "ophys-activity", "nwb-inspect"],
    "openfield-5xfad": ["pose-estimate", "pose-kinematics", "behavior-syllables", "nwb-inspect"],
    "grosmark": ["neuro-align", "neuro-encoding", "neuro-embedding", "neuro-decoding", "nwb-inspect"],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True, help="workflow-systems-neuroscience/data")
    ap.add_argument("--demo", action="append", choices=sorted(DEMOS), help="default: all")
    ap.add_argument("--out", type=Path, help="write <out>/<demo>/neuro-report/ instead of data/work/<demo>/")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    worst = 0
    for demo in args.demo or list(DEMOS):
        work = args.data / "work" / demo
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp)
            (inp / "steps").mkdir()
            linked = []
            for a in DEMOS[demo]:
                if (work / a / "provenance.json").exists() or (work / a / "summary.json").exists():
                    (inp / "steps" / a).symlink_to((work / a).resolve())
                    linked.append(a)
            sheet = args.data / demo / "sessions.csv"
            if sheet.exists():
                (inp / "metadata").mkdir()
                (inp / "metadata" / "sessions.csv").symlink_to(sheet.resolve())
            out = (args.out / demo) if args.out else work
            print(f"=== {demo}: {', '.join(linked)} -> {out / 'neuro-report'}")
            params = {"REPORT_TITLE": "", "MAX_FIGURES": 24, "DATASET_DOIS": "", "WRITE_PDF": True}
            worst = max(worst, app.run(inp, out, params))
    return worst


if __name__ == "__main__":
    sys.exit(main())
