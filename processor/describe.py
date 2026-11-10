"""
What a step actually did, from its own provenance.json (parameters, tools, variant) and
summary.json: the methods sentence, a run note under the step's description, and which upstream
software to acknowledge. Every statement is built from values the step recorded; when a value is
missing the sentence says less, never more.
"""
from __future__ import annotations

import re
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


def methods(app: str, params: dict[str, Any], sessions: dict[str, dict[str, Any]], tools: dict[str, Any],
            variant: str, summary: dict[str, Any]) -> str:
    s = sessions
    if app == "ephys-prep":
        steps = []
        if str(_p(params, "PHASE_SHIFT") or "").lower() not in ("", "off", "false", "none"):
            steps.append("channel phase-shift correction")
        f = str(_p(params, "FILTER") or "").lower()
        lo, hi = _p(params, "FREQ_MIN"), _p(params, "FREQ_MAX")
        if f == "highpass" and lo:
            steps.append(f"a {num_text(lo)} Hz high-pass filter")
        elif f == "bandpass" and lo and hi:
            steps.append(f"a {num_text(lo)}-{num_text(hi)} Hz band-pass filter")
        elif f:
            steps.append(f"filtering ({f})")
        if str(_p(params, "BAD_CHANNELS") or "").lower() not in ("", "off", "none", "false"):
            steps.append(f"bad-channel detection ({params['BAD_CHANNELS']})")
        ref = str(_p(params, "REFERENCE") or "").lower()
        if ref in ("cmr", "car"):
            steps.append("common " + ("median" if ref == "cmr" else "average") + " referencing")
        elif ref and ref not in ("none", "off"):
            steps.append(f"re-referencing ({ref})")
        text = "Recordings were preprocessed with SpikeInterface" + (": " + join_and(steps) if steps else "")
        estimated = any(v.get("motion_estimated") for v in s.values())
        corrected = [k for k, v in s.items() if v.get("motion_corrected") is True]
        if estimated:
            preset = _p(params, "MOTION_PRESET")
            text += f". Drift was estimated ({preset})" if preset else ". Drift was estimated"
            if corrected:
                text += f" and corrected in {len(corrected)} of {len(s)} session{'s' if len(s) != 1 else ''}"
            else:
                thr = _p(params, "MOTION_THRESHOLD_UM")
                text += " and not corrected" + (f" (largest drift at most the {num_text(thr)} µm threshold, or "
                                                 "correction left to the sorter)" if thr else "")
        return text
    if app == "spike-sort":
        sorter = first(v.get("sorter") for v in s.values()) or _p(params, "SORTER")
        if not sorter:
            return "Spikes were sorted"
        name = SORTERS.get(str(sorter).lower(), str(sorter))
        version = first(v.get("sorter_version") for v in s.values())
        if not version and str(sorter).lower().startswith("kilosort"):
            version = (tools.get("kilosort") or "")
        text = f"Spikes were sorted with {name}" + (f" {version}" if version else "")
        if any(v.get("drift_correction_by_sorter") for v in s.values()):
            text += ", with the sorter's own drift correction"
        return text
    if app == "ephys-curate":
        parts = ["SpikeInterface quality metrics"]
        if "bombcell" in {k.lower() for k in tools} or any("bombcell" in v for v in s.values()):
            parts.append("Bombcell")
        if _true(params.get("UNITREFINE")) is not False and any("unitrefine" in v for v in s.values()):
            parts.append("UnitRefine")
        text = "Units were curated with " + join_and(parts)
        if _true(params.get("AUTO_MERGE")):
            merged = sum((v.get("auto_merge") or {}).get("n_merge_groups", 0) or 0 for v in s.values())
            text += f"; over-split units were merged automatically ({merged} merge group{'s' if merged != 1 else ''})"
        rule = _p(params, "LABEL_RULE") or first(v.get("label_rule") for v in s.values())
        if rule:
            text += f"; final labels by the '{rule}' rule"
        return text
    if app == "suite2p":
        bits = []
        if _true(params.get("DO_REGISTRATION")) is not False:
            nr = _true(params.get("NONRIGID"))
            bits.append("registered (" + ("rigid and non-rigid" if nr else "rigid") + ")" if nr is not None else "registered")
        det = _p(params, "DETECTION")
        bits.append(f"segmented into ROIs ({det} detection)" if det else "segmented into ROIs")
        thr = _p(params, "CLASSIFIER_THRESHOLD")
        bits.append(f"classified as cells at probability ≥ {num_text(thr)}" if thr is not None else "classified")
        return "Movies were " + join_and(bits) + " with Suite2p" + (f" {tools['suite2p']}" if tools.get("suite2p") else "")
    if app == "ophys-traces":
        coef = _p(params, "NEUROPIL_COEFFICIENT")
        text = "Neuropil was subtracted" + (f" (coefficient {num_text(coef)})" if coef is not None else "")
        base = _p(params, "BASELINE")
        text += " and ΔF/F computed" + (f" against a {base} baseline" if base else "")
        model = first(v.get("cascade_model") for v in s.values())
        if model:
            text += f"; spike rates were inferred with CASCADE (model {model})"
        if any(k.lower().startswith("oasis") for k in tools) or any(v.get("mean_oasis_event_rate_hz_accepted") is not None for v in s.values()):
            text += " and events with OASIS"
        return text
    if app == "ophys-activity":
        parts = []
        if "rastermap" in {k.lower() for k in tools}:
            parts.append("sorted with Rastermap")
        if any(v.get("n_assemblies") is not None for v in s.values()):
            parts.append("cell assemblies were detected (PCA/ICA)")
        if any(v.get("mean_activity_correlation") is not None for v in s.values()):
            parts.append("pairwise correlations measured")
        text = "Population activity was " + join_and(parts) if parts else "Population activity was summarised"
        stim = first(v.get("stim_table") for v in s.values() if v.get("analysis") == "stimulus-aligned")
        if stim:
            text += f"; responses were aligned to the '{stim}' stimulus table and tested for responsiveness and tuning"
        return text
    if app == "pose-estimate":
        dlc = tools.get("deeplabcut")
        text = "Body keypoints were tracked with DeepLabCut" + (f" {dlc}" if dlc else "")
        kind = summary.get("model_kind")
        model = summary.get("model") or _p(params, "MODEL")
        if kind == "superanimal" and model:
            text += f" using the SuperAnimal model {model} (zero-shot)"
        elif model:
            text += f" using the model {model}"
        if _true(params.get("VIDEO_ADAPT")):
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
        if units:
            text += " in " + join_and(sorted(units))
        return text
    if app == "behavior-syllables":
        method = str(_p(params, "METHOD") or summary.get("method") or variant or "").lower()
        n = summary.get("n_syllables")
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
        labels = _p(params, "UNIT_LABELS")
        if labels:
            text += f"; units labelled {labels} were kept"
        return text
    if app == "neuro-encoding":
        n = _p(params, "N_SHUFFLES")
        text = "Single-neuron tuning curves and information scores were computed and tested against " + \
               (f"{n} shuffles" if n else "shuffles")
        if _true(params.get("GLM")) or any(isinstance(v.get("glm"), dict) for v in s.values()):
            text += "; Poisson GLMs were fitted with NeMoS" + (f" {tools['nemos']}" if tools.get("nemos") else "")
        return text
    if app == "neuro-embedding":
        meths = [EMBEDDINGS.get(m, m) for m in _list(params.get("METHODS"))]
        if not meths:
            return "Population activity was embedded in a low-dimensional space"
        return "Population activity was embedded with " + join_and(meths)
    if app == "neuro-decoding":
        decs = [DECODERS.get(d, d) for d in _list(params.get("DECODERS"))]
        text = "Behaviour was decoded from population activity" + (" with " + join_and(decs) if decs else "")
        folds, shuf = _p(params, "CV_FOLDS"), _p(params, "N_SHUFFLES")
        if folds:
            text += f", {folds}-fold blocked cross-validation"
        if shuf:
            text += f" and a null distribution from {shuf} circular shifts"
        return text
    if app == "nwb-inspect":
        checks = [CHECKS.get(c, c) for c in _list(params.get("CHECKS"))]
        return "NWB files were checked" + (" with " + join_and(checks) if checks else "")
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
               summary: dict[str, Any]) -> set[str]:
    """Tool names this run used: provenance `tools`, minus those its settings did not use, plus
    the app's primary tools."""
    used = {k.lower() for k in tools}
    if app == "spike-sort":
        sorters = {str(v.get("sorter") or params.get("SORTER") or "").lower() for v in sessions.values()} or \
                  {str(params.get("SORTER") or "").lower()}
        if not any(x.startswith("kilosort") for x in sorters):
            used -= {"kilosort", "torch"}
    if app == "neuro-embedding":
        m = set(_list(params.get("METHODS")))
        if "cebra" not in m:
            used -= {"cebra", "torch"}
        if "gpfa" not in m:
            used -= {"elephant", "neo", "quantities"}
    if app == "neuro-encoding" and _true(params.get("GLM")) is False:
        used -= {"nemos", "jax", "jaxlib"}
    if app == "behavior-syllables":
        method = str(params.get("METHOD") or summary.get("method") or "").lower()
        if method == "hmm":
            used |= {"dynamax", "jax"}
            used -= {"keypoint-moseq"}
        elif method in ("kpms", "keypoint-moseq"):
            used |= {"keypoint-moseq", "jax"}
    if app == "pose-estimate" and summary.get("model_kind") == "superanimal":
        used |= {"superanimal"}
    if app == "ephys-curate" and _true(params.get("UNITREFINE")) is False:
        used -= {"skops", "unitrefine"}
    elif app == "ephys-curate":
        used |= {"unitrefine"}
    used |= set(ALWAYS.get(app, []))
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
