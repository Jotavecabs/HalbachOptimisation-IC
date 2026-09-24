"""Configuração comum dos testes."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

os.environ.setdefault("MPLBACKEND", "Agg")

LEGACY_DIR = Path(__file__).resolve().parents[1] / "legacy"


@pytest.fixture(scope="session")
def legacy() -> tuple[ModuleType, ModuleType]:
    """Importa os módulos originais (``halbachFields``, ``homogeneityOptimisation``) sem alterá-los."""
    sys.path.insert(0, str(LEGACY_DIR))
    try:
        fields = importlib.import_module("halbachFields")
        optimisation = importlib.import_module("homogeneityOptimisation")
    finally:
        sys.path.remove(str(LEGACY_DIR))
    return fields, optimisation
