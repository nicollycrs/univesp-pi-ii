# Fontes de dados

Este arquivo é a prestação de contas do projeto sobre a origem dos dados. Vira a
seção de metodologia do relatório. **Toda fonte usada aparece aqui com URL, data
de acesso, ano de referência e número de registros.**

Regra do projeto: se um arquivo não for encontrado, registrar a falha aqui.
Nunca substituir dado oficial por dado gerado, em silêncio.

---

## 1. Taxas de Rendimento Escolar do INEP

**Situação: em uso, dados reais carregados.**

| | 2023 | 2024 |
|---|---|---|
| **URL** | `https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2023/tx_rend_escolas_2023.zip` | `https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2024/tx_rend_escolas_2024.zip` |
| **Data de acesso** | 23/09/2026 | 23/09/2026 |
| **Tamanho do zip** | 70.080.905 bytes | 69.731.077 bytes |
| **MD5 do xlsx** | `13bd47509105fc6c6dbabcfc378bf882` | `c03736398d4826f844cea8593d9b6bfb` |
| **MD5 conferido** | sim, confere com o arquivo publicado pelo INEP | sim |
| **Registros na planilha** | 128.372 escolas | idem, ordem de grandeza |

O padrão de URL é estável entre edições:
`.../indicadores_educacionais/{ano}/tx_rend_escolas_{ano}.zip`. Também foi
confirmada a existência de 2022.

### Estrutura da planilha

Conferida em 23/09/2026. Importante, porque **os links de download não estão no
HTML das páginas do portal do INEP**: o corpo dessas páginas é montado por
JavaScript, e tentar raspar o HTML não devolve nada. O caminho que funciona é o
endereço direto em `download.inep.gov.br`.

| Item | Valor |
|---|---|
| Aba | `ESCOLAS` |
| Linhas 1 a 8 | Títulos e cabeçalho hierárquico em células mescladas |
| **Linha 9** | **Códigos legíveis por máquina.** É a linha que o leitor usa |
| Linha 10 em diante | Dados |
| Colunas | 63 |
| Marcador de ausente | `--` |
| Separador decimal | **ponto**, por exemplo `79.8` |

### Códigos das colunas

Identificação: `NU_ANO_CENSO`, `NO_REGIAO`, `SG_UF`, `CO_MUNICIPIO`,
`NO_MUNICIPIO`, `CO_ENTIDADE`, `NO_ENTIDADE`, `NO_CATEGORIA` (localização) e
`NO_DEPENDENCIA` (rede).

Indicadores seguem o padrão `{indicador}_CAT_{etapa}{_série}`:

| Prefixo | Indicador | Sufixo | Etapa |
|---|---|---|---|
| `1_` | Taxa de aprovação | `FUN` | Ensino fundamental |
| `2_` | Taxa de reprovação | `MED` | Ensino médio |
| `3_` | Taxa de abandono | `_01` a `_04`, `_AI`, `_AF`, `_NS` | Série ou agrupamento |

As colunas usadas pelo projeto são as do total do ensino médio: **`1_CAT_MED`**,
**`2_CAT_MED`** e **`3_CAT_MED`**.

### Recorte adotado

**Ensino médio, rede estadual, anos de 2023 e 2024.**

- Ensino médio, porque é onde o abandono se concentra e onde a literatura de
  referência do projeto atua.
- Rede estadual, porque responde pela maior parte da oferta de ensino médio.
- Dois anos consecutivos, porque o modelo preditivo da Fase 4 prevê a situação do
  ano seguinte a partir do anterior.

### Validação de sanidade aplicada

Aprovação, reprovação e abandono são partes de um todo e somam 100 por escola. O
comando `processar_inep` calcula essa soma média e alerta se ela fugir de 100.
É o sinal mais barato de que a conversão numérica quebrou.

**Esse teste pegou um erro real.** A primeira versão do conversor removia todo
ponto, assumindo separador de milhar, e transformava `79.8` em `798`. Como 798 é
um número válido, nada falhava: as taxas do painel ficariam dez vezes maiores sem
aviso. A correção e o teste de regressão estão em `etl/transformar.py` e
`tests/test_transformar.py::TestDeteccaoDeSeparadorDecimal`.

---

## 2. API de Localidades do IBGE

**Situação: em uso.**

| | |
|---|---|
| **URL** | `https://servicodados.ibge.gov.br/api/v1/localidades/estados/{UF}/municipios` |
| **Data de acesso** | 23/09/2026 |
| **Autenticação** | Não exige |
| **Consumido por** | `painel/ibge.py`, comando `sincronizar_ibge` |

Observação de formato: alguns municípios retornam `microrregiao` nula, e nesses
casos a UF precisa ser lida pelo caminho
`regiao-imediata > regiao-intermediaria > UF`. O cliente trata os dois caminhos,
com teste cobrindo cada um.

---

## 3. Indicadores ainda pendentes

Estes dois compõem o índice de risco e **ainda não foram localizados**. As
tentativas de endereço direto em `download.inep.gov.br` seguindo o padrão das
taxas de rendimento retornaram 404:

| Indicador | Peso no índice | Situação |
|---|---|---|
| Taxa de Distorção Idade-Série | 0,20 | Pendente. Padrões testados sem sucesso: `tx_distorcao_idade_serie_escolas_2023.zip`, `tx_dist_escolas_2023.zip`, `tdi_escolas_2023.zip`, `TDI_ESCOLAS_2023.zip` |
| INSE, nível socioeconômico | 0,15 | Pendente. Padrões testados sem sucesso: `inse_escolas_2023.zip`, `INSE_2021_escolas.xlsx` |

**Isso não bloqueia o projeto.** O índice de risco redistribui o peso dos
componentes ausentes entre os disponíveis, então ele funciona com aprovação,
reprovação e abandono, que somam 0,65 do peso total. Quando os dois indicadores
entrarem, o índice ganha precisão sem mudança de código.

Páginas oficiais para procurar os arquivos manualmente:

- Distorção idade-série: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/indicadores-educacionais/taxas-de-distorcao-idade-serie
- Indicadores educacionais: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/indicadores-educacionais

Ao encontrar, registrar aqui URL, data de acesso, ano e MD5, e acrescentar o
mapeamento de colunas em `etl/transformar.py`.

---

## 4. Amostra de desenvolvimento

**Situação: não mais necessária, mantida para testes.**

Gerada por `manage.py gerar_amostra`, código em `etl/amostra.py`. Foi usada
enquanto os arquivos do INEP não estavam mapeados. Toda linha sai com
`origem = AMOSTRA`, o painel exibe aviso enquanto houver amostra na base, e
`/api/indicadores/resumo/` devolve `contem_dados_de_amostra: true`.

**Nenhum número vindo dessa fonte pode aparecer no relatório como resultado.**

---

## Como mapear um arquivo novo

Os arquivos do INEP mudam de cabeçalho entre edições. A transformação é guiada
pelo dicionário `MAPA_PADRAO` em `etl/transformar.py`, com chaves em forma
normalizada, sem acento, minúsculas e apenas letras e números.

```python
from etl.transformar import normalizar_nome
normalizar_nome("3_CAT_MED")                    # '3catmed'
normalizar_nome("Distorção Idade-Série")        # 'distorcaoidadeserie'
```

Acrescente a entrada e rode `pytest tests/test_transformar.py`.
