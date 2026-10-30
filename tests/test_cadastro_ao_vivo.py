"""0.99.6: nó DICOM e servidor de impressão novos valem na hora, sem fechar e abrir a janela.

Bug relatado: *"quando acrescento um nó DICOM, ao testar dá erro. tenho que salvar, fechar e abrir a
janela para aparecer. o mesmo acontece quando acrescento um destino (impressora) na impressão"*.
"""
import socket

from PySide6.QtWidgets import QApplication, QDialog

from ipe.core.config import Settings


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_no_novo_vale_na_hora(env, monkeypatch):
    from ipe.network.service import NetworkService
    from ipe.ui import network_dialog as ND
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    st = Settings(paths.settings_file)
    st.set("dicom", {"enabled": True, "ae_title": "EU", "port": _porta_livre(), "accept": "known"})
    net = NetworkService(db, repo, paths.storage, st)
    assert net.server.start()
    mudou = []
    try:
        dlg = ND.NetworkDialog(st, repo, net, ao_mudar=lambda: mudou.append(1))

        def preencher(nd):
            nd.name.setText("Tomógrafo")
            nd.ae.setText("CT01")
            nd.host.setText("127.0.0.1")
            nd._ok()
            return nd.result()
        monkeypatch.setattr(ND.NodeDialog, "exec", preencher)
        dlg._edit_node(new=True)
        assert mudou == [1], "PACS, Gestão e Enviar para recarregam na hora"
        assert "CT01" in net.server._ae.require_calling_aet, "o tomógrafo já pode conectar"
        assert dlg._selected_node()["ae_title"] == "CT01", "o novo fica selecionado para o Testar"
        # o Testar do cadastro testa o que está na tela, mesmo sem salvar
        nd = ND.NodeDialog(None, None, net, st)
        nd.ae.setText("EU")
        nd.host.setText("127.0.0.1")
        nd.port.setValue(net.server.config["port"] if hasattr(net.server, "config") else 104)
        testados = []
        monkeypatch.setattr(net, "test_network", lambda node, ident, done: testados.append(node))
        nd._test()
        assert testados and testados[0]["ae_title"] == "EU" and testados[0]["kind"] == "dimse"
        assert isinstance(nd, QDialog)
    finally:
        net.shutdown()


def test_servidor_de_impressao_novo_responde_ao_teste_sem_ok(env):
    from ipe.network.service import NetworkService
    from ipe.printing import config as C
    from ipe.ui import print_settings as PS
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    st = Settings(paths.settings_file)
    net = NetworkService(db, repo, paths.storage, st)
    try:
        dlg = PS.PrintSettingsDialog(st, net)
        porta = _porta_livre()
        dlg.servers.append(C.ServerConfig(name="Sala 2", ae_title="SALA2", port=porta, enabled=True, accept="any"))
        dlg._encher_servidores()
        dlg.t_serv.selectRow(len(dlg.servers) - 1)
        dlg._testar_servidor()
        assert "respondeu na porta" in dlg.serv_status.text() and "aplicados" in dlg.serv_status.text(), \
            dlg.serv_status.text()
        assert any(s.port == porta and s.running for s in net.print_servers)
    finally:
        net.shutdown()
