# Qualidade dos dados

Relatório das decisões de limpeza do ETL e do que elas descartam. Vira seção de
metodologia do relatório acadêmico: um trabalho de ciência de dados precisa
declarar o que jogou fora e por quê.

---

## Como gerar este relatório

A função `etl.transformar.transformar()` devolve um objeto `Relatorio` com todas
as contagens. Para produzir o texto:

```python
import pandas as pd
from etl.transformar import transformar

bruto = pd.read_excel("dados_brutos/taxas_rendimento_2024.xlsx", skiprows=8)
limpo, rel = transformar(bruto, ano=2024, redes=("estadual",))
print(rel.resumo())
limpo.to_csv("dados_processados/indicadores.csv", index=False)
```

---

## Regras de limpeza aplicadas

| Regra | O que faz | Por quê |
|---|---|---|
| Código de escola inválido | Descarta a linha | Sem a chave não há como ligar o indicador a uma escola |
| UF fora da lista oficial | Descarta a linha | Pega lixo como `XX`, que passaria por um teste de "duas letras" |
| Vírgula decimal | Converte para ponto | Os arquivos do INEP usam formato brasileiro |
| Marcadores `--`, `-`, `ND` | Convertem para ausente | São os marcadores de indisponível do INEP |
| Taxa fora de 0 a 100 | **Anula o valor**, mantém a linha | Uma distorção de 180% não existe. Anular evita contaminar a média do painel sem ninguém perceber. A linha fica, porque os outros indicadores dela continuam válidos |
| Código de escola duplicado | Mantém o primeiro | Uma escola por ano, garantido também pela restrição no banco |
| Linha sem nenhum indicador | Descarta | Não serve para calcular risco |
| Fora do recorte de rede | Descarta | Recorte metodológico declarado |

A decisão mais relevante é a de **anular em vez de descartar** valores fora de
faixa. Descartar a linha inteira perderia indicadores válidos da mesma escola;
manter o valor absurdo estragaria as médias. Anular preserva o que é utilizável e
deixa o resto explicitamente ausente.

## Como o índice lida com ausentes

Um componente ausente não elimina a escola do ranking: o peso dele é
redistribuído proporcionalmente entre os componentes disponíveis, e o score
continua na escala de 0 a 1. Só fica sem índice a escola que não tem nenhum dos
quatro indicadores.

Isso tem uma consequência que precisa ser dita no relatório: escolas com poucos
indicadores disponíveis têm score calculado sobre base menor, e portanto menos
robusto. A contagem de ausentes por coluna, no relatório do ETL, é o que permite
avaliar o tamanho desse efeito.

---

## Registro das cargas

Preencher a cada carga de dados reais.

| Data | Arquivo | Ano | Lidas | Válidas | Principais descartes |
|---|---|---|---|---|---|
| | | | | | |

### Carga de amostra em 23/09/2026 (não é dado real)

| Data | Arquivo | Anos | Linhas | Escolas | Índices calculados |
|---|---|---|---|---|---|
| 23/09/2026 | `AMOSTRA_DESENVOLVIMENTO.csv` | 2023 e 2024 | 800 | 400 | 800 (272 alto, 266 médio, 262 baixo) |

Registrado para rastreabilidade do desenvolvimento. **Não são dados reais e não
devem aparecer como resultado no relatório.**
