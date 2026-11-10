"""
Synthetic step outputs for the report: for each app, its top folder with provenance.json,
summary.json (sessions, figures with captions, tables, warnings), small PNG figures and CSV tables,
following conventions.md; plus a session sheet. Also used by app.yml `review.generate`.

Deliberate quirks, so the tests see the report handle them: one figure path relative to the port
folder (`<app>/...`, as some apps write), one figure listed but missing, a SpikeInterface-style
provenance.json without an `app` key inside a step folder (must be ignored), an app the report does
not know (`future-app`), and a DOI that is not in the citation table.

    python -m tests.make_fixture OUT [--layout linked|flat|both] [--apps ephys-prep,spike-sort,...]

linked: OUT/linked/steps/<app>/... and OUT/linked/metadata/sessions.csv (each port a folder);
flat: everything side by side at OUT/flat/.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mpl"))
os.environ.setdefault("MPLBACKEND", "Agg")

SESSIONS = [("sub-A01_ses-day1", "A01", "control"), ("sub-B02_ses-day1", "B02", "treated")]
UNKNOWN_DOI = "10.9999/not-in-the-table.2026"
# As pose-estimate writes it when the SuperAnimal weights were used (with links), plus a link that
# must never become one.
LICENCE_NOTICE = ("SuperAnimal model weights (Mathis lab, https://www.mackenziemathislab.org): academic, "
                  "non-commercial use only; see https://huggingface.co/mwmathis/DeepLabCutModelZoo-SuperAnimal-TopViewMouse "
                  "and https://github.com/DeepLabCut/DeepLabCut. Cite https://doi.org/10.1038/s41467-024-48792-2 and "
                  "10.1038/s41596-019-0176-0. Not a link: javascript:alert(1).")

# Citations as the real apps list them (all in processor/references.json).
CITES = {
    "ephys-prep": ["10.7554/eLife.61834", "10.7554/eLife.110170", "10.1038/s41592-025-02614-5"],
    "spike-sort": ["10.7554/eLife.61834", "10.7554/eLife.110588"],
    "ephys-curate": ["10.1101/2025.03.30.645770", "10.5281/zenodo.8172821", "10.7554/eLife.61834"],
    "suite2p": ["10.64898/2026.02.04.703741", "10.1101/061507"],
    "ophys-traces": ["10.1038/s41593-021-00895-5", "10.1371/journal.pcbi.1005423"],
    "ophys-activity": ["10.1038/s41593-024-01783-4", "10.1016/j.jneumeth.2013.04.010"],
    "pose-estimate": ["10.1038/s41593-018-0209-y", "10.1038/s41467-024-48792-2"],
    "pose-kinematics": ["10.5281/zenodo.12755724"],
    "behavior-syllables": ["10.1016/j.neuron.2015.11.031", "10.21105/joss.07069"],
    "neuro-align": ["10.7554/eLife.85786", "10.7554/eLife.78362"],
    "neuro-encoding": ["10.7554/eLife.85786", "10.5281/zenodo.17553286"],
    "neuro-embedding": ["10.1038/s41586-023-06031-6", "10.1152/jn.90941.2008"],
    "neuro-decoding": ["10.1523/ENEURO.0506-19.2020", "10.1152/jn.1998.79.2.1017"],
    "nwb-inspect": ["10.7554/eLife.78362", "10.5281/zenodo.10611726"],
    "future-app": [UNKNOWN_DOI],
}

HEADLINE = {
    "ephys-prep": {"duration_s": 60.0, "sampling_frequency": 30000.0, "n_channels": 384, "n_bad_channels": 3,
                   "max_drift_range_um": 12.5, "motion_corrected": True, "peaks_per_s": 412.3},
    "spike-sort": {"sorter": "kilosort4", "n_units": 211, "n_spikes": 154321, "median_firing_rate_hz": 3.2,
                   "n_units_above_50uV": 150, "wall_seconds": 95.0, "realtime_factor": 1.6},
    "ephys-curate": {"label_rule": "consensus", "bombcell_thresholds_note": "synthetic thresholds note",
                     "n_units": 205, "n_good": 61, "n_mua": 100, "n_noise": 44, "bombcell_unitrefine_agreement": 0.81,
                     "median_snr_good": 7.4, "bombcell": {"good": 60, "mua": 101, "noise": 44},
                     "units_by_region": {"CA1": {"good": 30, "mua": 50, "noise": 10},
                                         "DG": {"good": 31, "mua": 50, "noise": 34}}},
    "suite2p": {"n_frames": 2000, "frame_rate": 30.0, "duration_s": 66.7, "n_rois": 120, "n_cells": 87,
                "rigid_shift_max_px": 2.1},
    "ophys-traces": {"n_rois": 120, "n_accepted": 87, "indicator": "GCaMP6f", "cascade_model": "Global_EXC_30Hz",
                     "median_snr_accepted": 5.2, "mean_cascade_rate_hz_accepted": 0.8},
    "ophys-activity": {"n_rois": 87, "analysis": "stimulus-aligned", "n_trials": 40, "n_responsive": 33,
                       "fraction_responsive": 0.379, "n_tuned": 21, "n_assemblies": 4,
                       "warnings": ["only 4 trials per condition"]},
    "pose-estimate": {"n_keypoints": 8, "n_frames_analysed": 1800, "duration_analysed_s": 60.0, "mean_confidence": 0.91,
                      "fraction_low_confidence_frames": 0.04},
    "pose-kinematics": {"units": "cm", "duration_s": 60.0, "valid_fraction": 0.97, "distance_travelled": 812.4,
                        "mean_speed": 13.5, "immobile_fraction": 0.22, "center_fraction": 0.11},
    "behavior-syllables": {"n_frames": 1800, "modelled_fraction": 0.95, "n_bouts": 140},
    "neuro-align": {"neural_kind": "units", "n_neurons": 61, "bin_size_s": 0.025, "n_bins": 2400, "duration_s": 60.0},
    "neuro-encoding": {"n_neurons": 61, "n_place_cells": 17, "glm": {"median_d2": 0.04, "n_fitted": 61}},
    "neuro-embedding": {"n_neurons": 61, "pca_n_pc_80": 12, "pca_var_3pc": 0.41, "fa_n_factors": 6, "cebra_behavior_gof_bits": 0.52,
                        "knn_r2_test": {"cebra_behavior": 0.61, "cebra_shuffled": -0.05}},
    "neuro-decoding": {"n_neurons": 61, "decode_bin_s": 0.1,
                       "variables": {"position": {"ridge_r2": 0.63, "bayes_r2": 0.58, "null_p95": 0.02, "p_value": 0.005,
                                                  "unit": "cm"},
                                     "speed": {"ridge_r2": 0.21, "null_p95": 0.03, "p_value": 0.005, "unit": "cm/s"}}},
    "nwb-inspect": {"dandi_ready": True, "n_critical": 0, "n_violations": 1, "n_suggestions": 4, "nwb_version": "2.7.0",
                    "file_size_mb": 12.5},
    "future-app": {"n_widgets": 42, "score": 0.734, "label": "text is not a headline number"},
}

ALL = list(HEADLINE)

# A few real tool names and parameters, so methods and acknowledgements have something to go on.
TOOLS = {"spike-sort": {"spikeinterface": "0.105.4", "kilosort": "4.1.7", "torch": "2.15.0"},
         "neuro-embedding": {"cebra": "0.6.1", "elephant": "1.2.1", "torch": "2.15.0", "scikit-learn": "1.9.1"},
         "behavior-syllables": {"dynamax": "1.0.3", "jax": "0.12.0"}}
PARAMS = {"spike-sort": {"SORTER": "kilosort4"},
          "neuro-embedding": {"METHODS": ["pca", "fa", "cebra", "gpfa"]},
          "neuro-decoding": {"DECODERS": ["ridge", "mlp", "bayes", "rrr"], "CV_FOLDS": 5, "N_SHUFFLES": 200},
          "behavior-syllables": {"METHOD": "hmm"}}


def _png(path: Path, title: str, seed: int) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    rng = np.random.default_rng(seed)
    fig, ax = plt.subplots(figsize=(4, 2.4), dpi=60)
    ax.plot(np.cumsum(rng.normal(size=200)), lw=1)
    ax.set_title(title, fontsize=8)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def write_app(root: Path, app: str, seed: int) -> Path:
    top = root / app
    top.mkdir(parents=True, exist_ok=True)
    sessions, figures = {}, []
    for i, (sid, subj, cond) in enumerate(SESSIONS):
        s = {"status": "ok", "subject_id": subj, "condition": cond, "group": ""}
        for k, v in HEADLINE[app].items():
            s[k] = (v * (1 + 0.1 * i)) if isinstance(v, float) and k not in ("frame_rate", "sampling_frequency") else v
        if app == "pose-kinematics" and i == 1:
            s["units"] = "px"
        sessions[sid] = s
        _png(top / sid / f"{sid}_overview.png", f"{sid}: {app} overview", seed + i)
        figures.append({"path": f"{sid}/{sid}_overview.png",
                        "caption": f"{app} overview of {sid}: look at the trend (synthetic caption {i + 1})."})
    _png(top / "group_summary.png", f"{app}: all sessions", seed + 9)
    # One app writes its path relative to the port folder, as some real apps do.
    figures.append({"path": f"{app}/group_summary.png" if app == "pose-kinematics" else "group_summary.png",
                    "caption": f"{app}: all sessions compared (synthetic)."})
    if app == "ephys-curate":
        figures.append({"path": "does_not_exist.png", "caption": "A figure the app forgot to write."})
    with open(top / "sessions.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["session_id", "status", "n_items"])
        for sid, _, _ in SESSIONS:
            w.writerow([sid, "ok", 10])
    summary = {"app": app, "version": "0.1.0", "sessions": sessions, "figures": figures,
               "tables": [{"path": "sessions.csv", "caption": "One row per session."}],
               "warnings": [f"{SESSIONS[1][0]}: synthetic warning from {app}"] if app in ("ephys-prep", "neuro-align") else []}
    if app == "pose-estimate":
        summary["model_kind"] = "superanimal"
        summary["licence_notice"] = LICENCE_NOTICE
    if app == "behavior-syllables":
        summary["n_syllables"] = 6
        summary["method"] = "hmm"
        summary["syllables"] = [{"syllable": k, "usage": round(0.3 - 0.04 * k, 3), "mean_duration_s": 0.4} for k in range(6)]
    (top / "summary.json").write_text(json.dumps(summary, indent=1))
    prov = {"app": app, "version": "0.1.0", "variant": "cpu" if app in ("spike-sort", "suite2p") else "",
            "tools": {"python": "3.12.11", "numpy": "2.5.4", f"{app}-core": "1.0.0", **TOOLS.get(app, {})},
            "parameters": {"SEED": 42, "THREADS": 0, **PARAMS.get(app, {})}, "inputs": ["x"],
            "started": f"2026-11-09T1{seed % 10}:00:00Z", "finished": f"2026-11-09T1{seed % 10}:05:00Z",
            "wall_seconds": 300.0, "peak_rss_mb": 512.0,
            "gpu": {"name": "Tesla T4", "peak_vram_mb": 2100} if app == "spike-sort" else None,
            "sessions": {sid: {"status": "ok", "seconds": 150.0} for sid, _, _ in SESSIONS},
            "citations": CITES[app]}
    (top / "provenance.json").write_text(json.dumps(prov, indent=1))
    if app == "ephys-prep":
        # SpikeInterface writes its own provenance.json into saved folders: no `app` key.
        rec = top / SESSIONS[0][0] / "recording"
        rec.mkdir(parents=True, exist_ok=True)
        (rec / "provenance.json").write_text(json.dumps({"class": "BinaryFolderRecording", "kwargs": {}}))
    return top


def write_sheet(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["session_id", "path", "subject_id", "condition", "group"])
        for sid, subj, cond in SESSIONS:
            w.writerow([sid, f"{sid}.nwb", subj, cond, ""])


def make(out: Path, layout: str = "linked", apps: list[str] | None = None) -> Path:
    apps = apps or ALL
    root = out / layout
    steps = root / "steps" if layout == "linked" else root
    for i, app in enumerate(apps):
        write_app(steps, app, seed=i)
    write_sheet((root / "metadata" if layout == "linked" else root) / "sessions.csv")
    return root


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--layout", choices=["linked", "flat", "both"], default="linked")
    ap.add_argument("--apps", help="comma-separated (default: all)")
    args = ap.parse_args()
    apps = args.apps.split(",") if args.apps else None
    for layout in (["linked", "flat"] if args.layout == "both" else [args.layout]):
        print(make(args.out, layout, apps))


if __name__ == "__main__":
    main()
