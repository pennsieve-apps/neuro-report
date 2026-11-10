"""
What the report knows about the apps of the systems neuroscience workflows: the workflows they
form, one paragraph per app saying what the step does, the methods sentence, and which
summary.json numbers are the headline of each session. Everything here is optional: an app that is
not listed is still reported, generically, from its summary.json and provenance.json.
"""
from __future__ import annotations

import re
from typing import Any

# The four workflows (and the end-to-end one), in pipeline order.
WORKFLOWS: list[dict[str, Any]] = [
    {"key": "spike-sorting", "name": "Neuropixels Spike Sorting",
     "chain": [["ephys-prep"], ["spike-sort"], ["ephys-curate"]]},
    {"key": "calcium-imaging", "name": "Two-photon Calcium Imaging",
     "chain": [["suite2p"], ["ophys-traces"], ["ophys-activity"]]},
    {"key": "behaviour", "name": "Markerless Behaviour",
     "chain": [["pose-estimate"], ["pose-kinematics"], ["behavior-syllables"]]},
    {"key": "decoding", "name": "Neural Population Dynamics & Decoding",
     "chain": [["neuro-align"], ["neuro-encoding", "neuro-embedding", "neuro-decoding"]]},
]
END_TO_END = {"key": "end-to-end", "name": "End-to-end: raw Neuropixels to decoding",
              "chain": [["ephys-prep"], ["spike-sort"], ["ephys-curate"], ["neuro-align"],
                        ["neuro-encoding", "neuro-embedding", "neuro-decoding"]]}

ORDER = ["nwb-inspect", "ephys-prep", "spike-sort", "ephys-curate", "suite2p", "ophys-traces", "ophys-activity",
         "pose-estimate", "pose-kinematics", "behavior-syllables", "neuro-align", "neuro-encoding",
         "neuro-embedding", "neuro-decoding"]
# nwb-inspect checks files of any step; it is shown after the analysis steps.
DISPLAY_ORDER = ORDER[1:] + ["nwb-inspect"]

# H: (label, key path in a session's summary, format). Formats: int, num, pct (fraction shown as
# %), bool, text. A label may use {units}, filled from the session's "units" value.
APPS: dict[str, dict[str, Any]] = {
    "ephys-prep": {
        "title": "Preprocessing (ephys-prep)",
        "about": "Reads the raw extracellular recording, keeps the requested time window on the session clock, "
                 "removes the probe's channel phase shift, high-pass filters, detects and removes bad channels "
                 "(dead, noisy, outside the brain), re-references to suppress noise shared by all channels, and "
                 "estimates (and, when it is large, corrects) the slow drift of the brain relative to the probe. "
                 "The preprocessing follows the Allen Institute for Neural Dynamics and International Brain "
                 "Laboratory pipelines, implemented with SpikeInterface.",
        "methods": "Recordings were preprocessed with SpikeInterface (phase-shift correction, high-pass filter, "
                   "bad-channel detection, common reference) and drift was estimated with DREDge",
        "headline": [("Duration (s)", "duration_s", "num"), ("Sampling rate (Hz)", "sampling_frequency", "num"),
                     ("Channels", "n_channels", "int"), ("Bad channels", "n_bad_channels", "int"),
                     ("Max drift (µm)", "max_drift_range_um", "num"), ("Motion corrected", "motion_corrected", "bool"),
                     ("Spikes detected / s", "peaks_per_s", "num")],
    },
    "spike-sort": {
        "title": "Spike sorting (spike-sort)",
        "about": "Finds the spikes in the preprocessed recording and groups them into units, each meant to be one "
                 "neuron, by the shape of its waveform across neighbouring channels. Kilosort4 runs on a GPU; on "
                 "CPUs SpikeInterface's Lupin or SpykingCircus2 sorter is used. The units are not yet curated: many "
                 "are multi-unit activity or noise until ephys-curate labels them.",
        "methods": "Spikes were sorted with {sorter}",
        "headline": [("Sorter", "sorter", "text"), ("Units", "n_units", "int"), ("Spikes", "n_spikes", "int"),
                     ("Median rate (Hz)", "median_firing_rate_hz", "num"),
                     ("Units > 50 µV", "n_units_above_50uV", "int"), ("Sorting time (s)", "wall_seconds", "num"),
                     ("× real time", "realtime_factor", "num")],
    },
    "ephys-curate": {
        "title": "Curation and quality metrics (ephys-curate)",
        "about": "Computes each unit's waveforms, location and quality metrics (firing rate, refractory-period "
                 "violations, amplitude, signal-to-noise and others), merges over-split units, and labels every unit "
                 "good (single neuron), mua (multi-unit activity) or noise with two automated curators, Bombcell's "
                 "interpretable thresholds and UnitRefine's pretrained classifiers. Writes an NWB Units table that "
                 "DANDI accepts.",
        "methods": "Units were curated with SpikeInterface quality metrics, Bombcell and UnitRefine",
        "headline": [("Units", "n_units", "int"), ("Good", "n_good", "int"), ("MUA", "n_mua", "int"),
                     ("Noise", "n_noise", "int"), ("Bombcell / UnitRefine agreement", "bombcell_unitrefine_agreement", "pct"),
                     ("Median SNR (good)", "median_snr_good", "num"),
                     ("Median rate, good (Hz)", "median_firing_rate_good", "num"),
                     ("Reference units matched", "reference.n_matched", "int"),
                     ("Reference units", "reference.n_reference_units", "int")],
    },
    "suite2p": {
        "title": "Motion correction and cell detection (suite2p)",
        "about": "Removes the brain's motion from the two-photon movie (registration), finds regions of pixels that "
                 "light up together (cell detection), decides with Suite2p's classifier which regions look like cell "
                 "bodies, and extracts each region's fluorescence and that of the surrounding neuropil.",
        "methods": "Two-photon movies were registered and segmented with Suite2p",
        "headline": [("Frames", "n_frames", "int"), ("Frame rate (Hz)", "frame_rate", "num"),
                     ("Duration (s)", "duration_s", "num"), ("ROIs", "n_rois", "int"), ("Cells", "n_cells", "int"),
                     ("Max rigid shift (px)", "rigid_shift_max_px", "num")],
    },
    "ophys-traces": {
        "title": "ΔF/F and spike inference (ophys-traces)",
        "about": "Subtracts the neuropil, computes ΔF/F, and infers spike rates with CASCADE's pretrained networks "
                 "(the model is picked from the indicator and frame rate) and discrete events with OASIS. Writes "
                 "an NWB file with the segmentation and all traces on the session clock.",
        "methods": "ΔF/F was computed after neuropil subtraction and spike rates were inferred with CASCADE "
                   "and OASIS",
        "headline": [("ROIs", "n_rois", "int"), ("Accepted", "n_accepted", "int"), ("Indicator", "indicator", "text"),
                     ("CASCADE model", "cascade_model", "text"), ("Median SNR", "median_snr_accepted", "num"),
                     ("Mean CASCADE rate (Hz)", "mean_cascade_rate_hz_accepted", "num"),
                     ("Neuropil / F", "median_neuropil_to_f_ratio", "num")],
    },
    "ophys-activity": {
        "title": "Population activity and tuning (ophys-activity)",
        "about": "Summarises population activity: event rates, the Rastermap-sorted raster, pairwise correlations "
                 "and cell assemblies (groups of neurons that are repeatedly co-active). When a stimulus or trials "
                 "table is available it aligns responses to it and measures responsiveness, reliability and "
                 "orientation/direction tuning.",
        "methods": "Population activity was summarised with Rastermap, correlations and PCA/ICA cell assemblies, "
                   "and stimulus responses with trial-aligned tuning metrics",
        "headline": [("ROIs", "n_rois", "int"), ("Analysis", "analysis", "text"), ("Trials", "n_trials", "int"),
                     ("Responsive", "n_responsive", "int"), ("Responsive fraction", "fraction_responsive", "pct"),
                     ("Tuned", "n_tuned", "int"), ("Mean event rate (Hz)", "mean_event_rate_hz", "num"),
                     ("Mean correlation", "mean_activity_correlation", "num"), ("Assemblies", "n_assemblies", "int")],
    },
    "pose-estimate": {
        "title": "Pose estimation (pose-estimate)",
        "about": "Tracks body parts (keypoints) in every video frame with DeepLabCut, either zero-shot with the "
                 "Mathis lab's SuperAnimal pretrained models (academic, non-commercial use) or with the lab's own "
                 "DeepLabCut model, and writes the pose as NWB (ndx-pose) with a confidence for every keypoint.",
        "methods": "Body keypoints were tracked with DeepLabCut",
        "headline": [("Keypoints", "n_keypoints", "int"), ("Frames analysed", "n_frames_analysed", "int"),
                     ("Seconds analysed", "duration_analysed_s", "num"), ("Mean confidence", "mean_confidence", "num"),
                     ("Low-confidence frames", "fraction_low_confidence_frames", "pct"),
                     ("Frames with animal detected", "fraction_frames_detected", "pct")],
    },
    "pose-kinematics": {
        "title": "Kinematics (pose-kinematics)",
        "about": "Cleans the pose (drops low-confidence points and jumps, interpolates short gaps, filters), "
                 "converts pixels to centimetres when the arena size is known, and computes speed, heading, "
                 "distances and the time spent in arena regions (centre, periphery) with the movement toolbox.",
        "methods": "Pose was filtered and kinematics were computed with movement",
        "headline": [("Duration (s)", "duration_s", "num"), ("Valid frames", "valid_fraction", "pct"),
                     ("Distance ({units})", "distance_travelled", "num"), ("Mean speed ({units}/s)", "mean_speed", "num"),
                     ("Immobile", "immobile_fraction", "pct"), ("Time in centre", "center_fraction", "pct"),
                     ("Thigmotaxis", "thigmotaxis", "num")],
    },
    "behavior-syllables": {
        "title": "Behavioural syllables (behavior-syllables)",
        "about": "Splits behaviour into short, reused motifs (syllables) without labels, with a sticky "
                 "autoregressive hidden Markov model on the kinematic features (the MoSeq idea), and reports how "
                 "often each syllable is used, how long it lasts, how syllables follow each other and, when expert "
                 "labels exist, how syllables agree with them.",
        "methods": "Behaviour was segmented into syllables with a sticky autoregressive HMM (Dynamax)",
        "headline": [("Frames", "n_frames", "int"), ("Modelled", "modelled_fraction", "pct"), ("Bouts", "n_bouts", "int")],
    },
    "neuro-align": {
        "title": "Alignment and binning (neuro-align)",
        "about": "Reads neural activity (sorted units or imaging ROIs) and behaviour from NWB, puts them on the "
                 "session clock, restricts them to the window where both exist, and bins them into a matrix of "
                 "neurons × time bins with the matching behaviour variables, the input of the encoding, embedding "
                 "and decoding steps.",
        "methods": "Neural activity and behaviour were aligned on the session clock and binned with pynapple",
        "headline": [("Neural data", "neural_kind", "text"), ("Neurons", "n_neurons", "int"),
                     ("Bin (s)", "bin_size_s", "num"), ("Bins", "n_bins", "int"), ("Duration (s)", "duration_s", "num"),
                     ("Events", "n_events", "int")],
    },
    "neuro-encoding": {
        "title": "Single-neuron encoding (neuro-encoding)",
        "about": "Asks what each neuron encodes: tuning curves for position, speed, head direction and other "
                 "variables, spatial information and speed scores tested against shuffles, and Poisson GLMs (NeMoS) "
                 "that measure how much each variable adds to predicting a neuron's spikes.",
        "methods": "Single-neuron tuning, spatial information and Poisson GLMs (NeMoS) were computed with "
                   "shuffle controls",
        "headline": [("Neurons", "n_neurons", "int"), ("Place cells", "n_place_cells", "int"),
                     ("Epoch (s)", "epoch_seconds", "num"), ("GLM median D²", "glm.median_d2", "num")],
    },
    "neuro-embedding": {
        "title": "Population embeddings (neuro-embedding)",
        "about": "Finds low-dimensional structure in the population: PCA and factor analysis, GPFA, and CEBRA "
                 "embeddings trained with behaviour, with time only, and with shuffled behaviour as a control, and "
                 "measures how well behaviour can be read out of each embedding.",
        "methods": "Population activity was embedded with PCA, factor analysis, GPFA (Elephant) and CEBRA",
        "headline": [("Neurons", "n_neurons", "int"), ("PCs for 80 % variance", "pca_n_pc_80", "int"),
                     ("Variance in 3 PCs", "pca_var_3pc", "pct"),
                     ("CEBRA behaviour fit (bits)", "cebra_behavior_gof_bits", "num"),
                     ("CEBRA shuffled fit (bits)", "cebra_shuffled_gof_bits", "num"),
                     ("kNN R², CEBRA-behaviour", "knn_r2_test.cebra_behavior", "num"),
                     ("kNN R², shuffled", "knn_r2_test.cebra_shuffled", "num")],
    },
    "neuro-decoding": {
        "title": "Decoding (neuro-decoding)",
        "about": "Decodes behaviour from population activity with cross-validated ridge, neural-network and "
                 "Bayesian decoders, compares each result with a null distribution from circularly shifted data, "
                 "and asks how decoding depends on the number of neurons and on the brain region.",
        "methods": "Behaviour was decoded from population activity with blocked cross-validation and "
                   "circular-shift null distributions",
        "headline": [("Neurons", "n_neurons", "int"), ("Bin (s)", "decode_bin_s", "num"),
                     ("Neural data", "neural_source", "text")],
    },
    "nwb-inspect": {
        "title": "NWB validation and DANDI readiness (nwb-inspect)",
        "about": "Validates NWB files against the NWB schema, runs the NWB Inspector's best-practice checks and "
                 "DANDI's upload checks, and summarises each file's contents, so a lab knows whether its files can "
                 "be shared on DANDI as they are.",
        "methods": "NWB files were validated with PyNWB, the NWB Inspector and the DANDI client",
        "headline": [("DANDI-ready", "dandi_ready", "bool"), ("Critical", "n_critical", "int"),
                     ("Violations", "n_violations", "int"), ("Suggestions", "n_suggestions", "int"),
                     ("NWB version", "nwb_version", "text"), ("Size (MB)", "file_size_mb", "num")],
    },
}

# Session sheet columns carried by every app (conventions.md): shown once, not as numbers.
SHEET_COLUMNS = ("subject_id", "condition", "group")

# Demo datasets, recognised by their session ids, so their authors are credited even though
# provenance.json does not name the source dataset. Every bibliographic detail comes from the
# bundled citation table (the sibling apps' verified CITATION.cff); this only links session ids
# to DOIs. Licences from the DANDI landing pages (all CC-BY-4.0), as recorded in
# workflow-systems-neuroscience data/README.md.
DATASETS: list[dict[str, Any]] = [
    {"pattern": r"^sub-NR-0031_", "doi": "10.48324/dandi.000409/0.260309.1324", "dandiset": "000409",
     "paper": "10.1038/s41586-025-09235-0", "licence": "CC-BY-4.0"},
    {"pattern": r"^sub-demo-npx-bio", "doi": "10.48324/dandi.001250/0.261108.1908", "dandiset": "001250",
     "paper": "10.1101/2024.12.04.626805", "licence": "CC-BY-4.0"},
    {"pattern": r"^sub-496001363_", "doi": "10.48324/dandi.000728/0.240827.1809", "dandiset": "000728",
     "paper": "10.1038/s41593-019-0550-9", "licence": "CC-BY-4.0"},
    {"pattern": r"^sub-F\d+_ses-OF-", "doi": "10.48324/dandi.002047/0.261106.0903", "dandiset": "002047",
     "paper": None, "licence": "CC-BY-4.0"},
    {"pattern": r"^sub-(Buddy|Achilles|Cicero|Gatsby)_", "doi": "10.48324/dandi.000044/0.261106.0236",
     "dandiset": "000044", "paper": "10.1126/science.aad1935", "licence": "CC-BY-4.0"},
]


def demo_datasets(session_ids: list[str]) -> list[dict[str, Any]]:
    return [d for d in DATASETS if any(re.match(d["pattern"], s) for s in session_ids)]


def title_of(app: str) -> str:
    return APPS.get(app, {}).get("title", app)


def order_key(app: str) -> tuple[int, str]:
    return (DISPLAY_ORDER.index(app) if app in DISPLAY_ORDER else len(DISPLAY_ORDER), app)


def detect_workflows(apps: set[str]) -> list[dict[str, Any]]:
    """The workflows whose steps are present (at least one app of the chain). The end-to-end
    workflow replaces spike sorting + decoding when both are present."""
    found = [w for w in WORKFLOWS if any(a in apps for stage in w["chain"] for a in stage)]
    keys = {w["key"] for w in found}
    if {"spike-sorting", "decoding"} <= keys:
        found = [END_TO_END] + [w for w in found if w["key"] not in ("spike-sorting", "decoding")]
    return found
