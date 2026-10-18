"""FalkorDB access. One tenant == one graph (`ks_<tenant>`); what-if forks are throwaway `GRAPH.COPY`s."""
import os
import re
import uuid
from contextlib import contextmanager
from functools import lru_cache

from falkordb import FalkorDB

TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
PREFIX = "ks_"
FORK = "__wi_"


@lru_cache(maxsize=1)
def client() -> FalkorDB:
    return FalkorDB(
        host=os.environ.get("FALKORDB_HOST", "localhost"),
        port=int(os.environ.get("FALKORDB_PORT", "6379")),
        password=os.environ.get("FALKORDB_PASSWORD") or None,
        ssl=os.environ.get("FALKORDB_TLS") == "1",
    )


def graph(tenant: str):
    """Tenant graph handle. The regex is the only place a tenant name becomes a key name."""
    if not TENANT_RE.match(tenant):
        raise ValueError(f"bad tenant name: {tenant!r}")
    return client().select_graph(PREFIX + tenant)


def tenants() -> list[str]:
    names = [n if isinstance(n, str) else n.decode() for n in client().list_graphs()]
    return sorted(n[len(PREFIX):] for n in names if n.startswith(PREFIX) and FORK not in n)


def exists(tenant: str) -> bool:
    return tenant in tenants()


@contextmanager
def fork(tenant: str):
    """Counterfactual sandbox: a full copy of the tenant graph that is always deleted afterwards."""
    name = f"{PREFIX}{tenant}{FORK}{uuid.uuid4().hex[:8]}"
    client().connection.execute_command("GRAPH.COPY", PREFIX + tenant, name)
    try:
        yield client().select_graph(name)
    finally:
        client().connection.execute_command("GRAPH.DELETE", name)


def q(g, cypher: str, params: dict | None = None, write: bool = False) -> list[list]:
    """Run a query, return rows. Reads use GRAPH.RO_QUERY so an agent tool can never mutate the graph."""
    res = (g.query if write else g.ro_query)(cypher, params or {})
    return res.result_set


def set_timeout_ms(ms: int = 30000) -> None:
    """Default 1s is too tight for whole-graph algorithms on a cold cache."""
    client().connection.execute_command("GRAPH.CONFIG", "SET", "TIMEOUT", ms)
