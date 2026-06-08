---
title: Architecture
description: How jupyter-acp-chat is put together — module map, data flows, and the non-obvious decisions.
---

# Architecture

`jupyter-acp-chat` is a Jupyter Server extension (Python) plus a JupyterLab
labextension (TypeScript/React), built on three open pieces and **nothing from
the `jupyter_ai_*` stack**:

- [`agent-client-protocol`](https://agentclientprotocol.com) — the official ACP
  Python library; all agent communication goes through it.
- [`@jupyter/chat`](https://github.com/jupyterlab/jupyter-chat) primitives +
  React for the panel.
- `jupyter-server` (+ its collaborative document layer) for routing and the
  live notebook-editing loop.

```
browser (React panel)
   │  REST: /jupyter_acp_chat/harnesses, /registry, /chats/<id>/{bind,state,model,mode,config-option}
   │  WebSocket: /jupyter_acp_chat/chats/<id>/stream   (prompts out, session/update events in)
   ▼
jupyter_acp_chat server extension
   BindingManager → ChatBinding → HarnessSession
                                      │  Agent Client Protocol (JSON-RPC over stdio)
                                      ▼
                              harness subprocess (claude-agent-acp, opencode, …)
                                      │  edits files on disk
                                      ▼
                          jupyter-server-documents → reflects into your open notebook
```

## Python package (`jupyter_acp_chat/`)

| Module | Role |
|---|---|
| `extension.py` | `AcpExtension(ExtensionApp)`: builds the registry (built-in `DEFAULT_HARNESSES` + the `harnesses` config trait), the `BindingManager`, and the remote `AcpRegistry`; registers routes. |
| `registry.py` | `HarnessSpec` (id, display_name, command, args, env) + `HarnessRegistry`; `harness_listing()` adds an `available` flag via `shutil.which`. |
| `acp_registry.py` | Integration with the shared ACP Agent Registry: fetch the index, `spec_from_distribution` (npx/uvx), and `binary_spec` (per-platform download). `_archive_kind` classifies each binary URL — extract an archive, decompress a single `.bz2`/`.gz`/`.xz`, or use a raw executable as-is. |
| `manager.py` | `BindingManager`: `bind`/`bind_spec` launch a harness + open a session; `bind_for_resume` relaunches with a *pending* `load_session` (run later by the stream handler); `close`/`close_all`. |
| `binding.py` | `ChatBinding`: per-chat state machine, draft→bound, immutable after bind. |
| `chat_index.py` | Persisted index of recent chats (harness id, cwd, title, timestamp, ACP session id) backing the picker's **Recent** list and resume. |
| `harness.py` | `HarnessSession`: wraps `acp.spawn_agent_process` + the `initialize`/`new_session`/`load_session`/`prompt`/capability-setter lifecycle. |
| `acp_client.py` | `HarnessClient(acp.Client)`: fans `session/update` to listeners; handles `request_permission` (defer to UI or auto-approve headless). |
| `state.py` | `SessionState`: the capability snapshot (models/modes/config/commands) the UI renders, kept current by setters + reactive updates. |
| `serialize.py` | `update_to_json`: ACP `session/update` → JSON-able dicts for the browser (messages, reasoning, tool calls with diffs/output/locations). |
| `handlers.py` | REST `APIHandler`s (token + XSRF) plus the `StreamHandler` websocket (authed separately — see gotchas). |

## Frontend (`src/`)

| File | Role |
|---|---|
| `index.ts` | Plugin: the inlined `LabIcon`, the sidebar panel, and `New ACP Chat` (main-area tabs). |
| `widget.tsx` | The React panel: harness picker (with registry search + `All`/`Runnable here`/`Needs download` filter), Recent chats, capability toolbar (model/mode/config selectors), slash completion, permission card, agent header, and the transcript — a `TranscriptItem` union of message/thought/tool, where tool cards merge by `tool_call_id` (via `upsertTool`) and render kind glyph, status, diff, output, and file locations. |
| `api.ts` | REST client (injectable `fetch`). |
| `stream.ts` | WebSocket client (prompt out; serialized `session/update` events in as the flat `StreamEvent`). |
| `server.ts` | Builds the API + ws URL from `ServerConnection` (base URL, token, XSRF). |
| `types.ts` | Types mirroring the server payloads. |

## Key data flows

**Bind a chat.** `POST /chats/<id>/bind` → `BindingManager.bind` looks up the
`HarnessSpec` (built-in, or derived from the shared registry), launches the
subprocess in the **server root dir**, runs `initialize` + `new_session`, and
captures the advertised capabilities into `SessionState`.

**Prompt + streaming.** The browser opens the per-chat websocket; a prompt is
run as an **asyncio task** so the handler stays free to receive the user's tool
approval mid-turn. `session/update` events are serialized and pushed back; a
`turn_end` event clears the "thinking" indicator.

**Tool approval.** The harness's `request_permission` is relayed over the ws as
a `permission_request`; the UI shows the harness's own options; the choice comes
back as `permission_response` and resolves the awaiting future (or auto-approves
when no UI is attached).

**Transcript rendering.** `serialize.update_to_json` maps each ACP
`session/update` into a flat JSON `StreamEvent`; the panel folds the stream into
a `TranscriptItem` union — agent text (message), reasoning (thought), and tool
calls (tool). Successive updates for one tool call merge by `tool_call_id`
(`upsertTool`), so a card accretes its status, diff, command output, and file
locations in place rather than appending duplicates.

**Resume a chat.** The picker's **Recent** list comes from `chat_index` (which
stores the ACP `session_id`, `cwd`, and a title — never the transcript). Picking
one calls the `ResumeHandler`, which relaunches the harness and binds with a
*pending* resume; the actual ACP `session/load` runs when the browser opens the
stream, so the harness's own replayed `session/update`s reach the panel — no new
session is created.

**Marketplace.** `AcpRegistry` fetches the shared index; npx/uvx agents are
runnable immediately, binary agents are fetched + cached on first bind (archives
extracted, single-file `.bz2`/`.gz`/`.xz` decompressed, raw executables saved
as-is). The picker offers a search box + a launchability filter over the listing.
`bind` falls back to the registry for non-built-in ids, with the **server**
deriving the launch command (the client never supplies an arbitrary command).

**Live notebook editing.** The harness writes the `.ipynb` on disk;
`jupyter-server-documents` detects the out-of-band change and reflects it into
the open notebook's YDoc — no chat-specific machinery. (Validated in
`validation/step0_notebook_reflection.py`.)

## Non-obvious decisions & gotchas

These cost real debugging; they're recorded so they don't have to be rediscovered:

- **REST handlers must be `APIHandler` + `@web.authenticated`.** Plain Tornado
  handlers are XSRF-rejected (403) on POST and aren't token-authed at all.
- **The websocket can't be an `APIHandler`.** `StreamHandler` is a
  `WebSocketHandler`, so it's authed the way `jupyter_server`'s own sockets are:
  `@ws_authenticated` rejects an unauthenticated upgrade with 403, and
  `WebSocketMixin.check_origin` blocks cross-origin upgrades.
- **`use_unstable_protocol=True`.** `set_session_model`/`_mode`/`_config_option`
  are unstable-protocol methods in ACP 0.9; both ends must opt in.
- **`bind` passes `cwd=server_root_dir`** (overridable per request) so the
  harness sees the user's files/notebooks — otherwise it inherits the launch dir.
- **Prompts run as asyncio tasks** in the ws handler; awaiting `prompt()` inline
  would block the same connection from delivering the permission response →
  deadlock.
- **Registry fetch sets a `User-Agent`** — the CDN 403s the default urllib UA —
  and runs in a thread so it never blocks the event loop.
- **A tool call's first `session/update` carries no `sessionUpdate` tag.** The
  initial `acp` `ToolCall` lacks the discriminator that later updates have, so
  `update_to_json` sets each event's type tag explicitly per class rather than
  reading it off the payload.
- **Production build works via a `yarn patch`.** `build:prod` once crashed in the
  old `license-webpack-plugin` pinned by `@jupyterlab/builder`; a one-line patch
  in `.yarn/patches/` (with a `resolutions` pin) fixes it, so `build_cmd =
  "build:prod"` in `pyproject.toml` ships the minified bundle +
  `third-party-licenses.json`. Install with `--no-build-isolation` so the build
  hook finds `jlpm`.
- **Handler tests spawn `python -m jupyter_server`**, not `-m jupyter server` —
  the latter dispatches to whatever `jupyter-server` is first on `PATH`, which
  may be a different interpreter without our extension.

## Testing

79 tests (`pytest`). Unit tests for the pure layers (registry, binding, state,
serializer, permission, chat index, capability derivation); integration tests
against a real `jupyter_server` subprocess (REST contract) and a
protocol-correct `tests/fake_agent.py` (the full ACP lifecycle, driven by
sentinel prompts such as `EMIT_TOOL`/`EMIT_MODE=`/`EMIT_CONFIG=`) — no network,
no real harness. The frontend has no JS test harness; type-check with `tsc
--noEmit` and confirm the bundle with `jlpm build`.
