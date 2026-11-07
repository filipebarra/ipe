r"""Capturas de tela do guia do usuário (0.99.87).

Abre o Ipê sem mostrar a janela (Qt offscreen), num banco temporário, importa os exames de exemplo
anonimizados e fotografa cada tela em `tools/guia/capturas/*.png`. O guia (`guia.md`) as usa com
`![Legenda](arquivo.png)`. Roda de novo a cada versão, para as imagens acompanharem a interface.

Uso:  python tools/guia/capturas.py PASTA_DOS_EXAMES [nome ...]
      (sem nomes: todas; com nomes: só essas, por exemplo `banco mamografia`)

Os exames de exemplo não vão para o repositório: são exames reais **anonimizados** (nome EXEMPLO^…,
datas deslocadas, UIDs novos, sem instituição, sem tags privadas, sem séries com texto gravado na
imagem). Cada captura é conferida a olho antes de entrar no guia.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["IPE_SEM_GITHUB"] = "1"
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
SAIDA = Path(__file__).with_name("capturas")
LARGURA, ALTURA = 1600, 960


def esperar(app, s: float = 0.6) -> None:
    fim = time.monotonic() + s
    while time.monotonic() < fim:
        app.processEvents()
        time.sleep(0.01)


def foto(widget, nome: str, app, espera: float = 0.6, recorte=None) -> Path:
    esperar(app, espera)
    img = widget.grab()
    if recorte is not None:
        img = img.copy(*recorte)
    SAIDA.mkdir(exist_ok=True)
    p = SAIDA / f"{nome}.png"
    img.save(str(p), "PNG")
    print("  ", p.name, img.width(), "x", img.height())
    return p


class Sessao:
    def __init__(self, exames: Path):
        home = Path(tempfile.mkdtemp(prefix="ipe_capturas_"))
        os.environ["DICOMVIEWER_HOME"] = str(home)
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication(sys.argv)
        from ipe.auth import session as S
        S.set_current(S.UserSession())
        from ipe.core.config import Settings, get_paths
        from ipe.db.repository import Repository
        from ipe.db.session import Database
        from ipe.importer.scanner import Importer
        from ipe.importer.thumbnails import generate_thumbnails
        self.paths = get_paths()
        self.db = Database(self.paths.database)
        self.repo = Repository(self.db)
        self.settings = Settings(self.paths.settings_file)
        r = Importer(self.db, self.paths.storage).import_paths([exames])
        generate_thumbnails(self.repo, r.new_series)
        print("importados:", r)
        from ipe.ui.main_window import MainWindow
        self.w = MainWindow(self.paths, self.settings, repo=self.repo, db=self.db)
        self.w.resize(LARGURA, ALTURA)
        self.w.show()
        esperar(self.app, 1.5)

    def uid(self, patient_id: str, indice: int = -1) -> str:
        rows = [r for r in self.repo.search_studies(limit=1000) if r.patient_id == patient_id]
        rows.sort(key=lambda r: r.study_date or "")
        return rows[indice].study_uid

    def abrir(self, patient_id: str, indice: int = -1):
        uid = self.uid(patient_id, indice)
        self.w.open_study(uid)
        esperar(self.app, 2.0)
        return self.w.tabs.currentWidget()

    def fechar_abas(self) -> None:
        while self.w.tabs.count() > 1:
            self.w._close_tab(self.w.tabs.count() - 1)
            esperar(self.app, 0.2)
        esperar(self.app, 0.3)


# ------------------------------------------------------------------ ajudantes
def serie(tab, texto: str, modalidade: str = "") -> str | None:
    for x in tab.series:
        if texto.lower() in (x.description or "").lower() and (not modalidade or x.modality == modalidade):
            return x.series_uid
    return None


def no_meio(vp, fracao: float = 0.5) -> None:
    if vp is not None and vp.frames:
        vp.set_index_silently(int((len(vp.frames) - 1) * fracao)) if hasattr(vp, "set_index_silently") else None
        vp._load_current()
        vp.update()


def arrastar(app, vp, a, b) -> None:
    """Arrasta o mouse no quadro de a para b (frações da largura/altura): cria a medida da ferramenta ativa."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    pa = QPoint(int(vp.width() * a[0]), int(vp.height() * a[1]))
    pb = QPoint(int(vp.width() * b[0]), int(vp.height() * b[1]))
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, pa)
    for t in (0.25, 0.5, 0.75, 1.0):
        QTest.mouseMove(vp, QPoint(int(pa.x() + (pb.x() - pa.x()) * t), int(pa.y() + (pb.y() - pa.y()) * t)))
        esperar(app, 0.03)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, pb)
    esperar(app, 0.2)


def dialogo(s, acao, nome: str, espera: float = 1.2, tamanho=None, ajuste=None):
    """Roda `acao` (que abre uma janela, modal ou não), fotografa a janela nova e fecha."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog
    antes = {id(w) for w in QApplication.topLevelWidgets() if w.isVisible()}
    feito = {}

    def pegar():
        novas = [w for w in QApplication.topLevelWidgets() if w.isVisible() and id(w) not in antes
                 and w is not s.w]
        if not novas:
            if feito.setdefault("tentativas", 0) < 40:
                feito["tentativas"] += 1
                QTimer.singleShot(150, pegar)
            return
        w = novas[-1]
        if tamanho:
            w.resize(*tamanho)
        if ajuste is not None:
            ajuste(w)
        esperar(s.app, espera)
        foto(w, nome, s.app, 0.1)
        feito["ok"] = True
        if isinstance(w, QDialog):
            w.reject()
        else:
            w.close()
    QTimer.singleShot(300, pegar)
    try:
        acao()
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
    fim = time.monotonic() + 10
    while "ok" not in feito and time.monotonic() < fim:
        s.app.processEvents()
        time.sleep(0.02)
    esperar(s.app, 0.3)


# ------------------------------------------------------------------ as capturas
def cap_banco(s: Sessao):
    s.w.tabs.setCurrentIndex(0)
    if hasattr(s.w, "browser"):
        s.w.browser.refresh()
        tv = getattr(s.w.browser, "table", None) or getattr(s.w.browser, "view", None)
        try:
            tv.selectRow(1)
        except Exception:  # noqa: BLE001
            pass
    foto(s.w, "banco", s.app, 1.0)


def cap_visualizador(s: Sessao):
    tab = s.abrir("EX002")
    portal = serie(tab, "PORTAL", "CT")
    tab.show_series([portal])
    esperar(s.app, 1.5)
    no_meio(tab.viewports[0], 0.78)
    foto(s.w, "visualizador_tc_orgaos", s.app, 2.5)
    # a barra, em duas metades empilhadas (inteira na largura da página ficaria miúda)
    from PySide6.QtGui import QPainter, QPixmap
    esperar(s.app, 0.2)
    tela = s.w.grab()
    metade = 780                                  # entre "Anteriores" e "Medidas"
    barra = QPixmap(LARGURA - metade, 120)
    barra.fill(tela.toImage().pixelColor(LARGURA - 8, 58))
    p = QPainter(barra)
    p.drawPixmap(0, 0, tela.copy(0, 50, metade, 60))
    p.drawPixmap(0, 60, tela.copy(metade, 50, LARGURA - metade, 60))
    p.end()
    barra.save(str(SAIDA / "barra_ferramentas.png"), "PNG")
    print("   barra_ferramentas.png", barra.width(), "x", barra.height())
    s.fechar_abas()


def cap_3d(s: Sessao):
    tab = s.abrir("EX003")
    pt = serie(tab, "PET AC", "PT")
    tab.show_series([pt])
    esperar(s.app, 1.5)
    tab.open_3d("mip")
    foto(s.w, "3d_mip_pet", s.app, 6.0)
    s.fechar_abas()


def cap_dinamica(s: Sessao):
    tab = s.abrir("EX005")
    dialogo(s, tab.open_dynamic, "dinamica_fases")
    s.fechar_abas()


def cap_layout(s: Sessao):
    tab = s.abrir("EX006")
    uids = [x.series_uid for x in tab.series if x.modality == "MR"][:4]
    tab.show_series(uids)
    esperar(s.app, 1.5)
    for vp in tab.viewports:
        no_meio(vp, 0.55)
    foto(s.w, "layout_rm_cranio", s.app, 1.5)
    s.fechar_abas()


def cap_mpr(s: Sessao):
    tab = s.abrir("EX002")
    portal = serie(tab, "PORTAL", "CT")
    tab.show_series([portal])
    esperar(s.app, 1.0)
    no_meio(tab.viewports[0], 0.45)
    tab.mpr_action.setChecked(True)
    esperar(s.app, 3.0)
    foto(s.w, "mpr", s.app, 1.5)
    s.fechar_abas()


def cap_mamografia(s: Sessao):
    tab = s.abrir("EX001")
    foto(s.w, "mamografia", s.app, 2.5)
    try:
        tab.active = tab.viewports[0]
        tab.mg_toggle_tomo()
        esperar(s.app, 2.0)
        foto(s.w, "mamografia_tomo", s.app, 1.5)
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
    s.fechar_abas()


def cap_pet(s: Sessao):
    tab = s.abrir("EX003")
    ct, pt = serie(tab, "STD", "CT"), serie(tab, "PET AC", "PT")
    tab.show_series([ct])
    esperar(s.app, 1.0)
    vp = tab.viewports[0]
    no_meio(vp, 0.5)
    tab.set_fusion(vp, pt)
    foto(s.w, "pet_fusao", s.app, 3.0)
    s.fechar_abas()


def cap_coluna(s: Sessao):
    tab = s.abrir("EX004")
    sag = serie(tab, "Sag T2", "MR")
    tab.show_series([sag])
    esperar(s.app, 2.0)
    no_meio(tab.viewports[0], 0.5)
    foto(s.w, "rm_coluna_niveis", s.app, 3.0)
    s.fechar_abas()


def _mama_series(tab):
    return [u for u in (serie(tab, "Ax T2"), serie(tab, "VIBRANT FLEX 1+3"), serie(tab, "Ph1/"), serie(tab, "Ph3/"))
            if u]


def cap_rm_mama(s: Sessao):
    tab = s.abrir("EX005")
    tab.show_series(_mama_series(tab))
    esperar(s.app, 1.5)
    for vp in tab.viewports:
        no_meio(vp, 0.5)
    foto(s.w, "rm_mama", s.app, 2.5)
    s.fechar_abas()


def cap_anteriores(s: Sessao):
    tab = s.abrir("EX005")
    tab.show_series(_mama_series(tab)[:2])
    esperar(s.app, 1.0)
    for vp in tab.viewports:
        no_meio(vp, 0.5)
    tab.toggle_priors_panel(True)
    esperar(s.app, 1.0)
    foto(s.w, "anteriores", s.app, 1.5)
    s.fechar_abas()


def cap_estruturas(s: Sessao):
    tab = s.abrir("EX002")
    portal = serie(tab, "PORTAL", "CT")
    tab.show_series([portal])
    esperar(s.app, 1.0)
    no_meio(tab.viewports[0], 0.45)
    no_meio(tab.viewports[0], 0.78)
    painel = tab.abrir_estruturas(tab.viewports[0])
    esperar(s.app, 2.0)
    if painel is not None and painel.isWindow():
        foto(painel, "estruturas_painel", s.app, 0.5)
    try:
        painel.close()
    except Exception:  # noqa: BLE001
        pass
    s.fechar_abas()


def cap_medidas(s: Sessao):
    """Por último: as medidas ficam gravadas no banco e apareceriam nas outras capturas."""
    tab = s.abrir("EX002")
    portal = serie(tab, "PORTAL", "CT")
    tab.show_series([portal])
    esperar(s.app, 1.5)
    vp = tab.viewports[0]
    no_meio(vp, 0.78)
    esperar(s.app, 1.0)
    tab.set_left_tool("measure")
    arrastar(s.app, vp, (0.335, 0.34), (0.335, 0.64))
    tab.set_left_tool("ellipse")
    arrastar(s.app, vp, (0.37, 0.38), (0.42, 0.46))
    foto(s.w, "medidas", s.app, 0.8)
    s.fechar_abas()


def _caminho_amigavel(w) -> None:
    from PySide6.QtWidgets import QLineEdit
    for e in w.findChildren(QLineEdit):
        if e.text().startswith(("/root", "/tmp", "/home")):
            e.setText("C:\\Users\\voce\\Documents")


def _primeira_aba(w) -> None:
    from PySide6.QtWidgets import QTabWidget
    for t in w.findChildren(QTabWidget):
        t.setCurrentIndex(0)


def cap_exportar(s: Sessao):
    tab = s.abrir("EX006")
    dialogo(s, tab.export_dialog, "exportar", ajuste=_caminho_amigavel)
    s.fechar_abas()


def cap_configuracoes(s: Sessao):
    s.w.tabs.setCurrentIndex(0)
    for nome_metodo, arquivo in (("abrir_config_barra", "config_barra"),
                                 ("open_network_settings", "config_rede"),
                                 ("open_central_settings", "config_servidor_central")):
        f = getattr(s.w, nome_metodo, None)
        if f is not None:
            dialogo(s, f, arquivo, ajuste=_primeira_aba)

CAPTURAS = {k[4:]: v for k, v in dict(globals()).items() if k.startswith("cap_")}
CAPTURAS["medidas"] = CAPTURAS.pop("medidas")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    exames = Path(argv[0])
    nomes = argv[1:] or list(CAPTURAS)
    s = Sessao(exames)
    for n in nomes:
        print(n)
        try:
            CAPTURAS[n](s)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            print(f"  FALHOU: {n}: {e}")
            s.fechar_abas()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
