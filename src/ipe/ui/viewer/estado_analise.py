"""Estado salvo da análise (0.99.58, item 6 do backlog — plano AW F3).

Pedido: *"reabrir como deixou; carregar ou fundir o anterior"*; decisão dele (04/11/2026): **só no Ipê** (no
banco deste computador, ou no servidor central para todas as estações; não vai junto com o exame).

O que se guarda ao fechar o exame (um estado por exame e por usuário):
- o layout, o quadro ativo e a ferramenta do botão esquerdo;
- em cada quadro: a série (ou a dinâmica agrupada, ou as imagens-chave), de qual exame, o corte (e a fração,
  para séries que mudaram de tamanho), a fase, e a vista — janela, zoom, pan, inversão, tabela de cores,
  giro, espelhos e filtro;
- os exames anteriores trazidos para a aba;
- os painéis abertos (Medidas, Lesões);
- os parâmetros da dinâmica e se o MPR estava ligado (os dois se religam com um clique: refazer a conta ao
  abrir o exame seria esperar sem ter pedido).

Ao abrir, Configurações ▸ Visualizador ▸ Estado da análise decide: reabrir sempre (padrão), perguntar ou
nunca. Não reabre quando o exame veio com séries escolhidas, repartido entre monitores, no modo mamografia
ou em reunião — nesses casos quem manda é o protocolo.

**Carregar** a montagem do anterior: o layout e as vistas do exame anterior do mesmo paciente, cada quadro
com a série equivalente deste exame (mesma modalidade e descrição). **Fundir**: o anterior entra na aba, com
os quadros dele como estavam, ao lado dos deste exame.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QPointF

log = logging.getLogger(__name__)

VERSAO = 1
CHAVE_AO_ABRIR = "viewer.estado_ao_abrir"
AO_ABRIR = {"sempre": "Reabrir como deixei", "perguntar": "Perguntar", "nunca": "Abrir como de fábrica"}
VIRTUAIS = ("mpr:", "dyn:", "dynph:")


def usuario_atual() -> str:
    try:
        from ipe.auth import session as S
        u = S.get()
        return (u.username or "") if u is not None else ""
    except Exception:  # noqa: BLE001
        return ""


# ------------------------------------------------------------------ capturar
def vista(vp) -> dict:
    st = vp.state
    return {"width": float(st.width), "level": float(st.level), "window_set": bool(st.window_set),
            "zoom": float(st.zoom), "pan": [float(st.pan.x()), float(st.pan.y())], "invert": bool(st.invert),
            "cmap": st.cmap or "", "rot": int(st.rot), "flip_h": bool(st.flip_h), "flip_v": bool(st.flip_v),
            "filter": st.filter or ""}


def quadro(vp, tab) -> dict:
    uid = vp.series_uid or ""
    if not uid or uid.startswith(VIRTUAIS):
        return {"series": ""}
    n = len(vp.frames)
    row = tab._series_row(uid) if ":" not in uid else None
    return {"series": uid, "study": vp.study_uid or "", "index": int(vp.index), "n": n,
            "fracao": (vp.index / (n - 1)) if n > 1 else 0.5, "phase": int(vp.phase or 0),
            "modality": (row.modality if row is not None else "") or "",
            "desc": (row.description if row is not None else "") or "", "vista": vista(vp)}


def capturar(tab) -> dict:
    n = tab._layout[0] * tab._layout[1]
    vps = tab.viewports[:n]
    # na dinâmica e no MPR, os quadros mostram mapas e reconstruções: o que vale é o arranjo de antes
    salvo = tab._dyn_saved or tab._mpr_saved
    quadros = [quadro(v, tab) for v in vps]
    layout = list(tab._layout)
    if salvo is not None:
        layout = list(salvo[0])
        quadros = [{"series": u, "index": int(i), "vista": None} if u and not str(u).startswith(VIRTUAIS)
                   else {"series": ""} for u, i in list(salvo[1])[: layout[0] * layout[1]]]
    ativo = vps.index(tab.active) if tab.active in vps else 0
    dyn = None
    if tab.dyn is not None:
        dyn = {k: v for k, v in (getattr(tab.dyn, "params", None) or {}).items()}
    mpr = None
    if tab.mpr_active:
        mpr = {"series": (tab._mpr_saved[1][0][0] if tab._mpr_saved and tab._mpr_saved[1] else "")}
    return {"versao": VERSAO, "layout": layout, "quadros": quadros, "ativo": ativo,
            "ferramenta": getattr(tab, "left_tool", "wl"), "anteriores": list(tab.study_order[1:]),
            "paineis": {"medidas": bool(getattr(tab, "measures_action", None) and tab.measures_action.isChecked()),
                        "lesoes": bool(getattr(tab, "lesions_action", None) and tab.lesions_action.isChecked())},
            "dinamica": dyn, "mpr": mpr}


def vale_a_pena(dados: dict) -> bool:
    return any(q.get("series") for q in (dados or {}).get("quadros", []))


# ------------------------------------------------------------------ aplicar
def aplicar_vista(vp, v: dict | None) -> None:
    if not v:
        return
    st = vp.state
    st.invert = bool(v.get("invert", False))
    st.rot = int(v.get("rot", 0)) % 360
    st.flip_h, st.flip_v = bool(v.get("flip_h", False)), bool(v.get("flip_v", False))
    if v.get("filter"):
        try:
            vp.set_filter(v["filter"])
        except Exception:  # noqa: BLE001
            log.debug("filtro %s", v["filter"], exc_info=True)
    if v.get("cmap"):
        try:
            vp.set_colormap(v["cmap"])
        except Exception:  # noqa: BLE001
            log.debug("cores %s", v["cmap"], exc_info=True)
    if v.get("window_set"):
        vp.set_window(float(v["width"]), float(v["level"]), emit=False)
    pan = v.get("pan") or [0, 0]
    vp.set_zoom_pan(float(v.get("zoom", 1.0) or 1.0), QPointF(float(pan[0]), float(pan[1])))
    vp.update()


def _por_quadro(tab, vp, q: dict, serie: str | None = None) -> bool:
    uid = serie or q.get("series") or ""
    if not uid:
        return False
    try:
        if uid.startswith("group:"):
            gid = int(uid.split(":")[1])
            if gid not in tab.groups:
                return False
            tab.load_series_into(vp, uid, phase=int(q.get("phase", 0) or 0))
        elif uid.startswith("key:"):
            tab.load_series_into(vp, uid)
        else:
            if tab._series_row(uid) is None:
                return False
            tab.load_series_into(vp, uid, como_serie=True)
        n = len(vp.frames)
        if n:
            idx = int(q.get("index", 0))
            if q.get("n") and int(q["n"]) != n:
                idx = round(float(q.get("fracao", 0.5)) * (n - 1))
            vp.set_index_silently(max(0, min(n - 1, idx)))
        aplicar_vista(vp, q.get("vista"))
        return True
    except Exception:  # noqa: BLE001
        log.exception("restaurar o quadro %s", uid)
        return False


def restaurar(tab, dados: dict) -> list[str]:
    """Põe a aba como estava. Devolve os avisos (o que não deu para refazer)."""
    avisos = []
    for ant in dados.get("anteriores") or []:
        if ant not in tab.study_order:
            try:
                tab.add_study(ant, colocar=False)
            except Exception:  # noqa: BLE001
                avisos.append("um exame anterior não abriu")
    lay = dados.get("layout") or [1, 1]
    tab.set_layout(int(lay[0]), int(lay[1]))
    quadros = dados.get("quadros") or []
    faltou = 0
    for vp, q in zip(tab.viewports, quadros):
        if not q.get("series"):
            continue
        if not _por_quadro(tab, vp, q):
            faltou += 1
    if faltou:
        avisos.append(f"{faltou} série(s) não estão mais no exame")
    ligar_anteriores(tab)
    i = int(dados.get("ativo", 0) or 0)
    if 0 <= i < len(tab.viewports):
        tab._activate(tab.viewports[i])
    ferr = dados.get("ferramenta")
    if ferr:
        try:
            tab.set_left_tool(ferr)
        except Exception:  # noqa: BLE001
            pass
    pan = dados.get("paineis") or {}
    for chave, nome in (("medidas", "measures_action"), ("lesoes", "lesions_action")):
        a = getattr(tab, nome, None)
        if pan.get(chave) and a is not None and not a.isChecked():
            a.trigger()
    tab.update_reference_lines()
    return avisos


def ligar_anteriores(tab) -> int:
    """Quadros de exames anteriores voltam ligados ao atual pelo alinhamento salvo (como no botão Anteriores)."""
    n = tab._layout[0] * tab._layout[1]
    vps = [v for v in tab.viewports[:n] if v.series_uid and v.frames]
    atual = next((v for v in vps if v.study_uid == tab.study_uid), None)
    if atual is None:
        return 0
    k = 0
    for v in vps:
        if v.study_uid and v.study_uid != tab.study_uid:
            try:
                k += int(bool(tab.hub.apply_saved(atual, v)))
            except Exception:  # noqa: BLE001
                log.debug("ligar o anterior", exc_info=True)
    return k


def montagem_do_anterior(tab, dados: dict) -> int:
    """Carrega a montagem de outro exame: o layout e as vistas, com as séries equivalentes deste exame."""
    from ipe.ui.viewer.viewer_tab import match_series
    lay = dados.get("layout") or [1, 1]
    tab.set_layout(int(lay[0]), int(lay[1]))
    deste = [s for s in tab.series if s.study_uid == tab.study_uid]
    usados: set[str] = set()
    n = 0
    for vp, q in zip(tab.viewports, dados.get("quadros") or []):
        if not q.get("series") or str(q["series"]).startswith(("key:", "group:")):
            continue
        ref = type("Ref", (), {"modality": q.get("modality", ""), "description": q.get("desc", "")})()
        livres = [s for s in deste if s.series_uid not in usados]
        m = match_series(ref, livres)
        if m is None or (m.modality != ref.modality and ref.modality):
            continue
        usados.add(m.series_uid)
        if _por_quadro(tab, vp, {**q, "n": 0}, serie=m.series_uid):
            n += 1
    if tab.viewports:
        tab._activate(tab.viewports[0])
    tab.update_reference_lines()
    return n


def fundir_anterior(tab, uid_anterior: str, dados: dict) -> int:
    """O anterior entra na aba com os quadros dele como estavam, ao lado dos deste exame."""
    if uid_anterior not in tab.study_order:
        tab.add_study(uid_anterior, colocar=False)
    n_atual = tab._layout[0] * tab._layout[1]
    atuais = [(vp.series_uid, vp.index, vista(vp), vp.phase) for vp in tab.viewports[:n_atual]
              if vp.series_uid and not vp.series_uid.startswith(VIRTUAIS)]
    do_anterior = [q for q in dados.get("quadros") or [] if q.get("series")]
    total = len(atuais) + len(do_anterior)
    if not do_anterior:
        return 0
    rows, cols = tab._layout_for(total)
    tab.set_layout(rows, cols)
    for vp, (uid, idx, v, ph) in zip(tab.viewports, atuais):
        _por_quadro(tab, vp, {"series": uid, "index": idx, "vista": v, "phase": ph})
    n = 0
    for vp, q in zip(tab.viewports[len(atuais):], do_anterior):
        if _por_quadro(tab, vp, q):
            n += 1
    ligar_anteriores(tab)
    tab.update_reference_lines()
    return n
