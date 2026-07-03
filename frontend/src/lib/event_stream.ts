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

export const DEFAULT_WS_URL = "ws://127.0.0.1:8765";

/**
 * Resolve the bridge URL. A `?ws=` query param overrides the default so an
 * operator (or a headless verification harness) can point the deck at an
 * alternate bridge — e.g. `?ws=ws://127.0.0.1:8766` — without a rebuild. Falls
 * back to {@link DEFAULT_WS_URL} outside a browser or when the param is absent.
 */
export function resolveWsUrl(): string {
  if (typeof window === "undefined") return DEFAULT_WS_URL;
  const override = new URLSearchParams(window.location.search).get("ws");
  return override !== null && override !== "" ? override : DEFAULT_WS_URL;
}

export type EnvelopeHandler = (envelope: SOEventEnvelope) => void;

/** Minimal receive-only socket surface (satisfied by the browser WebSocket). */
export interface WebSocketLike {
  addEventListener(type: "message", listener: (event: { data: unknown }) => void): void;
  close(): void;
}

export interface EventStreamOptions {
  /** Injected socket (tests); when omitted a WebSocket to `url` is opened. */
  socket?: WebSocketLike;
  url?: string;
}

export class EventStream {
  private readonly socket: WebSocketLike;
  private readonly handlers = new Set<EnvelopeHandler>();

  constructor(options: EventStreamOptions = {}) {
    this.socket = options.socket ?? new WebSocket(options.url ?? resolveWsUrl());
    this.socket.addEventListener("message", (event) => {
      if (typeof event.data !== "string") {
        throw new Error(`EventStream: expected a text frame, got ${typeof event.data}`);
      }
      const envelope = parseEnvelopeFrame(event.data);
      for (const handler of [...this.handlers]) {
        handler(envelope);
      }
    });
  }

  /** Register a handler; returns an unsubscribe function. */
  subscribe(handler: EnvelopeHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  close(): void {
    this.socket.close();
  }
}
