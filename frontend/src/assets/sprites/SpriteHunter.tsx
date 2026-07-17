/**
 * SpriteHunter — `chassis.medium.hunter_mk1`.
 *
 * Balanced quad-shoulder frame, mid boiler, twin vents. The four shoulder
 * pods are the signature silhouette.
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

const boilerAt = { cx: 50, cy: 52, r: 9 };
const noseY = 24;

function shoulder(cx: number, cy: number): JSX.Element {
  return <rect x={cx - 9} y={cy - 7} width={18} height={14} rx={3} {...plate} />;
}

function body(): JSX.Element {
  return (
    <g>
      {/* four shoulder pods */}
      {shoulder(30, 40)}
      {shoulder(70, 40)}
      {shoulder(30, 62)}
      {shoulder(70, 62)}
      {/* central hull */}
      <path d="M40 30 L60 30 L64 68 L36 68 Z" {...plate} />
      {/* prow */}
      <path d={`M50 ${noseY} L60 32 L40 32 Z`} {...plate} />
      {/* twin vents at the rear */}
      <rect x={43} y={66} width={5} height={10} rx={1.5} {...plate} />
      <rect x={52} y={66} width={5} height={10} rx={1.5} {...plate} />
      {/* side accent shoulders */}
      <line x1={30} y1={40} x2={30} y2={62} {...sideAccent} />
      <line x1={70} y1={40} x2={70} y2={62} {...sideAccent} />
      <Boiler {...boilerAt} />
      <Rivet cx={41} cy={35} />
      <Rivet cx={59} cy={35} />
      <Rivet cx={39} cy={64} />
      <Rivet cx={61} cy={64} />
      <circle cx={50} cy={30} r={2} fill={SIDE_ACCENT} stroke="none" />
    </g>
  );
}

function wreck(): JSX.Element {
  return (
    <g>
      <path d="M38 32 L58 28 L64 64 L34 66 Z" {...plate} transform="rotate(11 50 50)" />
      <rect x={21} y={40} width={16} height={12} rx={2} {...plate} transform="rotate(11 50 50)" />
      <path
        d="M66 44 L82 40"
        stroke={cssVar("ash")}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
      <WreckCracks />
    </g>
  );
}

export function SpriteHunter(props: ChassisSpriteProps): JSX.Element {
  return (
    <SpriteFrame
      chassis="hunter"
      body={body()}
      wreck={wreck()}
      noseY={noseY}
      boilerAt={boilerAt}
      {...props}
    />
  );
}

export default SpriteHunter;
