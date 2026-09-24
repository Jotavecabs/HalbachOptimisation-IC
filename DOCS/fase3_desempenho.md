# Fase 3 — Desempenho

Objetivo: rodar num notebook comum, sem cluster. Máquina de referência:
MacBook Air M4 (4 núcleos de desempenho + 6 de eficiência, sem ventoinha),
16 GB de RAM, Python 3.12.

Para reproduzir:

```bash
uv run python scripts/benchmark.py          # tempos por etapa, 1 e 10 processos
uv run python scripts/scaling.py            # escalabilidade do pré-cálculo
```

Os números ficam em [resultados/fase3/](resultados/fase3/). A linha de base
(`linha_de_base.json`) foi medida com o código do fim da Fase 2, antes de
qualquer mudança.

## O que mudou

1. **Avaliação vetorizada** (`Objective.evaluate_batch`). A população inteira é
   avaliada como uma operação matricial. A tabela foi reorganizada para
   `(slots, opções, pontos)`, de modo que `values[s, genes[:, s]]` lê linhas
   contíguas da memória. A soma é feita em float64, em blocos de tamanho
   configurável (`performance.eval_chunk_mb`).
2. **GA em NumPy** ([optimizer.py](../src/halbach_ic/optimizer.py)). A população
   é uma matriz de inteiros. Seleção por torneio, cruzamento de dois pontos e
   mutação uniforme inteira foram reimplementados com a mesma semântica do DEAP
   (`selTournament`, `cxTwoPoint` via `varAnd`, `mutUniformInt`). Antes, 25% do
   tempo do GA ia para o `deepcopy` dos 10 000 indivíduos a cada geração.
3. **Paralelismo real** com `multiprocessing.Pool` (modo `spawn`, igual em
   macOS, Linux e Windows):
   - pré-cálculo da tabela: uma tarefa por (slot, opção);
   - avaliação da população: um bloco de genes por processo;
   - mapa final do campo: os pontos divididos entre processos.
4. **Memória compartilhada.** A tabela de campos fica num único bloco de
   `shared_memory`, que os processos abrem sem copiar. Com 10 processos, a
   tabela continua ocupando 1× a RAM, e não 10×.
5. **Controle de memória** ([memory.py](../src/halbach_ic/memory.py)). Antes de
   alocar qualquer coisa, o programa estima a memória da tabela (float32), dos
   blocos de avaliação e dos temporários do modelo de campo e compara com a RAM
   disponível (`psutil`):
   - acima de 50% da RAM disponível: **aviso**, com sugestões para reduzir;
   - acima de 100%: **erro** antes de começar.

   O comando `halbach-ic info` mostra a memória prevista **e o tempo previsto**
   de pré-cálculo, calculado a partir do número de pares (ponto, ímã) e do custo
   medido por par.

Configuração nova no `config.toml`:

```toml
[defaults.performance]
n_workers = 0        # 0 = todos os núcleos, 1 = sem paralelismo
eval_chunk_mb = 64
```

## Resultados

| Etapa | Linha de base | Novo, 1 processo | Novo, 10 processos | Ganho |
|---|---|---|---|---|
| **Cabeça** — tabela, modelo exato | 74,8 s | 70,6 s | 21,5 s | 3,5× |
| Cabeça — tabela, dipolo | 5,2 s | 4,7 s | 1,1 s | 4,7× |
| Cabeça — GA (10 000 × 100) | 25,2 s | 7,9 s | 5,2 s | 4,8× |
| Cabeça — mapa final, modelo exato | 27,7 s | 26,4 s | 8,5 s | 3,3× |
| **Cabeça — execução completa (exato)** | **~128 s** | | **~35 s** | **3,6×** |
| **Membros** — tabela, modelo exato | 2,7 s | 3,1 s | 1,3 s | 2,1× |
| Membros — GA | 10,2 s | 1,0 s | 0,8 s | 13× |
| **Membros — execução completa (exato)** | **~14 s** | | **~3 s** | **4,9×** |

### Escalabilidade do pré-cálculo (cabeça, modelo exato)

| Processos | 1 | 2 | 4 | 6 | 10 |
|---|---|---|---|---|---|
| Aceleração | 1,0 | 1,7 | 2,5 | 2,8 | 3,0 |

(Medido com blocos de 1 milhão de pares. Com os blocos de 200 mil pares
adotados no fim da fase, 10 processos chegaram a 3,3×.)

O ganho satura perto de 3× a partir de 4 processos. Explicação: o M4 tem só 4
núcleos de desempenho (os outros 6 são de eficiência, bem mais lentos), as
contas do NumPy com arrays grandes são limitadas pela banda de memória, e um
notebook sem ventoinha reduz o clock sob carga contínua. Numa máquina com mais
núcleos de desempenho o ganho tende a ser maior.

## Observação importante: variação do GA entre sementes

O GA novo usa o gerador do NumPy, então a mesma semente não produz a mesma
sequência do DEAP. Para confirmar que a reimplementação é equivalente, os
dois foram rodados com 10 sementes cada (cenário completo, dipolo):

| | DEAP (antigo) | NumPy (novo) |
|---|---|---|
| Cabeça: mediana (mín–máx) | 793 ppm (589–914) | 770 ppm (659–969) |
| Membros: mediana (mín–máx) | 2085 ppm (1716–2849) | 2000 ppm (1522–2557) |

As distribuições são equivalentes. O dado mais relevante, porém, é a
**dispersão**: com a configuração atual, o resultado de uma única execução do
GA varia cerca de **±25% conforme a semente**. Números de uma só execução não
devem ser comparados entre si. A Fase 4 (MILP) dá o ótimo global como
referência, e na Fase 5 vale considerar várias execuções independentes ou mais
diversidade (hoje ~93% da população final é repetida).

## Cuidados de uso

- **Scripts próprios precisam de `if __name__ == "__main__":`.** Com o modo
  `spawn`, cada processo filho reimporta o arquivo principal. Todos os scripts
  do repositório já seguem isso. Código enviado pela entrada padrão
  (`python - <<EOF`) não pode ser reimportado; nesse caso o pacote detecta a
  situação e usa 1 processo, com aviso, em vez de travar.
- **Jupyter funciona normalmente,** porque as funções executadas nos
  processos filhos ficam no pacote, não no notebook.
- **Para usar menos memória:** `performance.n_workers` menor, `eval_chunk_mb`
  menor, `domain.symmetry = "octant"` ou uma grade mais grossa.
