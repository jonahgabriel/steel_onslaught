from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend/src"


def _source(relative: str) -> str:
    return (_FRONTEND / relative).read_text(encoding="utf-8")


@pytest.mark.unit
def test_main_is_the_only_browser_transport_composition_root() -> None:
    main = _source("main.tsx")
    assert main.count("new WebSocket(") == 1
    assert "createFrontendApplication" in main
    assert "loadFrontendBootstrap" in main

    for relative in (
        "App.tsx",
        "lib/event_stream.ts",
        "lib/transport.ts",
        "lib/useTransport.ts",
        "views/PressureDeck.tsx",
    ):
        source = _source(relative)
        assert "new WebSocket(" not in source
        assert "window.location" not in source
        assert "URLSearchParams" not in source
        assert "localStorage" not in source
        assert "sessionStorage" not in source
        assert "import.meta.env" not in source


@pytest.mark.unit
def test_inner_frontend_layers_have_no_constructor_or_scheduler_fallbacks() -> None:
    stream = _source("lib/event_stream.ts")
    hook = _source("lib/useTransport.ts")
    deck = _source("views/PressureDeck.tsx")

    assert "DEFAULT_WS_URL" not in stream
    assert "resolveWsUrl" not in stream
    assert ".send(" not in stream
    assert "new EventStream(" not in hook
    assert "new MatchTransport(" not in hook
    assert "requestAnimationFrame" not in hook
    assert "cancelAnimationFrame" not in hook
    assert "requestAnimationFrame" not in deck
    assert "cancelAnimationFrame" not in deck


@pytest.mark.unit
def test_frontend_application_parser_uses_unknown_without_cast_or_any_escape_hatches() -> None:
    application = _source("lib/application.ts")
    assert ": any" not in application
    assert " as " not in application
    assert "@ts-ignore" not in application
    assert "@ts-expect-error" not in application


@pytest.mark.unit
def test_vite_dev_proxy_uses_only_generated_overlay_authority() -> None:
    vite = (_ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    assert "127.0.0.1" not in vite
    assert "8765" not in vite
    assert "GENERATED_FRONTEND_BOOTSTRAP" in vite
    assert "parseFrontendBootstrap" in vite
    assert "frontendBootstrapHttpTarget" in vite
    assert "FRONTEND_EXPECTED_OVERLAY_HEADER" in vite
    assert "import.meta.env" not in vite
    assert "process.env" not in vite
