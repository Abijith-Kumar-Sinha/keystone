#!/bin/sh
# Start the embedded FalkorDB unless FALKORDB_HOST points somewhere else, build the graphs, serve the app.
set -e
if [ "${FALKORDB_HOST:-127.0.0.1}" = "127.0.0.1" ]; then
  # the graphs were built when the image was built: start from that dump, which Redis loads in about a second
  [ -f /app/seed/dump.rdb ] && cp /app/seed/dump.rdb /tmp/dump.rdb
  redis-server --loadmodule /var/lib/falkordb/bin/falkordb.so TIMEOUT 30000 RESULTSET_SIZE 100000 MAX_QUEUED_QUERIES 25 \
    --save "" --appendonly no --daemonize yes --dir /tmp --dbfilename dump.rdb --bind 127.0.0.1 --port 6379 >/tmp/redis.log 2>&1
fi
i=0
until /opt/venv/bin/python -c "import falkordb,os;falkordb.FalkorDB(host=os.environ.get('FALKORDB_HOST','127.0.0.1'),port=int(os.environ.get('FALKORDB_PORT','6379'))).list_graphs()" >/dev/null 2>&1; do
  i=$((i+1)); [ "$i" -gt 150 ] && { echo "FalkorDB did not come up"; exit 1; }; sleep 0.2
done
/opt/venv/bin/python -m keystone.bootstrap
exec /opt/venv/bin/uvicorn keystone.api:app --host 0.0.0.0 --port "${PORT:-7860}"
