"""0.99: Preferências ▸ CAD/IA — segmentação abdominal e implante de silicone, cada um com as suas
configurações: automático na chegada, como fazer e para onde mandar depois.
"""
import numpy as np
import pytest
from pydicom.uid import generate_uid

from ipe.ai import totalseg as TS
from ipe.automation import implante as IMP
from ipe.core.sample_data import _base, _mono, _save
from ipe.importer.scanner import Importer

CT_SOP = "1.2.840.10008.5.1.4.1.1.2"


def _exame_ct(env, tmp_path, series_desc=(("AX PORTAL", 60, 1.25),), estudo="ABDOME TOTAL C/C"):
    """Exame de TC com várias séries: (descrição, cortes, espessura)."""
    paths, db, repo = env
    pat = {"name": "CADIA^Teste", "id": "CAD1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261026", "accession": "CAD01", "description": estudo,
             "for": generate_uid()}
    uids = {}
    for num, (desc, n, esp) in enumerate(series_desc, start=2):
        series = {"uid": generate_uid(), "number": num, "description": desc}
        uids[desc] = series["uid"]
        pasta = tmp_path / f"s{num}"
        for k in range(n):
            ds = _base(CT_SOP, pat, study, series, "CT")
            ds.InstanceNumber = k + 1
            ds.ImagePositionPatient = [-60.0, -60.0, 40.0 - k * esp]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.PixelSpacing = [1.0, 1.0]
            ds.SliceThickness = esp
            ds.RescaleSlope, ds.RescaleIntercept = 1, 0
            img = np.zeros((48, 48), np.int16)
            if 10 <= k < 40:
                img[10:30, 12:36] = 200
            _mono(ds, img, signed=True)
            _save(ds, pasta)
        Importer(db, paths.storage).import_paths([pasta])
    return study["uid"], uids


def _settings(paths):
    from ipe.core.config import Settings
    return Settings(paths.settings_file)


# ------------------------------------------------------------------ escolha da série
def test_escolhe_pela_prioridade_e_respeita_os_filtros(env, tmp_path):
    paths, db, repo = env
    uid, s = _exame_ct(env, tmp_path, (("SCOUT", 60, 1.0), ("AX ARTERIAL", 60, 1.25),
                                       ("AX PORTAL 5mm", 60, 5.0), ("AX PORTAL", 50, 1.25),
                                       ("MIP PORTAL", 60, 1.0), ("CURTA PORTAL", 30, 1.0)))
    st = _settings(paths)
    assert TS.escolher_serie(repo, uid, st) == (s["AX PORTAL"], "")       # a de 5 mm passa do limite
    st.set(TS.CHAVE_ESPESSURA, 0)                                           # sem limite: a de mais cortes
    assert TS.escolher_serie(repo, uid, st)[0] == s["AX PORTAL 5mm"]
    st.set(TS.CHAVE_PRIOR_CT, "ARTERIAL|PORTAL")
    assert TS.escolher_serie(repo, uid, st)[0] == s["AX ARTERIAL"]
    st.set(TS.CHAVE_MIN_CORTES, 100)
    serie, motivo = TS.escolher_serie(repo, uid, st)
    assert serie is None and "cortes" in motivo


def test_exame_serve_pela_descricao_e_modalidade(env):
    paths, _db, _repo = env
    st = _settings(paths)
    assert TS.exame_serve({"modalities": "CT", "description": "TC de Abdômen total"}, st)
    assert not TS.exame_serve({"modalities": "CT", "description": "TC DE CRANIO"}, st)
    assert not TS.exame_serve({"modalities": "MG", "description": "ABDOME"}, st)
    st.set(TS.CHAVE_EXAME_CONTEM, "")
    assert TS.exame_serve({"modalities": "CT\\SR", "description": "qualquer"}, st)
    st.set(TS.CHAVE_MODALIDADES, ["MR"])
    assert not TS.exame_serve({"modalities": "CT", "description": "qualquer"}, st)


# ------------------------------------------------------------------ automático + destinos
class _Sinal:
    def connect(self, *_a):
        pass


class _Rede:
    received = _Sinal()
    job_finished = _Sinal()

    def __init__(self):
        self.envios = []

    def run_async(self, trabalho, pronto, *_a):
        try:
            pronto(trabalho(), None)
        except Exception as e:  # noqa: BLE001
            pronto(None, e)

    def send(self, node, identity, study_uids, label, series_uids=None):
        self.envios.append((node["name"], list(study_uids), list(series_uids or []), label))


def _no(repo, nome="PACS-TESTE"):
    return repo.save_node({"name": nome, "kind": "dimse", "ae_title": "PACSTESTE", "host": "127.0.0.1",
                           "port": 11112, "active": True, "use_in_send": True})


def test_segmentacao_automatica_na_chegada_e_envio(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.automation.engine import AutomationEngine
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, s = _exame_ct(env, tmp_path)
    no = _no(repo)
    st = _settings(paths)
    st.set(TS.CHAVE_AUTO, True)
    st.set(TS.CHAVE_DESTINOS, [no])
    st.set(TS.CHAVE_COUINAUD, False)
    rede = _Rede()
    eng = AutomationEngine(repo, db, rede, st, paths)
    eng._seg_simular = True
    prontos = []
    eng.segmentacao_pronta.connect(lambda u, saida: prontos.append(u))
    assert eng.segmentar_orgaos(uid)
    locais = TS.series_locais(repo, uid)
    assert len(locais) == 2 and prontos == [uid]
    assert any(r["kind"] == "segmentacao" and r["status"] == "ok" for r in repo.job_runs())
    assert len(rede.envios) == 1 and set(rede.envios[0][2]) == locais and rede.envios[0][0] == "PACS-TESTE"
    assert not TS.EM_CURSO
    # exame já segmentado não é refeito
    assert not eng.segmentar_orgaos(uid)
    assert len(TS.series_locais(repo, uid)) == 2


def test_segmentacao_automatica_desligada_ou_exame_que_nao_serve(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.automation.engine import AutomationEngine
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, _s = _exame_ct(env, tmp_path, estudo="TC DE CRANIO")
    st = _settings(paths)
    eng = AutomationEngine(repo, db, _Rede(), st, paths)
    eng._seg_simular = True
    assert not eng.segmentar_orgaos(uid)              # desligado (padrão)
    st.set(TS.CHAVE_AUTO, True)
    assert not eng.segmentar_orgaos(uid)              # crânio não está na descrição
    assert not TS.series_locais(repo, uid)


def test_implante_regra_da_marca_e_destinos(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.automation.engine import AutomationEngine
    from tests.test_implante_chegada import _exame
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid = _exame(env, tmp_path, [("R", "CC", "YES", True), ("L", "CC", "", True)])   # a CCE não traz a marca
    st = _settings(paths)
    st.set(IMP.CHAVE_SO_COM_MARCA, True)
    no = _no(repo)
    st.set(IMP.CHAVE_DESTINOS, [no])
    rede = _Rede()
    eng = AutomationEngine(repo, db, rede, st, paths)
    eng.corrigir_implantes(uid)
    assert len(IMP.ja_salvas(repo, uid)) == 1                     # só a que tem a marca
    assert len(rede.envios) == 1 and len(rede.envios[0][2]) == 1
    copia = rede.envios[0][2][0]
    assert any(s.series_uid == copia and s.description.endswith(" · sem implante")
               for s in repo.series_for_study(uid))


def test_botao_implante_respeita_a_opcao_de_salvar(env, tmp_path):
    from tests.test_implante_chegada import _exame, _janela
    paths, db, repo = env
    uid = _exame(env, tmp_path, [("R", "CC", "YES", True), ("L", "CC", "YES", True)])
    app, w = _janela(env)
    try:
        w.settings.set(IMP.CHAVE_SALVAR_BOTAO, False)
        assert w.handle_external({"accession": "IMPC01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        tab.mg_set_implant(True)
        for _ in range(40):
            app.processEvents()
        assert not IMP.ja_salvas(repo, uid)
    finally:
        w.close()


# ------------------------------------------------------------------ a aba
def test_aba_cad_ia_mostra_e_grava(env):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from ipe.ui.preferences import PreferencesDialog
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    no = _no(repo, "PACS-A")
    st = _settings(paths)

    class Pai:
        pass
    from PySide6.QtWidgets import QWidget
    pai = QWidget()
    pai.repo = repo
    dlg = PreferencesDialog(st, pai)
    nomes = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert "CAD/IA" in nomes and nomes.index("CAD/IA") == nomes.index("Mamografia") + 1
    assert not hasattr(dlg.mg_editor, "c_implante")               # mudou para a aba CAD/IA
    c = dlg.cad_ia
    assert not c.c_seg_auto.isChecked() and c.c_imp_auto.isChecked() and c.r_imp_qualquer.isChecked()
    assert c.l_seg_dest.count() == 1 and c.l_imp_dest.count() == 1
    c.c_seg_auto.setChecked(True)
    c.e_seg_ct.setText("PORTAL|ABD")
    c.s_seg_esp.setValue(2.5)
    c.c_seg_couinaud.setChecked(False)
    for k in range(c.l_seg_estr.count()):
        it = c.l_seg_estr.item(k)
        it.setCheckState(Qt.Checked if it.data(Qt.UserRole) in ("liver", "spleen", "aorta") else Qt.Unchecked)
    c.l_seg_dest.item(0).setCheckState(Qt.Checked)
    c.c_imp_auto.setChecked(False)
    c.r_imp_marca.setChecked(True)
    c.c_imp_botao.setChecked(False)
    c.l_imp_dest.item(0).setCheckState(Qt.Checked)
    c.save()
    assert st.get(TS.CHAVE_AUTO) is True and st.get(TS.CHAVE_PRIOR_CT) == "PORTAL|ABD"
    assert st.get(TS.CHAVE_ESPESSURA) == 2.5 and st.get(TS.CHAVE_COUINAUD) is False
    assert TS.estruturas(st) == ["liver", "spleen", "aorta"]
    assert [t["nome"] for t in TS.tarefas("CT", st)] == ["total"]
    assert st.get(TS.CHAVE_DESTINOS) == [no] and st.get(IMP.CHAVE_DESTINOS) == [no]
    assert st.get(IMP.CHAVE) is False and st.get(IMP.CHAVE_SO_COM_MARCA) is True
    assert st.get(IMP.CHAVE_SALVAR_BOTAO) is False


# ------------------------------------------------------------------ 0.99.1
def test_importar_pela_tela_tambem_dispara_o_cad_ia(env, tmp_path):
    """O defeito: o implante automático só rodava no exame que chegava pela rede (Q/R); importado
    direto (pasta, arquivos, ZIP, arrastar) não. Agora a importação chama o CAD/IA da chegada."""
    import time
    from PySide6.QtWidgets import QApplication

    from ipe.core.config import Settings
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.ui.main_window import MainWindow
    from tests.test_mammo import _mama_com_implante
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    pat = {"name": "IMPORTADA^Implante", "id": "IMP9", "birth": "19750101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261026", "accession": "IMP09", "description": "MAMOGRAFIA",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 1, "description": "2D_PROC"}
    pasta = tmp_path / "para_importar"
    for k, lado in enumerate(("R", "L"), start=1):
        px, _c, _p = _mama_com_implante(seed=k)
        ds = _base("1.2.840.10008.5.1.4.1.1.1.2", pat, study, series, "MG")
        ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition = k, lado, "CC"
        ds.BreastImplantPresent = "YES"
        ds.PresentationIntentType = "FOR PRESENTATION"
        ds.ImagerPixelSpacing = [0.1, 0.1]
        _mono(ds, (px if lado == "R" else px[:, ::-1].copy()).astype(np.uint16), signed=False)
        _save(ds, pasta)
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        w.start_import([pasta])
        fim = time.time() + 90
        while time.time() < fim and len(IMP.ja_salvas(repo, study["uid"])) < 2:
            app.processEvents()
            time.sleep(0.05)
        assert len(IMP.ja_salvas(repo, study["uid"])) == 2
        # importar de novo (nada novo) não refaz nada
        assert w.auto.cad_ia_importados(type("R", (), {"new_series": set(), "studies": {study["uid"]}})()) == []
    finally:
        w.close()


def test_layout_lista_a_esquerda_configuracoes_a_direita(env):
    from PySide6.QtWidgets import QApplication, QWidget

    from ipe.ui.preferences import PreferencesDialog
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    pai = QWidget()
    pai.repo = repo
    d = PreferencesDialog(_settings(paths), pai)
    c = d.cad_ia
    assert c.l_ferramentas.count() == 16 and c.painel.count() == 16       # + cálcio, carga PET, coluna, cefalometria, crânio, linfonodos, nódulos, composição, fígado na RM, enfisema, Genant, lesões hepáticas, autoPET, BraTS
    assert c.l_ferramentas.item(0).text().startswith("Segmentação abdominal")
    assert "só à mão" in c.l_ferramentas.item(0).text() and "automático" in c.l_ferramentas.item(2).text()
    c.c_seg_auto.setChecked(True)
    assert "automático" in c.l_ferramentas.item(0).text()
    c.l_ferramentas.setCurrentRow(2)
    assert c.painel.currentIndex() == 2
    h = d.hp_editor
    assert h.l_protos.count() == len(h.protos) and h.e_p_nome.text() == h.protos[h._pi]["name"]
    h._selecionar(1)
    assert h.e_p_nome.text() == h.protos[1]["name"]
    h.c_p_ativo.setChecked(False)
    assert h.protos[1]["enabled"] is False and h.l_protos.item(1).text().endswith("desligado")
