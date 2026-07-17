/**
 * Safe player-selection intent UI.
 *
 * The bootstrap projection owns which options exist and which seat may use
 * them. Browser state is only an unsubmitted intent: it is never a match
 * assignment. The production App injects no command capability in Phase 53,
 * so Start remains disabled and this component cannot launch a match.
 */
import type React from "react";
import { useState } from "react";
import type {
  FrontendBootstrap,
  PlayerRosterProjection,
  PlayerSide,
  PublicPlayerOption,
} from "../lib/application";

export interface MatchStartIntent {
  readonly expected_overlay_sha256: string;
  readonly roster_id: string;
  readonly expected_roster_sha256: string;
  readonly selections: readonly [
    { readonly side: "red"; readonly option_id: string },
    { readonly side: "blue"; readonly option_id: string },
  ];
}

export interface MatchStartIntentCapability {
  requestStart(intent: MatchStartIntent): void;
}

export interface MatchSetupProps {
  readonly bootstrap: FrontendBootstrap;
  readonly capability?: MatchStartIntentCapability;
}

function optionsFor(
  roster: PlayerRosterProjection,
  side: PlayerSide,
): readonly PublicPlayerOption[] {
  const policy = roster.seats.find((seat) => seat.side === side);
  if (policy === undefined) return [];
  const allowed = new Set(policy.allowed_option_ids);
  return roster.options.filter((option) => allowed.has(option.option_id));
}

function optionLabel(option: PublicPlayerOption): string {
  if (option.kind === "human") return `${option.display_name} · HUMAN`;
  return `${option.display_name} · ${option.model_identity_id}`;
}

function PlayerSelect({
  side,
  options,
  value,
  onChange,
}: {
  readonly side: PlayerSide;
  readonly options: readonly PublicPlayerOption[];
  readonly value: string;
  readonly onChange: (optionId: string) => void;
}): React.JSX.Element {
  const allowed = new Set(options.map((option) => option.option_id));
  return (
    <label className="so-setup-seat" data-side={side}>
      <span>{side.toUpperCase()} PILOT</span>
      <select
        aria-label={`${side} pilot`}
        value={value}
        onChange={(event) => {
          const candidate = event.currentTarget.value;
          onChange(candidate === "" || allowed.has(candidate) ? candidate : "");
        }}
      >
        <option value="">SELECT PILOT</option>
        {options.map((option) => (
          <option key={option.option_id} value={option.option_id}>
            {optionLabel(option)}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function MatchSetup({ bootstrap, capability }: MatchSetupProps): React.JSX.Element {
  const [redOptionId, setRedOptionId] = useState("");
  const [blueOptionId, setBlueOptionId] = useState("");
  const roster = bootstrap.player_roster;

  if (roster === null) {
    return (
      <section className="so-match-setup pd-panel" aria-label="Match setup">
        <h2>PLAYER SELECT</h2>
        <p data-testid="roster-unavailable">SERVER ROSTER UNAVAILABLE</p>
        <button type="button" disabled>
          START DISABLED
        </button>
      </section>
    );
  }

  const redOptions = optionsFor(roster, "red");
  const blueOptions = optionsFor(roster, "blue");
  const redSelectionAllowed = redOptions.some((option) => option.option_id === redOptionId);
  const blueSelectionAllowed = blueOptions.some((option) => option.option_id === blueOptionId);
  const rosterId = roster.roster_id;
  const rosterSha256 = roster.roster_sha256;
  const ready = redSelectionAllowed && blueSelectionAllowed && capability !== undefined;

  function submit(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!redSelectionAllowed || !blueSelectionAllowed || capability === undefined) return;
    capability.requestStart({
      expected_overlay_sha256: bootstrap.overlay_sha256,
      roster_id: rosterId,
      expected_roster_sha256: rosterSha256,
      selections: [
        { side: "red", option_id: redOptionId },
        { side: "blue", option_id: blueOptionId },
      ],
    });
  }

  return (
    <form className="so-match-setup pd-panel" aria-label="Match setup" onSubmit={submit}>
      <div className="so-setup-heading">
        <h2>PLAYER SELECT</h2>
        <span>{roster.roster_id}</span>
      </div>
      <div className="so-setup-seats">
        <PlayerSelect
          side="red"
          options={redOptions}
          value={redOptionId}
          onChange={setRedOptionId}
        />
        <PlayerSelect
          side="blue"
          options={blueOptions}
          value={blueOptionId}
          onChange={setBlueOptionId}
        />
      </div>
      <button type="submit" disabled={!ready}>
        {capability === undefined ? "START DISABLED" : "START MATCH"}
      </button>
    </form>
  );
}
