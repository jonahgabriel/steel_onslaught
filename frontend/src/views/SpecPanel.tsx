/**
 * SpecPanel — PRESSURE DECK left rail (Rev 2 mech spec panels).
 *
 * Two full mech readouts stacked RED over BLUE, each a projection of the same
 * envelope stream via `lib/gauges.ts` (restyled HeatBar / boiler dial reused,
 * not re-derived). Renders identity + seat assignment + vitals + thermal + mode
 * + per-weapon cooldowns + tallies + status — the fields folded in `GaugeState`.
 *
 * The seat line is the AUTHORITATIVE per-seat identity from MATCH_STARTED
 * `launch_provenance.seat_assignments`. It is deliberately rendered next to the
 * runtime-derived pilot line rather than merged into it: the two are separate
 * evidence sources, and a disagreement between them is a defect the operator
 * must be able to see.
 */
import type React from "react";
import { ChassisSprite, LampCooldown, LampReady, WEAPON_CLASS_GLYPH } from "../assets";
import {
  type GaugeState,
  type MechStatus,
  mechStateOf,
  pilotDescriptor,
  seatDescriptor,
} from "../lib/gauges";
import type { CardPriorities, Hands, PlayedCards } from "../lib/hands";
import type { Side } from "../lib/river";
import { weaponClassOf, weaponLabel } from "../lib/weapons";
import HandStrip from "./HandStrip";
import HeatBar from "./HeatBar";

const STATUS_LABEL: Record<MechStatus, string> = {
  alive: "NOMINAL",
  pilot_killed: "PILOT KILLED",
  destroyed: "DESTROYED",
};

const CLASS_CHIP: Record<GaugeState["chassisClass"], string> = {
  light: "LIGHT",
  medium: "MEDIUM",
  heavy: "HEAVY",
};

/** SVG boiler-pressure dial: amber arc, red zone, needle at current psi. */
function BoilerDial({
  mechId,
  current,
  maximum,
}: {
  mechId: string;
  current: number;
  maximum: number;
}): React.JSX.Element {
  const frac = maximum > 0 ? Math.max(0, Math.min(1, current / maximum)) : 0;
  const start = 150;
  const sweep = 240;
  const angle = start + frac * sweep;
  const cx = 46;
  const cy = 46;
  const r = 34;
  const rad = (deg: number): number => (deg * Math.PI) / 180;
  const arcPoint = (deg: number, radius: number): [number, number] => [
    cx + radius * Math.cos(rad(deg)),
    cy + radius * Math.sin(rad(deg)),
  ];
  const [nx, ny] = arcPoint(angle, r - 6);
  const [rzx1, rzy1] = arcPoint(start + sweep * 0.75, r);
  const [rzx2, rzy2] = arcPoint(start + sweep, r);
  /**
   * The arc command's large-arc-flag must be DERIVED from the swept angle, not
   * fixed (OMN-15584). With `rx == ry` the flag pair does not merely choose the
   * long or short way between two endpoints: it selects which of the two
   * circles through those endpoints is used. A hardcoded `1` on a sub-180°
   * sweep therefore draws the arc about a different center, off the dial face
   * and clipped by the viewBox into the fragments the operator reported.
   */
  const arcCommand = (fromDeg: number, toDeg: number): string => {
    const largeArc = Math.abs(toDeg - fromDeg) > 180 ? 1 : 0;
    return `M ${arcPoint(fromDeg, r).join(" ")} A ${r} ${r} 0 ${largeArc} 1 ${arcPoint(toDeg, r).join(" ")}`;
  };

  return (
    <svg className="pd-dial" width={80} height={68} viewBox="0 0 92 78" aria-hidden="true">
      <path d={arcCommand(start, start + sweep)} fill="none" stroke="#0d0f13" strokeWidth={7} />
      {/* A zero-length arc is dropped by the renderer, but its round line-cap
          still paints a stray dot on the dial face — omit it outright. */}
      {frac > 0 ? (
        <path
          data-testid={`spec-dial-value-${mechId}`}
          d={arcCommand(start, angle)}
          fill="none"
          stroke="var(--phosphor)"
          strokeWidth={5}
          strokeLinecap="round"
        />
      ) : null}
      <path
        data-testid={`spec-dial-redzone-${mechId}`}
        d={`M ${rzx1} ${rzy1} A ${r} ${r} 0 0 1 ${rzx2} ${rzy2}`}
        fill="none"
        stroke="var(--danger)"
        strokeWidth={5}
        opacity={0.85}
      />
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="var(--steam)" strokeWidth={2} />
      <circle cx={cx} cy={cy} r={3} fill="var(--steam)" />
      <text
        x={cx}
        y={cy + 20}
        textAnchor="middle"
        fontSize={11}
        fill="var(--ash)"
        fontFamily="var(--font-mono)"
      >
        {Math.round(current)}/{Math.round(maximum)}
      </text>
    </svg>
  );
}

function statLine(label: string, value: number | string, testid: string): React.JSX.Element {
  return (
    <div className="pd-tally" data-testid={testid}>
      <span className="pd-tally-k">{label}</span>
      <span className="pd-tally-v">{value}</span>
    </div>
  );
}

function WeaponRow({
  mechId,
  weaponId,
  cooldown,
}: {
  mechId: string;
  weaponId: string;
  cooldown: number;
}): React.JSX.Element {
  const cls = weaponClassOf(weaponId);
  const Glyph = WEAPON_CLASS_GLYPH[cls];
  const ready = cooldown <= 0;
  return (
    <div
      className="pd-weapon"
      data-testid={`spec-weapon-${mechId}-${weaponLabel(weaponId)}`}
      data-ready={ready}
      data-cooldown={cooldown}
    >
      <span className="pd-weapon-glyph" data-weapon-class={cls}>
        <Glyph size={13} />
      </span>
      <span className="pd-weapon-id">{weaponLabel(weaponId)}</span>
      {ready ? (
        <span className="pd-weapon-state" data-state="ready">
          <LampReady size={12} /> READY
        </span>
      ) : (
        <span className="pd-weapon-state" data-state="cooldown">
          <LampCooldown size={12} /> {cooldown}t
        </span>
      )}
    </div>
  );
}

function MechSpec({
  g,
  hands,
  priorities,
  played,
}: {
  g: GaugeState;
  hands: Hands;
  priorities: CardPriorities;
  played: PlayedCards;
}): React.JSX.Element {
  const armorPct =
    g.armorMax > 0 ? Math.max(0, Math.min(100, (g.armorValue / g.armorMax) * 100)) : 0;
  const hpPct = g.hpMax > 0 ? Math.max(0, Math.min(100, (g.hp / g.hpMax) * 100)) : 0;
  const redlinePct =
    g.ruptureThreshold > 0
      ? Math.max(0, Math.min(100, (g.redlineThreshold / g.ruptureThreshold) * 100))
      : 0;
  const spriteState = mechStateOf(g.hp, g.hpMax, g.status !== "destroyed");
  const pilot = pilotDescriptor(g);
  const seat = seatDescriptor(g);
  const weapons = Object.entries(g.weaponCooldowns);

  return (
    <section
      className="pd-spec pd-panel"
      data-side={g.side}
      data-status={g.status}
      data-testid={`spec-${g.mechId}`}
    >
      {/* identity */}
      <div className="pd-spec-id">
        <span className="pd-spec-thumb" data-testid={`spec-thumb-${g.mechId}`}>
          <ChassisSprite
            chassisClass={g.chassisClass}
            state={spriteState}
            side={g.side === "neutral" ? undefined : g.side}
            size={40}
          />
        </span>
        <div className="pd-spec-idtext">
          <div className="pd-spec-namerow">
            <span className="pd-spec-name" data-side={g.side}>
              {g.displayName}
            </span>
            <span className="pd-chip pd-classchip">{CLASS_CHIP[g.chassisClass]}</span>
          </div>
          <div className="pd-spec-pilot" data-testid={`spec-pilot-${g.mechId}`}>
            {pilot.kind} · {pilot.label}
          </div>
          {/* Authoritative seat identity from MATCH_STARTED launch_provenance —
              who was actually assigned this seat, as opposed to the pilot line
              above, which is derived from runtime LLM evidence. Rendering both
              is the point: a divergence between them is the seat-identity
              defect class, and it stayed invisible while this was unrendered. */}
          {seat !== null ? (
            <div
              className="pd-spec-seat"
              data-testid={`spec-seat-${g.mechId}`}
              data-seat-kind={seat.kind}
            >
              <span className="pd-chip pd-seatchip">{seat.kind}</span>
              <span className="pd-spec-seat-id">
                {seat.personaId === null
                  ? seat.identityId
                  : `${seat.personaId} · ${seat.identityId}`}
              </span>
              <span className="pd-spec-seat-kit">
                {seat.pilotSpecId} · {seat.loadoutId}
              </span>
            </div>
          ) : null}
        </div>
        <span className="pd-lamp" data-status={g.status} data-testid={`spec-status-${g.mechId}`}>
          {STATUS_LABEL[g.status]}
        </span>
      </div>

      {/* vitals */}
      <div className="pd-gauge-row">
        <span className="pd-gauge-label">HP</span>
        <div
          className="pd-hpbar"
          data-testid={`spec-hp-${g.mechId}`}
          data-hp-pct={Math.round(hpPct)}
        >
          <div className="pd-hpbar-fill" style={{ width: `${hpPct}%` }} />
          <span className="pd-hpbar-text">
            {Math.round(g.hp)}/{Math.round(g.hpMax)}
          </span>
        </div>
      </div>
      <div className="pd-gauge-row">
        <span className="pd-gauge-label">ARMOR</span>
        <div className="pd-armor" data-testid={`spec-armor-${g.mechId}`} data-armor={g.armorValue}>
          <div className="pd-armor-fill" style={{ width: `${armorPct}%` }} />
        </div>
      </div>
      <div className="pd-gauge-row">
        <span className="pd-gauge-label">HEAT</span>
        <div className="pd-heat-wrap" data-testid={`spec-heat-${g.mechId}`}>
          <HeatBar
            heat={g.heat}
            redlineThreshold={g.redlineThreshold}
            ruptureThreshold={g.ruptureThreshold}
          />
          <span className="pd-heat-redline" style={{ left: `${redlinePct}%` }} aria-hidden="true" />
        </div>
      </div>
      <div className="pd-spec-thermorow">
        <BoilerDial mechId={g.mechId} current={g.pressureCurrent} maximum={g.pressureMaximum} />
        <div className="pd-spec-lamps">
          {g.overloaded ? (
            <span className="pd-lamp pd-lamp-danger" data-testid={`spec-overloaded-${g.mechId}`}>
              OVERLOADED
            </span>
          ) : null}
          {g.redlineConsecutiveTicks > 0 ? (
            <span className="pd-lamp pd-lamp-warn" data-testid={`spec-redline-${g.mechId}`}>
              REDLINE {g.redlineConsecutiveTicks}t
            </span>
          ) : null}
          <span className="pd-mode-chip" data-testid={`spec-mode-${g.mechId}`}>
            {g.mode || "—"}
            {g.transitionToMode !== null ? (
              <span className="pd-mode-transition">
                {" ▸ "}
                {g.transitionToMode} ({g.transitionTicksRemaining}t)
              </span>
            ) : null}
          </span>
        </div>
      </div>

      {/* weapons */}
      {weapons.length > 0 ? (
        <div className="pd-weapons" data-testid={`spec-weapons-${g.mechId}`}>
          {weapons.map(([weaponId, cooldown]) => (
            <WeaponRow key={weaponId} mechId={g.mechId} weaponId={weaponId} cooldown={cooldown} />
          ))}
        </div>
      ) : null}

      {/* tallies */}
      <div className="pd-tallies">
        {statLine("DMG OUT", Math.round(g.damageDealt), `spec-dmg-dealt-${g.mechId}`)}
        {statLine("DMG IN", Math.round(g.damageTaken), `spec-dmg-taken-${g.mechId}`)}
        {statLine("SHOTS", g.shotsFired, `spec-shots-${g.mechId}`)}
        {statLine("DECISIONS", g.decisions, `spec-decisions-${g.mechId}`)}
      </div>
      <HandStrip
        mechId={g.mechId}
        hand={hands[g.mechId]}
        side={g.side}
        priorities={priorities}
        played={played[g.mechId]}
      />
    </section>
  );
}

export interface SpecPanelProps {
  gauges: readonly GaugeState[];
  hands?: Hands;
  priorities?: CardPriorities;
  played?: PlayedCards;
  side?: "left" | "right";
  emptyPlaceholder?: boolean;
}

const SIDE_ORDER: Record<Side, number> = { red: 0, blue: 1, neutral: 2 };

export default function SpecPanel({
  gauges,
  hands = {},
  priorities = {},
  played = {},
  side = "left",
  emptyPlaceholder = true,
}: SpecPanelProps): React.JSX.Element {
  const ordered = [...gauges].sort((a, b) => SIDE_ORDER[a.side] - SIDE_ORDER[b.side]);
  return (
    <div className="pd-rail" data-rail-side={side} data-testid={`spec-rail-${side}`}>
      {ordered.length === 0 ? (
        emptyPlaceholder ? (
          <div className="pd-earlier">awaiting match_started…</div>
        ) : null
      ) : (
        ordered.map((g) => (
          <MechSpec key={g.mechId} g={g} hands={hands} priorities={priorities} played={played} />
        ))
      )}
    </div>
  );
}
