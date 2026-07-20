// @vitest-environment jsdom
import "./setup-dom";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModelCatalogProjection } from "../lib/application";
import { parseFrontendBootstrap } from "../lib/application";
import MatchSetup from "../views/MatchSetup";

const BOOTSTRAP_FIXTURE = resolve(
  process.cwd(),
  "src/__tests__/fixtures/bootstrap/frontend_bootstrap.json",
);

function bootstrap() {
  const raw: unknown = JSON.parse(readFileSync(BOOTSTRAP_FIXTURE, "utf-8"));
  return parseFrontendBootstrap(raw);
}

afterEach(cleanup);

describe("MatchSetup safe player intent", () => {
  it("defaults both seats to GLM and remains disabled without an injected capability", () => {
    render(<MatchSetup bootstrap={bootstrap()} />);
    const red = screen.getByLabelText("red pilot") as HTMLSelectElement;
    const blue = screen.getByLabelText("blue pilot") as HTMLSelectElement;
    const start = screen.getByRole("button", { name: "START DISABLED" });

    expect(red.value).toBe("player_option.glm_model");
    expect(blue.value).toBe("player_option.glm_model");
    expect(start).toBeDisabled();

    fireEvent.change(red, { target: { value: "player_option.browser_human" } });
    fireEvent.change(blue, { target: { value: "player_option.local_model" } });
    expect(red.value).toBe("player_option.browser_human");
    expect(blue.value).toBe("player_option.local_model");
    expect(start).toBeDisabled();
  });

  it("applies exact per-seat allowlists through one generic model option shape", () => {
    render(<MatchSetup bootstrap={bootstrap()} />);
    const red = screen.getByLabelText("red pilot") as HTMLSelectElement;
    const blue = screen.getByLabelText("blue pilot") as HTMLSelectElement;
    const redLabels = Array.from(red.options).map((option) => option.textContent);
    const blueLabels = Array.from(blue.options).map((option) => option.textContent);

    expect(redLabels).toContain("Browser Operator · HUMAN");
    expect(blueLabels).not.toContain("Browser Operator · HUMAN");
    for (const identity of [
      "model_identity.local",
      "model_identity.openrouter",
      "model_identity.glm",
      "model_identity.gemini",
    ]) {
      expect(redLabels.some((label) => label?.includes(identity))).toBe(true);
      expect(blueLabels.some((label) => label?.includes(identity))).toBe(true);
    }
    expect(red.textContent).not.toMatch(/endpoint_url|provider_binding_id|secret_ref|token|key/i);
  });

  it("defaults both model-capable seats to the configured GLM option", () => {
    render(<MatchSetup bootstrap={bootstrap()} capability={{ requestStart: vi.fn() }} />);
    expect((screen.getByLabelText("red pilot") as HTMLSelectElement).value).toBe(
      "player_option.glm_model",
    );
    expect((screen.getByLabelText("blue pilot") as HTMLSelectElement).value).toBe(
      "player_option.glm_model",
    );
    expect(screen.getByRole("button", { name: "START MATCH" })).toBeEnabled();
  });

  it("uses the canonical catalog projection for provider labels and differentiated defaults", () => {
    const initial = bootstrap();
    if (initial.player_roster === null) throw new Error("fixture roster must be available");
    const providerByIdentity: Record<string, { binding: string; model: string }> = {
      "model_identity.local": { binding: "qwen35", model: "Qwen3.6-35B-A3B" },
      "model_identity.openrouter": { binding: "openrouter", model: "openrouter/free" },
      "model_identity.glm": { binding: "glm-5.2", model: "glm-5.2" },
      "model_identity.gemini": { binding: "gemini", model: "gemini-2.5-flash" },
    };
    const modelCatalog: ModelCatalogProjection = {
      schema_version: "1",
      kind: "steel_onslaught.model_catalog_projection",
      catalog_id: "catalog.configured_models",
      catalog_sha256: "c".repeat(64),
      options: initial.player_roster.options.map((option) => {
        if (option.kind === "human") return option;
        const provider = providerByIdentity[option.model_identity_id];
        if (provider === undefined) throw new Error("fixture identity missing provider binding");
        return {
          ...option,
          provider_binding_id: provider.binding,
          provider_model: provider.model,
        };
      }),
      default_option_ids: ["player_option.glm_model", "player_option.openrouter_model"],
      mirror_match_mode: false,
    };

    render(
      <MatchSetup
        bootstrap={{ ...initial, model_catalog: modelCatalog }}
        capability={{ requestStart: vi.fn() }}
      />,
    );

    expect((screen.getByLabelText("red pilot") as HTMLSelectElement).value).toBe(
      "player_option.glm_model",
    );
    expect((screen.getByLabelText("blue pilot") as HTMLSelectElement).value).toBe(
      "player_option.openrouter_model",
    );
    expect(screen.getByLabelText("red pilot")).toHaveTextContent("glm-5.2/glm-5.2");
    expect(screen.getByLabelText("blue pilot")).toHaveTextContent("openrouter/openrouter/free");
  });

  it("uses explicit seat defaults instead of option names or ordering", () => {
    const initial = bootstrap();
    if (initial.player_roster === null) throw new Error("fixture roster must be available");
    const configuredRoster = {
      ...initial.player_roster,
      seats: initial.player_roster.seats.map((seat) => ({
        ...seat,
        default_option_id:
          seat.side === "red" ? "player_option.local_model" : "player_option.openrouter_model",
      })),
    };

    render(
      <MatchSetup
        bootstrap={{ ...initial, player_roster: configuredRoster }}
        capability={{ requestStart: vi.fn() }}
      />,
    );

    expect((screen.getByLabelText("red pilot") as HTMLSelectElement).value).toBe(
      "player_option.local_model",
    );
    expect((screen.getByLabelText("blue pilot") as HTMLSelectElement).value).toBe(
      "player_option.openrouter_model",
    );
  });

  it("leaves legacy projections without defaults empty and start-disabled", () => {
    const raw = JSON.parse(readFileSync(BOOTSTRAP_FIXTURE, "utf-8")) as {
      player_roster: { seats: Array<Record<string, unknown>> };
    };
    for (const seat of raw.player_roster.seats) delete seat["default_option_id"];
    const legacy = parseFrontendBootstrap(raw);

    render(<MatchSetup bootstrap={legacy} capability={{ requestStart: vi.fn() }} />);

    expect((screen.getByLabelText("red pilot") as HTMLSelectElement).value).toBe("");
    expect((screen.getByLabelText("blue pilot") as HTMLSelectElement).value).toBe("");
    expect(screen.getByRole("button", { name: "START MATCH" })).toBeDisabled();
  });

  it("emits only typed non-authoritative intent when an explicit capability exists", () => {
    const requestStart = vi.fn();
    render(<MatchSetup bootstrap={bootstrap()} capability={{ requestStart }} />);
    fireEvent.change(screen.getByLabelText("red pilot"), {
      target: { value: "player_option.browser_human" },
    });
    fireEvent.change(screen.getByLabelText("blue pilot"), {
      target: { value: "player_option.gemini_model" },
    });
    const start = screen.getByRole("button", { name: "START MATCH" });
    expect(start).toBeEnabled();

    fireEvent.click(start);

    expect(requestStart).toHaveBeenCalledTimes(1);
    expect(requestStart).toHaveBeenCalledWith({
      expected_overlay_sha256: "a".repeat(64),
      roster_id: "roster.player_selector",
      expected_roster_sha256: "574d46f93bedc390b4b071a98168e6b06d993064c3199d55e8f4de2169cbb8cf",
      selections: [
        { side: "red", option_id: "player_option.browser_human" },
        { side: "blue", option_id: "player_option.gemini_model" },
      ],
    });
  });

  it("keeps launch disabled after receipt acceptance and hides it on MATCH_STARTED", () => {
    const requestStart = vi.fn();
    const { rerender } = render(
      <MatchSetup
        bootstrap={bootstrap()}
        capability={{ requestStart, status: "accepted" }}
        gatewayStatus="accepted"
      />,
    );

    expect(screen.getByRole("form", { name: "Match setup" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "START ACCEPTED" })).toBeDisabled();

    rerender(
      <MatchSetup
        bootstrap={bootstrap()}
        capability={{ requestStart, status: "accepted" }}
        gatewayStatus="accepted"
        matchStarted
      />,
    );
    expect(screen.queryByRole("form", { name: "Match setup" })).not.toBeInTheDocument();
  });

  it("fail-closes a retained selection when replacement authority disallows it", () => {
    const requestStart = vi.fn();
    const initial = bootstrap();
    if (initial.player_roster === null) throw new Error("fixture roster must be available");
    const replacementRoster = {
      ...initial.player_roster,
      roster_id: "roster.replacement",
      roster_sha256: "c".repeat(64),
      options: initial.player_roster.options.filter(
        (option) => option.option_id !== "player_option.browser_human",
      ),
      seats: initial.player_roster.seats.map((seat) => ({
        ...seat,
        allowed_option_ids: seat.allowed_option_ids.filter(
          (optionId) => optionId !== "player_option.browser_human",
        ),
      })),
    };
    const { rerender } = render(<MatchSetup bootstrap={initial} capability={{ requestStart }} />);
    fireEvent.change(screen.getByLabelText("red pilot"), {
      target: { value: "player_option.browser_human" },
    });
    fireEvent.change(screen.getByLabelText("blue pilot"), {
      target: { value: "player_option.local_model" },
    });
    expect(screen.getByRole("button", { name: "START MATCH" })).toBeEnabled();

    rerender(
      <MatchSetup
        bootstrap={{
          ...initial,
          overlay_sha256: "d".repeat(64),
          player_roster: replacementRoster,
        }}
        capability={{ requestStart }}
      />,
    );

    expect(screen.getByRole("button", { name: "START MATCH" })).toBeDisabled();
    fireEvent.submit(screen.getByRole("form", { name: "Match setup" }));
    expect(requestStart).not.toHaveBeenCalled();
  });

  it("renders explicit roster unavailability without selectors or fallback", () => {
    render(<MatchSetup bootstrap={{ ...bootstrap(), player_roster: null }} />);

    expect(screen.getByTestId("roster-unavailable")).toHaveTextContent("SERVER ROSTER UNAVAILABLE");
    expect(screen.queryByLabelText("red pilot")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "START DISABLED" })).toBeDisabled();
  });
});
