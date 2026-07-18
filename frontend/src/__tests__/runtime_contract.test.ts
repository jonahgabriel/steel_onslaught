import { describe, expect, it } from "vitest";
import { parseRuntimeCommand } from "../lib/runtime_contract";

const base = {
  schema_version: "1",
  kind: "steel_onslaught.runtime_command",
  command_id: "11111111-1111-4111-8111-111111111111",
  expected_revision: 0,
  owner_id: "runtime_owner.browser",
} as const;

describe("runtime command contract", () => {
  it.each(["one_game", "continuous"] as const)("accepts start/%s", (mode) => {
    expect(parseRuntimeCommand({ ...base, action: "start", mode })).toMatchObject({
      action: "start",
      mode,
      expected_revision: 0,
    });
  });

  it.each(["pause", "resume", "stop"] as const)("accepts %s without mode", (action) => {
    expect(parseRuntimeCommand({ ...base, action })).toMatchObject({ action });
  });

  it("rejects unknown fields", () => {
    expect(() => parseRuntimeCommand({ ...base, action: "pause", unexpected: true })).toThrow(
      /unknown field unexpected/,
    );
  });

  it("rejects missing and mismatched lifecycle fields", () => {
    expect(() => parseRuntimeCommand({ ...base, action: "start" })).toThrow(/missing field mode/);
    expect(() => parseRuntimeCommand({ ...base, action: "pause", mode: "one_game" })).toThrow(
      /unknown field mode/,
    );
    expect(() => parseRuntimeCommand({ ...base, action: "start", mode: "invalid" })).toThrow(
      /start mode/,
    );
  });

  it("rejects non-integral revisions and empty owners", () => {
    expect(() => parseRuntimeCommand({ ...base, action: "pause", expected_revision: 1.5 })).toThrow(
      /expected_revision/,
    );
    expect(() => parseRuntimeCommand({ ...base, action: "pause", owner_id: "" })).toThrow(
      /owner_id/,
    );
    expect(() =>
      parseRuntimeCommand({ ...base, action: "pause", command_id: "not-a-uuid" }),
    ).toThrow(/command_id.*UUID/);
    expect(() =>
      parseRuntimeCommand({ ...base, action: "pause", owner_id: "o".repeat(129) }),
    ).toThrow(/owner_id.*128/);
    expect(() =>
      parseRuntimeCommand({
        ...base,
        action: "pause",
        expected_revision: Number.MAX_SAFE_INTEGER + 1,
      }),
    ).toThrow(/expected_revision/);
  });

  it.each([
    "11111111111141118111111111111111",
    "{11111111-1111-4111-8111-111111111111}",
  ])("rejects non-canonical UUID spellings: %s", (commandId) => {
    expect(() => parseRuntimeCommand({ ...base, action: "pause", command_id: commandId })).toThrow(
      /command_id.*UUID/,
    );
  });
});
