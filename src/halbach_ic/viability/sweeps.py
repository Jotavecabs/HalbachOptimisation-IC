"""Leitura do ``viabilidade.toml``, execução das varreduras e critérios de viabilidade."""

from __future__ import annotations

import csv
import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from halbach_ic.config import ConfigError, ScenarioConfig
from halbach_ic.viability.params import PARAMS, ArrayParams, fixed_from_scenario
from halbach_ic.viability.simulate import METRICS, SimResult, simulate_many

DEFAULT_VIABILITY_PATH = Path(__file__).resolve().parents[3] / "viabilidade.toml"


@dataclass(frozen=True)
class GeneralSettings:
    """Seção ``[geral]``."""

    backend: str
    n_surface: int
    n_workers: int


@dataclass(frozen=True)
class LineSweep:
    """Gráfico de linha: ``x`` varia, uma curva por valor de ``series``."""

    x: str
    x_values: tuple[float, ...]
    series: str | None
    series_values: tuple[float, ...]

    @property
    def name(self) -> str:
        return f"linha_{self.x}" + (f"_por_{self.series}" if self.series else "")


@dataclass(frozen=True)
class MapSweep:
    """Mapa de calor: ``x`` e ``y`` variam juntos."""

    x: str
    x_values: tuple[float, ...]
    y: str
    y_values: tuple[float, ...]

    @property
    def name(self) -> str:
        return f"mapa_{self.x}_x_{self.y}"


@dataclass(frozen=True)
class Criteria:
    """Requisitos para um arranjo ser considerado viável."""

    target_mT: float
    tolerance_mT: float
    min_bore_diameter_mm: float
    max_mass_kg: float
    max_ppm: float | None
    """``None`` = homogeneidade não entra no critério (é o objetivo: quanto melhor, melhor)."""
    min_length_mm: float | None = None
    max_length_mm: float | None = None
    """Faixa aceita de comprimento do ímã (``None`` = sem limite)."""


@dataclass(frozen=True)
class ViabilityPlan:
    """Tudo o que uma análise precisa."""

    scenario: str
    general: GeneralSettings
    base: ArrayParams
    criteria: Criteria
    lines: tuple[LineSweep, ...]
    maps: tuple[MapSweep, ...]


def _range(name: str, spec: Any, integer: bool) -> tuple[float, ...]:
    if not (isinstance(spec, list) and len(spec) == 3 and all(isinstance(v, (int, float)) for v in spec)):
        raise ConfigError(f"{name} deve ser [início, fim, passo], recebido {spec!r}")
    start, stop, step = (float(v) for v in spec)
    if step <= 0 or stop < start:
        raise ConfigError(f"{name}: precisa de passo > 0 e fim >= início")
    count = int(math.floor((stop - start) / step + 1e-9)) + 1
    values = start + step * np.arange(count)
    return tuple(int(round(v)) if integer else round(float(v), 9) for v in values)


def _param_name(where: str, name: Any) -> str:
    if name not in PARAMS:
        raise ConfigError(f"{where}: parâmetro '{name}' desconhecido; disponíveis: {list(PARAMS)}")
    return name


def _check_keys(where: str, data: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ConfigError(f"{where}: chave(s) desconhecida(s) {sorted(unknown)}")


def load_plan(scenario_cfg: ScenarioConfig, path: Path | str = DEFAULT_VIABILITY_PATH) -> ViabilityPlan:
    """Lê o plano de análise de um cenário.

    Args:
        scenario_cfg: cenário do config.toml (fornece valores fixos e requisitos).
        path: arquivo ``viabilidade.toml``.
    """
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    _check_keys("viabilidade.toml", raw, {"geral", "cenarios"})
    geral = raw.get("geral", {})
    _check_keys("[geral]", geral, {"modelo", "pontos_superficie", "processos"})
    general = GeneralSettings(
        backend=str(geral.get("modelo", "cuboid")),
        n_surface=int(geral.get("pontos_superficie", 400)),
        n_workers=int(geral.get("processos", 0)),
    )
    if general.backend not in ("cuboid", "dipole"):
        raise ConfigError("[geral] modelo deve ser 'cuboid' ou 'dipole'")

    name = scenario_cfg.name
    scenarios = raw.get("cenarios", {})
    if name not in scenarios:
        raise ConfigError(f"viabilidade.toml não tem o cenário '{name}'; disponíveis: {sorted(scenarios)}")
    sc = scenarios[name]
    _check_keys(f"[cenarios.{name}]", sc, {"base", "ppm_maximo", "comprimento_min_mm", "comprimento_max_mm",
                                           "linhas", "mapas"})

    base_raw = sc.get("base", {})
    _check_keys(f"[cenarios.{name}.base]", base_raw, set(PARAMS))
    missing = set(PARAMS) - set(base_raw)
    if missing:
        raise ConfigError(f"[cenarios.{name}.base] faltam {sorted(missing)}")
    base = ArrayParams(fixed=fixed_from_scenario(scenario_cfg), **{
        k: (int(v) if PARAMS[k].integer else float(v)) for k, v in base_raw.items()
    })

    lines = []
    for i, item in enumerate(sc.get("linhas", [])):
        where = f"[[cenarios.{name}.linhas]] nº {i + 1}"
        _check_keys(where, item, {"x", "x_faixa", "serie", "serie_valores"})
        x = _param_name(where, item.get("x"))
        series = item.get("serie")
        if series is not None:
            _param_name(where, series)
        lines.append(LineSweep(
            x=x,
            x_values=_range(f"{where} x_faixa", item.get("x_faixa"), PARAMS[x].integer),
            series=series,
            series_values=tuple(item.get("serie_valores", ())) if series else (),
        ))
    maps = []
    for i, item in enumerate(sc.get("mapas", [])):
        where = f"[[cenarios.{name}.mapas]] nº {i + 1}"
        _check_keys(where, item, {"x", "x_faixa", "y", "y_faixa"})
        x, y = _param_name(where, item.get("x")), _param_name(where, item.get("y"))
        maps.append(MapSweep(
            x=x, x_values=_range(f"{where} x_faixa", item.get("x_faixa"), PARAMS[x].integer),
            y=y, y_values=_range(f"{where} y_faixa", item.get("y_faixa"), PARAMS[y].integer),
        ))

    ppm_max = float(sc.get("ppm_maximo", 0))
    criteria = Criteria(
        target_mT=scenario_cfg.field.target * 1e3,
        tolerance_mT=scenario_cfg.field.tolerance * 1e3,
        min_bore_diameter_mm=scenario_cfg.constraints.min_bore_diameter * 1e3,
        max_mass_kg=scenario_cfg.constraints.max_magnet_mass,
        max_ppm=ppm_max if ppm_max > 0 else None,
        min_length_mm=float(sc["comprimento_min_mm"]) if "comprimento_min_mm" in sc else None,
        max_length_mm=float(sc["comprimento_max_mm"]) if "comprimento_max_mm" in sc else None,
    )
    return ViabilityPlan(scenario=name, general=general, base=base, criteria=criteria,
                         lines=tuple(lines), maps=tuple(maps))


# --------------------------------------------------------------------------
# Viabilidade
# --------------------------------------------------------------------------

STATUS_LABELS: dict[int, str] = {
    0: "viável",
    1: "campo fora do alvo",
    2: "homogeneidade abaixo do mínimo",
    3: "comprimento fora da faixa",
    4: "massa acima do limite",
    5: "bore abaixo do mínimo",
    6: "geometria impossível",
}
"""Código de viabilidade → texto. Quando falham vários critérios, vale o de maior código."""


def viability_code(result: SimResult, criteria: Criteria) -> int:
    """Classifica um arranjo (ver :data:`STATUS_LABELS`)."""
    if result.status != "ok":
        return 6
    p, m = result.params, result.metrics
    if 2 * p.bore_radius_mm < criteria.min_bore_diameter_mm - 1e-9:
        return 5
    if m["mass_kg"] > criteria.max_mass_kg:
        return 4
    length = m["length_mm"]
    if (criteria.min_length_mm is not None and length < criteria.min_length_mm - 1e-9) or \
            (criteria.max_length_mm is not None and length > criteria.max_length_mm + 1e-9):
        return 3
    if criteria.max_ppm is not None and m["ppm"] > criteria.max_ppm:
        return 2
    if abs(m["b0_mT"] - criteria.target_mT) > criteria.tolerance_mT:
        return 1
    return 0


# --------------------------------------------------------------------------
# Execução
# --------------------------------------------------------------------------


@dataclass
class LineData:
    sweep: LineSweep
    results: dict[float | None, list[SimResult]] = field(default_factory=dict)
    """Valor da série (ou None) → resultados ao longo de x."""

    def metric(self, series_value: float | None, name: str) -> NDArray[np.float64]:
        return np.array([r.metrics[name] for r in self.results[series_value]])


@dataclass
class MapData:
    sweep: MapSweep
    results: list[list[SimResult]] = field(default_factory=list)
    """``results[i_y][i_x]``."""

    def metric(self, name: str) -> NDArray[np.float64]:
        return np.array([[r.metrics[name] for r in row] for row in self.results])

    def codes(self, criteria: Criteria) -> NDArray[np.int64]:
        return np.array([[viability_code(r, criteria) for r in row] for row in self.results])


@dataclass
class AnalysisData:
    plan: ViabilityPlan
    base: SimResult
    lines: list[LineData]
    maps: list[MapData]
    elapsed_s: float = 0.0

    def all_results(self) -> list[SimResult]:
        out = [self.base]
        for line in self.lines:
            for values in line.results.values():
                out.extend(values)
        for m in self.maps:
            for row in m.results:
                out.extend(row)
        return out


def run_analysis(plan: ViabilityPlan, log=print) -> AnalysisData:
    """Monta todos os arranjos de todas as varreduras, simula de uma vez e organiza."""
    import time

    t0 = time.perf_counter()
    base = plan.base
    requests: list[ArrayParams] = [base]
    for line in plan.lines:
        for s in (line.series_values or (None,)):
            fixed = base if s is None else base.with_(**{line.series: s})
            requests.extend(fixed.with_(**{line.x: x}) for x in line.x_values)
    for m in plan.maps:
        requests.extend(base.with_(**{m.x: x, m.y: y}) for y in m.y_values for x in m.x_values)
    unique = list(dict.fromkeys(requests))
    log(f"{len(unique)} arranjos distintos ({plan.general.backend}, {plan.general.n_surface} pontos na superfície)")
    results = dict(zip(unique, simulate_many(unique, plan.general.backend, plan.general.n_surface,
                                             plan.general.n_workers)))

    lines = []
    for line in plan.lines:
        data = LineData(line)
        for s in (line.series_values or (None,)):
            fixed = base if s is None else base.with_(**{line.series: s})
            data.results[s] = [results[fixed.with_(**{line.x: x})] for x in line.x_values]
        lines.append(data)
    maps = []
    for m in plan.maps:
        maps.append(MapData(m, [[results[base.with_(**{m.x: x, m.y: y})] for x in m.x_values]
                                for y in m.y_values]))
    return AnalysisData(plan=plan, base=results[base], lines=lines, maps=maps, elapsed_s=time.perf_counter() - t0)


def write_csv(results: list[SimResult], path: Path, criteria: Criteria) -> None:
    """Salva parâmetros, métricas e viabilidade de cada arranjo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([*PARAMS, *METRICS, "viabilidade", "observacao"])
        seen: set[ArrayParams] = set()
        for r in results:
            if r.params in seen:
                continue
            seen.add(r.params)
            code = viability_code(r, criteria)
            writer.writerow([getattr(r.params, p) for p in PARAMS]
                            + [f"{r.metrics[m]:.6g}" for m in METRICS]
                            + [STATUS_LABELS[code], "" if r.status == "ok" else r.status])
