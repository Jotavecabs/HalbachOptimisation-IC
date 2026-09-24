# Correções e mudanças em relação ao código original

Este documento lista cada problema encontrado no código original
([legacy/](../legacy/), LUMC-LowFieldMRI/HalbachOptimisation) e o que foi feito.
Os itens 1 a 8 foram levantados antes da reestruturação. Os itens A em diante
foram encontrados durante o trabalho.

Para cada item: **sintoma**, **causa**, **correção**, **impacto** e **como validar**.

---

## 1. Mutação inválida para genes inteiros (`mutFlipBit`)

- **Sintoma:** depois de mutado, todo gene vira 0 ou 1, qualquer que fosse seu valor.
- **Causa:** `tools.mutFlipBit` foi feita para genes binários e aplica
  `individual[i] = type(individual[i])(not individual[i])`. Para um inteiro
  `g > 0`, `not g` é `False` e vira 0; para `g = 0`, vira 1.
- **Correção:** `tools.mutUniformInt(low=0, up=n_opções-1, indpb)`, que sorteia
  um índice válido qualquer ([optimizer.py](../src/halbach_ic/optimizer.py)).
- **Impacto:** no original, a mutação empurrava a população para os dois menores
  raios e não conseguia introduzir os outros 17. A exploração do espaço ficava
  quase inteiramente a cargo do cruzamento, que só recombina valores já
  presentes na população inicial.
- **Validação:** `tests/test_optimizer.py::test_legacy_mutflipbit_collapses_integer_genes`
  (reproduz o bug) e `test_mut_uniform_int_covers_all_options`.

## 2. `innerNumMagnets` com 20 valores para 19 raios

- **Sintoma:** o último valor (69) nunca é usado.
- **Causa:** erro de digitação nas tabelas escritas à mão.
- **Correção:** as tabelas deixaram de existir. O número de ímãs de cada camada é
  calculado pela classe `HalbachRing` ([geometry.py](../src/halbach_ic/geometry.py))
  a partir do raio, do tamanho do cubo e da folga (ver item 7). Um valor manual
  continua possível (`n_magnets_override`), mas é recusado se não couber.
- **Impacto:** nenhum no resultado original. Com a regra nova e folga de 1,5 mm,
  o cálculo reproduz exatamente os valores escolhidos à mão no original (50 e 57
  ímãs no raio de 148/169 mm).
- **Validação:** `tests/test_geometry.py::test_computed_count_matches_original_lumc_design`.

## 3. `multiprocessing` importado e não usado

- **Sintoma:** o array compartilhado (`multiprocessing.Array`) é criado, mas a
  avaliação usa o `map` do Python, em série, num único núcleo.
- **Causa:** a paralelização ficou incompleta no original.
- **Correção (Fase 1):** o import e o array compartilhado foram removidos. A
  paralelização real (`multiprocessing.Pool` no pré-cálculo e na avaliação)
  está prevista para a Fase 3.
- **Medida provisória:** o GA novo guarda o resultado de cada vetor já avaliado
  (cache), então indivíduos repetidos não são recalculados.

## 4. Ímã posicionado em `-pos` em vez de `+pos`

- **Sintoma:** em `singleMagnet`, a malha é `linspace(-D/2 + pos, D/2 + pos)`, e
  essas coordenadas são usadas como o vetor que vai do ímã até o ponto. Isso
  equivale a colocar o ímã em `-pos`.
- **Causa:** sinal trocado no deslocamento da malha.
- **Análise:** trocar todas as posições `p` por `-p` mantendo os momentos é uma
  inversão pela origem. Como B e m são pseudovetores, o campo resultante é
  exatamente `B_original(g) = B_correto(-g)`. Na esfera inteira, que é simétrica
  pela origem, o conjunto de valores é o mesmo, então o ppm não muda. No
  octante, o original avaliava na prática o octante oposto, o que só importa se o
  campo não for simétrico (ver item 6, onde isso é desprezível).
- **Correção:** o modelo de campo recebe os pontos e as posições reais dos ímãs e
  calcula `r = ponto - ímã` ([field_model.py](../src/halbach_ic/field_model.py)).
- **Validação:** `tests/test_regression_legacy.py::test_field_matches_legacy`
  verifica que o campo novo em `-g` é igual ao original em `g`, e que um anel
  girado de 180° reproduz o original.

## 5. Nenhuma restrição de campo médio

- **Sintoma:** a função objetivo só olha `(max - min) / média`. Nada leva a
  solução para 50 mT.
- **Correção:** a função objetivo ([objective.py](../src/halbach_ic/objective.py))
  devolve o ppm e uma **violação normalizada**:

  `violação = max(0, |B_médio - B_alvo| - tol) / tol + max(0, massa - massa_max) / massa_max`

  O GA compara soluções pelo par `(violação, ppm)` em ordem lexicográfica (regras
  de Deb): viável vence inviável, entre inviáveis vence a que viola menos, entre
  viáveis vence a mais homogênea. Não há penalidade com peso arbitrário. A
  restrição de massa entra da mesma forma.
- **Validação:** `tests/test_objective.py::test_constraint_violation`,
  `tests/test_optimizer.py::test_ga_reaches_feasible_region_and_is_reproducible` e
  `test_ga_prefers_smaller_violation_when_infeasible`.

## 6. Simetria de octante aproximada

- **Hipótese inicial:** anéis com número ímpar de ímãs não são simétricos por
  espelhamento, então avaliar só o octante x, y, z ≥ 0 seria aproximado.
- **Medição** ([scripts/quantify_octant_error.py](../scripts/quantify_octant_error.py),
  saída completa em [resultados/](resultados/)), 300 soluções aleatórias, grade de 5 mm:

  | Erro relativo máximo, octante vs esfera | cabeça, B0 +x | cabeça, B0 −y | membros, B0 +x | membros, B0 −y |
  |---|---|---|---|---|
  | pico a pico (max − min) | 0 | 7×10⁻⁷ | 2×10⁻⁵ | 7×10⁻⁵ |
  | média simples (como no original) | 1,2×10⁻³ | 1,1×10⁻³ | 1,9×10⁻³ | 1,8×10⁻³ |
  | ppm com média simples (original) | 1,2×10⁻³ | 1,1×10⁻³ | 1,9×10⁻³ | 1,8×10⁻³ |
  | **ppm com média ponderada (novo)** | 1×10⁻¹¹ | 7×10⁻⁷ | 2×10⁻⁵ | 7×10⁻⁵ |

  Todas as opções de anel têm uma camada com N par e outra com N ímpar. A
  assimetria de espelho (x → −x e y → −y) do campo de um anel isolado ficou
  abaixo da resolução do float32 (~10⁻⁷ relativo). Os resíduos que sobram com a
  média ponderada são da mesma ordem do arredondamento de float32 na soma das
  colunas da tabela.

- **Conclusões:**
  1. **A assimetria de N ímpar é desprezível.** A parte não simétrica do campo de
     um anel discreto é um harmônico de ordem ≈ N, que decai como (r/R)^N. Com
     r = 100 mm, R ≈ 150 mm e N ≈ 50, isso dá (0,67)^50 ≈ 10⁻⁹. O pico a pico
     medido no octante é igual ao da esfera inteira, a menos do arredondamento
     do float32.
  2. **O erro real estava na média.** O octante inclui os pontos sobre os planos
     de simetria (x = 0, y = 0, z = 0). Esses pontos representam menos pontos
     da esfera do que um ponto interior, mas na média simples contam igual. Isso
     desloca a média e, portanto, o ppm e o campo médio. **Este é um bug do
     código original que não constava da lista inicial.**
- **Correção:** cada ponto do octante recebe o peso `2^(3-k)`, onde k é o número
  de coordenadas nulas: um ponto interior representa 8 pontos, um ponto num plano
  representa 4, e assim por diante (`EvaluationGrid.weights`). Com a média
  ponderada, o octante reproduz a esfera inteira.
- **Decisão:** a otimização por octante continua como padrão
  (`domain.symmetry = "octant"`), porque é cerca de 8 vezes mais rápida e usa 8
  vezes menos memória, sem perda de precisão. A avaliação final da melhor
  solução é sempre feita na esfera inteira, como verificação independente.
- **Validação:** `tests/test_objective.py::test_octant_with_weights_equals_full_sphere`.

## 7. Nenhuma verificação de viabilidade geométrica

- **Sintoma:** o otimizador podia escolher combinações de raio e número de ímãs
  em que os cubos se sobrepõem.
- **Correção:** a classe `HalbachRing` ([geometry.py](../src/halbach_ic/geometry.py))
  é parametrizada por grandezas físicas: raio livre do bore, cubo, número de
  camadas, folga entre camadas e folga entre ímãs. Ela calcula o raio de cada
  camada e o número máximo de ímãs:
  - como o cubo gira junto com a magnetização, no plano xy cada ímã é tratado
    como o círculo circunscrito ao quadrado, de diâmetro d = a√2 (conservador);
  - ímãs vizinhos na mesma camada: corda `2 r sin(π/N) ≥ d + folga`, logo
    `N_max = ⌊π / asin((d + folga) / 2r)⌋`;
  - camadas vizinhas: `Δr = d + folga_entre_camadas`;
  - anéis vizinhos em z (os cubos não giram em torno de x ou y): `Δz ≥ a + folga_axial`;
  - o bore mínimo (bobinas de gradiente e RF) filtra os candidatos.

  Configurações inviáveis geram `InfeasibleGeometryError` na construção.
  Candidatos recusados aparecem em `halbach-ic info`.
- **Observação:** pelo mesmo critério, a geometria original tem folga mínima de
  1,51 mm entre ímãs vizinhos, portanto era viável.
- **Validação:** `tests/test_geometry.py`. O teste
  `test_generated_rings_never_overlap` confere, com o teste exato de sobreposição
  de quadrados girados (teorema do eixo separador), 135 combinações de raio,
  número de camadas e ângulo inicial.

## 8. Sem dependências declaradas, sem testes, configuração no código

- **Correção:**
  - `pyproject.toml` com as dependências, gerenciado por `uv`;
  - todos os parâmetros em [config.toml](../config.toml), lidos e convertidos
    para SI em [config.py](../src/halbach_ic/config.py), com erro para chaves
    desconhecidas;
  - pacote `src/halbach_ic` separado em módulos;
  - testes com pytest (`uv run pytest`), incluindo soluções analíticas, direção
    de B0, geometria e regressão contra o código original.

---

## Outros problemas encontrados

### A. Convenção de sinal da direção do campo (na especificação da IC)

- A especificação dizia: *"se o momento do ímã no ângulo θ aponta na direção
  (kθ + φ), o campo resultante aponta na direção φ; use φ = −π/2 para campo em −y"*.
- **Para k = 2, o campo no centro aponta para −φ, não para +φ.** Dedução: girar
  a estrutura inteira de um ângulo β gira o campo de β. Os ímãs passam a ficar em
  θ' = θ + β com magnetização `2θ + φ + β = 2θ' + (φ − β)`, ou seja, a fase vira
  φ − β. Então, se ψ(φ) é a direção do campo, ψ(φ − β) = ψ(φ) + β, logo
  ψ = −φ + ψ(0). Com φ = 0, o original dá campo em +x, então ψ(0) = 0 e ψ = −φ.
- Consequência: φ = −π/2 daria campo para **cima** (+y).
- **Solução adotada:** o parâmetro de entrada é a **direção desejada de B0**
  (`field.direction_deg = -90`), e o código calcula a fase `φ = −direção`
  (`geometry.magnetization_phase`).
- **Validação:** `tests/test_field_direction.py`:
  `test_phase_convention_is_opposite_to_field_direction` mostra que φ = −π/2 dá
  +y, e `test_vertical_top_to_bottom_is_minus_y` confirma B0 em −y em todo o DSV
  com a configuração do projeto.

### B. Média do octante sem pesos

Ver item 6. Afeta o ppm e o campo médio relatados pelo original.

### C. Eixos da malha trocados em `singleMagnet`

`np.meshgrid(x, y, z)` usa a indexação padrão `'xy'` e devolve arrays com forma
`(Ny, Nx, Nz)`, mas `B0` é criado com forma `(Nx, Ny, Nz)`. Só funciona porque o
domínio original é cúbico. Com dimensões diferentes em x e y, o código quebra
com erro de broadcast. O código novo usa `indexing="ij"` em todo lugar
([domain.py](../src/halbach_ic/domain.py)).

### D. `resolution` com dois significados

No script principal, `resolution = 5` é o espaçamento em mm. Em `halbachFields`,
`resolution` é o número de pontos por metro, e o script converte com `1e3/resolution`.
O código novo usa só `grid_spacing_mm`.

### E. Gráficos do original

- O gráfico de perfil diz "X axis", mas `maskedField[meio, meio, :]` percorre o
  eixo **z**.
- `plt.legend()` é chamado sem nenhuma curva rotulada (só gera um aviso).
- Não há `plt.show()` nem `savefig`: rodando como script, os gráficos não aparecem.
- Faltam títulos, colorbar e unidades nos mapas.

Corrigido em [visualization.py](../src/halbach_ic/visualization.py).

### F. `magnetization()` quebra para outro formato de ímã

Com `shape != 'cube'`, a variável de retorno não é definida e dá
`UnboundLocalError`. O código novo tem o ímã como classe (`MagnetSpec`). Outros
formatos entram junto com o modelo exato na Fase 2.

### G. Comparação de float com zero

`if position == 0` decide se um anel é único (z = 0) ou um par ±z. Funciona por
acaso, porque `linspace` dá exatamente 0.0 no centro. O código novo
(`symmetric_slots`) decide pelo índice.

### H. Pontos de avaliação dentro dos ímãs

O original calcula o campo de dipolo em qualquer ponto da malha, inclusive a
poucos milímetros do centro do cubo (nos cantos da grade de 200 mm, a 6,6 mm do
ímã), onde o modelo não vale e pode haver divisão por zero. O modelo novo recusa
pontos a menos de meia diagonal do cubo (`a√3/2`). Na esfera do DSV isso não
acontece.

### I. Valores repetidos e padrões não usados

O tamanho do cubo (12 mm) aparece em 4 lugares. Os valores padrão de
`createHalbach` (24 ímãs, raio de 145 mm, cubo de 25,4 mm) nunca são usados.
Agora tudo vem do `config.toml`.

### J. Sinal do campo na otimização e no resultado final

A otimização usa Bx com sinal. O resultado final usa |Bx|. As duas coisas são
equivalentes só enquanto Bx > 0 em todo o DSV. O código novo usa sempre a
componente com sinal na direção de B0 e acusa violação se a média for negativa.

### K. Comportamentos mantidos de propósito (não são bugs, mas afetam o resultado)

- **Sem elitismo:** a população inteira é substituída a cada geração, então o
  melhor de uma geração pode ser pior que o da anterior. O original já era
  assim, e ele fica igual para comparar com o original. O melhor global é
  guardado à parte (`HallOfFame`). Elitismo e outros operadores podem ser
  avaliados junto com o NSGA-II (Fase 5).
- **Sem semente:** o original não era reproduzível. O código novo aceita
  `ga.seed` (padrão 0).
- **Homogeneidade de uma componente:** a homogeneidade é medida na componente de
  B na direção de B0, como no original. A frequência de RM depende de |B|, mas a
  diferença é de segunda ordem, porque as componentes transversais são pequenas.
  Isso pode ser reavaliado depois com o modelo exato.
