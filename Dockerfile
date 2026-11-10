FROM python:3.12.16-slim-bookworm@sha256:623674a14ef93d052bb9b0de4dbf5f28eb578a35263838941cc8aa43213c1487

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /processor

# Pinned, wheels only: no compiler, no system libraries (the PDF engine is pure-Python ReportLab
# with the DejaVu fonts inside matplotlib's wheel).
COPY requirements.txt /processor/requirements.txt
RUN pip install --only-binary=:all: -r /processor/requirements.txt

COPY processor/ /processor/processor/
COPY VERSION /processor/VERSION

# Caches that must be written (matplotlib's font cache) are set at run time under $TMPDIR
# (processor/main.py), never in the image: on Lambda only INPUT_DIR, OUTPUT_DIR, HOME and TMPDIR
# are writable. USER is set so nothing needs a passwd entry for the run-time uid.
ENV PYTHONPATH="/processor" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLBACKEND=Agg \
    USER=app

RUN python -c "import jinja2, reportlab, matplotlib.pyplot, PIL" \
    && useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin app

# Runs as uid 1000 on ECS and as an arbitrary uid on Lambda; nothing here needs root.
USER 1000

ENTRYPOINT ["python3", "-m", "processor.main"]
