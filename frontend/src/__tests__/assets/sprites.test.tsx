// @vitest-environment jsdom
/**
 * Chassis sprite tests — asset pack (SPEC Rev 2 §"Sprite + asset pack").
 *
 * Per sprite: renders every damage state, asserts the per-state testid, the
 * venting/firing flag overlays, and a facing-rotation transform.
 */
import "../setup-dom";
import { cleanup, render, screen } from "@testing-library/react";
import type { JSX } from "react";
import { afterEach, describe, expect, it } from "vitest";
import type { ChassisSpriteProps } from "../../assets";
import { SpriteHunter, SpriteIronclad, SpriteScout } from "../../assets";

afterEach(cleanup);

type SpriteComp = (p: ChassisSpriteProps) => JSX.Element;

const SPRITES: ReadonlyArray<[string, SpriteComp]> = [
  ["scout", SpriteScout],
  ["hunter", SpriteHunter],
  ["ironclad", SpriteIronclad],
];

describe.each(SPRITES)("Sprite %s", (name, Sprite) => {
  it("renders the root svg with class + state data attributes", () => {
    render(<Sprite state="nominal" />);
    const root = screen.getByTestId(`sprite-${name}`);
    expect(root).toBeInTheDocument();
    expect(root).toHaveAttribute("data-chassis", name);
    expect(root).toHaveAttribute("data-state", "nominal");
    // nominal has no scorch / glow / wreck
    expect(screen.queryByTestId("sprite-scorch")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sprite-critical-glow")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sprite-wreck")).not.toBeInTheDocument();
    // boiler present in a live hull
    expect(screen.getByTestId("sprite-boiler")).toBeInTheDocument();
  });

  it("damaged state shows scorch, no glow, no wreck", () => {
    render(<Sprite state="damaged" />);
    expect(screen.getByTestId(`sprite-${name}`)).toHaveAttribute("data-state", "damaged");
    expect(screen.getByTestId("sprite-scorch")).toBeInTheDocument();
    expect(screen.queryByTestId("sprite-critical-glow")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sprite-wreck")).not.toBeInTheDocument();
  });

  it("critical state shows the boiler glow pulse (with scorch)", () => {
    render(<Sprite state="critical" />);
    const glow = screen.getByTestId("sprite-critical-glow");
    expect(glow).toBeInTheDocument();
    expect(glow).toHaveClass("so-anim-crit");
    expect(screen.getByTestId("sprite-scorch")).toBeInTheDocument();
  });

  it("destroyed state swaps in the wreck variant (no live hull boiler)", () => {
    render(<Sprite state="destroyed" />);
    expect(screen.getByTestId(`sprite-${name}`)).toHaveAttribute("data-state", "destroyed");
    expect(screen.getByTestId("sprite-wreck")).toBeInTheDocument();
    expect(screen.queryByTestId("sprite-boiler")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sprite-muzzle")).not.toBeInTheDocument();
  });

  it("venting flag renders steam puffs", () => {
    render(<Sprite venting />);
    const vent = screen.getByTestId("sprite-vent");
    expect(vent).toBeInTheDocument();
    expect(screen.getByTestId(`sprite-${name}`)).toHaveAttribute("data-venting", "true");
  });

  it("firing flag renders a muzzle flash", () => {
    render(<Sprite firing />);
    expect(screen.getByTestId("sprite-muzzle")).toBeInTheDocument();
    expect(screen.getByTestId(`sprite-${name}`)).toHaveAttribute("data-firing", "true");
  });

  it("firing on a destroyed hull is suppressed", () => {
    render(<Sprite firing state="destroyed" />);
    expect(screen.getByTestId(`sprite-${name}`)).toHaveAttribute("data-firing", "false");
    expect(screen.queryByTestId("sprite-muzzle")).not.toBeInTheDocument();
  });

  it("applies facing as a rotation transform on the body group", () => {
    render(<Sprite facing={90} />);
    const root = screen.getByTestId(`sprite-${name}`);
    expect(root).toHaveAttribute("data-facing", "90");
    const body = screen.getByTestId("sprite-body");
    expect(body.getAttribute("transform")).toBe("rotate(90 50 50)");
  });

  it("threads side color into the --so-side custom property", () => {
    render(<Sprite side="red" />);
    const root = screen.getByTestId(`sprite-${name}`);
    expect(root.style.getPropertyValue("--so-side")).not.toBe("");
  });
});
