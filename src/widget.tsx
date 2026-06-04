// The ACP chat panel: pick a harness, bind, then chat. Capability selectors
// (model / mode) sit just below the input, Zed-style. Slash-command completion
// is driven by the commands the harness advertises.

import { ReactWidget } from '@jupyterlab/ui-components';
import React, { useEffect, useRef, useState } from 'react';

import { AcpApi } from './api';
import { makeApi, streamUrl } from './server';
import { ChatStream } from './stream';
import { AcpCommand, HarnessInfo, SessionStateSnapshot, StreamEvent } from './types';

interface Message {
  role: 'user' | 'assistant';
  text: string;
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
  const [chosen, setChosen] = useState<string>('');
  const [chatId, setChatId] = useState<string | null>(null);
  const [state, setState] = useState<SessionStateSnapshot | null>(null);
  const [commands, setCommands] = useState<AcpCommand[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiRef.current
      .listHarnesses()
      .then(hs => {
        setHarnesses(hs);
        if (hs[0]) {
          setChosen(hs[0].id);
        }
      })
      .catch(e => setError(String(e)));
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
    }
  };

  const start = async (): Promise<void> => {
    setError(null);
    const id = newChatId();
    await apiRef.current.bind(id, chosen);
    const snapshot = await apiRef.current.getState(id);
    const stream = new ChatStream({ url: streamUrl(id), onEvent });
    stream.connect();
    streamRef.current = stream;
    setChatId(id);
    setState(snapshot);
    setCommands(snapshot.available_commands ?? []);
  };

  const send = (): void => {
    const text = input.trim();
    if (!text || !streamRef.current) {
      return;
    }
    setMessages(prev => [...prev, { role: 'user', text }, { role: 'assistant', text: '' }]);
    streamRef.current.prompt(text);
    setInput('');
  };

  if (!chatId) {
    return (
      <div className="jacp-picker">
        <h3>New ACP chat</h3>
        {error && <div className="jacp-error">{error}</div>}
        <select value={chosen} onChange={e => setChosen(e.target.value)}>
          {harnesses.map(h => (
            <option key={h.id} value={h.id}>
              {h.display_name}
            </option>
          ))}
        </select>
        <button onClick={() => start().catch(e => setError(String(e)))} disabled={!chosen}>
          Start
        </button>
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
      <div className="jacp-messages">
        {messages.map((m, i) => (
          <div key={i} className={`jacp-msg jacp-${m.role}`}>
            <span className="jacp-role">{m.role}</span>
            <span className="jacp-text">{m.text}</span>
          </div>
        ))}
      </div>
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
