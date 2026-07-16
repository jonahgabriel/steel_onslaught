/**
 * Type-parity test — Task 31.
 *
 * Loads every Python-emitted JSON fixture under `./fixtures/` and parses it
 * through the hand-written TS types in `../types.ts`.  Any field added or
 * renamed in a Python event payload breaks this test until the TS type is
 * updated (regenerate fixtures with
 * `uv run python -m tests.fixtures.event_samples`).
 *
 * No `any` casts: `parseEnvelope` consumes `unknown` and constructs fully
 * typed envelopes field by field, rejecting unknown fields.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseEnvelope, SO_EVENT_TYPES } from "../types";

const FIXTURES_DIR = fileURLToPath(new URL("./fixtures", import.meta.url));

const fixtureFiles = readdirSync(FIXTURES_DIR)
  .filter((name) => name.endsWith(".json"))
  .sort();

describe("types parity against Python-emitted fixtures", () => {
  it("has exactly one fixture per SOEventType", () => {
    const expected = [...SO_EVENT_TYPES].map((t) => `${t}.json`).sort();
    expect(fixtureFiles).toEqual(expected);
  });

  for (const file of fixtureFiles) {
    it(`parses ${file} without unknown fields`, () => {
      const raw: unknown = JSON.parse(readFileSync(join(FIXTURES_DIR, file), "utf-8"));
      const envelope = parseEnvelope(raw);
      expect(envelope.event_type).toBe(file.replace(/\.json$/, ""));
      expect(envelope.match_id).toBe("match.fixture.0001");
      expect(envelope.event_id).toHaveLength(26);
    });
  }

  it("rejects an unknown envelope field", () => {
    const raw: unknown = JSON.parse(readFileSync(join(FIXTURES_DIR, "match_tick.json"), "utf-8"));
    const corrupted = { ...(raw as Record<string, unknown>), bogus_field: 1 };
    expect(() => parseEnvelope(corrupted)).toThrow(/bogus_field/);
  });

  it("rejects an unknown nested ONEX envelope field", () => {
    const raw: unknown = JSON.parse(readFileSync(join(FIXTURES_DIR, "match_tick.json"), "utf-8"));
    const record = raw as Record<string, unknown>;
    const envelope = { ...(record["envelope"] as Record<string, unknown>), bogus: 1 };
    expect(() => parseEnvelope({ ...record, envelope })).toThrow(/envelope\.envelope.*bogus/);
  });

  it("rejects an ONEX entity_id that differs from match_id", () => {
    const raw: unknown = JSON.parse(readFileSync(join(FIXTURES_DIR, "match_tick.json"), "utf-8"));
    const record = raw as Record<string, unknown>;
    const envelope = {
      ...(record["envelope"] as Record<string, unknown>),
      entity_id: "match.other.0001",
    };
    expect(() => parseEnvelope({ ...record, envelope })).toThrow(/must equal match_id/);
  });

  it("rejects an unknown payload field on a closed payload", () => {
    const raw: unknown = JSON.parse(
      readFileSync(join(FIXTURES_DIR, "boiler_updated.json"), "utf-8"),
    );
    const record = raw as Record<string, unknown>;
    const payload = { ...(record["payload"] as Record<string, unknown>), bogus: 1 };
    expect(() => parseEnvelope({ ...record, payload })).toThrow(/bogus/);
  });

  it("rejects a missing required payload field", () => {
    const raw: unknown = JSON.parse(
      readFileSync(join(FIXTURES_DIR, "victory_declared.json"), "utf-8"),
    );
    const record = raw as Record<string, unknown>;
    const payload = { ...(record["payload"] as Record<string, unknown>) };
    delete payload["winner_player_id"];
    expect(() => parseEnvelope({ ...record, payload })).toThrow(/winner_player_id/);
  });

  for (const eventType of ["victory_declared", "match_ended"] as const) {
    it(`rejects an unknown ${eventType} terminal field`, () => {
      const raw: unknown = JSON.parse(
        readFileSync(join(FIXTURES_DIR, `${eventType}.json`), "utf-8"),
      );
      const record = raw as Record<string, unknown>;
      const payload = {
        ...(record["payload"] as Record<string, unknown>),
        unexpected: true,
      };
      expect(() => parseEnvelope({ ...record, payload })).toThrow(/unexpected/);
    });
  }
});
