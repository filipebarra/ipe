"""0.100.1: o sinal da rede do cliente — barras (0 a 4) pelo pior entre a ida e volta e a vazão, o teste contra o
servidor (ping + 2 MB) e o indicador na barra de status."""
import time

from PySide6.QtWidgets import QApplication

from test_central import central  # noqa: F401  (fixture)
from test_central_progressivo import _cliente, _esperar
from ipe.ui.rede_sinal import SinalRede, barras, texto


def test_barras():
    assert barras(None, None, False) == 0 and barras(None, None) == 0
    assert barras(3, 900) == 4 and barras(3, None) == 4
    assert barras(3, 100) == 3 and barras(20, 900) == 3
    assert barras(50, 900) == 2 and barras(3, 30) == 2
    assert barras(200, 900) == 1 and barras(3, 5) == 1
    assert texto(12.4, 480.2) == "12 ms · 480 Mbit/s" and texto(12.4, None) == "12 ms"
    assert "ms" not in texto(None, None, False)


def test_teste_contra_o_servidor_e_indicador(central, tmp_path):  # noqa: F811
    paths, db, repo, srv = central
    app = QApplication.instance() or QApplication([])
    cr, *_ = _cliente(srv, paths, tmp_path)
    r = cr.client.medir_rede(True)
    assert r["ok"] and 0 < r["ping_ms"] < 2000 and r["mbps"] > 1
    assert cr.client.medir_rede(False)["mbps"] is None
    s = SinalRede(cr.client)
    assert s.nivel() == 0 and s._texto()
    s.medir(True)
    assert _esperar(lambda: s._tem and not s.medindo, app, 20)
    assert s.nivel() >= 1 and "Mbit/s" in s._texto() and "ms" in s.toolTip()
    antes = s.r["mbps"]
    s.medir(False)                                   # o teste rápido (a cada exame) não apaga a vazão
    time.sleep(0.05)
    assert _esperar(lambda: not s.medindo, app, 20) and s.r["mbps"] == antes
    s.vazao_do_download(42.0)
    assert _esperar(lambda: s.r["mbps"] == 42.0, app, 5)
    # servidor fora do ar: sem conexão, zero barras
    srv.stop()
    s.medir(True)
    assert _esperar(lambda: not s.medindo and s.nivel() == 0, app, 30)
    assert "Mbit" not in s._texto()
