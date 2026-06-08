---
title: jupyter-sidekick
description: A per-chat, single-agent ACP experience in JupyterLab.
---

# jupyter-sidekick

Jupyter-native access to coding agents over the
[Agent Client Protocol (ACP)](https://agentclientprotocol.com) — a per-chat,
single-agent experience in JupyterLab. Bind a chat to one agent (Claude Code,
OpenCode, Goose, Gemini, and ~30 more from the shared ACP registry); the
toolbar then surfaces *only what that agent advertises over ACP* — its models,
session modes, config options, and slash commands.

```{note}
**Early but working.** Install it, open a chat in the sidebar (or as draggable
main-area tabs), bind an agent, switch models/modes, run slash commands, approve
tool calls, and watch it edit your open notebook live.
```

## What makes it different

- **Harness ≠ model ≠ persona.** Selecting *which agent* runs is separate from
  *which model* it uses; a "persona" is just a Skill/MCP the harness already
  loads — not a bespoke Jupyter object.
- **It edits your live notebook.** The agent writes the `.ipynb` on disk and
  JupyterLab's document layer reflects it into your open view — the reason this
  is an extension and not a terminal beside Jupyter.
- **A marketplace, not a hard-coded list.** It consumes the shared
  [ACP Agent Registry](https://github.com/agentclientprotocol/registry)
  (jointly maintained by Zed + JetBrains), so new agents appear automatically.
- **A thin layer on open standards** — `agent-client-protocol` + `@jupyter/chat`
  + `jupyter-server`, with **no `jupyter_ai_*` dependency.**

## Where to go next

- [Install & use](./install.md)
- [Architecture](./architecture.md) — module map, data flows, gotchas
- [Design decisions](./design-decisions.md) — why it's built ground-up
- [Personas as Skills](./personas-as-skills.md) — the conceptual argument

## Context

This is an independent community project (not affiliated with Project Jupyter or
Zed Industries), built as a working artifact for the conversation in
[`jupyterlab/jupyter-ai#1558`](https://github.com/jupyterlab/jupyter-ai/issues/1558).
The per-chat agent model is inspired by [Zed](https://zed.dev/acp), which
co-created ACP.
