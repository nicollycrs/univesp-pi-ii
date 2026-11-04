# Validação do modelo contra 2025 observado

Gerado por `manage.py validar_modelo`. Previsões feitas a partir dos indicadores de **2024**, confrontadas com o que o INEP publicou para **2025**.

## Por que esta validação vale mais que a do treino

A partição de teste usada no treino separa linhas do **mesmo par de anos**: ela mede se o modelo generaliza para outras escolas, não para outro tempo. Aqui o ano observado é posterior a tudo que o modelo viu, e nenhuma linha dele participou do ajuste. É a pergunta que o projeto promete responder: o modelo acerta o futuro, ou apenas descreve bem o passado de onde saiu?

## Base

- Escolas com previsão: **20.073**
- Escolas observadas em 2025: **20.594**
- Cruzamento validado: **19.889**

## Resultado

| Métrica | Teste do treino | **Observado em 2025** |
|---|---|---|
| Sensibilidade | 0,581 | **0,562** |
| Especificidade | 0,735 | **0,743** |
| Precisão | 0,430 | **0,423** |
| AUC ROC | 0,726 | **0,697** |

```
verdadeiro negativo  11073   falso positivo   3823
falso negativo        2187   verdadeiro positivo   2806
```

O desempenho **se sustentou fora do tempo de treino**. A queda é pequena e na direção esperada, e a especificidade até subiu. O alerta do painel encontra pouco mais da metade das escolas que de fato foram para o quartil superior de abandono, que era exatamente o que a partição de teste prometia.

## O cuidado com empates, e por que ele muda o número

O abandono **caiu** de 2024 para 2025: a média foi de 3,54% para 2,58%, e a fatia de escolas com abandono zero subiu de 29,9% para 38,5%. Com a distribuição comprimida perto de zero, o corte do quartil passou a cair em cima de valores empatados.

| Rótulo | Positivos | Sensibilidade | Especificidade | AUC |
|---|---|---|---|---|
| Por posto (adotado) | 25,0% | 0,562 | 0,743 | 0,697 |
| Regra literal | 33,7% | 0,499 | 0,750 | 0,626 |

A regra literal (`taxa >= quantil`) era adequada no treino, onde apenas 0,9% das escolas ficavam exatamente no corte. Em 2025 isso saltou para 9,8%, e em duas unidades federativas o próprio corte virou zero, o que promoveria a positiva toda escola sem nenhum abandono. Os positivos subiriam a 33,7%, contra 25,6% no treino, e a comparação deixaria de ser justa.

Por isso a validação adota o corte **por posto**, que toma sempre o quarto superior e desempata pela ordem de aparição. As duas linhas estão na tabela: a queda aparente de AUC para 0,626 é artefato do empate, não degradação do modelo.

## O que isto não prova

- Uma única transição validada. Dois anos observados dariam uma leitura   mais firme sobre estabilidade.
- O rótulo continua sendo uma construção dos autores, e não uma medida   oficial de crise escolar.
- O modelo prevê posição relativa dentro da unidade federativa, não   valor absoluto de abandono, e nada sobre estudantes individuais.
