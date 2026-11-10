.PHONY: help test fixture run demos citations validate clean

SERVICE_NAME ?= neuro-report
PYTHON ?= .venv/bin/python
DATA ?= $(HOME)/code/pennsieve/workflow-systems-neuroscience/data

.DEFAULT: help

help:
	@echo "Make Help for $(SERVICE_NAME)"
	@echo ""
	@echo "make test       - pytest on synthetic step outputs of every app (no Docker)"
	@echo "make fixture    - write the synthetic fixture to data/fixture/{linked,flat}/"
	@echo "make run        - build the image and run it in Docker (read-only, no network) over data/fixture/linked/ (or INPUT_HOST=...), writing to data/output/"
	@echo "make demos      - reports on the demo workflows' real outputs, into DATA/work/<demo>/neuro-report/"
	@echo "make citations  - rebuild processor/references.json from the sibling apps' CITATION.cff files"
	@echo "make validate   - app.yml against the manifest schema, CITATION.cff with cffconvert"
	@echo "make clean      - remove data/output/"
	@echo ""
	@echo "PYTHON=$(PYTHON) (python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt)"

test:
	$(PYTHON) -m pytest -q tests

fixture:
	$(PYTHON) -m tests.make_fixture data/fixture --layout both

run: clean fixture
	mkdir -p data/output
	docker compose -f docker-compose.yml down --remove-orphans
	docker compose -f docker-compose.yml build
	docker compose -f docker-compose.yml up --exit-code-from processor
	docker compose -f docker-compose.yml down --remove-orphans
	@echo "--- outputs:"
	@find data/output -type f | sort

demos:
	$(PYTHON) scripts/run_demos.py --data $(DATA)

citations:
	$(PYTHON) scripts/build_citations.py

validate:
	$(PYTHON) scripts/validate.py

clean:
	rm -rf data/output
