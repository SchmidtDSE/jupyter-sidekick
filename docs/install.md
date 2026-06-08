---
title: Install & use
---

# Install & use

Requires JupyterLab ≥ 4.2 and at least one ACP agent on your `PATH` — e.g.
`claude-agent-acp` (Claude Code) or `opencode` — or any agent from the
[ACP registry](https://github.com/agentclientprotocol/registry), which runs on
demand via `npx`/`uvx`/downloaded binary.

```bash
pip install jupyter-acp-chat
```

The wheel ships the prebuilt labextension, so that's all you need — launch
`jupyter lab` and you're set.

## From source (development)

JupyterLab is needed at build time to compile the extension.

```bash
git clone https://github.com/SchmidtDSE/jupyter-acp-chat
cd jupyter-acp-chat
pip install jupyterlab hatchling hatch-jupyter-builder editables   # build tooling (jlpm)
jlpm install && jlpm build
pip install -e . --no-build-isolation                              # hook reuses the built JS
jupyter labextension develop --overwrite .
```

```{note}
`--no-build-isolation` is needed because the labextension build hook calls
`jlpm` (from JupyterLab) at install time, which pip's isolated build env lacks.
```

## Use

```bash
jupyter lab
```

- Click the **chat icon** in the left sidebar for the docked assistant, or
  **New ACP Chat** in the launcher to open a chat as a main-area tab (open as
  many as you like; drag/split them, file browser stays docked).
- Pick a **Configured** agent, or browse the **ACP Registry** cards and click
  one to launch it on demand.
- The **model / mode** selectors below the input reflect what the agent
  advertises; type **`/`** for its slash commands.
- When the agent wants a tool, an **approval card** appears — allow or reject.
  Approve a notebook edit and watch the open `.ipynb` update live.

## Configuring agents

Built-in harnesses can be extended or overridden from `jupyter_server_config.py`:

```python
c.AcpExtension.harnesses = [
    {"id": "my-agent", "display_name": "My Agent",
     "command": "my-agent", "args": ["--acp"], "env": {"API_KEY": "..."}},
]
```

## Develop

```bash
python -m pytest        # 47 tests: ACP core, capabilities, binding, handlers
                        # (real-server), serializer, permission, registry
jlpm build:lib          # typecheck the frontend
```
