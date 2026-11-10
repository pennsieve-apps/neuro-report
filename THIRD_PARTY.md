# Third-party components

The image bundles these components (pip wheels pinned in `requirements.txt`). None is GPL; the app is Apache-2.0.

| Component | Authors / copyright holder | Licence | URL |
|---|---|---|---|
| Python 3.12 (base image `python:3.12.16-slim-bookworm`) | Python Software Foundation; Debian | PSF-2.0; Debian packages under their own licences | https://www.python.org |
| ReportLab 5.1.0 (PDF) | ReportLab Inc. | BSD-3-Clause | https://www.reportlab.com/opensource/ |
| Jinja2 3.1.6 (HTML template) | Pallets | BSD-3-Clause | https://github.com/pallets/jinja |
| MarkupSafe 3.0.4 | Pallets | BSD-3-Clause | https://github.com/pallets/markupsafe |
| Matplotlib 3.11.2 (overview diagram) | Matplotlib Development Team; John D. Hunter | Matplotlib licence (PSF-based, BSD-compatible) | https://matplotlib.org |
| DejaVu fonts (inside matplotlib's wheel; the PDF's fonts, embedded as subsets) | Bitstream (Vera), DejaVu changes public domain | Bitstream Vera licence + public domain | https://dejavu-fonts.github.io |
| Pillow 13.0.0 (figure downscaling) | Jeffrey A. Clark and contributors; Secret Labs AB; Fredrik Lundh | MIT-CMU | https://python-pillow.org |
| NumPy 2.5.4 | NumPy Developers | BSD-3-Clause | https://numpy.org |
| contourpy, cycler, kiwisolver, fonttools, packaging, pyparsing, python-dateutil, tzdata, charset-normalizer | their authors | BSD-3-Clause / MIT / Apache-2.0 / Apache-2.0 or BSD-2-Clause / MIT / Apache-2.0 or BSD-3-Clause / Apache-2.0 / MIT | PyPI |

`processor/references.json` is bibliographic data (titles, author lists, journals, DOIs, PMIDs) copied by
`scripts/build_citations.py` from the CITATION.cff files of the sibling Pennsieve apps (Apache-2.0 or
GPL-3.0-or-later repositories; bibliographic facts, verified against Crossref, DataCite and PubMed).

Development only, not in the image: pytest (MIT), PyYAML (MIT), jsonschema (MIT), cffconvert (Apache-2.0),
PyMuPDF (AGPL-3.0; used only to render PDF pages to PNG for visual checks).
