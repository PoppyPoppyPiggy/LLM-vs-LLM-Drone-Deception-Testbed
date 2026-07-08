"""core.llm_client — the single async Ollama client shared by all agent roles.

Design:
  - Simple: a single async `chat()` that POSTs to /api/chat and (by default)
    parses the JSON content. Role wrappers (strategic/tactical/observer/attacker)
    call this; they do NOT each re-implement aiohttp.
  - Explicit fallback: on ANY failure (network, HTTP, JSON parse, empty) it returns
    a dict with `_fallback: True` instead of raising. The caller can then count
    fallbacks (the "fallback rate" that evidences "this was a real LLM decision,
    not a default"). Underscore-prefixed meta keys never collide with parsed fields.
  - RAG-agnostic: the client just receives `system`/`user` strings. Whether `user`
    was augmented by a KnowledgeSource (PromptOnly vs RAG) is decided in the AGENT,
    not here.

Return shape (always a dict):
  success: {<parsed JSON fields...>, "_fallback": False, "_latency_ms": float, "_raw": str}
  failure: {"_fallback": True, "_error": str, "_latency_ms": float, "_raw": str}
If parse_json=False: success returns {"_text": str, "_fallback": False, ...}.
"""
from __future__ import annotations
import contextvars
import json
import time
from typing import Any, Dict, Optional

try:
    import aiohttp
except ImportError:  # smoke for non-LLM steps shouldn't hard-fail at import
    aiohttp = None

# ── LLM I/O transcript logging (optional audit trail; agent interfaces UNCHANGED) ──
# A single sink in chat(); role/unit/turn flow via a contextvar set by the runner/episode
# (per-async-task → safe under --concurrency). θ never enters (prompts are θ-free).
_LLM_CTX: "contextvars.ContextVar[Dict[str, Any]]" = contextvars.ContextVar("llm_ctx", default={})
_IO_SINK: Dict[str, Any] = {"fh": None}

# ── deterministic AUDIT mode (debug harness — NOT a science mode) ──
# When on, every LLM call is forced to temperature=0 (greedy) so episode-level chaos from
# temp>0 sampling is removed and the *wiring* effect can be isolated bit-exactly. Real
# experiments keep temp>0 + n≥8 aggregation (this flag does NOT change the methodology).
_DETERMINISTIC: Dict[str, bool] = {"on": False}


def set_deterministic(on: bool) -> None:
    _DETERMINISTIC["on"] = bool(on)


# ── per-call token/latency accumulator (instrumentation; runner resets per episode) ──
_CALLS: list = []


def reset_calls() -> None:
    _CALLS.clear()


def get_calls() -> list:
    return list(_CALLS)


def _record_call(model, ms, data) -> None:
    try:
        ctx = dict(_LLM_CTX.get())
    except Exception:
        ctx = {}
    d = data or {}
    _CALLS.append({"model": model, "role": ctx.get("role"), "turn": ctx.get("turn"),
                   "latency_ms": round(ms, 1),
                   "prompt_tokens": d.get("prompt_eval_count"), "completion_tokens": d.get("eval_count")})

# ── structured-trace hook (core.observability) ──
# A single optional callback chat() invokes after every call (success AND fallback) with
# everything it knows (model/system/user/raw/parsed/tokens/latency/fallback). The observability
# layer enriches it (node_id/role/axes) from its own contextvar and writes the log schema.
# Kept as a registration hook so llm_client never imports observability (no cycle) and the
# default build has ZERO overhead when no run is active.
_TRACE_HOOK = None  # Optional[callable]


def register_trace_hook(fn) -> None:
    global _TRACE_HOOK
    _TRACE_HOOK = fn


def _emit_trace(model, system, user, raw, parsed, ms, fallback, data, options) -> None:
    hook = _TRACE_HOOK
    if hook is None:
        return
    tokens = {"prompt": None, "completion": None}
    if isinstance(data, dict):
        tokens = {"prompt": data.get("prompt_eval_count"),
                  "completion": data.get("eval_count")}
    try:
        hook(model=model, system=system, user=user, raw=raw, parsed=parsed,
             latency_ms=ms, fallback=bool(fallback), tokens=tokens,
             seed=(options or {}).get("seed"))
    except Exception:
        pass  # tracing must never break a run


def set_llm_context(**kw) -> None:
    cur = dict(_LLM_CTX.get()); cur.update(kw); _LLM_CTX.set(cur)


def open_io_log(path) -> None:
    close_io_log()
    _IO_SINK["fh"] = open(path, "a", encoding="utf-8")


def close_io_log() -> None:
    fh = _IO_SINK.get("fh")
    if fh is not None:
        try: fh.close()
        finally: _IO_SINK["fh"] = None


def _emit_io(model, system, user, raw, ms, fallback, options) -> None:
    fh = _IO_SINK.get("fh")
    if fh is None:
        return
    try:
        rec = {**_LLM_CTX.get(), "model": model, "system": system, "user": user,
               "raw_response": raw, "latency_ms": round(ms, 1), "fallback": bool(fallback),
               "seed": (options or {}).get("seed")}
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()
    except Exception:
        pass   # logging must never break a run


class LLMClient:
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434"):
        self._url = ollama_url.rstrip("/") + "/api/chat"
        self._session: Optional["aiohttp.ClientSession"] = None

    async def _ensure(self, timeout: float) -> "aiohttp.ClientSession":
        if aiohttp is None:
            raise RuntimeError("aiohttp not installed; required for LLM calls")
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout))
        return self._session

    async def chat(self, model: str, system: str, user: str, *,
                   format: str = "json", temperature: float = 0.9,
                   timeout: float = 20.0, options: Optional[Dict[str, Any]] = None,
                   parse_json: bool = True) -> Dict[str, Any]:
        opts = {"temperature": temperature}
        if options:
            opts.update(options)
        if _DETERMINISTIC["on"]:                 # audit mode: force greedy for bit-exact isolation
            opts["temperature"] = 0.0
            opts.setdefault("seed", 0)
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False, "options": opts, "keep_alive": "1h",
        }
        if format:
            payload["format"] = format
        t0 = time.time()
        raw = ""
        try:
            session = await self._ensure(timeout)
            async with session.post(self._url, json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()
            raw = (data.get("message") or {}).get("content", "") or ""
            ms = (time.time() - t0) * 1000.0
            _record_call(model, ms, data)            # token/latency instrumentation
            if not parse_json:
                _emit_io(model, system, user, raw, ms, False, options)
                _emit_trace(model, system, user, raw, None, ms, False, data, options)
                return {"_text": raw, "_fallback": False, "_latency_ms": round(ms, 1), "_raw": raw}
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError(f"expected JSON object, got {type(parsed).__name__}")
            _emit_io(model, system, user, raw, ms, False, options)
            _emit_trace(model, system, user, raw, parsed, ms, False, data, options)
            return {**parsed, "_fallback": False, "_latency_ms": round(ms, 1), "_raw": raw}
        except Exception as e:  # network / HTTP / JSON / empty — surface as fallback
            ms = (time.time() - t0) * 1000.0
            _record_call(model, ms, None)            # count fallback calls (latency only)
            _emit_io(model, system, user, raw, ms, True, options)
            _emit_trace(model, system, user, raw, None, ms, True, None, options)
            return {"_fallback": True, "_error": f"{type(e).__name__}: {str(e)[:160]}",
                    "_latency_ms": round(ms, 1), "_raw": raw}

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
