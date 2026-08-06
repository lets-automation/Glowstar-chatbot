"""
check_lmstudio.py
-----------------
Is a remote LM Studio server actually usable by this app? Run this BEFORE
editing .env - it turns "the bot says sorry" into a named cause.

    venv\\Scripts\\python.exe scripts\\check_lmstudio.py
    venv\\Scripts\\python.exe scripts\\check_lmstudio.py http://192.168.1.14:1235/v1

With no argument it tests LMSTUDIO_BASE_URL from .env.

It checks the five things that have actually broken this setup, in the order
they bite:

  1. reachable      - LM Studio binds 127.0.0.1 and its newer UI has no
                      "serve on local network" switch, so a second PC gets
                      nothing until a portproxy forwards the port.
  2. model id       - LMSTUDIO_MODEL must match exactly; JIT loading reports a
                      mismatch as a generic "Failed to load model".
  3. answers        - proves the model runs at all.
  4. TOOL CALLING   - THE GATE. Every answer in this app comes from run_sql, so
                      a model that can't call tools returns chat and zero data.
                      Uses the app's REAL tool specs, which is what caught LM
                      Studio's engine rejecting union types.
  5. real prompt    - sends the app's actual ~25k-token system prompt. A model
                      loaded at LM Studio's default 8k context fails here, and
                      a 32k context leaves too little room for tool results.
"""

import sys

sys.path.insert(0, __file__.rsplit("scripts", 1)[0])

from openai import OpenAI  # noqa: E402

from app.agent import groq_backend, tools  # noqa: E402
from app.config import settings  # noqa: E402

base_url = (sys.argv[1] if len(sys.argv) > 1 else settings.LMSTUDIO_BASE_URL).rstrip("/")
if not base_url.endswith("/v1"):
    base_url += "/v1"

client = OpenAI(api_key="lmstudio", base_url=base_url, timeout=600)
print(f"target: {base_url}\n")

# 1 + 2 ---------------------------------------------------------------------
try:
    models = client.models.list().data
except Exception as exc:
    print(f"FAIL  not reachable: {str(exc)[:200]}\n")
    print("  -> Turn the server ON in LM Studio (Settings -> Local Model API).")
    print("  -> If it IS on, it is bound to localhost. On the LM Studio PC run as")
    print("     Administrator:")
    print("     netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 "
          "listenport=1235 connectaddress=127.0.0.1 connectport=1234")
    print("     New-NetFirewallRule -DisplayName 'LM Studio' -Direction Inbound "
          "-Protocol TCP -LocalPort 1235 -Action Allow")
    print("     ...then use port 1235 in LMSTUDIO_BASE_URL.")
    raise SystemExit(1)

if not models:
    print("FAIL  server is up but NO model is loaded.")
    raise SystemExit(1)

ids = [m.id for m in models]
print("PASS  reachable. Models loaded:")
for i in ids:
    print(f"        {i}")

# Prefer the configured model; fall back to the first non-embedding one.
model = settings.LMSTUDIO_MODEL
if model not in ids:
    chat_ids = [i for i in ids if "embed" not in i.lower()]
    picked = chat_ids[0] if chat_ids else ids[0]
    print(f"\nWARN  LMSTUDIO_MODEL={model!r} is NOT loaded. Testing {picked!r} instead.")
    print(f"  -> set LMSTUDIO_MODEL={picked} in .env")
    model = picked
print()

# 3 -------------------------------------------------------------------------
try:
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with the single word: ready"}],
        max_tokens=400, temperature=0,
    )
    txt = (r.choices[0].message.content or "").strip()
    reasoning = getattr(r.choices[0].message, "reasoning_content", None)
    print(f"PASS  responds: {txt[:60]!r}")
    if reasoning:
        print(f"  NOTE this is a REASONING model ({len(reasoning)} chars of hidden")
        print("       thinking). It spends part of LLM_MAX_TOKENS before answering,")
        print("       and part of the context window - both need extra headroom.")
except Exception as exc:
    print(f"FAIL  cannot complete: {str(exc)[:200]}")
    raise SystemExit(1)

# 4 -------------------------------------------------------------------------
tools_ok = False
try:
    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You answer ONLY by calling the run_sql tool."},
            {"role": "user", "content": "How many rows are in tblEmployee?"},
        ],
        tools=groq_backend._tools_for_provider(),
        tool_choice="auto", max_tokens=600, temperature=0,
    )
    calls = r.choices[0].message.tool_calls or []
    if calls:
        tools_ok = True
        print("\nPASS  TOOL CALLING works:")
        for c in calls:
            print(f"        {c.function.name}({c.function.arguments[:70]})")
    else:
        print("\nFAIL  TOOL CALLING: model replied with TEXT instead of calling a tool:")
        print(f"        {(r.choices[0].message.content or '')[:200]!r}")
except Exception as exc:
    msg = str(exc)
    print(f"\nFAIL  TOOL CALLING rejected: {msg[:200]}")
    if "filter-mapping" in msg:
        print("  -> LM Studio cannot compile a UNION type in a tool schema. This is")
        print("     supposed to be handled by _collapse_union_types in groq_backend")
        print("     (_UNION_INTOLERANT) - check LLM_PROVIDER is exactly 'lmstudio'.")

if not tools_ok:
    print("\n  -> UNUSABLE for this app: every answer comes from run_sql. Load a")
    print("     tool-capable model (Qwen2.5-7B-Instruct is this project's known-good"
          )
    print("     local model; see LM_STUDIO_SETUP.md).")

# 5 -------------------------------------------------------------------------
q = "Give me an analytics dashboard of production"
system = tools.system_prompt_for(q)
print(f"\n--- real prompt test ({len(system):,} chars, ~{len(system)//4:,} tokens) ---")
try:
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": q}],
        tools=groq_backend._tools_for_provider(),
        tool_choice="auto",
        max_tokens=settings.LLM_MAX_TOKENS, temperature=0,
    )
    ch = r.choices[0]
    calls = ch.message.tool_calls or []
    print(f"PASS  accepted. prompt={r.usage.prompt_tokens:,} "
          f"completion={r.usage.completion_tokens:,} finish={ch.finish_reason}")
    if ch.finish_reason == "length" and not calls:
        print("  WARN ran out of room before calling a tool -> the app shows an EMPTY")
        print("       answer with no SQL. RAISE the model's Context Length in LM")
        print("       Studio (Local Model Defaults), then eject in Loaded Instances.")
        tools_ok = False
    elif calls:
        print(f"  first tool call: {calls[0].function.name}")
except Exception as exc:
    msg = str(exc)
    print(f"FAIL  {msg[:220]}")
    if "context" in msg.lower():
        print("\n  -> Context too small. Set Context Length in LM Studio ->")
        print("     Local Model Defaults (NOT on the running instance), then eject")
        print("     the model in Loaded Instances so JIT reloads it. Our prompt is")
        print("     ~25k tokens; SCHEMA_MAX_COLS does NOT shrink it meaningfully.")
    tools_ok = False

print("\n" + "=" * 60)
print("READY" if tools_ok else "NOT READY - see the FAIL/WARN lines above")
