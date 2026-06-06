// REST client for the jupyterlab_acp server extension.
//
// `fetch` and `baseUrl` are injectable so this is unit-testable and so the
// JupyterLab plugin can later supply a `ServerConnection`-aware fetch (XSRF,
// base URL) without changing call sites.

import { HarnessInfo, RegistryAgent, SessionStateSnapshot } from './types';

export interface ApiOptions {
  /** e.g. "/jupyterlab_acp" (no trailing slash required). */
  baseUrl: string;
  fetch?: typeof fetch;
}

export class AcpApi {
  private baseUrl: string;
  private _fetch: typeof fetch;

  constructor(options: ApiOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, '');
    this._fetch = options.fetch ?? globalThis.fetch.bind(globalThis);
  }

  private url(path: string): string {
    return `${this.baseUrl}/${path}`;
  }

  private chat(chatId: string, path: string): string {
    return this.url(`chats/${encodeURIComponent(chatId)}/${path}`);
  }

  private async readJson<T>(res: Response): Promise<T> {
    if (!res.ok) {
      // Surface the server's error message (e.g. "could not launch …") rather
      // than a bare status code.
      let detail = '';
      try {
        const body = await res.json();
        if (body && typeof body.error === 'string') {
          detail = `: ${body.error}`;
        }
      } catch {
        /* no JSON body */
      }
      throw new Error(`Request failed (${res.status})${detail}`);
    }
    return (await res.json()) as T;
  }

  private post(url: string, body: unknown): Promise<Response> {
    return this._fetch(url, { method: 'POST', body: JSON.stringify(body) });
  }

  async listHarnesses(): Promise<HarnessInfo[]> {
    const res = await this._fetch(this.url('harnesses'));
    const body = await this.readJson<{ harnesses: HarnessInfo[] }>(res);
    return body.harnesses;
  }

  async listRegistry(): Promise<RegistryAgent[]> {
    const res = await this._fetch(this.url('registry'));
    const body = await this.readJson<{ agents: RegistryAgent[] }>(res);
    return body.agents;
  }

  async bind(chatId: string, harnessId: string): Promise<{ harness_id: string }> {
    const res = await this.post(this.chat(chatId, 'bind'), { harness_id: harnessId });
    return this.readJson(res);
  }

  async getState(chatId: string): Promise<SessionStateSnapshot> {
    const res = await this._fetch(this.chat(chatId, 'state'));
    return this.readJson<SessionStateSnapshot>(res);
  }

  async setModel(chatId: string, modelId: string): Promise<void> {
    await this.post(this.chat(chatId, 'model'), { model_id: modelId });
  }

  async setMode(chatId: string, modeId: string): Promise<void> {
    await this.post(this.chat(chatId, 'mode'), { mode_id: modeId });
  }

  async setConfigOption(chatId: string, configId: string, value: unknown): Promise<void> {
    await this.post(this.chat(chatId, 'config-option'), { config_id: configId, value });
  }

  /** Tear down the chat's binding + harness subprocess. Idempotent server-side. */
  async close(chatId: string): Promise<void> {
    await this.post(this.chat(chatId, 'close'), {});
  }
}
