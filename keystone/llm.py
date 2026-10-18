"""Tiny tool-calling LLM client: Anthropic Messages API or any OpenAI-compatible endpoint (Groq, Gemini, OpenRouter, OpenAI...).

The model only ever *chooses tools and phrases the answer*. It never writes Cypher; see tools.py.
No key configured -> agent.py falls back to its deterministic router, so the product still works.
"""
import json
import os
import re
import time

import httpx

DEFAULTS = {
    "anthropic": {"model": "claude-haiku-5-5", "base_url": "https://api.anthropic.com"},
    "openai": {"model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1"},
}


def from_env() -> dict | None:
    """Server-side config. A key is never sent to the browser; BYO keys arrive per-request and are never stored or logged."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return {"kind": "anthropic", "key": os.environ["ANTHROPIC_API_KEY"], "model": os.environ.get("KEYSTONE_MODEL")}
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY"):
        return {"kind": "openai", "key": os.environ.get("LLM_API_KEY") or os.environ["OPENAI_API_KEY"],
                "model": os.environ.get("KEYSTONE_MODEL"), "base_url": os.environ.get("LLM_BASE_URL")}
    return None


def _args(raw) -> dict:
    """Tool arguments arrive as a JSON string (OpenAI style) or an object; anything else becomes no arguments."""
    if isinstance(raw, dict):
        return raw
    try:
        out = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


def chain_from_env() -> list[dict]:
    """Server-side models in order of preference: the primary (LLM_* or ANTHROPIC_API_KEY), then an optional backup (LLM2_*),
    used when the primary is slow, overloaded or down. Keys are never sent to the browser."""
    out = [c for c in (from_env(),) if c]
    if os.environ.get("LLM2_API_KEY"):
        out.append({"kind": "openai", "key": os.environ["LLM2_API_KEY"], "model": os.environ.get("LLM2_MODEL"), "base_url": os.environ.get("LLM2_BASE_URL")})
    return out


class Provider:
    def __init__(self, kind: str, key: str, model: str | None = None, base_url: str | None = None):
        d = DEFAULTS.get(kind) or DEFAULTS["openai"]
        self.kind, self.key = kind, key
        self.model = model or d["model"]
        self.base = (base_url or d["base_url"]).rstrip("/")
        self.local = any(h in self.base for h in ("localhost", "127.0.0.1"))
        self.effort = os.environ.get("LLM_REASONING_EFFORT") or None   # optional: "low" makes reasoning models answer faster
        self.timeout = 600 if self.local else 30          # a local thinking model can reason for minutes on a laptop GPU; a hosted one should not

    def _post(self, url: str, headers: dict, payload: dict) -> "httpx.Response":
        """POST with a short retry for transient overload (5xx) and a rate limit that clears in seconds. A longer 429 is returned at once:
        the caller moves on to the backup model instead of waiting out a per-minute quota."""
        for attempt in range(3):
            r = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
            if r.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
                return r
            try:
                wait = float(r.headers.get("retry-after", ""))
            except ValueError:
                wait = 1.0 * (attempt + 1)
            if r.status_code == 429 and wait > 3:
                return r
            time.sleep(min(wait, 3))
        return r

    def start(self, system: str, history: list[dict], question: str) -> dict:
        msgs = [{"role": m["role"], "content": m["content"]} for m in history[-6:]] + [{"role": "user", "content": question}]
        return {"system": system, "messages": msgs}

    def step(self, st: dict, tools: list[dict]) -> tuple[str, list[tuple[str, str, dict]]]:
        if self.kind == "anthropic":
            r = self._post(f"{self.base}/v1/messages", {"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                           {"model": self.model, "max_tokens": 1500, "system": st["system"], "messages": st["messages"],
                            "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]})
            r.raise_for_status()
            blocks = r.json()["content"]
            st["messages"].append({"role": "assistant", "content": blocks})
            return ("".join(b["text"] for b in blocks if b["type"] == "text"),
                    [(b["id"], b["name"], b["input"]) for b in blocks if b["type"] == "tool_use"])
        effort = {"reasoning_effort": "none"} if self.local else {"reasoning_effort": self.effort} if self.effort else {}   # local thinking models answer faster without it
        r = self._post(f"{self.base}/chat/completions", {"Authorization": f"Bearer {self.key}"},
                       {"model": self.model, "tool_choice": "auto", **effort,
                        "messages": [{"role": "system", "content": st["system"]}] + st["messages"],
                        "tools": [{"type": "function", "function": t} for t in tools]})
        r.raise_for_status()
        m = r.json()["choices"][0]["message"]
        text = re.sub(r"<think>.*?</think>", "", m.get("content") or "", flags=re.S).strip()   # reasoning models may inline their thoughts
        st["messages"].append({**{k: v for k, v in m.items() if k in ("role", "tool_calls") and v is not None}, "content": text})
        return (text, [(c["id"], c["function"]["name"], _args(c["function"]["arguments"])) for c in m.get("tool_calls") or []])

    def add_results(self, st: dict, results: list[tuple[str, str]]) -> None:
        if self.kind == "anthropic":
            st["messages"].append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": i, "content": c} for i, c in results]})
        else:
            st["messages"] += [{"role": "tool", "tool_call_id": i, "content": c} for i, c in results]
