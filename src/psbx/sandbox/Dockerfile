# Search sidecar. libfaketime from https://github.com/wolfcw/libfaketime.git
# (distro package, not a vendored clone). Agent / vendor LLM APIs stay on the host.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends libfaketime iptables \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PSBX_ROOT=/app
ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PSBX_SEARCH_HOST=0.0.0.0
ENV PSBX_SEARCH_PORT=8766

RUN groupadd --system psbx \
    && useradd --system --gid psbx --home-dir /nonexistent --shell /usr/sbin/nologin psbx
RUN mkdir -p /app/data/corpus

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY config /app/config
RUN pip install --no-cache-dir /app

COPY src/psbx/sandbox/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
