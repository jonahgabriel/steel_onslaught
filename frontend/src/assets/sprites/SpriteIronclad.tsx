/**
 * SpriteIronclad — `chassis.heavy.ironclad_mk1`.
 *
 * Broad riveted slab, oversized boiler stack, heavy plating over tracks.
 * The widest, most armored silhouette.
 */
import type { JSX } from "react";
import { cssVar, SIDE_ACCENT } from "../theme";
import {
  Boiler,
  type ChassisSpriteProps,
  plate,
  Rivet,
  SpriteFrame,
  sideAccent,
  WreckCracks,
} from "./parts";

const boilerAt = { cx: 50, cy: 58, r: 12 };
const noseY = 26;

function body(): JSX.Element {
  return (
    <g>
      {/* tracks — long side treads */}
      <rect x={20} y={34} width={12} height={44} rx={3} {...plate} />
      <rect x={68} y={34} width={12} height={44} rx={3} {...plate} />
      {/* tread rungs */}
      <g stroke={cssVar("ash")} strokeWidth={2} vectorEffect="non-scaling-stroke">
        <path d="M20 44 h12 M20 54 h12 M20 64 h12 M68 44 h12 M68 54 h12 M68 64 h12" />
      </g>
      {/* broad hull slab */}
      <path d="M34 32 L66 32 L70 74 L30 74 Z" {...plate} />
      {/* prow */}
      <path d={`M50 ${noseY} L64 34 L36 34 Z`} {...plate} />
      {/* front armor accent band */}
      <line x1={36} y1={38} x2={64} y2={38} {...sideAccent} />
      {/* oversized boiler stack */}
      <Boiler {...boilerAt} />
      <rect x={44} y={70} width={12} height={10} rx={2} {...plate} />
      {/* rivet field */}
      <Rivet cx={38} cy={40} />
      <Rivet cx={62} cy={40} />
      <Rivet cx={36} cy={68} />
      <Rivet cx={64} cy={68} />
      <Rivet cx={50} cy={38} />
      <circle cx={50} cy={33} r={2.2} fill={SIDE_ACCENT} stroke="none" />
    </g>
  );
}

function wreck(): JSX.Element {
  return (
    <g>
      <path d="M32 34 L64 30 L70 72 L28 74 Z" {...plate} transform="rotate(-8 50 50)" />
      <rect x={18} y={36} width={11} height={40} rx={2} {...plate} transform="rotate(-8 50 50)" />
      <path
        d="M70 40 L86 34 M70 60 L88 66"
        stroke={cssVar("ash")}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
      <WreckCracks />
    </g>
  );
}

export function SpriteIronclad(props: ChassisSpriteProps): JSX.Element {
  return (
    <SpriteFrame
      chassis="ironclad"
      body={body()}
      wreck={wreck()}
      noseY={noseY}
      boilerAt={boilerAt}
      {...props}
    />
  );
}

export default SpriteIronclad;
