// WebSocket client for a per-chat stream: send prompts, receive session/update
// events (serialized by the server's serialize.update_to_json).
//
// `WebSocketImpl` is injectable for testing.

import { StreamEvent } from './types';

export interface ChatStreamOptions {
  /** ws(s)://.../jupyter_acp/chats/<id>/stream */
  url: string;
  onEvent: (event: StreamEvent) => void;
  WebSocketImpl?: typeof WebSocket;
}

export class ChatStream {
  private opts: ChatStreamOptions;
  private ws: WebSocket | null = null;

  constructor(opts: ChatStreamOptions) {
    this.opts = opts;
  }

  connect(): void {
    const Impl = this.opts.WebSocketImpl ?? WebSocket;
    const ws = new Impl(this.opts.url);
    ws.onmessage = (event: MessageEvent) => {
      try {
        this.opts.onEvent(JSON.parse(event.data) as StreamEvent);
      } catch {
        // ignore malformed frames
      }
    };
    this.ws = ws;
  }

  private send(message: object): void {
    this.ws?.send(JSON.stringify(message));
  }

  prompt(text: string): void {
    this.send({ type: 'prompt', text });
  }

  respondPermission(requestId: string, optionId: string | null): void {
    this.send({ type: 'permission_response', request_id: requestId, option_id: optionId });
  }

  close(): void {
    this.ws?.close();
    this.ws = null;
  }
}
