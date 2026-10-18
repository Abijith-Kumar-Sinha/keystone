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

## Giving the agent a real model

Without a key, visitors get the keyword router (it handled about two thirds of unseen wording in our evaluation, and a model does the tool choosing properly). The app accepts any OpenAI-compatible endpoint, or Anthropic:

- **Google Gemini** (free tier, no card): key at https://aistudio.google.com/apikey. `LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/` and `KEYSTONE_MODEL=gemini-3.5-flash-lite` (fast and available when we tested; `gemini-3.8-flash` was overloaded). The 2.5 models are no longer given to new accounts.
- **Groq** (free plan): key at https://console.groq.com/keys. `LLM_BASE_URL=https://api.groq.com/openai/v1` and `KEYSTONE_MODEL=openai/gpt-oss-120b`.
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
- `claude mcp add --transport http keystone https://<host>/mcp` lists 15 tools.
