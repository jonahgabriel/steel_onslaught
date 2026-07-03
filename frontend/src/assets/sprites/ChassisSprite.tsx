/**
 * ChassisSprite — dispatcher that picks the right sprite for a chassis class
 * or chassis id. Convenience for the arena + spec panels, which fold a
 * `chassis_class` / `chassis_id` off the mech payload.
 */
import type { JSX } from "react";
import { CHASSIS_ID_TO_CLASS, type ChassisClass } from "../theme";
import type { ChassisSpriteProps } from "./parts";
import { SpriteHunter } from "./SpriteHunter";
import { SpriteIronclad } from "./SpriteIronclad";
import { SpriteScout } from "./SpriteScout";

const BY_CLASS: Record<ChassisClass, (p: ChassisSpriteProps) => JSX.Element> = {
  light: SpriteScout,
  medium: SpriteHunter,
  heavy: SpriteIronclad,
};

export interface ChassisSpriteDispatchProps extends ChassisSpriteProps {
  /** Chassis class, or a `chassis.<class>.<name>` id resolved to its class. */
  chassisClass?: ChassisClass;
  chassisId?: string;
}

export function ChassisSprite({
  chassisClass,
  chassisId,
  ...rest
}: ChassisSpriteDispatchProps): JSX.Element {
  const cls: ChassisClass =
    chassisClass ?? (chassisId ? CHASSIS_ID_TO_CLASS[chassisId] : undefined) ?? "medium";
  const Sprite = BY_CLASS[cls];
  return <Sprite {...rest} />;
}

export default ChassisSprite;
