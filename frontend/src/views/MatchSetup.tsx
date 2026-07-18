/**
 * Safe player-selection intent UI.
 *
 * The bootstrap projection owns which options exist and which seat may use
 * them. Browser state is only an unsubmitted intent: it is never a match
 * assignment. The production App injects the command capability from the
 * validated bootstrap. Defaults come only from each server-declared seat
 * policy; there is no identifier/display-name inference. A null default leaves
 * the seat empty and keeps start disabled until an allowed option is chosen.
 */
import type React from "react";
import { useState } from "react";
import type {
  FrontendBootstrap,
  PlayerRosterProjection,
  PlayerSide,
  PublicPlayerOption,
} from "../lib/application";
import type { BrowserActionIntent, BrowserHumanTurnPrompt } from "../lib/command_gateway";

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
  readonly enabled?: boolean;
  readonly status?: "idle" | "pending" | "accepted" | "cancelled" | "failed" | "rejected";
  cancel?(): void;
  submitAction?(action: BrowserActionIntent): void;
}

export interface MatchSetupProps {
  readonly bootstrap: FrontendBootstrap;
  readonly capability?: MatchStartIntentCapability;
  readonly humanPrompt?: BrowserHumanTurnPrompt | null;
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

function defaultOptionId(roster: PlayerRosterProjection | null, side: PlayerSide): string {
  if (roster === null) return "";
  const policy = roster.seats.find((seat) => seat.side === side);
  if (policy === undefined || policy.default_option_id === null) return "";
  const allowed = new Set(optionsFor(roster, side).map((option) => option.option_id));
  return allowed.has(policy.default_option_id) ? policy.default_option_id : "";
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

export default function MatchSetup({
  bootstrap,
  capability,
  humanPrompt,
}: MatchSetupProps): React.JSX.Element {
  const roster = bootstrap.player_roster;
  const [redOptionId, setRedOptionId] = useState(() => defaultOptionId(roster, "red"));
  const [blueOptionId, setBlueOptionId] = useState(() => defaultOptionId(roster, "blue"));

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
  const gatewayEnabled = capability?.enabled !== false;
  const pending = capability?.status === "pending";
  const ready =
    redSelectionAllowed && blueSelectionAllowed && capability !== undefined && gatewayEnabled;

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
    <>
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
        <button type="submit" disabled={!ready || pending}>
          {capability === undefined || !gatewayEnabled
            ? "START DISABLED"
            : pending
              ? "START PENDING"
              : "START MATCH"}
        </button>
      </form>
      {humanPrompt !== null &&
      humanPrompt !== undefined &&
      capability?.submitAction !== undefined ? (
        <section className="so-human-turn pd-panel" aria-label="Human turn">
          <div className="so-setup-heading">
            <h2>{humanPrompt.side.toUpperCase()} ACTION</h2>
            <span>Tick {humanPrompt.expected_tick}</span>
          </div>
          <div className="so-setup-seats">
            {humanPrompt.available_actions.map((action) => (
              <button
                key={JSON.stringify(action)}
                type="button"
                onClick={() =>
                  capability.submitAction?.({
                    match_id: humanPrompt.match_id,
                    side: humanPrompt.side,
                    turn_id: humanPrompt.turn_id,
                    expected_tick: humanPrompt.expected_tick,
                    observation_sha256: humanPrompt.observation_sha256,
                    action,
                  })
                }
              >
                {String(action["kind"]).replaceAll("_", " ").toUpperCase()}
              </button>
            ))}
            <button type="button" onClick={() => capability.cancel?.()}>
              CANCEL TURN
            </button>
          </div>
        </section>
      ) : null}
    </>
  );
}
