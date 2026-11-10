# Sample input

The report needs the outputs of other steps, not raw data. Three ways to get some:

1. **Synthetic, every app at once:** `python -m tests.make_fixture data/fixture --layout both` writes
   `data/fixture/linked/steps/<app>/...` (one folder per app, as the platform links them) and
   `data/fixture/linked/metadata/sessions.csv`; `flat/` has everything merged at the root. `make run` runs the
   image on it.
2. **The demo workflows' real outputs:** with the workflow repo's demo data staged and the steps run
   (`workflow-systems-neuroscience/data/work/<demo>/<app>/`), `make demos` links them into a temporary input and
   writes `data/work/<demo>/neuro-report/` for `ibl` (end-to-end), `ground-truth` (spike sorting), `allen-2p`
   (calcium imaging), `openfield-5xfad` (behaviour) and `grosmark` (decoding).
3. **On Pennsieve:** add neuro-report as the last step of a workflow and link the output port of every step you
   want in the report to its `steps` input; optionally link the first step's `sessions.csv` (or your own sheet)
   to `metadata`.

The demo data are DANDI:000409 (IBL), 001250 (Laquitaine et al.), 000728 (Allen Institute), 002047 (Plusnin,
Pospelov) and 000044 (Grosmark & Buzsáki), all CC-BY-4.0; see the README's Citations.
