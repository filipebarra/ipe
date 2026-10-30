"""Protocolo de exibição com etapas no visualizador (0.88) — o que a mamografia tem, para TC, RM…

Ao abrir um exame cujo protocolo (Preferências ▸ Protocolos de exibição) tem etapas, o exame abre
na etapa 1; ← → (ou a barra de etapas) passam de uma para a outra. Cada etapa diz o layout e, para
cada quadro, a série (com alternativas em ordem de preferência), o plano, MIP/MinIP/média com a
espessura, a janela, a cor, onde entrar na pilha e quais quadros andam juntos.

Como na mamografia, a etapa é **da estação**, não de um monitor: com o exame repartido entre telas,
passar de etapa numa passa em todas, e cada tela mostra o pedaço dela (`hanging.parte_da_tela`).

Quadro cuja série não existe no exame não fica vazio calado: mostra "Série não encontrada" com o que
foi procurado, e a barra de estado diz quantos faltaram.
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import QComboBox, QLabel, QToolBar

from ipe.ui.viewer import hanging as H

log = logging.getLogger(__name__)


class Sessao:
    """O protocolo com etapas em uso numa aba."""

    def __init__(self, proto: dict, monitor: int = 0, telas: int = 1):
        self.proto = proto
        self.steps = H.etapas(proto)
        self.indice = 0
        self.monitor = int(monitor or 0)
        self.telas = max(1, int(telas or 1))
        self._cand: dict[bool, list] = {}
        self.prior_uid: str | None = None
        self.prior_procurado = False

    @property
    def nome(self) -> str:
        return self.proto.get("name", "") or "Protocolo"

    def candidatos(self, tab, anterior: bool) -> list:
        """(uid, palavras, texto) das séries do exame atual — ou do anterior."""
        if anterior and not self.prior_procurado:
            self.prior_procurado = True
            try:
                self.prior_uid = tab._hanging_prior(self.proto)
            except Exception:  # noqa: BLE001
                log.exception("anterior do protocolo")
                self.prior_uid = None
            if self.prior_uid:
                tab.add_study_silent(self.prior_uid)
        if anterior not in self._cand:
            alvo = self.prior_uid if anterior else tab.study_uid
            if not alvo:
                self._cand[anterior] = []
            else:
                linhas = [s for s in tab.series if s.study_uid == alvo and s.num_images]
                self._cand[anterior] = [(s.series_uid, *H.series_words(tab.repo, s)) for s in linhas]
        return self._cand[anterior]


def achar(settings, mods: set, descricao: str) -> dict | None:
    """O protocolo **com etapas** deste exame (o primeiro ativo que combinar), ou None."""
    proto = H.find_protocol(settings, mods, descricao)
    return proto if H.tem_etapas(proto) else None


def iniciar(tab, proto: dict, monitor: int = 0, telas: int = 1) -> bool:
    tab.exib = Sessao(proto, monitor, telas)
    ok = aplicar_etapa(tab, 0, propagar=False)
    if not ok:
        tab.exib = None
    sincronizar_barra(tab)
    return ok


def _janela(vp, valor: str, settings) -> None:
    valor = (valor or "").strip()
    if not valor:
        return
    if "/" in valor:
        try:
            w, lv = (float(x.replace(",", ".")) for x in valor.split("/", 1))
            vp.set_window(w, lv)
        except ValueError:
            log.info("janela %r do protocolo não entendida", valor)
        return
    vp.apply_preset(valor)


def _posicao(vp, pos: str, centro) -> None:
    n = len(vp.frames or [])
    if not n or pos == "auto":
        return
    if pos == "inicio":
        vp.set_index_silently(0)
    elif pos == "meio":
        vp.set_index_silently(n // 2)
    elif pos == "ponto" and centro is not None:
        plano = getattr(vp, "mpr_plane", None)
        try:
            if plano is not None and hasattr(plano, "index_for_point"):
                vp.set_index_silently(int(plano.index_for_point(centro)))
            else:
                from ipe.imaging.series import quadro_na_posicao
                vp.set_index_silently(quadro_na_posicao(vp.frames, centro))
        except Exception:  # noqa: BLE001
            log.debug("posição do quadro", exc_info=True)


def aplicar_etapa(tab, i: int, propagar: bool = True) -> bool:
    """Monta a etapa `i` na aba. Devolve False quando nenhum quadro achou série."""
    sess = getattr(tab, "exib", None)
    if sess is None or not sess.steps:
        return False
    i = max(0, min(len(sess.steps) - 1, int(i)))
    st = H.parte_da_tela(sess.steps[i], sess.telas, sess.monitor)
    centro = None
    if tab.active is not None and tab.active.frames:
        try:
            centro = tab.active.ponto_central()
        except Exception:  # noqa: BLE001
            centro = None
    if getattr(tab, "dyn", None) is not None:
        # a etapa anterior abriu a avaliação dinâmica: ela fecha ao passar de etapa
        try:
            tab.close_dynamic(restore=False)
        except Exception:  # noqa: BLE001
            log.exception("fechar a dinâmica da etapa")
        tab._dyn_saved = None
    din = H.etapa(sess.steps[i]).get("dinamica")
    if din and sess.monitor == 0:
        return _etapa_dinamica(tab, sess, i, din, propagar)
    try:
        tab.hub.unlink(list(tab.viewports))
    except Exception:  # noqa: BLE001
        pass
    tab.set_layout(st["rows"], st["cols"])
    usados: set[str] = set()
    grupos: dict[int, list] = {}
    faltaram: list[str] = []
    achados = 0
    for q, vp in zip(st["cells"], tab.viewports):
        vp.empty_note = ""
        if not q["series"]:
            vp.clear()
            continue
        if q["fase"]:
            try:
                nota = _quadro_da_fase(tab, sess, vp, q, centro)
            except Exception:  # noqa: BLE001
                log.exception("quadro da fase, protocolo %r, etapa %d", sess.nome, i + 1)
                nota = "Não foi possível montar este quadro."
            if nota:
                vp.clear()
                vp.empty_note = nota
                faltaram.append(q["series"].split("|")[0])
            else:
                achados += 1
            if q["sync"] and not nota:
                grupos.setdefault(q["sync"], []).append(vp)
            continue
        uid = H.escolher_serie(q["series"], sess.candidatos(tab, q["prior"]), usados)
        if uid is None:
            vp.clear()
            onde = " no exame anterior" if q["prior"] else ""
            vp.empty_note = f"Série não encontrada{onde}:\n{q['series'].replace('|', ' ou ')}"
            faltaram.append(q["series"].split("|")[0])
            continue
        usados.add(uid)
        achados += 1
        try:
            tab.load_series_into(vp, uid)
            nota = _montar(tab, vp, q, uid, None, None, "", centro)
            if nota:
                vp.empty_note = nota
        except Exception:  # noqa: BLE001 - um quadro que falha não derruba a etapa
            log.exception("quadro do protocolo %r, etapa %d", sess.nome, i + 1)
        if q["sync"]:
            grupos.setdefault(q["sync"], []).append(vp)
    for vs in grupos.values():
        try:
            tab.hub.link_all(vs)
        except Exception:  # noqa: BLE001
            log.debug("sincronia da etapa", exc_info=True)
    sess.indice = i
    if tab.viewports:
        tab._activate(tab.viewports[0])
    tab.hanging_name = sess.nome
    tab.update_reference_lines()
    sincronizar_barra(tab)
    if hasattr(tab, "update_render3d_bar"):
        tab.update_render3d_bar()
    if getattr(tab.active, "mpr_plane", None) is not None and hasattr(tab, "_sync_slab_controls"):
        tab._sync_slab_controls(tab.active)
    msg = f"Etapa {i + 1} de {len(sess.steps)} ({sess.steps[i]['name']}) — protocolo {sess.nome}"
    if faltaram:
        msg += f". Sem série para {len(faltaram)} quadro(s): {', '.join(faltaram[:3])}"
    tab.status_message.emit(msg)
    if propagar:
        for t in tab.irmaos():
            if getattr(t, "exib", None) is not None:
                aplicar_etapa(t, i, propagar=False)
    return achados > 0


def _reconstrucao(vp, q: dict, sufixo: str) -> None:
    """MIP/MinIP/média do quadro já reconstruído: a espessura escolhida ou, com "metade", a metade
    do paciente inteira (a meia mama)."""
    from ipe.imaging.volume import SLAB_MODES
    pl = vp.mpr_plane
    modo = q["recon"] or "mip"
    if q["metade"]:
        idx, mm = metade_do_plano(pl, q["metade"])
        pl.set_slab(mm, modo)
        vp.set_index_silently(idx)
        lado = "direita" if q["metade"] == "direita" else "esquerda"
        vp.series_label = f"Mama {lado}: {SLAB_MODES[modo]}{sufixo}"
    else:
        mm = float(q["slab"] or 10)
        pl.set_slab(mm, modo)
        vp.series_label = f"MPR {pl.name}  {SLAB_MODES[modo]} {mm:.0f} mm{sufixo}"
    vp._qimage_key = None
    vp._load_current()


def metade_do_plano(pl, metade: str) -> tuple[int, float]:
    """(corte do centro, espessura em mm) para o MIP que pega só a metade direita ou esquerda do
    paciente. O meio é o centro do campo de visão, na direção direita-esquerda (x do paciente:
    negativo = direita). O plano precisa andar em x (sagital)."""
    import numpy as np
    n = pl.n
    x0, x1 = float(pl.position(0)[0]), float(pl.position(n - 1)[0])
    if abs(x1 - x0) < 1e-6:
        return n // 2, pl.step_mm * n
    meio = n / 2.0
    # metade "baixa" dos índices é a de x menor (direita do paciente) quando x cresce com o índice
    direita_embaixo = x1 > x0
    quer_baixa = (metade == "direita") == direita_embaixo
    lo, hi = (0, int(np.floor(meio))) if quer_baixa else (int(np.ceil(meio)), n)
    centro = (lo + hi - 1) // 2
    largura = max(1, hi - lo)
    # _extract usa centro ± round(mm / passo / 2): largura - 1 cortes cobrem lo..hi-1
    return centro, max(pl.step_mm, (largura - 1) * pl.step_mm)


#: as Vistas da barra do 3D: (giro, elevação) da câmera
def _vistas() -> dict:
    from ipe.ui.viewer.render3d_view import VISTAS
    return {nome.lower(): (az, el) for nome, az, el in VISTAS}


def _aplicar_vista(tab, vp, vista: str) -> None:
    """De que lado se olha. No 3D é a câmera (como o menu Vistas da barra). Num corte, é o espelho
    que deixa a imagem como ela apareceria olhando daquele lado — só se o corte for daquele plano
    (vista lateral num sagital, frontal num coronal, de cima/baixo num axial)."""
    import numpy as np
    az, el = _vistas()[vista]
    v3 = getattr(vp, "render3d", None)
    if v3 is not None:
        v3.set_view(az, el)
        return
    f = vp.current_frame()
    if f is None or f.orientation is None:
        return
    from ipe.imaging.render3d import rotation
    u, v, d = rotation(az, el)
    o = np.asarray(f.orientation, float)
    linha, coluna = o[:3], o[3:]
    if abs(float(np.dot(np.cross(linha, coluna), d))) < 0.7:
        tab.status_message.emit(f"Vista {vista}: este quadro não é um corte visto desse lado.")
        return
    melhor, nota_m = (0, False, False), -9.0
    for rot in (0, 90, 180, 270):
        for fh in (False, True):
            for fv in (False, True):
                vp.state.rot, vp.state.flip_h, vp.state.flip_v = rot, fh, fv
                tela = vp.display_orientation()
                nota = float(np.dot(tela[:3], u) + np.dot(tela[3:], v)) - 0.001 * (rot / 90 + fh + fv)
                if nota > nota_m:
                    melhor, nota_m = (rot, fh, fv), nota
    vp.set_orientation(*melhor)


def _montar(tab, vp, q: dict, uid: str, frames, chave, sufixo: str, centro) -> str:
    """Do quadro já carregado com a série (ou a fase) até o que o protocolo pede: o plano, a
    reconstrução (espessura, MPR fino, MIP 3D ou VR), a metade, a janela, a cor e a vista.
    Devolve "" ou o aviso para o quadro."""
    recon = q["recon"]
    if recon in H.RECONS_3D:
        # o mesmo 3D do botão 3D: um volume próprio por quadro, com a barra do 3D inteira
        v = tab.abrir_3d_no_quadro(vp, uid, H.RECONS_3D[recon], frames=frames, chave=chave)
        if v is None:
            return f"Não deu para montar o 3D{sufixo}: memória ou volume."
        nome = H.RECON_CURTO[recon]
        if q["metade"]:
            v.r.cut_at(v.r.center, "right" if q["metade"] == "direita" else "left")
            v.title = f"Mama {q['metade']}: {nome}{sufixo}"
        else:
            v.title = f"{nome}{sufixo}"
        vp.series_label = v.title
        _acabamento(tab, vp, q, centro)
        if v.mode == "mip" and not q["window"]:
            _janela_do_mip(v)
        v.refresh(fast=False)
        return ""
    plano = q["plane"]
    if recon and not plano:
        plano = vp.plano_nome() if vp.plano_nome() in ("Axial", "Coronal", "Sagital") else "Axial"
    if plano:
        rotulo = f"Reconstrução {plano}{sufixo}"
        if not tab.plano_no_quadro(vp, uid, plano, frames=frames, chave=chave, rotulo=rotulo):
            return f"Não deu para reconstruir em {plano}{sufixo}: memória ou volume."
        if recon and recon != "mpr" and vp.mpr_plane is not None:
            _reconstrucao(vp, q, sufixo)
        elif vp.mpr_plane is not None:
            vp.series_label = f"MPR {vp.mpr_plane.name}{sufixo}"
        if vp.mpr_plane is not None and hasattr(tab, "registrar_recon"):
            # 0.93: a barra do 3D vale para esta reconstrução, que vira 3D quando ele mexer nela
            tab.registrar_recon(vp, uid, frames, chave)
    elif sufixo:
        vp.series_label = f"{vp.series_label}{sufixo}"
    _acabamento(tab, vp, q, centro)
    return ""


def _janela_do_mip(v) -> None:
    """Janela do MIP 3D tirada da própria projeção (do fundo ao realce), e não da janela do corte:
    o MIP junta o máximo de cada raio e estouraria a janela de um corte."""
    import numpy as np
    try:
        px = np.asarray(v.image().pixels, float)
        dentro = px[px > float(np.percentile(px, 5))]
        if dentro.size < 16:
            return
        lo, hi = float(np.percentile(dentro, 1)), float(np.percentile(dentro, 99.9))
        if hi > lo:
            v.lo, v.hi = lo, hi
    except Exception:  # noqa: BLE001
        log.debug("janela do MIP 3D", exc_info=True)


def _acabamento(tab, vp, q: dict, centro) -> None:
    _janela(vp, q["window"], tab.settings)
    if q["cmap"]:
        vp.set_colormap(q["cmap"])
    if not q["metade"] and getattr(vp, "render3d", None) is None:
        _posicao(vp, q["pos"], centro)
    if q["vista"]:
        _aplicar_vista(tab, vp, q["vista"])
    vp.update()


def _quadro_da_fase(tab, sess, vp, q: dict, centro) -> str:
    """Quadro que pede uma fase da dinâmica (e, talvez, o MIP de meia mama). Devolve "" quando
    montou, ou o aviso para o quadro."""
    cand = [c for c in sess.candidatos(tab, q["prior"]) if tab.grupo_dinamico_de(c[0]) is not None]
    uid = H.escolher_serie(q["series"], cand, set())
    onde = " no exame anterior" if q["prior"] else ""
    if uid is None:
        return f"Dinâmica não encontrada{onde}:\n{q['series'].replace('|', ' ou ')}"
    gid, _f = tab.grupo_dinamico_de(uid)
    g = tab.groups[gid]
    phases, rotulos = tab._group_phases(g)
    k = H.fase_indice(q["fase"], len(phases))
    if k is None:
        return f"A dinâmica tem {len(phases)} fase(s); falta: {H.fase_texto(q['fase'])}."
    sufixo = f" — {H.fase_texto(q['fase'])}"
    tab._load_group(vp, gid, k)
    separadas = not g.get("fases") and k < len(g.get("series_uids") or [])
    serie = g["series_uids"][k] if separadas else g["series_uids"][0]
    chave = f"etapa:{serie}" if separadas else f"etapa:fase:{gid}:{k}"
    if not q["plane"] and not q["recon"]:
        vp.series_label = f"{vp.series_label}{sufixo}"
        _acabamento(tab, vp, q, centro)
        return ""
    return _montar(tab, vp, q, serie, phases[k], chave, sufixo, centro)


def _etapa_dinamica(tab, sess, i: int, din: dict, propagar: bool) -> bool:
    """Etapa que abre a avaliação dinâmica (0.94) — o mesmo do botão Dinâmica, sem a janela: as fases
    vêm da dinâmica do exame (a série do protocolo, ou a detecção automática) e os parâmetros são os
    pré-configurados (ou os últimos usados, se ele escolheu assim); o layout dos mapas é o da etapa."""
    from ipe.ui.viewer import dinamica_config as DC
    from ipe.ui.viewer.dynamic import DynamicDialog
    pre = None
    cand = [c for c in sess.candidatos(tab, False) if tab.grupo_dinamico_de(c[0]) is not None]
    uid = H.escolher_serie(din["series"], cand, set())
    if uid is not None:
        gid, _f = tab.grupo_dinamico_de(uid)
        g = tab.groups[gid]
        pre = list(g["series_uids"][:1] if g.get("fases") else g["series_uids"])
    previous = DC.parametros_iniciais(tab.settings)
    # o layout é o da etapa: pelo nome (0.99.9), ou pelo número dos protocolos gravados antes disso
    lay = DC.escolher(tab.settings, din.get("layout", 0), din.get("layout_nome", ""))
    previous["layout"] = DC.nomes(tab.settings).index(lay["nome"])
    previous["layout_nome"] = lay["nome"]
    dlg = DynamicDialog(tab, pre, previous)
    dset, params = dlg.dset, dlg.params()
    dlg.deleteLater()
    nota = ""
    if dset is None:
        nota = "Avaliação dinâmica: as fases da dinâmica não foram encontradas neste exame."
    elif not params["pre"] < params["early"] <= params["late"]:
        nota = "Avaliação dinâmica: a fase inicial precisa vir depois do pré-contraste."
    ok = False
    if not nota:
        try:
            ok = tab.start_dynamic(dset, params)
        except Exception:  # noqa: BLE001
            log.exception("dinâmica da etapa")
        if not ok:
            nota = "Avaliação dinâmica: não foi possível calcular os mapas."
    sess.indice = i
    tab.hanging_name = sess.nome
    sincronizar_barra(tab)
    if nota:
        tab.set_layout(1, 1)
        vp = tab.viewports[0]
        vp.clear()
        vp.empty_note = nota
        tab.status_message.emit(nota)
    else:
        tab.status_message.emit(f"Etapa {i + 1} de {len(sess.steps)} ({sess.steps[i]['name']}) — avaliação "
                                f"dinâmica, protocolo {sess.nome}")
    if propagar:
        for t in tab.irmaos():
            if getattr(t, "exib", None) is not None:
                aplicar_etapa(t, i, propagar=False)
    return ok


def passo(tab, d: int) -> None:
    sess = getattr(tab, "exib", None)
    if sess is None:
        return
    novo = sess.indice + d
    if not 0 <= novo < len(sess.steps):
        tab.status_message.emit("Esta é a última etapa." if d > 0 else "Esta é a primeira etapa.")
        return
    aplicar_etapa(tab, novo)


def encerrar(tab) -> None:
    tab.exib = None
    sincronizar_barra(tab)


# ------------------------------------------------------------------ gravar a tela como etapa
def gravar_tela(tab) -> dict:
    """A etapa que reproduz o que está na tela agora: layout e, por quadro, série, plano, MIP,
    janela, cor e sincronia. É o jeito rápido de montar um protocolo: arrumar e gravar."""
    rows, cols = tab._layout
    presets = tab.settings.get("viewer.wl_presets", {}) or {}
    grupos: dict[int, int] = {}
    cells = []
    for vp in tab.viewports[: rows * cols]:
        uid = tab._source_series(vp) if vp.frames else None
        s = tab._series_row(uid) if uid else None
        if s is None:
            cells.append(H.quadro(""))
            continue
        serie = (s.description or "").strip() or (s.modality or "")
        q = {"series": serie, "prior": s.study_uid != tab.study_uid}
        from ipe.imaging.volume import MPRPlane
        plano = getattr(vp, "mpr_plane", None)
        if isinstance(plano, MPRPlane) and plano.name in ("Axial", "Coronal", "Sagital"):
            q["plane"] = plano.name
            if float(getattr(plano, "slab_mm", 0) or 0) > 0:
                q["recon"] = plano.mode
                q["slab"] = float(plano.slab_mm)
            else:
                q["recon"] = "mpr"
        v3 = getattr(vp, "render3d", None)
        if v3 is not None and v3.mode in ("mip", "vr"):
            q["recon"] = "mip3d" if v3.mode == "mip" else "vr"
            q["vista"] = next((nome for nome, (az, el) in _vistas().items()
                               if abs((v3.az - az + 180) % 360 - 180) < 1 and abs(v3.el - el) < 1), "")
        if vp.state.window_set:
            w, lv = float(vp.state.width), float(vp.state.level)
            chave = next((k for k, (_n, pw, pl) in presets.items()
                          if abs(float(pw) - w) < 0.5 and abs(float(pl) - lv) < 0.5), "")
            q["window"] = chave or f"{w:g}/{lv:g}"
        if vp.state.cmap:
            q["cmap"] = vp.state.cmap
        g = tab.hub.group_of(vp)
        if g is not None:
            q["sync"] = grupos.setdefault(g, len(grupos) + 1)
        cells.append(H.quadro(q))
    return H.etapa({"name": "Etapa", "rows": rows, "cols": cols, "cells": cells})


def salvar_etapa(settings, etapa: dict, nome_proto: str, modalidade: str = "", descricao: str = "",
                 substituir: int | None = None) -> dict:
    """Grava `etapa` no protocolo `nome_proto` (cria o protocolo se não existir). Devolve o protocolo."""
    protos = [dict(p) for p in H.protocols(settings)]
    proto = next((p for p in protos if p.get("name") == nome_proto), None)
    if proto is None:
        proto = {"name": nome_proto, "modality": modalidade.upper(), "description": descricao,
                 "enabled": True, "prior": False, "steps": []}
        protos.append(proto)
    novo = H.convertido(proto)
    passos = list(novo.get("steps") or [])
    if not H.tem_etapas(proto) and not proto.get("layout") and not proto.get("cells"):
        passos = []
    if substituir is not None and 0 <= substituir < len(passos):
        passos[substituir] = etapa
    else:
        passos.append(etapa)
    novo["steps"] = passos
    protos[protos.index(proto)] = novo
    settings.set("hanging_protocols", protos)
    settings.save()
    return novo


# ------------------------------------------------------------------ barra
class EtapasBar(QToolBar):
    """Barra do protocolo com etapas: nome, etapa atual (escolher), ◀ ▶, gravar a tela, editar."""

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.setStyleSheet("QToolBar{background:#1f2c33;color:#ddd;spacing:6px}QLabel{color:#ddd}"
                           "QToolButton{color:#e8e8e8;padding:2px 6px}QToolButton:hover{background:#2f4450}")
        self.l_nome = QLabel("")
        self.addWidget(self.l_nome)
        self.addWidget(QLabel(" etapa:"))
        self.c_step = QComboBox()
        self.c_step.setMinimumWidth(240)
        self.c_step.activated.connect(self._escolheu)
        self.addWidget(self.c_step)
        for texto, dica, d in (("◀", "Etapa anterior (←)", -1), ("▶", "Próxima etapa (→)", 1)):
            a = self.addAction(texto)
            a.setToolTip(dica)
            a.triggered.connect(lambda _=False, k=d: passo(tab, k))
        self.addSeparator()
        a = self.addAction("Gravar a tela como etapa…")
        a.setToolTip("Grava o que está na tela agora (layout, séries, planos, MIP, janela, cor) como uma "
                     "etapa deste protocolo, ou de um protocolo novo")
        a.triggered.connect(lambda: tab.gravar_tela_como_etapa())
        a = self.addAction("Editar protocolos…")
        a.triggered.connect(lambda: tab.editar_protocolos())
        a = self.addAction("Sair do protocolo")
        a.setToolTip("Deixa os quadros como estão e esconde esta barra")
        a.triggered.connect(lambda: encerrar(tab))
        self.setVisible(False)

    def _escolheu(self, i: int) -> None:
        sess = getattr(self.tab, "exib", None)
        if sess is not None and 0 <= i < len(sess.steps):
            aplicar_etapa(self.tab, i)

    def sync(self) -> None:
        sess = getattr(self.tab, "exib", None)
        self.setVisible(sess is not None)
        if sess is None:
            return
        self.l_nome.setText(f"  {sess.nome}")
        self.c_step.blockSignals(True)
        self.c_step.clear()
        for k, st in enumerate(sess.steps):
            self.c_step.addItem(f"{k + 1}. {st['name']}")
        self.c_step.setCurrentIndex(sess.indice)
        self.c_step.blockSignals(False)


def sincronizar_barra(tab) -> None:
    barra = getattr(tab, "etapas_bar", None)
    if barra is not None:
        barra.sync()
