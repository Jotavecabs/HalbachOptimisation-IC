# Análise de viabilidade — guia de uso

Esta ferramenta simula arranjos Halbach variando os parâmetros de projeto e
mostra como o **campo**, a **homogeneidade**, a **massa**, o **tamanho** e a
**frequência de operação** respondem. Ela gera um relatório completo, com
gráficos de linha, mapas de calor e explicações.

Relatórios já gerados:
- [cabeça](resultados/viabilidade/head/relatorio.md)
- [membros](resultados/viabilidade/limb/relatorio.md)

## Rodar

```bash
cd ~/Documents/ic/HalbachOptimisation-IC
uv run halbach-ic viabilidade --scenario head     # ~1-2 min
uv run halbach-ic viabilidade --scenario limb     # ~15 s
```

A saída vai para `results/viabilidade_<cenário>_<data>/`. Ela tem:

| Arquivo | Conteúdo |
|---|---|
| `relatorio.md` | relatório completo com todos os gráficos e explicações. No VS Code, abra e aperte **Cmd+Shift+V** para ver formatado |
| `figuras/*.png` | cada gráfico separado, para usar em slides ou no relatório da IC |
| `dados/*.csv` | os números de cada arranjo simulado (abre no Excel) |

Opções úteis:

```bash
--backend dipole          # modelo rápido (aproximado), para testar faixas novas
--out minha_pasta         # escolhe onde salvar
--plano outro.toml        # usa outro arquivo de varreduras
--workers 4               # número de processos
```

## Mudar o que é simulado

Tudo fica em [viabilidade.toml](../viabilidade.toml), sem mexer em código.

**Configuração de referência** (`[cenarios.head.base]`): o arranjo de onde
todas as varreduras partem.

**Gráfico de linha:** um parâmetro no eixo x e, opcionalmente, uma curva para
cada valor de outro parâmetro.

```toml
[[cenarios.head.linhas]]
x = "bore_radius_mm"          # parâmetro do eixo horizontal
x_faixa = [100, 220, 5]       # [início, fim, passo]
serie = "n_bands"             # opcional: uma curva para cada valor
serie_valores = [1, 2, 3]
```

**Mapa de calor:** dois parâmetros variando juntos.

```toml
[[cenarios.head.mapas]]
x = "n_rings"
x_faixa = [5, 45, 2]
y = "bore_radius_mm"
y_faixa = [100, 220, 5]
```

Parâmetros disponíveis: `n_rings`, `ring_spacing_mm`, `bore_radius_mm`,
`n_bands`, `magnet_size_mm`, `remanence_T`, `dsv_diameter_mm`.

## Requisitos e objetivo

Um arranjo é **viável** quando atende a todos os requisitos:

| Requisito | Valor | Onde fica |
|---|---|---|
| Campo no centro | 50 ± 1 mT | `config.toml` |
| Bore mínimo | Ø270 mm (cabeça), Ø150 mm (membros) | `config.toml` |
| Massa de ímãs | ≤ 40 kg (cabeça), ≤ 20 kg (membros) | `config.toml` |
| Comprimento | entre 54 e 76 cm | `viabilidade.toml` (`comprimento_min_mm`, `comprimento_max_mm`) |

A **homogeneidade é o objetivo**, não um corte: entre os viáveis, o melhor
é o mais próximo de 100 %. Ela aparece em % (100 % = campo perfeitamente
uniforme) e em ppm:

| ppm | homogeneidade |
|---|---|
| 10 000 | 99 % |
| 1 000 | 99,9 % |
| 100 | 99,99 % |

Para exigir um mínimo, use `ppm_maximo` no `viabilidade.toml`.

## Busca da configuração de referência

As configurações de referência do `viabilidade.toml` são os **melhores
arranjos de anéis iguais que atendem a todos os requisitos**. Elas foram
encontradas testando todas as combinações de número de anéis, espaçamento,
bore e número de camadas:

```bash
uv run python scripts/buscar_referencia.py --scenario head
uv run python scripts/buscar_referencia.py --scenario limb --camadas 1 2 --csv viaveis_limb.csv
```

| Cenário | Melhor arranjo de anéis iguais | B0 | Homogeneidade | Massa | Comprimento |
|---|---|---|---|---|---|
| Cabeça | 47 anéis, 1 camada, espaçamento 16 mm, bore Ø280 mm | 50,3 mT | 99,29 % (7 098 ppm) | 30,5 kg | 74,8 cm |
| Membros | 35 anéis, 1 camada, espaçamento 22 mm, bore Ø200 mm | 49,6 mT | 99,93 % (685 ppm) | 16,3 kg | 76,0 cm |

(valores com o modelo exato; a busca usa o dipolo, que difere ~3 % na
inomogeneidade dos membros)

Nos dois cenários, os melhores são **ímãs longos (perto de 76 cm) com uma
camada só**: o comprimento afasta as pontas do DSV, e uma camada basta para
os 50 mT, deixando massa sobrando para mais anéis.

**Custo:** cada arranjo leva de milissegundos a ~1 s, conforme o tamanho.
Varreduras em número de anéis são quase de graça, porque são calculadas por
somas acumuladas. Um mapa de 20 × 25 células da cabeça leva cerca de 20 s.

## Como o cálculo funciona (resumo para o relatório)

1. Cada arranjo tem **todos os anéis iguais**, igualmente espaçados e
   centrados em z = 0. A magnetização segue o padrão Halbach k = 2 e gera
   campo vertical.
2. O campo de cada cubo vem da **expressão analítica exata** do cubo
   uniformemente magnetizado (magpylib).
3. **Princípio do máximo:** no DSV não há ímãs, então ∇²B = 0, e os extremos
   do campo ficam na superfície da esfera. A inomogeneidade é medida com
   ~400 pontos no oitavo positivo da superfície. Os outros sete oitavos são
   iguais por simetria, o que é verificado em teste.
4. **Propriedade da média:** a média de uma função harmônica no volume de uma
   esfera é o valor no centro. O campo do DSV é B0 no centro.
5. Arranjos que só diferem no número de anéis são calculados juntos: o campo
   é a soma das contribuições de cada par de anéis (±z).

Validação (`tests/test_viability.py`):
- o método da superfície coincide com o cálculo numa grade 3D completa;
- o campo é proporcional a Br, e a homogeneidade não muda com Br;
- as somas acumuladas coincidem com o cálculo de cada arranjo isolado.

## Cuidado ao interpretar

Com anéis todos iguais, a homogeneidade absoluta é **pessimista**: dezenas de
milhares de ppm na configuração de referência da cabeça, contra algumas
centenas quando o raio de cada anel é otimizado (branch `main`). Use esta
análise para entender **tendências** e para dimensionar campo, massa e
tamanho. O número final de homogeneidade depende da otimização.
