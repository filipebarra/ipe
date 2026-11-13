"""Menu Configurações (0.99.12): um submenu por assunto, uma janela por item.

Pedido dele: *"criar um menu de configurações com submenus [...] um sub menu para cada
configuração, evitando deixar poluído o que hoje temos como configurações"* — e, perguntado, **uma
janela para cada item**.

Até a 0.99.11 as configurações estavam em quatro lugares: a janela de Preferências com 14 abas, e
itens soltos nos menus Exibir, Rede, Impressão e Usuário. Agora os menus de ação ficam só com
ações (Consulta PACS, Gestão DICOM, Lista de impressões…) e tudo o que se configura mora aqui.

Cada item é `(texto, alvo, permissão)`:
- `"p:<id>"` abre uma página das Preferências sozinha (`preferences.PAGINAS`);
- `"f:<método>"` chama um método da janela principal;
- um `callable(win)` faz o que precisar.

O mesmo catálogo monta o menu da barra de menus e o do botão Configurações da tela inicial.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

#: (submenu, [(texto, alvo, permissão)]); permissão "" = qualquer um, "configure", "users"
CATALOGO: list[tuple[str, list[tuple[str, object, str]]]] = [
    ("Visualizador", [
        ("Barra de ferramentas e aplicações…", "f:abrir_config_barra", ""),
        ("Botões extras na barra…", "p:botoes", ""),
        ("Mouse…", "p:mouse", ""),
        ("Atalhos de teclado…", "p:atalhos", ""),
        ("Presets de janela…", "p:presets", ""),
        ("Anotações…", "p:anotacoes", ""),
        ("Texto e marcas sobre a imagem…", "p:aparencia", ""),
        ("Sincronização automática…", "p:sincronia", ""),
        ("Fechar o exame sozinho…", "f:abrir_fechar_sozinho", ""),
        ("Estado da análise ao abrir…", "f:abrir_estado_ao_abrir", ""),
    ]),
    ("Protocolos de exame", [
        ("Protocolos de exibição…", "p:protocolos", ""),
        ("Mamografia…", "p:mamografia", ""),
        ("Dinâmica da mama…", "p:dinamica_mama", ""),
        ("Dinâmicos (juntar e separar séries)…", "p:dinamicos", ""),
        ("Regiões do corpo…", "f:abrir_config_regioes", ""),
    ]),
    ("CAD/IA", [
        ("Análises automáticas (CAD/IA)…", "p:cad_ia", ""),
        ("Segmentação abdominal…", lambda w: w.abrir_cad_ia("Segmentação abdominal"), ""),
        ("Níveis da coluna…", lambda w: w.abrir_cad_ia("Níveis da coluna"), ""),
        ("Implante de silicone (mamografia)…", lambda w: w.abrir_cad_ia("Implante de silicone"), ""),
        ("Cefalometria do cavum…", lambda w: w.abrir_cad_ia("Cefalometria do cavum"), ""),
        ("Índices do crânio (SynthSeg)…", lambda w: w.abrir_cad_ia("Índices do crânio"), ""),
        ("Níveis linfonodais…", lambda w: w.abrir_cad_ia("Níveis linfonodais"), ""),
        ("Instalar a segmentação de órgãos (TotalSegmentator)…", "f:instalar_segmentacao", "configure"),
        ("Instalar os modelos extras (MedSAM2, autoPET, BraTS, FLAMeS, medula)…", "f:instalar_modelos_extras", "configure"),
    ]),
    ("Laudos", [
        ("Prioridade, subespecialidade e prazos (SLA)…", "f:abrir_config_sla", "users"),
        ("Busca ativa (prazos por BI-RADS)…", "f:abrir_config_busca_ativa", "users"),
        ("Fim da leitura (enviar ao PACS ao assinar)…", "f:abrir_config_fim_leitura", "configure"),
        ("IA no texto do laudo…", "f:abrir_config_laudo_ia", ""),
    ]),
    ("Monitores", [
        ("Papel, layout e ordem dos monitores…", "p:monitores", "configure"),
        ("Calibração GSDF do monitor…", "f:open_gsdf", "configure"),
    ]),
    ("Rede", [
        ("Nós DICOM (PACS, estações)…", "f:open_network_settings", "query"),
        ("Automação (buscas agendadas, anteriores, roteamento, limpeza)…", "f:open_automation", "configure"),
        ("Servidor central (intranet)…", "f:open_central_settings", "configure"),
        ("Atualizações pelo servidor central…", "f:abrir_atualizacoes", "users"),
        ("Registrar link ipe:// neste computador", "f:_register_url", "configure"),
    ]),
    ("Impressão", [
        ("Acrescentar impressora DICOM…", "f:acrescentar_impressora_dicom", ""),
        ("Impressoras DICOM…", lambda w: w.acrescentar_impressora_dicom(nova=False), ""),
        ("Servidores, destinos, regras e modelos de folha…", "f:open_print_settings", "configure"),
    ]),
    ("Banco de dados", [
        ("Importação…", "p:importacao", ""),
        ("Mudar a pasta do banco deste computador…", "f:move_default_database", "configure"),
        ("Servidor de banco de dados (PostgreSQL)…", "f:abrir_banco_postgres", "configure"),
        ("Abrir a pasta de dados", "f:_open_data_folder", ""),
    ]),
    ("Usuários", [
        ("Modo de uso (só eu, várias pessoas, servidor)…", "f:abrir_modo_de_uso", "users"),
        ("Usuários e permissões…", lambda w: w.open_users(tab=0), "users"),
        ("Configurações pessoais e compartilhadas…", "f:abrir_config_niveis", ""),
        ("Perfis por grupo e computador…", "f:abrir_perfis", "users"),
    ]),
    ("Sistema", [
        ("Ao abrir o programa…", "p:abertura", ""),
        ("Desempenho…", "p:desempenho", "configure"),
        ("Módulos…", "p:modulos", ""),
        ("Idioma…", "p:idioma", ""),
        ("Exportar as configurações…", "f:exportar_configuracoes", ""),
        ("Importar configurações…", "f:importar_configuracoes", ""),
    ]),
]

#: item que some quando o módulo dele está desligado (Configurações ▸ Sistema ▸ Módulos)
MODULO_DO_ITEM = {"Servidores, destinos, regras e modelos de folha…": "impressao"}


def executar(win, alvo) -> None:
    if callable(alvo):
        alvo(win)
    elif isinstance(alvo, str) and alvo.startswith("p:"):
        win.open_config(alvo[2:])
    elif isinstance(alvo, str) and alvo.startswith("f:"):
        getattr(win, alvo[2:])()


def _pode(permissao: str) -> bool:
    if not permissao:
        return True
    from ipe.auth import session as S
    return bool(S.can(permissao))


# ------------------------------------------------------------------ 0.99.73: a janela de um grupo
def itens_do_grupo(win, nome: str) -> list[tuple[str, object, bool]]:
    """(texto, alvo, pode) dos itens do grupo que aparecem no menu (módulo desligado fica de fora)."""
    from ipe import modules as MOD
    desligados = MOD.desligados(win.settings)
    for n, itens in CATALOGO:
        if n == nome:
            return [(t, a, _pode(p)) for t, a, p in itens if MODULO_DO_ITEM.get(t) not in desligados]
    return []


class GrupoDialog(QDialog):
    """Clique no nome do grupo (Visualizador, CAD/IA…): uma janela com as etapas do grupo à esquerda. As páginas
    de preferências aparecem ali mesmo e são gravadas juntas no OK; as que têm janela própria abrem pelo botão."""

    def __init__(self, win, nome: str):
        super().__init__(win)
        self.win, self.nome = win, nome
        self.setWindowTitle(f"Configurações — {nome}")
        self.resize(980, 640)
        self.itens = itens_do_grupo(win, nome)
        pids = [a[2:] for _t, a, ok in self.itens if isinstance(a, str) and a.startswith("p:") and ok]
        self.lista = QListWidget()
        self.lista.setMaximumWidth(300)
        for texto, _alvo, ok in self.itens:
            it = QListWidgetItem(texto.rstrip("…"))
            if not ok:
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
                it.setToolTip("Você não tem permissão para esta configuração.")
            self.lista.addItem(it)
        self.pilha = QStackedWidget()
        self.prefs = None
        if pids:
            from ipe.ui.preferences import PreferencesDialog
            self.prefs = PreferencesDialog(win.settings, win, paginas=pids)
            self.prefs.setWindowFlags(Qt.Widget)
            self.prefs.bb.hide()
            self.pilha.addWidget(self.prefs)
        self.cartao = QWidget()
        c = QVBoxLayout(self.cartao)
        self.c_titulo = QLabel()
        self.c_titulo.setStyleSheet("font-size:16px;font-weight:bold")
        self.c_texto = QLabel("Esta configuração tem uma janela própria.")
        self.c_texto.setWordWrap(True)
        self.c_botao = QPushButton("Abrir…")
        self.c_botao.clicked.connect(self._abrir_atual)
        c.addWidget(self.c_titulo)
        c.addWidget(self.c_texto)
        c.addWidget(self.c_botao, 0, Qt.AlignLeft)
        c.addStretch(1)
        self.pilha.addWidget(self.cartao)
        h = QHBoxLayout()
        h.addWidget(self.lista)
        h.addWidget(self.pilha, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        if self.prefs is None:                         # nada para gravar aqui: só Fechar
            bb.button(QDialogButtonBox.Ok).hide()
            bb.button(QDialogButtonBox.Cancel).setText("Fechar")
        lay = QVBoxLayout(self)
        lay.addLayout(h, 1)
        lay.addWidget(bb)
        self.lista.currentRowChanged.connect(self._mostrar)
        primeiro = next((i for i, (_t, _a, ok) in enumerate(self.itens) if ok), 0)
        self.lista.setCurrentRow(primeiro)

    def _mostrar(self, linha: int) -> None:
        if not (0 <= linha < len(self.itens)):
            return
        texto, alvo, ok = self.itens[linha]
        if isinstance(alvo, str) and alvo.startswith("p:") and self.prefs is not None and ok:
            self.prefs.mostrar(alvo[2:])
            self.pilha.setCurrentWidget(self.prefs)
            return
        self.c_titulo.setText(texto.rstrip("…"))
        self.c_botao.setEnabled(ok)
        self.pilha.setCurrentWidget(self.cartao)

    def _abrir_atual(self) -> None:
        linha = self.lista.currentRow()
        if 0 <= linha < len(self.itens) and self.itens[linha][2]:
            executar(self.win, self.itens[linha][1])

    def _ok(self) -> None:
        if self.prefs is not None:
            self.prefs._save()
            if self.prefs.result() != QDialog.Accepted:
                return                                  # o _save avisou o que corrigir
            self.win._preferencias_salvas()
        self.accept()


class _CliqueNoGrupo(QObject):
    """Clique (soltar o botão) no nome de um submenu do Configurações abre a janela do grupo."""

    def __init__(self, win, menu: QMenu):
        super().__init__(menu)
        self.win, self.menu = win, menu

    def eventFilter(self, obj, e) -> bool:  # noqa: N802
        if e.type() == QEvent.MouseButtonRelease and e.button() == Qt.LeftButton:
            a = self.menu.actionAt(e.position().toPoint())
            nome = a.data() if a is not None and a.menu() is not None else None
            if isinstance(nome, str) and nome:
                self.menu.close()
                QTimer.singleShot(0, lambda: abrir_grupo(self.win, nome))
                return True
        return False


def abrir_grupo(win, nome: str):
    d = GrupoDialog(win, nome)
    d.exec()
    return d


def montar(win, menu: QMenu, dono=None, acao_todas: QAction | None = None) -> QMenu:
    """Enche `menu` com os submenus. `dono` é o pai das QActions (a janela que mostra o menu).

    `acao_todas` é a ação "Todas as preferências" da janela, que carrega o Ctrl+, — criada uma vez
    só: refazer a ação a cada abertura do menu deixaria duas teclas iguais valendo, e o Qt não
    dispara nenhuma."""
    dono = dono or menu
    menu.clear()
    from ipe import modules as MOD
    desligados = MOD.desligados(win.settings)
    for nome, itens in CATALOGO:
        sub = menu.addMenu(nome)
        sub.menuAction().setData(nome)               # 0.99.73: clicar no nome abre a janela do grupo
        sub.menuAction().setToolTip("Clique para abrir todas as configurações deste grupo")
        for texto, alvo, permissao in itens:
            if MODULO_DO_ITEM.get(texto) in desligados:
                continue
            a = QAction(texto, dono)
            a.setEnabled(_pode(permissao))
            a.triggered.connect(lambda _=False, al=alvo: executar(win, al))
            sub.addAction(a)
    if not getattr(menu, "_clique_no_grupo", None):
        menu._clique_no_grupo = _CliqueNoGrupo(win, menu)
        menu.installEventFilter(menu._clique_no_grupo)
    menu.addSeparator()
    if acao_todas is None:
        acao_todas = QAction("Todas as preferências (janela completa)…", dono)
        acao_todas.triggered.connect(lambda _=False: win.open_preferences())
    menu.addAction(acao_todas)
    return menu


def acao_todas_as_preferencias(win, dono) -> QAction:
    a = QAction("Todas as preferências (janela completa)…", dono)
    a.setShortcut(QKeySequence("Ctrl+,"))
    a.triggered.connect(lambda _=False: win.open_preferences())
    return a


def itens(win=None) -> list[tuple[str, str, object]]:
    """Lista plana (submenu, texto, alvo) — usada pelos testes que conferem que nada ficou sem porta."""
    return [(nome, texto, alvo) for nome, lista in CATALOGO for texto, alvo, _p in lista]
