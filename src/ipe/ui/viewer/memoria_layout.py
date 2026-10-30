"""Memória do layout: o exame abre como ele deixou da última vez, sem configurar nada.

A ideia, nas palavras dele: "quando eu abrir uma ressonância de ombro, eu vou ajustar o layout e
quando fechar o sistema vai memorizar". É um protocolo de exibição que ninguém escreve — o uso é
que escreve.

Por que não é a mesma coisa que a aba Protocolos de exibição: aquilo é uma regra **declarada**,
que diz também quais séries vão em quais quadros. Isto aqui é só a **grade**, aprendida sozinha,
e por isso perde para qualquer protocolo que ele tenha escrito: escolha explícita manda sobre
hábito observado.

O que **não** é guardado, de propósito: quais séries estavam em quais quadros. Repetir a grade
erra pouco — repetir a série errada no quadro errado é pior que não fazer nada, porque parece
certo. Quem quiser isso escreve um protocolo.
"""

from __future__ import annotations

import re
import unicodedata

CHAVE = "viewer.layout_lembrado"
MAX = 300                       # mais que isso é lixo de anos; o mais antigo sai primeiro

# Palavras que não mudam o arranjo: lado, contraste, aparelho. Sem tirá-las, "RM OMBRO DIREITO" e
# "RM OMBRO ESQUERDO" seriam dois exames diferentes para a memória, e ele teria de ensinar duas
# vezes a mesma coisa.
RUIDO = {"DIREITO", "DIREITA", "ESQUERDO", "ESQUERDA", "DIR", "ESQ", "D", "E", "BILATERAL",
         "AMBOS", "COM", "SEM", "E", "DE", "DO", "DA", "DOS", "DAS", "CONTRASTE", "CONTRASTADA",
         "CONTRASTADO", "ENDOVENOSO", "EV", "SIMPLES"}


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def chave(modalidades, descricao: str) -> str:
    """A etiqueta do exame para a memória: modalidade + as palavras que importam da descrição.

    Números somem (data, número do protocolo, "3 FASES" viraria outro exame a cada variação) e
    as palavras de ruído também. "RM OMBRO DIREITO C/ CONTRASTE" e "RM Ombro esquerdo" caem na
    mesma etiqueta: `MR|OMBRO`.
    """
    mods = "+".join(sorted({str(m).upper() for m in (modalidades or set()) if m}))
    bruto = _sem_acento(str(descricao or "")).upper()
    # Palavra de uma letra só nunca distingue exame ("c/ contraste" vira "C"); fora.
    palavras = [p for p in re.split(r"[^A-Z]+", bruto) if len(p) > 1 and p not in RUIDO]
    return f"{mods}|{' '.join(palavras)}".strip()


def sufixo_das_telas(telas: int, tela: int) -> str:
    """O que distingue a memória de um monitor da do outro.

    Com duas telas o médico não quer a mesma grade nas duas: ele põe as sagitais numa e as
    axiais noutra, em arranjos diferentes. E a memória de uma tela não serve para quando ele
    abre o mesmo exame em três — por isso a quantidade também entra na etiqueta.
    """
    n = max(1, int(telas or 1))
    if n <= 1:
        return ""
    k = min(max(0, int(tela or 0)), n - 1)
    return f"|{n}t{k + 1}"


def lembrado(settings, etiqueta: str) -> tuple[int, int] | None:
    """A grade que ele deixou da última vez neste tipo de exame, ou None."""
    if settings is None or not etiqueta:
        return None
    guardados = settings.get(CHAVE, {}) or {}
    valor = guardados.get(etiqueta)
    if not isinstance(valor, (list, tuple)) or len(valor) != 2:
        return None
    try:
        linhas, colunas = int(valor[0]), int(valor[1])
    except (TypeError, ValueError):
        return None
    return (linhas, colunas) if 1 <= linhas <= 4 and 1 <= colunas <= 6 else None


def lembrar(settings, etiqueta: str, layout) -> bool:
    """Guarda a grade deste tipo de exame. Devolve se mudou alguma coisa."""
    if settings is None or not etiqueta or not layout:
        return False
    try:
        linhas, colunas = int(layout[0]), int(layout[1])
    except (TypeError, ValueError, IndexError):
        return False
    if not (1 <= linhas <= 4 and 1 <= colunas <= 6):
        return False
    guardados = dict(settings.get(CHAVE, {}) or {})
    if guardados.get(etiqueta) == [linhas, colunas]:
        guardados.pop(etiqueta)                 # tira e põe de volta: o mais usado fica por último
        guardados[etiqueta] = [linhas, colunas]
        settings.set(CHAVE, guardados)
        return False
    guardados.pop(etiqueta, None)
    guardados[etiqueta] = [linhas, colunas]
    while len(guardados) > MAX:
        guardados.pop(next(iter(guardados)))
    settings.set(CHAVE, guardados)
    return True


def esquecer(settings, etiqueta: str = "") -> None:
    """Apaga uma etiqueta (ou tudo). Não há botão para isto: existe para o programa e os testes."""
    if settings is None:
        return
    if not etiqueta:
        settings.set(CHAVE, {})
        return
    guardados = dict(settings.get(CHAVE, {}) or {})
    if guardados.pop(etiqueta, None) is not None:
        settings.set(CHAVE, guardados)
