/*
  EducaAlerta - painel.

  Consome a API REST do proprio projeto (/api/...) por fetch. Nenhum dado vem
  embutido no HTML: e isso que faz a API ser parte do produto.

  Cuidados de acessibilidade implementados aqui:
    - toda mudanca de conteudo e anunciada na regiao #status (aria-live);
    - o nivel de risco sempre aparece como texto, alem da cor (criterio 1.4.1);
    - cada grafico tem uma tabela equivalente preenchida com os mesmos dados
      (criterio 1.1.1);
    - os botoes de paginacao sao <button> de verdade, focaveis por teclado.
*/

(function () {
  "use strict";

  var PALETA = JSON.parse(document.getElementById("paleta").textContent || "{}");
  var GRAFICO = PALETA.grafico || {};

  var form = document.getElementById("filtros");
  if (!form) return; // pagina sem dados carregados

  var status = document.getElementById("status");
  var corpoRanking = document.querySelector("#t-ranking tbody");
  var pagInfo = document.getElementById("pag-info");
  var btnAnterior = document.getElementById("pag-anterior");
  var btnProxima = document.getElementById("pag-proxima");

  var DESCRICOES = JSON.parse(
    (document.getElementById("descricoes-versao") || {}).textContent || "{}"
  );
  var btnLimpar = document.getElementById("limpar");
  var campoVersao = document.getElementById("f-versao");
  var ajudaVersao = document.getElementById("ajuda-versao");
  var conteudo = document.getElementById("conteudo");

  var estado = { pagina: 1, totalPaginas: 1, total: 0, resumoAnterior: null, grupo: null };
  var graficoDispersao = null;

  function anunciar(texto) {
    status.textContent = texto;
  }

  /*
    Estado sem dados de um grafico.

    Um canvas vazio parece defeito, e com role="img" o leitor de tela anunciaria
    uma imagem que nao informa nada. Quando a serie vem vazia, o canvas e
    escondido e uma explicacao entra no lugar. Acontece de verdade neste projeto:
    o grafico de INSE depende de um indicador do INEP que ainda nao foi carregado.
  */
  function marcarSemDados(idCanvas, mensagem) {
    var canvas = document.getElementById(idCanvas);
    if (!canvas) return;
    var aviso = document.getElementById(idCanvas + "-vazio");
    if (!aviso) {
      aviso = document.createElement("p");
      aviso.id = idCanvas + "-vazio";
      aviso.className = "aviso";
      aviso.setAttribute("role", "status");
      canvas.parentNode.insertBefore(aviso, canvas.nextSibling);
    }
    aviso.textContent = mensagem;
    canvas.hidden = true;
    aviso.hidden = false;
    if (canvas.parentNode.classList.contains("grafico-area")) {
      canvas.parentNode.classList.add("vazia");
    }
  }

  function marcarComDados(idCanvas) {
    var canvas = document.getElementById(idCanvas);
    if (canvas) {
      canvas.hidden = false;
      if (canvas.parentNode.classList.contains("grafico-area")) {
        canvas.parentNode.classList.remove("vazia");
      }
    }
    var aviso = document.getElementById(idCanvas + "-vazio");
    if (aviso) aviso.hidden = true;
  }

  function filtrosAtuais() {
    var dados = new FormData(form);
    var p = new URLSearchParams();
    ["uf", "ano", "classe", "busca", "versao"].forEach(function (chave) {
      var valor = dados.get(chave);
      if (valor) p.set(chave, valor);
    });
    return p;
  }

  function numero(valor, casas) {
    if (valor === null || valor === undefined) return "sem dado";
    return Number(valor).toLocaleString("pt-BR", {
      minimumFractionDigits: casas === undefined ? 1 : casas,
      maximumFractionDigits: casas === undefined ? 1 : casas,
    });
  }

  /* Evita exibir "sem dado%" quando o indicador nao esta na base. */
  function porcentagem(valor) {
    if (valor === null || valor === undefined) return "sem dado";
    return numero(valor) + "%";
  }

  async function buscarJson(url) {
    var resposta = await fetch(url, { headers: { Accept: "application/json" } });
    if (!resposta.ok) throw new Error("A API respondeu " + resposta.status);
    return resposta.json();
  }

  /*
    Variacao em relacao ao ano anterior.

    Uma taxa de 3,5% diz pouco sozinha. Dizer que subiu 0,3 ponto em relacao ao
    ano anterior muda a leitura, e e informacao que a base ja tem. A seta nunca
    aparece sozinha: vem sempre com o sinal e o numero, pelo criterio 1.4.1.
  */
  // `neutro` desliga a leitura de bom e ruim. Nas taxas, subir e ruim e cair e
  // bom, e a cor ajuda. Na contagem de escolas nao ha bom nem ruim: pintar de
  // vermelho "mais 80 escolas na selecao" sugeriria um alarme que nao existe.
  function mostrarVariacao(id, atual, anterior, sufixo, casas, neutro) {
    var el = document.getElementById(id);
    if (!el) return;
    if (atual === null || atual === undefined || anterior === null || anterior === undefined) {
      el.textContent = "";
      el.className = "variacao";
      return;
    }
    var delta = atual - anterior;
    // O limiar acompanha a precisao exibida: com uma casa decimal, uma variacao
    // de 0,02 arredonda para 0,0, e mostrar a seta com "+0,0" parecia defeito.
    var casasUsadas = casas === undefined ? 1 : casas;
    var limiar = Math.pow(10, -casasUsadas) / 2;
    var simbolo = delta >= limiar ? "▲" : delta <= -limiar ? "▼" : "=";
    var classe = delta >= limiar ? "subiu" : delta <= -limiar ? "caiu" : "igual";
    var texto = Math.abs(delta) < limiar
      ? "estável em relação ao ano anterior"
      : simbolo + " " + (delta > 0 ? "+" : "") + numero(delta, casasUsadas) +
        (sufixo || "") + " em relação ao ano anterior";
    el.textContent = texto;
    el.className = "variacao " + (neutro ? "igual" : classe);
  }

  async function buscarAnoAnterior(ano) {
    var p = filtrosAtuais();
    p.set("ano", String(Number(ano) - 1));
    p.delete("classe");
    try {
      return await buscarJson("/api/indicadores/resumo/?" + p.toString());
    } catch (e) {
      return null;
    }
  }

  // --------------------------------------------------------------- resumo
  async function carregarResumo() {
    var p = filtrosAtuais();
    p.delete("classe"); // o resumo nao filtra por classe
    var dados = await buscarJson("/api/indicadores/resumo/?" + p.toString());
    var a = dados.agregados;

    document.getElementById("c-escolas").textContent = numero(a.escolas, 0);
    document.getElementById("c-abandono").textContent = porcentagem(a.abandono_medio);
    document.getElementById("c-reprovacao").textContent = porcentagem(a.reprovacao_media);
    document.getElementById("c-distorcao").textContent = porcentagem(a.distorcao_media);


    var ano = new FormData(form).get("ano");
    if (ano) {
      var anterior = await buscarAnoAnterior(ano);
      var b = anterior && anterior.agregados;
      if (b && b.escolas) {
        mostrarVariacao("v-abandono", a.abandono_medio, b.abandono_medio, " p.p.");
        mostrarVariacao("v-reprovacao", a.reprovacao_media, b.reprovacao_media, " p.p.");
        mostrarVariacao("v-distorcao", a.distorcao_media, b.distorcao_media, " p.p.");
        mostrarVariacao("v-escolas", a.escolas, b.escolas, " escolas", 0, true);
      } else {
        ["v-abandono","v-reprovacao","v-distorcao","v-escolas"].forEach(function (id) {
          var el = document.getElementById(id);
          if (el) { el.textContent = ""; el.className = "variacao"; }
        });
      }
    }
    return dados;
  }

  // ------------------------------------------------------------ dispersao
  async function carregarDispersao() {
    var p = filtrosAtuais();
    p.delete("classe");
    var dados = await buscarJson("/api/indicadores/dispersao/?" + p.toString());
    var rotulo = dados.rotulo_eixo || "Indicador";
    var comUnidade = dados.unidade_eixo ? rotulo + " (" + dados.unidade_eixo + ")" : rotulo;
    desenharDispersao(dados.pontos, comUnidade);
    preencherTabelaDispersao(dados.pontos);
    atualizarTextosDispersao(dados.eixo, rotulo, comUnidade, dados.pontos.length);
  }

  // O eixo horizontal do grafico nao e fixo: a API informa qual indicador tinha
  // dados na selecao. Titulo, resumo e cabecalho da tabela acompanham, do
  // contrario a pagina descreveria um grafico diferente do que esta na tela.
  function atualizarTextosDispersao(eixo, rotulo, comUnidade, quantidade) {
    var titulo = document.getElementById("titulo-g2");
    var resumo = document.getElementById("resumo-g2");
    var cabecalho = document.getElementById("th-dispersao");
    if (titulo) titulo.textContent = rotulo + " e taxa de abandono";
    if (cabecalho) cabecalho.textContent = comUnidade;
    if (!resumo) return;
    if (!quantidade) {
      resumo.textContent = "";
      return;
    }
    var texto =
      "Cada ponto é uma escola. O eixo horizontal traz " + rotulo.toLowerCase() +
      " e o vertical a taxa de abandono em porcentagem.";
    if (eixo === "contexto") {
      // Os pontos formam colunas verticais porque o indicador e municipal.
      // Sem esta frase o grafico parece defeito de dados, quando na verdade
      // esta mostrando com fidelidade o limite da fonte.
      texto +=
        " Os pontos se alinham em colunas porque este indicador é municipal: " +
        "todas as escolas de um mesmo município compartilham o mesmo valor no " +
        "eixo horizontal.";
    } else if (eixo === "distorcao") {
      texto +=
        " O contexto socioeconômico seria o indicador preferido aqui, mas não " +
        "há valor dele na seleção atual; a distorção idade-série entra no lugar.";
    }
    resumo.textContent = texto;
  }

  function desenharDispersao(pontos, rotulo) {
    var ctx = document.getElementById("g-dispersao");
    if (!ctx) return;
    if (!pontos.length) {
      marcarSemDados(
        "g-dispersao",
        "Gráfico indisponível: nenhum dos indicadores deste gráfico, nível " +
        "socioeconômico ou distorção idade-série, tem dados na seleção atual. " +
        "As demais informações da página não são afetadas."
      );
      if (graficoDispersao) { graficoDispersao.destroy(); graficoDispersao = null; }
      return;
    }
    marcarComDados("g-dispersao");
    if (graficoDispersao) graficoDispersao.destroy();
    graficoDispersao = new Chart(ctx, {
      type: "scatter",
      data: {
        datasets: [{
          label: "Escolas",
          data: pontos.map(function (p) { return { x: p.x, y: p.taxa_abandono }; }),
          backgroundColor: GRAFICO.neutro,
          pointRadius: 3,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { title: { display: true, text: rotulo } },
          y: { title: { display: true, text: "Taxa de abandono (%)" }, beginAtZero: true },
        },
      },
    });
  }

  function preencherTabelaDispersao(pontos) {
    var corpo = document.querySelector("#t-dispersao tbody");
    corpo.innerHTML = "";
    if (!pontos.length) {
      var tr = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 3;
      td.textContent = "Sem dados para este gráfico na seleção atual.";
      tr.appendChild(td);
      corpo.appendChild(tr);
      return;
    }
    pontos
      .slice()
      .sort(function (a, b) { return b.taxa_abandono - a.taxa_abandono; })
      .slice(0, 50)
      .forEach(function (p) {
        var tr = document.createElement("tr");
        var th = document.createElement("th");
        th.scope = "row";
        th.textContent = p.escola_nome;
        tr.appendChild(th);
        [numero(p.x, 2), numero(p.taxa_abandono)].forEach(function (v) {
          var td = document.createElement("td");
          td.className = "numero";
          td.textContent = v;
          tr.appendChild(td);
        });
        corpo.appendChild(tr);
      });
  }

  // -------------------------------------------------------------- ranking
  async function carregarRanking() {
    var p = filtrosAtuais();
    var uf = p.get("uf");
    if (uf) { p.delete("uf"); p.set("escola__uf", uf); }
    var busca = p.get("busca");
    if (busca) { p.delete("busca"); p.set("search", busca); }
    if (estado.grupo) {
      // O endpoint resolve o quadrante cruzando as duas versoes, entao a
      // versao escolhida no formulario deixa de valer aqui.
      p.delete("versao");
      p.set("grupo", estado.grupo);
      p.set("ordering", ordenacaoDoGrupo(estado.grupo));
    }
    p.set("page", estado.pagina);

    var dados = await buscarJson("/api/risco/?" + p.toString());
    estado.total = dados.count;
    estado.totalPaginas = Math.max(1, Math.ceil(dados.count / 50));

    corpoRanking.innerHTML = "";
    dados.results.forEach(function (r) {
      var tr = document.createElement("tr");

      var th = document.createElement("th");
      th.scope = "row";
      var a = document.createElement("a");
      a.href = "/escola/" + r.co_entidade + "/";
      a.textContent = r.escola_nome;
      th.appendChild(a);
      tr.appendChild(th);

      [r.uf, r.municipio_nome || "sem dado", r.ano].forEach(function (v) {
        var td = document.createElement("td");
        td.textContent = v;
        tr.appendChild(td);
      });

      // Indice com barra proporcional desenhada atras do numero. A barra e
      // decorativa: o valor continua disponivel como texto para leitor de tela.
      var tdScore = document.createElement("td");
      tdScore.className = "numero celula-indice";
      var barra = document.createElement("span");
      barra.className = "barra";
      barra.setAttribute("aria-hidden", "true");
      barra.style.width = Math.round(Math.max(0, Math.min(1, r.score)) * 100) + "%";
      var valor = document.createElement("span");
      valor.className = "valor";
      valor.textContent = numero(r.score, 3);
      tdScore.appendChild(barra);
      tdScore.appendChild(valor);
      tr.appendChild(tdScore);

      // Tarja com cor E texto. Sem o texto, a informacao dependeria da cor.
      var tdNivel = document.createElement("td");
      var span = document.createElement("span");
      span.className = "tarja tarja-" + r.classe;
      span.textContent = r.rotulo;
      tdNivel.appendChild(span);
      tr.appendChild(tdNivel);

      // A coluna de previsao so existe com um grupo selecionado, porque so
      // nessa consulta a previsao vem anexada a cada linha.
      if (estado.grupo) {
        var tdPrev = document.createElement("td");
        if (r.classe_prevista) {
          var transicao = document.createElement("span");
          transicao.className = "transicao";
          transicao.appendChild(document.createTextNode(numero(r.score, 3)));
          var seta = document.createElement("span");
          seta.className = "seta";
          seta.textContent = " → ";
          transicao.appendChild(seta);
          transicao.appendChild(document.createTextNode(numero(r.score_previsto, 3)));
          tdPrev.appendChild(transicao);
          tdPrev.appendChild(document.createTextNode(" "));
          var tarjaPrev = document.createElement("span");
          tarjaPrev.className = "tarja tarja-" + r.classe_prevista;
          tarjaPrev.textContent = r.rotulo_previsto;
          tdPrev.appendChild(tarjaPrev);
        } else {
          tdPrev.textContent = "sem previsão";
        }
        tr.appendChild(tdPrev);
      }

      corpoRanking.appendChild(tr);
    });

    var thPrevisao = document.getElementById("th-previsao");
    if (thPrevisao) thPrevisao.hidden = !estado.grupo;

    // A legenda descreve a ordenacao, que muda com o grupo. Deixa-la fixa faria
    // a tabela afirmar uma ordem diferente da que esta na tela.
    var legenda = document.getElementById("legenda-ranking");
    if (legenda) {
      legenda.textContent = estado.grupo
        ? "Escolas do grupo selecionado. " + explicarOrdem(estado.grupo)
        : "Escolas ordenadas do maior para o menor índice de risco.";
    }

    pagInfo.textContent =
      "Página " + estado.pagina + " de " + estado.totalPaginas +
      " (" + numero(estado.total, 0) + " escolas)";
    btnAnterior.disabled = estado.pagina <= 1;
    btnProxima.disabled = estado.pagina >= estado.totalPaginas;
    return dados;
  }

  // -------------------------------------------------- matriz de decisao
  /*
    A matriz cruza o indice atual com a previsao do modelo e separa as escolas
    em quatro grupos de acao. Selecionar um grupo filtra o ranking abaixo.

    Acessibilidade: cada cartao e um <button> com aria-pressed, traz por escrito
    a sua condicao e a sua prioridade, e nao depende da posicao na grade nem da
    cor para ser compreendido. Em tela estreita a grade vira uma coluna e os
    rotulos de eixo somem, porque o texto do cartao ja os torna dispensaveis.
  */
  var CLASSE_DO_GRUPO = {
    alto: "grupo-alto",
    medio: "grupo-medio",
    baixo: "grupo-baixo",
    neutro: "grupo-neutro",
  };

  // Dentro de cada grupo, a ordem util nao e sempre a mesma. Em deterioracao o
  // que importa e quem o modelo aponta com mais forca, e nao quem esta pior
  // hoje: por definicao, essas escolas nao estao mal hoje.
  var ORDEM_DO_GRUPO = { deterioracao: "-score_previsto" };

  function ordenacaoDoGrupo(grupo) {
    return ORDEM_DO_GRUPO[grupo] || "-score";
  }

  function explicarOrdem(grupo) {
    return grupo === "deterioracao"
      ? "Ordenadas da maior para a menor probabilidade apontada pelo modelo."
      : "Ordenadas do maior para o menor índice atual.";
  }

  async function carregarMatriz() {
    var secao = document.getElementById("secao-matriz");
    var grade = document.getElementById("matriz");
    var nota = document.getElementById("matriz-nota");
    if (!secao || !grade) return;

    var p = filtrosAtuais();
    // A matriz combina as duas versoes do indice, entao nao faz sentido
    // filtrar por uma delas nem por nivel de risco isolado.
    ["classe", "versao", "busca"].forEach(function (c) { p.delete(c); });

    var dados = await buscarJson("/api/indicadores/matriz/?" + p.toString());

    if (!dados.previsao_disponivel) {
      // Acontece no ano mais antigo da base: ha indice, mas nao ha previsao,
      // porque o modelo precisa do par de anos. A secao sai da tela em vez de
      // mostrar quatro zeros, que pareceriam ausencia de escolas.
      grade.innerHTML = "";
      secao.hidden = true;
      if (estado.grupo) selecionarGrupo(null, { recarregar: false });
      return dados;
    }
    secao.hidden = false;

    grade.innerHTML = "";
    var maior = dados.grupos.reduce(function (m, g) { return Math.max(m, g.escolas); }, 0);

    grade.appendChild(celulaVazia());

    dados.eixo_coluna.forEach(function (rotulo, i) {
      grade.appendChild(rotuloDeEixo("matriz-eixo-coluna", rotulo, i + 2, 1));
    });
    dados.eixo_linha.forEach(function (rotulo, i) {
      grade.appendChild(rotuloDeEixo("matriz-eixo-linha", rotulo, 1, i + 2));
    });
    // Ordem do DOM e a de prioridade, e nao a da grade. Em tela larga o CSS
    // reposiciona os cartoes nos quadrantes; em tela estreita, onde a grade
    // colapsa em uma coluna, a ordem que sobra e a util: a acao mais urgente
    // primeiro. E tambem a ordem em que um leitor de tela percorre os cartoes.
    dados.grupos
      .slice()
      .sort(function (a, b) { return a.urgencia - b.urgencia; })
      .forEach(function (g) {
        grade.appendChild(cartaoDoGrupo(g, maior));
      });

    if (nota) {
      // Frase montada aqui, e nao concatenando a explicacao vinda da API: a
      // explicacao e escrita no singular ("a escola nao aparece...") e emendada
      // depois de "Outras 103" produzia plural com singular e maiuscula no meio
      // da frase.
      var texto =
        numero(dados.escolas_com_previsao, 0) + " escolas com índice e previsão.";
      if (dados.sem_previsao.escolas) {
        texto += " Outras " + numero(dados.sem_previsao.escolas, 0) +
          " ficam de fora por não aparecerem nos dois anos que o modelo exige, " +
          "e seguem no ranking.";
      }
      nota.textContent = texto;
    }

    // O grupo escolhido continua valendo depois de trocar de UF ou de ano, mas
    // as contagens mudam, entao o painel do grupo precisa ser reescrito.
    if (estado.grupo) {
      var atual = dados.grupos.filter(function (g) { return g.grupo === estado.grupo; })[0];
      if (atual) mostrarGrupoEscolhido(atual);
    }
    return dados;
  }

  function celulaVazia() {
    var el = document.createElement("span");
    el.className = "matriz-canto";
    el.setAttribute("aria-hidden", "true");
    return el;
  }

  function rotuloDeEixo(classe, texto, coluna, linha) {
    var el = document.createElement("p");
    el.className = classe;
    el.textContent = texto;
    // Posicao vai como variavel CSS, nunca como grid-column inline: estilo
    // inline vence media query, e a grade precisa poder colapsar em uma coluna
    // na tela estreita.
    el.style.setProperty("--col", String(coluna));
    el.style.setProperty("--linha", String(linha));
    // Escondido do leitor de tela de proposito: o cartao ja diz a sua condicao
    // por escrito, e anunciar os eixos de novo seria repeticao.
    el.setAttribute("aria-hidden", "true");
    return el;
  }

  function cartaoDoGrupo(g, maior) {
    var botao = document.createElement("button");
    botao.type = "button";
    botao.className = "matriz-cartao " + (CLASSE_DO_GRUPO[g.tarja] || "grupo-neutro");
    botao.style.setProperty("--col", String(g.coluna + 2));
    botao.style.setProperty("--linha", String(g.linha + 2));
    botao.setAttribute("aria-pressed", estado.grupo === g.grupo ? "true" : "false");

    function parte(classe, texto) {
      var el = document.createElement("span");
      el.className = classe;
      el.textContent = texto;
      botao.appendChild(el);
    }

    parte("prioridade", "Prioridade " + g.urgencia);
    parte("nome", g.rotulo);
    parte(
      "quantidade",
      numero(g.escolas, 0) + (g.proporcao === null ? "" : " · " + numero(g.proporcao, 1) + "%")
    );
    parte("condicao", g.condicao);

    var barra = document.createElement("span");
    barra.className = "proporcao-barra";
    barra.setAttribute("aria-hidden", "true");
    barra.style.width = (maior ? Math.round((g.escolas / maior) * 100) : 0) + "%";
    botao.appendChild(barra);

    // O nome acessivel reune tudo numa frase, para que o leitor de tela nao
    // anuncie fragmentos soltos.
    botao.setAttribute(
      "aria-label",
      g.rotulo + ", prioridade " + g.urgencia + ". " + g.condicao + ". " +
      numero(g.escolas, 0) + " escolas. Selecionar este grupo."
    );

    botao.addEventListener("click", function () {
      selecionarGrupo(estado.grupo === g.grupo ? null : g.grupo);
    });
    return botao;
  }

  function mostrarGrupoEscolhido(g) {
    var caixa = document.getElementById("grupo-escolhido");
    if (!caixa) return;
    caixa.hidden = false;
    caixa.className = "grupo-escolhido " + (CLASSE_DO_GRUPO[g.tarja] || "grupo-neutro");
    document.getElementById("grupo-nome").textContent =
      g.rotulo + " · " + numero(g.escolas, 0) + " escolas";
    document.getElementById("grupo-explicacao").textContent = g.explicacao;
    document.getElementById("grupo-acao").textContent =
      g.acao + " " + explicarOrdem(g.grupo);
  }

  // Com um grupo ativo o seletor de versao perde o sentido: a matriz ja usa as
  // duas leituras ao mesmo tempo. Em vez de ignorar a escolha em silencio, o
  // campo e desabilitado e o motivo aparece no texto de ajuda.
  function ajustarSeletorDeVersao() {
    if (!campoVersao) return;
    campoVersao.disabled = Boolean(estado.grupo);
    if (!estado.grupo) return;
    campoVersao.value = "regras-v1";
    if (ajudaVersao) {
      ajudaVersao.textContent =
        "Enquanto um grupo está selecionado, o ranking combina o índice atual " +
        "e a previsão. Limpe a seleção para escolher uma leitura só.";
    }
  }

  function selecionarGrupo(grupo, opcoes) {
    estado.grupo = grupo;
    estado.pagina = 1;

    document.querySelectorAll(".matriz-cartao").forEach(function (b) {
      b.setAttribute("aria-pressed", "false");
    });
    if (!grupo) {
      var caixa = document.getElementById("grupo-escolhido");
      if (caixa) caixa.hidden = true;
    }

    ajustarSeletorDeVersao();

    if (!opcoes || opcoes.recarregar !== false) {
      atualizar(grupo ? "Filtrando pelo grupo selecionado." : "Mostrando todas as escolas.");
    }
  }

  // ----------------------------------------------------- estado na URL
  /*
    Os filtros e o grupo escolhido vao para a barra de enderecos. Sem isso o
    painel nao tem como ser compartilhado: a pessoa que encontra as 2.367
    escolas em deterioracao no Acre nao consegue mandar essa tela para ninguem,
    e recarregar a pagina joga tudo fora. Tambem faz o botao de voltar do
    navegador se comportar como se espera.
  */
  var CAMPOS_NA_URL = ["uf", "ano", "classe", "busca", "versao"];

  function lerUrl() {
    var p = new URLSearchParams(location.search);
    CAMPOS_NA_URL.forEach(function (chave) {
      var campo = form.elements[chave];
      var valor = p.get(chave);
      if (!campo || !valor) return;
      // Valor fora das opcoes existentes e ignorado, e nao aplicado as cegas.
      if (campo.tagName === "SELECT") {
        var existe = Array.prototype.some.call(campo.options, function (o) {
          return o.value === valor;
        });
        if (!existe) return;
      }
      campo.value = valor;
    });

    var grupo = p.get("grupo");
    if (grupo) estado.grupo = grupo;

    var pagina = parseInt(p.get("pagina"), 10);
    if (pagina > 0) estado.pagina = pagina;

    ajustarSeletorDeVersao();
  }

  function escreverUrl() {
    var p = filtrosAtuais();
    if (estado.grupo) p.set("grupo", estado.grupo);
    if (estado.pagina > 1) p.set("pagina", String(estado.pagina));
    var consulta = p.toString();
    history.replaceState(null, "", consulta ? "?" + consulta : location.pathname);
  }

  // ------------------------------------------------------------ orquestracao
  function descreverVersao() {
    if (!campoVersao || !ajudaVersao) return;
    // Com um grupo ativo quem manda no texto de ajuda e ajustarSeletorDeVersao,
    // que explica por que o campo esta desabilitado. Sobrescrever aqui deixaria
    // na tela a descricao de uma leitura que nao esta sendo usada.
    if (estado.grupo) return;
    ajudaVersao.textContent = DESCRICOES[campoVersao.value] || "";
  }

  async function atualizar(mensagem) {
    anunciar(mensagem || "Atualizando dados.");
    if (conteudo) conteudo.classList.add("carregando");
    descreverVersao();
    try {
      await Promise.all([
        carregarResumo(), carregarDispersao(), carregarRanking(), carregarMatriz(),
      ]);
      anunciar(
        "Dados atualizados. " + numero(estado.total, 0) +
        " escolas na seleção, página " + estado.pagina + " de " + estado.totalPaginas + "."
      );
    } catch (erro) {
      anunciar("Não foi possível carregar os dados: " + erro.message);
      console.error(erro);
    } finally {
      if (conteudo) conteudo.classList.remove("carregando");
      escreverUrl();
    }
  }

  form.addEventListener("submit", function (evento) {
    evento.preventDefault();
    estado.pagina = 1;
    atualizar("Aplicando filtros.");
  });

  if (btnLimpar) {
    btnLimpar.addEventListener("click", function () {
      form.reset();
      if (campoVersao) campoVersao.disabled = false;
      selecionarGrupo(null, { recarregar: false });
      estado.pagina = 1;
      atualizar("Filtros limpos.");
    });
  }
  if (campoVersao) {
    campoVersao.addEventListener("change", function () {
      estado.pagina = 1;
      atualizar("Mudando a forma de calcular o risco.");
    });
  }

  /*
    Redesenho do grafico ao abrir o painel de contexto.

    Chart.js dimensiona o canvas pelo tamanho do container. Dentro de um
    <details> fechado o container tem altura e largura zero, entao o grafico
    desenhado ali sai vazio e permanece vazio depois de aberto. Redesenhar no
    evento `toggle` resolve, e so custa quando a pessoa realmente abre.
  */
  var panorama = document.querySelector(".panorama");
  if (panorama) {
    panorama.addEventListener("toggle", function () {
      if (!panorama.open) return;
      if (graficoDispersao) {
        graficoDispersao.resize();
      } else {
        carregarDispersao();
      }
    });
  }

  var btnGrupoLimpar = document.getElementById("grupo-limpar");
  if (btnGrupoLimpar) {
    btnGrupoLimpar.addEventListener("click", function () {
      selecionarGrupo(null);
    });
  }

  btnAnterior.addEventListener("click", function () {
    if (estado.pagina > 1) { estado.pagina -= 1; atualizar("Carregando página anterior."); }
  });
  btnProxima.addEventListener("click", function () {
    if (estado.pagina < estado.totalPaginas) { estado.pagina += 1; atualizar("Carregando próxima página."); }
  });

  lerUrl();
  atualizar("Carregando dados.");
})();
