"""
Cliente da API de localidades do IBGE.

Atende ao requisito de consumo de API externa do enunciado do PI.
Endpoint: https://servicodados.ibge.gov.br/api/v1/localidades
Publico, gratuito e sem autenticacao.

Politica de uso: a resposta e gravada na tabela Municipio e reaproveitada. A API
nao e chamada a cada requisicao do painel, so quando o cache esta vazio ou
quando a sincronizacao e pedida explicitamente. Falha de rede nunca derruba a
pagina: o painel continua funcionando com o que ja esta no banco.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BASE = "https://servicodados.ibge.gov.br/api/v1/localidades"


class ErroIBGE(RuntimeError):
    """Falha ao consultar a API do IBGE."""


def _uf_e_regiao(municipio):
    """
    Extrai sigla da UF e nome da regiao do JSON do IBGE.

    O caminho canonico passa por microrregiao > mesorregiao > UF, mas em alguns
    municipios microrregiao vem nula. Nesses casos cai para regiao-imediata >
    regiao-intermediaria > UF, que carrega a mesma informacao.
    """
    caminhos = (
        ("microrregiao", "mesorregiao"),
        ("regiao-imediata", "regiao-intermediaria"),
    )
    for externo, interno in caminhos:
        no = (municipio.get(externo) or {}).get(interno) or {}
        uf = no.get("UF") or {}
        if uf.get("sigla"):
            return uf["sigla"], (uf.get("regiao") or {}).get("nome", "")
    return "", ""


def buscar_municipios(uf=None, timeout=None):
    """
    Consulta a API e devolve a lista de municipios ja normalizada.

    Com `uf` busca so aquela unidade federativa, o que e bem mais rapido que
    baixar os mais de cinco mil municipios do pais.
    """
    url = f"{BASE}/estados/{uf}/municipios" if uf else f"{BASE}/municipios"
    timeout = timeout or getattr(settings, "IBGE_TIMEOUT", 8)

    try:
        resposta = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
        resposta.raise_for_status()
        dados = resposta.json()
    except requests.RequestException as exc:
        raise ErroIBGE(f"Falha ao consultar a API do IBGE em {url}: {exc}") from exc
    except ValueError as exc:
        raise ErroIBGE(f"A API do IBGE devolveu conteudo que nao e JSON: {exc}") from exc

    normalizados = []
    for m in dados:
        sigla, regiao = _uf_e_regiao(m)
        normalizados.append(
            {
                "codigo_ibge": str(m["id"]),
                "nome": m["nome"],
                "uf": sigla,
                "regiao": regiao,
            }
        )
    return normalizados


def sincronizar_municipios(uf=None):
    """
    Grava os municipios da API no banco e devolve quantos foram criados e
    atualizados. Idempotente: rodar duas vezes nao duplica registro.
    """
    from painel.models import Municipio

    registros = buscar_municipios(uf=uf)

    ja_existiam = set(
        Municipio.objects.filter(
            codigo_ibge__in=[r["codigo_ibge"] for r in registros]
        ).values_list("codigo_ibge", flat=True)
    )

    # Upsert em lote. Com update_or_create por municipio seriam mais de 11 mil
    # consultas para os 5.571 municipios do pais: em SQLite local passa, mas
    # contra o Neon, com latencia de rede em cada ida, levaria varios minutos.
    Municipio.objects.bulk_create(
        [
            Municipio(
                codigo_ibge=r["codigo_ibge"],
                nome=r["nome"],
                uf=r["uf"],
                regiao=r["regiao"],
            )
            for r in registros
        ],
        batch_size=1000,
        update_conflicts=True,
        update_fields=["nome", "uf", "regiao"],
        unique_fields=["codigo_ibge"],
    )

    criados = sum(1 for r in registros if r["codigo_ibge"] not in ja_existiam)
    atualizados = len(registros) - criados

    logger.info("IBGE sincronizado: %s criados, %s atualizados", criados, atualizados)
    return criados, atualizados


def municipios_em_cache(uf=None):
    """Le do banco, sem tocar na rede. E o que o painel usa."""
    from painel.models import Municipio

    qs = Municipio.objects.all()
    if uf:
        qs = qs.filter(uf=uf.upper())
    return qs


# ---------------------------------------------------------------- socioeconomico
#
# Segunda API do IBGE consumida pelo projeto, a de indicadores do panorama
# municipal (a mesma que alimenta cidades.ibge.gov.br).
#
# Por que ela existe aqui. O indice de risco reserva 0,15 do peso ao contexto
# socioeconomico. A fonte pretendida era o INSE do INEP, que nao e publicado de
# forma cruzavel: ele esta nos microdados do Saeb 2023, mas com os codigos de
# escola mascarados por LGPD, o que impede a juncao pelo codigo do Censo. O
# salario medio municipal ocupa essa vaga como proxy territorial, e e nomeado
# como tal em todo lugar: nunca como INSE.
BASE_INDICADORES = "https://servicodados.ibge.gov.br/api/v1/pesquisas/indicadores"

# Salario medio mensal dos trabalhadores formais, em salarios minimos.
INDICADOR_SALARIO_MEDIO = 29765

# A API devolve o codigo do municipio com 6 digitos, sem o digito verificador,
# enquanto o projeto guarda os 7 digitos do IBGE. A conversao e so truncar.
def _codigo_curto(codigo_ibge: str) -> str:
    return str(codigo_ibge)[:6]


def buscar_salario_medio(codigos_ibge, timeout=None, tamanho_lote=200):
    """
    Busca o salario medio mensal de cada municipio.

    Recebe codigos de 7 digitos e devolve {codigo_7_digitos: (valor, ano)}.
    Municipio sem dado publicado simplesmente nao aparece no resultado, em vez
    de entrar com zero: zero seria um municipio sem nenhuma renda, o que falseia
    o indice para baixo.
    """
    timeout = timeout or getattr(settings, "IBGE_TIMEOUT", 20)
    codigos = [str(c) for c in codigos_ibge]
    por_curto = {_codigo_curto(c): c for c in codigos}
    resultado = {}

    for inicio in range(0, len(codigos), tamanho_lote):
        lote = codigos[inicio : inicio + tamanho_lote]
        alvo = "|".join(_codigo_curto(c) for c in lote)
        url = f"{BASE_INDICADORES}/{INDICADOR_SALARIO_MEDIO}/resultados/{alvo}"
        try:
            resposta = requests.get(url, timeout=timeout)
            resposta.raise_for_status()
            dados = resposta.json()
        except (requests.RequestException, ValueError) as erro:
            raise ErroIBGE(f"Falha ao consultar o IBGE em {url}: {erro}") from erro

        for indicador in dados:
            for serie in indicador.get("res", []):
                curto = str(serie.get("localidade", ""))
                completo = por_curto.get(curto)
                if not completo:
                    continue
                valores = {
                    ano: v
                    for ano, v in (serie.get("res") or {}).items()
                    if v not in (None, "", "-", "..", "...")
                }
                if not valores:
                    continue
                ano = max(valores)
                try:
                    resultado[completo] = (float(valores[ano]), int(ano))
                except (TypeError, ValueError):
                    continue

    return resultado


def sincronizar_salario_medio(uf=None):
    """
    Preenche o salario medio dos municipios no banco. Idempotente.

    Devolve (preenchidos, sem_dado).
    """
    from painel.models import Municipio

    qs = Municipio.objects.all()
    if uf:
        qs = qs.filter(uf=uf.upper())
    codigos = list(qs.values_list("codigo_ibge", flat=True))
    if not codigos:
        return 0, 0

    valores = buscar_salario_medio(codigos)

    objetos = []
    for municipio in qs:
        par = valores.get(municipio.codigo_ibge)
        if not par:
            continue
        municipio.salario_medio, municipio.salario_medio_ano = par
        objetos.append(municipio)

    Municipio.objects.bulk_update(
        objetos, ["salario_medio", "salario_medio_ano"], batch_size=1000
    )

    logger.info(
        "Salario medio sincronizado: %s preenchidos, %s sem dado",
        len(objetos),
        len(codigos) - len(objetos),
    )
    return len(objetos), len(codigos) - len(objetos)
