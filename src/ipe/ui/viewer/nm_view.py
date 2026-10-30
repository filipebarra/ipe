"""Medicina nuclear na tela: vistas separadas, ANT/POST lado a lado e média geométrica.

Um arquivo de medicina nuclear costuma trazer várias imagens no mesmo cubo (ANT e POST do
corpo inteiro, duas janelas de energia da paratireoide, as fases do trifásico). O módulo
`imaging.nm` desempacota isso; aqui essas partes viram itens da tira de séries e quadros
na grade.

Identificador de uma vista: ``nm:<uid da série>:<chave da vista>``. A chave ``gm`` é a média
geométrica √(ANT × POST), calculada na hora — não há arquivo por trás dela.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QListWidgetItem, QMessageBox

from ipe.imaging import nm
from ipe.imaging.series import Frame, FrameImage, build_frames

log = logging.getLogger(__name__)

PREFIX = "nm:"
GM_KEY = "gm"
GM_LABEL = "Média geométrica"


def parse_uid(uid: str) -> tuple[str, str] | None:
    """``nm:<série>:<vista>`` -> (série, vista). Devolve None se não for uma vista de MN."""
    if not isinstance(uid, str) or not uid.startswith(PREFIX):
        return None
    rest = uid[len(PREFIX):]
    series_uid, _sep, view_key = rest.rpartition(":")
    return (series_uid, view_key) if series_uid and view_key else None


def make_uid(series_uid: str, view_key: str) -> str:
    return f"{PREFIX}{series_uid}:{view_key}"


# ------------------------------------------------------------------ vistas da série
def views_of(tab, series_uid: str) -> list[nm.NMView]:
    """Vistas de uma série, com cache na aba (a tira pergunta a cada redesenho)."""
    cache = getattr(tab, "_nm_views", None)
    if cache is None:
        cache = tab._nm_views = {}
    hit = cache.get(series_uid)
    if hit is None:
        frames = build_frames(tab.repo.instances_for_series(series_uid), series_uid)
        try:
            hit = nm.split_views(frames)
        except Exception:  # noqa: BLE001 - cabeçalho estranho não pode derrubar a tira
            log.exception("MN: não separou as vistas de %s", series_uid)
            hit = []
        cache[series_uid] = hit
    return hit


def clear_cache(tab) -> None:
    tab._nm_views = {}
    nm.clear_cache()


def view_by_key(tab, series_uid: str, view_key: str) -> nm.NMView | None:
    return next((v for v in views_of(tab, series_uid) if v.key == view_key), None)


def has_ant_post(tab, series_uid: str) -> bool:
    return nm.pair_ant_post(views_of(tab, series_uid)) is not None


def nm_series(tab) -> list:
    """Séries de medicina nuclear do estudo aberto que se dividem em vistas."""
    return [s for s in tab.series
            if (s.modality or "").upper() == "NM" and len(views_of(tab, s.series_uid)) > 1]


# ------------------------------------------------------------------ tira de séries
def strip_items(tab, series_uid: str) -> list[QListWidgetItem]:
    """Itens que entram na tira logo abaixo da série: uma linha por vista."""
    views = views_of(tab, series_uid)
    if len(views) < 2:
        return []
    out = []
    for v in views:
        it = QListWidgetItem(f"↳ {v.display}\n{v.n} im")
        it.setData(Qt.UserRole, make_uid(series_uid, v.key))
        it.setForeground(QBrush(QColor(210, 180, 120) if v.inferred else QColor(150, 205, 175)))
        it.setToolTip("A vista foi deduzida da descrição da série: o aparelho não gravou qual "
                      "detector é qual. Confira antes de usar para dizer o lado."
                      if v.inferred else
                      "Parte desta série de medicina nuclear. "
                      "Arraste para um quadro para ver só ela.")
        it.setSizeHint(QSize(112, 34))
        out.append(it)
    if nm.pair_ant_post(views) is not None:
        it = QListWidgetItem(f"↳ {GM_LABEL}\n√(ANT × POST)")
        it.setData(Qt.UserRole, make_uid(series_uid, GM_KEY))
        it.setForeground(QBrush(QColor(210, 190, 130)))
        it.setToolTip("Combinação das duas vistas que compensa a profundidade da fonte. "
                      "Imagem calculada aqui, não vem do aparelho.")
        it.setSizeHint(QSize(112, 34))
        out.append(it)
    return out


# ------------------------------------------------------------------ média geométrica
def _gm_image(cache, ant: Frame, post: Frame, flip: bool) -> FrameImage:
    a = cache.get(ant)
    p = cache.get(post)
    px = nm.geometric_mean(a.pixels, p.pixels, flip_post=flip)
    header = dict(a.header)
    header["SeriesDescription"] = GM_LABEL
    return FrameImage(px, False, None, a.pixel_spacing, a.spacing_source, "MONOCHROME2", header)


def geometric_mean_frames(tab, series_uid: str) -> tuple[list[Frame], str]:
    """Quadros virtuais da média geométrica. ("" no erro; senão o motivo de não dar.)"""
    views = views_of(tab, series_uid)
    par = nm.pair_ant_post(views)
    if par is None:
        return [], "Esta série não tem as duas vistas (ANT e POST)."
    ant, post = par
    n = min(ant.n, post.n)
    if n == 0:
        return [], "Uma das vistas está vazia."
    cache = tab.cache
    flip = bool(tab.settings.get("nm.flip_post", True))
    frames = []
    for k in range(n):
        fa, fp = ant.frames[k], post.frames[k]
        frames.append(Frame(path=fa.path, frame_index=k, sop_uid="", instance_number=k + 1,
                            position=fa.position, orientation=fa.orientation,
                            series_uid=series_uid,
                            provider=lambda _i, a=fa, p=fp: _gm_image(cache, a, p, flip)))
    return frames, ""


# ------------------------------------------------------------------ carregar num quadro
def load_into(tab, vp, uid: str) -> bool:
    """Põe uma vista de MN num quadro. False se o uid não for de medicina nuclear."""
    parsed = parse_uid(uid)
    if parsed is None:
        return False
    series_uid, view_key = parsed
    row = tab._series_row(series_uid)
    if row is None:
        return False
    if view_key == GM_KEY:
        frames, why = geometric_mean_frames(tab, series_uid)
        if not frames:
            tab.status_message.emit(why)
            return True
        label = f"Se {row.series_number} · {GM_LABEL}"
    else:
        view = view_by_key(tab, series_uid, view_key)
        if view is None:
            return False
        frames, label = view.frames, f"Se {row.series_number} · {view.display}"
    meta = tab.repo.series_meta(series_uid) or {}
    vp.mpr_plane = None
    vp.for_uid = meta.get("frame_of_reference", "") or f"study:{row.study_uid}"
    vp.study_uid = row.study_uid
    vp.modality = row.modality
    vp.key_frames = tab.key_set
    vp.set_series(uid, frames, label, tab.study_infos.get(row.study_uid, tab.study_info))
    vp.left_tool = tab.left_tool
    vp.anonymize = tab.anonymize
    tab.hub.leave(vp)
    tab._activate(vp)
    return True


# ------------------------------------------------------------------ layout
def open_views(tab, series_uid: str, with_gm: bool = False, max_frames: int = 6) -> bool:
    """Abre lado a lado **todas as vistas** da série, seja qual for o nome delas.

    Serve para ANT/POST, OAD/OPE, laterais, janelas de energia — qualquer coisa que a série
    traga separada. A ordem é a mesma da tira; ANT vem antes de POST quando existem os dois.
    Janela e zoom entram ligados, e a janela é calculada sobre as imagens juntas.
    """
    views = views_of(tab, series_uid)
    if len(views) < 2:
        return False
    escolhidas = views[:max_frames]
    uids = [make_uid(series_uid, v.key) for v in escolhidas]
    if with_gm and pair_ant_post(views) is not None and len(uids) < max_frames:
        uids.append(make_uid(series_uid, GM_KEY))
    tab.set_layout(*tab._layout_for(len(uids)))
    for vp, uid in zip(tab.viewports, uids):
        tab.load_series_into(vp, uid)
    alvo = tab.viewports[:len(uids)]
    tab.hub.set_flag("sync_wl", True)
    tab.hub.set_flag("sync_zoom", True)
    tab.hub.link_all(alvo)
    apply_common_window(alvo)
    if alvo:
        tab._activate(alvo[0])
    nomes = ", ".join(v.display for v in escolhidas)
    if any(v.inferred for v in escolhidas):
        tab.status_message.emit(f"{nomes} lado a lado. Atenção: a vista saiu da descrição da série, "
                                "não do cabeçalho — confira antes de dizer o lado.")
    else:
        tab.status_message.emit(f"{nomes} lado a lado, com a mesma janela e o zoom ligado.")
    if len(views) > len(escolhidas):
        tab.status_message.emit(f"Ficaram de fora {len(views) - len(escolhidas)} vista(s): "
                                "arraste da tira para ver as outras.")
    return True


def open_ant_post(tab, series_uid: str | None = None, with_gm: bool = False) -> None:
    """Abre ANT e POST lado a lado, com janela e zoom ligados entre os dois quadros.

    É o arranjo de leitura do corpo inteiro: comparar as duas vistas com janelas diferentes
    é erro de leitura, então os quadros entram já sincronizados.
    """
    if series_uid is None:
        series_uid = _current_nm_series(tab)
    if series_uid is None:
        QMessageBox.information(tab, "Medicina nuclear",
                                "Não há série de medicina nuclear com vistas separadas neste exame.")
        return
    views = views_of(tab, series_uid)
    par = nm.pair_ant_post(views)
    if par is None:
        QMessageBox.information(tab, "Medicina nuclear",
                                "Esta série não traz as vistas anterior e posterior separadas.")
        return
    uids = [make_uid(series_uid, par[0].key), make_uid(series_uid, par[1].key)]
    if with_gm:
        uids.append(make_uid(series_uid, GM_KEY))
    tab.set_layout(1, len(uids))
    for vp, uid in zip(tab.viewports, uids):
        tab.load_series_into(vp, uid)
    alvo = tab.viewports[:len(uids)]
    tab.hub.set_flag("sync_wl", True)
    tab.hub.set_flag("sync_zoom", True)
    tab.hub.link_all(alvo)
    apply_common_window(alvo)
    if alvo:
        tab._activate(alvo[0])
    if par[0].inferred or par[1].inferred:
        tab.status_message.emit("ANT e POST lado a lado. Atenção: qual detector é anterior saiu da "
                                "descrição da série, não do cabeçalho — confira antes de dizer o lado.")
    else:
        tab.status_message.emit("ANT e POST lado a lado, com a mesma janela e o zoom ligado.")


def open_series_views(tab, series_uid: str) -> bool:
    """Duplo clique numa série de MN: abre as vistas dela lado a lado. False se não há o que abrir."""
    return open_views(tab, series_uid)


def apply_common_window(vps: list) -> tuple[float, float] | None:
    """Mesma janela em todos os quadros, calculada sobre as imagens juntas.

    Cada quadro, sozinho, escolheria a própria janela automática — e comparar ANT com POST
    em janelas diferentes é erro de leitura. A janela sai do conjunto para que nenhuma das
    vistas sature.
    """
    amostras = []
    for vp in vps:
        img = vp._img
        if img is None or img.is_color or img.pixels.ndim != 2:
            continue
        px = img.pixels
        amostras.append(px[::max(1, px.shape[0] // 256), ::max(1, px.shape[1] // 256)].ravel())
    if not amostras:
        return None
    juntas = np.concatenate(amostras)
    lo, hi = np.percentile(juntas, [1, 99])       # mesmos percentis da janela automática
    if hi <= lo:
        lo, hi = float(juntas.min()), float(juntas.max()) + 1
    width, level = float(hi - lo), float((hi + lo) / 2)
    for vp in vps:
        vp.set_window(width, level, emit=False)
    return width, level


def _current_nm_series(tab) -> str | None:
    """A série de MN do quadro ativo; senão a primeira do estudo."""
    vp = tab.active
    if vp is not None and vp.series_uid:
        parsed = parse_uid(vp.series_uid)
        if parsed is not None:
            return parsed[0]
        if (vp.modality or "").upper() == "NM" and len(views_of(tab, vp.series_uid)) > 1:
            return vp.series_uid
    rows = nm_series(tab)
    return rows[0].series_uid if rows else None


def open_analysis(tab, series_uid: str | None = None, view_key: str = "") -> None:
    """Abre a janela de curvas para a série (ou a vista) dinâmica que estiver no quadro ativo."""
    vp = tab.active
    frames, titulo, info = [], "", None
    if vp is not None and vp.frames and (vp.modality or "").upper() == "NM":
        parsed = parse_uid(vp.series_uid)
        if series_uid is None and parsed is not None:
            series_uid, view_key = parsed
        frames, titulo = list(vp.frames), vp.series_label
    if series_uid is not None and view_key:
        view = view_by_key(tab, series_uid, view_key)
        if view is not None:
            frames = view.frames
            row = tab._series_row(series_uid)
            titulo = f"Se {row.series_number} · {view.display}" if row else view.display
    if not frames:
        QMessageBox.information(tab, "Medicina nuclear",
                                "Ponha no quadro ativo a série (ou a vista) de medicina nuclear "
                                "que você quer analisar.")
        return
    info = nm.info_for_file(frames[0].path)
    if len(frames) < 3:
        QMessageBox.information(tab, "Medicina nuclear",
                                "Esta vista tem poucos quadros: a curva atividade-tempo precisa "
                                "de uma série dinâmica.")
        return
    preset = "renograma" if _parece_renal(titulo, tab, series_uid) else "livre"
    from ipe.ui.viewer.nm_analysis import NMAnalysisDialog
    dlg = NMAnalysisDialog(frames, tab.cache, titulo, info, preset, tab, tab)
    dlg.setAttribute(Qt.WA_DeleteOnClose, False)
    dlg.exec()


# palavras da descrição do exame -> receita da janela entre séries
MULTI_PISTAS = [(("DMSA",), "dmsa"),
                (("PARATIREOIDE", "PARATIREOIDES"), "paratireoide"),
                (("TIREOIDE", "TIREÓIDE", "CAPTACAO", "CAPTAÇÃO"), "tireoide"),
                (("TRANSITO", "TRÂNSITO", "COLONICO", "CÓLON"), "transito")]


def open_multi(tab) -> None:
    """Compara as imagens do exame: ANT × POST, precoce × tardia, seringa, 24/48/72 h."""
    from ipe.imaging import nm_multi
    from ipe.ui.viewer.nm_multi_view import NMMultiDialog
    fontes = study_sources(tab)
    if len(fontes) < 2:
        QMessageBox.information(tab, "Medicina nuclear",
                                "Este exame não tem duas imagens de medicina nuclear para comparar.")
        return
    texto = (tab.study_info.get("description", "") or "").upper()
    preset = next((chave for palavras, chave in MULTI_PISTAS
                   if any(p in texto for p in palavras)), "livre")
    for s in fontes:
        s.rois = [r for r in nm_multi.multi_protocol(preset).rois[:0]]     # começa sem regiões
    dlg = NMMultiDialog(fontes, tab.cache, tab.study_info.get("description", "") or "Exame",
                        preset, tab, tab)
    dlg.exec()


def study_sources(tab, max_sources: int = 12) -> list:
    """Uma fonte por série (ou por vista) de medicina nuclear do exame aberto.

    Capturas de tela da estação ficam de fora: elas são a folha do laudo, não imagem de medida.
    """
    from ipe.imaging import nm_multi
    fontes = []
    for row in tab.series:
        if row.study_uid != tab.study_uid or (row.modality or "").upper() != "NM":
            continue
        frames = build_frames(tab.repo.instances_for_series(row.series_uid), row.series_uid)
        if not frames:
            continue
        if _e_captura(frames[0].path):
            continue
        views = views_of(tab, row.series_uid)
        if views:
            for v in views:
                fontes.append(nm_multi.Source(f"{row.series_uid}:{v.key}",
                                              f"Se {row.series_number} {row.description} · {v.display}",
                                              list(v.frames)))
        else:
            fontes.append(nm_multi.Source(row.series_uid,
                                          f"Se {row.series_number} {row.description}".strip(),
                                          frames))
        if len(fontes) >= max_sources:
            break
    return fontes


def _e_captura(path: str) -> bool:
    try:
        import pydicom
        from ipe.importer.scanner import SECONDARY_CAPTURE, is_workstation_capture
        ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
        return is_workstation_capture(ds, str(ds.get("SOPClassUID", "")) or SECONDARY_CAPTURE)
    except Exception:  # noqa: BLE001
        return False


def _parece_renal(titulo: str, tab, series_uid: str | None) -> bool:
    """Nome do exame que sugere renograma — só decide os nomes prontos das ROIs."""
    texto = (titulo or "").upper()
    if series_uid:
        row = tab._series_row(series_uid)
        if row is not None:
            texto += " " + (row.description or "").upper()
            texto += " " + (tab.study_infos.get(row.study_uid, {}).get("description", "") or "").upper()
    return any(p in texto for p in ("DTPA", "MAG3", "DMSA", "RENAL", "RENOGRAMA", "EC "))


def study_has_nm(tab) -> bool:
    return any((s.modality or "").upper() == "NM" for s in tab.series)
