# Análise de viabilidade — cenário `head`

Gerado em 22/10/2026 15:27. 1914 arranjos simulados em 53 s (modelo de campo: `cuboid`).

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
| Número de anéis | 47 |
| Espaçamento entre anéis | 16 mm |
| Raio livre interno (bore) | 140 mm |
| Camadas de ímãs por anel | 1 |
| Aresta do cubo | 12 mm |
| Remanência Br | 1,3 T |
| Diâmetro do DSV | 200 mm |

| Resultado | Valor |
|---|---|
| Campo B0 no centro | 50,31 mT |
| Inomogeneidade no DSV | 7 098 ppm |
| Homogeneidade | 99,29 % |
| Massa dos ímãs | 30,46 kg |
| Número de ímãs | 2 350  |
| Comprimento | 748 mm |
| Diâmetro externo | 314 mm |
| Campo por massa | 1,65 mT/kg |
| Frequência de Larmor (¹H) | 2,14 MHz |

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
* comprimento entre 54 e 76 cm;
* a **homogeneidade é o objetivo**, não um corte: entre os arranjos que atendem aos requisitos acima, o melhor é o mais próximo de 100 % (seção 8);
* geometria possível: os ímãs não se sobrepõem e o DSV cabe dentro do bore.

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

## 5. Gráficos de linha: um parâmetro de cada vez

### 5.1 Número de anéis (curvas: camadas de ímãs por anel)

![linha_n_rings_por_n_bands](figuras/linha_n_rings_por_n_bands.png)

**O que varia:** número de anéis de 1 a 61; cada curva é um valor de camadas de ímãs por anel. O resto fica igual à referência.

**Por que acontece:** Mais anéis deixam o cilindro mais comprido. Um cilindro Halbach infinito tem campo perfeitamente uniforme; as imperfeições vêm principalmente das pontas. Com mais anéis as pontas se afastam do DSV: o campo no centro cresce até saturar e a homogeneidade melhora, mas a massa cresce linearmente.

**O que os números mostram:**

* **Camadas de ímãs por anel = 1:** B0 vai de 4,1 a 50,5 mT; atinge o alvo de 50 mT em número de anéis ≈ 39; a melhor homogeneidade é 99,83 % (1 729 ppm), com número de anéis = 61; massa de 0,6 a 39,5 kg.
* **Camadas de ímãs por anel = 2:** B0 vai de 7,2 a 94,7 mT; atinge o alvo de 50 mT em número de anéis ≈ 7; a melhor homogeneidade é 99,78 % (2 189 ppm), com número de anéis = 61; massa de 1,4 a 84,6 kg.
* **Camadas de ímãs por anel = 3:** B0 vai de 9,7 a 133,9 mT; atinge o alvo de 50 mT em número de anéis ≈ 5; a melhor homogeneidade é 99,73 % (2 721 ppm), com número de anéis = 61; massa de 2,2 a 135,2 kg.

### 5.2 Raio livre interno (bore) (curvas: camadas de ímãs por anel)

![linha_bore_radius_mm_por_n_bands](figuras/linha_bore_radius_mm_por_n_bands.png)

**O que varia:** raio livre interno (bore) de 100 mm a 220 mm; cada curva é um valor de camadas de ímãs por anel. O resto fica igual à referência.

**Por que acontece:** Um anel maior comporta mais ímãs (N cresce com o raio), mas cada ímã fica mais longe do centro e o campo de um dipolo cai com 1/r³. O saldo é um campo que cai aproximadamente com 1/r². Em compensação, o DSV fica relativamente menor dentro do anel, o que favorece a homogeneidade no plano transversal.

**O que os números mostram:**

* **Camadas de ímãs por anel = 1:** B0 vai de 32,0 a 65,8 mT; atinge o alvo de 50 mT em raio livre interno (bore) ≈ 141,1 mm; a melhor homogeneidade é 99,49 % (5 136 ppm), com raio livre interno (bore) = 125 mm; massa de 23,1 a 46,9 kg; 1 ponto(s) impossível(is) (geometria ou DSV maior que o bore).
* **Camadas de ímãs por anel = 2:** B0 vai de 60,9 a 121,1 mT; fica sempre acima do alvo de 50 mT nesta faixa; a melhor homogeneidade é 99,36 % (6 408 ppm), com raio livre interno (bore) = 125 mm; massa de 50,6 a 98,1 kg; 1 ponto(s) impossível(is) (geometria ou DSV maior que o bore).
* **Camadas de ímãs por anel = 3:** B0 vai de 87,4 a 168,8 mT; fica sempre acima do alvo de 50 mT nesta faixa; a melhor homogeneidade é 99,24 % (7 561 ppm), com raio livre interno (bore) = 120 mm; massa de 82,2 a 153,5 kg; 1 ponto(s) impossível(is) (geometria ou DSV maior que o bore).

### 5.3 Espaçamento entre anéis (curvas: número de anéis)

![linha_ring_spacing_mm_por_n_rings](figuras/linha_ring_spacing_mm_por_n_rings.png)

**O que varia:** espaçamento entre anéis de 13 mm a 40 mm; cada curva é um valor de número de anéis. O resto fica igual à referência.

**Por que acontece:** Com o número de anéis fixo, espaçar mais deixa o ímã mais comprido (pontas mais longe do DSV) mas dilui o material: há menos ímãs por metro, então o campo no centro cai. O espaçamento mínimo é a aresta do cubo mais a folga axial.

**O que os números mostram:**

* **Número de anéis = 31:** B0 vai de 20,2 a 59,0 mT; atinge o alvo de 50 mT em espaçamento entre anéis ≈ 15,7 mm; a melhor homogeneidade é 99,63 % (3 689 ppm), com espaçamento entre anéis = 30 mm; massa de 20,1 a 20,1 kg.
* **Número de anéis = 39:** B0 vai de 20,3 a 60,7 mT; atinge o alvo de 50 mT em espaçamento entre anéis ≈ 16 mm; a melhor homogeneidade é 99,84 % (1 599 ppm), com espaçamento entre anéis = 27 mm; massa de 25,3 a 25,3 kg.
* **Número de anéis = 47:** B0 vai de 20,3 a 61,5 mT; atinge o alvo de 50 mT em espaçamento entre anéis ≈ 16,1 mm; a melhor homogeneidade é 99,921 % (788 ppm), com espaçamento entre anéis = 26 mm; massa de 30,5 a 30,5 kg.
* **Número de anéis = 55:** B0 vai de 20,3 a 61,8 mT; atinge o alvo de 50 mT em espaçamento entre anéis ≈ 16,2 mm; a melhor homogeneidade é 99,954 % (463 ppm), com espaçamento entre anéis = 24 mm; massa de 35,6 a 35,6 kg.

### 5.4 Aresta do cubo (curvas: camadas de ímãs por anel)

![linha_magnet_size_mm_por_n_bands](figuras/linha_magnet_size_mm_por_n_bands.png)

**O que varia:** aresta do cubo de 6 mm a 20 mm; cada curva é um valor de camadas de ímãs por anel. O resto fica igual à referência.

**Por que acontece:** Cubos maiores têm momento magnético proporcional a a³, mas cabem menos por anel (N ∝ 1/a). O campo cresce com o tamanho do ímã e a massa também. Cubos grandes também aumentam o erro do modelo de dipolo (ver DOCS/fase2_modelo_de_campo.md); aqui é usado o modelo configurado em viabilidade.toml.

**O que os números mostram:**

* **Camadas de ímãs por anel = 1:** B0 vai de 12,0 a 78,3 mT; atinge o alvo de 50 mT em aresta do cubo ≈ 12 mm; a melhor homogeneidade é 99,34 % (6 576 ppm), com aresta do cubo = 6 mm; massa de 6,9 a 48,8 kg; 5 ponto(s) impossível(is) (geometria ou DSV maior que o bore).
* **Camadas de ímãs por anel = 2:** B0 vai de 23,1 a 145,2 mT; atinge o alvo de 50 mT em aresta do cubo ≈ 8,72 mm; a melhor homogeneidade é 99,25 % (7 472 ppm), com aresta do cubo = 6 mm; massa de 14,3 a 105,9 kg; 5 ponto(s) impossível(is) (geometria ou DSV maior que o bore).

### 5.5 Remanência Br

![linha_remanence_T](figuras/linha_remanence_T.png)

**O que varia:** remanência Br de 1,1 T a 1,45 T. O resto fica igual à referência.

**Por que acontece:** Br é a 'força' do material (N35 ≈ 1,18 T, N42 ≈ 1,30 T, N52 ≈ 1,44 T). O campo é diretamente proporcional a Br e a homogeneidade em ppm NÃO muda, porque ela depende só da geometria. Serve também como verificação do modelo.

**O que os números mostram:**

* **Configuração de referência:** B0 vai de 42,6 a 56,1 mT; atinge o alvo de 50 mT em remanência Br ≈ 1,29 T; a inomogeneidade não muda (7 098 ppm); massa de 30,5 a 30,5 kg.

### 5.6 Diâmetro do DSV (curvas: número de anéis)

![linha_dsv_diameter_mm_por_n_rings](figuras/linha_dsv_diameter_mm_por_n_rings.png)

**O que varia:** diâmetro do DSV de 40 mm a 260 mm; cada curva é um valor de número de anéis. O resto fica igual à referência.

**Por que acontece:** O DSV é a região onde a imagem é feita. O ímã não muda; muda o tamanho da esfera onde a homogeneidade é medida. A inomogeneidade cresce rápido com o diâmetro (os termos de ordem n crescem com rⁿ), então este gráfico mostra até que tamanho de objeto o ímã é útil.

**O que os números mostram:**

* **Número de anéis = 23:** B0 vai de 47,2 a 47,2 mT; fica sempre abaixo do alvo de 50 mT nesta faixa; a melhor homogeneidade é 99,39 % (6 093 ppm), com diâmetro do DSV = 40 mm; massa de 14,9 a 14,9 kg.
* **Número de anéis = 35:** B0 vai de 49,7 a 49,7 mT; fica sempre abaixo do alvo de 50 mT nesta faixa; a melhor homogeneidade é 99,89 % (1 133 ppm), com diâmetro do DSV = 40 mm; massa de 22,7 a 22,7 kg.
* **Número de anéis = 47:** B0 vai de 50,3 a 50,3 mT; fica sempre acima do alvo de 50 mT nesta faixa; a melhor homogeneidade é 99,973 % (274 ppm), com diâmetro do DSV = 40 mm; massa de 30,5 a 30,5 kg.
* **Número de anéis = 59:** B0 vai de 50,5 a 50,5 mT; fica sempre acima do alvo de 50 mT nesta faixa; a melhor homogeneidade é 99,9917 % (83 ppm), com diâmetro do DSV = 40 mm; massa de 38,2 a 38,2 kg.

## 6. Mapas de calor: dois parâmetros ao mesmo tempo

### 6.1 Número de anéis × Raio livre interno (bore)

![mapa_n_rings_x_bore_radius_mm](figuras/mapa_n_rings_x_bore_radius_mm.png)

**O que varia:** número de anéis (eixo horizontal, 15 a 61) e raio livre interno (bore) (eixo vertical, 100 mm a 220 mm).

**Por que acontece:** *Número de anéis:* Mais anéis deixam o cilindro mais comprido. Um cilindro Halbach infinito tem campo perfeitamente uniforme; as imperfeições vêm principalmente das pontas. Com mais anéis as pontas se afastam do DSV: o campo no centro cresce até saturar e a homogeneidade melhora, mas a massa cresce linearmente. *Raio livre interno (bore):* Um anel maior comporta mais ímãs (N cresce com o raio), mas cada ímã fica mais longe do centro e o campo de um dipolo cai com 1/r³. O saldo é um campo que cai aproximadamente com 1/r². Em compensação, o DSV fica relativamente menor dentro do anel, o que favorece a homogeneidade no plano transversal.

**O que os números mostram:**

* O campo no centro varia de 21,3 a 65,9 mT no plano analisado.
* 31 de 600 arranjos (5,2 %) ficam dentro de 50 ± 1 mT.
* Melhor homogeneidade do mapa: 99,86 % (1 366 ppm), com número de anéis = 61 e raio livre interno (bore) = 125 mm (B0 = 56,3 mT, 35,6 kg).
* **Melhor arranjo viável:** número de anéis = 47, raio livre interno (bore) = 140 mm → B0 = 50,3 mT, homogeneidade 99,29 % (7 098 ppm), 30,5 kg, 74,8 cm.
* Classificação: viável 7; campo fora do alvo 100; comprimento fora da faixa 218; massa acima do limite 107; bore abaixo do mínimo 144; geometria impossível 24.

### 6.2 Espaçamento entre anéis × Número de anéis

![mapa_ring_spacing_mm_x_n_rings](figuras/mapa_ring_spacing_mm_x_n_rings.png)

**O que varia:** espaçamento entre anéis (eixo horizontal, 13 mm a 40 mm) e número de anéis (eixo vertical, 15 a 61).

**Por que acontece:** *Espaçamento entre anéis:* Com o número de anéis fixo, espaçar mais deixa o ímã mais comprido (pontas mais longe do DSV) mas dilui o material: há menos ímãs por metro, então o campo no centro cai. O espaçamento mínimo é a aresta do cubo mais a folga axial. *Número de anéis:* Mais anéis deixam o cilindro mais comprido. Um cilindro Halbach infinito tem campo perfeitamente uniforme; as imperfeições vêm principalmente das pontas. Com mais anéis as pontas se afastam do DSV: o campo no centro cresce até saturar e a homogeneidade melhora, mas a massa cresce linearmente.

**O que os números mostram:**

* O campo no centro varia de 20,0 a 62,0 mT no plano analisado.
* 20 de 672 arranjos (3,0 %) ficam dentro de 50 ± 1 mT.
* Melhor homogeneidade do mapa: 99,967 % (335 ppm), com espaçamento entre anéis = 23 mm e número de anéis = 61 (B0 = 35,2 mT, 39,5 kg).
* **Melhor arranjo viável:** espaçamento entre anéis = 16 mm, número de anéis = 47 → B0 = 50,3 mT, homogeneidade 99,29 % (7 098 ppm), 30,5 kg, 74,8 cm.
* Classificação: viável 7; campo fora do alvo 124; comprimento fora da faixa 541.

### 6.3 Aresta do cubo × Raio livre interno (bore)

![mapa_magnet_size_mm_x_bore_radius_mm](figuras/mapa_magnet_size_mm_x_bore_radius_mm.png)

**O que varia:** aresta do cubo (eixo horizontal, 6 mm a 20 mm) e raio livre interno (bore) (eixo vertical, 100 mm a 220 mm).

**Por que acontece:** *Aresta do cubo:* Cubos maiores têm momento magnético proporcional a a³, mas cabem menos por anel (N ∝ 1/a). O campo cresce com o tamanho do ímã e a massa também. Cubos grandes também aumentam o erro do modelo de dipolo (ver DOCS/fase2_modelo_de_campo.md); aqui é usado o modelo configurado em viabilidade.toml. *Raio livre interno (bore):* Um anel maior comporta mais ímãs (N cresce com o raio), mas cada ímã fica mais longe do centro e o campo de um dipolo cai com 1/r³. O saldo é um campo que cai aproximadamente com 1/r². Em compensação, o DSV fica relativamente menor dentro do anel, o que favorece a homogeneidade no plano transversal.

**O que os números mostram:**

* O campo no centro varia de 7,6 a 100,9 mT no plano analisado.
* 6 de 375 arranjos (1,6 %) ficam dentro de 50 ± 1 mT.
* Melhor homogeneidade do mapa: 99,50 % (5 029 ppm), com aresta do cubo = 10 mm e raio livre interno (bore) = 125 mm (B0 = 39,1 mT, 18,7 kg).
* **Melhor arranjo viável:** aresta do cubo = 12 mm, raio livre interno (bore) = 140 mm → B0 = 50,3 mT, homogeneidade 99,29 % (7 098 ppm), 30,5 kg, 74,8 cm.
* Classificação: viável 1; campo fora do alvo 123; massa acima do limite 56; bore abaixo do mínimo 60; geometria impossível 135.

## 7. Compromisso entre massa e homogeneidade

![compromisso](figuras/compromisso_massa_homogeneidade.png)

**O que mostra:** cada ponto é um arranjo dos mapas de calor, posicionado pela massa (horizontal) e pela inomogeneidade (vertical, escala log); a cor é o campo B0. Os pontos com contorno vermelho são os viáveis.

**Como ler:** o canto inferior esquerdo (leve e homogêneo) é o ideal. A borda inferior da nuvem de pontos é a **fronteira de compromisso**: para cada massa, a melhor homogeneidade que esses arranjos alcançam. Para ganhar homogeneidade além dela é preciso mudar o tipo de arranjo (por exemplo, otimizar o raio de cada anel), não só os parâmetros.

## 8. Arranjos viáveis

14 arranjos simulados atendem a todos os requisitos (homogeneidade medida no DSV de 200 mm do cenário). Como a homogeneidade é o objetivo (quanto mais perto de 100 %, melhor), eles estão ordenados por ela. Os 10 melhores:

| # | Anéis | Espaç. (mm) | Bore Ø (mm) | Camadas | Cubo (mm) | Br (T) | B0 (mT) | Homogeneidade | Inomog. (ppm) | Massa (kg) | Comprim. (cm) | Ø ext. (mm) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 47 | 16 | 280 | 1 | 12 | 1,30 | 50,3 | 99,29 % | 7 098 | 30,5 | 74,8 | 314 |
| 2 | 46 | 16 | 280 | 1 | 12 | 1,30 | 50,3 | 99,21 % | 7 938 | 29,8 | 73,2 | 314 |
| 3 | 45 | 16 | 280 | 1 | 12 | 1,30 | 50,3 | 99,11 % | 8 893 | 29,2 | 71,6 | 314 |
| 4 | 44 | 16 | 280 | 1 | 12 | 1,30 | 50,2 | 99,00 % | 9 977 | 28,5 | 70,0 | 314 |
| 5 | 43 | 16 | 280 | 1 | 12 | 1,30 | 50,2 | 98,88 % | 11 212 | 27,9 | 68,4 | 314 |
| 6 | 42 | 16 | 280 | 1 | 12 | 1,30 | 50,1 | 98,74 % | 12 620 | 27,2 | 66,8 | 314 |
| 7 | 41 | 16 | 280 | 1 | 12 | 1,30 | 50,1 | 98,58 % | 14 230 | 26,6 | 65,2 | 314 |
| 8 | 40 | 16 | 280 | 1 | 12 | 1,30 | 50,0 | 98,39 % | 16 071 | 25,9 | 63,6 | 314 |
| 9 | 39 | 16 | 280 | 1 | 12 | 1,30 | 50,0 | 98,18 % | 18 183 | 25,3 | 62,0 | 314 |
| 10 | 38 | 16 | 280 | 1 | 12 | 1,30 | 49,9 | 97,94 % | 20 607 | 24,6 | 60,4 | 314 |

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
