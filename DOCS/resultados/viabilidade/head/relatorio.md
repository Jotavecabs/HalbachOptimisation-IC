# Análise de viabilidade — cenário `head`

Gerado em 22/10/2026 15:12. 1681 arranjos simulados em 72 s (modelo de campo: `cuboid`).

Arquivos: figuras em `figuras/`, dados de todos os arranjos em `dados/` (CSV, abre no Excel).

**Sumário:** 1. O que é esta análise · 2. Configuração de referência · 3. Critérios de viabilidade · 4. Como ler os gráficos · 5. Gráficos de linha · 6. Mapas de calor · 7. Massa × homogeneidade · 8. Arranjos viáveis · 9. Limitações

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

## 2. Configuração de referência

Todos os gráficos partem deste arranjo e mudam um ou dois parâmetros de cada vez.

| Parâmetro | Valor |
|---|---|
| Número de anéis | 23 |
| Espaçamento entre anéis | 22 mm |
| Raio livre interno (bore) | 140 mm |
| Camadas de ímãs por anel | 2 |
| Aresta do cubo | 12 mm |
| Remanência Br | 1,3 T |
| Diâmetro do DSV | 200 mm |

| Resultado | Valor |
|---|---|
| Campo B0 no centro | 66,82 mT |
| Inomogeneidade no DSV | 54 112 ppm |
| Massa dos ímãs | 31,89 kg |
| Número de ímãs | 2 461  |
| Comprimento | 496 mm |
| Diâmetro externo | 356 mm |
| Campo por massa | 2,09 mT/kg |
| Frequência de Larmor (¹H) | 2,84 MHz |

### Campo da configuração de referência

![cortes](figuras/referencia_cortes.png)

**O que mostra:** o campo B0 nos três planos centrais do DSV, na mesma escala de cor. **Como ler:** cor uniforme = campo homogêneo. No plano xy (transversal) o campo de um Halbach é quase uniforme. Nos planos que contêm o eixo z (xz e yz) aparece a variação ao longo do comprimento, causada pelas pontas do cilindro. É ela que domina a inomogeneidade quando os anéis são todos iguais.

![perfis](figuras/referencia_perfis.png)

**O que mostra:** o campo ao longo de três retas que passam pelo centro (x, y e z). A linha tracejada é o alvo. Curvas planas = homogêneo. A curva de z mostra o efeito das pontas do cilindro.

## 3. Critérios de viabilidade

Um arranjo é **viável** quando atende a todos estes requisitos (valores do `config.toml`):

* campo no centro entre 49 e 51 mT;
* diâmetro livre (bore) de pelo menos 270 mm (espaço para bobinas de gradiente e RF);
* massa de ímãs de no máximo 40,0 kg;
* a homogeneidade **não** entra no critério (ver seção 9);
* geometria possível: os ímãs não se sobrepõem e o DSV cabe dentro do bore.

## 4. Como ler os gráficos

**Gráficos de linha** (seção 5). Cada figura tem quatro painéis que
compartilham o eixo horizontal (o parâmetro variado):

| Painel | O que mostra | O que é bom |
|---|---|---|
| Campo B0 no centro | campo produzido; faixa cinza = alvo ± tolerância | estar dentro da faixa cinza |
| Inomogeneidade no DSV | variação do campo dentro da esfera, em ppm, **escala log** | quanto menor, melhor |
| Massa dos ímãs | massa de NdFeB; linha vermelha = limite | ficar abaixo da linha |
| Campo por massa | mT obtidos por kg de ímã | quanto maior, mais eficiente |

Cada curva é um valor de um segundo parâmetro (legenda). A linha
**pontilhada vertical** marca o valor da configuração de referência.

**Mapas de calor** (seção 6). Dois parâmetros variam juntos; cada célula é
um arranjo. Os quatro painéis são:

* **campo B0:** a **linha branca contínua** é o caminho dos arranjos que dão
  exatamente o campo alvo e as tracejadas, a tolerância. Qualquer ponto sobre
  a linha branca é um candidato;
* **inomogeneidade:** cores claras = melhor; as linhas pretas marcam 1 000,
  10 000, 100 000 ppm...;
* **massa:** a linha vermelha é o limite de massa;
* **viabilidade:** verde = atende a todos os critérios. Nas outras cores, o
  nome do critério que falha (quando falham vários, aparece o mais grave).

A **estrela** marca a configuração de referência.

Para achar um bom projeto num mapa: siga a linha branca do painel de campo e
procure, ao longo dela, a região mais clara no painel de inomogeneidade que
ainda esteja abaixo da linha vermelha de massa.

## 5. Gráficos de linha: um parâmetro de cada vez

### 5.1 Número de anéis (curvas: camadas de ímãs por anel)

![linha_n_rings_por_n_bands](figuras/linha_n_rings_por_n_bands.png)

**O que varia:** número de anéis de 1 a 45; cada curva é um valor de camadas de ímãs por anel. O resto fica igual à referência.

**Por que acontece:** Mais anéis deixam o cilindro mais comprido. Um cilindro Halbach infinito tem campo perfeitamente uniforme; as imperfeições vêm principalmente das pontas. Com mais anéis as pontas se afastam do DSV: o campo no centro cresce até saturar e a homogeneidade melhora, mas a massa cresce linearmente.

**O que os números mostram:**

* **Camadas de ímãs por anel = 1:** B0 vai de 4,1 a 36,8 mT; fica sempre abaixo do alvo de 50 mT nesta faixa; a melhor homogeneidade é 1 634 ppm, com número de anéis = 45; massa de 0,6 a 29,2 kg.
* **Camadas de ímãs por anel = 2:** B0 vai de 7,2 a 68,9 mT; atinge o alvo de 50 mT em número de anéis ≈ 9; a melhor homogeneidade é 2 044 ppm, com número de anéis = 45; massa de 1,4 a 62,4 kg.
* **Camadas de ímãs por anel = 3:** B0 vai de 9,7 a 97,4 mT; atinge o alvo de 50 mT em número de anéis ≈ 5; a melhor homogeneidade é 2 534 ppm, com número de anéis = 45; massa de 2,2 a 99,7 kg.

### 5.2 Raio livre interno (bore) (curvas: camadas de ímãs por anel)

![linha_bore_radius_mm_por_n_bands](figuras/linha_bore_radius_mm_por_n_bands.png)

**O que varia:** raio livre interno (bore) de 100 mm a 220 mm; cada curva é um valor de camadas de ímãs por anel. O resto fica igual à referência.

**Por que acontece:** Um anel maior comporta mais ímãs (N cresce com o raio), mas cada ímã fica mais longe do centro e o campo de um dipolo cai com 1/r³. O saldo é um campo que cai aproximadamente com 1/r². Em compensação, o DSV fica relativamente menor dentro do anel, o que favorece a homogeneidade no plano transversal.

**O que os números mostram:**

* **Camadas de ímãs por anel = 1:** B0 vai de 21,8 a 47,4 mT; fica sempre abaixo do alvo de 50 mT nesta faixa; a melhor homogeneidade é 40 026 ppm, com raio livre interno (bore) = 125 mm; massa de 11,3 a 23,0 kg; 1 ponto(s) impossível(is) (geometria ou DSV maior que o bore).
* **Camadas de ímãs por anel = 2:** B0 vai de 41,3 a 87,1 mT; atinge o alvo de 50 mT em raio livre interno (bore) ≈ 185,1 mm; a melhor homogeneidade é 45 356 ppm, com raio livre interno (bore) = 125 mm; massa de 24,7 a 48,0 kg; 1 ponto(s) impossível(is) (geometria ou DSV maior que o bore).
* **Camadas de ímãs por anel = 3:** B0 vai de 58,8 a 121,0 mT; fica sempre acima do alvo de 50 mT nesta faixa; a melhor homogeneidade é 50 725 ppm, com raio livre interno (bore) = 120 mm; massa de 40,2 a 75,1 kg; 1 ponto(s) impossível(is) (geometria ou DSV maior que o bore).

### 5.3 Espaçamento entre anéis (curvas: número de anéis)

![linha_ring_spacing_mm_por_n_rings](figuras/linha_ring_spacing_mm_por_n_rings.png)

**O que varia:** espaçamento entre anéis de 13 mm a 40 mm; cada curva é um valor de número de anéis. O resto fica igual à referência.

**Por que acontece:** Com o número de anéis fixo, espaçar mais deixa o ímã mais comprido (pontas mais longe do DSV) mas dilui o material: há menos ímãs por metro, então o campo no centro cai. O espaçamento mínimo é a aresta do cubo mais a folga axial.

**O que os números mostram:**

* **Número de anéis = 11:** B0 vai de 36,1 a 68,3 mT; atinge o alvo de 50 mT em espaçamento entre anéis ≈ 26 mm; a melhor homogeneidade é 100 399 ppm, com espaçamento entre anéis = 40 mm; massa de 15,3 a 15,3 kg.
* **Número de anéis = 17:** B0 vai de 37,5 a 89,5 mT; atinge o alvo de 50 mT em espaçamento entre anéis ≈ 29,4 mm; a melhor homogeneidade é 22 119 ppm, com espaçamento entre anéis = 40 mm; massa de 23,6 a 23,6 kg.
* **Número de anéis = 23:** B0 vai de 37,8 a 101,5 mT; atinge o alvo de 50 mT em espaçamento entre anéis ≈ 30 mm; a melhor homogeneidade é 8 964 ppm, com espaçamento entre anéis = 36 mm; massa de 31,9 a 31,9 kg.
* **Número de anéis = 29:** B0 vai de 37,9 a 108,1 mT; atinge o alvo de 50 mT em espaçamento entre anéis ≈ 30,3 mm; a melhor homogeneidade é 4 264 ppm, com espaçamento entre anéis = 33 mm; massa de 40,2 a 40,2 kg.

### 5.4 Aresta do cubo (curvas: camadas de ímãs por anel)

![linha_magnet_size_mm_por_n_bands](figuras/linha_magnet_size_mm_por_n_bands.png)

**O que varia:** aresta do cubo de 6 mm a 20 mm; cada curva é um valor de camadas de ímãs por anel. O resto fica igual à referência.

**Por que acontece:** Cubos maiores têm momento magnético proporcional a a³, mas cabem menos por anel (N ∝ 1/a). O campo cresce com o tamanho do ímã e a massa também. Cubos grandes também aumentam o erro do modelo de dipolo (ver DOCS/fase2_modelo_de_campo.md); aqui é usado o modelo configurado em viabilidade.toml.

**O que os números mostram:**

* **Camadas de ímãs por anel = 1:** B0 vai de 8,6 a 98,3 mT; atinge o alvo de 50 mT em aresta do cubo ≈ 14,1 mm; a melhor homogeneidade é 44 862 ppm, com aresta do cubo = 6 mm; massa de 3,4 a 44,2 kg.
* **Camadas de ímãs por anel = 2:** B0 vai de 16,4 a 178,2 mT; atinge o alvo de 50 mT em aresta do cubo ≈ 10,3 mm; a melhor homogeneidade é 48 852 ppm, com aresta do cubo = 6 mm; massa de 7,0 a 98,0 kg.

### 5.5 Remanência Br

![linha_remanence_T](figuras/linha_remanence_T.png)

**O que varia:** remanência Br de 1,1 T a 1,45 T. O resto fica igual à referência.

**Por que acontece:** Br é a 'força' do material (N35 ≈ 1,18 T, N42 ≈ 1,30 T, N52 ≈ 1,44 T). O campo é diretamente proporcional a Br e a homogeneidade em ppm NÃO muda, porque ela depende só da geometria. Serve também como verificação do modelo.

**O que os números mostram:**

* **Configuração de referência:** B0 vai de 56,5 a 74,5 mT; fica sempre acima do alvo de 50 mT nesta faixa; a inomogeneidade não muda (54 112 ppm); massa de 31,9 a 31,9 kg.

### 5.6 Diâmetro do DSV (curvas: número de anéis)

![linha_dsv_diameter_mm_por_n_rings](figuras/linha_dsv_diameter_mm_por_n_rings.png)

**O que varia:** diâmetro do DSV de 40 mm a 260 mm; cada curva é um valor de número de anéis. O resto fica igual à referência.

**Por que acontece:** O DSV é a região onde a imagem é feita. O ímã não muda; muda o tamanho da esfera onde a homogeneidade é medida. A inomogeneidade cresce rápido com o diâmetro (os termos de ordem n crescem com rⁿ), então este gráfico mostra até que tamanho de objeto o ímã é útil.

**O que os números mostram:**

* **Número de anéis = 11:** B0 vai de 55,3 a 55,3 mT; fica sempre acima do alvo de 50 mT nesta faixa; a melhor homogeneidade é 19 864 ppm, com diâmetro do DSV = 40 mm; massa de 15,3 a 15,3 kg.
* **Número de anéis = 17:** B0 vai de 63,8 a 63,8 mT; fica sempre acima do alvo de 50 mT nesta faixa; a melhor homogeneidade é 6 237 ppm, com diâmetro do DSV = 40 mm; massa de 23,6 a 23,6 kg.
* **Número de anéis = 23:** B0 vai de 66,8 a 66,8 mT; fica sempre acima do alvo de 50 mT nesta faixa; a melhor homogeneidade é 2 034 ppm, com diâmetro do DSV = 40 mm; massa de 31,9 a 31,9 kg.
* **Número de anéis = 29:** B0 vai de 68,0 a 68,0 mT; fica sempre acima do alvo de 50 mT nesta faixa; a melhor homogeneidade é 736 ppm, com diâmetro do DSV = 40 mm; massa de 40,2 a 40,2 kg.
* **Número de anéis = 35:** B0 vai de 68,5 a 68,5 mT; fica sempre acima do alvo de 50 mT nesta faixa; a melhor homogeneidade é 297 ppm, com diâmetro do DSV = 40 mm; massa de 48,5 a 48,5 kg.

## 6. Mapas de calor: dois parâmetros ao mesmo tempo

### 6.1 Número de anéis × Raio livre interno (bore)

![mapa_n_rings_x_bore_radius_mm](figuras/mapa_n_rings_x_bore_radius_mm.png)

**O que varia:** número de anéis (eixo horizontal, 5 a 45) e raio livre interno (bore) (eixo vertical, 100 mm a 220 mm).

**Por que acontece:** *Número de anéis:* Mais anéis deixam o cilindro mais comprido. Um cilindro Halbach infinito tem campo perfeitamente uniforme; as imperfeições vêm principalmente das pontas. Com mais anéis as pontas se afastam do DSV: o campo no centro cresce até saturar e a homogeneidade melhora, mas a massa cresce linearmente. *Raio livre interno (bore):* Um anel maior comporta mais ímãs (N cresce com o raio), mas cada ímã fica mais longe do centro e o campo de um dipolo cai com 1/r³. O saldo é um campo que cai aproximadamente com 1/r². Em compensação, o DSV fica relativamente menor dentro do anel, o que favorece a homogeneidade no plano transversal.

**O que os números mostram:**

* O campo no centro varia de 15,3 a 88,3 mT no plano analisado.
* 29 de 525 arranjos (5,5 %) ficam dentro de 50 ± 1 mT.
* Menor inomogeneidade do mapa: 1 891 ppm, com número de anéis = 45 e raio livre interno (bore) = 135 mm (B0 = 70,7 mT, 60,1 kg).
* **Melhor arranjo viável:** número de anéis = 21, raio livre interno (bore) = 185 mm → B0 = 49,1 mT, 110 267 ppm, 37,3 kg.
* Classificação: viável 8; campo fora do alvo 169; massa acima do limite 201; bore abaixo do mínimo 126; geometria impossível 21.

### 6.2 Espaçamento entre anéis × Número de anéis

![mapa_ring_spacing_mm_x_n_rings](figuras/mapa_ring_spacing_mm_x_n_rings.png)

**O que varia:** espaçamento entre anéis (eixo horizontal, 13 mm a 40 mm) e número de anéis (eixo vertical, 5 a 41).

**Por que acontece:** *Espaçamento entre anéis:* Com o número de anéis fixo, espaçar mais deixa o ímã mais comprido (pontas mais longe do DSV) mas dilui o material: há menos ímãs por metro, então o campo no centro cai. O espaçamento mínimo é a aresta do cubo mais a folga axial. *Número de anéis:* Mais anéis deixam o cilindro mais comprido. Um cilindro Halbach infinito tem campo perfeitamente uniforme; as imperfeições vêm principalmente das pontas. Com mais anéis as pontas se afastam do DSV: o campo no centro cresce até saturar e a homogeneidade melhora, mas a massa cresce linearmente.

**O que os números mostram:**

* O campo no centro varia de 27,7 a 113,6 mT no plano analisado.
* 19 de 532 arranjos (3,6 %) ficam dentro de 50 ± 1 mT.
* Menor inomogeneidade do mapa: 1 264 ppm, com espaçamento entre anéis = 28 mm e número de anéis = 41 (B0 = 54,2 mT, 56,9 kg).
* **Melhor arranjo viável:** espaçamento entre anéis = 30 mm, número de anéis = 27 → B0 = 50,3 mT, 6 710 ppm, 37,4 kg.
* Classificação: viável 12; campo fora do alvo 324; massa acima do limite 196.

### 6.3 Aresta do cubo × Raio livre interno (bore)

![mapa_magnet_size_mm_x_bore_radius_mm](figuras/mapa_magnet_size_mm_x_bore_radius_mm.png)

**O que varia:** aresta do cubo (eixo horizontal, 6 mm a 20 mm) e raio livre interno (bore) (eixo vertical, 100 mm a 220 mm).

**Por que acontece:** *Aresta do cubo:* Cubos maiores têm momento magnético proporcional a a³, mas cabem menos por anel (N ∝ 1/a). O campo cresce com o tamanho do ímã e a massa também. Cubos grandes também aumentam o erro do modelo de dipolo (ver DOCS/fase2_modelo_de_campo.md); aqui é usado o modelo configurado em viabilidade.toml. *Raio livre interno (bore):* Um anel maior comporta mais ímãs (N cresce com o raio), mas cada ímã fica mais longe do centro e o campo de um dipolo cai com 1/r³. O saldo é um campo que cai aproximadamente com 1/r². Em compensação, o DSV fica relativamente menor dentro do anel, o que favorece a homogeneidade no plano transversal.

**O que os números mostram:**

* O campo no centro varia de 10,0 a 229,6 mT no plano analisado.
* 6 de 375 arranjos (1,6 %) ficam dentro de 50 ± 1 mT.
* Menor inomogeneidade do mapa: 43 372 ppm, com aresta do cubo = 6 mm e raio livre interno (bore) = 130 mm (B0 = 17,7 mT, 6,6 kg).
* **Melhor arranjo viável:** aresta do cubo = 11 mm, raio livre interno (bore) = 155 mm → B0 = 50,8 mT, 63 283 ppm, 28,9 kg.
* Classificação: viável 2; campo fora do alvo 118; massa acima do limite 150; bore abaixo do mínimo 90; geometria impossível 15.

## 7. Compromisso entre massa e homogeneidade

![compromisso](figuras/compromisso_massa_homogeneidade.png)

**O que mostra:** cada ponto é um arranjo dos mapas de calor, posicionado pela massa (horizontal) e pela inomogeneidade (vertical, escala log); a cor é o campo B0. Os pontos com contorno vermelho são os viáveis.

**Como ler:** o canto inferior esquerdo (leve e homogêneo) é o ideal. A borda inferior da nuvem de pontos é a **fronteira de compromisso**: para cada massa, a melhor homogeneidade que esses arranjos alcançam. Para ganhar homogeneidade além dela é preciso mudar o tipo de arranjo (por exemplo, otimizar o raio de cada anel), não só os parâmetros.

## 8. Arranjos viáveis

22 arranjos simulados atendem a todos os critérios. Os 10 mais homogêneos:

| # | Anéis | Espaç. (mm) | Bore Ø (mm) | Camadas | Cubo (mm) | Br (T) | B0 (mT) | Inomog. (ppm) | Massa (kg) | Comprim. (mm) | Ø ext. (mm) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 27 | 30 | 280 | 2 | 12 | 1,30 | 50,3 | 6 710 | 37,4 | 792 | 356 |
| 2 | 25 | 30 | 280 | 2 | 12 | 1,30 | 50,2 | 9 566 | 34,7 | 732 | 356 |
| 3 | 23 | 30 | 280 | 2 | 12 | 1,30 | 50,1 | 14 064 | 31,9 | 672 | 356 |
| 4 | 21 | 30 | 280 | 2 | 12 | 1,30 | 49,8 | 21 295 | 29,1 | 612 | 356 |
| 5 | 19 | 30 | 280 | 2 | 12 | 1,30 | 49,5 | 33 154 | 26,3 | 552 | 356 |
| 6 | 23 | 22 | 280 | 1 | 14 | 1,30 | 49,1 | 48 424 | 20,8 | 498 | 320 |
| 7 | 17 | 30 | 280 | 2 | 12 | 1,30 | 49,0 | 52 928 | 23,6 | 492 | 356 |
| 8 | 17 | 29 | 280 | 2 | 12 | 1,30 | 50,6 | 60 484 | 23,6 | 476 | 356 |
| 9 | 23 | 22 | 310 | 2 | 11 | 1,30 | 50,8 | 63 283 | 28,9 | 495 | 380 |
| 10 | 23 | 22 | 320 | 2 | 11 | 1,30 | 49,0 | 66 467 | 29,6 | 495 | 390 |

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
* **Critério de homogeneidade:** por padrão a homogeneidade **não entra** no
  critério de viabilidade, porque com anéis iguais nenhum arranjo chegaria a
  valores típicos de imagem. Para usar um limite, defina `ppm_maximo` no
  `viabilidade.toml`.
