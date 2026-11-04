# Identidade visual

Este arquivo registra as decisões de identidade do EducaAlerta e a razão de cada
uma. Toda escolha aqui tem uma restrição por trás, e nenhuma é puramente
estética: a interface precisa continuar atendendo à WCAG 2.1 nível AA.

---

## 1. O símbolo

![marca](../painel/static/painel/favicon.png)

Uma linha que **desce, hesita e dispara para cima**, com um ponto cheio marcando
o instante em que o painel aponta o risco, antes do topo.

É a tese do projeto desenhada. O produto não existe para constatar que a escola
entrou em crise, e sim para apontar antes: o grupo **Deterioração** da matriz de
decisão é exatamente a escola que vai bem hoje e que o modelo aponta para o ano
seguinte. O ponto fica onde a curva ainda está subindo, não no pico.

Arquivos:

| Arquivo | Uso |
|---|---|
| `painel/static/painel/marca.svg` | Ícone da aba e referência da geometria |
| `painel/static/painel/favicon.png` | Alternativa para navegador sem ícone SVG |
| Embutido em `base.html` | Assinatura no cabeçalho, herda a cor do CSS |

O SVG do cabeçalho é **embutido no HTML**, e não carregado como `<img>`. Dois
motivos: ele herda a cor das variáveis do CSS, e não custa uma requisição extra
no primeiro acesso, que no plano gratuito já é lento por causa da hibernação.

---

## 2. A cor

**A marca não tem cor própria. Usa o azul `#1D4ED8`, que já estava na paleta.**

Essa é uma decisão, não economia. No painel, vermelho, âmbar e verde carregam
significado: são níveis de risco. Uma marca colorida competiria com eles e, pior,
poderia ser lida como mais um estado. O azul é a cor institucional do sistema,
usada em links, foco e série neutra de gráfico, e é o único lugar onde a cor não
significa risco.

Benefício prático: nenhuma cor nova entrou na superfície que os testes de
contraste precisam cobrir. A paleta validada continua sendo exatamente a de
`painel/cores.py`, e um teste falha se o `marca.svg` divergir dela.

| Papel | Valor | Onde |
|---|---|---|
| Marca e sistema | `#1D4ED8` | Símbolo, links, foco, série neutra |
| Texto | `#1F2937` | Corpo e nome da marca |
| Texto secundário | `#4B5563` | Apoio, legendas |
| Risco alto | `#7F1D1D` sobre `#FEE2E2` | Tarjas e cartões |
| Risco médio | `#713F12` sobre `#FEF3C7` | Tarjas e cartões |
| Risco baixo | `#14532D` sobre `#DCFCE7` | Tarjas e cartões |

---

## 3. O nome

**EducaAlerta**, escrito junto, com peso tipográfico separando as duas metades:
`Educa` em peso normal, **`Alerta`** em peso 800.

A separação é por **peso, não por cor**. Se fosse por cor, a distinção sumiria
para quem não a percebe, e a marca passaria a depender de um recurso que o
projeto proíbe para informação (critério 1.4.1). Peso funciona em qualquer
condição, inclusive impressa em preto e branco.

O nome é sempre **texto**, nunca imagem: continua selecionável, cresce com o
zoom do navegador e é lido por leitor de tela. O símbolo ao lado leva
`aria-hidden`, porque anunciar os dois seria repetição.

---

## 4. Tipografia

Pilha de fontes do sistema, sem webfont:

```
ui-sans-serif, system-ui, -apple-system, "Segoe UI Variable Text",
"Segoe UI", Roboto, "Helvetica Neue", sans-serif
```

Não há fonte externa de propósito. Uma webfont adicionaria uma requisição
bloqueante a um serviço de terceiros em uma aplicação que já sofre com
hibernação no plano gratuito, e traria uma dependência de rede para algo que o
sistema operacional resolve bem. O caráter vem da **escala**, não do desenho da
fonte:

- título com escala fluida (`clamp`) e espaçamento de letra negativo;
- números sempre em `tabular-nums`, para as colunas alinharem;
- entrelinha de 1,65 no corpo e 1,15 no título.

---

## 5. Forma e profundidade

| Token | Valor | Uso |
|---|---|---|
| `--raio` | 10px | Cartões, tabelas, blocos |
| `--raio-pequeno` | 6px | Campos, botões, links do menu |
| `--raio-pilula` | 999px | Tarjas de risco e barras |
| `--sombra-leve` / `--sombra` / `--sombra-alta` | preto translúcido | Elevação |

A profundidade vem de **sombras pretas translúcidas**, não de cores cinzas
adicionais. A página recebe o cinza da paleta e os blocos vêm em branco por
cima; é a separação entre figura e fundo que dá relevo, sem ampliar a superfície
de cor a validar.

Movimento é discreto e some sob `prefers-reduced-motion`: cartões da matriz
sobem 2px no foco do mouse, botões afundam no clique, transições de 140ms.

---

## 6. O que a identidade não faz

- **Não usa cor sozinha para informar.** Toda tarja traz o rótulo em texto.
- **Não usa imagem para texto.** Nome e números são sempre texto real.
- **Não introduz cor fora de `painel/cores.py`.** Há teste que falha se o CSS ou
  o `marca.svg` divergirem da paleta validada.
- **Não depende de serviço externo** para fonte ou ícone.
