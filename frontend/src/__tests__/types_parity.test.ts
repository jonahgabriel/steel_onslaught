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
import { parseEnvelope, parseHistoricalReplayEnvelope, SO_EVENT_TYPES } from "../types";

const FIXTURES_DIR = fileURLToPath(new URL("./fixtures", import.meta.url));

const fixtureFiles = readdirSync(FIXTURES_DIR)
  .filter((name) => name.endsWith(".json"))
  .sort();

const CURRENT_LIVE_MECH_FIELDS = [
  "schema_version",
  "kind",
  "mech_id",
  "player_id",
  "side",
  "loadout_id",
  "pilot_id",
  "chassis_id",
  "chassis_class",
  "sensor_ids",
  "gizmo_ids",
  "base_speed",
  "position",
  "facing",
  "speed",
  "hp",
  "hp_max",
  "armor_value",
  "armor_max",
  "alive",
  "pilot_alive",
  "current_mode",
  "mode_lock_until",
  "transition_ticks_remaining",
  "transition_to_mode",
  "sensor_dropout_ticks_remaining",
  "mode_switch_disabled_until",
  "weapon_cooldowns",
  "evasion",
  "accuracy_penalty_next_fire",
  "jamming_intensity",
  "under_sensor_lock",
  "boiler",
  "redline_consecutive_ticks",
  "overloaded",
  "overloaded_consecutive_ticks",
] as const;

const CURRENT_LIVE_ARENA_FIELDS = [
  "schema_version",
  "kind",
  "arena_id",
  "size",
  "spawn_a",
  "spawn_b",
  "obstacles",
  "sudden_death_start_tick",
  "sudden_death_damage_base",
] as const;

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

  it("accepts finite nonnegative integer envelope ordering fields", () => {
    const raw = loadFixture("match_tick");
    const parsed = parseEnvelope({ ...raw, tick: 42, sequence_in_tick: 7 });
    expect(parsed.tick).toBe(42);
    expect(parsed.sequence_in_tick).toBe(7);
  });

  for (const field of ["tick", "sequence_in_tick"] as const) {
    it(`rejects missing envelope ${field}`, () => {
      const raw = loadFixture("match_tick");
      delete raw[field];
      expect(() => parseEnvelope(raw)).toThrow(new RegExp(field));
    });

    it.each([
      ["negative", -1],
      ["fractional", 0.5],
      ["NaN", Number.NaN],
      ["positive infinity", Number.POSITIVE_INFINITY],
    ])(`rejects %s envelope ${field}`, (_description, value) => {
      expect(() => parseEnvelope({ ...loadFixture("match_tick"), [field]: value })).toThrow(
        new RegExp(field),
      );
    });
  }

  it("rejects an unknown payload field on a closed payload", () => {
    const raw: unknown = JSON.parse(
      readFileSync(join(FIXTURES_DIR, "boiler_updated.json"), "utf-8"),
    );
    const record = raw as Record<string, unknown>;
    const payload = { ...(record["payload"] as Record<string, unknown>), bogus: 1 };
    expect(() => parseEnvelope({ ...record, payload })).toThrow(/bogus/);
  });

  it("keeps card event payloads closed and semantically strict", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("hand_dealt", (payload) => {
          payload["unknown"] = true;
        }),
      ),
    ).toThrow(/unknown/);

    expect(() =>
      parseEnvelope(
        corruptPayload("plan_committed", (payload) => {
          const registers = arrayValue(payload["registers"], "registers");
          objectValue(registers[0], "registers[0]")["unknown"] = true;
        }),
      ),
    ).toThrow(/unknown/);

    expect(() =>
      parseEnvelope(
        corruptPayload("register_resolved", (payload) => {
          payload["outcome"] = "invented";
        }),
      ),
    ).toThrow(/outcome/);

    expect(() =>
      parseEnvelope(
        corruptPayload("cards_discarded", (payload) => {
          payload["card_ids"] = ["not-a-card-id"];
        }),
      ),
    ).toThrow(/card/);

    expect(() =>
      parseEnvelope(
        corruptPayload("plan_committed", (payload) => {
          const registers = arrayValue(payload["registers"], "registers");
          objectValue(registers[1], "registers[1]")["register_index"] = 0;
        }),
      ),
    ).toThrow(/duplicate/);

    expect(() =>
      parseEnvelope(
        corruptPayload("cards_discarded", (payload) => {
          payload["card_ids"] = [];
        }),
      ),
    ).toThrow(/at least one/);

    expect(() =>
      parseEnvelope(
        corruptPayload("register_resolved", (payload) => {
          payload["outcome"] = "resolved";
          payload["card_id"] = null;
        }),
      ),
    ).toThrow(/requires a card/);
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

  it.each([
    "11111111111141118111111111111111",
    "{11111111-1111-4111-8111-111111111111}",
  ])("rejects non-canonical runtime status command UUID spellings: %s", (lastCommandId) => {
    expect(() =>
      parseEnvelope(
        corruptPayload("runtime_status_changed", (payload) => {
          payload["last_command_id"] = lastCommandId;
        }),
      ),
    ).toThrow(/last_command_id.*UUID/);
  });

  it("rejects an empty runtime status owner", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("runtime_status_changed", (payload) => {
          payload["owner_id"] = "";
        }),
      ),
    ).toThrow(/owner_id.*non-empty/);
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

  for (const eventType of [
    "llm_completion_requested",
    "llm_completion_resolved",
    "llm_completion_failed",
  ] as const) {
    it(`rejects an unknown ${eventType} field`, () => {
      expect(() =>
        parseEnvelope(
          corruptPayload(eventType, (payload) => {
            payload["unexpected"] = true;
          }),
        ),
      ).toThrow(/unexpected/);
    });
  }

  it("rejects missing and coerced LLM completion evidence fields", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("llm_completion_requested", (payload) => {
          delete payload["provider_id"];
        }),
      ),
    ).toThrow(/provider_id/);
    expect(() =>
      parseEnvelope(
        corruptPayload("llm_completion_resolved", (payload) => {
          payload["prompt_tokens"] = "64";
        }),
      ),
    ).toThrow(/prompt_tokens/);
    expect(() =>
      parseEnvelope(
        corruptPayload("llm_completion_resolved", (payload) => {
          delete payload["cost_usd"];
        }),
      ),
    ).toThrow(/cost_usd|cost field/);
  });

  it.each([
    "malformed_json",
    "unknown_action",
    "action_unavailable",
    "invalid_action_parameters",
  ])("accepts closed LLM semantic failure code %s", (semanticFailureCode) => {
    const parsed = parseEnvelope(
      corruptPayload("llm_completion_failed", (payload) => {
        payload["semantic_failure_code"] = semanticFailureCode;
        payload["finish_reason"] = "x".repeat(64);
      }),
    );
    if (parsed.event_type !== "llm_completion_failed") {
      throw new Error("wrong LLM failure event type");
    }
    expect(parsed.payload.semantic_failure_code).toBe(semanticFailureCode);
    expect(parsed.payload.finish_reason).toHaveLength(64);
  });

  it("accepts explicit null LLM failure metadata for a non-semantic failure", () => {
    const parsed = parseEnvelope(
      corruptPayload("llm_completion_failed", (payload) => {
        payload["reason_code"] = "provider_error";
        payload["semantic_failure_code"] = null;
        payload["model"] = null;
        payload["finish_reason"] = null;
        payload["prompt_tokens"] = null;
        payload["completion_tokens"] = null;
        payload["cost_usd"] = null;
      }),
    );
    if (parsed.event_type !== "llm_completion_failed") {
      throw new Error("wrong LLM failure event type");
    }
    expect(parsed.payload.semantic_failure_code).toBeNull();
    expect(parsed.payload.finish_reason).toBeNull();
  });

  it("requires a semantic failure code exactly for invalid_response", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("llm_completion_failed", (payload) => {
          payload["semantic_failure_code"] = null;
        }),
      ),
    ).toThrow(/semantic_failure_code/);
    expect(() =>
      parseEnvelope(
        corruptPayload("llm_completion_failed", (payload) => {
          payload["reason_code"] = "consumer_error";
        }),
      ),
    ).toThrow(/semantic_failure_code/);
  });

  it("rejects an unknown LLM semantic failure code", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("llm_completion_failed", (payload) => {
          payload["semantic_failure_code"] = "forged_semantic_code";
        }),
      ),
    ).toThrow(/semantic_failure_code/);
  });

  it.each([
    "semantic_failure_code",
    "model",
    "finish_reason",
    "prompt_tokens",
    "completion_tokens",
    "cost_usd",
  ])("rejects missing required nullable LLM failure field %s", (field) => {
    expect(() =>
      parseEnvelope(
        corruptPayload("llm_completion_failed", (payload) => {
          delete payload[field];
        }),
      ),
    ).toThrow(new RegExp(field));
  });

  it.each([
    ["empty", ""],
    ["unsafe", "unsafe reason"],
    ["too long", "x".repeat(65)],
  ])("rejects %s LLM failure finish_reason", (_description, finishReason) => {
    expect(() =>
      parseEnvelope(
        corruptPayload("llm_completion_failed", (payload) => {
          payload["finish_reason"] = finishReason;
        }),
      ),
    ).toThrow(/finish_reason/);
  });

  it("preserves explicit current-live RED/BLUE mech sides", () => {
    const current = parseEnvelope(loadFixture("match_started"));
    if (current.event_type !== "match_started") throw new Error("wrong current event type");
    expect(current.payload.mechs.map((mech) => mech.side)).toEqual(["red", "blue"]);
  });

  it.each(CURRENT_LIVE_MECH_FIELDS)("rejects missing current-live mech field %s", (field) => {
    expect(() =>
      parseEnvelope(
        corruptPayload("match_started", (payload) => {
          const mechs = arrayValue(payload["mechs"], "mechs");
          delete objectValue(mechs[0], "mechs[0]")[field];
        }),
      ),
    ).toThrow(new RegExp(field));
  });

  it("rejects missing current-live nested runtime fields", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("match_started", (payload) => {
          const mechs = arrayValue(payload["mechs"], "mechs");
          delete objectValue(mechs[0], "mechs[0]")["under_sensor_lock"];
        }),
      ),
    ).toThrow(/under_sensor_lock/);
  });

  it.each(CURRENT_LIVE_ARENA_FIELDS)("rejects missing current-live arena field %s", (field) => {
    expect(() =>
      parseEnvelope(
        corruptPayload("match_started", (payload) => {
          delete objectValue(payload["arena"], "arena")[field];
        }),
      ),
    ).toThrow(new RegExp(field));
  });

  it("rejects invalid current-live arena bounds and duplicate obstacles", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("match_started", (payload) => {
          objectValue(payload["arena"], "arena")["obstacles"] = [{ x: 40, y: 0 }];
        }),
      ),
    ).toThrow(/inside the arena/);
    expect(() =>
      parseEnvelope(
        corruptPayload("match_started", (payload) => {
          objectValue(payload["arena"], "arena")["obstacles"] = [
            { x: 4, y: 4 },
            { x: 4, y: 4 },
          ];
        }),
      ),
    ).toThrow(/duplicate/);
  });

  it("rejects a current-live roster without exactly two canonical seats", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("match_started", (payload) => {
          arrayValue(payload["mechs"], "mechs").pop();
        }),
      ),
    ).toThrow(/exactly two mechs/);
  });

  it("rejects current-live mech positions outside arena bounds", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("match_started", (payload) => {
          const mech = objectValue(arrayValue(payload["mechs"], "mechs")[0], "mechs[0]");
          mech["position"] = { x: 40, y: 5 };
        }),
      ),
    ).toThrow(/position must lie inside the arena/);
  });

  it("rejects current-live mech positions on arena obstacles", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("match_started", (payload) => {
          objectValue(payload["arena"], "arena")["obstacles"] = [{ x: 6, y: 5 }];
          const mech = objectValue(arrayValue(payload["mechs"], "mechs")[0], "mechs[0]");
          mech["position"] = { x: 6, y: 5 };
        }),
      ),
    ).toThrow(/position must not occupy an arena obstacle/);
  });

  it("binds current-live mech positions to spawn points in canonical roster order", () => {
    expect(() =>
      parseEnvelope(
        corruptPayload("match_started", (payload) => {
          const mechs = arrayValue(payload["mechs"], "mechs");
          const first = objectValue(mechs[0], "mechs[0]");
          const second = objectValue(mechs[1], "mechs[1]");
          const firstPosition = first["position"];
          first["position"] = second["position"];
          second["position"] = firstPosition;
        }),
      ),
    ).toThrow(/mechs\[0\]\.position must equal arena\.spawn_a/);
  });

  it("projects only sanctioned fields for versioned historical replay", () => {
    const historicalStarted = corruptPayload("match_started", (payload) => {
      const mechs = arrayValue(payload["mechs"], "mechs");
      delete objectValue(mechs[0], "mechs[0]")["side"];
      delete payload["arena"];
    });
    const started = parseHistoricalReplayEnvelope(historicalStarted);
    if (started.event_type !== "match_started") throw new Error("wrong historical event type");
    expect(started.payload.mechs[0]?.side).toBe("neutral");
    expect(started.payload.arena.arena_id).toBe("historical_open_field");
    expect(started.payload.mechs.map((mech) => mech.position)).toEqual([
      started.payload.arena.spawn_a,
      started.payload.arena.spawn_b,
    ]);

    const historicalResolved = corruptPayload("llm_completion_resolved", (payload) => {
      delete payload["cost_usd"];
    });
    const resolved = parseHistoricalReplayEnvelope(historicalResolved);
    if (resolved.event_type !== "llm_completion_resolved") {
      throw new Error("wrong historical event type");
    }
    expect(resolved.payload.cost_usd).toBeNull();

    const unexpected = corruptPayload("llm_completion_resolved", (payload) => {
      delete payload["cost_usd"];
      payload["unexpected"] = true;
    });
    expect(() => parseHistoricalReplayEnvelope(unexpected)).toThrow(/unexpected/);
  });

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

  it("accepts closed selected-launch and human-command provenance", () => {
    const started = corruptPayload("match_started", (payload) => {
      payload["launch_provenance"] = {
        schema_version: "1",
        kind: "steel_onslaught.match_launch_provenance",
        match_id: "match.01JABCDE0123456789ABCDEFGX",
        launch_command_id: "11111111-1111-4111-8111-111111111111",
        launch_command_sha256: "1".repeat(64),
        overlay_sha256: "2".repeat(64),
        roster_id: "roster.playable.local",
        roster_sha256: "3".repeat(64),
        seat_assignments: [
          {
            kind: "human",
            side: "red",
            player_id: "player.red",
            option_id: "player_option.browser_human",
            loadout_id: "loadout.playable.red_light",
            pilot_spec_id: "pilot.human.browser",
            option_sha256: "4".repeat(64),
            human_identity_id: "human_identity.local_browser",
            input_source: "browser_command",
          },
          {
            kind: "model",
            side: "blue",
            player_id: "player.blue",
            option_id: "player_option.local_model",
            loadout_id: "loadout.playable.blue_heavy",
            pilot_spec_id: "pilot.model.local",
            option_sha256: "5".repeat(64),
            model_identity_id: "model_identity.local_model",
            persona_id: "persona.local_model",
            input_source: "llm_completion",
          },
        ],
      };
      payload["card_rule_pack_provenance"] = {
        schema_version: "0.1.0",
        kind: "steel_onslaught.card_rule_pack",
        pack_id: "rules.card_programming_v1",
        handlers: [
          {
            schema_version: "0.1.0",
            kind: "steel_onslaught.card_rule_handler",
            handler_id: "prefer_attack_cards",
            version: "v1.0.0",
            implementation_sha256: "7".repeat(64),
          },
        ],
        content_sha256: "8".repeat(64),
      };
    });
    const decision = corruptPayload("pilot_decision_made", (payload) => {
      payload["decision_source"] = {
        kind: "human",
        input_source: "browser_command",
        command_id: "22222222-2222-4222-8222-222222222222",
        turn_id: "turn.match_01jabcde.tick_000001.red",
        observation_sha256: "6".repeat(64),
      };
    });

    expect(parseEnvelope(started).payload).toHaveProperty("launch_provenance");
    expect(parseEnvelope(started).payload).toHaveProperty("card_rule_pack_provenance");
    expect(parseEnvelope(decision).payload).toHaveProperty("decision_source");
  });

  it("accepts the explicit human-input pilot reason", () => {
    const decision = corruptPayload("pilot_decision_made", (payload) => {
      payload["reason_code"] = "human_input";
    });

    expect(parseEnvelope(decision).payload).toHaveProperty("reason_code", "human_input");
  });

  it("rejects unknown or contradictory provenance fields", () => {
    const decision = corruptPayload("pilot_decision_made", (payload) => {
      payload["decision_source"] = {
        kind: "human",
        input_source: "llm_completion",
        command_id: "22222222-2222-4222-8222-222222222222",
        turn_id: "turn.match_01jabcde.tick_000001.red",
        observation_sha256: "6".repeat(64),
        unexpected: true,
      };
    });

    expect(() => parseEnvelope(decision)).toThrow(/unexpected|browser_command/);
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

  it("accepts an explicit null match tick cap but rejects an omitted key", () => {
    const uncapped = parseEnvelope(
      corruptPayload("match_started", (payload) => {
        payload["max_ticks"] = null;
      }),
    );
    expect(uncapped.event_type).toBe("match_started");
    if (uncapped.event_type === "match_started") {
      expect(uncapped.payload.max_ticks).toBeNull();
    }
    expect(() =>
      parseEnvelope(
        corruptPayload("match_started", (payload) => {
          delete payload["max_ticks"];
        }),
      ),
    ).toThrow(/max_ticks/);
  });

  it("projects neutral sudden-death defaults onto an old arena snapshot", () => {
    const raw = loadFixture("match_started");
    const payload = objectValue(raw["payload"], "match_started.payload");
    const arena = objectValue(payload["arena"], "match_started.payload.arena");
    delete arena["sudden_death_start_tick"];
    delete arena["sudden_death_damage_base"];
    const projected = parseHistoricalReplayEnvelope(raw);
    if (projected.event_type !== "match_started") throw new Error("wrong fixture event type");
    expect(projected.payload.arena.sudden_death_start_tick).toBeNull();
    expect(projected.payload.arena.sudden_death_damage_base).toBe(8);
  });
});
