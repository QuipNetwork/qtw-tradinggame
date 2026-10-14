// A WebSocket that transparently reconnects with capped exponential backoff and
// guards JSON parsing, reporting connection-status transitions to the caller.
// Channel-agnostic so it serves agent updates today and the TV /tv/events feed
// later (see real.ts subscribeAgent).

import type { ConnectionStatus } from './types';

type Handlers<T> = {
  onMessage: (data: T) => void;
  onStatus?: (status: ConnectionStatus) => void;
};

const MAX_BACKOFF_MS = 10_000;

export class ReconnectingSocket<T> {
  private socket: WebSocket | null = null;
  private closedByUs = false;
  private attempt = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly url: string,
    private readonly handlers: Handlers<T>,
    // Sec-WebSocket-Protocol values; the agent channel carries its token here.
    private readonly protocols?: string[],
  ) {
    this.connect();
  }

  private connect(): void {
    this.handlers.onStatus?.(this.attempt === 0 ? 'connecting' : 'reconnecting');
    let socket: WebSocket;
    try {
      socket = new WebSocket(this.url, this.protocols);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.addEventListener('open', () => {
      this.attempt = 0;
      this.handlers.onStatus?.('live');
    });
    socket.addEventListener('message', event => {
      try {
        this.handlers.onMessage(JSON.parse(event.data) as T);
      } catch {
        // Drop a malformed frame rather than tearing down the whole stream.
      }
    });
    socket.addEventListener('close', () => {
      if (!this.closedByUs) this.scheduleReconnect();
    });
    socket.addEventListener('error', () => {
      // 'error' is always followed by 'close'; let close drive the reconnect.
      socket.close();
    });
  }

  private scheduleReconnect(): void {
    if (this.closedByUs) return;
    this.handlers.onStatus?.('reconnecting');
    const delay = Math.min(MAX_BACKOFF_MS, 500 * 2 ** this.attempt);
    this.attempt += 1;
    this.retryTimer = setTimeout(() => this.connect(), delay);
  }

  close(): void {
    this.closedByUs = true;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.handlers.onStatus?.('closed');
    this.socket?.close();
  }
}
