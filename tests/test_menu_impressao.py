"""0.99.6: menu Impressão (o que era de impressão no Arquivo) e Acrescentar impressora DICOM."""
from PySide6.QtWidgets import QApplication, QDialog

from ipe.core.config import Settings


def _menus(w):
    return {a.text(): a.menu() for a in w.menuBar().actions() if a.menu() is not None}


def test_menu_impressao_e_acrescentar_impressora(env, monkeypatch):
    from ipe.ui.film import dialogs as D
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        menus = _menus(w)
        nomes = list(menus)
        assert nomes.index("I&mpressão") == nomes.index("&Arquivo") + 1
        imp = [a.text() for a in menus["I&mpressão"].actions() if a.text()]
        assert imp == ["Filme / impressão (mostrar/esconder)", "Filmes salvos…",
                       "Impressões (recebidas e montadas aqui)…", "Painel de filmes e impressões…"]
        # 0.99.12: o que se configura foi para Configurações ▸ Impressão
        conf = next(a.menu() for a in menus["&Configurações"].actions() if a.text() == "Impressão")
        assert [a.text() for a in conf.actions()] == [
            "Acrescentar impressora DICOM…", "Impressoras DICOM…",
            "Servidores, destinos, regras e modelos de folha…"]
        arq = [a.text() for a in menus["&Arquivo"].actions()]
        assert not any("Impress" in t or "impress" in t or "Filme" in t for t in arq)

        def preencher(dlg):
            dlg.f_name.setText(f"Dry {len(dlg.printers)}")
            dlg.f_ae.setText("DRY")
            dlg.f_host.setText("10.0.0.9")
            dlg._accept()
            return dlg.result()
        monkeypatch.setattr(D.DicomPrintDialog, "exec", preencher)
        w.acrescentar_impressora_dicom()                       # sem nenhuma: abre com uma nova
        assert [p["name"] for p in w.settings.get("printing.dicom_printers")] == ["Dry 1"]
        w.acrescentar_impressora_dicom()                       # com uma: acrescenta a segunda
        ps = w.settings.get("printing.dicom_printers")
        assert [p["name"] for p in ps] == ["Dry 1", "Dry 2"] and ps[1]["host"] == "10.0.0.9"
        # sem AE/IP não salva
        monkeypatch.setattr(D.QMessageBox, "warning", staticmethod(lambda *a, **k: 0))
        monkeypatch.setattr(D.DicomPrintDialog, "exec", lambda dlg: (dlg._accept(), dlg.result())[1])
        w.acrescentar_impressora_dicom()
        assert len(w.settings.get("printing.dicom_printers")) == 2
        assert QDialog
    finally:
        w.close()


def test_menu_rede_tem_a_gestao_e_a_automatica(env):
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        rede = _menus(w)["&Rede"]
        acoes = {a.text(): a for a in rede.actions() if a.text()}
        assert "Gestão DICOM (exames das modalidades no PACS)…" in acoes
        acoes["Gestão automática (regras com horário)…"].trigger()
        g = w.gestao_window
        assert g.isVisible() and g.abas.currentWidget() is g.painel_auto
        g.close()
        acoes["Gestão DICOM (exames das modalidades no PACS)…"].trigger()
        assert w.gestao_window.isVisible()
    finally:
        w.close()
