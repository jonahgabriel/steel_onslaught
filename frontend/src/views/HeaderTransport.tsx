/**
 * HeaderTransport — the deck's transport rail: play/pause, step ±1 tick,
 * restart, LIVE, speed toggle, and the multi-match picker.
 *
 * Presentational only: every action is a callback into the transport engine
 * (or the deck's local fallback when the engine is absent). Step/restart/LIVE/
 * picker render only when their handlers are wired (transport mode); the
 * play/pause + speed controls always render so an isolated deck still works.
 */
import type React from "react";
import type { MatchSummary, TransportSpeed } from "../lib/transport";

const SPEEDS: readonly TransportSpeed[] = [1, 2, 4];

/** Last dotted segment — "match.demo.0007" → "0007", "mech.red.01" → "01". */
function shortId(id: string): string {
  const parts = id.split(".");
  return parts[parts.length - 1] || id;
}

function matchLabel(m: MatchSummary): string {
  const sides = m.redLabel && m.blueLabel ? `${shortId(m.redLabel)}v${shortId(m.blueLabel)}` : "—";
  return `${shortId(m.matchId)} · ${sides} · ${m.tickCount}t`;
}

export interface HeaderTransportProps {
  playing: boolean;
  live: boolean;
  speed: TransportSpeed;
  matches: readonly MatchSummary[];
  activeMatchId: string | null;
  onTogglePlay: () => void;
  onSetSpeed: (speed: TransportSpeed) => void;
  onStepBackward?: () => void;
  onStepForward?: () => void;
  onRestart?: () => void;
  onGoLive?: () => void;
  onSelectMatch?: (matchId: string) => void;
}

export default function HeaderTransport(props: HeaderTransportProps): React.JSX.Element {
  const {
    playing,
    live,
    speed,
    matches,
    activeMatchId,
    onTogglePlay,
    onSetSpeed,
    onStepBackward,
    onStepForward,
    onRestart,
    onGoLive,
    onSelectMatch,
  } = props;

  const playLabel = playing ? (live ? "▶ LIVE" : "▶ PLAY") : "∥ HELD";

  return (
    <div className="pd-transport" data-testid="transport">
      {onSelectMatch !== undefined && matches.length > 0 ? (
        <label className="pd-match-picker" data-testid="match-picker">
          <span className="pd-match-picker-label">MATCH</span>
          <select
            className="pd-select"
            aria-label="Select match"
            value={activeMatchId ?? ""}
            onChange={(e) => onSelectMatch(e.target.value)}
          >
            {matches.map((m) => (
              <option key={m.matchId} value={m.matchId}>
                {matchLabel(m)}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {onStepBackward !== undefined ? (
        <button
          type="button"
          className="pd-tbtn"
          aria-label="Step back one tick"
          data-testid="transport-step-back"
          onClick={onStepBackward}
        >
          ⇤
        </button>
      ) : null}

      <button
        type="button"
        className="pd-tbtn"
        aria-pressed={playing}
        aria-label={playing ? "Pause" : "Play"}
        onClick={onTogglePlay}
        data-testid="transport-play"
      >
        {playLabel}
      </button>

      {onStepForward !== undefined ? (
        <button
          type="button"
          className="pd-tbtn"
          aria-label="Step forward one tick"
          data-testid="transport-step-fwd"
          onClick={onStepForward}
        >
          ⇥
        </button>
      ) : null}

      {onRestart !== undefined ? (
        <button
          type="button"
          className="pd-tbtn"
          aria-label="Restart from tick 0"
          data-testid="transport-restart"
          onClick={onRestart}
        >
          ⟲
        </button>
      ) : null}

      {onGoLive !== undefined ? (
        <button
          type="button"
          className="pd-tbtn"
          aria-pressed={live}
          aria-label="Jump to live"
          data-testid="transport-live"
          onClick={onGoLive}
        >
          LIVE
        </button>
      ) : null}

      <div className="pd-speed" data-testid="transport-speed">
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            className="pd-tbtn"
            aria-pressed={speed === s}
            aria-label={`Speed ${s}x`}
            data-testid={`transport-speed-${s}`}
            onClick={() => onSetSpeed(s)}
          >
            ×{s}
          </button>
        ))}
      </div>
    </div>
  );
}
