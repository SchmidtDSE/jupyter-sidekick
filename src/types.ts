// Types mirroring the jupyter_acp server payloads.

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

/** Response of GET /jupyter_acp/chats/<id>/state */
export interface SessionStateSnapshot {
  harness_id: string | null;
  available_models?: ModelOption[];
  selected_model_id?: string | null;
  available_modes?: ModeOption[];
  selected_mode_id?: string | null;
  config_options?: ConfigOption[];
}

/** Entry of GET /jupyter_acp/harnesses */
export interface HarnessInfo {
  id: string;
  display_name: string;
}

/** A message pushed over the per-chat websocket (serialize.update_to_json). */
export interface StreamEvent {
  type: string;
  text?: string;
  mode_id?: string;
  config_options?: ConfigOption[];
  commands?: { name: string; description: string | null }[];
}
