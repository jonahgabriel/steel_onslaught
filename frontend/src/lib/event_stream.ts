/**
 * WebSocket event subscriber — Task 31.
 *
 * Connects to the Python WebSocket bridge (`so serve`, port 8765) and
 * delivers each frame to subscribers as a parsed, typed `SOEventEnvelope`.
 * The stream is a pure projection source: it never sends anything to the
 * server.  Invalid frames throw (fail fast) — the bridge re-emits envelopes
 * byte-identically, so a parse failure means the TS types are stale.
 */
import { parseEnvelopeFrame, type SOEventEnvelope } from "../types";

export type EnvelopeHandler = (envelope: SOEventEnvelope) => void;

type SocketLifecycleHandler = (event: never) => void;

/** Minimal receive-only socket surface (satisfied by the browser WebSocket). */
export interface WebSocketLike {
  addEventListener(type: "message", listener: (event: { data: unknown }) => void): void;
  /** Browser WebSocket lifecycle callbacks are optional so test doubles stay receive-only. */
  onclose?: SocketLifecycleHandler | null;
  onerror?: SocketLifecycleHandler | null;
  /** WebSocket.CONNECTING is 0; absent on minimal test doubles. */
  readonly readyState?: number;
  close(): void;
}

export class EventStream {
  private static readonly RECONNECT_DELAYS_MS = [
    25, 50, 100, 250, 500, 1_000, 2_000, 5_000,
  ] as const;

  private readonly openSocket: () => WebSocketLike;
  private socket: WebSocketLike | null = null;
  private readonly handlers = new Set<EnvelopeHandler>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;
  private closed = false;

  /**
   * Construct a receive-only stream from a socket or a socket factory.
   *
   * Factories allow a transient bridge disconnect to be repaired without
   * rebuilding subscribers or the transport. Replayed envelopes remain safe:
   * MatchTransport owns the canonical deduplication boundary.
   */
  constructor(socketOrFactory: WebSocketLike | (() => WebSocketLike)) {
    this.openSocket =
      typeof socketOrFactory === "function" ? socketOrFactory : () => socketOrFactory;
    this.connect();
  }

  private connect(): void {
    if (this.closed) return;

    let socket: WebSocketLike;
    try {
      socket = this.openSocket();
    } catch {
      // A bridge can disappear between a scheduled retry and the factory
      // call. Keep the stream alive and let the same bounded backoff handle
      // that failure instead of leaving the event feed permanently stalled.
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;
    socket.addEventListener("message", (event) => {
      // A late frame from a socket that failed while a replacement was being
      // opened must not interleave with the replacement stream.
      if (this.closed || this.socket !== socket) return;
      if (typeof event.data !== "string") {
        throw new Error(`EventStream: expected a text frame, got ${typeof event.data}`);
      }
      const envelope = parseEnvelopeFrame(event.data);
      // A valid frame proves that this connection is healthy. Keep the next
      // retry quick if a later bridge restart interrupts it.
      this.reconnectAttempt = 0;
      for (const handler of [...this.handlers]) {
        handler(envelope);
      }
    });
    const handleDisconnect = (): void => {
      if (this.closed || this.socket !== socket) return;
      this.scheduleReconnect();
    };
    socket.onerror = handleDisconnect;
    socket.onclose = handleDisconnect;
  }

  private scheduleReconnect(): void {
    if (this.closed || this.reconnectTimer !== null) return;

    const delay =
      EventStream.RECONNECT_DELAYS_MS[
        Math.min(this.reconnectAttempt, EventStream.RECONNECT_DELAYS_MS.length - 1)
      ];
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      const previous = this.socket;
      this.socket = null;
      // An error may arrive without a close event. Close an established stale
      // socket before replacing it, while avoiding the Chromium warning caused
      // by closing sockets that are still CONNECTING.
      if (previous !== null && previous.readyState !== 0) previous.close();
      this.connect();
    }, delay);
  }

  /** Register a handler; returns an unsubscribe function. */
  subscribe(handler: EnvelopeHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  close(): void {
    this.closed = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    const socket = this.socket;
    this.socket = null;
    // Calling close() while a browser socket is still CONNECTING emits a
    // noisy "closed before the connection was established" warning. The
    // pending socket is intentionally left to the browser's own lifecycle;
    // established sockets are still closed promptly during effect cleanup.
    if (socket !== null && socket.readyState !== 0) socket.close();
  }
}
