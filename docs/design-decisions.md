# ACP-in-Jupyter: design-decision record

**Status:** Decisions made; repo created at `SchmidtDSE/jupyter-acp-chat`; design spec next.
**Date:** 2026-06-03
**Author:** Carl Boettiger (cboettig)
**Supersedes the architecture of:** the proof-of-concept "bridge" at
[`cboettig/jupyter-ai@acp-bridge-impl:jupyter-ai-acp-bridge/`](https://github.com/cboettig/jupyter-ai/tree/acp-bridge-impl/jupyter-ai-acp-bridge),
which remains valid as a working artifact and empirical reference.
**Related:** [`jupyterlab/jupyter-ai#1558`](https://github.com/jupyterlab/jupyter-ai/issues/1558),
[Persona API v0.1 proposal](https://jupyter-ai.readthedocs.io/en/v3/proposals/persona-api-v0.1.html),
the [ACP bridge design spec](https://github.com/cboettig/jupyter-ai/blob/main/docs/superpowers/specs/2026-04-28-acp-bridge-design.md)
and the [personas-as-skills essay](personas-as-skills.md).

This is a concise record of the design forks we hit while deciding how to carry
the ACP-in-Jupyter work forward, the choice made at each, and why. It is a
decision log, not a full spec — the spec for the chosen direction ("B") follows
separately.

## Context

We have a working PoC (`jupyter-ai-acp-bridge`) that gives Jupyter AI a
Zed-style per-chat harness binding. It lives inside a fork of
`jupyterlab/jupyter-ai` and depends on the upstream `jupyter_ai_*` stack. In
parallel, the upstream Persona API v0.1 proposal has moved toward our position
— it now defines a persona's `context` as *system prompt + MCP servers + skill
paths* and adds a no-code `.persona.md` authoring path — but still wraps that
bundle in a Jupyter-specific format anchored to a `BasePersona` Python class,
and still binds model selection into the persona.

The remaining disconnect is narrow and nameable, which is what made it worth
resolving the forks below.

## The forks

### 1. What *is* a persona — and does the abstraction add capability?

- **Upstream framing:** a persona is an object that *collects* a system prompt,
  some MCP servers, and some skills. (Implicitly: MCP ≈ "tools," skills ≈
  "prompts," persona ≈ the bundle of them.)
- **Our position:** MCP and Skills are *each already complete context bundles*.
  MCP has prompts, tools, **and** resources as first-class primitives; a Skill
  has instructions (prompt), `scripts/` (executable tools), and
  `references/`/`assets/`. A coherent persona frequently collapses to a *single*
  MCP server or a *single* skill. "Collect several of these under a new
  Jupyter-specific object" therefore adds **packaging, not capability** — and
  the harness already loads skills and MCP natively.
- **Decision:** anchor the design on *persona-is-delivered-as-a-skill-(or-MCP)
  that the harness already loads*, not as a new Python class or a new
  `.persona.md` file format. Authoring a persona should mean writing a
  `SKILL.md` / configuring an MCP server — portable across the open ecosystem —
  not subclassing `BasePersona`.

### 2. How to advance the argument with the upstream team

- **Options:** (a) keep arguing in the #1558 thread; (b) build a working
  artifact that demonstrates the alternative; (c) both.
- **Decision:** both, with the artifact in service of the argument. Make the
  precise field-by-field case that `.persona.md` is structurally a `SKILL.md`
  with renamed fields, *and* ship an artifact whose dependency graph proves the
  persona layer isn't load-bearing.
- **Why:** v0.1 already conceded the substance; the surviving gap is
  invent-a-new-format vs. reuse-the-open-format. That is winnable in the thread,
  and a working artifact makes it undeniable rather than rhetorical.

### 3. Where the code lives

- **Finding:** the three upstream packages we build on — `jupyter_ai_acp_client`,
  `jupyter_ai_router`, `jupyter_ai_persona_manager` — are **pure upstream PyPI
  deps, unmodified**; nothing in our tree patches them. The only code that is
  ours is the bridge package.
- **Decision:** move to a **dedicated repository** (working name `jupyter-acp-chat`),
  not a package inside the fork.
- **Why:** escapes the "they forked jupyter-ai" framing, lets us shed the
  persona-suppression hacks entirely, and gives a clean install-and-try artifact
  to point people at. Extraction is near-mechanical since we carry no
  fork-local patches.

### 4. Dependency posture — drop-in vs. ground-up

- **Option A (drop-in):** rename the bridge to `jupyter-acp-chat`, keep depending on
  the upstream `jupyter_ai_*` stack. Cheap; works today.
- **Option B (ground-up):** depend on none of the `jupyter_ai_*` modules; build
  the Zed-like interface on the harness-agnostic primitives directly.
- **Decision:** **B**, realized as a hybrid — build on `agent-client-protocol`
  (Python) + `@jupyter/chat` (the standalone React widget lib) + the
  `jupyter-server` document layer; write our own Jupyter glue on top; drop the
  `jupyter_ai_*` trio. Use A only as a throwaway demo if one is needed before B
  is ready. (Exactly how we relate to `jupyter-ai-acp-client` is Fork 6.)
- **Why:** A permanently couples us to the abstraction we are arguing against,
  and inherits the brittle router-integration layer (observer-ordering traps,
  divergent-history YDoc recovery, slash-command reconstruction, three-site
  persona suppression, Lumino private-field surgery) — all of which exists only
  to coexist with the persona/router model. That is a worse maintenance surface
  than building fresh on the open protocol library. B's dependency graph (a
  `pip show` with no persona-manager) *is* the argument.

### 5. Chat interface and session persistence

- **Key distinction:** two different "collaboration" needs were being conflated.
  - **(a) Chat-transcript collaboration** — `.chat` files, YChat multiplayer,
    the router. Needed only for multi-user chat.
  - **(b) Live-document collaboration** — the RTC layer on the *notebook* you
    have open. This is the actual reason to be in Jupyter, and it is independent
    of (a).
- **Decision:** drop (a) — no `.chat`/multiplayer/router; lean on the harness's
  native ACP `session/load` save-and-resume for persistence. Keep (b).
- **Gated on Step 0** (below), which confirmed (b) is independent of the chat
  stack.

### 6. How we relate to `jupyter-ai-acp-client` — build on, vendor, or reference?

- **Finding (per-module coupling audit):** the line between "ACP core" and
  "Jupyter glue" inside `jupyter-ai-acp-client` is *not* clean. Of its 11
  modules, the four central ones — `base_acp_persona.py`, `default_acp_client.py`
  (the `JaiAcpClient` "core" itself), `tool_call_manager.py`, and `routes.py` —
  import `jupyter_ai_persona_manager` and/or `jupyterlab_chat`. Only
  `permission_manager.py`, `terminal_manager.py`, and `tool_call_renderer.py`
  are surface-clean. So "vendor the core, replace the wrapper" is a fuzzy line:
  the core *is* the coupled part.
- **The real shared foundation is one layer down:** `agent-client-protocol`
  (0.9.x), the official ACP Python library. `jupyter-ai-acp-client` is itself
  just that library + Jupyter glue, most of it chat/persona-coupled. The
  capability setters we need (`set_session_model` / `_mode` / `_config`) live on
  the library's connection object directly, so we don't need its wrapper.
- **Decision:** depend on **`agent-client-protocol`**, *not* on
  `jupyter-ai-acp-client`. We do **not** depend on, fork, or vendor that package;
  we treat it as a *reference implementation*. We write our own thin glue
  (subprocess launch, session/binding, our chat transport) on the open library.
  Where a *surface-clean* helper genuinely saves work — e.g. `terminal_manager`
  (ACP terminal tool-use is fiddly) — we port that specific file with
  attribution, rather than taking a dependency. Do **not** repackage
  `jupyter_ai_router` — it is intrinsically jupyterlab-chat-shaped and falls away
  once (a) is dropped.
- **Why this over vendoring:** it removes the confusion on both fronts. The
  codebase has one clean line — everything is ours, on the open protocol lib —
  and the pitch is crisp: *"we depend on the same open ACP library Zed publishes;
  we wrote the Jupyter integration fresh."* That is a stronger form of the
  clean-dependency-graph argument than "we vendored a stripped fork."

### Step 0 — does dropping the chat stack cost us live notebook editing?

- **Question:** when an ACP harness edits a notebook on disk, does that reflect
  into the user's open, live JupyterLab notebook view — and does that depend on
  the chat/persona stack?
- **Finding (from `jupyter-server-documents` 0.2.0 source):** **No dependency on
  the chat stack.** `YRoomFileAPI._watch_file()` polls `last_modified` (adaptive
  interval, min 0.5s); `_check_file()` detects out-of-band writes and calls
  `_reload_content_inplace()`, which applies the new disk content to the live
  YDoc and broadcasts the diff to connected clients via the `_on_ydoc_update`
  observer. This is the document/RTC layer, entirely independent of
  `jupyter_ai_*` and `jupyterlab-chat`.
- **Conclusion:** **green light for B**, now **live-validated** (2026-06-03).
  Harness writes `.ipynb` on disk → open notebook updates in ~0.5s–a few
  seconds, regardless of the chat layer.
- **Known caveats to carry into the spec:**
  - Polling latency grows with notebook size (interval = save-duration × 5,
    bounded below by 0.5s).
  - `_reload_content_inplace` replaces the whole YDoc source — concurrent
    user + harness edits are last-writer-wins. Fine for "ask the agent, wait";
    a hazard for genuine simultaneous editing.
  - Reverse staleness: the harness reads the on-disk file, so unsaved in-browser
    YDoc edits must be autosaved before the harness reads, or it sees stale
    content.
  - **Live validation (2026-06-03):** with all-real `jupyter-server-documents`
    components (`AsyncFileContentsManager` + `ArbitraryFileIdManager` +
    `OutputsManager` + `YRoomFileAPI`), an out-of-band `.ipynb` write was
    reflected into the live YDoc by the autonomous `_watch_file` poll in ~0.75s,
    producing broadcast-worthy `Doc` diffs. Reproducible at
    [`validation/step0_notebook_reflection.py`](../validation/step0_notebook_reflection.py).
    Still untested (lower-risk, separable): a real websocket-connected browser
    client receiving the broadcast, and a *real ACP harness* performing the
    write — which also raises the distinct question of how well harnesses edit
    `.ipynb` JSON.

## Decisions at a glance

| Fork | Decision |
|---|---|
| What a persona is | Delivered as a Skill / MCP the harness already loads; not a new class or `.persona.md` format |
| Advancing the argument | Make the SKILL.md-vs-`.persona.md` case in #1558 **and** ship the artifact as evidence |
| Where code lives | Dedicated repo (`jupyter-acp-chat`), not in the fork |
| Dependency posture | Ground-up (B): `agent-client-protocol` + `@jupyter/chat` + `jupyter-server`; no `jupyter_ai_*` |
| Chat & persistence | Drop `.chat`/multiplayer/router; use harness-native ACP session resume; keep notebook RTC |
| `jupyter-ai-acp-client` | Don't depend on / fork / vendor it; build on `agent-client-protocol` directly; reference it and port only surface-clean helpers (e.g. `terminal_manager`) with credit |
| Step 0 (value prop) | Confirmed independent of the chat stack — B keeps live notebook editing |

## Open questions for the B spec

- The chat surface without `jupyterlab-chat`: how much of `@jupyter/chat` we
  reuse vs. a minimal custom transport, and how ACP `session/load` maps onto
  reopening a chat.
- The shape of our own ACP glue on `agent-client-protocol`: subprocess launch +
  lifecycle (incl. the PDEATHSIG leak fix), session/binding, and how harness
  output (messages, tool calls, terminals) maps onto our chat transport.
- Which surface-clean helpers from `jupyter-ai-acp-client` (e.g.
  `terminal_manager`) are worth porting-with-credit vs. writing fresh.
- Whether/how to surface harness-advertised skills as the persona authoring
  surface in-product (vs. relying purely on on-disk skill folders).
- One live end-to-end validation of the Step 0 reload path with a real harness
  (`claude-agent-acp` / `opencode`, both present in the dev env).
