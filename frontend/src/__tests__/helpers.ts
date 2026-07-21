/**
 * Fixture builders for PRESSURE DECK tests.
 *
 * The JSON fixtures under `./fixtures/` are pinned one-per-SOEventType by
 * `types_parity.test.ts`, so river/causation tests build typed envelopes in
 * code instead.
 * Every builder returns a fully-typed `SOEventEnvelope`; the LLM-evidence
 * builders mirror `steel_onslaught/llm/effect.py` exactly — the first-class,
 * closed requested / resolved / failed payload contracts.
 */
import type {
  PayloadMap,
  PilotDecisionMadePayload,
  PlanCommittedPayload,
  SOArenaSnapshot,
  SOEventEnvelopeOf,
  SOEventType,
  SOModelSeatAssignment,
  SOPilotAction,
  SOPilotReasonCode,
} from "../types";

export const TEST_ARENA: SOArenaSnapshot = {
  schema_version: "0.1.0",
  kind: "steel_onslaught.arena_snapshot",
  arena_id: "arena.test.open_field",
  size: 40,
  spawn_a: { x: 5, y: 5 },
  spawn_b: { x: 35, y: 35 },
  obstacles: [],
  sudden_death_start_tick: null,
  sudden_death_damage_base: 8,
};

let idCounter = 0;

function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}${String(idCounter).padStart(26 - prefix.length, "0")}`.slice(0, 26);
}

export interface EnvelopeOverrides {
  tick?: number;
  seq?: number;
  mechId?: string;
  playerId?: string;
  matchId?: string;
  messageId?: string;
  causationId?: string | null;
}

export function makeEnvelope<K extends SOEventType>(
  eventType: K,
  payload: PayloadMap[K],
  o: EnvelopeOverrides = {},
): SOEventEnvelopeOf<K> {
  const messageId = o.messageId ?? nextId("m");
  return {
    schema_version: "0.1.0",
    event_id: nextId("01"),
    match_id: o.matchId ?? "match.test.0001",
    tick: o.tick ?? 0,
    sequence_in_tick: o.seq ?? 0,
    producer_node: "node.test",
    subject: {
      mech_id: o.mechId ?? "mech.red.01",
      player_id: o.playerId ?? "player.red",
    },
    event_type: eventType,
    payload,
    envelope: {
      message_id: messageId,
      correlation_id: "corr-0001",
      causation_id: o.causationId ?? null,
      emitted_at: "2026-07-02T00:00:00Z",
      entity_id: o.matchId ?? "match.test.0001",
    },
  } as SOEventEnvelopeOf<K>;
}

export function makeDecision(
  o: EnvelopeOverrides & {
    action?: SOPilotAction;
    reasonCode?: SOPilotReasonCode;
    confidence?: number;
    rationale?: string | null;
  } = {},
): SOEventEnvelopeOf<"pilot_decision_made"> {
  const payload: PilotDecisionMadePayload = {
    action: o.action ?? "fire_weapon",
    action_params: { weapon_id: "module.weapon.mg.02" },
    reason_code: o.reasonCode ?? "target_in_range",
    confidence: o.confidence ?? 0.8,
    considered_actions: [
      { action: o.action ?? "fire_weapon", score: o.confidence ?? 0.8 },
      { action: "vent", score: 0.2 },
    ],
    rationale: o.rationale ?? null,
  };
  return makeEnvelope("pilot_decision_made", payload, o);
}

/**
 * A committed card-cadence plan — the ONLY carrier of pilot rationale +
 * confidence in the card/paced mode the demo runs (`match/card_adapter.py`).
 */
export function makePlan(
  o: EnvelopeOverrides & {
    seat?: string;
    cardIds?: readonly string[];
    confidence?: number;
    rationale?: string | null;
  } = {},
): SOEventEnvelopeOf<"plan_committed"> {
  const cardIds = o.cardIds ?? [
    "card.movement.advance",
    "card.attack.fire_primary",
    "card.vent.emergency_vent",
  ];
  const payload: PlanCommittedPayload = {
    seat: o.seat ?? "a",
    registers: cardIds.map((card_id, register_index) => ({ register_index, card_id })),
    rationale: o.rationale ?? null,
    confidence: o.confidence ?? 0.8,
  };
  return makeEnvelope("plan_committed", payload, o);
}

/**
 * A model seat assignment, as carried by
 * `match_started.payload.launch_provenance.seat_assignments`.
 */
export function makeModelSeat(
  o: {
    side?: "red" | "blue";
    playerId?: string;
    personaId?: string;
    modelIdentityId?: string;
    loadoutId?: string;
    pilotSpecId?: string;
  } = {},
): SOModelSeatAssignment {
  const side = o.side ?? "red";
  return {
    kind: "model",
    side,
    player_id: o.playerId ?? `player.${side}`,
    option_id: `player_option.${side}_model`,
    loadout_id: o.loadoutId ?? `loadout.playable.${side}_light`,
    pilot_spec_id: o.pilotSpecId ?? `pilot.model.${side}`,
    option_sha256: "a".repeat(64),
    model_identity_id: o.modelIdentityId ?? `model_identity.${side}`,
    persona_id: o.personaId ?? `persona.${side}`,
    input_source: "llm_completion",
  };
}

/** LLM request evidence — mirrors the canonical closed payload. */
export function makeLlmRequest(
  o: EnvelopeOverrides & { persona?: string } = {},
): SOEventEnvelopeOf<"llm_completion_requested"> {
  return makeEnvelope(
    "llm_completion_requested",
    {
      provider_id: "stub",
      persona_id: o.persona ?? "aggressor",
      system_prompt_length: 120,
      user_prompt_length: 340,
    },
    o,
  );
}

/** LLM resolved evidence — mirrors effect.py resolved payload. */
export function makeLlmResolved(
  o: EnvelopeOverrides & {
    model?: string;
    promptTokens?: number;
    completionTokens?: number;
    costUsd?: number | null;
  } = {},
): SOEventEnvelopeOf<"llm_completion_resolved"> {
  return makeEnvelope(
    "llm_completion_resolved",
    {
      provider_id: "stub",
      model: o.model ?? "provider.glm.flash",
      finish_reason: "stop",
      prompt_tokens: o.promptTokens ?? 120,
      completion_tokens: o.completionTokens ?? 48,
      response_length: 210,
      cost_usd: o.costUsd === undefined ? 0 : o.costUsd,
    },
    o,
  );
}

/** LLM failure evidence — the sole terminal shape carrying optional cost. */
export function makeLlmFailed(
  o: EnvelopeOverrides & { model?: string; costUsd?: number | null } = {},
): SOEventEnvelopeOf<"llm_completion_failed"> {
  return makeEnvelope(
    "llm_completion_failed",
    {
      provider_id: "stub",
      reason_code: "consumer_error",
      semantic_failure_code: null,
      model: o.model ?? "provider.glm.flash",
      finish_reason: "stop",
      prompt_tokens: 120,
      completion_tokens: 48,
      cost_usd: o.costUsd ?? null,
    },
    o,
  );
}
