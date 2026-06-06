// Types mirroring the jupyterlab_acp server payloads.

export interface ModelOption {
  id: string;
  name: string;
}

export interface ModeOption {
  id: string;
  name: string;
}

export interface ConfigOption {
  id: string;
  name: string;
  kind: string | null;
  value: unknown;
}

export interface AcpCommand {
  name: string;
  description: string | null;
}

export interface PermissionOption {
  option_id: string;
  name: string;
  kind: string | null;
}

export interface ToolCallInfo {
  tool_call_id?: string | null;
  title?: string | null;
  kind?: string | null;
  status?: string | null;
}

/** Response of GET /jupyterlab_acp/chats/<id>/state */
export interface SessionStateSnapshot {
  harness_id: string | null;
  available_models?: ModelOption[];
  selected_model_id?: string | null;
  available_modes?: ModeOption[];
  selected_mode_id?: string | null;
  config_options?: ConfigOption[];
  available_commands?: AcpCommand[];
}

/** Entry of GET /jupyterlab_acp/harnesses */
export interface HarnessInfo {
  id: string;
  display_name: string;
  /** Whether the agent's command resolves on the server's PATH. */
  available?: boolean;
}

/** Entry of GET /jupyterlab_acp/registry (the shared ACP Agent Registry). */
export interface RegistryAgent {
  id: string;
  display_name: string;
  description?: string | null;
  icon?: string | null;
  launchable: boolean;
}

/** Entry of GET /jupyterlab_acp/chats — a resumable prior chat. */
export interface ChatRecord {
  chat_id: string;
  harness_id: string;
  session_id: string;
  cwd: string;
  title: string | null;
  created_at: number;
  updated_at: number;
}

/** A message pushed over the per-chat websocket (serialize.update_to_json). */
export interface StreamEvent {
  type: string;
  text?: string;
  mode_id?: string;
  config_options?: ConfigOption[];
  commands?: AcpCommand[];
  request_id?: string;
  tool_call?: ToolCallInfo;
  options?: PermissionOption[];
  /** 'resumed' carries the post-load capability snapshot. */
  state?: SessionStateSnapshot;
  /** 'resume_error' carries the failure message. */
  error?: string;
}
