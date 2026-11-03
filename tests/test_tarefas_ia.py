"""0.99.32: acompanhar e cancelar as IAs (inclusive as automáticas da chegada), a marca de IA no banco,
os órgãos abdominais no botão Aplicações e as janelas de configuração que diminuem e maximizam."""
import time

import pytest
from PySide6.QtWidgets import QApplication

from ipe.ai import tarefas as TA
from ipe.ai import totalseg as TS
from tests.test_cad_ia import _exame_ct, _Rede, _settings


@pytest.fixture(autouse=True)
def _registro_limpo():
    TA.REGISTRO.limpar_feitas()
    for t in TA.REGISTRO.ativas():
        TA.REGISTRO.mudar(t.id, TA.CANCELADO)
    TA.REGISTRO.limpar_feitas()
    yield


def test_registro():
    cancelados = []
    a = TA.REGISTRO.nova("Órgãos abdominais", "1.2", "TESTE, Ana TC", cancelar=lambda: cancelados.append(1))
    b = TA.REGISTRO.nova("Níveis da coluna", "1.3", "TESTE, Bia RM", origem="manual", estado=TA.RODANDO)
    assert TA.REGISTRO.resumo() == "IA: 1 rodando, 1 na fila"
    TA.REGISTRO.mudar(b.id, etapa="fast")
    assert TA.REGISTRO.cancelar(a.id) and cancelados == [1]
    assert next(t for t in TA.REGISTRO.tarefas() if t.id == a.id).estado == TA.CANCELADO   # na fila: na hora
    TA.REGISTRO.mudar(b.id, TA.PRONTO, mensagem="ok")
    assert TA.REGISTRO.resumo() == "" and not TA.REGISTRO.cancelar(b.id)
    assert TA.REGISTRO.limpar_feitas() == 2 and not TA.REGISTRO.tarefas()
    assert TA.ferramentas_da_serie("Órgãos abdominais · TotalSegmentator") == "órgãos abdominais"
    assert TA.ferramentas_da_serie("Encéfalo · SynthSeg") == "índices do crânio"
    assert TA.ferramentas_da_serie("MG CC · sem implante") == "implante"
    assert TA.ferramentas_da_serie("AX PORTAL") == ""


def test_automatica_aparece_e_termina(env, tmp_path):
    from ipe.automation.engine import AutomationEngine
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, _s = _exame_ct(env, tmp_path)
    st = _settings(paths)
    st.set(TS.CHAVE_AUTO, True)
    st.set(TS.CHAVE_COUINAUD, False)
    eng = AutomationEngine(repo, db, _Rede(), st, paths)
    eng._seg_simular = True
    assert eng.segmentar_orgaos(uid)
    t = next(x for x in TA.REGISTRO.tarefas() if x.study_uid == uid)
    assert t.estado == TA.PRONTO and t.origem == "automática" and t.ferramenta == "Órgãos abdominais"
    assert t.inicio and t.fim and "TESTE" in t.exame.upper()
    # o banco mostra a marca de IA
    row = next(r for r in repo.search_studies() if r.study_uid == uid)
    assert row.ia == "órgãos abdominais"
    from ipe.ui.browser import _marks, _marks_tip, _texto_ia
    assert "✦" in _marks(row) and "órgãos abdominais" in _marks_tip(row) and _texto_ia(row).startswith("✦")


def test_cancelar_na_fila_e_rodando(env, tmp_path, monkeypatch):
    from ipe.automation.engine import AutomationEngine
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, _s = _exame_ct(env, tmp_path)
    st = _settings(paths)
    st.set(TS.CHAVE_AUTO, True)
    eng = AutomationEngine(repo, db, _Rede(), st, paths)
    eng._seg_simular = True
    # 1) na fila (há outra rodando): cancelar tira da fila e não roda
    TS.EM_CURSO.add("outro")
    try:
        assert eng.segmentar_orgaos(uid)
        t = next(x for x in TA.REGISTRO.ativas() if x.study_uid == uid)
        assert t.estado == TA.FILA and eng._seg_fila
        from ipe.ui.tarefas_ia import TarefasIADialog
        d = TarefasIADialog()
        d.tabela.selectRow(0)
        assert d.cancelar_escolhida()
        assert not eng._seg_fila and next(x for x in TA.REGISTRO.tarefas() if x.id == t.id).estado == TA.CANCELADO
        d.close()
    finally:
        TS.EM_CURSO.discard("outro")
    # 2) rodando: o processo é derrubado e nada é gravado
    real = TS.Trabalho.rodar_aqui

    def demora(self, ao_ler_linha=None):
        ao_ler_linha and ao_ler_linha("ETAPA total (fast)")
        t = next(x for x in TA.REGISTRO.ativas() if x.study_uid == uid)
        assert t.estado == TA.RODANDO and t.etapa == "total (fast)"
        TA.REGISTRO.cancelar(t.id)                  # o usuário clica Cancelar enquanto roda
        assert self.cancelado
        return real(self, ao_ler_linha)             # já cancelado: não roda e avisa
    monkeypatch.setattr(TS.Trabalho, "rodar_aqui", demora)
    assert eng.segmentar_orgaos(uid)
    t = next(x for x in TA.REGISTRO.tarefas() if x.study_uid == uid and x.estado != TA.FILA)
    assert t.estado == TA.CANCELADO
    assert not TS.series_locais(repo, uid) and not TS.EM_CURSO
    assert any("cancelada" in r["message"] for r in repo.job_runs())


def test_trabalho_cancelar_derruba_o_processo(env, tmp_path):
    import subprocess
    import sys
    paths, _db, repo = env
    t = TS.Trabalho(repo, None, None, "1", "2", simular=True)
    t._proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    t0 = time.time()
    t.cancelar()
    t._proc.wait(10)
    assert t.cancelado and time.time() - t0 < 10


def test_aplicacao_orgaos_e_tarefas_no_menu(env, sample_dir):
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer import aplicacoes as AP
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    assert "abdome" in AP.APLICACOES
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        st = next(r for r in repo.search_studies() if (r.modalities or "").startswith("CT"))
        w.open_study(st.study_uid)
        QApplication.processEvents()
        tab = next(iter(w.all_viewer_tabs()))
        assert "abdome" in tab._apps
        tab._encher_todas_as_aplicacoes()
        textos = [a.text() for a in tab.todas_menu.actions()]
        assert any("Órgãos" in t for t in textos) or any("Órgãos" in (a.menu().title() if a.menu() else "")
                                                         for a in tab.todas_menu.actions())
        assert "Tarefas de IA (andamento e cancelar)…" in textos
        d = tab.abrir_tarefas_ia()
        assert d.isVisible() and w.abrir_tarefas_ia() is d          # a mesma janela
        d.close()
        # aviso na barra de status
        TA.REGISTRO.nova("Órgãos abdominais", st.study_uid, "x")
        w._update_status()
        assert w.ia_label.isVisibleTo(w) and "1 na fila" in w.ia_label.text()
        exibir = next(a.menu() for a in w.menuBar().actions() if a.text() == "&Exibir")
        assert "Tarefas de IA (andamento e cancelar)…" in [a.text() for a in exibir.actions()]
    finally:
        w.close()


def test_janelas_de_configuracao_diminuem_e_maximizam(env):
    from PySide6.QtCore import Qt
    from ipe.core.config import Settings
    from ipe.ui import janelas
    from ipe.ui.preferences import PreferencesDialog
    QApplication.instance() or QApplication([])
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    for pg in ("", "protocolos", "cad_ia", "mouse"):
        d = PreferencesDialog(s, None, pagina=pg)
        m = d.minimumSizeHint()
        assert m.width() < 700 and m.height() < 500, (pg, m)       # antes: ~1490 × 930
        assert janelas.com_maximizar(d)
        assert d.windowFlags() & Qt.WindowMaximizeButtonHint
    from PySide6.QtWidgets import QMessageBox
    assert not janelas.com_maximizar(QMessageBox())
