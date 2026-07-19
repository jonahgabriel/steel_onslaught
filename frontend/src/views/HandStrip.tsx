import type React from "react";
import { CardFace } from "../assets/cards";
import type { CardPriorities, HandState, PlayedCardBeat } from "../lib/hands";
import type { Side } from "../lib/river";

export default function HandStrip({
  mechId,
  hand,
  side,
  priorities = {},
  played,
}: {
  mechId: string;
  hand?: HandState;
  side: Side;
  priorities?: CardPriorities;
  played?: PlayedCardBeat;
}): React.JSX.Element {
  const accent = side === "neutral" ? undefined : side;
  const cardIds = hand?.cardIds ?? [];
  return (
    <section className="pd-hand" data-testid={`hand-${mechId}`} data-side={side}>
      {played ? (
        <div className="pd-played" data-testid={`played-${mechId}`} data-card-id={played.cardId}>
          <span className="pd-played-label">PLAYED</span>
          <CardFace cardId={played.cardId} side={accent} priority={priorities[played.cardId]} />
        </div>
      ) : null}
      <div className="pd-hand-head">
        <span className="pd-hand-label">HAND</span>
        {hand ? (
          <span className="pd-hand-meta">
            <span className="pd-hand-count">
              {cardIds.length}/{hand.handSize}
            </span>
            <span className="pd-hand-deck">· deck {hand.deckRemaining}</span>
            {hand.reshuffled ? <span> ⟳</span> : null}
          </span>
        ) : null}
      </div>
      {cardIds.length === 0 ? (
        <div className="pd-hand-empty">{hand ? "no cards" : "awaiting deal…"}</div>
      ) : (
        <div className="pd-cards" data-testid={`hand-cards-${mechId}`}>
          {cardIds.map((cardId, index) => (
            <CardFace
              key={`${cardId}-${cardIds.slice(0, index).filter((candidate) => candidate === cardId).length}`}
              cardId={cardId}
              side={accent}
              priority={priorities[cardId]}
            />
          ))}
        </div>
      )}
    </section>
  );
}
