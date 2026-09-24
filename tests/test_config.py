"""Testes da leitura de configuração."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from halbach_ic.config import ConfigError, available_scenarios, load_config


def test_scenarios_head_and_limb_exist() -> None:
    assert {"head", "limb"} <= set(available_scenarios())


def test_values_are_converted_to_si() -> None:
    cfg = load_config("head")
    assert cfg.field.target == pytest.approx(0.05)
    assert cfg.field.direction == pytest.approx(-math.pi / 2)
    assert cfg.magnet.size == pytest.approx(0.012)
    assert cfg.domain.dsv_diameter == pytest.approx(0.2)
    assert cfg.ring.bore_radius_candidates[0] == pytest.approx(0.140)
    assert cfg.ring.bore_radius_candidates[-1] == pytest.approx(0.194)


def test_scenario_overrides_only_what_it_declares() -> None:
    head, limb = load_config("head"), load_config("limb")
    assert limb.domain.dsv_diameter == pytest.approx(0.11)
    assert limb.stack.n_rings == 15
    assert limb.magnet == head.magnet
    assert limb.ga == head.ga


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cfg.toml"
    path.write_text(text)
    return path


def _base_config() -> str:
    return Path(__file__).resolve().parents[1].joinpath("config.toml").read_text()


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    text = _base_config().replace("n_bands = 2", "n_bands = 2\nn_bandz = 3", 1)
    with pytest.raises(ConfigError, match="n_bandz"):
        load_config("head", _write(tmp_path, text))


def test_invalid_value_is_rejected(tmp_path: Path) -> None:
    text = _base_config().replace("crossover_prob = 0.55", "crossover_prob = 1.5", 1)
    with pytest.raises(ConfigError, match="crossover_prob"):
        load_config("head", _write(tmp_path, text))


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ConfigError, match="não existe"):
        load_config("joelho")
