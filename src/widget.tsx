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
  ChatRecord,
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

/** Compact relative time for the recent-chats list (epoch seconds → "2h ago"). */
function relTime(epochSeconds: number): string {
  const s = Math.max(0, Date.now() / 1000 - epochSeconds);
  if (s < 60) {
    return 'just now';
  }
  const m = Math.floor(s / 60);
  if (m < 60) {
    return `${m}m ago`;
  }
  const h = Math.floor(m / 60);
  if (h < 24) {
    return `${h}h ago`;
  }
  return `${Math.floor(h / 24)}d ago`;
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
  // Agents (e.g. claude-agent-acp) often advertise `model`/`mode` as config
  // options too; those already have dedicated selectors, so render only the
  // *other* config options here (toggles, selects like an effort level, …).
  const configOptions = (state.config_options ?? []).filter(c => {
    if (c.id === 'model' && models.length > 0) {
      return false;
    }
    if (c.id === 'mode' && modes.length > 0) {
      return false;
    }
    return true;
  });

  const setConfig = async (id: string, value: unknown): Promise<void> => {
    await api.setConfigOption(chatId, id, value);
    setState(s =>
      s
        ? {
            ...s,
            config_options: (s.config_options ?? []).map(c =>
              c.id === id ? { ...c, value } : c
            )
          }
        : s
    );
  };

  if (models.length === 0 && modes.length === 0 && configOptions.length === 0) {
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
      {configOptions.map(opt =>
        opt.options && opt.options.length > 0 ? (
          <select
            key={opt.id}
            className="jacp-select"
            title={opt.name}
            value={opt.value == null ? '' : String(opt.value)}
            onChange={e => setConfig(opt.id, e.target.value)}
          >
            {opt.options.map(o => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        ) : opt.kind === 'boolean' ? (
          <label key={opt.id} className="jacp-config-bool" title={opt.name}>
            <input
              type="checkbox"
              checked={opt.value === true}
              onChange={e => setConfig(opt.id, e.target.checked)}
            />
            {opt.name}
          </label>
        ) : null
      )}
    </div>
  );
}

function ChatComponent(): JSX.Element {
  const apiRef = useRef<AcpApi>(makeApi());
  const streamRef = useRef<ChatStream | null>(null);
  // Mirrors `chatId` so the (deps-[]) unmount cleanup can close the *current*
  // binding rather than the value captured at mount.
  const chatIdRef = useRef<string | null>(null);
  const [harnesses, setHarnesses] = useState<HarnessInfo[]>([]);
  const [registry, setRegistry] = useState<RegistryAgent[]>([]);
  const [recents, setRecents] = useState<ChatRecord[]>([]);
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
    apiRef.current
      .listChats()
      .then(setRecents)
      .catch(() => undefined);
    // On dispose, close the stream and tell the server to tear down the binding
    // (and its harness subprocess) so it isn't orphaned.
    return () => {
      streamRef.current?.close();
      const id = chatIdRef.current;
      if (id) {
        apiRef.current.close(id).catch(() => undefined);
      }
    };
  }, []);

  // Keep chatIdRef in sync for the unmount cleanup above.
  useEffect(() => {
    chatIdRef.current = chatId;
  }, [chatId]);

  // Append a streamed chunk to the last message of the same role, or start a
  // new one. Used for live agent output and for replayed turns on resume.
  const appendChunk = (role: Message['role'], text: string): void => {
    setMessages(prev => {
      const next = prev.slice();
      const last = next[next.length - 1];
      if (last && last.role === role) {
        next[next.length - 1] = { ...last, text: last.text + text };
      } else {
        next.push({ role, text });
      }
      return next;
    });
  };

  const onEvent = (ev: StreamEvent): void => {
    if (ev.type === 'agent_message_chunk' && ev.text != null) {
      appendChunk('assistant', ev.text);
    } else if (ev.type === 'user_message_chunk' && ev.text != null) {
      // Replayed prior user turns when resuming a session.
      appendChunk('user', ev.text);
    } else if (ev.type === 'resumed') {
      // load_session finished; adopt the now-populated capability snapshot.
      if (ev.state) {
        setState(ev.state);
        setCommands(ev.state.available_commands ?? []);
      }
    } else if (ev.type === 'resume_error') {
      setError(ev.error ?? 'Could not resume this chat.');
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

  // Reopen a prior chat. The server relaunches the harness and (once this stream
  // attaches) reloads the session; the agent replays the transcript, which
  // arrives as user/agent chunks, and a "resumed" event fills the toolbar.
  const resume = async (rec: ChatRecord): Promise<void> => {
    setError(null);
    setStarting(rec.chat_id);
    try {
      await apiRef.current.resume(rec.chat_id);
      const snapshot = await apiRef.current.getState(rec.chat_id);
      const stream = new ChatStream({ url: streamUrl(rec.chat_id), onEvent });
      stream.connect();
      streamRef.current = stream;
      const reg = registry.find(a => a.id === rec.harness_id);
      const local = harnesses.find(h => h.id === rec.harness_id);
      setBoundAgent({
        name: reg?.display_name ?? local?.display_name ?? rec.harness_id,
        icon: reg?.icon ?? null
      });
      setChatId(rec.chat_id);
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
    const prev = chatId;
    streamRef.current?.close();
    streamRef.current = null;
    // Tear down the prior binding so its harness subprocess doesn't leak; the
    // next chat binds a fresh chat_id. Fire-and-forget — idempotent server-side.
    if (prev) {
      apiRef.current.close(prev).catch(() => undefined);
    }
    // Refresh the recent list so the chat we just left shows up.
    apiRef.current
      .listChats()
      .then(setRecents)
      .catch(() => undefined);
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
        {recents.length > 0 && (
          <div className="jacp-recents">
            <div className="jacp-recents-head">Recent</div>
            <div className="jacp-agent-list">
              {recents.map(rec => {
                const agentName =
                  registry.find(a => a.id === rec.harness_id)?.display_name ??
                  harnesses.find(h => h.id === rec.harness_id)?.display_name ??
                  rec.harness_id;
                return (
                  <button
                    key={rec.chat_id}
                    className="jacp-agent-card"
                    disabled={isStarting}
                    title={rec.cwd}
                    onClick={() => resume(rec)}
                  >
                    <span className="jacp-recent-glyph">↺</span>
                    <span className="jacp-agent-text">
                      <span className="jacp-agent-name">
                        {rec.title ?? '(untitled chat)'}
                        {starting === rec.chat_id ? ' · resuming…' : ''}
                      </span>
                      <span className="jacp-agent-desc">
                        {agentName} · {relTime(rec.updated_at)}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
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
