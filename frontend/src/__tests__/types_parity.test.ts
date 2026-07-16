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

type MutableObject = Record<string, unknown>;

function loadFixture(eventType: string): MutableObject {
  return JSON.parse(
    readFileSync(join(FIXTURES_DIR, `${eventType}.json`), "utf-8"),
  ) as MutableObject;
}

function objectValue(value: unknown, context: string): MutableObject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${context} is not an object`);
  }
  return value as MutableObject;
}

function arrayValue(value: unknown, context: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new Error(`${context} is not an array`);
  }
  return value;
}

function corruptPayload(
  eventType: string,
  mutate: (payload: MutableObject) => void,
): MutableObject {
  const envelope = loadFixture(eventType);
  const payload = objectValue(envelope["payload"], `${eventType}.payload`);
  mutate(payload);
  return envelope;
}

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

  for (const eventType of [
    "move_intent",
    "weapon_fire_intent",
    "mode_switch_intent",
    "vent_intent",
  ] as const) {
    it(`rejects an unknown ${eventType} field`, () => {
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

  for (const [eventType, requiredField] of [
    ["move_intent", "direction"],
    ["weapon_fire_intent", "weapon_id"],
    ["mode_switch_intent", "target_mode"],
  ] as const) {
    it(`rejects a missing ${eventType}.${requiredField}`, () => {
      const raw: unknown = JSON.parse(
        readFileSync(join(FIXTURES_DIR, `${eventType}.json`), "utf-8"),
      );
      const record = raw as Record<string, unknown>;
      const payload = { ...(record["payload"] as Record<string, unknown>) };
      delete payload[requiredField];
      expect(() => parseEnvelope({ ...record, payload })).toThrow(new RegExp(requiredField));
    });
  }

  for (const [description, eventType, mutate] of [
    [
      "sensor mode",
      "sensor_observation",
      (payload: MutableObject) => {
        payload["mode_estimate"] = "siege";
      },
    ],
    [
      "pilot action",
      "pilot_decision_made",
      (payload: MutableObject) => {
        payload["action"] = "teleport";
      },
    ],
    [
      "pilot reason",
      "pilot_decision_made",
      (payload: MutableObject) => {
        payload["reason_code"] = "because";
      },
    ],
    [
      "considered pilot action",
      "pilot_decision_made",
      (payload: MutableObject) => {
        const considered = arrayValue(payload["considered_actions"], "considered_actions");
        objectValue(considered[0], "considered_actions[0]")["action"] = "teleport";
      },
    ],
    [
      "runtime mode",
      "match_started",
      (payload: MutableObject) => {
        const mechs = arrayValue(payload["mechs"], "mechs");
        objectValue(mechs[0], "mechs[0]")["current_mode"] = "siege";
      },
    ],
    [
      "runtime chassis class",
      "match_started",
      (payload: MutableObject) => {
        const mechs = arrayValue(payload["mechs"], "mechs");
        objectValue(mechs[0], "mechs[0]")["chassis_class"] = "titan";
      },
    ],
    [
      "mode transition",
      "mode_transition_started",
      (payload: MutableObject) => {
        payload["to_mode"] = "siege";
      },
    ],
    [
      "terminal reason",
      "victory_declared",
      (payload: MutableObject) => {
        payload["reason"] = "timeout";
      },
    ],
    [
      "scored kind",
      "match_scored",
      (payload: MutableObject) => {
        payload["kind"] = "steel_onslaught.forged";
      },
    ],
  ] as const) {
    it(`rejects an unknown closed ${description} literal`, () => {
      expect(() => parseEnvelope(corruptPayload(eventType, mutate))).toThrow();
    });
  }

  for (const [description, eventType, mutate] of [
    [
      "boolean integer",
      "mech_spawned",
      (payload: MutableObject) => {
        payload["facing"] = true;
      },
    ],
    [
      "numeric string",
      "movement_resolved",
      (payload: MutableObject) => {
        payload["ticks_consumed"] = "1";
      },
    ],
    [
      "fractional integer",
      "movement_resolved",
      (payload: MutableObject) => {
        payload["ticks_consumed"] = 1.5;
      },
    ],
    [
      "non-positive duration",
      "movement_resolved",
      (payload: MutableObject) => {
        payload["ticks_consumed"] = 0;
      },
    ],
    [
      "out-of-range confidence",
      "sensor_observation",
      (payload: MutableObject) => {
        payload["confidence"] = 1.1;
      },
    ],
    [
      "non-finite probability",
      "weapon_fired",
      (payload: MutableObject) => {
        payload["hit_probability"] = Number.POSITIVE_INFINITY;
      },
    ],
    [
      "negative seed",
      "match_started",
      (payload: MutableObject) => {
        payload["seed"] = -1;
      },
    ],
    [
      "zero maximum ticks",
      "match_started",
      (payload: MutableObject) => {
        payload["max_ticks"] = 0;
      },
    ],
    [
      "hp above hp_max",
      "match_started",
      (payload: MutableObject) => {
        const mechs = arrayValue(payload["mechs"], "mechs");
        objectValue(mechs[0], "mechs[0]")["hp"] = 101;
      },
    ],
    [
      "heat above rupture threshold",
      "match_started",
      (payload: MutableObject) => {
        const mechs = arrayValue(payload["mechs"], "mechs");
        const mech = objectValue(mechs[0], "mechs[0]");
        objectValue(mech["boiler"], "mechs[0].boiler")["heat_current"] = 101;
      },
    ],
    [
      "unpaired mode transition",
      "match_started",
      (payload: MutableObject) => {
        const mechs = arrayValue(payload["mechs"], "mechs");
        objectValue(mechs[0], "mechs[0]")["transition_ticks_remaining"] = 1;
      },
    ],
    [
      "boolean score",
      "match_scored",
      (payload: MutableObject) => {
        const scores = objectValue(payload["scores"], "scores");
        const winner = String(payload["winner_player_id"]);
        objectValue(scores[winner], `scores.${winner}`)["victory"] = true;
      },
    ],
  ] as const) {
    it(`rejects ${description}`, () => {
      expect(() => parseEnvelope(corruptPayload(eventType, mutate))).toThrow();
    });
  }

  for (const value of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    it(`rejects nested pilot action_params non-finite value ${String(value)}`, () => {
      const raw = corruptPayload("pilot_decision_made", (payload) => {
        payload["action_params"] = { nested: [0, { invalid: value }] };
      });
      expect(() => parseEnvelope(raw)).toThrow(/not a JSON value/);
    });
  }

  it("rejects PILOT_DECISION domain-only keys and missing action_params", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("pilot_decision_made", (payload) => {
          payload["schema_version"] = "0.1.0";
        }),
      ),
    ).toThrow(/schema_version/);
    expect(() =>
      parseEnvelope(
        corruptPayload("pilot_decision_made", (payload) => {
          delete payload["action_params"];
        }),
      ),
    ).toThrow(/action_params/);
  });

  it("rejects a PILOT_DECISION whose chosen action was not considered", () => {
    const raw = corruptPayload("pilot_decision_made", (payload) => {
      payload["action"] = "vent";
    });
    expect(() => parseEnvelope(raw)).toThrow(/considered_actions/);
  });

  for (const [description, mutate] of [
    [
      "identical winner and loser IDs",
      (payload: MutableObject) => {
        payload["loser_player_id"] = payload["winner_player_id"];
      },
    ],
    [
      "missing loser score",
      (payload: MutableObject) => {
        const scores = objectValue(payload["scores"], "scores");
        delete scores[String(payload["loser_player_id"])];
      },
    ],
    [
      "flattened/nested score mismatch",
      (payload: MutableObject) => {
        payload["winner_score"] = Number(payload["winner_score"]) + 1;
      },
    ],
    [
      "draw with a winner",
      (payload: MutableObject) => {
        payload["is_draw"] = true;
      },
    ],
    [
      "decisive result without a winner",
      (payload: MutableObject) => {
        payload["winner"] = null;
      },
    ],
    [
      "winner block player mismatch",
      (payload: MutableObject) => {
        objectValue(payload["winner"], "winner")["player_id"] = payload["loser_player_id"];
      },
    ],
    [
      "winner without victory point",
      (payload: MutableObject) => {
        const scores = objectValue(payload["scores"], "scores");
        const winner = String(payload["winner_player_id"]);
        objectValue(scores[winner], `scores.${winner}`)["victory"] = 0;
      },
    ],
  ] as const) {
    it(`rejects contradictory MATCH_SCORED truth: ${description}`, () => {
      expect(() => parseEnvelope(corruptPayload("match_scored", mutate))).toThrow();
    });
  }

  it("normalizes omitted nullable payload fields to null", () => {
    const sensor = parseEnvelope(
      corruptPayload("sensor_observation", (payload) => {
        delete payload["heat_estimate"];
        delete payload["mode_estimate"];
      }),
    );
    expect(sensor.event_type).toBe("sensor_observation");
    if (sensor.event_type === "sensor_observation") {
      expect(sensor.payload.heat_estimate).toBeNull();
      expect(sensor.payload.mode_estimate).toBeNull();
    }

    const move = parseEnvelope(corruptPayload("move_intent", (payload) => delete payload["speed"]));
    expect(move.event_type).toBe("move_intent");
    if (move.event_type === "move_intent") {
      expect(move.payload.speed).toBeNull();
    }

    const weapon = parseEnvelope(
      corruptPayload("weapon_fire_intent", (payload) => delete payload["target_mech_id"]),
    );
    expect(weapon.event_type).toBe("weapon_fire_intent");
    if (weapon.event_type === "weapon_fire_intent") {
      expect(weapon.payload.target_mech_id).toBeNull();
    }

    const damage = parseEnvelope(
      corruptPayload("damage_applied", (payload) => {
        delete payload["source_mech_id"];
        delete payload["radius_cells"];
      }),
    );
    expect(damage.event_type).toBe("damage_applied");
    if (damage.event_type === "damage_applied") {
      expect(damage.payload.source_mech_id).toBeNull();
      expect(damage.payload.radius_cells).toBeNull();
    }

    const destroyed = parseEnvelope(
      corruptPayload("mech_destroyed", (payload) => delete payload["source_mech_id"]),
    );
    expect(destroyed.event_type).toBe("mech_destroyed");
    if (destroyed.event_type === "mech_destroyed") {
      expect(destroyed.payload.source_mech_id).toBeNull();
    }
  });
});
