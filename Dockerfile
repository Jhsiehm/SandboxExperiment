# Initialized with docker init; adapted for the ANES batch experiment.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /workspace

COPY pyproject.toml README.md ./
COPY src ./src
COPY custom ./custom
COPY leaderboard ./leaderboard

RUN pip install . && \
    useradd --create-home --uid 10001 psbx

USER 10001:10001

CMD ["psbx", "--help"]
