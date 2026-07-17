/**
 * SpriteScout — `chassis.light.scout_mk1`.
 *
 * Slim bipedal frame, small boiler, antenna array. Fast, narrow silhouette.
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

const boilerAt = { cx: 50, cy: 55, r: 7 };
const noseY = 22;

function body(): JSX.Element {
  return (
    <g>
      {/* legs — thin, splayed */}
      <path d="M40 52 L30 82 L37 84 L44 58 Z" {...plate} />
      <path d="M60 52 L70 82 L63 84 L56 58 Z" {...plate} />
      {/* narrow torso */}
      <path d="M42 30 L58 30 L60 62 L40 62 Z" {...plate} />
      {/* cockpit prow */}
      <path d={`M50 ${noseY} L58 32 L42 32 Z`} {...plate} />
      {/* side accent spine */}
      <line x1={50} y1={30} x2={50} y2={60} {...sideAccent} />
      {/* antenna array */}
      <g stroke={cssVar("ash")} strokeWidth={2} vectorEffect="non-scaling-stroke" fill="none">
        <path d="M50 26 L44 14 M50 26 L50 12 M50 26 L56 14" />
      </g>
      <circle cx={50} cy={12} r={1.6} fill={SIDE_ACCENT} stroke="none" />
      <Boiler {...boilerAt} />
      <Rivet cx={44} cy={36} />
      <Rivet cx={56} cy={36} />
    </g>
  );
}

function wreck(): JSX.Element {
  return (
    <g>
      <path d="M42 34 L57 32 L58 60 L38 58 Z" {...plate} transform="rotate(-14 50 50)" />
      <path d="M40 54 L32 78 L38 80 L45 58 Z" {...plate} transform="rotate(-14 50 50)" />
      <path
        d="M62 50 L72 76"
        stroke={cssVar("ash")}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
      <WreckCracks />
    </g>
  );
}

export function SpriteScout(props: ChassisSpriteProps): JSX.Element {
  return (
    <SpriteFrame
      chassis="scout"
      body={body()}
      wreck={wreck()}
      noseY={noseY}
      boilerAt={boilerAt}
      {...props}
    />
  );
}

export default SpriteScout;
