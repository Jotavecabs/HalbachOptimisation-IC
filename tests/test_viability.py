"""Testes da análise de viabilidade."""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

import numpy as np
import pytest

from halbach_ic.config import ConfigError, load_config
from halbach_ic.domain import make_grid
from halbach_ic.field_model import DipoleBackend
from halbach_ic.geometry import DesignSpace, MagnetArray, symmetric_slots
from halbach_ic.objective import build_field_table, field_unit_vector, homogeneity_ppm
from halbach_ic.viability.params import MM, ArrayParams, fixed_from_scenario
from halbach_ic.viability.simulate import octant_surface_points, simulate_group
from halbach_ic.viability.sweeps import (
    Criteria,
    GeneralSettings,
    LineSweep,
    MapSweep,
    ViabilityPlan,
    load_plan,
    run_analysis,
    viability_code,
)


@pytest.fixture(scope="module")
def base() -> ArrayParams:
    fixed = fixed_from_scenario(load_config("limb"))
    return ArrayParams(n_rings=9, ring_spacing_mm=22.0, bore_radius_mm=80.0, n_bands=1, magnet_size_mm=12.0,
                       remanence_T=1.3, dsv_diameter_mm=110.0, fixed=fixed)


def test_surface_method_matches_full_grid(base) -> None:
    """Princípio do máximo e propriedade da média: superfície + centro = grade 3D inteira."""
    result = simulate_group([base], DipoleBackend(), n_surface=600)[0]
    ring = base.ring()
    space = DesignSpace(slots=symmetric_slots(base.n_rings, base.ring_spacing_mm * MM), options=(ring,))
    grid = make_grid(base.dsv_diameter_mm * MM, 2.5 * MM)
    table = build_field_table(space, grid.points("full"), DipoleBackend(), -math.pi / 2)
    field = table.total_field([0] * space.n_slots)
    assert result.metrics["b0_mT"] == pytest.approx(field.mean() * 1e3, rel=1e-4)
    # a grade nunca vê mais variação que a superfície (os extremos estão nela)
    assert homogeneity_ppm(field) <= result.metrics["ppm"] * (1 + 1e-6)
    assert homogeneity_ppm(field) == pytest.approx(result.metrics["ppm"], rel=0.02)


def test_field_is_mirror_symmetric_on_surface(base) -> None:
    """Justifica amostrar só o oitavo positivo da superfície."""
    ring = base.ring()
    magnets = MagnetArray.concatenate([ring.magnets(z) for z in (-0.044, -0.022, 0.0, 0.022, 0.044)])
    pts = octant_surface_points(0.05, 100)
    unit = field_unit_vector(-math.pi / 2)
    ref = DipoleBackend().field(pts, magnets) @ unit
    for sign in ([-1, 1, 1], [1, -1, 1], [1, 1, -1]):
        mirrored = DipoleBackend().field(pts * sign, magnets) @ unit
        np.testing.assert_allclose(mirrored, ref, rtol=1e-8)


def test_cumulative_rings_match_individual(base) -> None:
    group = [base.with_(n_rings=n) for n in (1, 2, 5, 8, 9)]
    together = simulate_group(group, DipoleBackend(), 200)
    for p, r in zip(group, together):
        alone = simulate_group([p], DipoleBackend(), 200)[0]
        assert r.metrics["b0_mT"] == pytest.approx(alone.metrics["b0_mT"], rel=1e-12)
        assert r.metrics["ppm"] == pytest.approx(alone.metrics["ppm"], rel=1e-9)
        assert r.metrics["mass_kg"] == pytest.approx(p.n_rings * p.ring().mass)


def test_remanence_scales_field_not_homogeneity(base) -> None:
    a = simulate_group([base], DipoleBackend(), 200)[0]
    b = simulate_group([base.with_(remanence_T=1.43)], DipoleBackend(), 200)[0]
    assert b.metrics["b0_mT"] == pytest.approx(a.metrics["b0_mT"] * 1.1, rel=1e-12)
    assert b.metrics["ppm"] == pytest.approx(a.metrics["ppm"], rel=1e-9)


def test_impossible_arrangements_are_flagged(base) -> None:
    too_close = simulate_group([base.with_(ring_spacing_mm=10.0)], DipoleBackend(), 50)[0]
    assert too_close.status != "ok" and math.isnan(too_close.metrics["b0_mT"])
    dsv_too_big = simulate_group([base.with_(dsv_diameter_mm=170.0)], DipoleBackend(), 50)[0]
    assert "não cabe" in dsv_too_big.status


def test_viability_code(base) -> None:
    crit = Criteria(target_mT=50, tolerance_mT=1, min_bore_diameter_mm=150, max_mass_kg=20, max_ppm=None)
    r = simulate_group([base], DipoleBackend(), 50)[0]
    code = viability_code(r, crit)
    b0 = r.metrics["b0_mT"]
    on_target = dataclasses.replace(crit, target_mT=b0)
    assert code == 1 and viability_code(r, on_target) == 0
    assert viability_code(r, dataclasses.replace(on_target, max_mass_kg=1)) == 3
    assert viability_code(r, dataclasses.replace(on_target, min_bore_diameter_mm=500)) == 4
    assert viability_code(r, dataclasses.replace(on_target, max_ppm=1)) == 2


def test_default_plan_loads_both_scenarios() -> None:
    for name in ("head", "limb"):
        plan = load_plan(load_config(name))
        assert plan.lines and plan.maps
        assert plan.criteria.target_mT == pytest.approx(50)


def test_plan_rejects_unknown_parameter(tmp_path: Path) -> None:
    text = Path(__file__).resolve().parents[1].joinpath("viabilidade.toml").read_text()
    path = tmp_path / "v.toml"
    path.write_text(text.replace('x = "n_rings"', 'x = "numero_de_aneis"', 1))
    with pytest.raises(ConfigError, match="numero_de_aneis"):
        load_plan(load_config("head"), path)


def test_small_analysis_and_report(base, tmp_path: Path) -> None:
    from halbach_ic.viability.report import write_report

    plan = ViabilityPlan(
        scenario="teste",
        general=GeneralSettings(backend="dipole", n_surface=50, n_workers=1),
        base=base,
        criteria=Criteria(target_mT=50, tolerance_mT=1, min_bore_diameter_mm=150, max_mass_kg=20, max_ppm=None),
        lines=(LineSweep("n_rings", (3, 5, 7, 9), "n_bands", (1, 2)),),
        maps=(MapSweep("n_rings", (5, 7, 9), "bore_radius_mm", (70.0, 80.0, 90.0)),),
    )
    data = run_analysis(plan, log=lambda *_: None)
    report = write_report(data, tmp_path, log=lambda *_: None)
    text = report.read_text()
    assert "![linha_n_rings_por_n_bands](figuras/linha_n_rings_por_n_bands.png)" in text
    for name in ("linha_n_rings_por_n_bands.png", "mapa_n_rings_x_bore_radius_mm.png",
                 "compromisso_massa_homogeneidade.png", "referencia_cortes.png"):
        assert (tmp_path / "figuras" / name).exists()
    assert (tmp_path / "dados" / "todos_os_arranjos.csv").read_text().count("\n") > 10
