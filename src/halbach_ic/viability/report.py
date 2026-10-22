"""Gera o relatório da análise de viabilidade: figuras, CSVs e ``relatorio.md``.

O relatório é escrito para ser lido sem conhecer o código: cada gráfico vem
com o que ele mostra, a explicação física e observações tiradas dos números.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from halbach_ic.field_model import get_backend  # noqa: E402
from halbach_ic.geometry import Design, DesignSpace, symmetric_slots  # noqa: E402
from halbach_ic.domain import make_grid  # noqa: E402
from halbach_ic.pipeline import field_map  # noqa: E402
from halbach_ic.visualization import plot_profiles, plot_slices  # noqa: E402
from halbach_ic.viability.params import MM, PARAMS, ArrayParams  # noqa: E402
from halbach_ic.viability.plots import plot_line, plot_map, plot_tradeoff  # noqa: E402
from halbach_ic.viability.simulate import METRICS, SimResult  # noqa: E402
from halbach_ic.viability.sweeps import (  # noqa: E402
    STATUS_LABELS,
    AnalysisData,
    Criteria,
    LineData,
    MapData,
    viability_code,
    write_csv,
)


# --------------------------------------------------------------------------
# formatação
# --------------------------------------------------------------------------


def num(value: float, digits: int = 1) -> str:
    """Número em português: vírgula decimal e espaço como separador de milhar."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    text = f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")
    return text


def param_value(name: str, value: float) -> str:
    info = PARAMS[name]
    text = str(int(value)) if info.integer else num(value, 2 if abs(value) < 10 else 1).rstrip("0").rstrip(",")
    return f"{text} {info.unit}".strip()


def pct(ppm: float) -> str:
    """Homogeneidade em % a partir da inomogeneidade em ppm (100 % = perfeito)."""
    if not math.isfinite(ppm):
        return "—"
    value = 100 - ppm / 1e4
    digits = 2 if ppm >= 1000 else 3 if ppm >= 100 else 4
    return num(value, digits) + " %"


def crossings(x: np.ndarray, y: np.ndarray, level: float) -> list[float]:
    """Valores de x onde y cruza ``level`` (interpolação linear)."""
    out = []
    for i in range(len(x) - 1):
        a, b = y[i] - level, y[i + 1] - level
        if np.isfinite(a) and np.isfinite(b) and a * b <= 0 and a != b:
            out.append(float(x[i] + (x[i + 1] - x[i]) * a / (a - b)))
    return out


# --------------------------------------------------------------------------
# observações automáticas
# --------------------------------------------------------------------------


def line_observations(line: LineData, criteria: Criteria) -> list[str]:
    sweep = line.sweep
    x = np.array(sweep.x_values, dtype=float)
    x_info = PARAMS[sweep.x]
    notes = []
    for value in line.results:
        label = "Configuração de referência" if value is None else \
            f"{PARAMS[sweep.series].label} = {param_value(sweep.series, value)}"  # type: ignore[index]
        b0, ppm, mass = (line.metric(value, k) for k in ("b0_mT", "ppm", "mass_kg"))
        valid = np.isfinite(b0)
        if not valid.any():
            notes.append(f"**{label}:** nenhum arranjo válido nesta faixa.")
            continue
        parts = [f"B0 vai de {num(np.nanmin(b0))} a {num(np.nanmax(b0))} mT"]
        hits = crossings(x, b0, criteria.target_mT)
        if hits:
            parts.append("atinge o alvo de " + num(criteria.target_mT, 0) + " mT em "
                         + ", ".join(f"{x_info.lower} ≈ {param_value(sweep.x, h)}" for h in hits))
        else:
            side = "sempre abaixo" if np.nanmax(b0) < criteria.target_mT else "sempre acima"
            parts.append(f"fica {side} do alvo de {num(criteria.target_mT, 0)} mT nesta faixa")
        finite = np.isfinite(ppm)
        if finite.any():
            spread = np.nanmax(ppm) / np.nanmin(ppm)
            if spread < 1 + 1e-4:
                parts.append(f"a inomogeneidade não muda ({num(np.nanmin(ppm), 0)} ppm)")
            else:
                i = int(np.nanargmin(ppm))
                parts.append(f"a melhor homogeneidade é {pct(ppm[i])} ({num(ppm[i], 0)} ppm), com "
                             f"{x_info.lower} = {param_value(sweep.x, x[i])}")
        parts.append(f"massa de {num(np.nanmin(mass))} a {num(np.nanmax(mass))} kg")
        invalid = int((~valid).sum())
        if invalid:
            parts.append(f"{invalid} ponto(s) impossível(is) (geometria ou DSV maior que o bore)")
        notes.append(f"**{label}:** " + "; ".join(parts) + ".")
    return notes


def describe(r: SimResult) -> str:
    return ", ".join(f"{PARAMS[k].lower} {param_value(k, getattr(r.params, k))}" for k in PARAMS)


def map_observations(m: MapData, criteria: Criteria) -> list[str]:
    sweep = m.sweep
    flat = [r for row in m.results for r in row]
    ok = [r for r in flat if r.status == "ok"]
    notes = []
    if not ok:
        return ["Nenhum arranjo válido nesta faixa."]
    b0 = np.array([r.metrics["b0_mT"] for r in ok])
    notes.append(f"O campo no centro varia de {num(b0.min())} a {num(b0.max())} mT no plano analisado.")
    on_target = [r for r in ok if abs(r.metrics["b0_mT"] - criteria.target_mT) <= criteria.tolerance_mT]
    notes.append(f"{len(on_target)} de {len(flat)} arranjos ({num(100 * len(on_target) / len(flat))} %) ficam "
                 f"dentro de {num(criteria.target_mT, 0)} ± {num(criteria.tolerance_mT, 0)} mT.")
    best = min(ok, key=lambda r: r.metrics["ppm"])
    notes.append(f"Melhor homogeneidade do mapa: {pct(best.metrics['ppm'])} ({num(best.metrics['ppm'], 0)} ppm), com "
                 f"{PARAMS[sweep.x].lower} = {param_value(sweep.x, getattr(best.params, sweep.x))} e "
                 f"{PARAMS[sweep.y].lower} = {param_value(sweep.y, getattr(best.params, sweep.y))} "
                 f"(B0 = {num(best.metrics['b0_mT'])} mT, {num(best.metrics['mass_kg'])} kg).")
    viable = [r for r in flat if viability_code(r, criteria) == 0]
    if viable:
        bv = min(viable, key=lambda r: r.metrics["ppm"])
        notes.append(f"**Melhor arranjo viável:** {PARAMS[sweep.x].lower} = "
                     f"{param_value(sweep.x, getattr(bv.params, sweep.x))}, {PARAMS[sweep.y].lower} = "
                     f"{param_value(sweep.y, getattr(bv.params, sweep.y))} → B0 = {num(bv.metrics['b0_mT'])} mT, "
                     f"homogeneidade {pct(bv.metrics['ppm'])} ({num(bv.metrics['ppm'], 0)} ppm), "
                     f"{num(bv.metrics['mass_kg'])} kg, {num(bv.metrics['length_mm'] / 10, 1)} cm.")
    else:
        notes.append("**Nenhum arranjo deste mapa atende a todos os critérios.** O mapa de viabilidade mostra "
                     "qual critério falha em cada região.")
    counts = {}
    for r in flat:
        counts[viability_code(r, criteria)] = counts.get(viability_code(r, criteria), 0) + 1
    notes.append("Classificação: " + "; ".join(f"{STATUS_LABELS[c]} {n}" for c, n in sorted(counts.items())) + ".")
    return notes


# --------------------------------------------------------------------------
# textos fixos
# --------------------------------------------------------------------------

INTRO = """\
## 1. O que é esta análise

Esta é uma **análise de viabilidade por varredura de parâmetros**. Não há
otimização: em cada arranjo simulado, **todos os anéis são iguais** (mesmo
raio, mesmo número de camadas, mesmo ímã), igualmente espaçados e centrados no
meio do ímã. Partindo de uma **configuração de referência**, um parâmetro
(gráficos de linha) ou dois parâmetros (mapas de calor) são variados, e os
demais ficam fixos. Assim dá para ver separadamente o efeito de cada escolha
de projeto.

**Como o campo é calculado.** Cada cubo de NdFeB é simulado com a expressão
analítica exata do campo de um cubo uniformemente magnetizado (biblioteca
magpylib), com a magnetização girando ao redor do anel no padrão Halbach
(k = 2), para gerar um campo transversal na direção vertical.

**Duas propriedades físicas tornam o cálculo exato e rápido.** Dentro do DSV
não há ímãs, então cada componente do campo é uma função harmônica
(∇²B = 0). Disso decorre que:

* o **maior e o menor valor do campo dentro da esfera ficam na superfície**
  (princípio do máximo). A inomogeneidade do volume inteiro é medida com
  pontos só na superfície do DSV;
* a **média do campo no volume é igual ao campo no centro** (propriedade da
  média). Por isso o "campo do ímã" é B0 no centro.

Os dois resultados foram conferidos contra o cálculo numa grade 3D completa
(diferença de 6×10⁻⁶ no campo e < 0,5 ppm na inomogeneidade).

**Importante — os valores absolutos de homogeneidade são pessimistas.** Com
anéis todos iguais, a homogeneidade fica na casa de dezenas de milhares de
ppm. Escolhendo um raio diferente para cada anel (otimização, feita na branch
`main` deste repositório), o mesmo tipo de arranjo chega a algumas centenas
de ppm. Por isso esta análise serve para comparar **tendências** (o que
melhora e o que piora cada parâmetro) e para dimensionar campo, massa e
tamanho. O valor final de homogeneidade depende da otimização.
"""

READING_GUIDE = """\
## 4. Como ler os gráficos

**Gráficos de linha** (seção 5). Cada figura tem quatro painéis que
compartilham o eixo horizontal (o parâmetro variado):

| Painel | O que mostra | O que é bom |
|---|---|---|
| Campo B0 no centro | campo produzido; faixa cinza = alvo ± tolerância | estar dentro da faixa cinza |
| Inomogeneidade no DSV | variação do campo dentro da esfera, em ppm, **escala log** (homogeneidade = 100 % − ppm/10 000) | quanto menor, melhor |
| Massa dos ímãs | massa de NdFeB; linha vermelha = limite | ficar abaixo da linha |
| Campo por massa | mT obtidos por kg de ímã | quanto maior, mais eficiente |

Cada curva é um valor de um segundo parâmetro (legenda). A linha
**pontilhada vertical** marca o valor da configuração de referência.

**Mapas de calor** (seção 6). Dois parâmetros variam juntos; cada célula é
um arranjo. Os quatro painéis são:

* **campo B0:** a **linha branca contínua** é o caminho dos arranjos que dão
  exatamente o campo alvo e as tracejadas, a tolerância. Qualquer ponto sobre
  a linha branca é um candidato;
* **inomogeneidade:** cores claras = melhor (mais perto de 100 % de
  homogeneidade); as linhas pretas marcam 1 000 ppm (99,9 %), 10 000 ppm
  (99 %), 100 000 ppm (90 %)...;
* **massa:** a linha vermelha é o limite de massa;
* **viabilidade:** verde = atende a todos os critérios. Nas outras cores, o
  nome do critério que falha (quando falham vários, aparece o mais grave).

A **estrela** marca a configuração de referência. As linhas **azuis
traço-ponto** marcam os limites de comprimento (quando o mapa os cruza): os
arranjos aceitáveis ficam entre elas.

Para achar um bom projeto num mapa: siga a linha branca do painel de campo e
procure, ao longo dela, a região mais clara no painel de inomogeneidade que
ainda esteja abaixo da linha vermelha de massa.
"""

LIMITS = """\
## 9. Limitações e próximos passos

* **Anéis iguais:** a homogeneidade absoluta é pessimista (ver seção 1). Os
  valores servem para comparar tendências; o número final vem da otimização
  dos raios.
* **Só ímãs:** a massa não inclui a estrutura de suporte, as bobinas nem a
  blindagem.
* **Ímãs ideais:** todos os cubos com o mesmo Br e posição perfeita. Na
  prática, Br varia ~±1-2 % entre peças e há erro de montagem. Isso piora a
  homogeneidade e normalmente é corrigido com shimming.
* **Temperatura:** o NdFeB perde ~0,1 %/°C de Br. O campo (e a frequência de
  Larmor) varia com a temperatura, mas a homogeneidade em ppm não.
* **Homogeneidade como objetivo:** a homogeneidade não é um corte de
  viabilidade; os arranjos viáveis são ordenados por ela (o mais perto de
  100 % vence). Para exigir um valor mínimo, defina `ppm_maximo` no
  `viabilidade.toml` (ex.: 99,9 % = 1000 ppm).
"""


# --------------------------------------------------------------------------
# relatório
# --------------------------------------------------------------------------


def _save(fig, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path.as_posix()


def _base_field_figures(data: AnalysisData, outdir: Path, n_workers: int) -> tuple[str, str] | None:
    """Mapas e perfis do campo da configuração de referência."""
    base = data.plan.base
    if data.base.status != "ok":
        return None
    ring = base.ring()
    space = DesignSpace(slots=symmetric_slots(base.n_rings, base.ring_spacing_mm * MM), options=(ring,))
    design = Design(space, (0,) * space.n_slots)
    grid = make_grid(base.dsv_diameter_mm * MM, base.dsv_diameter_mm * MM / 40)
    fmap = field_map(design, grid, get_backend(data.plan.general.backend),
                     math.radians(base.fixed.field_direction_deg), n_workers)
    target = data.plan.criteria.target_mT * 1e-3
    return (_save(plot_slices(fmap), outdir / "figuras" / "referencia_cortes.png"),
            _save(plot_profiles(fmap, target), outdir / "figuras" / "referencia_perfis.png"))


def _rel(path: str, outdir: Path) -> str:
    return Path(path).relative_to(outdir).as_posix()


def _viable_table(data: AnalysisData, limit: int = 10) -> list[str]:
    crit = data.plan.criteria
    dsv = data.plan.base.dsv_diameter_mm
    seen: dict[ArrayParams, SimResult] = {}
    for r in data.all_results():
        # o DSV é requisito do cenário, não escolha de projeto: compara todos no mesmo DSV
        if r.params.dsv_diameter_mm == dsv and viability_code(r, crit) == 0:
            seen[r.params] = r
    if not seen:
        return ["Nenhum dos arranjos simulados atende a todos os critérios ao mesmo tempo. Os mapas de "
                "viabilidade mostram qual critério falha em cada região; os próximos passos naturais são "
                "ampliar as faixas das varreduras ou rever os limites."]
    best = sorted(seen.values(), key=lambda r: r.metrics["ppm"])[:limit]
    lines = [f"{len(seen)} arranjos simulados atendem a todos os requisitos (homogeneidade medida no DSV de "
             f"{num(dsv, 0)} mm do cenário). Como a homogeneidade é o "
             f"objetivo (quanto mais perto de 100 %, melhor), eles estão ordenados por ela. Os {len(best)} melhores:",
             "",
             "| # | Anéis | Espaç. (mm) | Bore Ø (mm) | Camadas | Cubo (mm) | Br (T) | B0 (mT) | Homogeneidade "
             "| Inomog. (ppm) | Massa (kg) | Comprim. (cm) | Ø ext. (mm) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(best, 1):
        p, m = r.params, r.metrics
        lines.append(f"| {i} | {p.n_rings} | {num(p.ring_spacing_mm, 0)} | {num(2 * p.bore_radius_mm, 0)} | "
                     f"{p.n_bands} | {num(p.magnet_size_mm, 0)} | {num(p.remanence_T, 2)} | {num(m['b0_mT'])} | "
                     f"{pct(m['ppm'])} | {num(m['ppm'], 0)} | {num(m['mass_kg'])} | {num(m['length_mm'] / 10, 1)} | "
                     f"{num(m['outer_diameter_mm'], 0)} |")
    return lines


def write_report(data: AnalysisData, outdir: Path, log=print) -> Path:
    """Gera figuras, CSVs e o relatório em ``outdir``. Devolve o caminho do relatório."""
    plan, crit, base = data.plan, data.plan.criteria, data.plan.base
    outdir.mkdir(parents=True, exist_ok=True)
    md: list[str] = []

    md += [f"# Análise de viabilidade — cenário `{plan.scenario}`", "",
           f"Gerado em {time.strftime('%d/%m/%Y %H:%M')}. {len(set(r.params for r in data.all_results()))} "
           f"arranjos simulados em {num(data.elapsed_s, 0)} s (modelo de campo: `{plan.general.backend}`).", "",
           "Arquivos: figuras em `figuras/`, dados de todos os arranjos em `dados/` (CSV, abre no Excel).", "",
           "**Sumário:** 1. O que é esta análise · 2. Configuração de referência · 3. Critérios de viabilidade · "
           "4. Como ler os gráficos · 5. Gráficos de linha · 6. Mapas de calor · 7. Massa × homogeneidade · "
           "8. Arranjos viáveis · 9. Limitações", "", INTRO]

    # 2. referência
    md += ["## 2. Configuração de referência", "",
           "Todos os gráficos partem deste arranjo e mudam um ou dois parâmetros de cada vez.", "",
           "| Parâmetro | Valor |", "|---|---|"]
    md += [f"| {PARAMS[k].label} | {param_value(k, getattr(base, k))} |" for k in PARAMS]
    if data.base.status == "ok":
        md += ["", "| Resultado | Valor |", "|---|---|"]
        md += [f"| {METRICS[k].label} | {num(v, 0 if k in ('ppm', 'n_magnets', 'length_mm', 'outer_diameter_mm') else 2)} {METRICS[k].unit} |"
               for k, v in data.base.metrics.items()]
        log("figuras da configuração de referência...")
        figs = _base_field_figures(data, outdir, plan.general.n_workers)
        if figs:
            md += ["", "### Campo da configuração de referência", "",
                   f"![cortes]({_rel(figs[0], outdir)})", "",
                   "**O que mostra:** o campo B0 nos três planos centrais do DSV, na mesma escala de cor. "
                   "**Como ler:** cor uniforme = campo homogêneo. No plano xy (transversal) o campo de um "
                   "Halbach é quase uniforme. Nos planos que contêm o eixo z (xz e yz) aparece a variação ao "
                   "longo do comprimento, causada pelas pontas do cilindro. É ela que domina a inomogeneidade "
                   "quando os anéis são todos iguais.", "",
                   f"![perfis]({_rel(figs[1], outdir)})", "",
                   "**O que mostra:** o campo ao longo de três retas que passam pelo centro (x, y e z). A "
                   "linha tracejada é o alvo. Curvas planas = homogêneo. A curva de z mostra o efeito das "
                   "pontas do cilindro."]
    else:
        md += ["", f"A configuração de referência é inviável: {data.base.status}."]

    # 3. critérios
    md += ["", "## 3. Critérios de viabilidade", "",
           "Um arranjo é **viável** quando atende a todos estes requisitos (valores do `config.toml`):", "",
           f"* campo no centro entre {num(crit.target_mT - crit.tolerance_mT, 0)} e "
           f"{num(crit.target_mT + crit.tolerance_mT, 0)} mT;",
           f"* diâmetro livre (bore) de pelo menos {num(crit.min_bore_diameter_mm, 0)} mm (espaço para "
           "bobinas de gradiente e RF);",
           f"* massa de ímãs de no máximo {num(crit.max_mass_kg)} kg;",
           *([f"* comprimento entre {num((crit.min_length_mm or 0) / 10, 0)} e "
              f"{num((crit.max_length_mm or math.inf) / 10, 0)} cm;"]
             if crit.min_length_mm is not None or crit.max_length_mm is not None else []),
           (f"* inomogeneidade de no máximo {num(crit.max_ppm, 0)} ppm;" if crit.max_ppm is not None else
            "* a **homogeneidade é o objetivo**, não um corte: entre os arranjos que atendem aos requisitos "
            "acima, o melhor é o mais próximo de 100 % (seção 8);"),
           "* geometria possível: os ímãs não se sobrepõem e o DSV cabe dentro do bore.", "", READING_GUIDE]

    # 5. linhas
    md += ["## 5. Gráficos de linha: um parâmetro de cada vez", ""]
    for i, line in enumerate(data.lines, 1):
        sweep = line.sweep
        log(f"gráfico {sweep.name}...")
        fig = plot_line(line, getattr(base, sweep.x), crit, plan.scenario)
        path = _save(fig, outdir / "figuras" / f"{sweep.name}.png")
        write_csv([r for rs in line.results.values() for r in rs], outdir / "dados" / f"{sweep.name}.csv", crit)
        info = PARAMS[sweep.x]
        title = f"### 5.{i} {info.label}"
        if sweep.series:
            title += f" (curvas: {PARAMS[sweep.series].lower})"
        md += [title, "", f"![{sweep.name}]({_rel(path, outdir)})", "",
               f"**O que varia:** {info.lower} de {param_value(sweep.x, sweep.x_values[0])} a "
               f"{param_value(sweep.x, sweep.x_values[-1])}"
               + (f"; cada curva é um valor de {PARAMS[sweep.series].lower}." if sweep.series else ".")
               + " O resto fica igual à referência.", "",
               f"**Por que acontece:** {info.explanation}", "",
               "**O que os números mostram:**", ""]
        md += [f"* {note}" for note in line_observations(line, crit)]
        md += [""]

    # 6. mapas
    md += ["## 6. Mapas de calor: dois parâmetros ao mesmo tempo", ""]
    for i, m in enumerate(data.maps, 1):
        sweep = m.sweep
        log(f"gráfico {sweep.name}...")
        path = _save(plot_map(m, base, crit, plan.scenario), outdir / "figuras" / f"{sweep.name}.png")
        write_csv([r for row in m.results for r in row], outdir / "dados" / f"{sweep.name}.csv", crit)
        xi, yi = PARAMS[sweep.x], PARAMS[sweep.y]
        md += [f"### 6.{i} {xi.label} × {yi.label}", "", f"![{sweep.name}]({_rel(path, outdir)})", "",
               f"**O que varia:** {xi.lower} (eixo horizontal, {param_value(sweep.x, sweep.x_values[0])} a "
               f"{param_value(sweep.x, sweep.x_values[-1])}) e {yi.lower} (eixo vertical, "
               f"{param_value(sweep.y, sweep.y_values[0])} a {param_value(sweep.y, sweep.y_values[-1])}).", "",
               f"**Por que acontece:** *{xi.label}:* {xi.explanation} *{yi.label}:* {yi.explanation}", "",
               "**O que os números mostram:**", ""]
        md += [f"* {note}" for note in map_observations(m, crit)]
        md += [""]

    # 7. compromisso
    if data.maps:
        path = _save(plot_tradeoff(data), outdir / "figuras" / "compromisso_massa_homogeneidade.png")
        md += ["## 7. Compromisso entre massa e homogeneidade", "", f"![compromisso]({_rel(path, outdir)})", "",
               "**O que mostra:** cada ponto é um arranjo dos mapas de calor, posicionado pela massa (horizontal) "
               "e pela inomogeneidade (vertical, escala log); a cor é o campo B0. Os pontos com contorno "
               "vermelho são os viáveis.", "",
               "**Como ler:** o canto inferior esquerdo (leve e homogêneo) é o ideal. A borda inferior da "
               "nuvem de pontos é a **fronteira de compromisso**: para cada massa, a melhor homogeneidade que "
               "esses arranjos alcançam. Para ganhar homogeneidade além dela é preciso mudar o tipo de "
               "arranjo (por exemplo, otimizar o raio de cada anel), não só os parâmetros.", ""]

    # 8. viáveis
    md += ["## 8. Arranjos viáveis", ""] + _viable_table(data) + [""]
    md += [LIMITS]

    all_results = data.all_results()
    write_csv(all_results, outdir / "dados" / "todos_os_arranjos.csv", crit)
    report = outdir / "relatorio.md"
    report.write_text("\n".join(md), encoding="utf-8")
    return report
