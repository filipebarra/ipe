"""Preferências: mouse, atalhos de teclado, presets de janela e opções gerais."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QGroupBox, QHeaderView, QKeySequenceEdit,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QHBoxLayout, QScrollArea, QVBoxLayout, QWidget,
)

from ipe.core.config import DEFAULT_SETTINGS
from ipe.core.sysinfo import auto_cache_mb, auto_volume_mb, total_ram_mb
from ipe.ui.monitors import ROLES, identify_screens, screen_key, screen_label
from ipe.ui.viewer.actions import ACTIONS, shortcut_for
from ipe.ui.viewer.viewer_tab import LAYOUTS, ViewerTab

from ipe.ui.viewer.annotate import TOOLS  # noqa: E402
from ipe.ui.tabelas import colunas_ajustaveis
from ipe.ui.table_filter import fold

# qualquer ferramenta da barra pode ir para o direito/meio (arrastar ou clique, conforme a ferramenta)
DRAG_ACTIONS = list(TOOLS.items()) + [("none", "Nada")]
LEFT_TOOLS = list(TOOLS.items())
SIDE_ACTIONS = [("series_prev", "Série anterior"), ("series_next", "Próxima série"),
                ("frame_prev", "Corte anterior"), ("frame_next", "Próximo corte"),
                ("key", "Marcar imagem-chave"), ("none", "Nada")]
CLICK_ACTIONS = [("menu", "Menu flutuante"), ("fit", "Ajustar à janela"), ("none", "Nada")]
WHEEL_ACTIONS = [("scroll", "Rolar 1 corte"), ("scroll5", "Rolar 5 cortes"), ("zoom", "Zoom"),
                 ("none", "Nada")]


def _combo(options, current) -> QComboBox:
    c = QComboBox()
    for key, label in options:
        c.addItem(label, key)
    i = c.findData(current)
    c.setCurrentIndex(max(0, i))
    return c


def _rolavel(interno: QWidget) -> QWidget:
    """A aba cresceu: com seções, ela passa da altura da janela em tela pequena.

    Sem a barra de rolagem, a última seção fica fora do alcance — e opção fora do alcance é
    opção que não existe.
    """
    area = QScrollArea()
    area.setWidget(interno)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    return area


#: As janelas do menu Configurações (0.99.12): cada item abre **uma** página, sozinha.
#: id -> (título da janela, aba de onde ela vem, seções da aba que aparecem — None = a aba inteira)
PAGINAS: dict[str, tuple[str, str, tuple | None]] = {
    "mouse": ("Mouse", "Mouse", None),
    "atalhos": ("Atalhos de teclado", "Atalhos de teclado", None),
    "presets": ("Presets de janela", "Presets de janela", None),
    "anotacoes": ("Anotações", "Anotações", None),
    "aparencia": ("Texto e marcas sobre a imagem", "Geral", ("Texto e marcas sobre a imagem",)),
    "sincronia": ("Sincronização automática", "Geral", ("Sincronização automática no mesmo estudo",)),
    "botoes": ("Botões extras na barra", "Geral", ("Botões na barra do visualizador",)),
    "protocolos": ("Protocolos de exibição", "Protocolos de exibição", None),
    "mamografia": ("Mamografia", "Mamografia", None),
    "dinamica_mama": ("Dinâmica da mama", "Dinâmica da mama", None),
    "dinamicos": ("Dinâmicos (juntar e separar séries)", "Dinâmicos", None),
    "cad_ia": ("CAD/IA", "CAD/IA", None),
    "monitores": ("Monitores", "Monitores", None),
    "desempenho": ("Desempenho", "Desempenho", None),
    "abertura": ("Ao abrir o programa", "Geral", ("Ao abrir o programa",)),
    "importacao": ("Importação", "Geral", ("Importação",)),
    "idioma": ("Idioma", "Geral", ("Idioma",)),
    "modulos": ("Módulos", "Módulos", None),
}
SECOES_DA_GERAL = ("Ao abrir o programa", "Texto e marcas sobre a imagem",
                   "Sincronização automática no mesmo estudo", "Botões na barra do visualizador",
                   "Importação", "Idioma")


class PreferencesDialog(QDialog):
    def __init__(self, settings, parent=None, pagina: str = ""):
        super().__init__(parent)
        self.settings = settings
        self.pagina = pagina if pagina in PAGINAS else ""
        self.setWindowTitle("Preferências")
        self.resize(720, 560)
        tabs = QTabWidget()
        tabs.addTab(self._mouse_tab(), "Mouse")
        tabs.addTab(self._shortcuts_tab(), "Atalhos de teclado")
        tabs.addTab(self._presets_tab(), "Presets de janela")
        tabs.addTab(self._monitors_tab(), "Monitores")
        tabs.addTab(self._performance_tab(), "Desempenho")
        tabs.addTab(self._hanging_tab(), "Protocolos de exibição")
        tabs.addTab(self._dinamicas_tab(), "Dinâmicos")
        from ipe.ui.viewer.dinamica_editor import DinamicaMamaEditor
        self.din_mama = DinamicaMamaEditor(settings, self)
        tabs.addTab(_rolavel(self.din_mama), "Dinâmica da mama")
        from ipe.ui.viewer.anotacoes_editor import AnotacoesEditor
        self.anot_editor = AnotacoesEditor(settings, self)
        tabs.addTab(self.anot_editor, "Anotações")
        from ipe.ui.viewer.mammo_view import MgProtocolsEditor
        self.mg_editor = MgProtocolsEditor(settings, self)
        tabs.addTab(self.mg_editor, "Mamografia")
        from ipe.ui.cad_ia import CadIaTab
        self.cad_ia = CadIaTab(settings, getattr(parent, "repo", None), self)
        tabs.addTab(_rolavel(self.cad_ia), "CAD/IA")
        tabs.addTab(self._general_tab(), "Geral")
        tabs.addTab(self._modulos_tab(), "Módulos")
        self.tabs = tabs
        from ipe.auth import session as S
        if not S.can("configure"):          # do computador: só quem configura
            for i in range(tabs.count()):
                if tabs.tabText(i) in ("Monitores", "Desempenho"):
                    tabs.setTabEnabled(i, False)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel |
                              QDialogButtonBox.RestoreDefaults)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.button(QDialogButtonBox.RestoreDefaults).setText("Restaurar padrões")
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)
        if self.pagina:
            self._so_a_pagina(bb)

    def _so_a_pagina(self, bb) -> None:
        """Mostra só a página pedida pelo menu Configurações: sem as outras abas e sem as outras
        seções da aba. O resto continua montado por baixo (e é gravado igual a como estava), para
        que salvar uma página nunca mexa no que as outras guardam."""
        titulo, aba, secoes = PAGINAS[self.pagina]
        self.setWindowTitle(f"Configurações — {titulo}")
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == aba:
                self.tabs.setCurrentIndex(i)
                break
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        if secoes:
            pagina = self.tabs.currentWidget()
            for g in pagina.findChildren(QGroupBox):
                if g.title() in SECOES_DA_GERAL:
                    g.setVisible(g.title() in secoes)
            self.resize(620, 360)
        # "Restaurar padrões" volta **tudo** aos de fábrica: numa janela de um assunto só, não
        bb.button(QDialogButtonBox.RestoreDefaults).hide()

    # ------------------------------------------------------------ abas
    def _mouse_tab(self) -> QWidget:
        m = self.settings.get("viewer.mouse", {})
        w = QWidget()
        f = QFormLayout(w)
        self.c_left = _combo(LEFT_TOOLS, m.get("left", "wl"))
        self.c_right = _combo(DRAG_ACTIONS, m.get("right", "zoom"))
        self.c_right_click = _combo(CLICK_ACTIONS, m.get("right_click", "menu"))
        self.c_middle = _combo(DRAG_ACTIONS, m.get("middle", "pan"))
        self.c_middle_click = _combo(CLICK_ACTIONS, m.get("middle_click", "fit"))
        self.c_wheel = _combo(WHEEL_ACTIONS, m.get("wheel", "scroll"))
        self.c_ctrl_wheel = _combo(WHEEL_ACTIONS, m.get("ctrl_wheel", "zoom"))
        self.c_shift_wheel = _combo(WHEEL_ACTIONS, m.get("shift_wheel", "scroll5"))
        self.c_back = _combo(SIDE_ACTIONS, m.get("back", "series_prev"))
        self.c_forward = _combo(SIDE_ACTIONS, m.get("forward", "series_next"))
        self.s_click_ms = QSpinBox(minimum=80, maximum=800, suffix=" ms",
                                   value=int(self.settings.get("viewer.click_max_ms", 220)))
        self.s_click_px = QSpinBox(minimum=1, maximum=20, suffix=" px",
                                   value=int(self.settings.get("viewer.click_max_px", 4)))
        self.cb_invert_wheel = QCheckBox("Inverter a direção da rodinha")
        self.cb_invert_wheel.setChecked(bool(self.settings.get("viewer.invert_wheel", False)))
        f.addRow(QLabel("<b>Botões</b>"))
        f.addRow("Esquerdo (ferramenta inicial):", self.c_left)
        tip = QLabel("Dica: clique com o botão direito ou do meio num ícone da barra do visualizador para "
                     "atribuir a ferramenta a esse botão. Com ferramenta de medida/filme no direito, "
                     "Shift + clique direito abre o menu.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#9a9a9a")
        f.addRow(tip)
        f.addRow("Direito — segurar e arrastar:", self.c_right)
        f.addRow("Direito — clicar e soltar:", self.c_right_click)
        f.addRow("Meio — segurar e arrastar:", self.c_middle)
        f.addRow("Meio — clicar:", self.c_middle_click)
        f.addRow(QLabel("<b>Rodinha</b>"))
        f.addRow("Rodinha:", self.c_wheel)
        f.addRow("Ctrl + rodinha:", self.c_ctrl_wheel)
        f.addRow("Shift + rodinha:", self.c_shift_wheel)
        f.addRow("", self.cb_invert_wheel)
        f.addRow(QLabel("<b>Botões laterais</b> (4 e 5, nos mouses que têm)"))
        f.addRow("Botão 4 (voltar):", self.c_back)
        f.addRow("Botão 5 (avançar):", self.c_forward)
        f.addRow(QLabel("<small>As teclas que emprestam o botão esquerdo (Shift, Ctrl) ficam na aba "
                        "Atalhos de teclado.</small>"))
        f.addRow(QLabel("<b>Clique × segurar</b> — um clique precisa ser mais rápido e mover menos que:"))
        f.addRow("Tempo máximo do clique:", self.s_click_ms)
        f.addRow("Movimento máximo do clique:", self.s_click_px)
        return w

    def _shortcuts_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Clique no atalho e pressione a nova combinação. "
                             "Deixe vazio para desativar."))
        # São mais de 80 ações e, de fábrica, quase nenhuma tem tecla: configurar significa
        # **achar** a ação. Daí a busca e o cabeçalho que ordena. A tabela é remontada a cada
        # busca e a cada troca de ordem, e quem manda na tecla é `key_values`, não o editor na
        # tela: QTableWidget apaga o widget da célula quando a linha sai, então guardar o valor
        # no widget perderia o que ele digitou ao filtrar — e ação escondida pela busca tem de
        # continuar valendo na hora de salvar.
        self.e_busca_atalho = QLineEdit()
        self.e_busca_atalho.setPlaceholderText("Buscar ação, grupo ou atalho (acento não importa)")
        self.e_busca_atalho.setClearButtonEnabled(True)
        self.e_busca_atalho.textChanged.connect(lambda _t: self._keys_montar())
        lay.addWidget(self.e_busca_atalho)

        self.t_keys = QTableWidget(0, 3)
        self.t_keys.setHorizontalHeaderLabels(["Grupo", "Ação", "Atalho"])
        self.t_keys.verticalHeader().setVisible(False)
        self.t_keys.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.key_values: dict[str, str] = {aid: shortcut_for(self.settings, aid)
                                           for aid, _name, _default, _group in ACTIONS}
        self.key_edits: dict[str, QKeySequenceEdit] = {}
        self._keys_ordem: tuple[int, object] = (0, Qt.AscendingOrder)
        cab = self.t_keys.horizontalHeader()
        cab.setSectionsClickable(True)
        cab.setSortIndicatorShown(True)
        cab.setSortIndicator(0, Qt.AscendingOrder)
        cab.sectionClicked.connect(self._keys_ordenar)
        cab.setToolTip("Clique no título da coluna para ordenar; clique de novo para inverter.")
        lay.addWidget(self.t_keys)
        self.l_keys_conta = QLabel()
        self.l_keys_conta.setWordWrap(True)
        lay.addWidget(self.l_keys_conta)
        self._keys_montar()
        self.t_keys.setColumnWidth(2, 160)
        colunas_ajustaveis(self.t_keys)
        fixed = QLabel("Fixos: ↑↓ ou PgUp/PgDn rolam os cortes; Home/End primeira/última; "
                       "1–9 presets; 0 janela do arquivo; Del apaga medidas do corte. "
                       "As setas ← → saíram da navegação: são o atalho das etapas do protocolo "
                       "de mamografia.")
        fixed.setWordWrap(True)
        lay.addWidget(fixed)

        # Tecla segurada ≠ atalho: ela **empresta** o botão esquerdo enquanto está apertada e
        # devolve ao soltar, sem trocar a ferramenta da barra. Por isso é um menu de teclas, e
        # não uma caixa de combinação como as de cima — modificador sozinho não se digita ali.
        from ipe.ui.viewer.viewport import Viewport
        emp = QLabel("<b>Teclas que emprestam o botão esquerdo</b> — valem só enquanto você segura; "
                     "a ferramenta escolhida na barra não muda, e ao soltar tudo volta ao que era.")
        emp.setWordWrap(True)
        lay.addWidget(emp)
        atual = Viewport.PADRAO_TECLAS.copy()
        guardado = self.settings.get("viewer.teclas_emprestadas", None)
        if guardado is None:
            if not self.settings.get("viewer.teclas_do_mouse", True):
                atual = {}
        else:
            atual = dict(guardado or {})
        opcoes = [("shift", "Shift"), ("ctrl", "Ctrl"), ("alt", "Alt  (também solta a sincronia)"),
                  ("", "Nenhuma")]
        self.c_teclas: dict[str, QComboBox] = {}
        fe = QFormLayout()
        for ferramenta, rotulo, dica in (
                ("cross", "Cursor 3D (o ponto segue o mouse, sem clicar):",
                 "Segurando esta tecla, o ponto 3D acompanha o mouse mesmo sem clicar."),
                ("scroll", "Rolar cortes (segurar o esquerdo e mover):",
                 "Segurando esta tecla, o botão esquerdo rola os cortes.")):
            c = _combo(opcoes, atual.get(ferramenta, ""))
            c.setToolTip(dica)
            self.c_teclas[ferramenta] = c
            fe.addRow(rotulo, c)
        lay.addLayout(fe)
        return w

    def _keys_ordenar(self, col: int) -> None:
        coluna, ordem = self._keys_ordem
        nova = (Qt.DescendingOrder if coluna == col and ordem == Qt.AscendingOrder
                else Qt.AscendingOrder)
        self._keys_ordem = (col, nova)
        self.t_keys.horizontalHeader().setSortIndicator(col, nova)
        self._keys_montar()

    def _keys_sincronizar(self) -> None:
        """Leva para `key_values` o que está nos editores da tela — eles são refeitos a cada busca."""
        for aid, ed in list(self.key_edits.items()):
            try:
                self.key_values[aid] = ed.keySequence().toString()
            except RuntimeError:                  # editor já apagado pela tabela
                self.key_edits.pop(aid, None)

    def _keys_linhas(self) -> list[tuple[str, str, str, str]]:
        """As ações na ordem e com a busca escolhidas: (id, grupo, nome, atalho de agora).

        O atalho vem de `key_values`: ordenar ou buscar por atalho depois de digitar um tem de
        levar a tecla nova em conta, mesmo que a linha dela esteja fora da tela.
        """
        col, ordem = self._keys_ordem
        termo = fold(self.e_busca_atalho.text().strip())
        linhas = []
        for aid, nome, _default, grupo in ACTIONS:
            tecla = self.key_values.get(aid, "")
            if termo and termo not in fold(f"{grupo} {nome} {tecla}"):
                continue
            linhas.append((aid, grupo, nome, tecla))
        chaves = {
            0: lambda r: (fold(r[1]), fold(r[2])),
            1: lambda r: (fold(r[2]), fold(r[1])),
            # sem tecla vai para o fim na ordem crescente (e para o começo na decrescente, que é
            # justamente "me mostre o que ainda está vazio")
            2: lambda r: (not r[3], fold(r[3]), fold(r[2])),
        }
        linhas.sort(key=chaves.get(col, chaves[0]), reverse=ordem == Qt.DescendingOrder)
        return linhas

    def _keys_montar(self) -> None:
        self._keys_sincronizar()
        linhas = self._keys_linhas()
        t = self.t_keys
        self.key_edits = {}
        t.setRowCount(0)                    # aqui a tabela apaga os editores; o valor já está guardado
        t.setRowCount(len(linhas))
        for row, (aid, grupo, nome, tecla) in enumerate(linhas):
            for col, texto in ((0, grupo), (1, nome)):
                it = QTableWidgetItem(texto)
                it.setFlags(Qt.ItemIsEnabled)
                t.setItem(row, col, it)
            ed = QKeySequenceEdit(QKeySequence(tecla))
            ed.keySequenceChanged.connect(
                lambda ks, a=aid: self.key_values.__setitem__(a, ks.toString()))
            t.setCellWidget(row, 2, ed)
            self.key_edits[aid] = ed
        if not getattr(self, "_keys_montada", False):
            t.resizeColumnToContents(0)     # só na primeira vez: depois a largura é escolha dele
            self._keys_montada = True
        total = len(ACTIONS)
        com_tecla = sum(1 for k in self.key_values.values() if k)
        if not linhas:
            self.l_keys_conta.setText(f"Nenhuma das {total} ações combina com a busca.")
        elif len(linhas) == total:
            self.l_keys_conta.setText(f"São {total} ações, {com_tecla} com atalho.")
        else:
            self.l_keys_conta.setText(f"Mostrando {len(linhas)} de {total} ações "
                                      f"({com_tecla} com atalho no total).")

    def teclas_emprestadas(self) -> dict[str, str]:
        return {f: c.currentData() for f, c in self.c_teclas.items() if c.currentData()}

    #: listas de presets de janela: a geral e uma por modalidade (0.99.22)
    PRESET_LISTAS = (("", "Geral (e TC)"), ("CT", "TC (lista própria)"), ("MR", "RM"), ("MG", "Mamografia"),
                     ("PT", "PET"), ("NM", "Medicina nuclear"), ("CR", "Raio X (CR)"), ("DX", "Raio X (DX)"),
                     ("US", "Ultrassom"), ("XA", "Angiografia"))

    def _presets_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        mods = self.settings.get("viewer.wl_presets_mod", {}) or {}
        self._presets_listas = {"": dict(self.settings.get("viewer.wl_presets", {}) or {})}
        self._presets_listas.update({k: dict(v) for k, v in mods.items() if isinstance(v, dict)})
        topo = QHBoxLayout()
        topo.addWidget(QLabel("Lista:"))
        self.c_preset_lista = QComboBox()
        for chave, nome in self.PRESET_LISTAS:
            self.c_preset_lista.addItem(nome, chave)
        topo.addWidget(self.c_preset_lista, 1)
        lay.addLayout(topo)
        self.t_presets = QTableWidget(9, 4)
        self.t_presets.setHorizontalHeaderLabels(["Tecla", "Nome", "Largura (W)", "Nível (L)"])
        self.t_presets.verticalHeader().setVisible(False)
        self.t_presets.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._preset_lista_atual = ""
        self._mostrar_presets("")
        self.c_preset_lista.currentIndexChanged.connect(self._trocar_lista_de_presets)
        lay.addWidget(self.t_presets)
        colunas_ajustaveis(self.t_presets)
        lay.addWidget(QLabel("Deixe o nome vazio para não usar a tecla. A modalidade com lista vazia usa a "
                             "geral. No quadro, o menu da janela tem \"Guardar a janela atual como preset\"."))
        return w

    def _mostrar_presets(self, chave: str) -> None:
        presets = self._presets_listas.get(chave, {}) or {}
        for row in range(9):
            key = str(row + 1)
            name, ww, wl = presets.get(key, ["", "", ""])
            k_item = QTableWidgetItem(key)
            k_item.setFlags(Qt.ItemIsEnabled)
            self.t_presets.setItem(row, 0, k_item)
            for col, val in ((1, name), (2, ww), (3, wl)):
                self.t_presets.setItem(row, col, QTableWidgetItem(str(val)))

    def _ler_presets_da_tabela(self) -> dict | None:
        presets = {}
        for row in range(9):
            name = (self.t_presets.item(row, 1).text() or "").strip()
            if not name:
                continue
            try:
                ww = float(self.t_presets.item(row, 2).text().replace(",", "."))
                wl = float(self.t_presets.item(row, 3).text().replace(",", "."))
            except ValueError:
                QMessageBox.warning(self, "Preset inválido", f"Largura/nível inválidos na tecla {row + 1}.")
                return None
            presets[str(row + 1)] = [name, ww, wl]
        return presets

    def _trocar_lista_de_presets(self, _i: int) -> None:
        lidos = self._ler_presets_da_tabela()
        if lidos is None:
            i = self.c_preset_lista.findData(self._preset_lista_atual)
            self.c_preset_lista.blockSignals(True)
            self.c_preset_lista.setCurrentIndex(i)
            self.c_preset_lista.blockSignals(False)
            return
        self._presets_listas[self._preset_lista_atual] = lidos
        self._preset_lista_atual = self.c_preset_lista.currentData()
        self._mostrar_presets(self._preset_lista_atual)


    DIN_COLS = ["Ação", "Modalidade", "Descrição contém", "Nome", "Situação", "Exame de origem"]

    def _dinamicas_tab(self) -> QWidget:
        """Duas coisas opostas do mesmo assunto, no mesmo lugar: juntar e separar."""
        from ipe.imaging import dinamicas as D
        w = QWidget()
        lay = QVBoxLayout(w)
        tip = QLabel("Ao abrir um exame, as regras **confirmadas** valem sozinhas. "
                     "“Juntar” é para o aparelho que grava uma série por fase (RM de mama): as séries "
                     "viram uma dinâmica. “Separar” é para o aparelho que grava todas as fases na mesma "
                     "série (comum na TC): a série é repartida em fases **só na tela** — o banco e os "
                     "arquivos não mudam.")
        tip.setWordWrap(True)
        tip.setTextFormat(Qt.MarkdownText)
        tip.setStyleSheet("color:#9a9a9a")
        lay.addWidget(tip)
        nota = QLabel("Quando você marca uma dinâmica na mão, o programa anota a regra aqui como "
                      "**pendente**. Pendente não age. Na coluna Situação você escolhe: "
                      "**Confirmada** (vale em todo exame), **Ignorar** (vale só no exame onde foi "
                      "criada, para o arranjo voltar quando você reabrir aquele exame) ou deixar "
                      "pendente. O botão **Remover** apaga a regra de vez.")
        nota.setWordWrap(True)
        nota.setTextFormat(Qt.MarkdownText)
        nota.setStyleSheet("color:#9a9a9a")
        lay.addWidget(nota)
        t = QTableWidget(0, len(self.DIN_COLS))
        t.setHorizontalHeaderLabels(self.DIN_COLS)
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        self.din_table = t
        for r in D.carregar(self.settings):
            self._din_add(r)
        lay.addWidget(t, 1)
        colunas_ajustaveis(t)
        row = QHBoxLayout()
        row.addWidget(self._botao("+ Juntar", lambda: self._din_add(
            {"acao": "juntar", "modalidade": "MR", "contem": "", "nome": "Dinâmica",
             "status": "confirmada", "exame": "", "estudo": ""})))
        row.addWidget(self._botao("+ Separar", lambda: self._din_add(
            {"acao": "separar", "modalidade": "CT", "contem": "", "nome": "Fases",
             "status": "confirmada"})))
        row.addWidget(self._botao("Remover regra", lambda: t.removeRow(t.currentRow())
                                  if t.currentRow() >= 0 else None))
        row.addWidget(self._botao("Ignorar (só no exame de origem)", self._din_ignorar))
        row.addStretch(1)
        lay.addLayout(row)
        return w

    @staticmethod
    def _botao(texto, fn) -> QPushButton:
        b = QPushButton(texto)
        b.clicked.connect(fn)
        return b

    def _din_add(self, r: dict) -> None:
        from ipe.imaging import dinamicas as D
        t = self.din_table
        i = t.rowCount()
        t.insertRow(i)
        c_acao = _combo(list(D.ACOES.items()), r.get("acao", "juntar"))
        t.setCellWidget(i, 0, c_acao)
        t.setItem(i, 1, QTableWidgetItem((r.get("modalidade") or "").upper()))
        t.setItem(i, 2, QTableWidgetItem(r.get("contem", "")))
        t.setItem(i, 3, QTableWidgetItem(r.get("nome", "")))
        c_st = _combo(list(D.STATUS.items()), r.get("status", "confirmada"))
        t.setCellWidget(i, 4, c_st)
        origem = QTableWidgetItem(r.get("exame", ""))
        origem.setFlags(Qt.ItemIsEnabled)          # é de onde ela veio, não se edita
        origem.setData(Qt.UserRole, r.get("estudo", ""))
        origem.setToolTip("Exame em que esta regra foi criada. “Ignorar” faz a regra valer só nele."
                          if r.get("exame") else "Regra escrita à mão: não tem exame de origem, "
                          "então “Ignorar” equivale a desligá-la.")
        t.setItem(i, 5, origem)
        t.resizeColumnsToContents()
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

    def _din_ignorar(self) -> None:
        i = self.din_table.currentRow()
        if i < 0:
            return
        c = self.din_table.cellWidget(i, 4)
        c.setCurrentIndex(max(0, c.findData("ignorada")))

    def regras_dinamicas(self) -> list[dict]:
        t = self.din_table
        out = []
        for i in range(t.rowCount()):
            contem = (t.item(i, 2).text() if t.item(i, 2) else "").strip()
            if not contem:
                continue
            origem = t.item(i, 5)
            out.append({"acao": t.cellWidget(i, 0).currentData(),
                        "modalidade": (t.item(i, 1).text() if t.item(i, 1) else "").strip().upper(),
                        "contem": contem,
                        "nome": (t.item(i, 3).text() if t.item(i, 3) else "").strip() or "Dinâmica",
                        "status": t.cellWidget(i, 4).currentData(),
                        "estudo": (origem.data(Qt.UserRole) if origem else "") or "",
                        "exame": (origem.text() if origem else "")})
        return out

    def _ordenar_pela_posicao(self) -> None:
        """Ordem pela posição física: da esquerda para a direita, de cima para baixo."""
        por_pos = sorted(range(len(self._telas)),
                         key=lambda i: (self._telas[i].geometry().x(), self._telas[i].geometry().y()))
        for n, i in enumerate(por_pos, 1):
            self.mon_rows[i][3].setValue(n)

    def _hanging_tab(self) -> QWidget:
        """Protocolos de exibição com etapas (0.88): ver ui/viewer/protocolos_editor.py."""
        from ipe.ui.viewer.protocolos_editor import ProtocolosEditor
        self.hp_editor = ProtocolosEditor(self.settings, self)
        return self.hp_editor

    def hanging_protocols(self) -> list[dict]:
        return self.hp_editor.protocolos()

    def _modulos_tab(self) -> QWidget:
        """Ligar e desligar módulos (0.84). O dado fica, a ferramenta some."""
        from ipe import modules as MOD
        w = QWidget()
        lay = QVBoxLayout(w)
        expl = QLabel("Desligue o que não usa: os botões e serviços daquele módulo somem do programa. "
                      "<b>Nenhum exame é apagado</b> — o exame continua abrindo como imagem comum, e "
                      "religar o módulo devolve tudo.")
        expl.setWordWrap(True)
        lay.addWidget(expl)
        fora = MOD.desligados(self.settings)
        self.c_modulos: dict[str, QCheckBox] = {}
        for mid, (nome, oque) in MOD.MODULOS.items():
            cb = QCheckBox(nome)
            cb.setChecked(mid not in fora)
            cb.setStyleSheet("font-weight:bold")
            det = QLabel(oque)
            det.setWordWrap(True)
            det.setStyleSheet("color:#9a9a9a; margin-left:22px")
            lay.addWidget(cb)
            lay.addWidget(det)
            self.c_modulos[mid] = cb
        lay.addStretch(1)
        from ipe.auth import session as S
        if not S.can("configure"):
            for cb in self.c_modulos.values():
                cb.setEnabled(False)
        return w

    def _general_tab(self) -> QWidget:
        """Geral, em seções. Era uma pilha de caixas sem assunto: importação, letra, bandeja e
        idioma na mesma lista. Cada coisa agora mora junto do que é do mesmo assunto."""
        from ipe.core import i18n
        w = QWidget()
        raiz = QVBoxLayout(w)

        # --- ao abrir o programa
        g1 = QGroupBox("Ao abrir o programa")
        f1 = QFormLayout(g1)
        self.c_maximizada = QCheckBox("Abrir maximizado")
        self.c_maximizada.setChecked(bool(self.settings.get("ui.start_maximized", True)))
        self.c_maximizada.setToolTip("Vale para a janela do banco de dados, na tela em que ela abre.")
        f1.addRow(self.c_maximizada)
        self.c_todas_max = QCheckBox("Abrir as janelas no centro da tela, com 80% do tamanho dela")
        self.c_todas_max.setChecked(bool(self.settings.get("ui.janelas_maximizadas", True)))
        self.c_todas_max.setToolTip("Telas de trabalho (filme, impressões, PACS, preferências…) abrem centradas, com 80% do "
                                    "monitor. Perguntas, avisos e formulários pequenos ficam do tamanho deles.")
        f1.addRow(self.c_todas_max)
        self.c_confirmar = QCheckBox("Perguntar antes de fechar o programa")
        self.c_confirmar.setChecked(bool(self.settings.get("ui.confirmar_sair", True)))
        f1.addRow(self.c_confirmar)
        self.c_layout = QComboBox()
        for r, c in LAYOUTS:
            self.c_layout.addItem(f"{r} × {c}", [r, c])
        i = self.c_layout.findData(self.settings.get("viewer.default_layout", [1, 1]))
        self.c_layout.setCurrentIndex(max(0, i))
        f1.addRow("Layout inicial dos quadros:", self.c_layout)
        self.s_ask = QSpinBox(minimum=0, maximum=200, value=int(self.settings.get("viewer.ask_series_above", 0) or 0))
        self.s_ask.setSpecialValueText("nunca")
        self.s_ask.setSuffix(" séries")
        f1.addRow("Perguntar quais séries abrir com mais de:", self.s_ask)
        self.cb_auto = QCheckBox("Iniciar junto com o sistema (minimizado)")
        self.cb_auto.setChecked(bool(self.settings.get("viewer.autostart", False)))
        f1.addRow(self.cb_auto)
        self.cb_tray = QCheckBox("Ao fechar a janela, continuar na bandeja do sistema "
                                 "(nó DICOM e buscas agendadas continuam)")
        self.cb_tray.setChecked(bool(self.settings.get("viewer.close_to_tray", False)))
        f1.addRow(self.cb_tray)
        raiz.addWidget(g1)

        # --- o que aparece sobre a imagem
        g2 = QGroupBox("Texto e marcas sobre a imagem")
        f2 = QFormLayout(g2)
        # A letra acompanha o tamanho do quadro; isto é um multiplicador em cima disso, para quem
        # lê de longe (ou de perto) — o quadro dividido em quatro não vira texto.
        self.s_letra_med = QSpinBox(minimum=60, maximum=250, suffix=" %")
        self.s_letra_med.setValue(int(round(100 * float(
            self.settings.get("viewer.measure_font_scale", 1.0) or 1.0))))
        self.s_letra_med.setToolTip("Tamanho do texto das medidas, ROIs, setas e anotações "
                                    "desenhadas sobre a imagem.")
        f2.addRow("Letra das medidas e anotações:", self.s_letra_med)
        self.s_letra_ov = QSpinBox(minimum=60, maximum=250, suffix=" %")
        self.s_letra_ov.setValue(int(round(100 * float(
            self.settings.get("viewer.overlay_font_scale", 1.0) or 1.0))))
        self.s_letra_ov.setToolTip("Tamanho do texto dos cantos: paciente, série, janela, FOV.")
        f2.addRow("Letra das informações nos cantos:", self.s_letra_ov)
        self.cb_hot = QCheckBox("Áreas clicáveis no texto sobre a imagem")
        self.cb_hot.setChecked(bool(self.settings.get("viewer.overlay_hotspots", True)))
        f2.addRow(self.cb_hot)
        self.cb_dial = QCheckBox("Indicador de profundidade da tomossíntese no canto do quadro")
        self.cb_dial.setChecked(bool(self.settings.get("viewer.tomo_dial", True)))
        f2.addRow(self.cb_dial)
        self.cb_incerteza = QCheckBox("Mostrar a incerteza ao lado da medida (± pixel na régua, ± na área)")
        self.cb_incerteza.setChecked(bool(self.settings.get("viewer.incerteza_medidas", False)))
        self.cb_incerteza.setToolTip("O erro de pôr cada ponta num pixel. O aviso de cortes grossos e de "
                                     "medida menor que a espessura aparece sempre.")
        f2.addRow(self.cb_incerteza)
        raiz.addWidget(g2)

        # --- sincronização automática por modalidade (0.99.9)
        from ipe.ui.viewer import sync as SY
        g_sync = QGroupBox("Sincronização automática no mesmo estudo")
        f_sync = QVBoxLayout(g_sync)
        f_sync.addWidget(QLabel("<small>Marcado, as séries do mesmo plano do exame rolam juntas sozinhas. "
                                "O botão <b>Sincronizar</b> do visualizador e o item <b>Automática</b> do "
                                "menu dele mudam isto para a modalidade do quadro ativo. Os três planos do "
                                "MPR e os quadros da dinâmica andam juntos sempre.</small>"))
        hub = SY.SyncHub(None, None, self.settings)
        grade_sync = QGridLayout()
        self.c_sync_mod = {}
        for k, mod in enumerate(("MR", "CT", "PT", "NM", "MG", "US", "CR", "DX", "XA")):
            nome = SY.MODALIDADE_TXT.get(mod, mod)
            cb = QCheckBox(nome if f"({mod})" in nome else f"{nome} ({mod})")
            cb.setChecked(hub.auto_da_modalidade(mod))
            self.c_sync_mod[mod] = cb
            grade_sync.addWidget(cb, k // 3, k % 3)
        f_sync.addLayout(grade_sync)
        hub.deleteLater()
        raiz.addWidget(g_sync)

        # --- botões da barra
        g3 = QGroupBox("Botões na barra do visualizador")
        f3 = QVBoxLayout(g3)
        f3.addWidget(QLabel("<small>Desmarcado, o botão sai da barra e fica no menu <b>Mais</b> — "
                            "a função continua lá.</small>"))
        fora = self.settings.get("viewer.botoes_fora", None)
        fora = set(ViewerTab.FORA_POR_PADRAO) if fora is None else set(fora)
        self.c_botoes = {}
        for aid, nome in ViewerTab.NOME_DOS_OPCIONAIS.items():
            cb = QCheckBox(nome)
            cb.setChecked(aid not in fora)
            self.c_botoes[aid] = cb
            f3.addWidget(cb)
        self.cb_all_btn = QCheckBox("Mostrar também os botões que não servem à modalidade do exame")
        self.cb_all_btn.setChecked(bool(self.settings.get("viewer.all_buttons", False)))
        f3.addWidget(self.cb_all_btn)
        raiz.addWidget(g3)

        # --- importação
        g4 = QGroupBox("Importação")
        f4 = QVBoxLayout(g4)
        self.cb_copy = QCheckBox("Copiar os arquivos para o armazenamento do programa ao importar")
        self.cb_copy.setChecked(bool(self.settings.get("import.copy_to_storage", True)))
        f4.addWidget(self.cb_copy)
        f4.addWidget(QLabel("<small>Desmarcado, o programa só referencia os arquivos no local "
                            "original — e nunca os altera.</small>"))
        raiz.addWidget(g4)

        # --- idioma
        g5 = QGroupBox("Idioma")
        f5 = QFormLayout(g5)
        self.c_lang = QComboBox()
        for code, name in i18n.available():
            self.c_lang.addItem(f"{name} ({code})", code)
        cur = self.settings.get("language", "") or i18n.current()
        if self.c_lang.findData(cur) < 0:
            self.c_lang.addItem(f"{i18n.language_name(cur)} ({cur})", cur)
        self.c_lang.setCurrentIndex(max(0, self.c_lang.findData(cur)))
        b_tr = QPushButton("Editar traduções / novo idioma…")
        b_tr.clicked.connect(self._open_translations)
        row = QHBoxLayout()
        row.addWidget(self.c_lang, 1)
        row.addWidget(b_tr)
        f5.addRow("Idioma do programa:", row)
        f5.addRow(QLabel("<small>A troca aparece ao reabrir o programa; o original é o "
                         "português.</small>"))
        raiz.addWidget(g5)
        raiz.addStretch(1)
        return _rolavel(w)

    def _open_translations(self) -> None:
        from ipe.core import i18n
        from ipe.ui.translate_dialog import TranslateDialog
        code = self.c_lang.currentData() or "en"
        TranslateDialog(code if code != i18n.BASE_LANG else "en", self).exec()

    def _monitors_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(
            "Escolha o papel de cada monitor. Estudos abertos vão para o monitor <b>Viewer</b>; "
            "exames anteriores, para o de <b>Comparação</b>, já ligados ao exame atual. "
            "O layout vale para os estudos abertos naquele monitor."))
        lay.itemAt(0).widget().setWordWrap(True)
        from ipe.ui.monitors import telas_ordenadas
        screens = telas_ordenadas(self.settings)
        self._telas = screens
        conf = self.settings.get("monitors", {}) or {}
        self.t_mon = QTableWidget(len(screens), 4)
        self.t_mon.setHorizontalHeaderLabels(["Ordem", "Monitor", "Papel", "Layout"])
        self.t_mon.verticalHeader().setVisible(False)
        self.t_mon.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        colunas_ajustaveis(self.t_mon)
        self.mon_rows: list[tuple[str, QComboBox, QComboBox, QSpinBox]] = []
        for row, sc in enumerate(screens):
            key = screen_key(sc)
            c = conf.get(key, {}) or {}
            ordem = QSpinBox(minimum=1, maximum=max(1, len(screens)))
            ordem.setValue(row + 1)
            ordem.setToolTip("Quem é o Monitor 1, 2, 3… para o programa. É este número que a etapa "
                             "de mamografia usa (“com 2 telas, mostrar no Monitor 2”).")
            self.t_mon.setCellWidget(row, 0, ordem)
            it = QTableWidgetItem(screen_label(sc, row + 1))
            it.setFlags(Qt.ItemIsEnabled)
            self.t_mon.setItem(row, 1, it)
            role = _combo(list(ROLES.items()), c.get("role", ""))
            layc = QComboBox()
            layc.addItem("Padrão", None)
            for r, cc in LAYOUTS:
                layc.addItem(f"{r} × {cc}", [r, cc])
            i = layc.findData(c.get("layout"))
            layc.setCurrentIndex(max(0, i))
            self.t_mon.setCellWidget(row, 2, role)
            self.t_mon.setCellWidget(row, 3, layc)
            self.mon_rows.append((key, role, layc, ordem))
        self.t_mon.resizeColumnToContents(0)
        self.t_mon.resizeColumnToContents(2)
        lay.addWidget(self.t_mon)
        ord_row = QHBoxLayout()
        b_pos = QPushButton("Ordenar pela posição na mesa (esquerda → direita)")
        b_pos.setToolTip("Preenche a ordem pela posição física das telas, como o sistema as colocou "
                         "lado a lado. Serve como ponto de partida; depois é só ajustar.")
        b_pos.clicked.connect(self._ordenar_pela_posicao)
        ord_row.addWidget(b_pos)
        ord_row.addStretch(1)
        lay.addLayout(ord_row)
        from ipe.ui.viewer.viewer_tab import ViewerTab
        self.c_tira = _combo(list(ViewerTab.TIRA_MODOS.items()),
                             self.settings.get("viewer.tira_repartida", "mamografia"))
        self.c_tira.setToolTip("Com o exame repartido entre monitores, a tira de miniaturas da tela "
                               "de dentro fica bem no meio das duas imagens. Aqui ela some das telas "
                               "2, 3 e 4 e fica só na primeira.")
        linha_tira = QHBoxLayout()
        linha_tira.addWidget(QLabel("Tira de séries só no primeiro monitor:"))
        linha_tira.addWidget(self.c_tira, 1)
        lay.addLayout(linha_tira)
        self.ck_sync_mon = QCheckBox("Monitores de viewer andam juntos (rolagem, janela e zoom)")
        self.ck_sync_mon.setChecked(bool(self.settings.get("monitors.sync_group", True)))
        self.ck_sync_mon.setToolTip("Clicar num ponto numa tela leva as outras ao mesmo lugar. "
                                    "Desmarque para deixar cada monitor por conta própria.")
        lay.addWidget(self.ck_sync_mon)
        btn = QPushButton("Identificar monitores")
        btn.setToolTip("Mostra o número de cada tela, como o programa a chama — a mesma numeração "
                       "da coluna Ordem e das etapas de mamografia.")
        btn.clicked.connect(lambda: identify_screens(settings=self.settings))
        lay.addWidget(btn)
        for texto in (
            "Marque quantos monitores quiser como Viewer: eles funcionam como uma estação só. "
            "O exame abre em todos, o que você manda pelo menu vale para todos, rolagem, janela "
            "e zoom andam juntos, e fechar num deles fecha nos outros.",
            "Em mamografia há arranjo pronto para 1, 2, 3 e 4 monitores — com dois, as CC num e "
            "as MLO no outro —, escolhido pelo número de monitores marcados. Nas outras "
            "modalidades as séries são repartidas na ordem.",
            "A janela do banco de dados sai sozinha dos monitores de Viewer e dos marcados como "
            "Não usar. Monitores de diagnóstico em retrato: use layout 1 × 2 ou 2 × 1. No Linux, "
            "rode em X11 (em Wayland o sistema não deixa o programa escolher o monitor).",
        ):
            note = QLabel(texto)
            note.setWordWrap(True)
            lay.addWidget(note)
        return w

    def _performance_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        ram = total_ram_mb()
        f.addRow(QLabel(f"Memória do computador: <b>{ram / 1024:.1f} GB</b>"))
        self.s_cache = QSpinBox(minimum=0, maximum=max(1024, ram), singleStep=256, suffix=" MB")
        self.s_cache.setSpecialValueText(f"Automático ({auto_cache_mb()} MB)")
        self.s_cache.setValue(int(self.settings.get("performance.cache_mb", 0) or 0))
        self.s_vol = QSpinBox(minimum=0, maximum=max(1024, ram), singleStep=256, suffix=" MB")
        self.s_vol.setSpecialValueText(f"Automático ({auto_volume_mb()} MB)")
        self.s_vol.setValue(int(self.settings.get("performance.max_volume_mb", 0) or 0))
        f.addRow("Cache de imagens (teto):", self.s_cache)
        f.addRow(QLabel("   Imagens já lidas ficam na memória para rolar rápido; "
                        "as menos usadas saem primeiro."))
        f.addRow("Volume de MPR (máximo sem aviso):", self.s_vol)
        f.addRow(QLabel("   Acima disso o programa pergunta antes de montar o volume."))
        # Existiam no settings.json e em lugar nenhum da tela: quem não edita JSON nunca soube
        # que dava para mexer. Opção sem porta visível é opção que não existe.
        self.s_3d = QSpinBox(minimum=96, maximum=768, singleStep=32, suffix=" voxels")
        self.s_3d.setValue(int(self.settings.get("viewer.render3d_size", 256) or 256))
        self.s_3d.setToolTip("Lado máximo do volume usado no 3D. Maior = mais detalhe e mais "
                             "lento; o 3D roda na CPU.")
        f.addRow("Detalhe do 3D (lado do volume):", self.s_3d)
        self.s_lupa = QSpinBox(minimum=100, maximum=600, singleStep=20, suffix=" px")
        self.s_lupa.setValue(int(self.settings.get("viewer.loupe_size", 240) or 240))
        self.s_lupa.setToolTip("Diâmetro da lupa da mamografia (o botão Lupa na barra do exame).")
        f.addRow("Tamanho da lupa:", self.s_lupa)
        f.addRow(QLabel("A barra de status mostra a RAM usada pelo programa, o cache e os volumes."))
        f.addRow(QLabel("<i>Controles de memória da placa de vídeo entram com o 3D (VTK).</i>"))
        return w

    # ------------------------------------------------------------ salvar
    def _save(self) -> None:
        # conflitos de atalho
        self._keys_sincronizar()
        seen: dict[str, str] = {}
        shortcuts = {}
        for aid, _nome, _default, _grupo in ACTIONS:
            key = self.key_values.get(aid, "")
            shortcuts[aid] = key
            if key:
                if key in seen:
                    QMessageBox.warning(self, "Atalho repetido",
                                        f"O atalho {key} está em duas ações. Troque um deles.")
                    return
                seen[key] = aid
        lidos = self._ler_presets_da_tabela()
        if lidos is None:
            return
        self._presets_listas[self._preset_lista_atual] = lidos
        presets = self._presets_listas.get("", {})
        teclas = self.teclas_emprestadas()
        if len(set(teclas.values())) != len(teclas):
            QMessageBox.warning(self, "Tecla repetida",
                                "A mesma tecla está emprestando o botão esquerdo para duas "
                                "ferramentas. Escolha teclas diferentes.")
            return
        s = self.settings
        s.set("shortcuts", shortcuts)
        s.set("viewer.teclas_emprestadas", teclas)
        s.set("viewer.wl_presets", presets)
        s.set("viewer.wl_presets_mod", {k: v for k, v in self._presets_listas.items() if k and v})
        s.set("viewer.mouse", {
            "left": self.c_left.currentData(), "right": self.c_right.currentData(),
            "right_click": self.c_right_click.currentData(), "middle": self.c_middle.currentData(),
            "middle_click": self.c_middle_click.currentData(), "wheel": self.c_wheel.currentData(),
            "ctrl_wheel": self.c_ctrl_wheel.currentData(), "shift_wheel": self.c_shift_wheel.currentData(),
            "back": self.c_back.currentData(), "forward": self.c_forward.currentData(),
        })
        ordens = [o.value() for _k, _r, _l, o in self.mon_rows]
        if len(set(ordens)) != len(ordens):
            QMessageBox.warning(self, "Ordem repetida",
                                "Dois monitores estão com o mesmo número de ordem. "
                                "Cada tela precisa do seu.")
            return
        monitors = dict(s.get("monitors", {}) or {})
        for key, role, layc, ordem in self.mon_rows:
            entry = {k: v for k, v in (("role", role.currentData()), ("layout", layc.currentData())) if v}
            entry["ordem"] = ordem.value()
            monitors[key] = entry
        s.set("monitors", monitors)
        s.set("monitors.sync_group", self.ck_sync_mon.isChecked())
        s.set("viewer.tira_repartida", self.c_tira.currentData())
        s.set("hanging_protocols", self.hanging_protocols())
        from ipe.imaging import dinamicas as D
        D.salvar(s, self.regras_dinamicas())
        self.mg_editor.save()
        self.cad_ia.save()
        self.din_mama.save()
        self.anot_editor.save()
        auto_mod = dict(s.get("viewer.sync_auto_mod", {}) or {})
        auto_mod.update({m: cb.isChecked() for m, cb in self.c_sync_mod.items()})
        s.set("viewer.sync_auto_mod", auto_mod)
        s.set("performance.cache_mb", self.s_cache.value())
        s.set("performance.max_volume_mb", self.s_vol.value())
        s.set("viewer.render3d_size", self.s_3d.value())
        s.set("viewer.loupe_size", self.s_lupa.value())
        s.set("viewer.click_max_ms", self.s_click_ms.value())
        s.set("viewer.click_max_px", self.s_click_px.value())
        s.set("viewer.invert_wheel", self.cb_invert_wheel.isChecked())
        s.set("import.copy_to_storage", self.cb_copy.isChecked())
        s.set("viewer.overlay_hotspots", self.cb_hot.isChecked())
        s.set("viewer.measure_font_scale", round(self.s_letra_med.value() / 100.0, 2))
        s.set("viewer.incerteza_medidas", self.cb_incerteza.isChecked())
        s.set("viewer.overlay_font_scale", round(self.s_letra_ov.value() / 100.0, 2))
        s.set("ui.start_maximized", self.c_maximizada.isChecked())
        s.set("ui.janelas_maximizadas", self.c_todas_max.isChecked())
        s.set("ui.confirmar_sair", self.c_confirmar.isChecked())
        s.set("viewer.botoes_fora", sorted(a for a, cb in self.c_botoes.items() if not cb.isChecked()))
        s.set("viewer.tomo_dial", self.cb_dial.isChecked())
        s.set("viewer.all_buttons", self.cb_all_btn.isChecked())
        from ipe import modules as MOD
        MOD.definir(s, {m: cb.isChecked() for m, cb in self.c_modulos.items()})
        s.set("viewer.default_layout", self.c_layout.currentData())
        s.set("viewer.ask_series_above", self.s_ask.value())
        s.set("viewer.close_to_tray", self.cb_tray.isChecked())
        lang = self.c_lang.currentData()
        if lang and lang != (s.get("language", "") or ""):
            from ipe.core import i18n
            s.set("language", lang)
            if lang != i18n.current():      # só avisa quando o idioma muda de verdade
                QMessageBox.information(self, "Idioma",
                                        "O idioma muda quando você abrir o programa de novo.")
        if self.cb_auto.isChecked() != bool(s.get("viewer.autostart", False)):
            try:
                from ipe.core.autostart import set_autostart
                set_autostart(self.cb_auto.isChecked())
                s.set("viewer.autostart", self.cb_auto.isChecked())
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Iniciar com o sistema", f"Não foi possível configurar: {e}")
        s.save()
        self.accept()

    def _restore_defaults(self) -> None:
        if QMessageBox.question(self, "Restaurar padrões",
                                "Voltar mouse, atalhos e presets aos valores de fábrica?") != QMessageBox.Yes:
            return
        self.settings.reset_defaults()
        self.settings.save()
        self.accept()
