---
title: Architecture
description: How jupyter-acp is put together — module map, data flows, and the non-obvious decisions.
---

# Architecture

`jupyter-acp` is a Jupyter Server extension (Python) plus a JupyterLab
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
   │  REST: /jupyter_acp/harnesses, /registry, /chats/<id>/{bind,state,model,mode,config-option}
   │  WebSocket: /jupyter_acp/chats/<id>/stream   (prompts out, session/update events in)
   ▼
jupyter_acp server extension
   BindingManager → ChatBinding → HarnessSession
                                      │  Agent Client Protocol (JSON-RPC over stdio)
                                      ▼
                              harness subprocess (claude-agent-acp, opencode, …)
                                      │  edits files on disk
                                      ▼
                          jupyter-server-documents → reflects into your open notebook
```

## Python package (`jupyter_acp/`)

| Module | Role |
|---|---|
| `extension.py` | `AcpExtension(ExtensionApp)`: builds the registry (built-in `DEFAULT_HARNESSES` + the `harnesses` config trait), the `BindingManager`, and the remote `AcpRegistry`; registers routes. |
| `registry.py` | `HarnessSpec` (id, display_name, command, args, env) + `HarnessRegistry`; `harness_listing()` adds an `available` flag via `shutil.which`. |
| `acp_registry.py` | Integration with the shared ACP Agent Registry: fetch the index, `spec_from_distribution` (npx/uvx) and `binary_spec` (download+extract per platform). |
| `manager.py` | `BindingManager`: `bind`/`bind_spec` launch a harness + open a session; `close`/`close_all`. |
| `binding.py` | `ChatBinding`: per-chat state machine, draft→bound, immutable after bind. |
| `harness.py` | `HarnessSession`: wraps `acp.spawn_agent_process` + the `initialize`/`new_session`/`prompt`/capability-setter lifecycle. |
| `acp_client.py` | `HarnessClient(acp.Client)`: fans `session/update` to listeners; handles `request_permission` (defer to UI or auto-approve headless). |
| `state.py` | `SessionState`: the capability snapshot (models/modes/config/commands) the UI renders, kept current by setters + reactive updates. |
| `serialize.py` | `update_to_json`: ACP `session/update` → JSON-able dicts for the browser. |
| `handlers.py` | REST `APIHandler`s + the `StreamHandler` websocket. |

## Frontend (`src/`)

| File | Role |
|---|---|
| `index.ts` | Plugin: the inlined `LabIcon`, the sidebar panel, and `New ACP Chat` (main-area tabs). |
| `widget.tsx` | The React panel: harness picker + registry marketplace, capability toolbar, slash completion, permission card, agent header, message stream. |
| `api.ts` | REST client (injectable `fetch`). |
| `stream.ts` | WebSocket client (prompt out; `session/update` events in). |
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

**Marketplace.** `AcpRegistry` fetches the shared index; npx/uvx agents are
runnable immediately, binary agents are downloaded+extracted+cached on first
bind. `bind` falls back to the registry for non-built-in ids, with the **server**
deriving the launch command (the client never supplies an arbitrary command).

**Live notebook editing.** The harness writes the `.ipynb` on disk;
`jupyter-server-documents` detects the out-of-band change and reflects it into
the open notebook's YDoc — no chat-specific machinery. (Validated in
`validation/step0_notebook_reflection.py`.)

## Non-obvious decisions & gotchas

These cost real debugging; they're recorded so they don't have to be rediscovered:

- **REST handlers must be `APIHandler` + `@web.authenticated`.** Plain Tornado
  handlers are XSRF-rejected (403) on POST and aren't token-authed at all.
- **`use_unstable_protocol=True`.** `set_session_model`/`_mode`/`_config_option`
  are unstable-protocol methods in ACP 0.9; both ends must opt in.
- **`bind` passes `cwd=server_root_dir`** (overridable per request) so the
  harness sees the user's files/notebooks — otherwise it inherits the launch dir.
- **Prompts run as asyncio tasks** in the ws handler; awaiting `prompt()` inline
  would block the same connection from delivering the permission response →
  deadlock.
- **Registry fetch sets a `User-Agent`** — the CDN 403s the default urllib UA —
  and runs in a thread so it never blocks the event loop.
- **Build uses the *dev* labextension build.** `build:prod` crashes in the old
  `license-webpack-plugin` pinned by `@jupyterlab/builder`. Install with
  `--no-build-isolation` so the build hook finds `jlpm`. (See issue #1.)
- **Handler tests spawn `python -m jupyter_server`**, not `-m jupyter server` —
  the latter dispatches to whatever `jupyter-server` is first on `PATH`, which
  may be a different interpreter without our extension.

## Testing

47 tests (`pytest`). Unit tests for the pure layers (registry, binding, state,
serializer, permission, capability derivation); integration tests against a real
`jupyter_server` subprocess (REST contract) and a protocol-correct
`tests/fake_agent.py` (the full ACP lifecycle) — no network, no real harness,
no auth required.
