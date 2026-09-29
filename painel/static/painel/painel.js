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

  var estado = { pagina: 1, totalPaginas: 1, total: 0 };
  var graficoClasses = null;
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
  }

  function marcarComDados(idCanvas) {
    var canvas = document.getElementById(idCanvas);
    if (canvas) canvas.hidden = false;
    var aviso = document.getElementById(idCanvas + "-vazio");
    if (aviso) aviso.hidden = true;
  }

  function filtrosAtuais() {
    var dados = new FormData(form);
    var p = new URLSearchParams();
    ["uf", "ano", "classe"].forEach(function (chave) {
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

    desenharClasses(dados.risco_por_classe);
    preencherTabelaClasses(dados.risco_por_classe);
    return dados;
  }

  function desenharClasses(porClasse) {
    var ctx = document.getElementById("g-classes");
    if (!ctx) return;
    var total = porClasse.reduce(function (s, i) { return s + i.escolas; }, 0);
    if (!total) {
      marcarSemDados("g-classes", "Nenhuma escola com índice de risco na seleção atual.");
      return;
    }
    marcarComDados("g-classes");
    var rotulos = porClasse.map(function (i) { return i.rotulo; });
    var valores = porClasse.map(function (i) { return i.escolas; });
    var cores = porClasse.map(function (i) {
      return GRAFICO[i.classe] || GRAFICO.neutro;
    });

    if (graficoClasses) graficoClasses.destroy();
    graficoClasses = new Chart(ctx, {
      type: "bar",
      data: {
        labels: rotulos,
        datasets: [{ label: "Escolas", data: valores, backgroundColor: cores }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, title: { display: true, text: "Quantidade de escolas" } },
          x: { title: { display: true, text: "Nível de risco" } },
        },
      },
    });
  }

  function preencherTabelaClasses(porClasse) {
    var corpo = document.querySelector("#t-classes tbody");
    corpo.innerHTML = "";
    porClasse.forEach(function (i) {
      var tr = document.createElement("tr");
      var th = document.createElement("th");
      th.scope = "row";
      th.textContent = i.rotulo;
      var td = document.createElement("td");
      td.className = "numero";
      td.textContent = numero(i.escolas, 0);
      tr.appendChild(th);
      tr.appendChild(td);
      corpo.appendChild(tr);
    });
  }

  // ------------------------------------------------------------ dispersao
  async function carregarDispersao() {
    var p = filtrosAtuais();
    p.delete("classe");
    var dados = await buscarJson("/api/indicadores/dispersao/?" + p.toString());
    desenharDispersao(dados.pontos);
    preencherTabelaDispersao(dados.pontos);
  }

  function desenharDispersao(pontos) {
    var ctx = document.getElementById("g-dispersao");
    if (!ctx) return;
    if (!pontos.length) {
      marcarSemDados(
        "g-dispersao",
        "Gráfico indisponível: depende do indicador de nível socioeconômico (INSE) " +
        "do INEP, que ainda não foi carregado na base. As demais informações da " +
        "página não são afetadas."
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
          data: pontos.map(function (p) { return { x: p.inse, y: p.taxa_abandono }; }),
          backgroundColor: GRAFICO.neutro,
          pointRadius: 3,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { title: { display: true, text: "INSE (nível socioeconômico)" } },
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
      td.textContent = "Sem dados: o indicador INSE ainda não foi carregado.";
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
        [numero(p.inse, 2), numero(p.taxa_abandono)].forEach(function (v) {
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

      var tdScore = document.createElement("td");
      tdScore.className = "numero";
      tdScore.textContent = numero(r.score, 3);
      tr.appendChild(tdScore);

      // Tarja com cor E texto. Sem o texto, a informacao dependeria da cor.
      var tdNivel = document.createElement("td");
      var span = document.createElement("span");
      span.className = "tarja tarja-" + r.classe;
      span.textContent = r.rotulo;
      tdNivel.appendChild(span);
      tr.appendChild(tdNivel);

      corpoRanking.appendChild(tr);
    });

    pagInfo.textContent =
      "Página " + estado.pagina + " de " + estado.totalPaginas +
      " (" + numero(estado.total, 0) + " escolas)";
    btnAnterior.disabled = estado.pagina <= 1;
    btnProxima.disabled = estado.pagina >= estado.totalPaginas;
    return dados;
  }

  // ------------------------------------------------------------ orquestracao
  async function atualizar(mensagem) {
    anunciar(mensagem || "Atualizando dados.");
    try {
      await Promise.all([carregarResumo(), carregarDispersao(), carregarRanking()]);
      anunciar(
        "Dados atualizados. " + numero(estado.total, 0) +
        " escolas na seleção, página " + estado.pagina + " de " + estado.totalPaginas + "."
      );
    } catch (erro) {
      anunciar("Não foi possível carregar os dados: " + erro.message);
      console.error(erro);
    }
  }

  form.addEventListener("submit", function (evento) {
    evento.preventDefault();
    estado.pagina = 1;
    atualizar("Aplicando filtros.");
  });

  btnAnterior.addEventListener("click", function () {
    if (estado.pagina > 1) { estado.pagina -= 1; atualizar("Carregando página anterior."); }
  });
  btnProxima.addEventListener("click", function () {
    if (estado.pagina < estado.totalPaginas) { estado.pagina += 1; atualizar("Carregando próxima página."); }
  });

  atualizar("Carregando dados.");
})();
