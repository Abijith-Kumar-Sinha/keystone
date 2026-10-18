"""Build every tenant graph from the committed snapshots in data/snapshot/ (no GitHub access needed).

  python -m keystone.bootstrap            # create tenants that do not exist yet
  python -m keystone.bootstrap --force    # rebuild all of them
  python -m keystone.snapshot             # (maintainers) re-compress data/raw/*.json into data/snapshot/

A tenant with a `history` entry is built the way a real deployment lives: the agent reviews the org as of an EARLIER date and
writes its decisions and tasks to memory; then the data is refreshed to today with the memory untouched. So a fresh install already
has something real for `changes_since` to answer: which of last quarter's recommendations actually happened.
"""
import argparse
import glob
import gzip
import json
from pathlib import Path

from . import db, load, workflow

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "data" / "snapshot"


def manifest() -> dict:
    return json.loads((ROOT / "data" / "tenants.json").read_text(encoding="utf-8"))


def files_for(spec: dict) -> list[Path]:
    return sorted(Path(p) for pat in spec["files"] for p in glob.glob(str(SNAP / pat)))


def build(tenant: str, spec: dict) -> dict:
    files = files_for(spec)
    if not files:
        raise SystemExit(f"no snapshot files for {tenant}: run `python -m keystone.snapshot` first")
    hist = spec.get("history")
    if not hist:
        return load.load(tenant, files)
    load.load(tenant, files, as_of=hist["as_of"])
    for who in hist["reviews"]:
        workflow.succession_review(tenant, who)
    return load.load(tenant, files, reset=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    db.set_timeout_ms(60000)
    for tenant, spec in manifest().items():
        if db.exists(tenant) and not a.force:
            print(f"{tenant}: exists, skipping (use --force to rebuild)")
            continue
        print(tenant, build(tenant, spec))


if __name__ == "__main__":
    main()
