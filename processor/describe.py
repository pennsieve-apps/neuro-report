"""
What a step actually did, from its own provenance.json (parameters, tools, variant) and
summary.json: the methods sentence, a run note under the step's description, and which upstream
software to acknowledge. Every statement is built from values the step recorded; when a value is
missing the sentence says less, never more.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any



def first(values) -> Any:
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


def join_and(items: list[str]) -> str:
    items = [str(i) for i in items if str(i)]
    return items[0] if len(items) == 1 else (", ".join(items[:-1]) + " and " + items[-1] if items else "")


def num_text(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(x)) if x.is_integer() else f"{x:g}"


def _p(params: dict[str, Any], key: str) -> Any:
    v = params.get(key)
    return None if v in (None, "", [], {}) else v


def _list(v: Any) -> list[str]:
    if isinstance(v, (list, tuple)):
        return [str(x).strip().lower() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip().lower() for x in re.split(r"[,;\s]+", v) if x.strip()]
    return []


def _true(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("true", "false", "1", "0", "yes", "no"):
        return v.strip().lower() in ("true", "1", "yes")
    return None


def _tool(tools: dict[str, Any], name: str) -> str:
    for k, v in tools.items():
        if k.lower() == name.lower():
            return f"{k} {v}"
    return ""


SORTERS = {"kilosort4": "Kilosort4", "kilosort": "Kilosort", "lupin": "Lupin (SpikeInterface)",
           "spykingcircus2": "SpykingCircus2 (SpikeInterface)", "tridesclous2": "Tridesclous2 (SpikeInterface)"}
EMBEDDINGS = {"pca": "PCA", "fa": "factor analysis", "gpfa": "GPFA (Elephant)", "cebra": "CEBRA"}
DECODERS = {"ridge": "ridge regression", "mlp": "a neural network (MLP)", "bayes": "a Bayesian position decoder",
            "logistic": "logistic regression for trial variables", "knn": "kNN on CEBRA embeddings",
            "rrr": "reduced-rank regression between regions"}
CHECKS = {"schema": "PyNWB schema validation", "inspector": "the NWB Inspector's best-practice checks",
          "dandi": "DANDI's upload checks"}


def _json(path: Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            v = json.load(fh)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def _per_session(folder: Path | None, sessions: dict[str, Any], name: str) -> dict[str, dict[str, Any]]:
    """<folder>/<session_id>/<name> for each session that has one (session.json, manifest.json)."""
    if folder is None:
        return {}
    out = {}
    for sid in sessions:
        got = _json(folder / sid / name)
        if got:
            out[sid] = got
    return out


def _vars(sessions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [v for s in sessions.values() if isinstance(s.get("variables"), dict)
            for v in s["variables"].values() if isinstance(v, dict)]


def evidence(app: str, sessions: dict[str, dict[str, Any]], summary: dict[str, Any], folder: Path | None,
             params: dict[str, Any]) -> dict[str, Any]:
    """What the step's outputs show it did (not what its parameters asked for)."""
    s = sessions
    ev: dict[str, Any] = {}
    if app == "ephys-prep":
        ev["session_json"] = _per_session(folder, s, "session.json")
    elif app == "spike-sort":
        ev["sorters"] = sorted({str(v["sorter"]) for v in s.values() if v.get("sorter")})
    elif app == "ephys-curate":
        ev["bombcell"] = any(isinstance(v.get("bombcell"), dict) for v in s.values())
        ev["unitrefine"] = any(isinstance(v.get("unitrefine"), dict) for v in s.values())
        merges = [v["auto_merge"] for v in s.values() if isinstance(v.get("auto_merge"), dict)]
        ev["merge_groups"] = sum(int(m.get("n_merge_groups") or 0) for m in merges) if merges else None
    elif app == "suite2p":
        ev["registered"] = any(v.get("rigid_shift_max_px") is not None for v in s.values())
        ev["nonrigid"] = any(v.get("regDX_max_px") is not None for v in s.values())
    elif app == "ophys-traces":
        ev["cascade"] = first(v.get("cascade_model") for v in s.values())
        ev["oasis"] = any(v.get("mean_oasis_event_rate_hz_accepted") is not None for v in s.values())
        ev["neuropil"] = first(v.get("neuropil_coefficient") for v in s.values())
    elif app == "ophys-activity":
        ev["rastermap"] = any(isinstance(v.get("rastermap"), dict) for v in s.values())
        ev["assemblies"] = any(v.get("n_assemblies") is not None for v in s.values())
        ev["correlations"] = any(v.get("mean_activity_correlation") is not None for v in s.values())
        ev["stim"] = first(v.get("stim_table") for v in s.values() if v.get("analysis") == "stimulus-aligned")
    elif app == "behavior-syllables":
        ev["method"] = str(summary.get("method") or "").lower()
    elif app == "neuro-align":
        ev["manifests"] = _per_session(folder, s, "manifest.json")
    elif app == "neuro-encoding":
        ev["glm"] = any(isinstance(v.get("glm"), dict) and (v["glm"].get("n_fitted") or v["glm"].get("median_d2") is not None)
                        for v in s.values())
        ev["variables"] = sorted({k for v in s.values() if isinstance(v.get("variables"), dict) for k in v["variables"]})
    elif app == "neuro-embedding":
        keys = {k for v in s.values() for k in v}
        ev["methods"] = [m for m in ("pca", "fa", "gpfa", "cebra") if any(k.startswith(m + "_") for k in keys)]
    elif app == "neuro-decoding":
        vs = _vars(s)
        has = lambda pred: any(any(pred(k) for k in v) for v in vs)  # noqa: E731
        decs = []
        if has(lambda k: k.startswith("ridge_")):
            decs.append("ridge")
        if has(lambda k: k.startswith("mlp_")):
            decs.append("mlp")
        if has(lambda k: k.startswith("bayes_")):
            decs.append("bayes")
        if has(lambda k: k == "balanced_accuracy"):
            decs.append("logistic")
        if has(lambda k: k.startswith("knn_")):
            decs.append("knn")
        if folder is not None and (folder / "rrr.csv").is_file():
            decs.append("rrr")
        ev["decoders"] = decs
        ev["null"] = has(lambda k: k == "null_p95")
        ev["regions"] = any(isinstance(v.get("regions"), dict) and v["regions"] for v in vs)
        ev["dropping"] = folder is not None and (folder / "dropping.csv").is_file()
        ev["heldout"] = bool(summary.get("heldout_session"))
    elif app == "nwb-inspect":
        ev["dandi"] = any(v.get("dandi_ready") is not None for v in s.values())
    return ev


PREP_STEPS = {"phase_shift": "channel phase-shift correction", "highpass_filter": "a {freq_min} Hz high-pass filter",
              "bandpass_filter": "a {freq_min}-{freq_max} Hz band-pass filter",
              "detect_bad_channels": "bad-channel detection ({n_bad} removed)",
              "common_reference": "common {operator} referencing", "whiten": "whitening"}


def _prep_phrase(step: dict[str, Any]) -> str:
    name = str(step.get("step") or "")
    if name in ("window", "scale_to_uV", ""):
        return ""
    tmpl = PREP_STEPS.get(name)
    if not tmpl:
        return name.replace("_", " ")
    vals = {k: num_text(v) for k, v in step.items()}
    if name == "common_reference":
        vals["operator"] = {"median": "median", "average": "average"}.get(str(step.get("operator")), str(step.get("operator") or ""))
    try:
        return tmpl.format(**vals)
    except KeyError:
        return re.sub(r"\s*\(?\{[^}]*\}\)?", "", tmpl).replace("a  ", "a ").replace("  ", " ")


def methods(app: str, params: dict[str, Any], sessions: dict[str, dict[str, Any]], tools: dict[str, Any],
            variant: str, summary: dict[str, Any], folder: Path | None = None) -> str:
    s = sessions
    ev = evidence(app, s, summary, folder, params)
    if app == "ephys-prep":
        steps: list[str] = []
        for sj in ev["session_json"].values():
            for st in sj.get("preprocessing") or []:
                ph = _prep_phrase(st) if isinstance(st, dict) else ""
                if ph and ph not in steps:
                    steps.append(ph)
        text = "Recordings were preprocessed with SpikeInterface" + (": " + join_and(steps) if steps else "")
        # "DREDge (dredge_fast), estimated only" -> "DREDge (dredge_fast)": corrected or not is said below.
        methods_ = sorted({re.sub(r",\s*(estimated only|corrected|applied)$", "", str(sj["motion_method"]))
                           for sj in ev["session_json"].values() if sj.get("motion_method")})
        estimated = any(v.get("motion_estimated") for v in s.values()) or bool(methods_)
        corrected = [k for k, v in s.items() if v.get("motion_corrected") is True]
        if estimated:
            text += ". Drift was estimated" + (f" with {'; '.join(methods_)}" if methods_ else "")
            text += (f" and corrected in {len(corrected)} of {len(s)} session{'s' if len(s) != 1 else ''}"
                     if corrected else " and not corrected by this step")
        return text
    if app == "spike-sort":
        if not ev["sorters"]:
            return "Spikes were sorted"
        parts = []
        for x in ev["sorters"]:
            version = first(v.get("sorter_version") for v in s.values() if str(v.get("sorter")) == x)
            if not version and x.lower().startswith("kilosort"):
                version = tools.get("kilosort") or ""
            parts.append(SORTERS.get(x.lower(), x) + (f" {version}" if version else ""))
        text = "Spikes were sorted with " + join_and(parts)
        if any(v.get("drift_correction_by_sorter") for v in s.values()):
            text += ", with the sorter's own drift correction"
        return text
    if app == "ephys-curate":
        parts = ["SpikeInterface quality metrics"] + (["Bombcell"] if ev["bombcell"] else []) + \
                (["UnitRefine"] if ev["unitrefine"] else [])
        text = "Units were curated with " + join_and(parts)
        if ev["merge_groups"] is not None:
            n = ev["merge_groups"]
            text += (f"; over-split units were merged automatically ({n} merge group{'s' if n != 1 else ''})" if n
                     else "; automatic merging found no over-split units, so no units were merged")
        rule = first(v.get("label_rule") for v in s.values())
        if rule:
            text += f"; final labels by the '{rule}' rule"
        return text
    if app == "suite2p":
        bits = []
        if ev["registered"]:
            bits.append("registered (" + ("rigid and non-rigid" if ev["nonrigid"] else "rigid") + ")")
        det = _p(params, "DETECTION")
        if any(v.get("n_rois") is not None for v in s.values()):
            bits.append(f"segmented into ROIs ({det} detection)" if det else "segmented into ROIs")
        if any(v.get("n_cells") is not None for v in s.values()):
            thr = _p(params, "CLASSIFIER_THRESHOLD")
            bits.append(f"classified as cells at probability ≥ {num_text(thr)}" if thr is not None else "classified")
        if not bits:
            return "Movies were processed with Suite2p"
        return "Movies were " + join_and(bits) + " with Suite2p" + (f" {tools['suite2p']}" if tools.get("suite2p") else "")
    if app == "ophys-traces":
        coef = ev["neuropil"]
        text = "Neuropil was subtracted" + (f" (coefficient {num_text(coef)})" if coef is not None else "")
        base = _p(params, "BASELINE")
        text += " and ΔF/F computed" + (f" against a {base} baseline" if base else "")
        if ev["cascade"]:
            text += f"; spike rates were inferred with CASCADE (model {ev['cascade']})"
        if ev["oasis"]:
            text += (" and" if ev["cascade"] else ";") + " events with OASIS"
        return text
    if app == "ophys-activity":
        parts = (["sorted with Rastermap"] if ev["rastermap"] else []) + \
                (["cell assemblies were detected (PCA/ICA)"] if ev["assemblies"] else []) + \
                (["pairwise correlations measured"] if ev["correlations"] else [])
        text = "Population activity was " + join_and(parts) if parts else "Population activity was summarised"
        if ev["stim"]:
            text += f"; responses were aligned to the '{ev['stim']}' stimulus table and tested for responsiveness and tuning"
        return text
    if app == "pose-estimate":
        dlc = tools.get("deeplabcut")
        text = "Body keypoints were tracked with DeepLabCut" + (f" {dlc}" if dlc else "")
        kind, model = summary.get("model_kind"), summary.get("model")
        if kind == "superanimal" and model:
            text += f" using the SuperAnimal model {model} (zero-shot)"
        elif model:
            text += f" using the model {model}"
        if any(v.get("video_adapt") is True for v in s.values()):
            text += ", adapted to each video"
        return text
    if app == "pose-kinematics":
        bits = []
        c = _p(params, "CONFIDENCE_THRESHOLD")
        if c is not None:
            bits.append(f"points below confidence {num_text(c)} dropped")
        g = _p(params, "MAX_GAP_S")
        if g is not None:
            bits.append(f"gaps up to {num_text(g)} s interpolated")
        sm = _p(params, "SMOOTHING")
        if sm and str(sm).lower() not in ("none", "off"):
            bits.append(f"{sm} smoothing")
        mv = tools.get("movement")
        text = "Pose was cleaned" + (" (" + ", ".join(bits) + ")" if bits else "")
        units = {v.get("units") for v in s.values() if v.get("units")}
        text += " and kinematics computed with movement" + (f" {mv}" if mv else "")
        return text + (" in " + join_and(sorted(units)) if units else "")
    if app == "behavior-syllables":
        method, n = ev["method"], summary.get("n_syllables")
        if method == "hmm":
            text = "Behaviour was segmented into syllables with a sticky autoregressive HMM (Dynamax)"
        elif method in ("kpms", "keypoint-moseq"):
            text = "Behaviour was segmented into syllables with keypoint-MoSeq"
        else:
            text = "Behaviour was segmented into syllables"
        return text + (f", {n} syllables" if n else "")
    if app == "neuro-align":
        kinds = sorted({str(v.get("neural_kind")) for v in s.values() if v.get("neural_kind")})
        bins = sorted({v.get("bin_size_s") for v in s.values() if v.get("bin_size_s")})
        text = "Neural activity" + (f" ({join_and(kinds)})" if kinds else "") + " and behaviour were aligned on the " \
               "session clock and binned" + (f" at {join_and([num_text(b) for b in bins])} s" if bins else "")
        if "pynapple" in {k.lower() for k in tools}:
            text += " with pynapple"
        notes = []
        for sid, man in ev["manifests"].items():
            neural = man.get("neural") or {}
            filt, dropped = neural.get("filters") or {}, neural.get("dropped") or {}
            col, acc, n_in = filt.get("label_column"), filt.get("accepted_labels"), filt.get("n_units_in_file")
            pre = f"{sid}: " if len(ev["manifests"]) > 1 else ""
            if col and dropped.get("label"):
                notes.append(f"{pre}units with {col} {'/'.join(map(str, acc or []))} were kept "
                             f"({dropped['label']} of {n_in} dropped by label)" if n_in else
                             f"{pre}units with {col} {'/'.join(map(str, acc or []))} were kept ({dropped['label']} dropped)")
            elif not col and neural.get("kind") == "units":
                notes.append(f"{pre}the file has no unit labels, so no units were dropped by label")
            if dropped.get("min_rate") and filt.get("min_rate_hz") is not None:
                notes.append(f"{pre}{dropped['min_rate']} units below {num_text(filt['min_rate_hz'])} Hz were dropped")
        return text + ("; " + "; ".join(notes) if notes else "")
    if app == "neuro-encoding":
        n = _p(params, "N_SHUFFLES")
        text = "Single-neuron tuning curves and information scores were computed" + \
               (f" for {join_and(ev['variables'])}" if ev["variables"] else "") + \
               " and tested against " + (f"{n} shuffles" if n else "shuffles")
        if ev["glm"]:
            text += "; Poisson GLMs were fitted with NeMoS" + (f" {tools['nemos']}" if tools.get("nemos") else "")
        return text
    if app == "neuro-embedding":
        meths = [EMBEDDINGS[m] for m in ev["methods"]]
        return ("Population activity was embedded with " + join_and(meths)) if meths else \
            "Population activity was embedded in a low-dimensional space"
    if app == "neuro-decoding":
        decs = [DECODERS[d] for d in ev["decoders"]]
        text = "Behaviour was decoded from population activity" + (" with " + join_and(decs) if decs else "")
        folds, shuf = _p(params, "CV_FOLDS"), _p(params, "N_SHUFFLES")
        if decs and folds:
            text += f", {folds}-fold blocked cross-validation"
        if ev["null"]:
            text += " and a circular-shift null distribution" + (f" ({shuf} shifts)" if shuf else "")
        extra = (["per brain region"] if ev["regions"] else []) + (["neuron-dropping curves"] if ev["dropping"] else []) + \
                (["held-out-session decoding"] if ev["heldout"] else [])
        return text + ("; also " + join_and(extra) if extra else "")
    if app == "nwb-inspect":
        checks = [c for c in _list(params.get("CHECKS")) if c != "dandi" or ev["dandi"]]
        return "NWB files were checked" + (" with " + join_and([CHECKS.get(c, c) for c in checks]) if checks else "")
    return f"The {app} step was run"


def run_note(app: str, params: dict[str, Any], sessions: dict[str, dict[str, Any]]) -> str:
    """One sentence on what this run did, where the description says what the step can do."""
    if app == "ephys-prep":
        notes = []
        for sid, v in sessions.items():
            dec = v.get("motion_decision")
            if dec:
                notes.append(f"{sid}: {dec}" if len(sessions) > 1 else str(dec))
        return ("In this run, drift was " + "; ".join(notes) + ".") if notes else ""
    if app == "spike-sort":
        sorters = sorted({str(v.get("sorter")) for v in sessions.values() if v.get("sorter")})
        return f"In this run the sorter was {join_and([SORTERS.get(x.lower(), x) for x in sorters])}." if sorters else ""
    return ""


# Software each app uses in every run, matched against the app's CITATION.cff software entries
# (by tool name or URL), besides the tools its provenance lists.
ALWAYS = {
    "ephys-prep": ["spikeinterface", "aind-ephys-pipeline"],
    "spike-sort": ["spikeinterface", "aind-ephys-pipeline"],
    "ephys-curate": ["spikeinterface"],
    "suite2p": ["suite2p"],
    "ophys-traces": ["oasis"],
    "pose-estimate": ["deeplabcut", "ndx-pose"],
    "pose-kinematics": ["movement"],
    "neuro-align": ["pynapple", "pynwb"],
    "neuro-encoding": ["pynapple"],
    "neuro-decoding": ["scikit-learn"],
    "nwb-inspect": ["pynwb", "nwbinspector"],
}
ALIASES = {"torch": "pytorch", "oasis-deconv": "oasis", "opencv-python-headless": "opencv", "faiss-cpu": "faiss",
           "cascadetorch": "cascadetorch", "dandi": "dandi-cli"}


def used_tools(app: str, params: dict[str, Any], sessions: dict[str, dict[str, Any]], tools: dict[str, Any],
               summary: dict[str, Any], folder: Path | None = None) -> set[str]:
    """Tool names this run used: provenance `tools`, minus those its outputs show it did not use,
    plus the app's primary tools."""
    used = {k.lower() for k in tools}
    ev = evidence(app, sessions, summary, folder, params)
    if app == "spike-sort" and not any(x.lower().startswith("kilosort") for x in ev["sorters"]):
        used -= {"kilosort", "torch"}
    if app == "neuro-embedding":
        if "cebra" not in ev["methods"]:
            used -= {"cebra", "torch"}
        if "gpfa" not in ev["methods"]:
            used -= {"elephant", "neo", "quantities"}
    if app == "neuro-encoding" and not ev["glm"]:
        used -= {"nemos", "jax", "jaxlib"}
    if app == "behavior-syllables":
        if ev["method"] == "hmm":
            used |= {"dynamax", "jax"}
            used -= {"keypoint-moseq"}
        elif ev["method"] in ("kpms", "keypoint-moseq"):
            used |= {"keypoint-moseq", "jax"}
    if app == "pose-estimate" and summary.get("model_kind") == "superanimal":
        used |= {"superanimal"}
    if app == "ephys-curate":
        if ev["unitrefine"]:
            used |= {"unitrefine"}
        else:
            used -= {"skops", "unitrefine"}
        if not ev["bombcell"]:
            used -= {"bombcell"}
    if app == "ophys-traces":
        if not ev["cascade"]:
            used -= {"cascadetorch"}
        if not ev["oasis"]:
            used -= {"oasis-deconv", "oasis"}
    if app == "ophys-activity" and not ev["rastermap"]:
        used -= {"rastermap"}
    used |= set(ALWAYS.get(app, []))
    if app == "ophys-traces" and not ev["oasis"]:
        used -= {"oasis"}
    return used | {ALIASES[k] for k in list(used) if k in ALIASES}


# Primary projects whose citation is a paper rather than a software record in the apps'
# CITATION.cff: credited (linked to that paper, from the bundled table) when the run used them.
PROJECTS = {
    "spikeinterface": ("SpikeInterface", "10.7554/elife.61834"),
    "kilosort": ("Kilosort4", "10.1038/s41592-024-02232-7"),
    "suite2p": ("Suite2p", "10.64898/2026.02.04.703741"),
    "cascadetorch": ("CASCADE", "10.1038/s41593-021-00895-5"),
    "oasis": ("OASIS", "10.1371/journal.pcbi.1005423"),
    "rastermap": ("Rastermap", "10.1038/s41593-024-01783-4"),
    "deeplabcut": ("DeepLabCut", "10.1038/s41593-018-0209-y"),
    "superanimal": ("SuperAnimal models", "10.1038/s41467-024-48792-2"),
    "dynamax": ("Dynamax", "10.21105/joss.07069"),
    "keypoint-moseq": ("keypoint-MoSeq", "10.1038/s41592-024-02318-2"),
    "pynapple": ("pynapple", "10.7554/elife.85786"),
    "cebra": ("CEBRA", "10.1038/s41586-023-06031-6"),
    "elephant": ("Elephant (GPFA)", "10.5281/zenodo.1186602"),
    "nemos": ("NeMoS", "10.5281/zenodo.17553286"),
    "pynwb": ("PyNWB", "10.7554/elife.78362"),
}


def _matches(tool: str, text: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(tool)}(?![a-z0-9])", text.lower()))


def acknowledged(software: list[dict[str, str]], used: set[str]) -> list[dict[str, str]]:
    """The app's CITATION.cff software entries this run used, plus its primary projects known by
    their paper (only DOIs in the bundled table)."""
    from processor import citations as C

    out = [sw for sw in software if any(_matches(t, sw.get("title", "") + " " + sw.get("url", "")) for t in used)]
    for tool, (name, doi) in PROJECTS.items():
        if tool in used and C.lookup(doi) and not any(_matches(tool, sw["title"]) or
                                                      _matches(name.split()[0].lower(), sw["title"]) for sw in out):
            out.append({"title": name, "url": C.doi_url(doi), "doi": doi})
    return out
