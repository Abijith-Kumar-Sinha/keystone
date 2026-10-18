"""Fetch merged-PR history (authors, reviewers, changed files, linked issues) from public GitHub repos.

Usage:  python -m keystone.fetch OWNER/REPO [OWNER/REPO ...]
Token:  $GITHUB_TOKEN, else `gh auth token`. Raw JSON lands in data/raw/ (gitignored).
Only public repo metadata is read. Emails are never requested.
"""
import json, os, subprocess, sys, time
from pathlib import Path

import httpx

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

QUERY = """
query($owner:String!, $name:String!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequests(first: 50, after: $after, states: MERGED, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url mergedAt changedFiles
        author { __typename login }
        mergedBy { login }
        reviews(first: 25) { nodes { state submittedAt author { __typename login } } }
        files(first: 100) { nodes { path } }
        closingIssuesReferences(first: 5) { nodes { number title url } }
      }
    }
  }
}
"""


def token() -> str:
    t = os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def gql(client: httpx.Client, variables: dict) -> dict:
    for attempt in range(6):
        r = client.post("https://api.github.com/graphql", json={"query": QUERY, "variables": variables})
        if r.status_code == 200 and "errors" not in r.json():
            return r.json()["data"]
        time.sleep(2 ** attempt)  # 5xx / secondary rate limit: back off
    raise RuntimeError(f"GitHub GraphQL kept failing for {variables}: {r.status_code} {r.text[:300]}")


def fetch_repo(client: httpx.Client, slug: str) -> list[dict]:
    owner, name = slug.split("/")
    prs, after = [], None
    while True:
        page = gql(client, {"owner": owner, "name": name, "after": after})["repository"]["pullRequests"]
        prs += [p for p in page["nodes"] if p]
        print(f"  {slug}: {len(prs)} PRs", flush=True)
        if not page["pageInfo"]["hasNextPage"]:
            return prs
        after = page["pageInfo"]["endCursor"]


def fetch_codeowners(slugs: list[str]) -> None:
    """Real CODEOWNERS per repo (public raw files), cached so actions.py never needs the network at runtime."""
    from concurrent.futures import ThreadPoolExecutor
    out = RAW.parent / "codeowners.json"
    have = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}

    def one(slug: str):
        for path in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
            try:
                r = httpx.get(f"https://raw.githubusercontent.com/{slug}/HEAD/{path}", timeout=30)
                if r.status_code == 200:
                    return slug, [path, r.text]
            except httpx.HTTPError:
                pass
        return slug, None

    todo = [s for s in slugs if s not in have]
    with ThreadPoolExecutor(8) as ex:
        have.update(dict(ex.map(one, todo)))
    out.write_text(json.dumps(have, indent=1), encoding="utf-8")
    print(f"codeowners: {sum(1 for v in have.values() if v)}/{len(have)} repos have one")


def main(slugs: list[str]) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"Authorization": f"bearer {token()}"}, timeout=90) as client:
        for slug in slugs:
            out = RAW / (slug.replace("/", "__") + ".json")
            if out.exists():
                print(f"skip {slug} (cached {out.name}); delete it to refetch")
                continue
            prs = fetch_repo(client, slug)
            out.write_text(json.dumps(prs), encoding="utf-8")
            print(f"saved {slug}: {len(prs)} PRs", flush=True)
    fetch_codeowners(slugs)


if __name__ == "__main__":
    main(sys.argv[1:])
