/**
 * Fixture builders for PRESSURE DECK tests.
 *
 * The 27 JSON fixtures under `./fixtures/` are pinned one-per-SOEventType by
 * `types_parity.test.ts`, so river/causation tests build typed envelopes in
 * code instead (the same approach `DecisionInspector.test.tsx` already uses).
 * Every builder returns a fully-typed `SOEventEnvelope`; the LLM-evidence
 * builder mirrors `steel_onslaught/llm/effect.py` exactly (a `kind` marker on
 * the SENSOR_OBSERVATION telemetry slot).
 */
import type {
  PayloadMap,
  PilotDecisionMadePayload,
  SOEventEnvelope,
  SOEventEnvelopeOf,
  SOEventType,
} from "../types";

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
    action?: string;
    reasonCode?: string;
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

/** LLM request evidence — mirrors effect.py (sensor_observation slot + kind). */
export function makeLlmRequest(o: EnvelopeOverrides & { persona?: string } = {}): SOEventEnvelope {
  return {
    ...baseLlm(o),
    payload: {
      kind: "llm_completion_requested",
      persona: o.persona ?? "aggressor",
      system_prompt_len: 120,
      user_prompt_len: 340,
    },
  } as unknown as SOEventEnvelope;
}

/** LLM resolved evidence — mirrors effect.py resolved payload. */
export function makeLlmResolved(
  o: EnvelopeOverrides & {
    model?: string;
    promptTokens?: number;
    completionTokens?: number;
    costUsd?: number;
  } = {},
): SOEventEnvelope {
  const payload: Record<string, string | number> = {
    kind: "llm_completion_resolved",
    model: o.model ?? "provider.glm.flash",
    finish_reason: "stop",
    prompt_tokens: o.promptTokens ?? 120,
    completion_tokens: o.completionTokens ?? 48,
    text_len: 210,
  };
  if (o.costUsd !== undefined) payload["cost_usd"] = o.costUsd;
  return { ...baseLlm(o), payload } as unknown as SOEventEnvelope;
}

function baseLlm(o: EnvelopeOverrides): Record<string, unknown> {
  const messageId = o.messageId ?? nextId("m");
  return {
    schema_version: "0.1.0",
    event_id: nextId("01"),
    match_id: o.matchId ?? "match.test.0001",
    tick: o.tick ?? 0,
    sequence_in_tick: o.seq ?? 0,
    producer_node: "node.llm.effect",
    subject: { mech_id: o.mechId ?? "mech.red.01", player_id: "*" },
    event_type: "sensor_observation",
    envelope: {
      message_id: messageId,
      correlation_id: "corr-0001",
      causation_id: o.causationId ?? null,
      emitted_at: "2026-07-02T00:00:00Z",
      entity_id: o.matchId ?? "match.test.0001",
    },
  };
}
