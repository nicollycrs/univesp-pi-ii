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

## 3. Taxas de Distorção Idade-Série do INEP

**Situação: em uso, dados reais carregados.**

| | 2023 | 2024 |
|---|---|---|
| **URL** | `https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2023/TDI_2023_ESCOLAS.zip` | `.../2024/TDI_2024_ESCOLAS.zip` |
| **Data de acesso** | 19/10/2026 | 19/10/2026 |
| **Tamanho do zip** | 35.125.615 bytes | 34.988.097 bytes |
| **MD5 do xlsx** | `8b587f43079bdcf63fb920369c0b18ee` | conferido |
| **Registros** | 128.239 escolas | ordem de grandeza igual |
| **Cobertura após o recorte** | 99,3% das escolas | 99,2% |

### Como o arquivo foi encontrado

Registro aqui porque custou tempo e a lição é reaproveitável. **Os links de
download não estão no HTML das páginas do INEP**: o corpo dessas páginas é
montado por JavaScript, e requisições simples devolvem a página sem nenhum link.
Dezenas de tentativas de adivinhar o endereço falharam, entre elas
`tdi_escolas_2023.zip`, `tx_dist_escolas_2023.zip` e `TDI_ESCOLAS_2023.zip`.

A solução foi **renderizar a página em um navegador sem interface** e extrair o
DOM já processado, onde o endereço aparece. O padrão real é
`TDI_{ano}_ESCOLAS.zip`, em maiúsculas e com o ano antes da palavra ESCOLAS,
ordem inversa da usada nas taxas de rendimento.

### Estrutura

Idêntica à das taxas de rendimento: aba `ESCOLAS`, códigos legíveis por máquina
na linha 9, dados a partir da linha 10, `--` como marcador de ausente e ponto
como separador decimal. Os códigos de indicador seguem o padrão
`{ETAPA}_CAT_0` para o total da etapa, de modo que a coluna usada é
**`MED_CAT_0`**, o total do ensino médio.

Por essa semelhança, o mesmo leitor atende aos dois arquivos: `etl/rendimento.py`
aceita um mapa de colunas, e `etl/transformar.py` fornece `mapa_etapa()` para o
rendimento e `mapa_distorcao()` para a distorção.

### O que mudou no índice

Com a distorção carregada, o índice passou a operar com **0,85 do peso total**,
contra 0,65 antes. Resta apenas o INSE, de peso 0,15.

---

## 4. INSE do INEP: por que não foi usado

**Situação: indisponível de forma cruzável. Substituído, com declaração.**

O INSE era a fonte pretendida para o componente socioeconômico do índice, peso
0,15. A busca foi encerrada em 27/10/2026 com um resultado negativo bem
determinado, que vale registrar porque é ele que justifica a substituição.

### O que foi verificado

| Caminho | Resultado |
|---|---|
| Página oficial do INSE no portal do INEP | Renderizada com navegador. Contém **apenas cinco notas técnicas em PDF**, de 2013 a 2023. Nenhum arquivo de dados. |
| `download.inep.gov.br`, padrões de URL | Todos 404 confirmado por cabeçalho, inclusive o padrão `INSE_{ano}_ESCOLAS` nas extensões `.xlsx`, `.csv` e `.zip`, em `informacoes_estatisticas/` e `publicacoes/`. |
| Catálogo `dados.gov.br` | Registra o conjunto, formato XLSX, edições 2011-2013, 2015, 2019 e 2021. Os links ficam atrás de API autenticada. |
| **Microdados do Saeb 2023** | **O INSE está lá**, em `DADOS/TS_ESCOLA.csv`, coluna `NIVEL_SOCIO_ECONOMICO`, 70.151 escolas, 100% preenchido, níveis I a VII. **Mas o código da escola é fictício.** |
| Mirror da Secretaria de Educação de SP | `INSE_2019_ESCOLAS.csv`, mas chaveado pelo código estadual (CIE) e derivado do SARESP, não do Saeb. Apenas SP. |

### O impedimento, em uma linha

O dicionário oficial dos microdados do Saeb 2023 define o campo assim:

```
ID_ESCOLA = 'Máscaras dos Códigos de Escola (são códigos fictícios)'
```

Todos os identificadores começam com `61` e o código de município também está
mascarado. O cruzamento com as 20.408 escolas do recorte do projeto, pelo código
do Censo, devolve **zero correspondências**. É anonimização deliberada, coerente
com a LGPD, e não uma falha de busca.

### Nota de método

Para inspecionar os 694 MB dos microdados foram baixados apenas **5 MB**: o
índice central de um arquivo ZIP fica no fim do arquivo, então uma requisição
HTTP por intervalo de bytes traz a lista de membros, e uma segunda traz só o
membro desejado, que é então descomprimido localmente. A técnica é reaproveitável
para qualquer arquivo grande do INEP.

---

## 5. Contexto socioeconômico municipal, do IBGE

**Situação: em uso. Ocupa a vaga do INSE no índice.**

| | |
|---|---|
| **Indicador** | Salário médio mensal dos trabalhadores formais |
| **Unidade** | Salários mínimos |
| **Ano de referência** | 2021 |
| **Fonte** | IBGE, API de indicadores do panorama municipal |
| **URL** | `https://servicodados.ibge.gov.br/api/v1/pesquisas/indicadores/29765/resultados/{municipios}` |
| **Data de acesso** | 27/10/2026 |
| **Autenticação** | Não exige |
| **Cobertura** | 5.570 de 5.571 municípios; **100% dos indicadores do projeto** |
| **Amplitude** | 1,0 a 5,9 salários mínimos, média 2,01 |
| **Consumido por** | `painel/ibge.py`, comando `sincronizar_socioeconomico` |

Detalhe de formato: a API devolve o código do município com **6 dígitos**, sem o
dígito verificador, enquanto o projeto guarda os 7 do IBGE. A conversão é
truncar, e está em `_codigo_curto()`.

### O que a substituição preserva e o que ela custa

**Preserva.** É dado público, oficial, cruzável pelo código de município que o
projeto já mantém via API do IBGE, e **varia dentro de cada UF**, que é a
condição para o componente contribuir, já que a normalização do índice acontece
dentro do grupo (uf, ano). Um indicador constante dentro da UF seria normalizado
para 0,5 em todas as escolas e não alteraria ranking nenhum.

**Custa, e isto precisa ser dito no relatório:**

1. **A granularidade cai de escola para município.** Escolas do mesmo município
   recebem o mesmo valor, e o componente não as diferencia entre si.
2. **Mede o território, não as famílias** dos estudantes daquela escola, que era
   o que o INSE media.
3. **Cobre apenas o trabalho formal**, então subestima a informalidade, o que
   tende a achatar a diferença entre municípios pobres e muito pobres.

Por isso o componente **nunca é chamado de INSE** em lugar nenhum do código, da
interface ou da documentação. O nome dele é `contexto_socioeconomico`, e a
página `/sobre/` declara a troca para quem usa o painel.

O campo `inse` continua existindo no modelo e no ETL, vazio. Se o INEP voltar a
publicar o indicador por escola de forma cruzável, ele volta ao índice sem
mudança de estrutura.

---

## 6. Amostra de desenvolvimento

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
