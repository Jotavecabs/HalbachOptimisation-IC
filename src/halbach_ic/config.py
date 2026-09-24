"""Leitura do arquivo de configuração (``config.toml``).

O arquivo usa unidades práticas (mm, mT, graus) indicadas no nome de cada
chave. Aqui tudo é convertido para SI (m, T, rad, kg) e guardado em
dataclasses imutáveis. Nenhum outro módulo lê o TOML diretamente.
"""

from __future__ import annotations

import copy
import math
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

MM = 1e-3
MT = 1e-3

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.toml"

Symmetry = Literal["octant", "full"]


class ConfigError(ValueError):
    """Erro de conteúdo no arquivo de configuração."""


@dataclass(frozen=True)
class FieldConfig:
    """Requisitos do campo B0 (SI)."""

    target: float
    """Campo médio alvo no DSV [T]."""
    tolerance: float
    """Meia largura da faixa aceita em torno do alvo [T]."""
    direction: float
    """Direção de B0 no plano xy, medida a partir de +x [rad]."""


@dataclass(frozen=True)
class MagnetConfig:
    """Ímã cúbico (SI)."""

    size: float
    """Aresta do cubo [m]."""
    remanence: float
    """Remanência Br [T]."""
    density: float
    """Densidade [kg/m³]."""


@dataclass(frozen=True)
class RingConfig:
    """Parâmetros construtivos dos anéis e candidatos de raio (SI)."""

    n_bands: int
    band_gap: float
    magnet_gap: float
    angle_offset: float
    bore_radius_candidates: tuple[float, ...]
    """Raios livres internos que o otimizador pode escolher [m]."""


@dataclass(frozen=True)
class StackConfig:
    """Disposição dos anéis ao longo de z (SI)."""

    n_rings: int
    ring_spacing: float
    axial_gap: float


@dataclass(frozen=True)
class DomainConfig:
    """Região de avaliação do campo (SI)."""

    dsv_diameter: float
    grid_spacing: float
    symmetry: Symmetry


@dataclass(frozen=True)
class ConstraintsConfig:
    """Restrições construtivas (SI)."""

    min_bore_diameter: float
    max_magnet_mass: float


@dataclass(frozen=True)
class GAConfig:
    """Parâmetros do algoritmo genético."""

    population: int
    generations: int
    crossover_prob: float
    mutation_prob: float
    gene_mutation_prob: float
    tournament_size: int
    seed: int | None
    """``None`` = semente aleatória."""


@dataclass(frozen=True)
class ScenarioConfig:
    """Configuração completa de um cenário (cabeça, membros, ...)."""

    name: str
    field: FieldConfig
    magnet: MagnetConfig
    ring: RingConfig
    stack: StackConfig
    domain: DomainConfig
    constraints: ConstraintsConfig
    ga: GAConfig


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Combina dois dicionários aninhados; ``override`` tem prioridade."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class _Section:
    """Lê as chaves de uma seção e acusa chaves faltantes ou desconhecidas."""

    def __init__(self, name: str, data: dict[str, Any]) -> None:
        self.name = name
        self.data = data
        self.used: set[str] = set()

    def get(self, key: str) -> Any:
        if key not in self.data:
            raise ConfigError(f"[{self.name}] falta a chave '{key}'")
        self.used.add(key)
        return self.data[key]

    def number(self, key: str, *, positive: bool = False, nonnegative: bool = False) -> float:
        value = self.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"[{self.name}] '{key}' deve ser numérico, recebido {value!r}")
        value = float(value)
        if not math.isfinite(value):
            raise ConfigError(f"[{self.name}] '{key}' deve ser finito")
        if positive and value <= 0:
            raise ConfigError(f"[{self.name}] '{key}' deve ser > 0, recebido {value}")
        if nonnegative and value < 0:
            raise ConfigError(f"[{self.name}] '{key}' deve ser >= 0, recebido {value}")
        return value

    def integer(self, key: str, *, minimum: int | None = None) -> int:
        value = self.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"[{self.name}] '{key}' deve ser inteiro, recebido {value!r}")
        if minimum is not None and value < minimum:
            raise ConfigError(f"[{self.name}] '{key}' deve ser >= {minimum}, recebido {value}")
        return value

    def probability(self, key: str) -> float:
        value = self.number(key)
        if not 0.0 <= value <= 1.0:
            raise ConfigError(f"[{self.name}] '{key}' deve estar entre 0 e 1, recebido {value}")
        return value

    def finish(self) -> None:
        unknown = set(self.data) - self.used
        if unknown:
            raise ConfigError(f"[{self.name}] chave(s) desconhecida(s): {sorted(unknown)}")


def _candidate_radii(minimum: float, maximum: float, step: float) -> tuple[float, ...]:
    """Lista inclusiva ``minimum, minimum+step, ..., <= maximum`` [m]."""
    if maximum < minimum:
        raise ConfigError("[ring] bore_radius_max_mm deve ser >= bore_radius_min_mm")
    count = int(math.floor((maximum - minimum) / step + 1e-9)) + 1
    return tuple(float(v) for v in minimum + step * np.arange(count))


def _parse_scenario(name: str, raw: dict[str, Any]) -> ScenarioConfig:
    expected = {"field", "magnet", "ring", "stack", "domain", "constraints", "ga"}
    missing = expected - set(raw)
    unknown = set(raw) - expected
    if missing:
        raise ConfigError(f"cenário '{name}': seções faltando {sorted(missing)}")
    if unknown:
        raise ConfigError(f"cenário '{name}': seções desconhecidas {sorted(unknown)}")

    s = _Section(f"{name}.field", raw["field"])
    field = FieldConfig(
        target=s.number("target_mT", positive=True) * MT,
        tolerance=s.number("tolerance_mT", positive=True) * MT,
        direction=math.radians(s.number("direction_deg")),
    )
    s.finish()

    s = _Section(f"{name}.magnet", raw["magnet"])
    magnet = MagnetConfig(
        size=s.number("size_mm", positive=True) * MM,
        remanence=s.number("remanence_T", positive=True),
        density=s.number("density_kg_m3", positive=True),
    )
    s.finish()

    s = _Section(f"{name}.ring", raw["ring"])
    ring = RingConfig(
        n_bands=s.integer("n_bands", minimum=1),
        band_gap=s.number("band_gap_mm", nonnegative=True) * MM,
        magnet_gap=s.number("magnet_gap_mm", nonnegative=True) * MM,
        angle_offset=math.radians(s.number("angle_offset_deg")),
        bore_radius_candidates=_candidate_radii(
            s.number("bore_radius_min_mm", positive=True) * MM,
            s.number("bore_radius_max_mm", positive=True) * MM,
            s.number("bore_radius_step_mm", positive=True) * MM,
        ),
    )
    s.finish()

    s = _Section(f"{name}.stack", raw["stack"])
    stack = StackConfig(
        n_rings=s.integer("n_rings", minimum=1),
        ring_spacing=s.number("ring_spacing_mm", positive=True) * MM,
        axial_gap=s.number("axial_gap_mm", nonnegative=True) * MM,
    )
    s.finish()

    s = _Section(f"{name}.domain", raw["domain"])
    symmetry = s.get("symmetry")
    if symmetry not in ("octant", "full"):
        raise ConfigError(f"[{name}.domain] symmetry deve ser 'octant' ou 'full', recebido {symmetry!r}")
    domain = DomainConfig(
        dsv_diameter=s.number("dsv_diameter_mm", positive=True) * MM,
        grid_spacing=s.number("grid_spacing_mm", positive=True) * MM,
        symmetry=symmetry,
    )
    s.finish()

    s = _Section(f"{name}.constraints", raw["constraints"])
    constraints = ConstraintsConfig(
        min_bore_diameter=s.number("min_bore_diameter_mm", nonnegative=True) * MM,
        max_magnet_mass=s.number("max_magnet_mass_kg", positive=True),
    )
    s.finish()

    s = _Section(f"{name}.ga", raw["ga"])
    seed = s.integer("seed")
    ga = GAConfig(
        population=s.integer("population", minimum=2),
        generations=s.integer("generations", minimum=1),
        crossover_prob=s.probability("crossover_prob"),
        mutation_prob=s.probability("mutation_prob"),
        gene_mutation_prob=s.probability("gene_mutation_prob"),
        tournament_size=s.integer("tournament_size", minimum=1),
        seed=None if seed < 0 else seed,
    )
    s.finish()

    return ScenarioConfig(
        name=name,
        field=field,
        magnet=magnet,
        ring=ring,
        stack=stack,
        domain=domain,
        constraints=constraints,
        ga=ga,
    )


def available_scenarios(path: Path | str = DEFAULT_CONFIG_PATH) -> list[str]:
    """Nomes dos cenários definidos no arquivo."""
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    return sorted(raw.get("scenarios", {}))


def load_config(scenario: str, path: Path | str = DEFAULT_CONFIG_PATH) -> ScenarioConfig:
    """Lê ``path`` e devolve a configuração do cenário pedido, em SI.

    Args:
        scenario: nome do cenário (``head``, ``limb``, ...).
        path: caminho do arquivo TOML.

    Raises:
        ConfigError: cenário inexistente, chave faltando/desconhecida ou valor inválido.
    """
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    unknown_top = set(raw) - {"defaults", "scenarios"}
    if unknown_top:
        raise ConfigError(f"seções de topo desconhecidas: {sorted(unknown_top)}")
    scenarios = raw.get("scenarios", {})
    if scenario not in scenarios:
        raise ConfigError(f"cenário '{scenario}' não existe; disponíveis: {sorted(scenarios)}")
    merged = _deep_merge(raw.get("defaults", {}), scenarios[scenario])
    return _parse_scenario(scenario, merged)
