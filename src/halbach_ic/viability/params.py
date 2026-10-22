"""Parâmetros de um arranjo Halbach "uniforme" usado na análise de viabilidade.

Na análise de viabilidade não há otimização: todos os anéis do arranjo são
iguais (mesmo raio, mesmo número de camadas, mesmo ímã), igualmente
espaçados e centrados em z = 0. Variar um parâmetro de cada vez (ou dois, nos
mapas de calor) mostra como o campo, a homogeneidade, a massa etc. respondem.

Os parâmetros ficam nas unidades de entrada (mm, T, mm) para os gráficos e
tabelas; a conversão para SI acontece em :meth:`ArrayParams.ring`.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

from halbach_ic.config import ScenarioConfig
from halbach_ic.geometry import HalbachRing, InfeasibleGeometryError, MagnetSpec

MM = 1e-3


@dataclass(frozen=True)
class ParamInfo:
    """Como um parâmetro aparece nos gráficos e no relatório."""

    label: str
    unit: str
    integer: bool
    explanation: str
    """Explicação física curta de como o parâmetro afeta o ímã."""

    def axis_label(self) -> str:
        return f"{self.label} ({self.unit})" if self.unit else self.label

    @property
    def lower(self) -> str:
        """Rótulo com só a primeira letra minúscula (preserva siglas como DSV e Br)."""
        return self.label[:1].lower() + self.label[1:]


PARAMS: dict[str, ParamInfo] = {
    "n_rings": ParamInfo(
        "Número de anéis", "", True,
        "Mais anéis deixam o cilindro mais comprido. Um cilindro Halbach infinito tem campo perfeitamente "
        "uniforme; as imperfeições vêm principalmente das pontas. Com mais anéis as pontas se afastam do DSV: "
        "o campo no centro cresce até saturar e a homogeneidade melhora, mas a massa cresce linearmente.",
    ),
    "ring_spacing_mm": ParamInfo(
        "Espaçamento entre anéis", "mm", False,
        "Com o número de anéis fixo, espaçar mais deixa o ímã mais comprido (pontas mais longe do DSV) mas "
        "dilui o material: há menos ímãs por metro, então o campo no centro cai. O espaçamento mínimo é a "
        "aresta do cubo mais a folga axial.",
    ),
    "bore_radius_mm": ParamInfo(
        "Raio livre interno (bore)", "mm", False,
        "Um anel maior comporta mais ímãs (N cresce com o raio), mas cada ímã fica mais longe do centro e o "
        "campo de um dipolo cai com 1/r³. O saldo é um campo que cai aproximadamente com 1/r². Em compensação, "
        "o DSV fica relativamente menor dentro do anel, o que favorece a homogeneidade no plano transversal.",
    ),
    "n_bands": ParamInfo(
        "Camadas de ímãs por anel", "", True,
        "Cada camada extra é um anel concêntrico mais externo. O campo cresce (para um cilindro contínuo, "
        "B = Br·ln(r_ext/r_int)), mas com ganho decrescente: a camada de fora está mais longe e pesa mais.",
    ),
    "magnet_size_mm": ParamInfo(
        "Aresta do cubo", "mm", False,
        "Cubos maiores têm momento magnético proporcional a a³, mas cabem menos por anel (N ∝ 1/a). O campo "
        "cresce com o tamanho do ímã e a massa também. Cubos grandes também aumentam o erro do modelo de dipolo "
        "(ver DOCS/fase2_modelo_de_campo.md); aqui é usado o modelo configurado em viabilidade.toml.",
    ),
    "remanence_T": ParamInfo(
        "Remanência Br", "T", False,
        "Br é a 'força' do material (N35 ≈ 1,18 T, N42 ≈ 1,30 T, N52 ≈ 1,44 T). O campo é diretamente "
        "proporcional a Br e a homogeneidade em ppm NÃO muda, porque ela depende só da geometria. Serve também "
        "como verificação do modelo.",
    ),
    "dsv_diameter_mm": ParamInfo(
        "Diâmetro do DSV", "mm", False,
        "O DSV é a região onde a imagem é feita. O ímã não muda; muda o tamanho da esfera onde a homogeneidade "
        "é medida. A inomogeneidade cresce rápido com o diâmetro (os termos de ordem n crescem com rⁿ), então "
        "este gráfico mostra até que tamanho de objeto o ímã é útil.",
    ),
}
"""Parâmetros que podem ser varridos, na ordem em que aparecem no relatório."""


@dataclass(frozen=True)
class FixedParams:
    """Valores que não são varridos (vêm do config.toml)."""

    band_gap_mm: float
    magnet_gap_mm: float
    axial_gap_mm: float
    density_kg_m3: float
    field_direction_deg: float


@dataclass(frozen=True)
class ArrayParams:
    """Um arranjo uniforme: todos os anéis iguais."""

    n_rings: int
    ring_spacing_mm: float
    bore_radius_mm: float
    n_bands: int
    magnet_size_mm: float
    remanence_T: float
    dsv_diameter_mm: float
    fixed: FixedParams

    def with_(self, **changes: float) -> ArrayParams:
        """Cópia com alguns parâmetros trocados (inteiros são arredondados)."""
        clean = {}
        for name, value in changes.items():
            if name not in PARAMS:
                raise KeyError(f"parâmetro desconhecido: {name}; disponíveis: {list(PARAMS)}")
            clean[name] = int(round(value)) if PARAMS[name].integer else float(value)
        return dataclasses.replace(self, **clean)

    def magnet(self) -> MagnetSpec:
        """Ímã em SI."""
        return MagnetSpec(size=self.magnet_size_mm * MM, remanence=self.remanence_T,
                          density=self.fixed.density_kg_m3)

    def ring(self) -> HalbachRing:
        """Anel em SI. Gera :class:`InfeasibleGeometryError` se não for construível."""
        return HalbachRing(
            bore_radius=self.bore_radius_mm * MM,
            magnet=self.magnet(),
            n_bands=self.n_bands,
            band_gap=self.fixed.band_gap_mm * MM,
            magnet_gap=self.fixed.magnet_gap_mm * MM,
            field_direction=math.radians(self.fixed.field_direction_deg),
        )

    def check_axial(self) -> None:
        """Recusa espaçamento menor que o cubo mais a folga axial (anéis se sobreporiam)."""
        if self.ring_spacing_mm < self.magnet_size_mm + self.fixed.axial_gap_mm - 1e-9:
            raise InfeasibleGeometryError(
                f"espaçamento {self.ring_spacing_mm:g} mm < cubo {self.magnet_size_mm:g} mm + folga "
                f"{self.fixed.axial_gap_mm:g} mm"
            )
        if self.n_rings < 1:
            raise InfeasibleGeometryError("é preciso pelo menos 1 anel")

    def group_key(self) -> tuple:
        """Tudo menos n_rings e DSV: arranjos com a mesma chave são calculados juntos."""
        return (self.ring_spacing_mm, self.bore_radius_mm, self.n_bands, self.magnet_size_mm,
                self.remanence_T, self.fixed)


def fixed_from_scenario(cfg: ScenarioConfig) -> FixedParams:
    """Valores fixos tirados do cenário do config.toml."""
    return FixedParams(
        band_gap_mm=cfg.ring.band_gap / MM,
        magnet_gap_mm=cfg.ring.magnet_gap / MM,
        axial_gap_mm=cfg.stack.axial_gap / MM,
        density_kg_m3=cfg.magnet.density,
        field_direction_deg=math.degrees(cfg.field.direction),
    )
