# HalbachOptimisation-IC

Otimização da configuração de anéis de ímãs permanentes (arranjo Halbach) para
um aparelho de ressonância magnética portátil de campo baixo (50 mT), voltado
para imagem de cabeça e de membros.

Projeto de Iniciação Científica — Engenharia de Computação, UTFPR.

## Origem e licença

Este repositório é um **trabalho derivado** de
[LUMC-LowFieldMRI/HalbachOptimisation](https://github.com/LUMC-LowFieldMRI/HalbachOptimisation),
de Tom O'Reilly, distribuído sob a licença MIT (ver [LICENSE](LICENSE), mantido
com o copyright original). O código original, sem nenhuma alteração, está em
[legacy/](legacy/) e é usado nos testes de regressão.

O código original acompanha o ímã Halbach de 50 mT do LUMC, descrito em:

> T. O'Reilly, W. M. Teeuwisse, A. G. Webb. *Three-dimensional MRI in a
> homogenous 27 cm diameter bore Halbach array magnet.* Journal of Magnetic
> Resonance 307 (2019) 106578.

As diferenças em relação ao original (bugs corrigidos, mudanças de modelo e
decisões de projeto) estão documentadas em [DOCS/correcoes.md](DOCS/correcoes.md).

## O que o programa faz

1. Monta o espaço de busca: `n_rings` anéis ao longo do eixo z, e cada anel pode
   ter um entre vários raios de bore. Para cada raio, a classe `HalbachRing`
   calcula quantos cubos cabem em cada camada sem sobreposição e recusa
   configurações inviáveis.
2. Pré-calcula o campo de cada opção de anel em cada posição, nos pontos da
   esfera útil (DSV).
3. Um algoritmo genético escolhe o raio de cada posição para **minimizar a
   inomogeneidade (ppm)**. O campo médio precisa ficar em 50 mT ± tolerância e a
   massa abaixo do limite, ambos como restrições.
4. Recalcula o campo da melhor solução na esfera inteira, salva os resultados e
   gera os gráficos.

O campo B0 é transversal ao bore, na direção configurada em
`field.direction_deg`. O padrão é −90°, ou seja, vertical, de cima para baixo (−y).

## Instalação

Requer [uv](https://docs.astral.sh/uv/) (`brew install uv`). Ele cria um Python
3.12 isolado na pasta `.venv` e instala as dependências:

```bash
uv sync
```

## Como rodar

Toda a configuração fica em [config.toml](config.toml), com um bloco `defaults` e
os cenários `head` (cabeça, DSV 200 mm) e `limb` (membros, DSV 110 mm). As unidades
estão no nome de cada chave (mm, mT, graus, kg).

```bash
# ver o espaço de busca, as opções de anel, a massa e a memória, sem otimizar
uv run halbach-ic info --scenario head

# otimizar (salva em results/<cenário>_<data>/)
uv run halbach-ic run --scenario head

# execução rápida para testar
uv run halbach-ic run --scenario limb --population 1000 --generations 20

# testes
uv run pytest

# erro da simetria de octante (item 6 de DOCS/correcoes.md)
uv run python scripts/quantify_octant_error.py --scenario head
```

### Saídas de `run`

| Arquivo | Conteúdo |
|---|---|
| `resultado.json` | genes, raio e número de ímãs de cada anel, ppm e campo médio (na região otimizada e na esfera inteira), massa, tempos, histórico por geração e a configuração usada |
| `convergencia.png` | ppm do melhor indivíduo de cada geração (escala log). Pontos azuis = soluções viáveis. Uma curva que ainda desce no final indica que mais gerações ajudariam. |
| `perfis.png` | B0 ao longo de x, y e z passando pelo centro, com a linha do alvo. Uma curva plana é bom sinal; as pontas mostram onde o campo se degrada na borda do DSV. |
| `cortes.png` | B0 nos três planos centrais, na mesma escala de cor. O padrão mostra que termo domina a inomogeneidade (por exemplo, variação ao longo de z = efeito das pontas do cilindro). |

Durante a execução, cada linha mostra a geração, o ppm e o campo do melhor
indivíduo, se ele é viável, a fração de viáveis e a fração de indivíduos
repetidos. Muitos repetidos indicam perda de diversidade.

## Estrutura

```
config.toml               parâmetros (único lugar com valores numéricos)
src/halbach_ic/
  config.py               lê o TOML e converte para SI
  geometry.py             HalbachRing, DesignSpace, Design (posições e orientações)
  field_model.py          modelos de campo (dipolo; cubo exato na Fase 2)
  domain.py               grade, esfera do DSV, simetria de octante
  objective.py            tabela de campos, ppm, restrições
  optimizer.py            algoritmo genético (DEAP)
  pipeline.py             liga as peças
  visualization.py        gráficos
  cad_export.py           exportação CAD (Fase 7)
  cli.py                  linha de comando
tests/                    pytest
scripts/                  análises avulsas
legacy/                   código original, intacto
DOCS/                     correções e resultados para o relatório
```

## Convenções

- Internamente tudo está em SI (m, T, rad, kg). A conversão acontece só na
  leitura do `config.toml` e na apresentação.
- Um ímã na posição angular θ tem magnetização no ângulo `2θ + fase`. Para
  Halbach k = 2, o campo no centro aponta para `−fase`. Por isso o código recebe
  a **direção desejada de B0** e calcula `fase = −direção`. Ver
  `tests/test_field_direction.py`.
- Cada cubo gira junto com a magnetização. Para evitar sobreposição, cada cubo é
  tratado no plano xy como o círculo circunscrito (diâmetro a√2). O raio de bore
  informado é o raio livre até esse círculo, portanto conservador.
