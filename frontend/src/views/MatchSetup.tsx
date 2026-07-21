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
  ModelCatalogProjection,
  PlayerRosterProjection,
  PlayerSide,
  PublicModelCatalogOption,
  PublicPlayerOption,
} from "../lib/application";
import type { BrowserActionIntent, BrowserHumanTurnPrompt } from "../lib/command_gateway";
import type { OverlayFragment } from "../lib/prompt_rules";
import PromptRulesWorkbench from "./PromptRulesWorkbench";

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
  /** Canonical MATCH_STARTED has arrived; hide only the launch form. */
  readonly matchStarted?: boolean;
  /** Optional subscribed status snapshot used to invalidate the launch form. */
  readonly gatewayStatus?: MatchStartIntentCapability["status"];
}

function optionsFor(
  roster: PlayerRosterProjection,
  side: PlayerSide,
  catalog: ModelCatalogProjection | null,
): readonly PickerOption[] {
  const policy = roster.seats.find((seat) => seat.side === side);
  if (policy === undefined) return [];
  const allowed = new Set(policy.allowed_option_ids);
  const rosterOptions = roster.options.filter((option) => allowed.has(option.option_id));
  if (catalog === null) return rosterOptions;
  const catalogOptions = new Map(catalog.options.map((option) => [option.option_id, option]));
  return rosterOptions.map((option) => catalogOptions.get(option.option_id) ?? option);
}

function defaultOptionId(
  roster: PlayerRosterProjection | null,
  side: PlayerSide,
  catalog: ModelCatalogProjection | null,
): string {
  if (roster === null) return "";
  const policy = roster.seats.find((seat) => seat.side === side);
  if (policy === undefined) return "";
  const catalogDefault = catalog?.default_option_ids[side === "red" ? 0 : 1] ?? null;
  const candidate = catalogDefault ?? policy.default_option_id;
  if (candidate === null) return "";
  const allowed = new Set(optionsFor(roster, side, catalog).map((option) => option.option_id));
  return allowed.has(candidate) ? candidate : "";
}

type PickerOption = PublicPlayerOption | PublicModelCatalogOption;

function optionLabel(option: PickerOption): string {
  if (option.kind === "human") return `${option.display_name} · HUMAN`;
  // A catalog projection carries the persona, so an operator can tell
  // "Qwen35 / sniper" from "Qwen35 / berserker" instead of reading an opaque
  // option id.  The roster-only projection has no persona, so it falls back to
  // the model identity it does carry.
  if ("persona_id" in option) {
    return `${option.display_name} · ${option.provider_binding_id} / ${option.persona_id}`;
  }
  return `${option.display_name} · ${option.model_identity_id}`;
}

/**
 * The (decision-maker, role) pair the server enforces seat identity on.
 *
 * A model option's decision-maker is its provider binding plus its persona; a
 * human option's is the operator behind it.  Two seats that resolve to the same
 * pair are a mirror — the server rejects it — while the same persona on two
 * different models is a legal, and the most informative, contest.  Only the
 * catalog projection carries the fields to compute this; a roster-only
 * projection falls back to option identity so the client never over-blocks a
 * pairing the server would actually admit.
 */
function seatIdentity(option: PickerOption): string {
  if (option.kind === "human") {
    return "human_identity_id" in option
      ? `human:${option.human_identity_id}`
      : `option:${option.option_id}`;
  }
  if ("persona_id" in option) {
    return `model:${option.provider_binding_id}:${option.persona_id}`;
  }
  return `option:${option.option_id}`;
}

function mirrorConflictMessage(red: PickerOption, blue: PickerOption): string | null {
  if (seatIdentity(red) !== seatIdentity(blue)) return null;
  if (red.kind === "human" && blue.kind === "human") {
    return "Both seats are the same operator. Pick a model for one seat.";
  }
  const shared =
    "persona_id" in red ? `${red.provider_binding_id} / ${red.persona_id}` : red.display_name;
  return (
    `Both seats would be the same pilot (${shared}). ` +
    "Change the model or the persona on one seat — the same persona on two " +
    "different models is allowed."
  );
}

function PlayerSelect({
  side,
  options,
  value,
  onChange,
}: {
  readonly side: PlayerSide;
  readonly options: readonly PickerOption[];
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
  matchStarted = false,
  gatewayStatus,
}: MatchSetupProps): React.JSX.Element {
  const roster = bootstrap.player_roster;
  const catalog = bootstrap.model_catalog;
  const promptProvenance = bootstrap.prompt_provenance;
  const ruleCatalog = bootstrap.rule_catalog;
  const [redOptionId, setRedOptionId] = useState(() => defaultOptionId(roster, "red", catalog));
  const [blueOptionId, setBlueOptionId] = useState(() => defaultOptionId(roster, "blue", catalog));
  // The derived overlay fragment for any pending prompt/rule edits. It is the
  // exact fragment `so prompts set` / `so rules set` emit; an edit takes effect
  // only through the overlay -> composition -> MATCH_STARTED provenance path,
  // which is what keeps an edited prompt recorded in the ledger and
  // replay-detectable rather than mutating a live match out of band.
  const [editedFragment, setEditedFragment] = useState<OverlayFragment | null>(null);
  const pendingPromptEdits = editedFragment?.persona_overrides ?? [];

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

  const redOptions = optionsFor(roster, "red", catalog);
  const blueOptions = optionsFor(roster, "blue", catalog);
  const redOption = redOptions.find((option) => option.option_id === redOptionId);
  const blueOption = blueOptions.find((option) => option.option_id === blueOptionId);
  const redSelectionAllowed = redOption !== undefined;
  const blueSelectionAllowed = blueOption !== undefined;
  // A mirror is the one legal-looking pairing the server still rejects, so the
  // client explains it up front rather than surfacing the rejection as a
  // generic failure after a round trip. This is only computed against the
  // catalog projection, which carries the (provider, persona) identity the
  // server enforces; a roster-only projection cannot see that identity, so the
  // client defers to the server there rather than guessing from option ids.
  const conflictMessage =
    catalog !== null && redOption !== undefined && blueOption !== undefined
      ? mirrorConflictMessage(redOption, blueOption)
      : null;
  const rosterId = roster.roster_id;
  const rosterSha256 = roster.roster_sha256;
  const gatewayEnabled = capability?.enabled !== false;
  const status = gatewayStatus ?? capability?.status;
  const starting = status === "pending" || status === "accepted";
  const ready =
    redSelectionAllowed &&
    blueSelectionAllowed &&
    conflictMessage === null &&
    capability !== undefined &&
    gatewayEnabled;

  function submit(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (
      !redSelectionAllowed ||
      !blueSelectionAllowed ||
      conflictMessage !== null ||
      capability === undefined
    )
      return;
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
      {!matchStarted ? (
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
          {conflictMessage !== null ? (
            <p className="so-setup-conflict" role="alert" data-testid="seat-identity-conflict">
              {conflictMessage}
            </p>
          ) : null}
          {pendingPromptEdits.length > 0 ? (
            <p className="so-pending-prompt-edits" data-testid="pending-prompt-edits">
              {pendingPromptEdits.length} prompt edit
              {pendingPromptEdits.length === 1 ? "" : "s"} pending (
              {pendingPromptEdits.map((override) => override.persona_id).join(", ")}). Saved edits
              run through the overlay and are recorded in MATCH_STARTED.
            </p>
          ) : null}
          <button type="submit" disabled={!ready || starting}>
            {capability === undefined || !gatewayEnabled
              ? "START DISABLED"
              : status === "accepted"
                ? "START ACCEPTED"
                : status === "pending"
                  ? "START PENDING"
                  : "START MATCH"}
          </button>
        </form>
      ) : null}
      {!matchStarted && promptProvenance !== null && ruleCatalog !== null ? (
        <details className="so-prompt-rules pd-panel" data-testid="prompt-rules-workbench">
          <summary>PROMPT &amp; RULE WORKBENCH</summary>
          <PromptRulesWorkbench
            provenance={promptProvenance}
            catalog={ruleCatalog}
            onFragmentChange={setEditedFragment}
          />
        </details>
      ) : null}
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
