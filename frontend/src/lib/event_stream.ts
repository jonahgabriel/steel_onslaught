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

/** Minimal receive-only socket surface (satisfied by the browser WebSocket). */
export interface WebSocketLike {
  addEventListener(type: "message", listener: (event: { data: unknown }) => void): void;
  close(): void;
}

export class EventStream {
  private readonly socket: WebSocketLike;
  private readonly handlers = new Set<EnvelopeHandler>();

  constructor(socket: WebSocketLike) {
    this.socket = socket;
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
