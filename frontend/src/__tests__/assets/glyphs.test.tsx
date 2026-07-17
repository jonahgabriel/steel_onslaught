// @vitest-environment jsdom
/**
 * Glyph + furniture smoke tests — asset pack (SPEC Rev 2, glyph set +
 * deck furniture).
 */
import "../setup-dom";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  AwaitingTransmission,
  ChassisSprite,
  Favicon,
  faviconDataUri,
  GLYPHS,
  GlyphFire,
  LampCooldown,
  LampNominal,
  LampReady,
  LampSkull,
  LampWreck,
  MODE_GLYPH,
  WEAPON_CLASS_GLYPH,
  Wordmark,
} from "../../assets";

afterEach(cleanup);

describe("Glyph set", () => {
  it("every registry glyph renders a 16-viewBox svg with its testid", () => {
    for (const [name, Comp] of Object.entries(GLYPHS)) {
      const { unmount } = render(<Comp />);
      const svg = screen.getByTestId(`glyph-${name}`);
      expect(svg).toHaveAttribute("viewBox", "0 0 16 16");
      expect(svg).toHaveAttribute("role", "img");
      unmount();
    }
  });

  it("renders a single glyph by name with an accessible title", () => {
    render(<GlyphFire title="fired" />);
    const svg = screen.getByTestId("glyph-fire");
    expect(svg).toHaveAttribute("aria-label", "fired");
  });

  it("weapon-class + mode registries resolve to glyph components", () => {
    render(
      <>
        <WEAPON_CLASS_GLYPH.siege />
        <MODE_GLYPH.recon />
      </>,
    );
    expect(screen.getByTestId("glyph-weapon-siege")).toBeInTheDocument();
    expect(screen.getByTestId("glyph-recon")).toBeInTheDocument();
  });

  it("status + ready lamps render", () => {
    render(
      <>
        <LampNominal />
        <LampSkull />
        <LampWreck />
        <LampReady />
        <LampCooldown />
      </>,
    );
    for (const id of ["lamp-nominal", "lamp-skull", "lamp-wreck", "lamp-ready", "lamp-cooldown"]) {
      expect(screen.getByTestId(`glyph-${id}`)).toBeInTheDocument();
    }
  });
});

describe("Deck furniture", () => {
  it("favicon renders and exposes a data-URI string", () => {
    render(<Favicon />);
    expect(screen.getByTestId("favicon")).toBeInTheDocument();
    expect(faviconDataUri.startsWith("data:image/svg+xml,")).toBe(true);
    expect(faviconDataUri).toContain("svg");
  });

  it("wordmark lockup renders the brand type", () => {
    render(<Wordmark />);
    const mark = screen.getByTestId("wordmark");
    expect(mark.textContent).toContain("Steel");
    expect(mark.textContent).toContain("Onslaught");
  });

  it("awaiting-transmission empty state renders label + hint", () => {
    render(<AwaitingTransmission />);
    const el = screen.getByTestId("awaiting-transmission");
    expect(el.textContent).toContain("Awaiting Transmission");
  });
});

describe("ChassisSprite dispatcher", () => {
  it("maps chassis class to the right sprite", () => {
    const { rerender } = render(<ChassisSprite chassisClass="light" />);
    expect(screen.getByTestId("sprite-scout")).toBeInTheDocument();
    rerender(<ChassisSprite chassisClass="heavy" />);
    expect(screen.getByTestId("sprite-ironclad")).toBeInTheDocument();
  });

  it("resolves a chassis id to its class sprite", () => {
    render(<ChassisSprite chassisId="chassis.medium.hunter_mk1" />);
    expect(screen.getByTestId("sprite-hunter")).toBeInTheDocument();
  });
});
