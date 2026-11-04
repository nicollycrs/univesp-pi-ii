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
| Regressão logística | 0.565 | 0.741 | 0.429 | 0.488 | 0.709 |
| Floresta aleatória | 0.581 | 0.731 | 0.426 | 0.492 | 0.722 |

**Modelo escolhido: Regressão logística.**

A sensibilidade mais alta foi a de Floresta aleatória (0.581 contra 0.565), mas a diferença de 0.016 cabe dentro da tolerância de 0.02 adotada pelo projeto. Em uma única divisão entre treino e teste, diferença dessa ordem é ruído amostral, não desempenho. Havendo empate técnico, vence o modelo interpretável, cujos coeficientes podem ser lidos e defendidos.

### Matriz de confusão do modelo escolhido

```
Regressão logística
  sensibilidade (recall):  0.565
  especificidade:          0.741
  precisao:                0.429
  F1:                      0.488
  AUC ROC:                 0.709
  matriz de confusao:
    verdadeiro negativo   2737   falso positivo    955
    falso negativo         552   verdadeiro positivo    718
```

### Contribuição de cada atributo

Coeficientes da regressão logística, sobre atributos padronizados. O **sinal** diz a direção do efeito e a magnitude diz a força.

| Atributo | Coeficiente |
|---|---|
| taxa_abandono | +0.6899 |
| distorcao_idade_serie | +0.2208 |
| taxa_reprovacao | +0.1168 |
| rural | -0.0895 |
| contexto_socioeconomico | +0.0852 |

## Limites declarados

- A base dispõe de **apenas uma transição entre anos**, de 2023 para 2024. Não é possível validar o modelo em outro par de
  anos, o que seria o teste mais honesto de generalização.
- O rótulo é uma **construção dos autores**, não uma medida oficial de crise
  escolar. Mudar o quantil ou o recorte geográfico muda o problema.
- O modelo prevê **posição relativa dentro da UF**, não valor absoluto de
  abandono, e não deve ser lido como previsão do que acontecerá com estudantes
  individuais.
