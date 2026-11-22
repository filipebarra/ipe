"""0.100.98: o lote a partir de planilha no Ipê cliente roda no servidor central — o servidor busca no PACS (nó
compartilhado), baixa, faz e grava a planilha; o cliente acompanha, baixa a planilha e traz o exame para o banco dele.
O "PACS" é um nó de teste em loopback. Só dados inventados."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_pacs_pelo_servidor import _compartilhar, servidor  # noqa: E402,F401

from ipe.automation import planilha as P  # noqa: E402


def _girar(app, cond, s=120):
    fim = time.time() + s
    while time.time() < fim:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_lote_no_servidor_pelo_cliente(servidor, tmp_path, monkeypatch):  # noqa: F811
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from ipe.central import lote_servidor as LS
    from ipe.central.client_repo import ClientRepository
    from ipe.central.remote import RemoteClient
    from ipe.core.config import Settings
    from ipe.db.repository import Repository
    from ipe.db.session import Database
    from ipe.ui.lote_dialogo import LoteDialog
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: avisos.append(a[2])))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: avisos.append(a[2])))
    _compartilhar(servidor)
    cli = RemoteClient(f"http://127.0.0.1:{servidor.port}")
    cli.login("admin", "admin123")
    cache = Database(tmp_path / "cache" / "cache.sqlite")
    repo = ClientRepository(Repository(cache), cli, tmp_path / "cache" / "Storage")
    lista = tmp_path / "lista.csv"
    lista.write_text("Paciente;Nº de acesso;Nota\nEXEMPLO;ACC1001;7\nOUTRO;NAOEXISTE;1\n", encoding="utf-8")
    d = LoteDialog(repo, cache, None, Settings(tmp_path / "c.json"), tmp_path / "cache" / "Storage", None)
    assert d.remoto and [d.l_nos.item(i).text() for i in range(d.l_nos.count())] == ["PACS"]
    assert not d.k_trazer.isHidden() and not d.c_ident.isEnabled()
    assert d.abrir_arquivo(str(lista)) and d.tipos() == ["nome", "acesso", "ignorar"]
    d.l_nos.item(0).setCheckState(Qt.Checked)
    d.k_trazer.setChecked(True)
    d.k_apagar.setChecked(True)
    d.iniciar()
    assert not avisos, avisos
    assert _girar(servidor.app, lambda: not d._timer_remoto.isActive(), 180), d.diario.toPlainText()
    texto = d.diario.toPlainText()
    assert "Linha 2: feito" in texto and "Linha 3: não encontrado" in texto, texto
    assert "EXEMPLO" not in texto
    saida = Path(d.e_saida.text())
    t = P.ler_planilha(saida)
    r = dict(zip(t[0], t[1]))
    assert r["Ipê: situação"] == "feito" and r["Ipê: Study UID"] == servidor.estudo and r["Nota"] == "7"
    # o exame veio para o banco deste computador e, copiado, saiu do servidor (o lote o baixou só para isso)
    assert _girar(servidor.app, lambda: repo.local.study_uids_present([servidor.estudo]), 120)
    assert _girar(servidor.app, lambda: servidor.repo_.study_info(servidor.estudo) is None, 60)
    # mandar de novo com o mesmo nome continua: nada a fazer, e o lote é de quem pediu
    assert LS._LOTES[d.remoto_id].dono == "admin"
    cli2 = RemoteClient(f"http://127.0.0.1:{servidor.port}")
    cli2.login("med", "medic123")
    try:
        cli2.rpc("lote_estado", d.remoto_id, 0)
        assert False, "outro usuário viu o lote"
    except Exception as e:  # noqa: BLE001
        assert "outro usuário" in str(e)
    d.close()
