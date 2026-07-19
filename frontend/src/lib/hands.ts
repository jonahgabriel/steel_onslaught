import type { SOEventEnvelope } from "../types";

export interface HandState {
  readonly mechId: string;
  readonly seat: string;
  readonly deckId: string;
  readonly cardIds: readonly string[];
  readonly handSize: number;
  readonly deckRemaining: number;
  readonly reshuffled: boolean;
}

export type Hands = Readonly<Record<string, HandState>>;
export type CardPriorities = Readonly<Record<string, number>>;

export interface PlayedCardBeat {
  readonly mechId: string;
  readonly cardId: string;
  readonly playKey: number;
}

export type PlayedCards = Readonly<Record<string, PlayedCardBeat>>;

export function applyHandEvent(hands: Hands, env: SOEventEnvelope): Hands {
  if (env.event_type !== "hand_dealt") return hands;
  const payload = env.payload;
  return {
    ...hands,
    [env.subject.mech_id]: {
      mechId: env.subject.mech_id,
      seat: payload.seat,
      deckId: payload.deck_id,
      cardIds: [...payload.card_ids],
      handSize: payload.hand_size,
      deckRemaining: payload.deck_remaining,
      reshuffled: payload.reshuffled,
    },
  };
}

export function applyCardPriority(
  priorities: CardPriorities,
  env: SOEventEnvelope,
): CardPriorities {
  if (env.event_type !== "register_resolved" || env.payload.card_id === null) return priorities;
  return { ...priorities, [env.payload.card_id]: env.payload.priority };
}

export function applyCardPlay(played: PlayedCards, env: SOEventEnvelope): PlayedCards {
  if (env.event_type !== "cards_discarded" || env.payload.reason !== "played") return played;
  const cardId = env.payload.card_ids.at(-1);
  if (cardId === undefined) return played;
  const mechId = env.subject.mech_id;
  return { ...played, [mechId]: { mechId, cardId, playKey: (played[mechId]?.playKey ?? 0) + 1 } };
}
