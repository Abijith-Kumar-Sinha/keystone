"""Compress data/raw/*.json (fetched by keystone.fetch) into the committed data/snapshot/*.json.gz."""
import gzip
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    out = ROOT / "data" / "snapshot"
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted((ROOT / "data" / "raw").glob("*.json")):
        with open(f, "rb") as src, gzip.open(out / (f.name + ".gz"), "wb", compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)
        print(f"{f.name}: {f.stat().st_size // 1024} KB -> {(out / (f.name + '.gz')).stat().st_size // 1024} KB")
