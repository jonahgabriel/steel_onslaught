/**
 * EventStream test — Task 31.
 *
 * The subscriber receives parsed, typed envelopes for every WebSocket frame.
 * Uses an injected fake socket so no network or browser APIs are needed.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { EventStream, type WebSocketLike } from "../lib/event_stream";
import type { SOEventEnvelope } from "../types";

const FIXTURES_DIR = fileURLToPath(new URL("./fixtures", import.meta.url));

function fixtureText(name: string): string {
  return readFileSync(join(FIXTURES_DIR, `${name}.json`), "utf-8");
}

type MessageListener = (event: { data: unknown }) => void;

class FakeSocket implements WebSocketLike {
  listeners: MessageListener[] = [];
  closed = false;

  addEventListener(_type: "message", listener: MessageListener): void {
    this.listeners.push(listener);
  }

  close(): void {
    this.closed = true;
  }

  emit(data: string): void {
    for (const listener of this.listeners) {
      listener({ data });
    }
  }
}

describe("EventStream", () => {
  it("delivers parsed envelopes to subscribers", () => {
    const socket = new FakeSocket();
    const stream = new EventStream(socket);
    const received: SOEventEnvelope[] = [];
    stream.subscribe((envelope) => received.push(envelope));

    socket.emit(fixtureText("boiler_updated"));
    socket.emit(fixtureText("weapon_fired"));

    expect(received).toHaveLength(2);
    expect(received[0]?.event_type).toBe("boiler_updated");
    expect(received[1]?.event_type).toBe("weapon_fired");
    if (received[1]?.event_type === "weapon_fired") {
      expect(received[1].payload.weapon_id).toBe("module.weapon.machine_gun");
    }
  });

  it("unsubscribe stops delivery", () => {
    const socket = new FakeSocket();
    const stream = new EventStream(socket);
    const received: SOEventEnvelope[] = [];
    const unsubscribe = stream.subscribe((envelope) => received.push(envelope));

    socket.emit(fixtureText("match_tick"));
    unsubscribe();
    socket.emit(fixtureText("match_tick"));

    expect(received).toHaveLength(1);
  });

  it("supports multiple subscribers", () => {
    const socket = new FakeSocket();
    const stream = new EventStream(socket);
    let a = 0;
    let b = 0;
    stream.subscribe(() => {
      a += 1;
    });
    stream.subscribe(() => {
      b += 1;
    });

    socket.emit(fixtureText("match_tick"));

    expect(a).toBe(1);
    expect(b).toBe(1);
  });

  it("throws on a frame that is not a valid envelope (fail fast)", () => {
    const socket = new FakeSocket();
    new EventStream(socket);
    expect(() => socket.emit('{"not": "an envelope"}')).toThrow();
  });

  it("close() closes the underlying socket", () => {
    const socket = new FakeSocket();
    const stream = new EventStream(socket);
    stream.close();
    expect(socket.closed).toBe(true);
  });
});
