"""0.100.8: retomar a sessão depois de uma queda — o que estava aberto fica anotado; fechar direito apaga a marca;
abrir depois de uma queda oferece reabrir (perguntar, sempre ou nunca), e o estado da análise é guardado de tempos
em tempos, não só ao fechar."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_pedidos_29_10 import _sem_protocolos  # noqa: E402
from test_pet_onco import _gravar_pet  # noqa: E402

from ipe.ui import sessao as SS  # noqa: E402


def test_marca_e_queda(tmp_path):
    s = SS.Sessao(tmp_path)
    assert not s.caiu() and s.exames_da_queda() == []
    s.gravar([{"study": "1.2", "series": ["a"], "titulo": "X"}], "1.2")
    dados = json.loads((tmp_path / SS.ARQUIVO).read_text())
    assert dados["aberta"] and dados["ativo"] == "1.2"
    # o mesmo processo não é queda (testes, reabrir a janela)
    assert not SS.Sessao(tmp_path).caiu()
    dados["pid"] = -1
    (tmp_path / SS.ARQUIVO).write_text(json.dumps(dados))
    outra = SS.Sessao(tmp_path)
    assert outra.caiu() and outra.exames_da_queda()[0]["study"] == "1.2"
    outra.encerrar()
    assert not SS.Sessao(tmp_path).caiu()
    # arquivo pela metade não derruba nada
    (tmp_path / SS.ARQUIVO).write_text('{"aberta": tr')
    assert not SS.Sessao(tmp_path).caiu()
    assert "e mais 2" in SS.descrever([{"study": str(i)} for i in range(8)])


@pytest.fixture
def dois_exames(env, tmp_path):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    a = _gravar_pet(tmp_path / "a", acc="SES01")
    b = _gravar_pet(tmp_path / "b", acc="SES02")
    Importer(db, paths.storage).import_paths([tmp_path / "a", tmp_path / "b"])
    return paths, db, repo, a, b


def _janela(paths):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    st = _sem_protocolos(Settings(paths.settings_file))
    w = MainWindow(paths, st)
    w.show()
    app.processEvents()
    return app, w, st


def _cair(paths, w):
    """Simula a queda: a marca de "aberto" fica, de outro processo."""
    arq = paths.config / SS.ARQUIVO
    w.gravar_sessao()
    dados = json.loads(arq.read_text())
    w.close()                                               # o X fecha os exames…
    w.close()                                               # …e o segundo, o programa
    assert not json.loads(arq.read_text())["aberta"]          # fechar direito apaga a marca
    dados["pid"] = -1
    arq.write_text(json.dumps(dados))
    return dados


def test_reabre_o_que_estava_aberto(dois_exames):
    paths, db, repo, a, b = dois_exames
    app, w, st = _janela(paths)
    w.handle_external({"accession": "SES01"})
    w.handle_external({"accession": "SES02"})
    w.open_study(a)                                         # o primeiro fica na frente
    app.processEvents()
    dados = _cair(paths, w)
    assert [e["study"] for e in dados["exames"]] == [a, b] and dados["ativo"] == a
    assert all(e["series"] for e in dados["exames"])
    app, w2, st2 = _janela(paths)
    try:
        perguntas = []
        assert w2.oferecer_retomar(perguntar=lambda t: perguntas.append(t) or True) == 2
        assert "Os 2 exames" in perguntas[0] and perguntas[0].count("• ") == 2
        assert {t.study_uid for t in w2.all_viewer_tabs()} == {a, b}
        assert w2.tabs.currentWidget().study_uid == a
        # só uma vez: a mesma queda não é oferecida de novo
        assert w2.oferecer_retomar(perguntar=lambda t: True) == 0
    finally:
        w2.close()


def test_agora_nao_e_nunca(dois_exames):
    paths, db, repo, a, b = dois_exames
    app, w, st = _janela(paths)
    w.handle_external({"accession": "SES01"})
    app.processEvents()
    _cair(paths, w)
    app, w2, st2 = _janela(paths)
    try:
        assert w2.oferecer_retomar(perguntar=lambda t: False) == 0
        assert w2.all_viewer_tabs() == []
    finally:
        w2.close()
    # "nunca": nem pergunta
    app, w3, st3 = _janela(paths)
    w3.handle_external({"accession": "SES01"})
    app.processEvents()
    _cair(paths, w3)
    app, w4, st4 = _janela(paths)
    try:
        st4.set(SS.CHAVE_RETOMAR, "nunca")
        assert w4.oferecer_retomar(perguntar=lambda t: pytest.fail("perguntou")) == 0
    finally:
        w4.close()


def test_estado_guardado_de_tempos_em_tempos(dois_exames, monkeypatch):
    from ipe.ui.viewer.viewer_tab import ViewerTab
    paths, db, repo, a, b = dois_exames
    app, w, st = _janela(paths)
    try:
        assert w._t_estados.isActive() and w._t_estados.interval() == SS.INTERVALO_ESTADO_S * 1000
        w.handle_external({"accession": "SES01"})
        app.processEvents()
        chamadas = []
        monkeypatch.setattr(ViewerTab, "guardar_estado", lambda self: chamadas.append(self.study_uid) or True)
        w._t_estados.timeout.emit()
        assert chamadas == [a]
    finally:
        w.close()


def test_preferencia_na_janela_do_estado(dois_exames, monkeypatch):
    from PySide6.QtWidgets import QDialog
    paths, db, repo, a, b = dois_exames
    app, w, st = _janela(paths)
    try:
        def aceitar(d):
            d._r.setCurrentIndex(d._r.findData("sempre"))
            return True
        monkeypatch.setattr(QDialog, "exec", aceitar)
        w.abrir_estado_ao_abrir()
        assert st.get(SS.CHAVE_RETOMAR) == "sempre"
    finally:
        w.close()
