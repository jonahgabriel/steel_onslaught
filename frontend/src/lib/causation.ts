/**
 * Causation graph — PRESSURE DECK.
 *
 * Pure, side-effect-free ancestry/lane math for the Event River's causation
 * gutter.  The causal identity of an envelope lives on its nested ONEX
 * envelope: `envelope.message_id` is the node's own id and
 * `envelope.causation_id` points at the parent that produced it (null at a
 * chain root).  These are the ACTUAL field names in `types.ts` — read, not
 * guessed.
 *
 * Everything here is deterministic and unit-tested directly
 * (`__tests__/causation.test.ts`); no React, no DOM, no time.
 */
import type { SOEventEnvelope } from "../types";

/** A causal identity — the value of `envelope.message_id`. */
export type MessageId = string;

/** Precomputed causal links over a set of envelopes. */
export interface CausationIndex {
  /** message_id → causation_id (null at a root). */
  readonly parent: ReadonlyMap<MessageId, MessageId | null>;
  /** causation_id → child message_ids, in insertion order. */
  readonly children: ReadonlyMap<MessageId, readonly MessageId[]>;
  /** message_ids actually present in the indexed set. */
  readonly present: ReadonlySet<MessageId>;
}

/** The causal id of an envelope (its own message_id). */
export function messageIdOf(env: SOEventEnvelope): MessageId {
  return env.envelope.message_id;
}

/** The causal id of an envelope's parent, or null at a chain root. */
export function parentIdOf(env: SOEventEnvelope): MessageId | null {
  return env.envelope.causation_id;
}

/** Build the causal index for a batch of envelopes (order preserved). */
export function buildCausationIndex(envelopes: readonly SOEventEnvelope[]): CausationIndex {
  const parent = new Map<MessageId, MessageId | null>();
  const children = new Map<MessageId, MessageId[]>();
  const present = new Set<MessageId>();

  for (const env of envelopes) {
    const id = messageIdOf(env);
    const cid = parentIdOf(env);
    parent.set(id, cid);
    present.add(id);
    if (cid !== null) {
      const bucket = children.get(cid);
      if (bucket === undefined) {
        children.set(cid, [id]);
      } else {
        bucket.push(id);
      }
    }
  }

  return { parent, children, present };
}

/**
 * `ancestryOf(id) → Set<id>` — the id itself plus every reachable ancestor,
 * walking `causation_id` links.  Stops at a root (parent null) or at the edge
 * of the indexed set (parent unknown).  Cycle-guarded.
 */
export function ancestryOf(id: MessageId, index: CausationIndex): Set<MessageId> {
  const out = new Set<MessageId>([id]);
  let cur: MessageId = id;
  for (;;) {
    const p = index.parent.get(cur);
    if (p === undefined || p === null) break;
    if (out.has(p)) break; // defensive cycle guard
    out.add(p);
    cur = p;
  }
  return out;
}

/**
 * `descendantsOf(id) → Set<id>` — the id itself plus every transitive child.
 * Breadth-first over the `children` map; cycle-guarded.
 */
export function descendantsOf(id: MessageId, index: CausationIndex): Set<MessageId> {
  const out = new Set<MessageId>([id]);
  const queue: MessageId[] = [id];
  while (queue.length > 0) {
    const cur = queue.shift() as MessageId;
    const kids = index.children.get(cur);
    if (kids === undefined) continue;
    for (const kid of kids) {
      if (out.has(kid)) continue;
      out.add(kid);
      queue.push(kid);
    }
  }
  return out;
}

/**
 * The full chain to highlight when a row is focused: ancestors ∪ self ∪
 * descendants.  Everything NOT in this set is dimmed in the river.
 */
export function highlightChain(id: MessageId, index: CausationIndex): Set<MessageId> {
  const out = ancestryOf(id, index);
  for (const d of descendantsOf(id, index)) out.add(d);
  return out;
}

/** The topmost present ancestor of `id` (the root of its visible chain). */
export function rootOf(id: MessageId, index: CausationIndex): MessageId {
  let cur: MessageId = id;
  const seen = new Set<MessageId>([id]);
  for (;;) {
    const p = index.parent.get(cur);
    if (p === undefined || p === null) break;
    if (!index.present.has(p)) break;
    if (seen.has(p)) break;
    seen.add(p);
    cur = p;
  }
  return cur;
}

/**
 * Assign each message id a gutter lane (column).  Every id in a causal chain
 * shares the lane of its root, so threads read as continuous vertical tracks.
 * Lanes wrap at `laneCount` so the gutter stays narrow.
 */
export function assignLanes(
  orderedIds: readonly MessageId[],
  index: CausationIndex,
  laneCount = 6,
): Map<MessageId, number> {
  const rootLane = new Map<MessageId, number>();
  const out = new Map<MessageId, number>();
  let next = 0;
  for (const id of orderedIds) {
    const root = rootOf(id, index);
    let lane = rootLane.get(root);
    if (lane === undefined) {
      lane = next % laneCount;
      next += 1;
      rootLane.set(root, lane);
    }
    out.set(id, lane);
  }
  return out;
}
