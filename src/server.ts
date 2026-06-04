// Build the REST client and websocket URL from JupyterLab's ServerConnection
// settings (base URL, token, XSRF) so calls hit the authed server correctly.

import { URLExt } from '@jupyterlab/coreutils';
import { ServerConnection } from '@jupyterlab/services';

import { AcpApi } from './api';

const NAMESPACE = 'jupyter_acp';

export function makeApi(): AcpApi {
  const settings = ServerConnection.makeSettings();
  const baseUrl = URLExt.join(settings.baseUrl, NAMESPACE);
  const fetchImpl = ((url: string, init?: RequestInit) =>
    ServerConnection.makeRequest(url, init ?? {}, settings)) as unknown as typeof fetch;
  return new AcpApi({ baseUrl, fetch: fetchImpl });
}

export function streamUrl(chatId: string): string {
  const settings = ServerConnection.makeSettings();
  let url = URLExt.join(
    settings.wsUrl,
    NAMESPACE,
    'chats',
    encodeURIComponent(chatId),
    'stream'
  );
  if (settings.token) {
    url += `?token=${encodeURIComponent(settings.token)}`;
  }
  return url;
}
