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
}
# métodos com texto em posições específicas: classe -> {método: (índices dos argumentos de texto)}
_TEXT_ARGS = {
    "QComboBox": {"addItem": (0,), "insertItem": (1,), "setItemText": (1,), "setItemData": ()},
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
}
# métodos que recebem uma lista de textos
_TEXT_LISTS = {"QTreeWidget": ("setHeaderLabels",), "QTableWidget": ("setHorizontalHeaderLabels",
               "setVerticalHeaderLabels"), "QListWidget": ("addItems",), "QComboBox": ("addItems",)}
# funções estáticas (diálogos prontos): índices dos argumentos de texto
_STATICS = {
    "QMessageBox": {"information": (1, 2), "warning": (1, 2), "critical": (1, 2), "question": (1, 2),
                    "about": (1, 2)},
    "QInputDialog": {"getText": (1, 2), "getInt": (1, 2), "getDouble": (1, 2), "getItem": (1, 2)},
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
    for name, idx in _CTOR_ARGS.items():
        m, cls = find(name)
        if cls is None or getattr(cls, "_i18n_base", None) is not None:
            continue
        setattr(m, name, _make_subclass(cls, idx, name in _CTOR_LIST_ARG))
    _installed = True
    return True
