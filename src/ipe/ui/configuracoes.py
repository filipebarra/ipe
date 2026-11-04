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

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu

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
    ]),
    ("Laudos", [
        ("Busca ativa (prazos por BI-RADS)…", "f:abrir_config_busca_ativa", "users"),
    ]),
    ("Monitores", [
        ("Papel, layout e ordem dos monitores…", "p:monitores", "configure"),
        ("Calibração GSDF do monitor…", "f:open_gsdf", "configure"),
    ]),
    ("Rede", [
        ("Nós DICOM (PACS, estações)…", "f:open_network_settings", "query"),
        ("Automação (buscas agendadas, anteriores, roteamento, limpeza)…", "f:open_automation", "configure"),
        ("Servidor central (intranet)…", "f:open_central_settings", "configure"),
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
        ("Abrir a pasta de dados", "f:_open_data_folder", ""),
    ]),
    ("Usuários", [
        ("Modo de uso (só eu, várias pessoas, servidor)…", "f:abrir_modo_de_uso", "users"),
        ("Usuários e permissões…", lambda w: w.open_users(tab=0), "users"),
        ("Configurações pessoais e compartilhadas…", "f:abrir_config_niveis", ""),
    ]),
    ("Sistema", [
        ("Ao abrir o programa…", "p:abertura", ""),
        ("Desempenho…", "p:desempenho", "configure"),
        ("Módulos…", "p:modulos", ""),
        ("Idioma…", "p:idioma", ""),
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
        for texto, alvo, permissao in itens:
            if MODULO_DO_ITEM.get(texto) in desligados:
                continue
            a = QAction(texto, dono)
            a.setEnabled(_pode(permissao))
            a.triggered.connect(lambda _=False, al=alvo: executar(win, al))
            sub.addAction(a)
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
