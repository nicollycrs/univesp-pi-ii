# EducaAlerta

Aplicação web acessível para identificação precoce de risco de abandono e
reprovação na educação básica, construída sobre dados abertos do INEP.

Projeto Integrador II, Bacharelado em Ciência de Dados, **Univesp**, 2º semestre
de 2026.

| | |
|---|---|
| **Integrantes** | Nicolly Candida Rodrigues de Souza (RA 24209418), Bruno Gomes Lopes, Matheus Lucas Santos Silva |
| **Orientadora** | Ana Elisa Teixeira da Silva |
| **Aplicação em nuvem** | **https://educaalerta.onrender.com** |
| **Dados** | Taxas de Rendimento Escolar e Taxas de Distorção Idade-Série do INEP, 2023 e 2024, ensino médio da rede estadual |

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

# Segunda API do IBGE: contexto socioeconômico de cada município
python manage.py sincronizar_socioeconomico
```

Agora os dados reais do INEP. Baixe e descompacte em `dados_brutos/`:

```bash
mkdir -p dados_brutos && cd dados_brutos

# Taxas de rendimento: aprovação, reprovação e abandono (cerca de 70 MB cada)
curl -LO https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2023/tx_rend_escolas_2023.zip
curl -LO https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2024/tx_rend_escolas_2024.zip

# Distorção idade-série (cerca de 35 MB cada)
curl -LO https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2023/TDI_2023_ESCOLAS.zip
curl -LO https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2024/TDI_2024_ESCOLAS.zip

unzip -o "tx_rend_escolas_*.zip" && unzip -o "TDI_*_ESCOLAS.zip" && cd ..
```

Reparando no padrão de nome: as taxas de rendimento usam minúsculas e o ano no
fim, a distorção usa maiúsculas e o ano no meio. Depois:

```bash
# Lê as planilhas, limpa e gera o CSV canônico (leva alguns minutos)
python manage.py processar_inep --ano 2023 --ano 2024 --etapa MED --rede estadual

python manage.py carregar_dados dados_processados/indicadores.csv
python manage.py calcular_risco

# Treina o modelo preditivo e grava as previsões para o ano seguinte
python manage.py treinar_modelo

DJANGO_DEBUG=True python manage.py runserver
```

Números obtidos em 19/10/2026 com esse recorte: **20.408 escolas**, **40.384
registros** de indicadores em **27 UFs**, nos anos de 2023 e 2024, com distorção
idade-série presente em **99,3%** deles.

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
| `sincronizar_socioeconomico [--uf SP]` | Busca o contexto socioeconômico municipal no IBGE |
| `processar_inep --ano 2023 --ano 2024` | Lê as planilhas do INEP e gera o CSV canônico |
| `gerar_amostra [--escolas N]` | Gera CSV de amostra (dados não reais) |
| `carregar_dados [caminho]` | Carrega um CSV canônico. Idempotente |
| `calcular_risco [--ano] [--uf]` | Calcula o índice de risco baseado em regras. Idempotente |
| `treinar_modelo [--ano-base] [--ano-alvo]` | Treina o modelo preditivo, grava as previsões e escreve a avaliação em `docs/` |
| `verificar_fontes` | Confere se os portais das fontes ainda respondem |

## A API

| Rota | Descrição |
|---|---|
| `GET /api/escolas/` | Escolas, com filtros `uf`, `rede`, `municipio`, `localizacao` e busca por `search` |
| `GET /api/escolas/<co_entidade>/` | Escola com série histórica e riscos |
| `GET /api/risco/` | Ranking de risco, filtros `ano`, `classe`, `escola__uf`, `versao` e `grupo` |
| `GET /api/municipios/` | Municípios em cache, vindos do IBGE |
| `GET /api/indicadores/resumo/` | Agregados e distribuição por nível de risco |
| `GET /api/indicadores/dispersao/` | Pares de indicador socioeducacional e taxa de abandono. `eixo` aceita `inse`, `distorcao` ou `auto` |
| `GET /api/indicadores/matriz/` | Contagem de escolas em cada grupo da matriz de decisão |
| `GET /saude/` | Verificação de saúde em JSON |

O painel consome exatamente esses endpoints por `fetch`. Nenhum dado vem
embutido no HTML.

Os filtros, o grupo selecionado e a página ficam na barra de endereços, então
qualquer recorte do painel é um link que pode ser compartilhado e recarregado.
Por exemplo, `/?grupo=deterioracao&uf=AC` abre direto nas escolas do Acre que o
modelo aponta como prováveis casos de risco no ano seguinte.

## Índice de risco

Quatro componentes normalizados de 0 a 1 dentro do grupo formado por UF e ano,
combinados por soma ponderada:

| Componente | Peso | Sentido |
|---|---|---|
| Taxa de abandono | 0,40 | Maior valor eleva o risco |
| Taxa de reprovação | 0,25 | Maior valor eleva o risco |
| Distorção idade-série | 0,20 | Maior valor eleva o risco |
| Contexto socioeconômico do município | 0,15 | **Invertido**: contexto mais pobre eleva o risco |

A classificação em três níveis usa tercis dentro do mesmo grupo. Componente
ausente tem o peso redistribuído entre os demais, para que a escola receba índice
em vez de ser descartada.

**Os pesos são uma escolha do grupo**, informada pela literatura, e não valor
consagrado na área. A fundamentação e os limites estão na página
`/sobre/` da aplicação.

**Estado atual dos componentes.** Os quatro estão preenchidos com dados reais e
o índice opera com **peso total 1,00**. Abandono, reprovação e distorção
idade-série vêm do INEP, por escola. O contexto socioeconômico vem do IBGE, por
município.

### Por que o componente socioeconômico é municipal

A fonte pretendida era o **INSE do INEP**, por escola. Ele não é publicado de
forma cruzável, e isso foi verificado, não suposto:

- a página oficial do indicador traz **apenas notas técnicas em PDF**;
- todos os padrões de URL no servidor de download do INEP retornam 404;
- o valor por escola **existe** nos microdados do Saeb 2023, na coluna
  `NIVEL_SOCIO_ECONOMICO`, 70.151 escolas, 100% preenchido. Mas o dicionário
  oficial define o identificador como `Máscaras dos Códigos de Escola (são
  códigos fictícios)`. Todos começam com `61`, o município também está
  mascarado, e o cruzamento pelo código do Censo devolve **zero**
  correspondências. É anonimização por LGPD.

No lugar entra o **salário médio mensal dos trabalhadores formais do município**,
do IBGE, referente a 2021, invertido da mesma forma. Cobre **100%** das escolas
do recorte, varia de 1,0 a 5,9 salários mínimos.

A troca tem custo, declarado aqui, na página `/sobre/` e em
[docs/FONTES_DE_DADOS.md](docs/FONTES_DE_DADOS.md): a granularidade cai de escola
para município, de modo que **escolas do mesmo município recebem o mesmo valor**
neste componente; ele mede o território e não as famílias; e considera apenas o
trabalho formal. Por isso **nunca é chamado de INSE** no código, na interface ou
na documentação. O campo `inse` segue no modelo, vazio, pronto para reassumir a
vaga se o INEP voltar a publicá-lo.

## Modelo preditivo

O índice acima descreve o presente. A pergunta do projeto, no entanto, é sobre o
futuro, e ela exige outro instrumento:

```
treino     indicadores de 2023  ->  quartil superior de abandono em 2024?
previsão   indicadores de 2024  ->  quartil superior de abandono em 2025?
```

O modelo é **treinado** na transição de 2023 para 2024, a única com dado
observado dos dois lados, e é nela que as métricas abaixo foram medidas. O que o
painel **exibe** são previsões de **2025**, obtidas aplicando esse modelo aos
indicadores de 2024, para 20.073 escolas.

Isso importa: prever um ano já observado não é previsão, e pontuar as mesmas
linhas usadas no ajuste produz número otimista. A separação entre o par de
treino e o ano de aplicação é o que torna o número do painel uma estimativa
honesta do futuro. O preço é que ela **só poderá ser conferida quando o INEP
publicar o Censo de 2025**.

Os dados públicos não trazem um rótulo de "escola em crise", então ele foi
construído assim, e isso é declarado como escolha dos autores. O quartil é
calculado **dentro de cada UF**, porque comparar uma escola do Acre com uma de
Santa Catarina na mesma escala mediria sobretudo a diferença entre os estados.

Dois modelos são treinados e comparados a cada execução, uma regressão logística
e uma floresta aleatória. O critério de escolha é a **sensibilidade**, não a
acurácia: em uma base com 25,6% de casos positivos, classificar tudo como sem
risco acertaria 74% e não encontraria escola nenhuma. Havendo empate técnico,
prevalece o modelo interpretável.

| Modelo | Sensibilidade | Especificidade | AUC ROC |
|---|---|---|---|
| **Floresta aleatória** (escolhida) | 0,581 | 0,735 | 0,726 |
| Regressão logística | 0,558 | 0,748 | 0,718 |

A entrada do contexto socioeconômico melhorou o modelo: a sensibilidade subiu de
0,562 para 0,581 e a AUC de 0,722 para 0,726.

A ordem de importância dos atributos discorda dos pesos escolhidos a priori para
o índice de regras, e esse desacordo é um resultado:

| Atributo | Importância |
|---|---|
| Taxa de abandono | 0,456 |
| Distorção idade-série | 0,264 |
| Taxa de reprovação | 0,155 |
| Contexto socioeconômico | 0,115 |
| Localização rural | 0,011 |

A reprovação pesa menos, e a distorção mais, do que o índice de regras supõe. O
painel permite alternar entre as duas leituras em vez de esconder a divergência.

Atenção à leitura: são **importâncias de atributo** da floresta aleatória, sempre
positivas, que medem o quanto cada atributo foi usado para separar os casos. Não
são coeficientes e **não indicam a direção do efeito**. Quando o modelo escolhido
é a regressão logística, o relatório gerado traz coeficientes com sinal, e o diz.

Avaliação completa, matriz de confusão e limites declarados em
[docs/AVALIACAO_DO_MODELO.md](docs/AVALIACAO_DO_MODELO.md).

## Explicabilidade

Nenhum dos dois cálculos é caixa fechada. A página de cada escola abre a conta,
e as duas aberturas são **exatas**:

- **Índice de regras:** as quatro parcelas (valor, posição no grupo, peso,
  contribuição) somam o índice exibido.
- **Modelo preditivo:** a previsão é decomposta por percurso de árvore, creditando
  a cada indicador a mudança de probabilidade nos nós em que ele decidiu a
  divisão. Base mais contribuições reproduz a probabilidade exibida. Para a
  regressão logística, a decomposição é sobre os coeficientes padronizados.

A implementação está em [etl/modelo.py](etl/modelo.py) e **não usa biblioteca
externa**: `shap` resolveria, mas é peso demais para uma instância de 512 MB, e
o cálculo cabe em poucas linhas para os dois modelos do projeto. O teste que
importa verifica a identidade `base + Σ contribuições == previsão`, para os
dois.

A versão vetorizada existe por desempenho: percorrer 300 árvores por escola em
laço Python levava mais de dez minutos para 20 mil escolas, contra **72
segundos** usando `decision_path`. Um teste compara as duas implementações linha
a linha, porque uma divergência silenciosa faria a página explicar algo que o
modelo não fez.

A explicação é calculada no treino, na máquina local, e gravada em JSON no banco.
O processo web apenas lê.

## Matriz de decisão

Um ranking diz onde o problema é maior, não o que fazer. O painel cruza as duas
leituras e separa as escolas em quatro grupos, cada um com uma resposta
diferente. Números de 2024, rede estadual:

|  | Previsão de risco baixo ou médio | Previsão de risco alto |
|---|---|---|
| **Situação aceitável hoje** | Estável, 10.877 escolas | **Deterioração, 2.367 escolas** |
| **Risco alto hoje** | Recuperação, 2.345 escolas | Crise persistente, 4.259 escolas |

**Deterioração é o grupo que justifica ter construído os dois instrumentos.**
São escolas que não aparecem no topo do ranking atual, porque hoje estão bem, e
que o modelo aponta como prováveis casos de risco no ano seguinte. A primeira
delas tem índice atual 0,118, risco baixo, posição aproximada 17.000 no ranking,
e probabilidade prevista de 1,000. Nenhuma das duas leituras isoladas a revela.

Na matriz, o ano selecionado é o ano de referência: escolhido 2024, ela lê
"situação observada em 2024 contra previsão para 2025". Por isso uma linha de
`modelo-v1` guarda o ano dos **indicadores que a geraram**, e o ano previsto é
esse mais um; a página de cada escola mostra os dois por extenso.

Selecionar um grupo filtra o ranking, acrescenta a coluna de previsão e reordena:
em deterioração a ordem útil é a da probabilidade prevista, já que por definição
essas escolas não estão mal hoje.

Para formar quatro grupos, os três níveis de cada leitura viram dois, risco alto
contra os demais. A regra vive em [painel/matriz.py](painel/matriz.py), que é o
único lugar que decide o quadrante de uma escola.

As 384 escolas que aparecem em apenas um dos dois anos não recebem previsão e
ficam fora da matriz. O painel informa quantas são em vez de somá-las a algum
grupo.

O treino roda na máquina local, junto do ETL. **O processo web não importa
scikit-learn**: ele apenas lê do banco as previsões já calculadas, o que mantém o
consumo de memória dentro dos 512 MB do plano gratuito.

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
ausentes), a transformação do ETL com uma planilha suja realista, a junção da
distorção idade-série, o modelo preditivo (construção do rótulo, escolha entre
modelos, classificação por tercis), a matriz de decisão (regra de agrupamento e
coerência entre a contagem do cartão e a lista que ele abre), os endpoints da
API, o cliente do IBGE com resposta simulada, a idempotência dos comandos e a
acessibilidade (contraste, sincronia entre paleta e CSS, estrutura dos
templates, páginas renderizadas e regras de reflow).

O CI roda `manage.py check`, confere que não falta migration, executa a suíte e
valida o `collectstatic` a cada push e pull request.

## Deploy

A aplicação está publicada desde 29/09/2026 em
**https://educaalerta.onrender.com**.

| Camada | Serviço | Configuração |
|---|---|---|
| Aplicação | Render, plano free | Região Virginia, build `./build.sh`, start `gunicorn educaalerta.wsgi:application`, health check em `/saude/` |
| Banco | Neon, plano free | PostgreSQL 17, região Virginia, 29 MB de 500 MB usados |

A infraestrutura está descrita em [`render.yaml`](render.yaml), então o Render é
configurado a partir do próprio repositório, e não por cliques no painel. Cada
`git push` na branch `main` dispara build, `collectstatic`, `migrate` e
publicação automaticamente.

Duas decisões que valem registro:

**O banco não é o PostgreSQL do Render**, e sim o Neon. O gratuito do Render
expira 30 dias após ser criado, e o projeto vai até novembro. O plano gratuito do
Neon não expira e desperta sozinho após hibernar.

**Aplicação e banco ficam na mesma região.** Em costas opostas dos Estados Unidos,
cada consulta somaria cerca de 60 ms. Virginia também é a região dos EUA mais
próxima do Brasil.

Só duas variáveis precisam ser cadastradas à mão no Render: `DATABASE_URL`, com a
connection string do Neon, e nada mais. A `DJANGO_SECRET_KEY` é gerada pelo
próprio Render, conforme declarado no `render.yaml`.

Se `DATABASE_URL` faltar ou vier malformada, a aplicação **falha no build com
mensagem explicando o problema**, em vez de subir usando SQLite no disco efêmero
do contêiner e perder os dados a cada deploy.

## Estrutura

```
educaalerta/     configuração do projeto Django
painel/          app principal: models, API, views, templates, estáticos
  cores.py       paleta e cálculo de contraste da WCAG
  risco.py       índice de risco (sem pandas, para caber na RAM do plano free)
  matriz.py      cruzamento entre índice atual e previsão, os quatro grupos
  ibge.py        cliente da API do IBGE
etl/             extração, transformação e modelo (pandas e scikit-learn, roda local)
  modelo.py      modelo preditivo: construção do rótulo, treino e comparação
tests/           suíte pytest
docs/            fontes, qualidade dos dados e avaliação
```

## Licença

Ver [LICENSE](LICENSE).
