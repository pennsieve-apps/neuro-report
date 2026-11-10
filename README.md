# neuro-report

This app writes the report at the end of the systems neuroscience workflows. **The analyses in it are other
people's methods, packaged as Pennsieve apps; the report credits them.** Each step's own section names the tools
it runs, the References list the papers each step cites (full author lists, from the apps' CITATION.cff files,
verified against Crossref, DataCite and PubMed), and the Acknowledgements name the upstream projects and the
authors of the datasets. The report itself is rendered with [Jinja](https://github.com/pallets/jinja) (Pallets),
[ReportLab](https://www.reportlab.com/opensource/) (ReportLab Inc.) and
[Matplotlib](https://matplotlib.org) (Hunter 2007, [10.1109/MCSE.2007.55](https://doi.org/10.1109/MCSE.2007.55)).
**Pennsieve built the report; it did not develop the methods it reports on.** The demo reports were made from the
DANDI datasets of the International Brain Laboratory (DANDI:000409), Laquitaine et al. (DANDI:001250), the Allen
Institute (DANDI:000728), Plusnin & Pospelov (DANDI:002047) and Grosmark & Buzsáki (DANDI:000044); see
[Citations](#citations).

The last step of every systems neuroscience workflow:

- **Neuropixels Spike Sorting:** `ephys-prep → spike-sort → ephys-curate → neuro-report`
- **Two-photon Calcium Imaging:** `suite2p → ophys-traces → ophys-activity → neuro-report`
- **Markerless Behaviour:** `pose-estimate → pose-kinematics → behavior-syllables → neuro-report`
- **Neural Population Dynamics & Decoding:** `neuro-align → {neuro-encoding, neuro-embedding, neuro-decoding} → neuro-report`
- **End-to-end:** raw Neuropixels + behaviour NWB → sorted units → decoding → `neuro-report`

`nwb-inspect` can be linked into any of them: its DANDI-readiness verdicts appear as badges.

**For a neuroscientist.** Link the outputs of the steps you ran into `steps` (as many as you like), and you get
one report you can read, keep with the data and send to a colleague: an HTML page that opens offline (every figure
is inside the file) and the same report as a PDF. It says which workflow ran, on which sessions and which data,
then for each step: what the step does (one paragraph), its headline numbers per session, its figures in the order
the step chose with the caption the step wrote (each says what to look at), and its warnings, shown prominently and
gathered once more at the top. It ends with a methods summary you can adapt for a paper, a table of software
versions, run times and memory, the references, acknowledgements, and a note on how to cite the analysis.

**For a computational analyst.** The report reads only the shared contract of conventions.md: each app's top
folder `<app>/` with `provenance.json` (`app`, `version`, `variant`, `tools`, `parameters`, `wall_seconds`,
`peak_rss_mb`, `gpu`, `sessions`, `citations`) and `summary.json` (`sessions`, `figures` `[{path, caption}]`,
`tables`, `warnings`). Steps are found recursively (following symlinks) by a `provenance.json` with an `app` key,
so it works whether links land in `steps/<app>/`, side by side, or merged at the input root; other
`provenance.json` files (SpikeInterface writes one into every saved folder) are ignored. It renders any app
generically: the numeric values of each session become the headline table, nested records (e.g. decoded variables,
units per region, syllables) small tables, top-level values an "overall" table. For the known apps it adds a
built-in description, a methods sentence and a curated choice of headline numbers. Nothing is recomputed: the
numbers are the step's, formatted (integers exactly, other numbers to three significant digits, fractions marked as
such as percentages). DOIs in `provenance.citations` are resolved from a citation table bundled at build time
(`processor/references.json`, written by `scripts/build_citations.py` from the sibling apps' verified
CITATION.cff files); a DOI not in it is listed DOI-only with a warning, never filled in from elsewhere. Where a
step's output departs from the contract (a figure listed but missing, no caption, a caption with an unformatted
`{placeholder}`, a headline number written as a string, figure paths relative to the port instead of the app
folder) the report still renders it and lists the problem under "Notes on the inputs" for the app's maintainers.

## Ports

| Port | Direction | Content |
|---|---|---|
| `steps` | in (required) | Outputs of any steps, several links side by side (`<app>/provenance.json`, `summary.json`, the PNGs and CSVs it lists). Media types `application/json`, `image/png`, `text/csv`: NWB and binary data are not read. |
| `metadata` | in (optional) | `sessions.csv` (`session_id`, `subject_id`, `condition`, `group`, optionally `dataset_doi` or `dandiset`). |
| `report` | out | `neuro-report/report.html`, `report.pdf`, `report.json`, `summary.json`, `provenance.json`, `figures/workflow_overview.png`. |

## Parameters

| Name | Default | What it does |
|---|---|---|
| `REPORT_TITLE` | empty | Title. Empty: "Analysis report: " + the workflows found. |
| `MAX_FIGURES` | `24` | Figures shown per step, in the step's order; the rest are named and stay in the step's output. |
| `DATASET_DOIS` | empty | DOIs of the datasets analysed (comma-separated), credited and cited. The demo datasets are recognised from their session ids; a session sheet's `dataset_doi` column is read too. |
| `WRITE_PDF` | `true` | Also write `report.pdf`. |

## Outputs

- `report.html`: one self-contained file. Inline CSS, figures as `data:` URIs, no scripts, no fonts or styles
  loaded from anywhere (links to DOIs and repositories are plain links). Sections: overview (workflows, overview
  diagram, sessions), warnings, one section per step (description, overall values, headline numbers, more numbers,
  figures with captions, the step's tables (small CSVs inline), parameters), methods, software & provenance,
  references, acknowledgements, how to cite, notes on the inputs.
- `report.pdf`: the same content, A4, ReportLab with the DejaVu fonts from matplotlib's wheel (no system fonts).
  Figures wider than 1600 px are downscaled for both files.
- `report.json`: everything the report shows, as data (steps, headline tables, figure paths and captions,
  warnings, references, datasets, input notes).
- `summary.json` and `provenance.json` (conventions.md); `summary.json` lists the overview figure, and counts of
  steps, figures, references, DOI-only references and input notes.

Exit codes: `0` ok, `1` no step output found, `2` bad parameters.

## Runtime

`cpu: 1024`, `memory: 2048` MiB, `computeTypes: [standard]`, `timeoutSeconds: 600`: within the Lambda limits, so
the platform can run it as a Lambda step. Measured in the image (linux/amd64 under emulation on an M-series Mac),
read-only file system, uid 65534, HOME and TMPDIR under `/tmp/w`, `--memory 2g`, cgroup `memory.peak`:

| Demo | Steps | Figures | Wall time (container) | Peak memory |
|---|---|---|---|---|
| IBL end-to-end (`ibl`) | 8 | 28 | 15 s | 279 MB |
| Markerless Behaviour (`openfield-5xfad`, 6 sessions) | 4 | 75 | 17 s | 186 MB |

The other demos (ground truth, Allen 2p, Grosmark) take 1-3 s outside Docker. Image 444 MB (105 MB compressed).
Memory grows with the largest figure, not with the data: the report never opens NWB or binary files. Output size
is dominated by the embedded figures (2-14 MB per file on the demos).

## Limitations

- It reports what the steps wrote. It does not check that a number is right, re-run a statistic or compare
  sessions; a wrong caption or number upstream is a wrong caption or number in the report.
- Session ids are taken as each step wrote them; `nwb-inspect` reports files, which are mapped to the session
  through their `session_id`.
- Datasets are credited only when recognised (demo session ids), given in `DATASET_DOIS`, or named in the
  session sheet: provenance.json does not record the source dataset.
- A cited DOI that is not in the bundled table is shown DOI-only; rebuild the table (`make citations`) after a
  sibling app adds a citation.

## Development

```
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
make test            # pytest on synthetic outputs of every app (tests/make_fixture.py)
make run             # the image, read-only and offline, over the fixture
make demos           # reports on the demo workflows' real outputs (DATA=.../workflow-systems-neuroscience/data)
make citations       # rebuild processor/references.json from ../<app>/CITATION.cff
make validate        # app.yml (manifest schema) and CITATION.cff (cffconvert)
```

## Licences

Apache-2.0 (`LICENSE`). Bundled components and their licences: `THIRD_PARTY.md` (all permissive; no GPL code).

## Citations

Please cite these works if you use this app; cite also the works listed under References in each report, which
are the methods the steps used. Verified on Crossref/DataCite and PubMed; full author lists in CITATION.cff.

- Hunter JD. Matplotlib: A 2D Graphics Environment. Computing in Science & Engineering 2007;9(3):90-95.
  [10.1109/MCSE.2007.55](https://doi.org/10.1109/MCSE.2007.55)
- Rübel O, Tritt A, Ly R, et al. The Neurodata Without Borders ecosystem for neurophysiological data science.
  eLife 2022;11:e78362. [10.7554/eLife.78362](https://doi.org/10.7554/eLife.78362)
- Software: ReportLab (ReportLab Inc., https://www.reportlab.com/opensource/), Jinja (Pallets,
  https://github.com/pallets/jinja).

Demo data (CC-BY-4.0):

- International Brain Laboratory. IBL - Brain Wide Map. DANDI Archive.
  [10.48324/dandi.000409/0.260309.1324](https://doi.org/10.48324/dandi.000409/0.260309.1324); International Brain
  Laboratory et al. A brain-wide map of neural activity during complex behaviour. Nature 2025.
  [10.1038/s41586-025-09235-0](https://doi.org/10.1038/s41586-025-09235-0)
- Laquitaine S, Imbeni M, Tharayil J, Isbister J, Reimann M. DANDI:001250. [10.48324/dandi.001250/0.261108.1908](https://doi.org/10.48324/dandi.001250/0.261108.1908);
  Spike sorting biases and information loss in a detailed cortical model. bioRxiv 2024.
  [10.1101/2024.12.04.626805](https://doi.org/10.1101/2024.12.04.626805)
- Baker C. Allen Institute - Visual Coding - Optical Physiology. DANDI:000728.
  [10.48324/dandi.000728/0.240827.1809](https://doi.org/10.48324/dandi.000728/0.240827.1809); de Vries SEJ, Lecoq JA,
  et al. A large-scale standardized physiological survey reveals functional organization of the mouse visual
  cortex. Nature Neuroscience 2019;23(1):138-151. [10.1038/s41593-019-0550-9](https://doi.org/10.1038/s41593-019-0550-9)
- Plusnin V, Pospelov N. Hippocampal CA1 one-photon calcium imaging and pose-tracked behavior in wild-type and
  5xFAD mice across four behavioral paradigms. DANDI:002047. [10.48324/dandi.002047/0.261106.0903](https://doi.org/10.48324/dandi.002047/0.261106.0903)
- Grosmark AD, Buzsáki G. DANDI:000044. [10.48324/dandi.000044/0.261106.0236](https://doi.org/10.48324/dandi.000044/0.261106.0236);
  Diversity in neural firing dynamics supports both rigid and learned hippocampal sequences. Science
  2016;351(6280):1440-1443.
  [10.1126/science.aad1935](https://doi.org/10.1126/science.aad1935)

## Acknowledgements

The methods in every report belong to their authors, credited in each report's Acknowledgements and References and
in each app's README. We thank the International Brain Laboratory, the Allen Institute, the Buzsáki lab, the
Viktor Plusnin, Nikita Pospelov and colleagues, and Laquitaine et al. for sharing their data on the DANDI Archive, and the Neurodata Without Borders
and DANDI teams for the standards and archive the workflows are built on.
