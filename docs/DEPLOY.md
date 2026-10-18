# Deploying Keystone

The repository builds one container that holds FalkorDB and the app (`Dockerfile`). The graphs are built **while the image is built** and kept as a Redis dump, so a cold start loads them instead of rebuilding: about 1 second on a normal CPU and 12 seconds on a 0.1 CPU free host (measured). The container uses roughly 160 to 200 MB of memory, so a free 512 MB instance is enough.

Public deployments set `KEYSTONE_WRITABLE=sandbox` (already the image default): base graphs are read-only and each visitor gets a private `GRAPH.COPY` sandbox that is deleted after three hours.

## Pick a host

| Host | Cost | Notes |
|---|---|---|
| **Render free web service** (recommended) | free | 512 MB RAM and 0.1 CPU. Sleeps after 15 minutes without traffic and takes about a minute to wake (Render's docs). Render may ask for a card to run a $1 check that is reversed. Steps below. |
| Hugging Face Spaces | **PRO plan required** | Per Hugging Face's docs, Docker and Gradio Spaces need a paid plan; only Static Spaces are free, and they cannot run this backend. `scripts\deploy-hf.ps1` exists if you have PRO. |
| Your own laptop plus a free tunnel | free | `docker compose up --build`, then `cloudflared tunnel --url http://localhost:8000` prints a public https address. It works only while the laptop stays on. |
| Any other Docker host (Fly.io, Railway, Koyeb, a VPS) | usually needs a card | `docker build -t keystone .` then `docker run -p 7860:7860 keystone`. Point the host at port 7860, or set `PORT`. |
| Nothing | free | The rules accept complete local setup instructions plus the demo video if the project cannot be deployed. `docker compose up --build` is the whole procedure (see the README). |

## Render, step by step

1. The code must be on GitHub (public repository).
2. Sign up at render.com with your GitHub account.
3. **New**, then **Blueprint**, pick the `keystone` repository. Render reads `render.yaml` and shows one free web service.
4. It asks for two secrets: `LLM_API_KEY` (your Gemini key) and `LLM2_API_KEY` (your Groq key). Paste them there and nowhere else. Click **Apply**.
5. Wait about five minutes for the build. Your address looks like `https://keystone-xxxx.onrender.com`.
6. Check `https://<your-address>/api/health`: it should list `falkordb` and `pallets`, `"writable":"sandbox"` and `"server_llm":true` with the model names (never the keys).
7. Optional, recommended: a free monitor (for example UptimeRobot) that requests `/api/health` every 5 minutes keeps the service awake, so a judge never waits for a cold start. A free instance has 750 hours a month, enough for one service running all month.

## Settings that matter on a public host

| Variable | Default | What it does |
|---|---|---|
| `KEYSTONE_WRITABLE` | `sandbox` in the image | Base graphs are read-only; only a visitor's private sandbox accepts writes. It also lets `/mcp` answer to the public host name: with any other value the MCP SDK's DNS-rebinding guard accepts only `localhost` and replies HTTP 421 to everything else. |
| `MAX_SANDBOXES` | 40 (20 in `render.yaml`) | How many sandboxes exist at once. If every one was used in the last two minutes a new one is refused with 503 "busy"; otherwise the least recently used is replaced. |
| `MAX_SANDBOXES_PER_CLIENT` | 6 | One address may hold this many sandboxes. Past that it gets 429 unless one of its own has been idle for two minutes, which is then replaced; an active sandbox is never cut off, because an address can be several visitors. |
| `SANDBOX_TTL` | 10800 | Seconds a sandbox may sit idle before it is deleted. |
| `KEYSTONE_TRUSTED_PROXIES` | 1 | How many reverse proxies sit in front of the app. The client address is the `X-Forwarded-For` entry that many hops from the right, which a client cannot forge, and the header is believed only when the connection comes from a private address (your proxy). Use 0 with no proxy. |
| `KEYSTONE_ADMIN_TOKEN` | unset | Needed (as the `x-admin-token` header) to post a drafted issue as a real GitHub issue, and only when `KEYSTONE_GH_REPO` and `GITHUB_TOKEN` are also set. Leave all three unset on a public demo. |

Rate limits apply per client and across everyone, to the API and to `/mcp`.

## Giving the agent a real model

Without a key, visitors get the keyword router (it handled about two thirds of unseen wording in our evaluation, and a model does the tool choosing properly). The app accepts any OpenAI-compatible endpoint, or Anthropic:

- **Groq** (free plan, no card): key at https://console.groq.com/keys. `https://api.groq.com/openai/v1` with `openai/gpt-oss-120b`. Measured: 2 to 3 seconds per question, but the free plan allows 8,000 tokens a minute (about two questions a minute) and 1,000 requests a day.
- **Google Gemini** (free tier, no card): key at https://aistudio.google.com/apikey. `https://generativelanguage.googleapis.com/v1beta/openai/` with `gemini-3.5-flash-lite` (3 to 13 s per question depending on the hour; it served all of our evaluation runs without hitting a daily limit). Do not pick `gemini-3.6-flash` for a public demo: it answered in about 7 s but its free plan allows only 20 requests a day, which ran out within hours; `gemini-3.8-flash` timed out. The 2.5 models are no longer given to new accounts.

The deployed site asks Groq first and Gemini second (`KEYSTONE_LLM_ORDER=2,1`, with the Groq key in `LLM2_API_KEY` and the Gemini key in `LLM_API_KEY`): a visitor who asks a second question inside the same minute is served by Gemini, and if both are limited the router answers instantly.
- Anthropic: `ANTHROPIC_API_KEY` (default model `claude-haiku-5-5`).

The primary model is `LLM_*`; an optional backup is `LLM2_*`. If the primary is rate-limited (free tiers answer 429 when a burst passes their per-minute quota), slow (over 45 s overall) or down, the backup answers, and if both fail the router does. A provider outage never breaks the demo. Keys stay on the server and never reach the browser; the button at the bottom right of the workbench shows MODEL instead of ROUTER, and the TRACE tab says which model answered. Visitors can also paste their own key in the app. Set `KEYSTONE_SERVER_LLM=0` to ignore server keys, and `LLM_REASONING_EFFORT=low` if a reasoning model answers slowly.

## Hugging Face Spaces (only with a PRO plan)

1. Create a Space at huggingface.co/new-space: SDK **Docker**, public, name `keystone`.
2. Create a write token at huggingface.co/settings/tokens.
3. `scripts\deploy-hf.ps1 -User your-hf-username` (Git asks for the username and, as the password, the token). It pushes a copy of the repo with the Space header on `README.md`.
4. Under the Space's Settings, Variables and secrets: add `LLM_API_KEY` as a secret and `LLM_BASE_URL` and `KEYSTONE_MODEL` as variables. The Space restarts by itself.

## Local, with a separate database container

```bash
docker compose up --build            # app http://localhost:8000, FalkorDB Browser http://localhost:3000
```

## Checks after deploying

- `GET /api/health` returns `"writable":"sandbox"`, both tenants, and the model names if you set keys.
- A write against a base graph (for example `succession_review` on `falkordb`) is refused; the same call on your sandbox works.
- `claude mcp add --transport http keystone https://<host>/mcp` lists 15 tools. Check this from a machine that is not the server: it is the one check that only fails on a public host name (HTTP 421 "Invalid Host header" means `KEYSTONE_WRITABLE` is not `sandbox`).
