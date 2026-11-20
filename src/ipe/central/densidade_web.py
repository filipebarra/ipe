"""0.100.50: a densidade mamária no Ipê Web — o mesmo botão Densidade do Ipê de mesa.

Pergunta dele (15/11/2026): *"a densidade mamária não vai para o ipeweb?"* — agora vai. A mesma medida
(`imaging/densidade_revisao`: a rede da NYU nas quatro incidências 2D do exame, guardada em `revisao_ia`, módulo
"densidade") e a mesma confirmação (estado aceito/editado e a linha em `revisao_densidade`, que dá a concordância).
Medir no navegador é medir no servidor: ele lê o exame do banco dele e roda a rede.

- ver e medir: quem abre o exame (`view`);
- confirmar é ato médico: precisa da permissão de escrever laudos (`report`);
- a frase do laudo é a mesma do Ipê (`frase_do_laudo`).

Cada medida e confirmação fica no registro de acesso (ação `densidade`).
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

_TRAVAS: dict[str, threading.Lock] = {}
_TRAVA = threading.Lock()


def _exame(c, s, study: str) -> None:
    if not s.can("view"):
        raise PermissionError("sem permissão")
    if not study or not c.pode_ver(s, study):
        raise PermissionError("exame não visível")


def _saida(m: dict | None, s) -> dict:
    from ipe.imaging import densidade_revisao as R
    if not m:
        return {"medida": None, "pode_confirmar": s.can("report")}
    out = {k: m.get(k) for k in ("nyu", "nyu_probs", "nyu_aviso", "avisos", "aparelho", "quando", "categoria",
                                 "estado", "revisor", "confirmado_em")}
    out["avisos"] = list(out.get("avisos") or [])
    out["frase"] = R.frase_do_laudo(m.get("categoria") or m.get("nyu") or "")
    return {"medida": out, "pode_confirmar": s.can("report"),
            "frases": {k: R.frase_do_laudo(k) for k in R.CATEGORIAS}}


def ver(c, s, study: str) -> dict:
    from ipe.imaging import densidade_revisao as R
    _exame(c, s, study)
    return _saida(R.guardada(c.repo, study), s)


def medir(c, s, study: str, de_novo: bool = False) -> dict:
    """Mede no servidor (uma vez por exame de cada vez) e guarda; com medida guardada, só a devolve."""
    from ipe.imaging import densidade_revisao as R
    _exame(c, s, study)
    with _TRAVA:
        trava = _TRAVAS.setdefault(study, threading.Lock())
    with trava:
        if not de_novo:
            g = R.guardada(c.repo, study)
            if g:
                return _saida(g, s)
        m = R.medir_exame(c.repo, study)
        if m.get("nyu"):
            R.guardar_medida(c.repo, study, m)
        c.repo.audit("densidade", f"medida pelo navegador: {(m.get('nyu') or '—').upper()}", user=s.username,
                     study_uid=study)
        return _saida(R.guardada(c.repo, study) or m, s)


def confirmar(c, s, study: str, categoria: str) -> dict:
    from ipe.imaging import densidade_revisao as R
    _exame(c, s, study)
    if not s.can("report"):
        raise PermissionError("confirmar a densidade pede a permissão de escrever laudos")
    categoria = str(categoria or "").lower()
    if categoria not in R.CATEGORIAS:
        raise ValueError("categoria inválida (a, b, c ou d)")
    m = R.guardada(c.repo, study)
    if not m:
        raise ValueError("o exame ainda não foi medido")
    R.confirmar(c.repo, study, m, categoria, s.username)
    c.repo.audit("densidade", f"confirmada pelo navegador: {categoria.upper()} (rede {(m.get('nyu') or '—').upper()})",
                 user=s.username, study_uid=study)
    gravar_sr(c, s, study)                        # 0.100.57: tudo confirmado → o SR no exame
    return _saida(R.guardada(c.repo, study), s)


def gravar_sr(c, s, study: str) -> None:
    """0.100.57: com a densidade e as calcificações confirmadas, grava o SR e as imagens marcadas (em segundo plano)."""
    import threading

    from ipe.ai import mama_sr as MS
    db, storage = getattr(c, "db", None), getattr(c, "storage", None)
    if db is None or storage is None:
        return
    from ipe.automation import mama_auto as MA
    settings = getattr(c, "settings", None)
    sem = MA.sem_conferir(settings)

    def trabalho():
        out = MS.depois_de_confirmar(c.repo, db, storage, study, s.full_name or s.username, sem_conferir=sem)
        if out:                                    # 0.100.78: e para o PACS, se configurado
            try:
                MS.enviar(getattr(c, "net", None), c.repo, settings, study, out)
            except Exception:  # noqa: BLE001
                pass
    threading.Thread(target=trabalho, daemon=True, name="mama-sr").start()
