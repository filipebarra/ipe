"""Quem vê cada configuração (0.99.26, etapa 2 do plano do modo de uso).

Pedido dele: nas configurações (nós DICOM, servidores e regras de impressão…) escolher **compartilhado,
compartilhar com usuários escolhidos ou pessoal**. Decisões dele: o administrador vê o que é dos
outros; "faça o que achar melhor" para o resto — e o melhor me pareceu: o administrador **vê e edita**
o pessoal dos outros na tela de configuração (marcado "de fulano"), mas nas escolhas do dia a dia (com
que nó buscar, para onde mandar) aparecem só o compartilhado, o dele e o que compartilharam com ele.

Cada item guarda dois campos:

- `dono`: "" = do serviço (todos veem); um usuário = pessoal dele;
- `visivel_para`: outros usuários que também veem (separados por vírgula), quando há dono.

A visão é a da sessão aberta. No servidor central cada pedido de cliente roda com a visão de quem
pediu (`com_visao`), e não com a de quem está logado na tela do servidor.
"""
from __future__ import annotations

import contextlib
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class Visao:
    usuario: str
    admin: bool = False


_ctx: ContextVar[Visao | None] = ContextVar("visao_ipe", default=None)
_FORCADA: ContextVar[bool] = ContextVar("visao_forcada", default=False)
_SESSAO: ContextVar[object] = ContextVar("sessao_forcada", default=None)


def _da_sessao(s) -> Visao | None:
    nome = str(getattr(s, "username", "") or "")
    if not nome or nome == "sistema":
        return None                          # "só eu" sem usuário: tudo é de todos
    return Visao(nome, str(getattr(s, "role", "")) == "admin")


def visao_atual() -> Visao | None:
    """A visão de quem está pedindo. None = sem filtro (modo só eu, sessão do sistema)."""
    if _FORCADA.get():
        return _ctx.get()
    from ipe.auth import session as S
    try:
        return _da_sessao(S.get())
    except Exception:  # noqa: BLE001
        return None


@contextlib.contextmanager
def com_visao(sessao):
    """O pedido de um cliente no servidor central enxerga o que **ele** enxerga."""
    t1 = _ctx.set(_da_sessao(sessao))
    t2 = _FORCADA.set(True)
    t3 = _SESSAO.set(sessao)
    try:
        yield
    finally:
        _SESSAO.reset(t3)
        _FORCADA.reset(t2)
        _ctx.reset(t1)


def pode(perm: str) -> bool:
    """A permissão de quem está pedindo (no servidor, a do cliente; 0.99.29)."""
    s = _SESSAO.get() if _FORCADA.get() else None
    if s is None:
        from ipe.auth import session as S
        try:
            s = S.get()
        except Exception:  # noqa: BLE001
            return True
    try:
        return bool(s.can(perm))
    except Exception:  # noqa: BLE001
        return False


def lista(texto) -> list[str]:
    if isinstance(texto, (list, tuple, set)):
        return [str(x).strip() for x in texto if str(x).strip()]
    return [x.strip() for x in str(texto or "").split(",") if x.strip()]


def visivel(item, visao: Visao | None, gerenciar: bool = False) -> bool:
    """O item aparece para esta visão? `gerenciar` = tela de configuração (o administrador vê tudo)."""
    if visao is None:
        return True
    dono = str(_get(item, "dono") or "").strip()
    if not dono:
        return True
    u = visao.usuario.lower()
    if dono.lower() == u or u in (x.lower() for x in lista(_get(item, "visivel_para"))):
        return True
    return bool(gerenciar and visao.admin)


def filtrar(itens, visao: Visao | None = None, gerenciar: bool = False, *, usar_sessao: bool = True) -> list:
    v = visao if visao is not None or not usar_sessao else visao_atual()
    return [x for x in itens if visivel(x, v, gerenciar)]


def padrao_novo(visao: Visao | None = None) -> dict:
    """Item novo: o administrador cria do serviço; os outros, pessoal."""
    v = visao if visao is not None else visao_atual()
    if v is None or v.admin:
        return {"dono": "", "visivel_para": ""}
    return {"dono": v.usuario, "visivel_para": ""}


def rotulo(item, visao: Visao | None = None) -> str:
    """'Todos', 'Só eu', 'Eu + ana, bia', 'de fulano', 'de fulano + ana'."""
    v = visao if visao is not None else visao_atual()
    dono = str(_get(item, "dono") or "").strip()
    outros = lista(_get(item, "visivel_para"))
    if not dono:
        return "Todos"
    if v is not None and dono.lower() == v.usuario.lower():
        return "Só eu" if not outros else "Eu + " + ", ".join(outros)
    return f"de {dono}" + (" + " + ", ".join(outros) if outros else "")


def _get(item, k):
    if isinstance(item, dict):
        return item.get(k, "")
    return getattr(item, k, "")


def modo_com_usuarios(settings) -> bool:
    """O campo "Visível para" só faz sentido quando há várias pessoas (não no "só eu")."""
    try:
        from ipe.auth import modo as MODO
        return MODO.modo_atual(settings) != "um"
    except Exception:  # noqa: BLE001
        return True
