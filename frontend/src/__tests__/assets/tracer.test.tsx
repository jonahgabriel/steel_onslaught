// @vitest-environment jsdom
/**
 * Weapon tracer tests — asset pack (SPEC Rev 2, per-class tracer styles).
 */
import "../setup-dom";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { WeaponClass } from "../../assets";
import { Tracer } from "../../assets";

afterEach(cleanup);

const CLASSES: readonly WeaponClass[] = ["light", "medium", "heavy", "siege"];

describe("Tracer — per weapon class", () => {
  it.each(CLASSES)("renders a %s tracer with the class testid + data attribute", (cls) => {
    render(<Tracer from={{ x: 2, y: 3 }} to={{ x: 10, y: 12 }} weaponClass={cls} />);
    const svg = screen.getByTestId(`tracer-${cls}`);
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute("data-weapon-class", cls);
    expect(svg).toHaveAttribute("viewBox", "0 0 40 40");
  });

  it("light class draws a dashed stipple line", () => {
    render(<Tracer from={{ x: 0, y: 0 }} to={{ x: 5, y: 0 }} weaponClass="light" />);
    const line = screen.getByTestId("tracer-light").querySelector("line");
    expect(line).not.toBeNull();
    expect(line?.getAttribute("stroke-dasharray")).toBeTruthy();
  });

  it("siege class always renders an impact ring and an arced path", () => {
    render(<Tracer from={{ x: 1, y: 1 }} to={{ x: 20, y: 5 }} weaponClass="siege" />);
    const svg = screen.getByTestId("tracer-siege");
    expect(svg.querySelector("path")?.getAttribute("d")).toContain("Q");
    expect(screen.getByTestId("tracer-impact")).toBeInTheDocument();
  });

  it("non-siege only shows the impact ring when impact is set", () => {
    const { rerender } = render(
      <Tracer from={{ x: 0, y: 0 }} to={{ x: 4, y: 4 }} weaponClass="medium" />,
    );
    expect(screen.queryByTestId("tracer-impact")).not.toBeInTheDocument();
    rerender(<Tracer from={{ x: 0, y: 0 }} to={{ x: 4, y: 4 }} weaponClass="medium" impact />);
    expect(screen.getByTestId("tracer-impact")).toBeInTheDocument();
  });

  it("honors a custom grid size in the viewBox", () => {
    render(<Tracer from={{ x: 0, y: 0 }} to={{ x: 1, y: 1 }} weaponClass="heavy" gridCells={64} />);
    expect(screen.getByTestId("tracer-heavy")).toHaveAttribute("viewBox", "0 0 64 64");
  });
});
