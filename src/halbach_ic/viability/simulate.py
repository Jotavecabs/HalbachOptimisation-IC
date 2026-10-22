"""Cálculo das métricas de um arranjo uniforme.

Duas propriedades das funções harmônicas tornam o cálculo barato e exato.
Dentro do DSV não há ímãs, então cada componente de B satisfaz ∇²B = 0:

* **princípio do máximo:** o maior e o menor valor de B dentro da esfera ficam
  na superfície. A inomogeneidade pico a pico no volume é medida só na
  superfície do DSV;
* **propriedade da média:** a média de B no volume da esfera é igual ao valor
  no centro. O campo "médio" do DSV é B0 no centro.

Pela simetria do arranjo (espelho em x, y e z, ver DOCS/correcoes.md item 6),
basta amostrar o oitavo da superfície com x, y, z >= 0.

Arranjos que diferem só no número de anéis são calculados juntos: o campo
é a soma das contribuições de cada par de anéis (±z), então os totais para
todos os números de anéis saem de somas acumuladas.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from halbach_ic.field_model import FieldBackend, get_backend
from halbach_ic.geometry import InfeasibleGeometryError, MagnetArray
from halbach_ic.objective import field_unit_vector
from halbach_ic.parallel import resolve_workers, spawn_context
from halbach_ic.viability.params import MM, ArrayParams

LARMOR_MHZ_PER_T = 42.577
"""Razão giromagnética do hidrogênio, γ/2π [MHz/T]."""


@dataclass(frozen=True)
class MetricInfo:
    """Como uma métrica aparece nos gráficos e no relatório."""

    label: str
    unit: str
    log: bool
    """Usar escala logarítmica."""
    explanation: str

    def axis_label(self) -> str:
        return f"{self.label} ({self.unit})" if self.unit else self.label


METRICS: dict[str, MetricInfo] = {
    "b0_mT": MetricInfo(
        "Campo B0 no centro", "mT", False,
        "Componente do campo na direção de B0 no centro do ímã. Pela propriedade da média das funções "
        "harmônicas, é também o campo médio de todo o DSV. O alvo do projeto é 50 mT.",
    ),
    "ppm": MetricInfo(
        "Inomogeneidade no DSV", "ppm", True,
        "(B_máx − B_mín) / B0 × 10⁶ dentro da esfera do DSV. Quanto MENOR, melhor. 1000 ppm = 0,1 %: a "
        "50 mT isso corresponde a 50 µT de variação, ou 2,1 kHz de largura de linha na frequência de Larmor.",
    ),
    "mass_kg": MetricInfo(
        "Massa dos ímãs", "kg", False,
        "Massa total de NdFeB (densidade × volume × número de ímãs). Não inclui a estrutura de suporte.",
    ),
    "n_magnets": MetricInfo("Número de ímãs", "", False, "Total de cubos do arranjo (afeta custo e montagem)."),
    "length_mm": MetricInfo("Comprimento", "mm", False, "Do primeiro ao último cubo, ao longo do eixo z."),
    "outer_diameter_mm": MetricInfo("Diâmetro externo", "mm", False, "Diâmetro ocupado pelos ímãs da camada externa."),
    "efficiency_mT_per_kg": MetricInfo(
        "Campo por massa", "mT/kg", False,
        "B0 dividido pela massa: quanto campo cada quilo de ímã produz. Ajuda a comparar arranjos para um "
        "aparelho portátil.",
    ),
    "larmor_MHz": MetricInfo(
        "Frequência de Larmor (¹H)", "MHz", False,
        "f = γ·B0, com γ/2π = 42,577 MHz/T. É a frequência em que a bobina de RF precisa trabalhar.",
    ),
}
"""Métricas calculadas para cada arranjo."""


def octant_surface_points(radius: float, n_octant: int) -> NDArray[np.float64]:
    """Pontos quase uniformes no oitavo da esfera com x, y, z >= 0, mais os três polos.

    Usa a espiral de Fibonacci na esfera inteira (8·n_octant pontos) e guarda
    só o oitavo positivo. Os polos (onde costumam ficar os extremos) entram
    sempre.
    """
    n_total = 8 * n_octant
    i = np.arange(n_total) + 0.5
    phi = np.arccos(1 - 2 * i / n_total)
    theta = np.pi * (1 + 5**0.5) * i
    pts = np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1)
    pts = pts[np.all(pts >= 0, axis=1)]
    return radius * np.vstack([pts, np.eye(3)])


def nan_metrics() -> dict[str, float]:
    """Métricas de um arranjo inviável."""
    return {name: math.nan for name in METRICS}


@dataclass(frozen=True)
class SimResult:
    """Resultado de um arranjo."""

    params: ArrayParams
    metrics: dict[str, float]
    status: str
    """``"ok"`` ou o motivo de o arranjo ser inviável."""


def _field_component(backend: FieldBackend, points: NDArray[np.float64], magnets: MagnetArray,
                     unit: NDArray[np.float64]) -> NDArray[np.float64]:
    return backend.field(points, magnets) @ unit


def simulate_group(params: Sequence[ArrayParams], backend: FieldBackend, n_surface: int) -> list[SimResult]:
    """Calcula arranjos que só diferem em ``n_rings`` e ``dsv_diameter_mm``.

    Args:
        params: arranjos com a mesma :meth:`ArrayParams.group_key`.
        backend: modelo de campo.
        n_surface: pontos no oitavo da superfície de cada DSV.
    """
    base = params[0]
    if any(p.group_key() != base.group_key() for p in params):
        raise ValueError("todos os arranjos de um grupo devem ter a mesma group_key")
    try:
        for p in params:
            p.check_axial()
        ring = base.ring()
    except InfeasibleGeometryError as exc:
        return [SimResult(p, nan_metrics(), str(exc)) for p in params]

    # pontos: centro + superfície de cada DSV pedido que caiba no bore
    dsvs = sorted({p.dsv_diameter_mm for p in params if p.dsv_diameter_mm / 2 < p.bore_radius_mm})
    blocks = [np.zeros((1, 3))] + [octant_surface_points(d * MM / 2, n_surface) for d in dsvs]
    offsets = np.cumsum([0] + [b.shape[0] for b in blocks])
    surface_slice = {d: slice(offsets[k + 1], offsets[k + 2]) for k, d in enumerate(dsvs)}
    points = np.vstack(blocks)
    unit = field_unit_vector(math.radians(base.fixed.field_direction_deg))
    spacing = base.ring_spacing_mm * MM

    # contribuições acumuladas: n ímpar = anel central + pares em ±j·s; n par = pares em ±(j−½)·s
    max_pairs_odd = max([(p.n_rings - 1) // 2 for p in params if p.n_rings % 2 == 1], default=-1)
    max_pairs_even = max([p.n_rings // 2 for p in params if p.n_rings % 2 == 0], default=0)
    odd = np.zeros((max(max_pairs_odd, 0) + 1, points.shape[0]))
    even = np.zeros((max_pairs_even + 1, points.shape[0]))
    try:
        if max_pairs_odd >= 0:
            odd[0] = _field_component(backend, points, ring.magnets(0.0), unit)
            for j in range(1, max_pairs_odd + 1):
                pair = MagnetArray.concatenate([ring.magnets(-j * spacing), ring.magnets(j * spacing)])
                odd[j] = odd[j - 1] + _field_component(backend, points, pair, unit)
        for j in range(1, max_pairs_even + 1):
            z = (j - 0.5) * spacing
            pair = MagnetArray.concatenate([ring.magnets(-z), ring.magnets(z)])
            even[j] = even[j - 1] + _field_component(backend, points, pair, unit)
    except ValueError as exc:  # ex.: o dipolo recusa pontos colados nos ímãs
        return [SimResult(p, nan_metrics(), f"modelo de campo recusou: {exc}") for p in params]

    results = []
    for p in params:
        if p.dsv_diameter_mm / 2 >= p.bore_radius_mm:
            results.append(SimResult(p, nan_metrics(),
                                     f"DSV (Ø{p.dsv_diameter_mm:g} mm) não cabe no bore (Ø{2 * p.bore_radius_mm:g} mm)"))
            continue
        total = odd[(p.n_rings - 1) // 2] if p.n_rings % 2 == 1 else even[p.n_rings // 2]
        b0 = float(total[0])
        inside = np.concatenate([total[:1], total[surface_slice[p.dsv_diameter_mm]]])
        ppm = float((inside.max() - inside.min()) / b0 * 1e6) if b0 > 0 else math.inf
        mass = p.n_rings * ring.mass
        results.append(SimResult(p, {
            "b0_mT": b0 * 1e3,
            "ppm": ppm,
            "mass_kg": mass,
            "n_magnets": float(p.n_rings * ring.total_magnets),
            "length_mm": (p.n_rings - 1) * p.ring_spacing_mm + p.magnet_size_mm,
            "outer_diameter_mm": 2 * ring.outer_radius / MM,
            "efficiency_mT_per_kg": b0 * 1e3 / mass,
            "larmor_MHz": b0 * LARMOR_MHZ_PER_T,
        }, "ok"))
    return results


def _group(params: Sequence[ArrayParams]) -> list[list[ArrayParams]]:
    groups: dict[tuple, list[ArrayParams]] = {}
    for p in params:
        groups.setdefault(p.group_key(), []).append(p)
    return list(groups.values())


_worker_state: dict[str, object] = {}


def _init_worker(backend_name: str, n_surface: int) -> None:
    _worker_state.update(backend=get_backend(backend_name), n_surface=n_surface)


def _simulate_in_worker(group: list[ArrayParams]) -> list[SimResult]:
    return simulate_group(group, _worker_state["backend"], _worker_state["n_surface"])  # type: ignore[arg-type]


def simulate_many(params: Sequence[ArrayParams], backend_name: str, n_surface: int,
                  n_workers: int = 0) -> list[SimResult]:
    """Simula vários arranjos (em paralelo) e devolve os resultados na mesma ordem.

    Args:
        params: arranjos.
        backend_name: ``"dipole"`` ou ``"cuboid"``.
        n_surface: pontos no oitavo da superfície do DSV.
        n_workers: processos (0 = todos os núcleos).
    """
    groups = _group(params)
    workers = min(resolve_workers(n_workers), len(groups))
    if workers <= 1:
        backend = get_backend(backend_name)
        outputs = [simulate_group(g, backend, n_surface) for g in groups]
    else:
        # grupos maiores primeiro, para equilibrar a carga entre processos
        order = sorted(range(len(groups)), key=lambda i: -max(p.n_rings for p in groups[i]))
        with spawn_context().Pool(workers, initializer=_init_worker, initargs=(backend_name, n_surface)) as pool:
            computed = pool.map(_simulate_in_worker, [groups[i] for i in order], chunksize=1)
        outputs = [None] * len(groups)
        for i, out in zip(order, computed):
            outputs[i] = out
    by_params = {r.params: r for out in outputs for r in out}  # type: ignore[union-attr]
    return [by_params[p] for p in params]
