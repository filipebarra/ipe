"""0.100.100: no Ipê cliente, a IA roda no servidor (padrão) ou neste computador, conforme a preferência, o perfil e o
pacote de IA; o que roda aqui sobe sozinho ao servidor. Só dados inventados."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_web_ia import servidor  # noqa: E402,F401

from ipe.ai import onde as OND  # noqa: E402
from ipe.ai import tarefas as TA  # noqa: E402
from ipe.ai import totalseg as TS  # noqa: E402


class _Cliente:
    client = object()

    def upload_study(self, uid, wait=False):
        pass


def test_decidir():
    from ipe.core.config import Settings
    st = Settings(Path("/nonexistent/x.json"))
    assert OND.decidir(object(), st) == (OND.LOCAL, "")                       # banco próprio: sempre aqui
    assert OND.decidir(_Cliente(), st, perms={"ia_local"}, instalado=True) == (OND.SERVIDOR, "")   # padrão
    st.set(OND.CHAVE, OND.LOCAL)
    assert OND.decidir(_Cliente(), st, perms={"ia_local"}, instalado=True) == (OND.LOCAL, "")
    onde, aviso = OND.decidir(_Cliente(), st, perms=set(), instalado=True)
    assert onde == OND.SERVIDOR and "perfil" in aviso
    onde, aviso = OND.decidir(_Cliente(), st, perms={"ia_local"}, instalado=False)
    assert onde == OND.SERVIDOR and "não está instalado" in aviso


def test_permissao_nova_entra_na_tabela_gravada():
    from ipe.auth import permissions as PM

    class Repo:
        def __init__(self, v):
            self.v = v

        def get_app_setting(self, k, padrao=None):
            return self.v
    antiga = {"medico": ["view", "ai"], "residente": ["view"]}            # gravada antes da 0.100.100
    t = PM.role_permissions(Repo(antiga))
    assert "ia_local" in t["medico"] and "ia_local" not in t["residente"]
    nova = PM.tabela_para_gravar({"medico": ["view", "ai"], "residente": ["view"]})   # ele tirou de propósito
    assert "ia_local" not in PM.role_permissions(Repo(nova))["medico"]
    assert "ia_local" in PM.DEFAULT_ROLE_PERMS["medico"] and "ia_local" not in PM.DEFAULT_ROLE_PERMS["tecnico"]


def _girar(app, cond, s=90):
    fim = time.time() + s
    while time.time() < fim:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_cliente_pede_a_ia_ao_servidor(servidor, tmp_path, monkeypatch):  # noqa: F811
    from PySide6.QtWidgets import QMessageBox, QWidget
    from PySide6.QtCore import Signal
    from ipe.central.client_repo import ClientRepository
    from ipe.central.remote import RemoteClient
    from ipe.core.config import Settings
    from ipe.db.repository import Repository
    from ipe.db.session import Database
    from ipe.ui.segmentacao import Segmentacao
    srv = servidor
    msgs = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: msgs.append(a[2])))
    cli = RemoteClient(f"http://127.0.0.1:{srv.port}")
    cli.login("admin", "admin123")
    # cliente e servidor no mesmo processo (no teste): o pedido vai numa linha à parte enquanto a linha principal
    # gira, porque o servidor põe a fila de IA na linha principal (na vida real são dois programas)
    original = cli.rpc

    def rpc(metodo, *a, **k):
        import threading
        caixa = {}

        def ir():
            try:
                caixa["r"] = original(metodo, *a, **k)
            except Exception as e:  # noqa: BLE001
                caixa["e"] = e
        th = threading.Thread(target=ir)
        th.start()
        while th.is_alive():
            srv.app.processEvents()
            time.sleep(0.01)
        if "e" in caixa:
            raise caixa["e"]
        return caixa["r"]
    cli.rpc = rpc
    cache = Database(tmp_path / "cache" / "cache.sqlite")
    repo = ClientRepository(Repository(cache), cli, tmp_path / "cache" / "Storage")
    st = Settings(tmp_path / "c.json")                       # padrão: no servidor

    class Aba(QWidget):
        status_message = Signal(str)

        def __init__(self):
            super().__init__()
            self.chamadas = []

        def recarregar_series(self):
            self.chamadas.append("series")

        def achados_mudaram(self):
            self.chamadas.append("achados")
    aba = Aba()
    seg = Segmentacao(aba, repo, st, tmp_path / "cache" / "Storage", srv.estudo, srv.serie, tipo="abdome")
    assert seg.iniciar()
    assert _girar(srv.app, lambda: not seg._timer_servidor.isActive(), 120), msgs
    assert msgs and "Feito no servidor central" in msgs[-1], msgs
    assert len(TS.series_locais(srv.repo_, srv.estudo)) == 2                   # gravado no servidor
    assert aba.chamadas[:1] == ["series"]
    t = [x for x in TA.REGISTRO.tarefas() if x.ferramenta.endswith("(no servidor)")][0]
    assert t.estado == TA.PRONTO
    assert srv.repo_.access_log(limit=5, action="ia", study_uid=srv.estudo)


def test_lote_espera_a_ia_do_cliente(monkeypatch, tmp_path):
    """O servidor pede as IAs ao cliente e espera; quando o cliente avisa, recolhe o que ele subiu."""
    import threading
    from types import SimpleNamespace as NS

    from ipe.automation import lote as L
    from ipe.automation import lote_ipe as LP
    from ipe.central import lote_servidor as LS
    recolhidos = []

    def servicos(*a, **k):
        def ias(uid, tipos, refazer, parar=None):
            recolhidos.append((uid, tuple(tipos), refazer))
            return {t: {"titulo": t, "situacao": "já feita", "motivo": "", "campos": {"X": 1}, "series": []}
                    for t in tipos}
        return L.Servicos(local=lambda c: [{"study_uid": "U1", "patient_id": "1", "study_date": "20240101",
                                            "num_images": 3, "modalities": "CT"}],
                          no=lambda n, c: [], tem=lambda u: True, baixar=None, ias=ias,
                          protocolo=lambda u: {}, enviar=None, imprimir=None, exportar=None, apagar=lambda u: None)
    monkeypatch.setattr(LP, "servicos", servicos)
    from ipe.central import pacs_servidor as PS
    monkeypatch.setattr(PS, "compartilhados", lambda c, s: [])
    c = NS(repo=NS(audit=lambda *a, **k: None), db=None, net=None, settings=None, storage=tmp_path / "Storage",
           auto=None, ponte=NS(chamar=lambda fn, espera=0: fn()))
    s = NS(username="ana", perms={"view", "query", "retrieve"})
    cfg = L.Config(ias=["enfisema"], colunas=["id", "data"])
    r = LS.iniciar(c, s, {"nome": "teste", "cabecalho": ["ID", "Data"], "dados": [["1", "2024-01-01"]],
                          "config": cfg.to_dict(), "ia_no_cliente": True})
    ident = r["id"]
    fim = time.time() + 10
    pedidos = []
    while time.time() < fim and not pedidos:
        pedidos = LS.estado(c, s, ident)["pedidos_ia"]
        time.sleep(0.05)
    assert pedidos and pedidos[0]["study_uid"] == "U1" and pedidos[0]["tipos"] == ["enfisema"]
    assert not recolhidos                                      # o servidor não roda: espera o cliente
    LS.ia_feita(c, s, ident, "U1", True, "")
    e = LS._LOTES[ident]
    e.linha.join(10)
    assert recolhidos == [("U1", ("enfisema",), False)]
    res = e.lote.resultados[e.lote.linhas[0].chave]
    assert res["situacao"] == L.FEITO and res["exames"][0]["ias"]["enfisema"]["campos"] == {"X": 1}
