"""
Paleta do painel e calculo de contraste da WCAG 2.1.

Este modulo e a fonte unica de verdade das cores. O CSS repete os mesmos valores
hexadecimais, e existe teste automatizado que falha se o CSS divergir daqui ou se
qualquer par deixar de atender ao contraste minimo. Assim a acessibilidade de cor
nao depende de alguem lembrar de conferir.

Criterios atendidos:
  1.4.3 Contraste Minimo, nivel AA: 4,5:1 para texto normal.
  1.4.11 Contraste Nao Textual, nivel AA: 3:1 para elementos graficos.
"""

from __future__ import annotations

BRANCO = "#FFFFFF"

# Pares de texto sobre fundo usados nas tarjas de risco.
# A cor nunca aparece sozinha: sempre acompanhada do rotulo textual, por causa do
# criterio 1.4.1 Uso da Cor, nivel A.
TARJAS = {
    "alto": {"texto": "#7F1D1D", "fundo": "#FEE2E2"},
    "medio": {"texto": "#713F12", "fundo": "#FEF3C7"},
    "baixo": {"texto": "#14532D", "fundo": "#DCFCE7"},
}

# Cores de serie nos graficos, avaliadas contra o fundo branco da area de plotagem.
GRAFICO = {
    "alto": "#B91C1C",
    "medio": "#A16207",
    "baixo": "#15803D",
    "neutro": "#1D4ED8",
}

# Texto e interface.
FUNDO_SUAVE = "#F3F4F6"

TEXTO = "#1F2937"
TEXTO_SECUNDARIO = "#4B5563"
LINK = "#1D4ED8"
FOCO = "#1D4ED8"
BORDA = "#6B7280"

CONTRASTE_MINIMO_TEXTO = 4.5
CONTRASTE_MINIMO_GRAFICO = 3.0


def _canal(c: float) -> float:
    """Linearizacao de canal conforme a formula de luminancia relativa da WCAG."""
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminancia(hexcor: str) -> float:
    """Luminancia relativa de uma cor hexadecimal, de 0 (preto) a 1 (branco)."""
    h = hexcor.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        raise ValueError(f"Cor hexadecimal invalida: {hexcor!r}")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _canal(r) + 0.7152 * _canal(g) + 0.0722 * _canal(b)


def contraste(cor_a: str, cor_b: str) -> float:
    """
    Razao de contraste entre duas cores, de 1:1 a 21:1.

    Formula da WCAG 2.1: (L1 + 0,05) / (L2 + 0,05), com L1 sendo a maior das
    duas luminancias.
    """
    l1, l2 = sorted((luminancia(cor_a), luminancia(cor_b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def todos_os_hex() -> set[str]:
    """Todos os valores hexadecimais da paleta, em maiusculas."""
    valores = {BRANCO, FUNDO_SUAVE, TEXTO, TEXTO_SECUNDARIO, LINK, FOCO, BORDA}
    valores |= set(GRAFICO.values())
    for par in TARJAS.values():
        valores |= set(par.values())
    return {v.upper() for v in valores}
