import type { JSX } from "react";
import { type CardCategory, cardCategoryOf, cardLabelOf } from "../lib/cards";
import { SIDE_ACCENT, type Side, sideStyle } from "./theme";

function Glyph({ category }: { category: CardCategory }): JSX.Element {
  const common = { stroke: "currentColor", strokeWidth: 1.5, fill: "none" };
  if (category === "attack") {
    return (
      <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true" {...common}>
        <circle cx="8" cy="8" r="5" />
        <path d="M8 1v3m0 8v3M1 8h3m8 0h3" />
      </svg>
    );
  }
  if (category === "movement") {
    return (
      <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true" {...common}>
        <path d="M8 14V3m-4 3.5L8 2.5l4 4" />
      </svg>
    );
  }
  if (category === "vent") {
    return (
      <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true" {...common}>
        <path d="M4 13c0-4 4-3 4-6S6 4 6 2m3 11c0-4 4-3 4-6 0-2-1.5-2-1.5-4" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true" {...common}>
      <path
        d={
          category === "rotate"
            ? "M12.5 6A5 5 0 1 0 13.5 9.5M9.5 5.5l3.2.1-.3-3.2"
            : "M8 1.5 9.4 6.6 14.5 8 9.4 9.4 8 14.5 6.6 9.4 1.5 8 6.6 6.6Z"
        }
      />
    </svg>
  );
}

export function CardFace({
  cardId,
  side,
  priority,
  size = 46,
}: {
  cardId: string;
  side?: Side;
  priority?: number;
  size?: number;
}): JSX.Element {
  const category = cardCategoryOf(cardId);
  const height = Math.round(size * 1.32);
  return (
    <div
      className="pd-card"
      data-testid={`card-face-${cardId}`}
      data-card-id={cardId}
      data-category={category}
      style={sideStyle(side, { width: size, height })}
      title={cardLabelOf(cardId)}
    >
      <svg
        className="pd-card-plate"
        viewBox="0 0 40 54"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path
          d="M7 1h32v46l-6 6H1V7Z"
          fill="var(--iron,#16181D)"
          stroke={SIDE_ACCENT}
          strokeWidth="1.4"
        />
        <path d="M5 50h30" stroke="var(--seam,#262A33)" />
      </svg>
      {priority !== undefined ? <span className="pd-card-prio">{priority}</span> : null}
      <span className="pd-card-glyph">
        <Glyph category={category} />
      </span>
      <span className="pd-card-name">{cardLabelOf(cardId)}</span>
    </div>
  );
}
