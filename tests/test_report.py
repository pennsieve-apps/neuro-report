"""
The report on synthetic step outputs (tests/make_fixture.py): no Docker, no network.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from processor import apps as A
from processor import citations as C
from processor import main as app
from processor.inputs import find_steps
from tests import make_fixture as F

PARAMS = {"REPORT_TITLE": "", "MAX_FIGURES": 24, "DATASET_DOIS": "", "WRITE_PDF": True}


def run(tmp_path: Path, layout: str = "linked", apps: list[str] | None = None, **params) -> tuple[int, Path]:
    root = F.make(tmp_path / "in", layout, apps)
    out = tmp_path / "out"
    code = app.run(root, out, {**PARAMS, **params})
    return code, out / "neuro-report"


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("full")
    code, out = run(tmp)
    assert code == 0
    return out, json.loads((out / "report.json").read_text()), (out / "report.html").read_text()


def test_outputs(full):
    out, _, _ = full
    for name in ("report.html", "report.pdf", "report.json", "summary.json", "provenance.json",
                 "figures/workflow_overview.png"):
        assert (out / name).is_file(), name
    pdf = (out / "report.pdf").read_bytes()
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type /Page[^s]", pdf)) > 10
    prov = json.loads((out / "provenance.json").read_text())
    assert prov["app"] == "neuro-report" and set(prov) >= {"version", "variant", "tools", "parameters", "inputs",
                                                           "started", "finished", "wall_seconds", "peak_rss_mb",
                                                           "gpu", "sessions", "citations"}
    assert all(C.lookup(d) for d in prov["citations"])
    summ = json.loads((out / "summary.json").read_text())
    assert summ["n_steps"] == len(F.ALL) and set(summ["sessions"]) == {s for s, _, _ in F.SESSIONS}


def test_html_is_self_contained(full):
    _, _, html = full
    assert "<script" not in html and "<link" not in html and "@import" not in html and "<iframe" not in html
    loaded = re.findall(r'(?:src|srcset|poster)\s*=\s*"(?!data:)([^"]*)"', html)
    assert loaded == []
    assert not re.search(r"url\(\s*['\"]?(?!data:)", html)


def test_every_step_and_workflow(full):
    _, m, _ = full
    assert [s["app"] for s in m["steps"]] == sorted(F.ALL, key=A.order_key)
    names = [w["name"] for w in m["workflows"]]
    assert names[0] == A.END_TO_END["name"]  # spike sorting + decoding together
    assert "Two-photon Calcium Imaging" in names and "Markerless Behaviour" in names
    assert set(m["extra_apps"]) == {"nwb-inspect", "future-app"}


def test_figures_in_order_with_captions(full):
    _, m, html = full
    for s in m["steps"]:
        caps = [f["caption"] for f in s["figures"]]
        if s["app"] == "ephys-curate":
            assert s["missing_figures"] == ["does_not_exist.png"]
        assert caps[:2] == [f"{s['app']} overview of {sid}: look at the trend (synthetic caption {i + 1})."
                            for i, (sid, _, _) in enumerate(F.SESSIONS)]
        assert caps[2] == f"{s['app']}: all sessions compared (synthetic)."
        positions = [html.index(c) for c in caps]
        assert positions == sorted(positions)
    # The port-relative path of pose-kinematics was found, and noted.
    pk = next(s for s in m["steps"] if s["app"] == "pose-kinematics")
    assert len(pk["figures"]) == 3
    assert any("relative to the port folder" in i["problem"] for i in m["issues"] if i["app"] == "pose-kinematics")
    assert any("does_not_exist.png" in i["problem"] for i in m["issues"])
    # Figures are numbered through the report and embedded.
    assert [f["number"] for s in m["steps"] for f in s["figures"]] == list(range(1, 1 + sum(len(s["figures"]) for s in m["steps"])))
    assert html.count('src="data:image/png;base64,') == 1 + sum(len(s["figures"]) for s in m["steps"])


def test_headline_numbers_faithful(full):
    _, m, html = full
    sort = next(s for s in m["steps"] if s["app"] == "spike-sort")
    assert sort["session_header"][sort["session_header"].index("Units")]
    col = sort["session_header"].index("Units")
    assert [r[col] for r in sort["session_rows"]] == ["211", "211"]
    cur = next(s for s in m["steps"] if s["app"] == "ephys-curate")
    col = cur["session_header"].index("Bombcell / UnitRefine agreement")
    assert cur["session_rows"][0][col] == "81.0 %"
    # Nested values become small tables (units by region, decoded variables).
    assert any(t["name"] == "Units by region" for d in cur["details"] for t in d["tables"])
    dec = next(s for s in m["steps"] if s["app"] == "neuro-decoding")
    t = next(t for d in dec["details"] for t in d["tables"] if t["name"] == "Variables")
    assert t["rows"][0][:2] == ["position", "0.63"]
    # pose-kinematics labels take the session's units.
    pk = next(s for s in m["steps"] if s["app"] == "pose-kinematics")
    assert "Distance (cm)" in pk["session_header"]
    # Top-level lists of records become tables (behavior-syllables `syllables`).
    bs = next(s for s in m["steps"] if s["app"] == "behavior-syllables")
    assert bs["overall_tables"][0]["n_rows"] == 6
    assert "154,321" in html


def test_unknown_app_generic(full):
    _, m, _ = full
    fut = next(s for s in m["steps"] if s["app"] == "future-app")
    assert not fut["known"]
    assert "N widgets" in fut["session_header"] and "Score" in fut["session_header"]
    assert "Label" not in fut["session_header"]


def test_warnings_prominent(full):
    _, m, html = full
    texts = [w["text"] for w in m["warnings"]]
    assert f"{F.SESSIONS[1][0]}: synthetic warning from ephys-prep" in texts
    assert any("only 4 trials per condition" in t for t in texts)  # a session-level warning
    assert any(F.UNKNOWN_DOI in t for t in texts)
    assert html.index('id="warnings"') < html.index('id="step-1"')


def test_references(full):
    _, m, html = full
    dois = [r["doi"].lower() for r in m["references"]]
    assert len(dois) == len(set(dois))
    expected = {C.norm(d) for cites in F.CITES.values() for d in cites}
    assert {C.norm(d) for d in dois} == expected
    unknown = [r for r in m["references"] if not r["known"]]
    assert [r["doi"] for r in unknown] == [F.UNKNOWN_DOI]
    assert "DOI only (not in the report&#39;s citation table)" in html or "DOI only (not in the report's citation table)" in html
    # Known references carry the verified record: full author list from the table.
    ks = next(r for r in m["references"] if r["doi"].lower() == "10.7554/elife.61834")
    rec = C.lookup("10.7554/eLife.61834")
    assert ks["authors"].count(",") == len(rec["authors"]) - 1
    # Each step's numbers point at its own citations.
    sp = next(s for s in m["steps"] if s["app"] == "spike-sort")
    assert {m["references"][n - 1]["doi"].lower() for n in sp["refs"]} == {C.norm(d) for d in F.CITES["spike-sort"]}


def test_software_and_cite(full):
    _, m, html = full
    sp = next(s for s in m["steps"] if s["app"] == "spike-sort")
    assert sp["gpu"].startswith("Tesla T4") and sp["peak_rss_mb"] == 512.0
    assert "spike-sort-core 1.0.0" in html
    assert "https://github.com/pennsieve-apps/spike-sort" in html
    assert 'id="acknowledgements"' in html and "SpikeInterface" in html


def test_flat_layout_same_steps(tmp_path):
    root = F.make(tmp_path, "flat")
    steps, sheets = find_steps(root)
    assert sorted(s.app for s in steps) == sorted(F.ALL)
    assert [p.name for p in sheets] == ["sessions.csv"] and sheets[0].parent == root
    # The SpikeInterface provenance.json inside ephys-prep is not a step.
    assert sum(1 for s in steps if s.app == "ephys-prep") == 1


@pytest.mark.parametrize("apps,expected", [
    (["suite2p", "ophys-traces", "ophys-activity"], ["Two-photon Calcium Imaging"]),
    (["ephys-prep", "spike-sort", "ephys-curate"], ["Neuropixels Spike Sorting"]),
    (["neuro-align", "neuro-decoding"], ["Neural Population Dynamics & Decoding"]),
    (["pose-kinematics", "behavior-syllables", "nwb-inspect"], ["Markerless Behaviour"]),
])
def test_workflow_detection(tmp_path, apps, expected):
    code, out = run(tmp_path, apps=apps, WRITE_PDF=False)
    assert code == 0
    m = json.loads((out / "report.json").read_text())
    assert [w["name"] for w in m["workflows"]] == expected
    assert m["title"] == "Analysis report: " + expected[0]
    assert not (out / "report.pdf").exists()


def test_max_figures(tmp_path):
    code, out = run(tmp_path, apps=["suite2p"], MAX_FIGURES=1, WRITE_PDF=False)
    m = json.loads((out / "report.json").read_text())
    s = m["steps"][0]
    assert len(s["figures"]) == 1 and len(s["omitted_figures"]) == 2


def test_dataset_doi_parameter(tmp_path):
    code, out = run(tmp_path, apps=["suite2p"], DATASET_DOIS="10.48324/dandi.000728/0.240827.1809", WRITE_PDF=False)
    m = json.loads((out / "report.json").read_text())
    assert m["datasets"][0]["known"] and m["datasets"][0]["title"].startswith("Allen Institute")


def test_demo_dataset_recognised():
    assert [d["dandiset"] for d in A.demo_datasets(["sub-NR-0031_ses-caa5dddc"])] == ["000409"]
    for d in A.DATASETS:
        assert C.lookup(d["doi"]), d["doi"]
        assert d["paper"] is None or C.lookup(d["paper"]), d["paper"]


def test_known_apps_cover_the_workflows():
    for w in A.WORKFLOWS:
        for stage in w["chain"]:
            for a in stage:
                assert a in A.APPS and A.APPS[a]["about"] and A.APPS[a]["headline"]


def test_exit_codes(tmp_path, monkeypatch):
    (tmp_path / "in").mkdir()
    monkeypatch.setenv("INPUT_DIR", str(tmp_path / "in"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    assert app.main() == 1  # nothing to report
    monkeypatch.setenv("MAX_FIGURES", "many")
    assert app.main() == 2
    monkeypatch.setenv("MAX_FIGURES", "4")
    monkeypatch.setenv("WRITE_PDF", "maybe")
    assert app.main() == 2


def test_lambda_style_scratch(tmp_path, monkeypatch):
    """HOME and TMPDIR given as folders that don't exist yet: the app makes them and writes its
    matplotlib cache there."""
    F.make(tmp_path / "in", "linked", ["neuro-align"])
    monkeypatch.setenv("INPUT_DIR", str(tmp_path / "in" / "linked"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("HOME", str(tmp_path / "w" / "home"))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "w" / "tmp"))
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", None)
    assert app.main() == 0
    assert (tmp_path / "w" / "home").is_dir() and (tmp_path / "w" / "tmp" / "mpl").is_dir()


def test_format_numbers():
    from processor.model import fmt
    assert fmt(2711794) == "2,711,794"
    assert fmt(0.7391, "pct") == "73.9 %"
    assert fmt(30000.48) == "30,000"
    assert fmt(8.369786) == "8.37"
    assert fmt("58", "int") == "58"
    assert fmt(None) == "–" and fmt(True) == "yes"
    assert fmt(600.0, "num") == "600"


def test_generated_at_is_utc():
    now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    from processor import model as M
    m = M.build([], [], Path("."), PARAMS, now, "0.1.0")
    assert m["generated"] == "2026-11-09 12:00 UTC" and m["steps"] == []
