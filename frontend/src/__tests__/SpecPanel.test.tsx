// @vitest-environment jsdom
/**
 * SpecPanel tests — Rev 2 mech spec panels.
 *
 * Fixture-replay: fold the match_started fixture + a synthetic event sequence
 * through `lib/gauges.ts` (the same fold the deck uses) and assert the rendered
 * spec panel surfaces hp / armor / heat / redline / overload / mode + transition
 * / per-weapon cooldowns / tallies / pilot line / status — the Rev 2 acceptance
 * list. A second block drives cooldown-countdown + destroyed rendering from a
 * hand-built GaugeState.
 */
import "./setup-dom";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { applyGaugeEvent, type GaugeState, initGauges } from "../lib/gauges";
import { buildSideMap } from "../lib/river";
import { parseEnvelope, type SOEventEnvelope } from "../types";
import SpecPanel from "../views/SpecPanel";
import {
  makeDecision,
  makeEnvelope,
  makeLlmRequest,
  makeLlmResolved,
  makeModelSeat,
  makePlan,
} from "./helpers";

const FIXTURES_DIR = join(process.cwd(), "src/__tests__/fixtures");
function fixtureText(name: string): string {
  return readFileSync(join(FIXTURES_DIR, `${name}.json`), "utf-8");
}

afterEach(cleanup);

function foldedGauges(): GaugeState[] {
  const started = parseEnvelope(JSON.parse(fixtureText("match_started")));
  if (started.event_type !== "match_started") throw new Error("fixture is not match_started");
  const sides = buildSideMap(started.payload.mechs);
  let gauges = initGauges(started.payload.mechs, sides);

  const events: SOEventEnvelope[] = [
    makeEnvelope(
      "weapon_fired",
      {
        weapon_id: "module.weapon.machine_gun",
        target_id: "mech.b.01",
        hit_probability: 0.6,
        pressure_cost: 4,
        heat_generated: 6,
      },
      { mechId: "mech.a.01", playerId: "player.a" },
    ),
    makeDecision({ mechId: "mech.a.01", playerId: "player.a" }),
    makeEnvelope(
      "boiler_overloaded",
      {
        heat: 78,
        redline_threshold: 70,
        redline_consecutive_ticks: 3,
        accuracy_penalty_next_fire: 0.25,
        mode_switch_disabled_until: 14,
      },
      { mechId: "mech.a.01", playerId: "player.a" },
    ),
    makeEnvelope(
      "boiler_updated",
      { pressure_before: 45, pressure_after: 40, heat_before: 60, heat_after: 80 },
      { mechId: "mech.a.01", playerId: "player.a" },
    ),
    makeEnvelope(
      "mode_transition_started",
      {
        from_mode: "recon",
        to_mode: "assault",
        costs: { pressure: 10, heat: 5, transition_ticks: 2 },
        sensor_dropout_ticks: 1,
        evasion_penalty: 0.2,
      },
      { mechId: "mech.a.01", playerId: "player.a" },
    ),
    makeLlmRequest({ mechId: "mech.a.01", persona: "berserker" }),
    makeLlmResolved({ mechId: "mech.a.01", model: "stub" }),
    makeEnvelope(
      "damage_applied",
      {
        target_id: "mech.b.01",
        damage: 8,
        cause: "weapon_hit",
        hp_after: 92,
        source_mech_id: "mech.a.01",
        radius_cells: 0,
      },
      { mechId: "mech.b.01", playerId: "player.b" },
    ),
    makeEnvelope(
      "armor_absorbed",
      { target_id: "mech.b.01", absorbed_amount: 4, armor_after: 6 },
      { mechId: "mech.a.01", playerId: "player.a" },
    ),
  ];
  for (const e of events) gauges = applyGaugeEvent(gauges, e);
  return Object.values(gauges);
}

describe("SpecPanel — fixture replay", () => {
  it("renders both mech spec panels (RED over BLUE)", () => {
    render(<SpecPanel gauges={foldedGauges()} />);
    expect(screen.getByTestId("spec-mech.a.01")).toBeInTheDocument();
    expect(screen.getByTestId("spec-mech.b.01")).toBeInTheDocument();
  });

  it("folds attacker tallies (shots, decisions, damage dealt)", () => {
    render(<SpecPanel gauges={foldedGauges()} />);
    const a = screen.getByTestId("spec-mech.a.01");
    expect(within(a).getByTestId("spec-shots-mech.a.01").textContent).toContain("1");
    expect(within(a).getByTestId("spec-decisions-mech.a.01").textContent).toContain("1");
    expect(within(a).getByTestId("spec-dmg-dealt-mech.a.01").textContent).toContain("8");
  });

  it("folds victim hp, damage taken and armor pool", () => {
    render(<SpecPanel gauges={foldedGauges()} />);
    const b = screen.getByTestId("spec-mech.b.01");
    expect(within(b).getByTestId("spec-hp-mech.b.01")).toHaveAttribute("data-hp-pct", "92");
    expect(within(b).getByTestId("spec-hp-mech.b.01").textContent).toContain("92/100");
    expect(within(b).getByTestId("spec-dmg-taken-mech.b.01").textContent).toContain("8");
    expect(within(b).getByTestId("spec-armor-mech.b.01")).toHaveAttribute("data-armor", "6");
  });

  it("surfaces overload + redline warning + heat redline", () => {
    render(<SpecPanel gauges={foldedGauges()} />);
    const a = screen.getByTestId("spec-mech.a.01");
    expect(within(a).getByTestId("spec-overloaded-mech.a.01")).toBeInTheDocument();
    expect(within(a).getByTestId("spec-redline-mech.a.01").textContent).toContain("3");
    const heat = within(a).getByTestId("spec-heat-mech.a.01");
    expect(heat.querySelector('[data-heat-level="redline"]')).toBeInTheDocument();
  });

  it("shows current mode + transition countdown", () => {
    render(<SpecPanel gauges={foldedGauges()} />);
    const mode = within(screen.getByTestId("spec-mech.a.01")).getByTestId("spec-mode-mech.a.01");
    expect(mode.textContent).toContain("recon");
    expect(mode.textContent).toContain("assault");
    expect(mode.textContent).toContain("2t");
  });

  it("shows the LLM pilot line with persona + model", () => {
    render(<SpecPanel gauges={foldedGauges()} />);
    const pilot = within(screen.getByTestId("spec-mech.a.01")).getByTestId("spec-pilot-mech.a.01");
    expect(pilot.textContent).toContain("berserker");
    expect(pilot.textContent).toContain("stub");
    expect(pilot.textContent).toContain("LLM");
  });

  it("renders a READY weapon cooldown row from weapon_cooldowns", () => {
    render(<SpecPanel gauges={foldedGauges()} />);
    const row = within(screen.getByTestId("spec-mech.a.01")).getByTestId(
      "spec-weapon-mech.a.01-machine_gun",
    );
    expect(row).toHaveAttribute("data-ready", "true");
    expect(row.textContent).toContain("READY");
  });
});

describe("SpecPanel — card cadence + authoritative seat identity", () => {
  function startedFixture() {
    const started = parseEnvelope(JSON.parse(fixtureText("match_started")));
    if (started.event_type !== "match_started") throw new Error("fixture is not match_started");
    return started;
  }

  it("counts a committed plan in the DECISIONS tally (card cadence emits no pilot_decision_made)", () => {
    const started = startedFixture();
    const sides = buildSideMap(started.payload.mechs);
    let gauges = initGauges(started.payload.mechs, sides);
    for (const env of [
      makePlan({ seat: "a", mechId: "mech.a.01", playerId: "player.a" }),
      makePlan({ seat: "a", mechId: "mech.a.01", playerId: "player.a" }),
    ]) {
      gauges = applyGaugeEvent(gauges, env);
    }
    render(<SpecPanel gauges={Object.values(gauges)} />);
    const a = screen.getByTestId("spec-mech.a.01");
    expect(within(a).getByTestId("spec-decisions-mech.a.01").textContent).toContain("2");
    // The opposing seat committed nothing, so its tally must stay honest.
    const b = screen.getByTestId("spec-mech.b.01");
    expect(within(b).getByTestId("spec-decisions-mech.b.01").textContent).toContain("0");
  });

  it("renders the authoritative per-seat identity, visibly different per side", () => {
    const started = startedFixture();
    const sides = buildSideMap(started.payload.mechs);
    const gauges = initGauges(started.payload.mechs, sides, [
      makeModelSeat({
        side: "red",
        playerId: "player.a",
        personaId: "persona.berserker",
        modelIdentityId: "model_identity.glm_flash",
        loadoutId: "loadout.playable.red_light",
      }),
      makeModelSeat({
        side: "blue",
        playerId: "player.b",
        personaId: "persona.sniper",
        modelIdentityId: "model_identity.claude_haiku",
        loadoutId: "loadout.playable.blue_heavy",
      }),
    ]);
    render(<SpecPanel gauges={Object.values(gauges)} />);

    const red = screen.getByTestId("spec-seat-mech.a.01");
    const blue = screen.getByTestId("spec-seat-mech.b.01");
    expect(red).toHaveAttribute("data-seat-kind", "MODEL");
    expect(red.textContent).toContain("persona.berserker");
    expect(red.textContent).toContain("model_identity.glm_flash");
    expect(red.textContent).toContain("loadout.playable.red_light");
    expect(blue.textContent).toContain("persona.sniper");
    expect(blue.textContent).toContain("model_identity.claude_haiku");
    // The whole point of surfacing this: the two seats must not read the same.
    expect(blue.textContent).not.toBe(red.textContent);
  });

  it("renders no seat line at all when the match carried no launch provenance", () => {
    const started = startedFixture();
    const sides = buildSideMap(started.payload.mechs);
    render(<SpecPanel gauges={Object.values(initGauges(started.payload.mechs, sides))} />);
    expect(screen.queryByTestId("spec-seat-mech.a.01")).not.toBeInTheDocument();
  });
});

describe("SpecPanel — synthetic state", () => {
  function gauge(overrides: Partial<GaugeState>): GaugeState {
    return {
      mechId: "mech.x.01",
      playerId: "player.x",
      side: "red",
      displayName: "X-01",
      chassisClass: "heavy",
      chassisId: "chassis.heavy.ironclad_mk1",
      pilotId: "pilot.tactician",
      seat: null,
      isLlm: false,
      persona: null,
      model: null,
      heat: 20,
      redlineThreshold: 70,
      ruptureThreshold: 100,
      redlineConsecutiveTicks: 0,
      overloaded: false,
      pressureCurrent: 45,
      pressureMaximum: 90,
      hp: 40,
      hpMax: 100,
      armorValue: 8,
      armorMax: 10,
      mode: "assault",
      transitionToMode: null,
      transitionTicksRemaining: 0,
      weaponCooldowns: { "module.weapon.steam_cannon": 2 },
      damageDealt: 0,
      damageTaken: 60,
      shotsFired: 0,
      decisions: 0,
      status: "alive",
      ...overrides,
    };
  }

  it("renders a countdown weapon row (N ticks, not ready)", () => {
    render(<SpecPanel gauges={[gauge({})]} />);
    const row = screen.getByTestId("spec-weapon-mech.x.01-steam_cannon");
    expect(row).toHaveAttribute("data-ready", "false");
    expect(row).toHaveAttribute("data-cooldown", "2");
    expect(row.textContent).toContain("2t");
  });

  it("labels an LLM pilot only from canonical evidence metadata", () => {
    render(<SpecPanel gauges={[gauge({ isLlm: true, persona: "berserker" })]} />);
    const pilot = screen.getByTestId("spec-pilot-mech.x.01");
    expect(pilot.textContent).toContain("LLM");
    expect(pilot.textContent).toContain("berserker");
    expect(pilot.textContent).not.toContain("UNKNOWN");
  });

  it("shows unknown with the exact pilot id when identity metadata is absent", () => {
    render(<SpecPanel gauges={[gauge({})]} />);
    const pilot = screen.getByTestId("spec-pilot-mech.x.01");
    expect(pilot.textContent).toBe("UNKNOWN · pilot.tactician");
  });

  it("labels a human seat as HUMAN with its human identity, never a persona", () => {
    render(
      <SpecPanel
        gauges={[
          gauge({
            seat: {
              kind: "human",
              side: "red",
              player_id: "player.x",
              option_id: "player_option.browser_human",
              loadout_id: "loadout.playable.red_light",
              pilot_spec_id: "pilot.human.browser",
              option_sha256: "b".repeat(64),
              human_identity_id: "human_identity.local_browser",
              input_source: "browser_command",
            },
          }),
        ]}
      />,
    );
    const seat = screen.getByTestId("spec-seat-mech.x.01");
    expect(seat).toHaveAttribute("data-seat-kind", "HUMAN");
    expect(seat.textContent).toContain("human_identity.local_browser");
    expect(seat.textContent).not.toContain("persona");
  });

  it("marks a destroyed mech in the status lamp + section", () => {
    render(<SpecPanel gauges={[gauge({ status: "destroyed" })]} />);
    expect(screen.getByTestId("spec-mech.x.01")).toHaveAttribute("data-status", "destroyed");
    expect(screen.getByTestId("spec-status-mech.x.01").textContent).toContain("DESTROYED");
  });

  it("exposes split-rail side identity and suppresses the right empty placeholder", () => {
    render(<SpecPanel gauges={[]} side="right" emptyPlaceholder={false} />);
    expect(screen.getByTestId("spec-rail-right")).toHaveAttribute("data-rail-side", "right");
    expect(screen.queryByText("awaiting match_started…")).not.toBeInTheDocument();
  });

  it("keeps the left rail placeholder while awaiting match_started", () => {
    render(<SpecPanel gauges={[]} />);
    expect(screen.getByTestId("spec-rail-left")).toHaveAttribute("data-rail-side", "left");
    expect(screen.getByText("awaiting match_started…")).toBeInTheDocument();
  });
});
