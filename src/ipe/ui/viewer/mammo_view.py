"""Mamografia no visualizador: protocolos por etapas (layout + incidências), barra de navegação,
zoom por quadrante sincronizado e editor de protocolos."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QToolBar,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ipe.imaging import mammo as M
from ipe.imaging.series import build_frames

log = logging.getLogger(__name__)

CELL_CHOICES = [""] + [f"{v}{s}{t}{a}" for a in ("", " ant", " ant2") for t in ("", " tomo", " rec")
                       for v in ("CC", "MLO", "ML", "LM", "XCCL", "XCCM", "AT", "SPOT", "MAG", "")
                       for s in ("D", "E")] + ["US", "RM"]
# zoom por quadrante: duas etapas, ancoradas na parede torácica (posterior)
QUAD_NAMES = ["posterior e superior", "posterior e inferior"]
SLAB_STEPS = [1, 5, 10, 20]                         # tomossíntese: espessura em cortes


# ============================================================================ sessão
class MgSession:
    """Protocolo de mamografia ativo numa aba do visualizador."""

    def __init__(self, tab, proto: dict):
        self.tab, self.proto = tab, proto
        self.step = 0
        self._images: dict[int, list] = {}           # 0 = atual; 1 = anterior…
        self._studies: dict[int, str | None] = {0: tab.study_uid}
        self._frames: dict[str, list] = {}           # série -> quadros

    @property
    def steps(self) -> list[dict]:
        """As etapas do protocolo — as mesmas em todos os monitores do conjunto."""
        return M.passos_do_protocolo(self.proto)

    # ------------------------------------------------------------------ exames
    def prior_uid(self, n: int) -> str | None:
        if n in self._studies:
            return self._studies[n]
        t = self.tab
        date = t.study_info.get("study_date", "")
        others = [r for r in t.repo.other_studies_same_patient(t.study_uid)
                  if "MG" in (r.modalities or "").upper() and r.study_date and r.study_date < date]
        others.sort(key=lambda r: r.study_date, reverse=True)
        uid = others[n - 1].study_uid if len(others) >= n else None
        self._studies[n] = uid
        return uid

    def images(self, n: int) -> list:
        if n not in self._images:
            uid = self.prior_uid(n) if n else self.tab.study_uid
            if uid is None:
                self._images[n] = []
            else:
                if n:
                    self.tab.add_study_silent(uid)
                self._images[n] = M.read_images(self.tab.repo, uid)
        return self._images[n]

    def has_images(self) -> bool:
        return any(im.side for im in self.images(0))

    # ------------------------------------------------------------------ etapas
    def apply_step(self, i: int) -> None:
        steps = self.steps
        if not steps:
            return
        i %= len(steps)
        self.step = i
        st = steps[i]
        t = self.tab
        # O que **este** monitor mostra nesta etapa. A etapa é a mesma em todas as telas; o que
        # muda é o pedaço que cabe a cada uma.
        quantos = max(1, int(getattr(t, "mg_telas", 1) or 1))
        indice = max(0, int(getattr(t, "mg_monitor", 0) or 0))
        quadros = [M.quadro_da_etapa(st, quantos, j) for j in range(quantos)]
        meu = quadros[indice] if indice < len(quadros) else quadros[-1]
        deslocamento = sum(q["cols"] for q in quadros[:indice])
        rows, cols = max(1, int(meu["rows"])), max(1, int(meu["cols"]))
        celulas = list(meu["cells"])
        t.set_layout(rows, cols)
        used: dict[int, set] = {}
        for k in range(rows * cols):
            vp = t.viewports[k]
            code = celulas[k] if k < len(celulas) else ""
            cell = M.parse_code(code) if code else None
            vp.mg_cell = None
            vp.empty_note = ""
            outro = M.parse_outro(code) if code and cell is None else None
            if outro is not None:                # 0.99.61 (PV 19): última US / última RM no quadro
                self._load_outro(vp, *outro)
                continue
            if cell is None:
                vp.clear()
                vp.empty_note = "(quadro vazio no protocolo)" if not code else f"{code}: código inválido"
                continue
            im = M.pick_image(self.images(cell.prior), cell, used.setdefault(cell.prior, set()))
            if im is None:
                vp.clear()
                vp.set_orientation(0, False, False)
                vp.empty_note = f"{cell.label}\nnão encontrada" + ("" if not cell.prior or self.prior_uid(cell.prior)
                                                                  else " (sem exame anterior)")
                continue
            used[cell.prior].add(im.sop_uid)
            self._load(vp, im, cell)
            # Para que lado vai a parede torácica. Com as duas mamas na linha, decide a mama; com
            # uma só (atual × anterior), decide a coluna — veja `M.parede_desejada`. Num monitor
            # de uma coluna só, a linha é a etapa inteira e a coluna vem da posição do monitor no
            # conjunto, porque as telas vizinhas formam o par.
            if cols >= 2:
                col, quantas = k % cols, cols
                linha = celulas[(k // cols) * cols:(k // cols + 1) * cols]
            else:
                col, quantas = deslocamento % 2, 2
                linha = list(st.get("cells") or [])
            want = M.parede_desejada(cell.side, col, quantas, M.lados_das_celulas(linha))
            vp.mg_cell = (col, quantas, want)
            self._orient(vp, want)
        self.enquadrar(st)
        if t.viewports:
            t._activate(t.viewports[0])
        t.update_reference_lines()
        t._sync_mg_bar()

    def enquadrar(self, st: dict | None = None, so_pendentes: bool = False) -> str:
        """Enquadra os quadros da etapa. Devolve o modo aplicado (para a barra de estado).

        O zoom sai do tamanho do quadro, que depende do monitor: a mesma etapa enquadra diferente
        numa tela de 1920 e numa de 2560, e é isso que se quer. Com o zoom sincronizado, as duas
        mamas da etapa ficam na **mesma escala** — comparar lado a lado em escalas diferentes não
        é comparar.
        """
        st = self.steps[self.step] if st is None and self.steps else st
        modo = M.enquadre_da_etapa(st)
        vps = [vp for vp in self.tab.viewports if vp.mg_cell is not None and vp._img is not None]
        if so_pendentes:
            # Refazendo por mudança de tamanho: só os quadros que **ainda** estão no enquadramento
            # automático. Quem mexeu no zoom à mão não quer o zoom de volta.
            vps = [vp for vp in vps if (getattr(vp, "anat_lock", None) or ("mama",))[0] == "mama"]
        if not vps:
            return modo
        if modo == "imagem":
            for vp in vps:
                vp.fit()
            return modo
        if modo == "pixel":
            for vp in vps:
                vp.zoom_actual_pixels()
            return modo
        zooms = [(vp, vp.zoom_da_mama()) for vp in vps]
        achados = [z for _vp, z in zooms if z]
        if not achados:
            for vp in vps:
                vp.fit()
            self.tab.status_message.emit("Não achei a mama nestas imagens: enquadrei a imagem inteira.")
            return "imagem"
        comum = min(achados) if self.proto.get("sync_zoom", True) else None
        faltaram = 0
        for vp, z in zooms:
            vp.mg_dy = 0.0
            if not vp.enquadrar_na_mama(comum if comum is not None else z):
                vp.fit()
                faltaram += 1
        if faltaram:
            self.tab.status_message.emit(
                f"Não achei a mama em {faltaram} quadro(s): esses abriram com a imagem inteira.")
        if M.alinhamento_do_protocolo(self.proto) == "mamilo":
            self.alinhar_pelo_mamilo([vp for vp, _z in zooms])
        return modo

    def alinhar_pelo_mamilo(self, vps) -> int:
        """PV 16: na mesma linha da tela, o mamilo das duas mamas na mesma altura (a média das alturas). Fica
        guardado em `mg_dy`, para a tomo e a recombinada continuarem alinhadas ao rolar. Devolve quantos
        quadros alinhou."""
        t = self.tab
        cols = max(1, t._layout[1])
        linhas: dict[int, list] = {}
        for vp in vps:
            if vp in t.viewports and getattr(vp, "anat_lock", None) and vp.anat_lock[0] == "mama":
                linhas.setdefault(t.viewports.index(vp) // cols, []).append(vp)
        n = 0
        for grupo in linhas.values():
            ys = [(vp, vp.mamilo_na_tela()) for vp in grupo]
            ys = [(vp, y) for vp, y in ys if y is not None]
            if len(ys) < 2:
                continue
            alvo = sum(y for _vp, y in ys) / len(ys)
            for vp, y in ys:
                vp.mg_dy = float(alvo - y)             # o enquadramento soma isto à altura do alvo
                vp.enquadrar_na_mama(vp.state.zoom, vp.anat_lock[2])
                n += 1
        return n

    def _series_frames(self, series_uid: str) -> list:
        if series_uid not in self._frames:
            self._frames[series_uid] = build_frames(self.tab.repo.instances_for_series(series_uid), series_uid)
        return self._frames[series_uid]

    def cell_frames(self, im, cell) -> tuple[list, int, tuple[int, int] | None]:
        """Quadros do quadro da mamografia: as imagens 2D da mesma mama e incidência e, em seguida, os cortes
        da tomossíntese dessa incidência — a roda passa de uma para a outra, como numa série só.
        Devolve (quadros, índice inicial, [início, fim) dos cortes da tomo ou None)."""
        imgs = self.images(cell.prior)
        base = cell.with_tomo(False)
        two_d = [x for x in M.same_view(imgs, base) if not x.tomo]
        tomos = [x for x in M.same_view(imgs, base.with_tomo(True)) if x.tomo]
        frames, start = [], 0
        for x in two_d:
            f = next((f for f in self._series_frames(x.series_uid) if f.sop_uid == x.sop_uid), None)
            if f is not None:
                if x.sop_uid == im.sop_uid:
                    start = len(frames)
                frames.append(f)
        n2d = len(frames)
        for x in tomos:
            fs = sorted((f for f in self._series_frames(x.series_uid) if f.sop_uid == x.sop_uid),
                        key=lambda f: f.frame_index)
            if x.sop_uid == im.sop_uid and fs:
                start = len(frames) + len(fs) // 2
            frames.extend(fs)
        rng = (n2d, len(frames)) if len(frames) > n2d else None
        return frames, start, rng

    def _load(self, vp, im, cell) -> None:
        t = self.tab
        frames, start, rng = self.cell_frames(im, cell)
        if not frames:
            return
        cell_name = f"{im.view or '?'} {'D' if im.side == 'R' else 'E' if im.side == 'L' else ''}".strip()
        # Variante da incidência (mesmo ViewPosition, outro nome — a complementar do serviço):
        # o quadro diz de que série veio, senão "MLO D" estaria mentindo sobre o que está na tela.
        if cell.view != "ANY" and not getattr(im, "exata", True):
            qual = getattr(im, "rotulo", "") or getattr(im, "serie", "")
            if qual:
                cell_name += f" · {qual}"
        if getattr(im, "sintetica", False):
            cell_name += " · 2D sintética"     # é a incidência, mas não é a imagem adquirida
        if im.energy == "rec":
            cell_name += " recombinada"
        elif im.energy == "low":
            cell_name += " baixa energia"
        n2d = rng[0] if rng else len(frames)
        parts = []
        if n2d:
            parts.append(f"{n2d} imagem" if n2d == 1 else f"{n2d} imagens")
        if rng:
            parts.append(f"tomo {rng[1] - rng[0]} cortes")
        if len(parts) > 1 or rng or n2d > 1:
            cell_name += f" ({' + '.join(parts)})"
        if im.study_uid != t.study_uid:
            info = t.study_infos.get(im.study_uid, {})
            d = info.get("study_date", "")
            cell_name += f" — anterior {d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else " — anterior"
        uid = f"mg:{im.study_uid}:{cell.side}{cell.view}{'R' if im.energy == 'rec' else ''}"
        implant = bool(getattr(vp, "implant_mask", False))
        t.load_frames_into(vp, uid, frames, cell_name, im.study_uid, im.series_uid, start)
        vp.mg_spec = cell
        vp.tomo_range = rng
        vp.mg_tomo = rng is not None
        vp.cine_bounce = rng is not None
        if rng is not None:                  # recalcula a janela sabendo onde está a tomo
            vp.state.window_set = False
            vp._win_seg = None
            vp._qimage_key = None
            vp._load_current()
            vp.update()
        if rng and getattr(t, "mg_slab", 1) > 1:
            vp.set_tomo_slab(t.mg_slab, getattr(t, "mg_slab_mode", "mip"))
        if implant or getattr(t, "mg_implant", False):
            vp.set_implant_mask(True)
        if getattr(t, "mg_inverter_mama", False):
            vp.set_inverter_mama(True)

    # ------------------------------------------------------------------ outro exame (PV 19)
    def exame_outro(self, mod: str):
        """O exame mais recente do paciente com `mod` (US ou MR), da mama de preferência. Guardado."""
        chave = f"outro:{mod}"
        if chave in self._studies:
            return self._studies[chave]
        t = self.tab
        try:
            rows = t.repo.other_studies_same_patient(t.study_uid)
        except Exception:  # noqa: BLE001
            rows = []
        r, da_mama = M.estudo_outro(rows, mod, t.study_info.get("study_date", ""), t.study_uid)
        self._studies[chave] = (r, da_mama) if r is not None else None
        return self._studies[chave]

    def _load_outro(self, vp, mod: str, filtro: str = "") -> bool:
        t = self.tab
        achado = self.exame_outro(mod)
        rotulo = M.rotulo_outro(mod)
        vp.mg_cell = None
        if achado is None:
            vp.clear()
            vp.set_orientation(0, False, False)
            vp.empty_note = rotulo + "\n" + "nenhum exame do paciente"
            return False
        r, da_mama = achado
        t.add_study_silent(r.study_uid)
        serie = M.serie_outra([s for s in t.series if s.study_uid == r.study_uid], mod, filtro)
        if serie is None:
            vp.clear()
            vp.empty_note = rotulo + "\n" + "sem imagens"
            return False
        vp.set_orientation(0, False, False)
        vp.align_edge = None
        t.load_series_into(vp, serie.series_uid, como_serie=True)
        d = r.study_date or ""
        data = f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else d
        vp.series_label = rotulo + " — " + data + (" · " + serie.description if serie.description else "") + \
            ("" if da_mama else " (não é da mama?)")
        vp.update()
        return True

    def toggle_tomo(self, vp) -> bool:
        """Atalho (Shift+T): pula entre a imagem 2D e o meio da tomossíntese, na mesma lista do quadro."""
        rng = getattr(vp, "tomo_range", None)
        if not rng:
            self.tab.status_message.emit("Não há tomossíntese desta incidência neste exame.")
            return False
        if vp.in_tomo():
            vp.go_to(max(0, rng[0] - 1))
        else:
            vp.go_to(rng[0] + (rng[1] - rng[0]) // 2)
        return True

    def toggle_rec(self, vp) -> bool:
        """Mamografia com contraste: alterna o quadro entre baixa energia e recombinada."""
        cell = getattr(vp, "mg_spec", None)
        if cell is None:
            return False
        new = cell.with_rec(not cell.rec)
        im = M.pick_image(self.images(new.prior), new)
        if im is None:
            self.tab.status_message.emit("Não há imagem " + ("recombinada" if new.rec else "de baixa energia")
                                         + f" de {new.label.replace(' recombinada', '')} neste exame.")
            return False
        col_cols = vp.mg_cell
        enquadre = vp.anat_state()          # guarda o zoom por quadrante para a imagem nova
        self._load(vp, im, new)
        vp.mg_cell = col_cols
        if col_cols:
            self._orient(vp, col_cols[-1])
        vp.restore_anat(enquadre)           # a recombinada abre no mesmo quadrante, com o mesmo zoom
        return True

    def _orient(self, vp, want: str | None) -> None:
        """Espelha o quadro para a parede torácica ficar do lado `want` da tela ("left"/"right")."""
        vp.set_orientation(0, False, False)
        vp.align_edge = None
        if want not in ("left", "right") or vp._img is None:
            vp.update()
            return
        if self.proto.get("chest_to_center", True):
            side = M.chest_wall_side(vp._img.pixels) if not vp._img.is_color else ""
            if side and side != want:
                vp.set_orientation(0, True, False)
        if self.proto.get("align_chest", True):
            vp.align_edge = want
        vp.update()

    def next(self, d: int = 1) -> None:
        self.apply_step(self.step + d)


def half_of(col: int, cols: int) -> str | None:
    """Metade da tela do quadro: "L" (esquerda), "R" (direita) ou None (coluna única/central)."""
    if cols < 2:
        return None
    if cols % 2 and col == cols // 2:
        return None
    return "L" if col < cols / 2 else "R"


# ============================================================================ barra
class MgBar(QToolBar):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.setStyleSheet("QToolBar{background:#2a2433;color:#ddd;spacing:6px}QLabel{color:#ddd}")
        self.addWidget(QLabel("  Mamografia:"))
        self.c_proto = QComboBox()
        self.c_proto.activated.connect(self._proto_chosen)
        self.addWidget(self.c_proto)
        self.addWidget(QLabel(" etapa:"))
        self.c_step = QComboBox()               # o nome da etapa à esquerda…
        self.c_step.setMinimumWidth(260)
        self.c_step.setToolTip("Etapa do protocolo. A última linha abre o editor de protocolos.")
        self.c_step.activated.connect(self._step_chosen)
        self.addWidget(self.c_step)
        for texto, dica, d in (("◀", "Etapa anterior (Shift+N)", -1), ("▶", "Próxima etapa (N)", 1)):
            a = QAction(texto, self)            # …e as duas setas juntas, à direita
            a.setToolTip(dica)
            a.triggered.connect(lambda _=False, k=d: tab.mg_next(k))
            self.addAction(a)
        self.addSeparator()
        self.addWidget(QLabel(" zoom:"))
        self.a_quad = QAction("Quadrante ↻", self)
        self.a_quad.setToolTip("Zoom por quadrante da mama: cada clique vai para o próximo (posterior e superior → "
                               "posterior e inferior → imagem inteira), nos quadros juntos e acompanhando a tomo e "
                               "a recombinada. Tecla Q; Shift+Q volta.")
        self.a_quad.triggered.connect(lambda: tab.mg_quadrant_cycle(tab.active, 1))
        self.addAction(self.a_quad)
        a = QAction("1:1", self)
        a.setToolTip("Tamanho real: 1 pixel da imagem = 1 pixel da tela")
        a.triggered.connect(lambda: tab._on_active(lambda v: v.zoom_actual_pixels()))
        self.addAction(a)
        a = QAction("Mama no quadro", self)
        a.setToolTip("Reenquadra todos os quadros com a mama ocupando o quadro, descartando o ar "
                     "(Alt+Q). O protocolo já faz isso ao abrir; isto é para depois de mexer no zoom.")
        a.triggered.connect(lambda: tab.mg_enquadrar())
        self.addAction(a)
        self.a_enquadre = a
        self.addAction(tab.tool_actions["loupe"])
        sz = getattr(tab, "sync_zoom_action", None)
        if sz is not None:                          # 0.99.61 (PV 16): zoom e pan espelhados entre as mamas
            self.addAction(sz)
        self.addSeparator()
        self.a_inv = QAction("Inverter só a mama", self, checkable=True)
        self.a_inv.setToolTip("Inverte o tecido da mama e deixa o fundo preto, em todos os quadros")
        self.a_inv.toggled.connect(lambda on: tab.mg_set_inverter_mama(on))
        self.addAction(self.a_inv)
        a = QAction("★ Corte", self)
        a.setToolTip("Marca o corte da tomossíntese (ou a imagem) do quadro ativo como imagem-chave. Para ir "
                     "ao próximo corte marcado, escolha uma tecla em Atalhos ▸ Mamografia")
        a.triggered.connect(lambda: tab.mg_corte_chave())
        self.addAction(a)
        self.addSeparator()
        from PySide6.QtWidgets import QMenu, QToolButton
        self.slab_btn = QToolButton()
        self.slab_btn.setText("Espessura: fina ▾")
        self.slab_btn.setToolTip("Tomossíntese: espessura (slab) em cortes — MIP ou média (Shift+J troca)")
        self.slab_btn.setPopupMode(QToolButton.InstantPopup)
        sm = QMenu(self.slab_btn)
        for n in SLAB_STEPS:
            act = sm.addAction("fina (1 corte)" if n == 1 else f"{n} cortes")
            act.triggered.connect(lambda _=False, k=n: tab.mg_set_slab(k))
        sm.addSeparator()
        for mode, lab in (("mip", "MIP (máximo)"), ("avg", "Média")):
            act = sm.addAction(lab)
            act.triggered.connect(lambda _=False, m=mode: tab.mg_set_slab(None, m))
        self.slab_btn.setMenu(sm)
        self.addWidget(self.slab_btn)
        self.addSeparator()
        a = QAction("BE ⇄ Recomb.", self)
        a.setToolTip("Mamografia com contraste (CEM): alterna o quadro ativo entre baixa energia e recombinada "
                     "(Shift+B). No protocolo, use \"rec\" no código (ex.: CCD rec).")
        a.triggered.connect(lambda: tab.mg_toggle_cem())
        self.addAction(a)
        self.a_implant = QAction("Implante", self, checkable=True)
        self.a_implant.setToolTip("Corrige a prótese em todos os quadros (Alt+I): o silicone desce ao nível do "
                                  "tecido em volta e o tecido na frente e atrás dele continua visível. A janela "
                                  "não muda. Não altera o arquivo.")
        self.a_implant.toggled.connect(lambda on: tab.mg_set_implant(on))
        self.addAction(self.a_implant)
        self.addSeparator()
        a = QAction("Achados…", self)
        a.setToolTip("Tabela dos achados marcados na CC e na MLO (botão direito na imagem ▸ Achado BI-RADS aqui): "
                     "distância ao mamilo, quadrante e hora; manda ao laudo BI-RADS")
        a.triggered.connect(lambda: tab.abrir_marcadores_mama())
        self.addAction(a)
        a = QAction("Densidade…", self)
        a.setToolTip("Mede quanto da mama é tecido fibroglandular (PD%) nas imagens que estiverem "
                     "nos quadros da tela, e deixa ver a máscara por cima delas. O número é do "
                     "programa; a categoria do BI-RADS é do radiologista.")
        a.triggered.connect(lambda: tab.mg_densidade())
        self.addAction(a)
        self.addSeparator()
        a = QAction("✕", self)
        a.setToolTip("Sair do protocolo de mamografia")
        a.triggered.connect(tab.close_mg)
        self.addAction(a)
        self.setVisible(False)

    def _step_chosen(self, i: int) -> None:
        """Escolheu uma etapa — ou a última linha, que abre o editor de protocolos."""
        s = self.tab.mg_session
        if s is None:
            return
        if i >= len(s.steps):                       # separador ou "Editar protocolos…"
            self.c_step.blockSignals(True)
            self.c_step.setCurrentIndex(s.step)     # a etapa mostrada não muda
            self.c_step.blockSignals(False)
            if i > len(s.steps):
                self.tab.edit_mg_protocols()
            return
        self.tab.mg_step(i)          # a etapa é do conjunto: muda em todos os monitores

    def sync(self) -> None:
        s = self.tab.mg_session
        self.setVisible(s is not None)
        if s is None:
            return
        protos = M.mg_protocols(self.tab.settings)
        self.c_proto.blockSignals(True)
        self.c_proto.clear()
        for i, p in enumerate(protos):
            self.c_proto.addItem(p.get("name", f"Protocolo {i + 1}"), i)
        i = next((k for k, p in enumerate(protos) if p.get("name") == s.proto.get("name")), 0)
        self.c_proto.setCurrentIndex(i)
        self.c_proto.blockSignals(False)
        self.c_step.blockSignals(True)
        self.c_step.clear()
        for k, st in enumerate(s.steps):
            self.c_step.addItem(f"{k + 1}. {M.step_title(st)}")
        self.c_step.insertSeparator(self.c_step.count())
        self.c_step.addItem("Editar protocolos…")      # última linha da lista de etapas
        self.c_step.setCurrentIndex(s.step)
        self.c_step.blockSignals(False)

    def _proto_chosen(self, i: int) -> None:
        protos = M.mg_protocols(self.tab.settings)
        if 0 <= i < len(protos):
            self.tab.start_mg(protos[i])


# ============================================================================ editor
class MgProtocolsEditor(QWidget):
    """Protocolos de mamografia: à esquerda os protocolos, à direita as etapas.

    **A etapa é do conjunto de monitores, não de um monitor.** Há uma lista de etapas só; o que
    cada tela mostra numa etapa se escolhe aqui, na própria etapa, com "com N telas, mostrar no
    Monitor k". Sem definir nada, a etapa se reparte sozinha entre as telas — numa etapa de duas
    linhas em duas telas, cada tela fica com uma linha.
    """

    TELAS = [1, 2, 3, 4]

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.protos = M.mg_protocols(settings)
        for pr in self.protos:
            pr["steps"] = M.passos_do_protocolo(pr)
            pr.pop("telas", None)                  # formato intermediário, com etapas por monitor
            pr.pop("monitores", None)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Protocolos</b> (o primeiro ativo que combina é usado)"))
        self.l_protos = QListWidget()
        self.l_protos.currentRowChanged.connect(self._proto_selected)
        left.addWidget(self.l_protos, 1)
        row = QHBoxLayout()
        for text, fn in (("+ Novo", self._new_proto), ("Duplicar", self._dup_proto), ("Remover", self._del_proto),
                         ("Padrão", self._reset)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        left.addLayout(row)
        # o implante na chegada (0.97) mudou para Preferências ▸ CAD/IA (0.99), com as outras opções dele
        lay.addLayout(left, 1)

        right = QVBoxLayout()
        g = QGroupBox("Protocolo")
        f = QFormLayout(g)
        self.e_name = QLineEdit()
        self.e_desc = QLineEdit(placeholderText="vazio = qualquer mamografia; ex.: RASTREAMENTO|DIAGNOSTICA")
        self.c_enabled = QCheckBox("Ativo")
        self.c_center = QCheckBox("Parede torácica voltada para o centro (espelha a imagem se precisar)")
        self.c_align = QCheckBox("Encostar a imagem na borda da parede torácica")
        self.c_sync = QCheckBox("Zoom por quadrante (Q) em todos os quadros juntos")
        f.addRow("Nome:", self.e_name)
        f.addRow("Descrição do exame contém:", self.e_desc)
        for c in (self.c_enabled, self.c_center, self.c_align, self.c_sync):
            f.addRow(c)
        self.c_alinhar = QComboBox()                # 0.99.61 (PV 16)
        for chave, rot in M.ALINHAMENTOS.items():
            self.c_alinhar.addItem(rot, chave)
        self.c_alinhar.setToolTip("Altura das mamas na mesma linha da tela, no enquadramento da mama")
        self.c_alinhar.currentIndexChanged.connect(lambda _i: self._store_proto())
        f.addRow("Alinhar na vertical:", self.c_alinhar)
        for wdg in (self.e_name, self.e_desc):
            wdg.editingFinished.connect(self._store_proto)
        for c in (self.c_enabled, self.c_center, self.c_align, self.c_sync):
            c.toggled.connect(lambda _on: self._store_proto())
        right.addWidget(g)

        gs = QGroupBox("Etapas (N / Shift+N no visualizador)")
        vs = QVBoxLayout(gs)
        nota = QLabel("A etapa vale para o conjunto: passar de etapa muda todos os monitores ao "
                      "mesmo tempo. Escolha abaixo o que cada tela mostra nesta etapa.")
        nota.setWordWrap(True)
        nota.setStyleSheet("color:#9a9a9a")
        vs.addWidget(nota)
        self.l_steps = QListWidget()
        self.l_steps.setMaximumHeight(120)
        self.l_steps.currentRowChanged.connect(self._step_selected)
        vs.addWidget(self.l_steps)
        row = QHBoxLayout()
        for text, fn in (("+ Etapa", self._new_step), ("Remover", self._del_step), ("↑", lambda: self._move(-1)),
                         ("↓", lambda: self._move(1))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        vs.addLayout(row)
        fs = QFormLayout()
        self.e_step_name = QLineEdit(placeholderText="ex.: CC atual × anterior")
        self.e_step_name.editingFinished.connect(self._store_step)
        fs.addRow("Nome da etapa:", self.e_step_name)
        self.c_enquadre = QComboBox()
        for chave, rotulo in M.ENQUADRES.items():
            self.c_enquadre.addItem(rotulo, chave)
        self.c_enquadre.setToolTip("O zoom sai do tamanho do quadro, que depende do monitor: a mesma "
                                   "etapa enquadra diferente em telas diferentes.")
        self.c_enquadre.currentIndexChanged.connect(lambda _i: self._store_step())
        fs.addRow("Ao abrir, enquadrar:", self.c_enquadre)
        linha = QHBoxLayout()
        self.c_telas = QComboBox()
        for n in self.TELAS:
            self.c_telas.addItem(M.TITULO_TELAS.get(n, "1 tela"), n)
        self.c_telas.currentIndexChanged.connect(lambda _i: self._alvo_mudou())
        self.c_monitor = QComboBox()
        self.c_monitor.currentIndexChanged.connect(lambda _i: self._alvo_mudou())
        self.b_auto = QPushButton("Repartir sozinho")
        self.b_auto.setToolTip("Volta esta etapa a se repartir automaticamente entre as telas.")
        self.b_auto.clicked.connect(self._repartir_sozinho)
        linha.addWidget(self.c_telas)
        linha.addWidget(QLabel("mostrar no"))
        linha.addWidget(self.c_monitor)
        linha.addWidget(self.b_auto)
        linha.addStretch(1)
        fs.addRow("Nesta etapa, com:", linha)
        lr = QHBoxLayout()
        self.s_rows = QSpinBox(minimum=1, maximum=4)
        self.s_cols = QSpinBox(minimum=1, maximum=6)
        for sp in (self.s_rows, self.s_cols):
            sp.valueChanged.connect(self._resize_grid)
        lr.addWidget(self.s_rows)
        lr.addWidget(QLabel("×"))
        lr.addWidget(self.s_cols)
        lr.addStretch(1)
        fs.addRow("Layout (linhas × colunas):", lr)
        self.e_text = QLineEdit(placeholderText="ex.: CCD, MLOD x CCE, MLOE")
        self.e_text.setToolTip("Colunas separadas por x, linhas por vírgula. D = direita, E = esquerda; "
                               "“ant” = exame anterior (ant2 = o anterior do anterior).")
        self.e_text.editingFinished.connect(self._text_edited)
        fs.addRow("Em texto:", self.e_text)
        vs.addLayout(fs)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        vs.addWidget(self.grid_host)
        dica = QLabel("<small>Incidências: CC, MLO, ML, LM, XCCL, XCCM, AT, SPOT, MAG (ou só D/E = qualquer). "
                      "Ex.: 1×2 “CCD x CCE”, 1×2 “MLOD x MLOE”, 2×2 “CCD, MLOD x CCE, MLOE”, "
                      "2×2 “CCD, CCD ant x CCE, CCE ant”. Outro exame: “US” = a última ultrassonografia da mama, "
                      "“RM” = a última RM da mama (“RM:SUB” escolhe a série pela descrição).</small>")
        dica.setWordWrap(True)
        vs.addWidget(dica)
        right.addWidget(gs, 1)
        lay.addLayout(right, 2)
        self.cells: list[QComboBox] = []
        self._loading = False
        self._fill_protos()

    # ------------------------------------------------------------------ protocolos
    def _fill_protos(self, select: int = 0) -> None:
        self.l_protos.blockSignals(True)
        self.l_protos.clear()
        for pr in self.protos:
            self.l_protos.addItem(QListWidgetItem(("" if pr.get("enabled", True) else "(inativo) ")
                                                  + pr.get("name", "?")))
        self.l_protos.blockSignals(False)
        self.l_protos.setCurrentRow(min(select, len(self.protos) - 1))
        self._proto_selected(self.l_protos.currentRow())

    def _cur(self) -> dict | None:
        i = self.l_protos.currentRow()
        return self.protos[i] if 0 <= i < len(self.protos) else None

    def _proto_selected(self, _i: int) -> None:
        pr = self._cur()
        if pr is None:
            return
        self._loading = True
        self.e_name.setText(pr.get("name", ""))
        self.e_desc.setText(pr.get("description", ""))
        self.c_enabled.setChecked(pr.get("enabled", True))
        self.c_center.setChecked(pr.get("chest_to_center", True))
        self.c_align.setChecked(pr.get("align_chest", True))
        self.c_sync.setChecked(pr.get("sync_zoom", True))
        self.c_alinhar.setCurrentIndex(max(0, self.c_alinhar.findData(M.alinhamento_do_protocolo(pr))))
        self._loading = False
        self._fill_steps()

    def _store_proto(self) -> None:
        pr = self._cur()
        if pr is None or self._loading:
            return
        pr.update({"name": self.e_name.text().strip() or "Mamografia", "description": self.e_desc.text().strip(),
                   "enabled": self.c_enabled.isChecked(), "chest_to_center": self.c_center.isChecked(),
                   "align_chest": self.c_align.isChecked(), "sync_zoom": self.c_sync.isChecked(),
                   "alinhar": self.c_alinhar.currentData() or M.ALINHAMENTO_PADRAO})
        it = self.l_protos.currentItem()
        if it is not None:
            it.setText(("" if pr["enabled"] else "(inativo) ") + pr["name"])

    def _new_proto(self) -> None:
        self.protos.append({"name": "Novo protocolo", "enabled": True, "description": "", "chest_to_center": True,
                            "align_chest": True, "sync_zoom": True,
                            "steps": [{"name": "", "rows": 1, "cols": 2, "cells": ["CCD", "CCE"]}]})
        self._fill_protos(len(self.protos) - 1)

    def _dup_proto(self) -> None:
        pr = self._cur()
        if pr is not None:
            import copy
            q = copy.deepcopy(pr)
            q["name"] = pr.get("name", "") + " (cópia)"
            self.protos.append(q)
            self._fill_protos(len(self.protos) - 1)

    def _del_proto(self) -> None:
        i = self.l_protos.currentRow()
        if 0 <= i < len(self.protos) and len(self.protos) > 1:
            del self.protos[i]
            self._fill_protos(max(0, i - 1))

    def _reset(self) -> None:
        if QMessageBox.question(self, "Mamografia", "Voltar aos protocolos de fábrica?") == QMessageBox.Yes:
            import copy
            self.protos = copy.deepcopy(M.DEFAULT_MG_PROTOCOLS)
            self._fill_protos()

    # ------------------------------------------------------------------ etapas
    def _steps(self) -> list[dict]:
        pr = self._cur()
        return pr.setdefault("steps", []) if pr is not None else []

    def _fill_steps(self, select: int = 0) -> None:
        self.l_steps.blockSignals(True)
        self.l_steps.clear()
        for k, st in enumerate(self._steps()):
            self.l_steps.addItem(f"{k + 1}. {M.step_title(st)}")
        self.l_steps.blockSignals(False)
        if self._steps():
            self.l_steps.setCurrentRow(min(select, len(self._steps()) - 1))
        else:
            self._step_selected(-1)

    def _cur_step(self) -> dict | None:
        i = self.l_steps.currentRow()
        s = self._steps()
        return s[i] if 0 <= i < len(s) else None

    def _step_selected(self, _i: int) -> None:
        st = self._cur_step()
        self._loading = True
        self.e_step_name.setText(st.get("name", "") if st else "")
        self.c_enquadre.setCurrentIndex(max(0, self.c_enquadre.findData(M.enquadre_da_etapa(st))))
        self._loading = False
        self._fill_monitores()

    def _telas_escolhidas(self) -> int:
        return int(self.c_telas.currentData() or 1)

    def _monitor_escolhido(self) -> int:
        return max(0, self.c_monitor.currentIndex())

    def _fill_monitores(self) -> None:
        """A lista de monitores segue a quantidade de telas escolhida."""
        n = self._telas_escolhidas()
        self._loading = True
        atual = self.c_monitor.currentIndex()
        self.c_monitor.clear()
        for k in range(n):
            self.c_monitor.addItem(f"Monitor {k + 1}")
        self.c_monitor.setCurrentIndex(min(max(0, atual), n - 1))
        self.c_monitor.setEnabled(n > 1)
        self.b_auto.setEnabled(n > 1 and bool((self._cur_step() or {}).get("telas", {}).get(str(n))))
        self._loading = False
        self._alvo_mudou()

    def _alvo_mudou(self) -> None:
        if self._loading:
            return
        if self.c_monitor.count() != self._telas_escolhidas():
            self._fill_monitores()
            return
        st = self._cur_step()
        n, k = self._telas_escolhidas(), self._monitor_escolhido()
        self.b_auto.setEnabled(n > 1 and bool((st or {}).get("telas", {}).get(str(n))))
        q = M.quadro_da_etapa(st, n, k) if st else {"rows": 1, "cols": 2, "cells": ["", ""]}
        self._loading = True
        self.s_rows.setValue(int(q["rows"]))
        self.s_cols.setValue(int(q["cols"]))
        self._loading = False
        self._build_grid(q)

    def _quadro_atual(self) -> dict | None:
        """O dicionário que está sendo editado: a própria etapa (1 tela) ou o quadro daquela tela.

        Ao mexer num arranjo que ainda não existia, ele é criado a partir da repartição
        automática — o que estava na tela continua valendo como ponto de partida.
        """
        st = self._cur_step()
        if st is None:
            return None
        n, k = self._telas_escolhidas(), self._monitor_escolhido()
        if n == 1:
            return st
        telas = st.setdefault("telas", {})
        arranjo = telas.get(str(n))
        if not isinstance(arranjo, list) or len(arranjo) != n:
            arranjo = M.repartir_etapa(st, n)
            telas[str(n)] = arranjo
        return arranjo[min(k, n - 1)]

    def _repartir_sozinho(self) -> None:
        st = self._cur_step()
        n = self._telas_escolhidas()
        if st is None or n == 1:
            return
        (st.get("telas") or {}).pop(str(n), None)
        if not st.get("telas"):
            st.pop("telas", None)
        self._alvo_mudou()

    def _build_grid(self, q: dict | None = None) -> None:
        for c in self.cells:
            c.setParent(None)
        self.cells = []
        st = self._cur_step()
        if st is None:
            self.e_text.setText("")
            return
        if q is None:
            q = M.quadro_da_etapa(st, self._telas_escolhidas(), self._monitor_escolhido())
        rows, cols = int(q["rows"]), int(q["cols"])
        cells = list(q["cells"]) + [""] * (rows * cols - len(q["cells"]))
        for k in range(rows * cols):
            cb = QComboBox()
            cb.setEditable(True)
            cb.addItems(CELL_CHOICES)
            cb.setCurrentText(cells[k])
            cb.setToolTip(f"Linha {k // cols + 1}, coluna {k % cols + 1}")
            cb.currentTextChanged.connect(lambda _t: self._store_step())
            self.grid.addWidget(cb, k // cols, k % cols)
            self.cells.append(cb)
        self.e_text.setText(M.step_text(q))

    def _resize_grid(self) -> None:
        if self._loading:
            return
        q = self._quadro_atual()
        if q is None:
            return
        rows, cols = self.s_rows.value(), self.s_cols.value()
        old_r, old_c = int(q["rows"]), int(q["cols"])
        old = list(q["cells"])
        new = []
        for r in range(rows):
            for c in range(cols):
                new.append(old[r * old_c + c] if r < old_r and c < old_c and r * old_c + c < len(old) else "")
        q.update({"rows": rows, "cols": cols, "cells": new})
        self._build_grid(q)
        self._refresh_step_title()

    def _store_step(self) -> None:
        if self._loading:
            return
        st = self._cur_step()
        if st is None:
            return
        st["name"] = self.e_step_name.text().strip()
        st["enquadre"] = self.c_enquadre.currentData() or M.ENQUADRE_PADRAO
        q = self._quadro_atual()
        if q is not None and self.cells:
            q["cells"] = [c.currentText().strip() for c in self.cells]
            self.e_text.setText(M.step_text(q))
        self.b_auto.setEnabled(self._telas_escolhidas() > 1
                               and bool(st.get("telas", {}).get(str(self._telas_escolhidas()))))
        self._refresh_step_title()

    def _text_edited(self) -> None:
        q = self._quadro_atual()
        if q is None:
            return
        parsed = M.parse_step(self.e_text.text())
        bad = [c for c in parsed["cells"] if c and M.parse_code(c) is None and M.parse_outro(c) is None]
        if bad:
            QMessageBox.warning(self, "Etapa", "Código(s) não reconhecido(s): " + ", ".join(bad))
            return
        q.update({"rows": parsed["rows"], "cols": parsed["cols"], "cells": parsed["cells"]})
        self._alvo_mudou()
        self._refresh_step_title()

    def _refresh_step_title(self) -> None:
        it = self.l_steps.currentItem()
        st = self._cur_step()
        if it is not None and st is not None:
            it.setText(f"{self.l_steps.currentRow() + 1}. {M.step_title(st)}")

    def _new_step(self) -> None:
        self._steps().append({"name": "", "rows": 1, "cols": 2, "cells": ["CCD", "CCE"]})
        self._fill_steps(len(self._steps()) - 1)

    def _del_step(self) -> None:
        i = self.l_steps.currentRow()
        s = self._steps()
        if 0 <= i < len(s) and len(s) > 1:
            del s[i]
            self._fill_steps(max(0, i - 1))

    def _move(self, d: int) -> None:
        i = self.l_steps.currentRow()
        s = self._steps()
        j = i + d
        if 0 <= i < len(s) and 0 <= j < len(s):
            s[i], s[j] = s[j], s[i]
            self._fill_steps(j)

    # ------------------------------------------------------------------ gravar
    def save(self) -> None:
        self._store_proto()
        self._store_step()
        self.settings.set("mg_protocols", self.protos)


class MgProtocolsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Protocolos de mamografia")
        self.resize(980, 640)
        lay = QVBoxLayout(self)
        self.editor = MgProtocolsEditor(settings, self)
        lay.addWidget(self.editor)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.settings = settings

    def _ok(self) -> None:
        self.editor.save()
        self.settings.save()
        self.accept()
