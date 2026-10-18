# One container = FalkorDB + Keystone. Runs anywhere Docker runs (Hugging Face Spaces, Render, Fly, a laptop).
# Local dev with a separate database container: see docker-compose.yml.
FROM falkordb/falkordb:latest

USER root
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
# dependencies come from pyproject.toml, so there is one list to maintain
RUN python3 -m venv /opt/venv \
 && python3 -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/req.txt \
 && /opt/venv/bin/pip install -r /tmp/req.txt

COPY keystone ./keystone
COPY web ./web
COPY data/snapshot ./data/snapshot
COPY data/tenants.json data/codeowners.json ./data/
COPY deploy/start.sh /start.sh

# Build the graphs once, while the image is built, and keep the Redis dump. A cold start then loads it in about a second instead of
# rebuilding for over a minute on the small shared CPU of a free host.
RUN set -e; \
    redis-server --loadmodule /var/lib/falkordb/bin/falkordb.so TIMEOUT 60000 --save "" --appendonly no --daemonize yes --dir /tmp --bind 127.0.0.1 --port 6379 >/tmp/seed-redis.log 2>&1; \
    until /opt/venv/bin/python -c "import falkordb;falkordb.FalkorDB(host='127.0.0.1',port=6379).list_graphs()" >/dev/null 2>&1; do sleep 0.5; done; \
    PYTHONPATH=/app /opt/venv/bin/python -m keystone.bootstrap; \
    redis-cli -p 6379 SAVE; \
    mkdir -p /app/seed && cp /tmp/dump.rdb /app/seed/dump.rdb; \
    redis-cli -p 6379 SHUTDOWN NOSAVE || true; \
    rm -f /tmp/dump.rdb /tmp/seed-redis.log

RUN chmod +x /start.sh && chown -R 1000:1000 /app

# a numeric UID is enough (hosts such as Hugging Face Spaces run as 1000); no passwd entry needed, so HOME is explicit
USER 1000
ENV HOME=/tmp PORT=7860 FALKORDB_HOST=127.0.0.1 KEYSTONE_WRITABLE=sandbox PYTHONPATH=/app
EXPOSE 7860
ENTRYPOINT ["/start.sh"]
