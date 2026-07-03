// @vitest-environment jsdom
/**
 * HeaderTransport — control-rail interaction tests.
 *
 * The rail is presentational: every button/picker is a callback into the
 * transport engine. These assert the wiring (which handler fires, the label /
 * aria-pressed state) and that step/restart/LIVE/picker only appear when their
 * handlers are supplied (transport mode vs. an isolated deck).
 */
import "./setup-dom";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MatchSummary } from "../lib/transport";
import HeaderTransport, { type HeaderTransportProps } from "../views/HeaderTransport";

afterEach(cleanup);

const MATCHES: MatchSummary[] = [
  {
    matchId: "match.alpha",
    redLabel: "mech.red.01",
    blueLabel: "mech.blue.01",
    tickCount: 12,
    eventCount: 40,
  },
  {
    matchId: "match.bravo",
    redLabel: "mech.red.02",
    blueLabel: "mech.blue.02",
    tickCount: 7,
    eventCount: 25,
  },
];

function renderRail(overrides: Partial<HeaderTransportProps> = {}) {
  const props: HeaderTransportProps = {
    playing: true,
    live: true,
    speed: 1,
    matches: MATCHES,
    activeMatchId: "match.alpha",
    onTogglePlay: vi.fn(),
    onSetSpeed: vi.fn(),
    onStepBackward: vi.fn(),
    onStepForward: vi.fn(),
    onRestart: vi.fn(),
    onGoLive: vi.fn(),
    onSelectMatch: vi.fn(),
    ...overrides,
  };
  render(<HeaderTransport {...props} />);
  return props;
}

describe("HeaderTransport — play/pause", () => {
  it("toggles play and shows the LIVE label when following live", () => {
    const props = renderRail({ playing: true, live: true });
    const btn = screen.getByTestId("transport-play");
    expect(btn).toHaveTextContent("LIVE");
    expect(btn).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(btn);
    expect(props.onTogglePlay).toHaveBeenCalledTimes(1);
  });

  it("shows HELD when paused and PLAY when playing a non-live replay", () => {
    renderRail({ playing: false, live: false });
    expect(screen.getByTestId("transport-play")).toHaveTextContent("HELD");
    cleanup();
    renderRail({ playing: true, live: false });
    expect(screen.getByTestId("transport-play")).toHaveTextContent("PLAY");
  });
});

describe("HeaderTransport — speed", () => {
  it("marks the active speed pressed and reports the chosen speed", () => {
    const props = renderRail({ speed: 2 });
    expect(screen.getByTestId("transport-speed-2")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("transport-speed-1")).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByTestId("transport-speed-4"));
    expect(props.onSetSpeed).toHaveBeenCalledWith(4);
  });
});

describe("HeaderTransport — step / restart / live", () => {
  it("fires the step, restart and live handlers", () => {
    const props = renderRail({ live: false });
    fireEvent.click(screen.getByTestId("transport-step-back"));
    fireEvent.click(screen.getByTestId("transport-step-fwd"));
    fireEvent.click(screen.getByTestId("transport-restart"));
    fireEvent.click(screen.getByTestId("transport-live"));
    expect(props.onStepBackward).toHaveBeenCalledTimes(1);
    expect(props.onStepForward).toHaveBeenCalledTimes(1);
    expect(props.onRestart).toHaveBeenCalledTimes(1);
    expect(props.onGoLive).toHaveBeenCalledTimes(1);
  });

  it("marks LIVE pressed only while following live", () => {
    renderRail({ live: true });
    expect(screen.getByTestId("transport-live")).toHaveAttribute("aria-pressed", "true");
  });

  it("omits step/restart/live/picker when their handlers are absent", () => {
    renderRail({
      onStepBackward: undefined,
      onStepForward: undefined,
      onRestart: undefined,
      onGoLive: undefined,
      onSelectMatch: undefined,
    });
    expect(screen.queryByTestId("transport-step-back")).not.toBeInTheDocument();
    expect(screen.queryByTestId("transport-restart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("transport-live")).not.toBeInTheDocument();
    expect(screen.queryByTestId("match-picker")).not.toBeInTheDocument();
    // play + speed always remain (an isolated deck still needs them).
    expect(screen.getByTestId("transport-play")).toBeInTheDocument();
    expect(screen.getByTestId("transport-speed-1")).toBeInTheDocument();
  });
});

describe("HeaderTransport — match picker", () => {
  it("lists every seen match with side + tick-count label and selects the active one", () => {
    renderRail();
    const select = screen.getByLabelText("Select match") as HTMLSelectElement;
    expect(select.value).toBe("match.alpha");
    const options = Array.from(select.options).map((o) => o.textContent);
    // short id · sides · tick count
    expect(options[0]).toContain("alpha");
    expect(options[0]).toContain("01v01");
    expect(options[0]).toContain("12t");
    expect(options[1]).toContain("bravo");
  });

  it("switches match on change", () => {
    const props = renderRail();
    fireEvent.change(screen.getByLabelText("Select match"), {
      target: { value: "match.bravo" },
    });
    expect(props.onSelectMatch).toHaveBeenCalledWith("match.bravo");
  });
});
