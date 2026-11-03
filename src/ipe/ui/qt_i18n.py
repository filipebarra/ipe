"""Tradução automática dos textos do Qt.

Em vez de marcar milhares de textos no código, o programa passa a traduzir no momento em que o
texto chega ao Qt: envolve os métodos que recebem texto (setText, setToolTip, addItem, addTab…) e
troca as classes cujo texto vem no construtor (QLabel("Abrir"), QPushButton("Salvar")…).

Chame install() UMA vez, antes de importar as telas (ui.main_window etc.).
"""

from __future__ import annotations

import logging

from ipe.core.i18n import tr

log = logging.getLogger(__name__)
_installed = False

# (classe, métodos cujos argumentos de texto são traduzidos)
_TEXT_METHODS = {
    "QWidget": ("setWindowTitle", "setToolTip", "setStatusTip", "setWhatsThis", "setAccessibleName"),
    "QLabel": ("setText",),
    "QAbstractButton": ("setText",),
    "QGroupBox": ("setTitle",),
    "QLineEdit": ("setPlaceholderText",),
    "QTextEdit": ("setPlaceholderText",),
    "QPlainTextEdit": ("setPlaceholderText",),
    "QComboBox": ("setPlaceholderText",),
    "QAbstractSpinBox": ("setSpecialValueText",),
    "QSpinBox": ("setSuffix", "setPrefix"),
    "QDoubleSpinBox": ("setSuffix", "setPrefix"),
    "QProgressDialog": ("setLabelText", "setCancelButtonText"),
    "QMessageBox": ("setText", "setInformativeText", "setDetailedText"),
    "QTabWidget": ("setTabText", "setTabToolTip"),
    "QTreeWidgetItem": ("setText", "setToolTip"),
    "QTableWidgetItem": ("setText", "setToolTip"),
    "QListWidgetItem": ("setText", "setToolTip"),
    "QHeaderView": (),
    "QToolButton": ("setText",),
    "QMenu": ("setTitle",),
    "QDockWidget": ("setWindowTitle",),
    "QFileDialog": ("setLabelText",),
    # 0.99.35: a barra de status e os avisos da bandeja são desenhados pelo Qt (C++), sem passar por aqui
    "QStatusBar": ("showMessage",),
    "QSystemTrayIcon": ("setToolTip",),
}
# métodos com texto em posições específicas: classe -> {método: (índices dos argumentos de texto)}
_TEXT_ARGS = {
    # QComboBox: addItem / insertItem / setItemText / addItems ficam com _wrap_combo
    "QTabWidget": {"addTab": (1,), "insertTab": (2,)},
    "QMenu": {"addAction": (0, 1), "addMenu": (0, 1), "addSection": (0, 1)},
    "QMenuBar": {"addMenu": (0, 1), "addAction": (0,)},
    "QToolBar": {"addAction": (0, 1), "addWidget": ()},
    "QListWidget": {"addItem": (0,), "insertItem": (1,), "addItems": ()},
    "QTreeWidget": {"setHeaderLabels": (), "setHeaderLabel": (0,)},
    "QTableWidget": {"setHorizontalHeaderLabels": (), "setVerticalHeaderLabels": ()},
    "QMessageBox": {"addButton": (0,), "setButtonText": (1,)},
    "QInputDialog": {"setLabelText": (0,), "setOkButtonText": (0,), "setCancelButtonText": (0,)},
    "QAction": {"setText": (0,), "setToolTip": (0,), "setIconText": (0,), "setStatusTip": (0,),
                "setWhatsThis": (0,)},
    "QSystemTrayIcon": {"showMessage": (0, 1)},
}
# métodos que recebem uma lista de textos
_TEXT_LISTS = {"QTreeWidget": ("setHeaderLabels",), "QTableWidget": ("setHorizontalHeaderLabels",
               "setVerticalHeaderLabels"), "QListWidget": ("addItems",)}
# funções estáticas (diálogos prontos): índices dos argumentos de texto
_STATICS = {
    "QMessageBox": {"information": (1, 2), "warning": (1, 2), "critical": (1, 2), "question": (1, 2),
                    "about": (1, 2)},
    "QInputDialog": {"getText": (1, 2), "getInt": (1, 2), "getDouble": (1, 2), "getItem": (1, 2)},
    "QToolTip": {"showText": (1,)},
    "QFileDialog": {"getSaveFileName": (1, 3, 4), "getOpenFileName": (1, 3, 4),
                    "getOpenFileNames": (1, 3, 4), "getExistingDirectory": (1,)},
}
# classes cujo texto vem no construtor: posições dos argumentos de texto
_CTOR_ARGS = {
    "QLabel": (0,), "QPushButton": (0,), "QCheckBox": (0,), "QRadioButton": (0,), "QGroupBox": (0,),
    "QToolButton": (), "QCommandLinkButton": (0, 1), "QTreeWidgetItem": (), "QTableWidgetItem": (0,),
    "QListWidgetItem": (0,), "QProgressDialog": (0, 1), "QMessageBox": (1, 2), "QAction": (0, 1),
    "QMenu": (0,), "QToolBar": (0,), "QDockWidget": (0,), "QWizardPage": (),
}
_CTOR_KWARGS = ("text", "title", "placeholderText", "suffix", "prefix", "toolTip", "windowTitle",
                "labelText", "specialValueText")
_CTOR_LIST_ARG = {"QTreeWidgetItem"}     # QTreeWidgetItem(["a", "b"])


def _wrap_method(cls, name: str, idx=(0,), as_list: bool = False) -> None:
    orig = getattr(cls, name, None)
    if orig is None or getattr(orig, "_i18n", False):
        return

    def wrapper(self, *args, **kwargs):
        if args:
            args = list(args)
            if as_list and args and isinstance(args[0], (list, tuple)):
                args[0] = [tr(x) if isinstance(x, str) else x for x in args[0]]
            else:
                for i in idx:
                    if i < len(args) and isinstance(args[i], str):
                        args[i] = tr(args[i])
        return orig(self, *args, **kwargs)
    wrapper._i18n = True
    try:
        setattr(cls, name, wrapper)
    except (TypeError, AttributeError) as e:  # noqa: BLE001
        log.debug("não deu para traduzir %s.%s: %s", cls.__name__, name, e)


def _wrap_static(cls, name: str, idx) -> None:
    orig = getattr(cls, name, None)
    if orig is None or getattr(orig, "_i18n", False):
        return

    def wrapper(*args, **kwargs):
        args = list(args)
        for i in idx:
            if i < len(args) and isinstance(args[i], str):
                args[i] = tr(args[i])
        return orig(*args, **kwargs)
    wrapper._i18n = True
    try:
        setattr(cls, name, staticmethod(wrapper))
    except (TypeError, AttributeError):  # noqa: BLE001
        pass


def _make_subclass(cls, idx, as_list: bool):
    class Translated(cls):                    # noqa: D401 - só traduz o texto do construtor
        def __init__(self, *args, **kwargs):
            if args:
                args = list(args)
                if as_list and isinstance(args[0], (list, tuple)):
                    args[0] = [tr(x) if isinstance(x, str) else x for x in args[0]]
                for i in idx:
                    if i < len(args) and isinstance(args[i], str):
                        args[i] = tr(args[i])
            for k in _CTOR_KWARGS:
                if isinstance(kwargs.get(k), str):
                    kwargs[k] = tr(kwargs[k])
            super().__init__(*args, **kwargs)
    Translated.__name__ = cls.__name__
    Translated.__qualname__ = cls.__qualname__
    Translated._i18n_base = cls
    return Translated


def _wrap_paint_text(QtGui) -> None:
    """QPainter.drawText: as telas desenhadas à mão (overlay do viewer, filme, gráficos)."""
    cls = QtGui.QPainter
    orig = getattr(cls, "drawText", None)
    if orig is None or getattr(orig, "_i18n", False):
        return

    def wrapper(self, *args, **kwargs):
        if args:
            args = list(args)
            for i, a in enumerate(args):
                if isinstance(a, str):
                    args[i] = tr(a)
                    break                     # só o texto; o resto são posições/flags
        return orig(self, *args, **kwargs)
    wrapper._i18n = True
    try:
        cls.drawText = wrapper
    except (TypeError, AttributeError) as e:  # noqa: BLE001
        log.debug("não deu para traduzir QPainter.drawText: %s", e)


#: papel do item da lista suspensa que guarda o texto original (em português)
ORIG_ROLE = 0x0100 + 0x1D1          # Qt.UserRole + 465: longe dos papéis que o programa usa


def _wrap_combo(QtWidgets) -> None:
    """0.99.34, relato dele: *"quando mudei o idioma de PT para ENG o meu banco de dados estava vazio"*.
    O filtro de modalidade tinha o item "Todas"; traduzido, virava "All", o código comparava com "Todas"
    e buscava a modalidade "All" — nenhum exame. O mesmo valia para qualquer lista suspensa cujo texto o
    código lê (filtros, nomes de layout, listas inteligentes…).

    Agora a lista mostra o texto traduzido, mas guarda o original no item, e o código lê o original:
    currentText(), itemText() e findText() / setCurrentText() falam português, como no programa em
    português. As listas editáveis (texto livre, que vai para o laudo) continuam devolvendo o que está
    escrito na tela."""
    cls = QtWidgets.QComboBox
    if getattr(cls.currentText, "_i18n", False):
        return
    o_add, o_ins, o_set = cls.addItem, cls.insertItem, cls.setItemText
    o_adds, o_inss = cls.addItems, cls.insertItems
    o_cur, o_item, o_find, o_setcur = cls.currentText, cls.itemText, cls.findText, cls.setCurrentText

    def _marcar(self, i, texto):
        if isinstance(texto, str) and 0 <= i < self.count():
            self.setItemData(i, texto, ORIG_ROLE)

    def _texto_de(args, pos):
        return args[pos] if len(args) > pos and isinstance(args[pos], str) else None

    def addItem(self, *args, **kwargs):  # noqa: N802
        args = list(args)
        pos = 0 if args and isinstance(args[0], str) else 1      # addItem(icone, texto, dado)
        orig = _texto_de(args, pos)
        if orig is not None:
            args[pos] = tr(orig)
        r = o_add(self, *args, **kwargs)
        _marcar(self, self.count() - 1, orig)
        return r

    def insertItem(self, index, *args, **kwargs):  # noqa: N802
        args = list(args)
        pos = 0 if args and isinstance(args[0], str) else 1
        orig = _texto_de(args, pos)
        if orig is not None:
            args[pos] = tr(orig)
        n = self.count()
        r = o_ins(self, index, *args, **kwargs)
        _marcar(self, index if 0 <= index <= n else n, orig)
        return r

    def addItems(self, textos):  # noqa: N802
        textos = list(textos)
        n = self.count()
        r = o_adds(self, [tr(t) if isinstance(t, str) else t for t in textos])
        for k, t in enumerate(textos):
            _marcar(self, n + k, t)
        return r

    def insertItems(self, index, textos):  # noqa: N802
        textos = list(textos)
        n = self.count()
        index = index if 0 <= index <= n else n
        r = o_inss(self, index, [tr(t) if isinstance(t, str) else t for t in textos])
        for k, t in enumerate(textos):
            _marcar(self, index + k, t)
        return r

    def setItemText(self, i, texto):  # noqa: N802
        r = o_set(self, i, tr(texto) if isinstance(texto, str) else texto)
        _marcar(self, i, texto)
        return r

    def _orig(self, i):
        v = self.itemData(i, ORIG_ROLE) if 0 <= i < self.count() else None
        return v if isinstance(v, str) else None

    def itemText(self, i):  # noqa: N802
        return _orig(self, i) or o_item(self, i)

    def currentText(self):  # noqa: N802
        if not self.isEditable():
            v = _orig(self, self.currentIndex())
            if v is not None:
                return v
        return o_cur(self)

    def findText(self, texto, *args, **kwargs):  # noqa: N802
        if isinstance(texto, str):
            for i in range(self.count()):
                if _orig(self, i) == texto:
                    return i
        return o_find(self, texto, *args, **kwargs)

    def setCurrentText(self, texto):  # noqa: N802
        if isinstance(texto, str):
            i = findText(self, texto)
            if i >= 0 and (not self.isEditable() or _orig(self, i) == texto):
                self.setCurrentIndex(i)
                return None
        return o_setcur(self, texto)

    for nome, fn in (("addItem", addItem), ("insertItem", insertItem), ("addItems", addItems),
                     ("insertItems", insertItems), ("setItemText", setItemText), ("itemText", itemText),
                     ("currentText", currentText), ("findText", findText), ("setCurrentText", setCurrentText)):
        fn._i18n = True
        try:
            setattr(cls, nome, fn)
        except (TypeError, AttributeError) as e:  # noqa: BLE001
            log.debug("não deu para traduzir QComboBox.%s: %s", nome, e)


def mesmo(texto_da_tela: str, original: str) -> bool:
    """O texto de uma aba, título ou botão é este (em português)? Vale com a tela traduzida."""
    return texto_da_tela == original or texto_da_tela == tr(original)


def install() -> bool:
    """Liga a tradução automática. Deve ser chamada antes de importar as telas."""
    global _installed
    if _installed:
        return False
    from PySide6 import QtGui, QtWidgets
    mods = (QtWidgets, QtGui)

    def find(name):
        for m in mods:
            c = getattr(m, name, None)
            if c is not None:
                return m, c
        return None, None

    for name, methods in _TEXT_METHODS.items():
        _m, cls = find(name)
        if cls is None:
            continue
        for meth in methods:
            _wrap_method(cls, meth)
    for name, methods in _TEXT_ARGS.items():
        _m, cls = find(name)
        if cls is None:
            continue
        for meth, idx in methods.items():
            if idx:
                _wrap_method(cls, meth, idx)
    for name, methods in _TEXT_LISTS.items():
        _m, cls = find(name)
        if cls is None:
            continue
        for meth in methods:
            _wrap_method(cls, meth, (0,), as_list=True)
    for name, methods in _STATICS.items():
        _m, cls = find(name)
        if cls is None:
            continue
        for meth, idx in methods.items():
            _wrap_static(cls, meth, idx)
    _wrap_paint_text(QtGui)
    _wrap_combo(QtWidgets)
    for name, idx in _CTOR_ARGS.items():
        m, cls = find(name)
        if cls is None or getattr(cls, "_i18n_base", None) is not None:
            continue
        setattr(m, name, _make_subclass(cls, idx, name in _CTOR_LIST_ARG))
    _installed = True
    return True
