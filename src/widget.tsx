// The ACP chat panel: pick a harness, bind, then chat. Capability selectors
// (model / mode) sit just below the input, Zed-style. Slash-command completion
// is driven by the commands the harness advertises.

import { ReactWidget } from '@jupyterlab/ui-components';
import React, { useEffect, useRef, useState } from 'react';

import { AcpApi } from './api';
import { makeApi, streamUrl } from './server';
import { ChatStream } from './stream';
import {
  AcpCommand,
  HarnessInfo,
  PermissionOption,
  RegistryAgent,
  SessionStateSnapshot,
  StreamEvent,
  ToolCallInfo
} from './types';

interface Message {
  role: 'user' | 'assistant';
  text: string;
}

interface PendingPermission {
  request_id: string;
  tool_call?: ToolCallInfo;
  options: PermissionOption[];
}

function newChatId(): string {
  return `chat-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

function Toolbar(props: {
  api: AcpApi;
  chatId: string;
  state: SessionStateSnapshot;
  setState: React.Dispatch<React.SetStateAction<SessionStateSnapshot | null>>;
}): JSX.Element | null {
  const { api, chatId, state, setState } = props;
  const models = state.available_models ?? [];
  const modes = state.available_modes ?? [];
  if (models.length === 0 && modes.length === 0) {
    return null;
  }
  return (
    <div className="jacp-toolbar">
      {models.length > 0 && (
        <select
          className="jacp-select"
          value={state.selected_model_id ?? ''}
          onChange={async e => {
            const v = e.target.value;
            await api.setModel(chatId, v);
            setState(s => (s ? { ...s, selected_model_id: v } : s));
          }}
        >
          {models.map(m => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      )}
      {modes.length > 0 && (
        <select
          className="jacp-select"
          value={state.selected_mode_id ?? ''}
          onChange={async e => {
            const v = e.target.value;
            await api.setMode(chatId, v);
            setState(s => (s ? { ...s, selected_mode_id: v } : s));
          }}
        >
          {modes.map(m => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

function ChatComponent(): JSX.Element {
  const apiRef = useRef<AcpApi>(makeApi());
  const streamRef = useRef<ChatStream | null>(null);
  const [harnesses, setHarnesses] = useState<HarnessInfo[]>([]);
  const [registry, setRegistry] = useState<RegistryAgent[]>([]);
  const [chatId, setChatId] = useState<string | null>(null);
  const [state, setState] = useState<SessionStateSnapshot | null>(null);
  const [commands, setCommands] = useState<AcpCommand[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [permission, setPermission] = useState<PendingPermission | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [boundAgent, setBoundAgent] = useState<{ name: string; icon?: string | null } | null>(
    null
  );

  useEffect(() => {
    apiRef.current
      .listHarnesses()
      .then(setHarnesses)
      .catch(e => setError(String(e)));
    // The shared ACP registry is best-effort (network); ignore failures.
    apiRef.current
      .listRegistry()
      .then(setRegistry)
      .catch(() => undefined);
    return () => streamRef.current?.close();
  }, []);

  const onEvent = (ev: StreamEvent): void => {
    if (ev.type === 'agent_message_chunk' && ev.text != null) {
      setMessages(prev => {
        const next = prev.slice();
        const last = next[next.length - 1];
        if (last && last.role === 'assistant') {
          next[next.length - 1] = { ...last, text: last.text + ev.text };
        } else {
          next.push({ role: 'assistant', text: ev.text as string });
        }
        return next;
      });
    } else if (ev.type === 'current_mode_update' && ev.mode_id) {
      setState(s => (s ? { ...s, selected_mode_id: ev.mode_id } : s));
    } else if (ev.type === 'config_option_update' && ev.config_options) {
      setState(s => (s ? { ...s, config_options: ev.config_options } : s));
    } else if (ev.type === 'available_commands_update' && ev.commands) {
      setCommands(ev.commands);
    } else if (ev.type === 'permission_request' && ev.request_id) {
      setPermission({
        request_id: ev.request_id,
        tool_call: ev.tool_call,
        options: ev.options ?? []
      });
    } else if (ev.type === 'turn_end') {
      setBusy(false);
    }
  };

  const respondPermission = (optionId: string | null): void => {
    if (permission) {
      streamRef.current?.respondPermission(permission.request_id, optionId);
      setPermission(null);
    }
  };

  const start = async (harnessId: string): Promise<void> => {
    setError(null);
    setStarting(harnessId);
    try {
      const id = newChatId();
      await apiRef.current.bind(id, harnessId);
      const snapshot = await apiRef.current.getState(id);
      const stream = new ChatStream({ url: streamUrl(id), onEvent });
      stream.connect();
      streamRef.current = stream;
      const reg = registry.find(a => a.id === harnessId);
      const local = harnesses.find(h => h.id === harnessId);
      setBoundAgent({
        name: reg?.display_name ?? local?.display_name ?? harnessId,
        icon: reg?.icon ?? null
      });
      setChatId(id);
      setState(snapshot);
      setCommands(snapshot.available_commands ?? []);
    } catch (e) {
      setError(String(e));
      setStarting(null);
    }
  };

  // "New chat" — tear down the current binding and return to the agent picker.
  // A chat is bound to one agent for its life, so starting fresh means picking
  // an agent again (Zed's "+ New chat" affordance).
  const resetToPicker = (): void => {
    streamRef.current?.close();
    streamRef.current = null;
    setChatId(null);
    setState(null);
    setMessages([]);
    setCommands([]);
    setBoundAgent(null);
    setPermission(null);
    setError(null);
    setStarting(null);
    setBusy(false);
    setInput('');
  };

  const send = (): void => {
    const text = input.trim();
    if (!text || !streamRef.current) {
      return;
    }
    setMessages(prev => [...prev, { role: 'user', text }, { role: 'assistant', text: '' }]);
    streamRef.current.prompt(text);
    setInput('');
    setBusy(true);
  };

  if (!chatId) {
    const localIds = new Set(harnesses.map(h => h.id));
    // Primary list: only agents actually installed on the server (their command
    // resolves on PATH). Not-installed built-ins are omitted — like Zed, the
    // picker lists what you can launch, and the registry below is where you add
    // more. Borrow the registry's icon when ids line up.
    const installedHarnesses = harnesses.filter(h => h.available !== false);
    const iconFor = (id: string): string | null => registry.find(r => r.id === id)?.icon ?? null;
    const registryAgents = registry.filter(a => a.launchable && !localIds.has(a.id));
    const isStarting = starting !== null;
    return (
      <div className="jacp-picker">
        <h3>New chat</h3>
        {error && <div className="jacp-error">{error}</div>}
        {installedHarnesses.length > 0 ? (
          <div className="jacp-agent-list">
            {installedHarnesses.map(h => {
              const icon = iconFor(h.id);
              return (
                <button
                  key={h.id}
                  className="jacp-agent-card"
                  disabled={isStarting}
                  onClick={() => start(h.id)}
                >
                  {icon ? (
                    <img className="jacp-agent-icon" src={icon} alt="" />
                  ) : (
                    <span className="jacp-agent-dot" />
                  )}
                  <span className="jacp-agent-text">
                    <span className="jacp-agent-name">
                      {h.display_name}
                      {starting === h.id ? ' · starting…' : ''}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="jacp-hint">
            No ACP agents are installed on the server. Add one below, or install an
            agent CLI (e.g. <code>claude-agent-acp</code> or <code>opencode</code>) on
            the server’s <code>PATH</code>.
          </div>
        )}
        {registryAgents.length > 0 && (
          <details className="jacp-registry">
            <summary className="jacp-registry-head">Add agents · ACP Registry</summary>
            <div className="jacp-registry-sub">
              Run on demand via npx / uvx / downloaded binary. May prompt for the agent’s own sign-in.
            </div>
            <div className="jacp-agent-list">
              {registryAgents.map(a => (
                <button
                  key={a.id}
                  className="jacp-agent-card"
                  disabled={isStarting}
                  title={a.description ?? undefined}
                  onClick={() => start(a.id)}
                >
                  {a.icon ? (
                    <img className="jacp-agent-icon" src={a.icon} alt="" />
                  ) : (
                    <span className="jacp-agent-dot" />
                  )}
                  <span className="jacp-agent-text">
                    <span className="jacp-agent-name">
                      {a.display_name}
                      {starting === a.id ? ' · starting…' : ''}
                    </span>
                    {a.description && <span className="jacp-agent-desc">{a.description}</span>}
                  </span>
                </button>
              ))}
            </div>
          </details>
        )}
      </div>
    );
  }

  // Slash-command completion: when the input is "/" + a word (no space yet),
  // offer matching advertised commands.
  const slashMatch = /^\/(\S*)$/.exec(input);
  const slashCommands = slashMatch
    ? commands.filter(c => c.name.toLowerCase().startsWith(slashMatch[1].toLowerCase()))
    : [];
  const showSlash = !!slashMatch && slashCommands.length > 0;

  return (
    <div className="jacp-chat">
      {boundAgent && (
        <div className="jacp-header">
          {boundAgent.icon ? (
            <img className="jacp-header-icon" src={boundAgent.icon} alt="" />
          ) : (
            <span className="jacp-header-dot" />
          )}
          <span className="jacp-header-name">{boundAgent.name}</span>
          <button
            className="jacp-newchat"
            title="Start a new chat (pick an agent)"
            onClick={resetToPicker}
          >
            + New chat
          </button>
        </div>
      )}
      <div className="jacp-messages">
        {messages.map((m, i) => (
          <div key={i} className={`jacp-msg jacp-${m.role}`}>
            <span className="jacp-role">{m.role}</span>
            <span className="jacp-text">{m.text}</span>
          </div>
        ))}
      </div>
      {permission && (
        <div className="jacp-perm">
          <div className="jacp-perm-title">
            Allow tool: {permission.tool_call?.title ?? permission.tool_call?.kind ?? 'action'}
          </div>
          <div className="jacp-perm-options">
            {permission.options.map(o => (
              <button
                key={o.option_id}
                className={`jacp-perm-btn jacp-perm-${(o.kind ?? '').startsWith('reject') ? 'reject' : 'allow'}`}
                onClick={() => respondPermission(o.option_id)}
              >
                {o.name}
              </button>
            ))}
          </div>
        </div>
      )}
      {busy && !permission && <div className="jacp-status">● thinking…</div>}
      {showSlash && (
        <div className="jacp-slash">
          {slashCommands.map(c => (
            <div
              key={c.name}
              className="jacp-slash-item"
              onMouseDown={e => {
                e.preventDefault();
                setInput(`/${c.name} `);
              }}
            >
              <span className="jacp-slash-name">/{c.name}</span>
              {c.description && <span className="jacp-slash-desc">{c.description}</span>}
            </div>
          ))}
        </div>
      )}
      <div className="jacp-input">
        <textarea
          value={input}
          placeholder="Message the agent…  (type / for commands)"
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button onClick={send}>Send</button>
      </div>
      {state && <Toolbar api={apiRef.current} chatId={chatId} state={state} setState={setState} />}
    </div>
  );
}

export class AcpChatPanel extends ReactWidget {
  constructor() {
    super();
    this.addClass('jacp-panel');
  }

  render(): JSX.Element {
    return <ChatComponent />;
  }
}
