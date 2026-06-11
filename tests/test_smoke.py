import importlib

import pytest


@pytest.mark.unit
def test_package_importable() -> None:
    mod = importlib.import_module("steel_onslaught")
    assert mod.__name__ == "steel_onslaught"
