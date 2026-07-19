/** Card display helpers derived from canonical card ids. */
export type CardCategory = "movement" | "rotate" | "attack" | "vent" | "special";

const CATEGORIES = new Set<CardCategory>(["movement", "rotate", "attack", "vent", "special"]);

export function cardCategoryOf(cardId: string): CardCategory {
  const category = cardId.split(".")[1] as CardCategory | undefined;
  return category !== undefined && CATEGORIES.has(category) ? category : "special";
}

export function cardLabelOf(cardId: string): string {
  const name = cardId.slice(cardId.lastIndexOf(".") + 1);
  return name
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
