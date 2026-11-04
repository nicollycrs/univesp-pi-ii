# Avaliação do modelo preditivo

Gerado por `manage.py treinar_modelo`. Versão `modelo-v1`.

## Desenho do problema

- **Atributos:** indicadores da escola em **2023**
- **Alvo:** a escola está no quartil superior de abandono da sua UF em **2024**
- **Escolas com os dois anos completos:** 19848
- **Casos positivos:** 5080 (25.6%)
- **Atributos usados:** taxa_abandono, taxa_reprovacao, distorcao_idade_serie, contexto_socioeconomico, rural
- **Divisão treino e teste:** 75% e 25%, estratificada, semente 42

O quartil é calculado **dentro de cada unidade federativa**. Comparar
escolas de estados diferentes na mesma escala mediria sobretudo a diferença
entre os estados, e não o risco relativo da escola no contexto em que opera.

## Por que não acurácia

Bowers, Sprott e Taff (2013) mostram que indicadores de evasão devem ser
avaliados por precisão, sensibilidade e especificidade. Em base desbalanceada,
a acurácia engana: classificar todas as escolas como sem risco acertaria cerca
de 74% dos casos e não encontraria nenhuma escola em risco.

## Resultados

| Modelo | Sensibilidade | Especificidade | Precisão | F1 | AUC ROC |
|---|---|---|---|---|---|
| Regressão logística | 0.558 | 0.748 | 0.432 | 0.487 | 0.718 |
| Floresta aleatória | 0.581 | 0.735 | 0.430 | 0.494 | 0.726 |

**Modelo escolhido: Floresta aleatória.** O critério foi a maior sensibilidade.
Encontrar a escola que vai piorar importa mais do que evitar o alarme falso:
o custo de olhar uma escola que estava bem é baixo; o de não olhar uma que
piorou, alto.

### Matriz de confusão do modelo escolhido

```
Floresta aleatória
  sensibilidade (recall):  0.581
  especificidade:          0.735
  precisao:                0.430
  F1:                      0.494
  AUC ROC:                 0.726
  matriz de confusao:
    verdadeiro negativo   2715   falso positivo    977
    falso negativo         532   verdadeiro positivo    738
```

### Contribuição de cada atributo

Importância de atributo da floresta aleatória. É sempre positiva e mede o quanto o atributo foi usado para separar os casos, **não** a direção do efeito. Não se lê como coeficiente de regressão.

| Atributo | Importância |
|---|---|
| taxa_abandono | 0.4562 |
| distorcao_idade_serie | 0.2635 |
| taxa_reprovacao | 0.1546 |
| contexto_socioeconomico | 0.1151 |
| rural | 0.0106 |

## Limites declarados

- A base dispõe de **apenas uma transição entre anos**, de 2023 para 2024. Não é possível validar o modelo em outro par de
  anos, o que seria o teste mais honesto de generalização.
- O rótulo é uma **construção dos autores**, não uma medida oficial de crise
  escolar. Mudar o quantil ou o recorte geográfico muda o problema.
- O modelo prevê **posição relativa dentro da UF**, não valor absoluto de
  abandono, e não deve ser lido como previsão do que acontecerá com estudantes
  individuais.
