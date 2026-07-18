/**
 * Compact, read-only arena feedback strip.
 *
 * Every field is derived from the same rows folded by PressureDeck.  The
 * component intentionally presents intent/rationale/score evidence without
 * introducing a writable card/register protocol that the current stream does
 * not expose.
 */
import type React from "react";
import { useMemo } from "react";
import {
  buildDecisionCards,
  buildLeague,
  buildMomentum,
  buildRecap,
  buildTelegraphs,
} from "../lib/feedback";
import { useReducedMotion } from "../lib/motion";
import type { RiverRow, SideMap } from "../lib/river";

export interface ArenaFeedbackProps {
  readonly rows: readonly RiverRow[];
  readonly sides: SideMap;
}

function sideName(side: "red" | "blue" | "neutral"): string {
  return side === "neutral" ? "NEUTRAL" : side.toUpperCase();
}

function shortId(id: string): string {
  const dot = id.lastIndexOf(".");
  return dot === -1 ? id : id.slice(dot + 1);
}

export default function ArenaFeedback({
  rows,
  sides,
}: ArenaFeedbackProps): React.JSX.Element | null {
  const reducedMotion = useReducedMotion();
  const momentum = useMemo(() => buildMomentum(rows, sides), [rows, sides]);
  const telegraphs = useMemo(() => buildTelegraphs(rows, sides), [rows, sides]);
  const recap = useMemo(() => buildRecap(rows, sides), [rows, sides]);
  const decisions = useMemo(() => buildDecisionCards(rows, sides), [rows, sides]);
  const league = useMemo(() => buildLeague(rows, sides), [rows, sides]);

  if (rows.length === 0) return null;

  return (
    <aside className="pd-feedback pd-panel" data-testid="arena-feedback">
      <div className="pd-feedback-head">
        <span>TACTICAL FEEDBACK</span>
        <span className="pd-feedback-kicker" data-testid="feedback-leader">
          {momentum.leader === "neutral" ? "EVEN FLOW" : `${sideName(momentum.leader)} EDGE`}
        </span>
      </div>

      <div className="pd-feedback-momentum" data-testid="feedback-momentum">
        <div className="pd-feedback-meter" data-side="red">
          <span>RED</span>
          <div className="pd-feedback-track" aria-hidden="true">
            <span style={{ width: `${momentum.red}%` }} />
          </div>
          <b data-testid="feedback-momentum-red">{momentum.red}</b>
        </div>
        <div className="pd-feedback-meter" data-side="blue">
          <span>BLUE</span>
          <div className="pd-feedback-track" aria-hidden="true">
            <span style={{ width: `${momentum.blue}%` }} />
          </div>
          <b data-testid="feedback-momentum-blue">{momentum.blue}</b>
        </div>
      </div>

      {telegraphs.length > 0 ? (
        <section className="pd-feedback-section" data-testid="feedback-telegraphs">
          <div className="pd-feedback-label">INTENT TELEGRAPHS</div>
          <div className="pd-feedback-list">
            {telegraphs.map((item) => (
              <div
                className="pd-feedback-intent"
                data-side={item.side}
                data-phase={item.status}
                data-testid={`feedback-telegraph-${item.messageId}`}
                key={item.messageId}
              >
                <span className="pd-feedback-phase">{item.status}</span>
                <span className="pd-feedback-intent-kind">{item.kind}</span>
                <span className="pd-feedback-intent-label">{item.label}</span>
                <span className="pd-feedback-tick">T{item.tick}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {decisions.length > 0 ? (
        <section className="pd-feedback-section" data-testid="feedback-decisions">
          <div className="pd-feedback-label">PILOT CARDS · READ ONLY</div>
          <div className="pd-feedback-list">
            {decisions.map((card) => (
              <div
                className="pd-feedback-card"
                data-side={card.side}
                data-testid={`feedback-card-${card.mechId}`}
                key={card.mechId}
              >
                <div className="pd-feedback-card-head">
                  <span>{shortId(card.mechId)}</span>
                  <span>{card.action.toUpperCase()}</span>
                  <span>{Math.round(card.confidence * 100)}%</span>
                </div>
                <div className="pd-feedback-card-reason">{card.reason.replaceAll("_", " ")}</div>
                {card.rationale !== null && card.rationale.trim() !== "" ? (
                  <div
                    className="pd-feedback-rationale"
                    data-reduced-motion={reducedMotion}
                    title={card.rationale}
                  >
                    “{card.rationale}”
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {recap.length > 0 ? (
        <section className="pd-feedback-section" data-testid="feedback-recap">
          <div className="pd-feedback-label">ROUND RECAP</div>
          <div className="pd-feedback-list">
            {recap.map((item) => (
              <div
                className="pd-feedback-recap"
                data-side={item.side}
                data-testid={`feedback-recap-${item.eventId}`}
                key={item.eventId}
              >
                <span>T{item.tick}</span>
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {league !== null ? (
        <section className="pd-feedback-section pd-feedback-league" data-testid="feedback-league">
          <div className="pd-feedback-label">
            LEAGUE SCORECARD · {league.isDraw ? "DRAW" : `${league.durationTicks} TICKS`}
          </div>
          <div className="pd-feedback-list">
            {league.entries.map((entry) => (
              <div
                className="pd-feedback-score"
                data-side={entry.side}
                data-winner={entry.winner}
                data-testid={`feedback-score-${entry.playerId}`}
                key={entry.playerId}
              >
                <span>{sideName(entry.side)}</span>
                <b>{entry.score.toFixed(1)}</b>
                <span>
                  {entry.damageDealt.toFixed(0)} dmg · {Math.round(entry.efficiency * 100)}% eff
                </span>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </aside>
  );
}
