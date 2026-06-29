// WebSocket client for a per-chat stream: send prompts, receive session/update
// events (serialized by the server's serialize.update_to_json).
//
// `WebSocketImpl` is injectable for testing.

import { StreamEvent } from './types';

export interface ChatStreamOptions {
  /** ws(s)://.../jupyter_sidekick/chats/<id>/stream */
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

  /** Reply to an fs/read_text_file the server forwarded for the live document. */
  respondFsRead(requestId: string, found: boolean, text: string | null): void {
    this.send({ type: 'fs_read_response', request_id: requestId, found, text });
  }

  /** Reply to an fs/write_text_file: whether we applied it to a live document. */
  respondFsWrite(requestId: string, applied: boolean): void {
    this.send({ type: 'fs_write_response', request_id: requestId, applied });
  }

  close(): void {
    this.ws?.close();
    this.ws = null;
  }
}
