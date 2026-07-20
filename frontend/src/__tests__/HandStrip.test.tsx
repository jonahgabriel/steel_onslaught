// @vitest-environment jsdom
import "./setup-dom";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import HandStrip from "../views/HandStrip";

afterEach(cleanup);

describe("HandStrip — authoritative hand projection", () => {
  it("renders every card in a five-card hand at a narrow rail", () => {
    render(
      <HandStrip
        mechId="mech.red.01"
        side="red"
        hand={{
          mechId: "mech.red.01",
          seat: "red",
          deckId: "deck.standard",
          cardIds: [
            "card.movement.advance",
            "card.attack.fire_primary",
            "card.vent.emergency_vent",
            "card.rotate.turn_left",
            "card.special.reposition",
          ],
          handSize: 5,
          deckRemaining: 11,
          reshuffled: false,
        }}
      />,
    );

    const hand = screen.getByTestId("hand-mech.red.01");
    expect(within(hand).getByTestId("hand-cards-mech.red.01")).toBeInTheDocument();
    expect(within(hand).getByText("5/5")).toBeInTheDocument();

    const cards = within(hand).getAllByTestId(/^card-face-/);
    expect(cards).toHaveLength(5);
    for (const card of cards) {
      expect(card).toHaveClass("pd-card-fluid");
      expect(card).toBeVisible();
    }
    expect(cards.map((card) => card.getAttribute("data-card-id"))).toEqual([
      "card.movement.advance",
      "card.attack.fire_primary",
      "card.vent.emergency_vent",
      "card.rotate.turn_left",
      "card.special.reposition",
    ]);
  });
});
