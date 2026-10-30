"""Editar um servidor de impressão tem de salvar (0.81: o OK não fechava a janela).

O combo "Aceitar conexões de" se chamava `self.accept` e apagava o `QDialog.accept`: o OK dava
erro escondido, a janela ficava aberta e nada era gravado.
"""

from PySide6.QtWidgets import QApplication, QDialog

from ipe.core.config import Settings
from ipe.printing import config as C
from ipe.ui import print_settings as PS


def test_ok_do_editor_fecha_e_devolve_os_dados(env):
    paths, _db, _repo = env
    _app = QApplication.instance() or QApplication([])
    s = Settings(paths.settings_file)
    srv = C.ServerConfig(name="Mamografia", ae_title="PRNMG", port=11113)
    dlg = PS.ServerEditor(srv, s, [])
    dlg.name.setText("Mamo sala 2")
    dlg.ae.setText("PRNMG2")
    dlg.port.setValue(11120)
    dlg.aceitar_de.setCurrentIndex(dlg.aceitar_de.findData("known"))
    dlg._ok()
    assert dlg.result() == QDialog.Accepted
    novo = dlg.server()
    assert (novo.name, novo.ae_title, novo.port, novo.accept) == ("Mamo sala 2", "PRNMG2", 11120, "known")


def test_editar_pela_janela_de_configuracoes_grava(env, monkeypatch):
    paths, _db, _repo = env
    _app = QApplication.instance() or QApplication([])
    s = Settings(paths.settings_file)
    C.save_servers(s, [C.ServerConfig(name="Mamografia", ae_title="PRNMG", port=11113)])
    s.save()

    def exec_editando(dlg):
        dlg.ae.setText("PRNNOVO")
        dlg.port.setValue(11150)
        dlg._ok()
        return dlg.result()
    monkeypatch.setattr(PS.ServerEditor, "exec", exec_editando)
    janela = PS.PrintSettingsDialog(s, None)
    janela.t_serv.selectRow(0)
    janela._editar_servidor()
    janela._salvar()
    lido = C.all_servers(Settings(paths.settings_file))
    assert (lido[0].ae_title, lido[0].port) == ("PRNNOVO", 11150)
