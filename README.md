# EducaAlerta

Aplicação web acessível para identificação precoce de risco de abandono e
reprovação na educação básica, construída sobre dados abertos do INEP.

Projeto Integrador II, Bacharelado em Ciência de Dados, **Univesp**, 2º semestre
de 2026.

| | |
|---|---|
| **Integrantes** | Nicolly Candida Rodrigues de Souza (RA 24209418), Bruno Gomes Lopes |
| **Orientadora** | Ana Elisa Teixeira da Silva |
| **Aplicação em nuvem** | *a publicar (ver Deploy)* |
| **Dados** | Taxas de Rendimento Escolar do INEP, 2023 e 2024, ensino médio da rede estadual |

> **Nota sobre o primeiro acesso.** A aplicação está hospedada em plano gratuito,
> que hiberna após 15 minutos sem uso. O primeiro acesso pode levar até 60
> segundos para responder. Depois disso a navegação é normal.

---

## O problema

A reprovação e o abandono na educação básica costumam ser reconhecidos pelas
equipes gestoras apenas ao final do período letivo, quando a intervenção
pedagógica já tem baixa efetividade. O INEP publica anualmente indicadores que
descrevem fluxo escolar, distorção idade-série e nível socioeconômico, mas em
arquivos volumosos e de formato técnico. A informação é pública e não chega a
quem poderia agir sobre ela.

O EducaAlerta transforma esses dados em um painel acessível, que ordena escolas
por um índice de risco e explica como esse índice foi construído.

## Como funciona

```
   Máquina local                          Nuvem
   ─────────────                          ─────
   dados_brutos/ (INEP, vários GB)
        │
        │ etl/ com pandas: limpeza e agregação por escola
        ▼
   dados_processados/*.csv ──push──► GitHub ──deploy──► Render (Django)
        │                                                    │
        └── manage.py carregar_dados ──────────────► Neon (PostgreSQL, 0,5 GB)
                                                             │
                                                      API REST (DRF)
                                                             │
                                                Painel (JavaScript + Chart.js)
```

O ETL pesado roda na máquina local e só a tabela agregada por escola sobe para a
nuvem. O motivo é o limite de 0,5 GB do plano gratuito do Neon: os microdados
brutos do Censo Escolar não caberiam.

## Rodar na sua máquina

Requisitos: Python 3.12 ou mais recente, e Git.

```bash
git clone https://github.com/nicollycrs/univesp-pi-ii.git
cd univesp-pi-ii

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux e macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Sem `DATABASE_URL` definida o projeto usa SQLite, o que basta para desenvolver.

```bash
python manage.py migrate

# Consome a API do IBGE e preenche os 5.571 municípios (idempotente)
python manage.py sincronizar_ibge
```

Agora os dados reais do INEP. Baixe e descompacte em `dados_brutos/`:

```bash
mkdir -p dados_brutos && cd dados_brutos
curl -LO https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2023/tx_rend_escolas_2023.zip
curl -LO https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2024/tx_rend_escolas_2024.zip
unzip -o "tx_rend_escolas_*.zip" && cd ..
```

Cada arquivo tem cerca de 70 MB. Depois:

```bash
# Lê as planilhas, limpa e gera o CSV canônico (leva alguns minutos)
python manage.py processar_inep --ano 2023 --ano 2024 --etapa MED --rede estadual

python manage.py carregar_dados dados_processados/indicadores.csv
python manage.py calcular_risco

DJANGO_DEBUG=True python manage.py runserver
```

Números obtidos em 23/09/2026 com esse recorte: **20.406 escolas**, **40.377
registros** de indicadores em **27 UFs**, nos anos de 2023 e 2024.

Se ainda não quiser baixar os arquivos do INEP, existe uma amostra para
desenvolvimento, com dados sintéticos:

```bash
python manage.py gerar_amostra --escolas 400
python manage.py carregar_dados dados_processados/AMOSTRA_DESENVOLVIMENTO.csv
python manage.py calcular_risco
```

Abra `http://127.0.0.1:8000/`.

### Sobre a amostra de desenvolvimento

Enquanto os arquivos oficiais do INEP não estão baixados e mapeados, o comando
`gerar_amostra` produz dados sintéticos para que a aplicação possa ser
desenvolvida e testada. **Esses números não são reais e não podem ser citados
como resultado.** Quatro salvaguardas evitam a confusão:

1. toda linha recebe `origem = AMOSTRA`;
2. o nome do arquivo diz `AMOSTRA_DESENVOLVIMENTO`;
3. o painel exibe aviso em destaque enquanto houver amostra na base;
4. `/api/indicadores/resumo/` devolve `contem_dados_de_amostra: true`.

Para carregar dados reais, ver [docs/FONTES_DE_DADOS.md](docs/FONTES_DE_DADOS.md).

## Comandos disponíveis

| Comando | O que faz |
|---|---|
| `sincronizar_ibge [--uf SP]` | Baixa municípios da API do IBGE e grava no banco |
| `processar_inep --ano 2023 --ano 2024` | Lê as planilhas do INEP e gera o CSV canônico |
| `gerar_amostra [--escolas N]` | Gera CSV de amostra (dados não reais) |
| `carregar_dados [caminho]` | Carrega um CSV canônico. Idempotente |
| `calcular_risco [--ano] [--uf]` | Calcula o índice de risco. Idempotente |
| `verificar_fontes` | Confere se os portais das fontes ainda respondem |

## A API

| Rota | Descrição |
|---|---|
| `GET /api/escolas/` | Escolas, com filtros `uf`, `rede`, `municipio`, `localizacao` e busca por `search` |
| `GET /api/escolas/<co_entidade>/` | Escola com série histórica e riscos |
| `GET /api/risco/` | Ranking de risco, filtros `ano`, `classe`, `escola__uf` |
| `GET /api/municipios/` | Municípios em cache, vindos do IBGE |
| `GET /api/indicadores/resumo/` | Agregados e distribuição por nível de risco |
| `GET /api/indicadores/dispersao/` | Pares de INSE e taxa de abandono |
| `GET /saude/` | Verificação de saúde em JSON |

O painel consome exatamente esses endpoints por `fetch`. Nenhum dado vem
embutido no HTML.

## Índice de risco

Quatro componentes normalizados de 0 a 1 dentro do grupo formado por UF e ano,
combinados por soma ponderada:

| Componente | Peso | Sentido |
|---|---|---|
| Taxa de abandono | 0,40 | Maior valor eleva o risco |
| Taxa de reprovação | 0,25 | Maior valor eleva o risco |
| Distorção idade-série | 0,20 | Maior valor eleva o risco |
| INSE | 0,15 | **Invertido**: nível socioeconômico menor eleva o risco |

A classificação em três níveis usa tercis dentro do mesmo grupo. Componente
ausente tem o peso redistribuído entre os demais, para que a escola receba índice
em vez de ser descartada.

**Os pesos são uma escolha do grupo**, informada pela literatura, e não valor
consagrado na área. A fundamentação e os limites estão na página
`/sobre/` da aplicação.

**Estado atual dos componentes.** Abandono e reprovação já vêm dos dados reais do
INEP. Distorção idade-série e INSE ainda não foram localizados para download
automático, e o índice redistribui o peso deles entre os disponíveis. Detalhes e
endereços testados em [docs/FONTES_DE_DADOS.md](docs/FONTES_DE_DADOS.md).

## Acessibilidade

A interface segue as diretrizes **WCAG 2.1 no nível AA**. O critério mais
importante para este projeto é o **1.4.1 Uso da Cor**: o nível de risco nunca é
comunicado apenas por cor, a tarja colorida sempre carrega o rótulo em texto.

Outros pontos implementados: alternativa em tabela para cada gráfico (1.1.1),
navegação completa por teclado (2.1.1), foco visível (2.4.7), idioma declarado
(3.1.1), contraste de 4,5:1 em texto e 3:1 em elementos gráficos (1.4.3 e
1.4.11), e reflow a 320 px (1.4.10).

A paleta vive em `painel/cores.py` e existe teste automatizado que falha se
qualquer par perder o contraste mínimo ou se o CSS divergir da paleta.

## Testes

```bash
pytest -q
```

A suíte cobre o índice de risco (inversão do INSE, normalização por grupo,
ausentes), a transformação do ETL com uma planilha suja realista, os endpoints da
API, o cliente do IBGE com resposta simulada, a idempotência dos comandos e a
acessibilidade (contraste, sincronia entre paleta e CSS, estrutura dos
templates).

O CI roda `manage.py check`, confere que não falta migration, executa a suíte e
valida o `collectstatic` a cada push e pull request.

## Deploy

O passo a passo completo está em `nuvem/GUIA_DEPLOY.md`, na pasta de trabalho do
grupo. Em resumo:

1. **Neon**: criar projeto PostgreSQL e copiar a connection string.
2. **Render**: novo Web Service apontando para este repositório, plano free,
   build `./build.sh`, start `gunicorn educaalerta.wsgi:application`.
3. Cadastrar as variáveis `DATABASE_URL`, `DJANGO_SECRET_KEY` e
   `DJANGO_DEBUG=False`.
4. Antes do primeiro push: `git update-index --chmod=+x build.sh`.

O banco **não** é o PostgreSQL gratuito do Render, que expira 30 dias após ser
criado. Fica no Neon, cujo plano gratuito não expira e desperta sozinho após
hibernar.

## Estrutura

```
educaalerta/     configuração do projeto Django
painel/          app principal: models, API, views, templates, estáticos
  cores.py       paleta e cálculo de contraste da WCAG
  risco.py       índice de risco (sem pandas, para caber na RAM do plano free)
  ibge.py        cliente da API do IBGE
etl/             extração e transformação com pandas (roda local)
tests/           suíte pytest
docs/            fontes, qualidade dos dados e avaliação
```

## Licença

Ver [LICENSE](LICENSE).
