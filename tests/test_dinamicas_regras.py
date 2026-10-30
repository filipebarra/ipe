"""Regras de dinâmico: juntar sozinho, separar sozinho, e a regra pendente."""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import dinamicas as D
from ipe.importer.scanner import Importer
from test_measure_tools import make_dynamic


# ------------------------------------------------------------------ regra
def test_o_trecho_comum_vira_a_regra():
    assert D.trecho_comum(["DYN fase 0", "DYN fase 1", "DYN fase 2"]).startswith("dyn fase")
    assert D.trecho_comum(["T1 VIBRANT Ph1", "T1 VIBRANT Ph2"]) == "t1 vibrant ph"
    assert D.trecho_comum(["AX T1", "COR T2"]) in ("", "t")
    assert D.trecho_comum([]) == ""


def test_a_regra_combina_sem_acento_e_sem_caixa():
    r = {"modalidade": "MR", "contem": "dinamica", "acao": "juntar"}
    assert D.casa(r, "MR", "RM Mama DINÂMICA pós")
    assert not D.casa(r, "CT", "RM Mama DINÂMICA pós"), "modalidade diferente não combina"
    assert D.casa({"modalidade": "", "contem": "mama", "acao": "juntar"}, "CT", "Mama")


def test_marcar_na_mao_vira_regra_pendente(tmp_path):
    st = Settings(tmp_path / "s.json")
    r = D.sugerir("MR", ["VIBRANT Ph1", "VIBRANT Ph2", "VIBRANT Ph3"], "juntar", "Mama")
    assert r and r["status"] == "pendente" and "vibrant" in r["contem"]
    assert D.acrescentar_pendente(st, r) is not None
    assert D.acrescentar_pendente(st, r) is None, "a mesma regra não entra duas vezes"
    assert len(D.carregar(st)) == 1
    # pendente não age
    class S:
        def __init__(self, uid, mod, desc):
            self.series_uid, self.modality, self.description = uid, mod, desc
    series = [S("a", "MR", "VIBRANT Ph1"), S("b", "MR", "VIBRANT Ph2")]
    assert D.para_juntar(D.carregar(st), series) == []
    regras = D.carregar(st)
    regras[0]["status"] = "confirmada"
    D.salvar(st, regras)
    assert D.para_juntar(D.carregar(st), series) == [("Mama", ["a", "b"])]


# ------------------------------------------------------------------ no visualizador
def _abre(env, tmp_path, one_series):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=one_series)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.browser.refresh()
    return app, w, uid


def test_a_regra_junta_as_series_ao_abrir(env, tmp_path):
    app, w, uid = _abre(env, tmp_path, one_series=False)
    D.salvar(w.settings, [{"acao": "juntar", "modalidade": "MR", "contem": "dyn fase",
                           "nome": "Mama", "status": "confirmada"}])
    w.open_study(uid)
    app.processEvents()
    tab = w.all_viewer_tabs()[-1]
    grupos = [g for g in tab.groups.values() if g["name"] == "Mama"]
    assert grupos and len(grupos[0]["series_uids"]) == 5
    assert grupos[0]["id"] > 0, "juntar fica guardado no banco"
    assert tab._regras_feitas
    w.close()


def test_a_regra_separa_a_serie_na_tela(env, tmp_path):
    app, w, uid = _abre(env, tmp_path, one_series=True)
    D.salvar(w.settings, [{"acao": "separar", "modalidade": "MR", "contem": "dyn",
                           "nome": "Fases", "status": "confirmada"}])
    w.open_study(uid)
    app.processEvents()
    tab = w.all_viewer_tabs()[-1]
    virtuais = [g for g in tab.groups.values() if g["id"] < 0]
    assert virtuais, "a série com as fases juntas tem de virar fases"
    g = virtuais[0]
    assert len(g["fases"]) == 5 and g.get("split")
    assert tab.repo.series_groups(uid) == [], "nada foi gravado no banco"
    # as fases aparecem na tira; desde a 0.69 a miniatura abre a dinâmica já naquela fase
    # ("uma vez que a série faça parte de um grupo dinâmico, trate-a sempre como dinâmica")
    uids = [tab.strip.item(i).data(0x0100) for i in range(tab.strip.count())]
    assert f"fase:{g['id']}:0" in uids and f"group:{g['id']}" in uids
    vp = tab.viewports[0]
    tab.load_series_into(vp, f"fase:{g['id']}:2")
    app.processEvents()
    assert vp.series_uid == f"group:{g['id']}" and vp.phase == 2 and len(vp.frames) == 3
    tab.load_series_into(vp, f"fase:{g['id']}:2", como_serie=True)
    assert vp.series_uid == f"fase:{g['id']}:2" and "Fase 3" in vp.series_label
    # desfazer devolve a série inteira
    tab.ungroup(g["id"])
    app.processEvents()
    assert all(k > 0 for k in tab.groups)
    assert vp.series_uid == g["series_uids"][0] and len(vp.frames) == 15
    w.close()


def test_separar_na_mao_anota_a_regra(env, tmp_path):
    app, w, uid = _abre(env, tmp_path, one_series=True)
    D.salvar(w.settings, [])
    w.open_study(uid)
    app.processEvents()
    tab = w.all_viewer_tabs()[-1]
    serie = tab.series[0].series_uid
    tab.separar_serie(serie)
    app.processEvents()
    assert any(g["id"] < 0 for g in tab.groups.values())
    regras = D.carregar(w.settings)
    assert regras and regras[0]["acao"] == "separar" and regras[0]["status"] == "pendente"
    w.close()


# ------------------------------------------------------------------ separar por aquisição
def _frames_falsos(blocos):
    """blocos = [(horário, z0, n, passo)] -> quadros com posição e horário."""
    import numpy as np
    from ipe.imaging.series import Frame
    out = []
    i = 0
    for hora, z0, n, passo in blocos:
        for k in range(n):
            i += 1
            f = Frame(path=f"/x/{i}.dcm", sop_uid=f"s{i}", series_uid="S", instance_number=i,
                      frame_index=0)
            f.position = np.array([0.0, 0.0, z0 + k * passo])
            f.orientation = [1, 0, 0, 0, 1, 0]
            f.acquisition_time = hora
            out.append(f)
    return out


def test_separa_a_tc_trifasica_pelo_horario():
    """O caso real do acervo: 142 imagens, dois horários, coberturas diferentes que se sobrepõem."""
    from ipe.imaging.dynamic import separar_fases, split_single_series
    fs = _frames_falsos([("110527.0", -274.0, 52, 5.0), ("110608.9", -464.0, 90, 5.0)])
    assert split_single_series(fs) is None, "não é 'k quadros por posição'; por isso falhava antes"
    fases = separar_fases(fs)
    assert fases and [len(x) for x in fases] == [52, 90]


def test_as_mesas_do_pet_nao_sao_fases():
    """Sete aquisições em sequência, cada uma numa região: é corpo inteiro, não fase."""
    from ipe.imaging.dynamic import separar_fases
    blocos = [(f"1100{i:02d}.0", -400.0 + i * 150.0, 38, 4.0) for i in range(7)]
    assert separar_fases(_frames_falsos(blocos)) is None


def test_um_horario_so_nao_separa():
    from ipe.imaging.dynamic import separar_fases
    assert separar_fases(_frames_falsos([("1100.0", 0.0, 40, 3.0)])) is None


# ------------------------------------------------------------------ ignorar e remover
class _S:
    def __init__(self, uid, mod, desc):
        self.series_uid, self.modality, self.description = uid, mod, desc


def test_ignorada_vale_so_no_exame_onde_nasceu(tmp_path):
    st = Settings(tmp_path / "s.json")
    r = D.sugerir("CT", ["ABDOMEN TRIFASICO"], "separar", "Fases", "EXAME-1", "ACC9 01/02/2026")
    assert r["estudo"] == "EXAME-1" and r["exame"]
    r["status"] = "ignorada"
    D.salvar(st, [r])
    series = [_S("a", "CT", "ABDOMEN TRIFASICO")]
    assert D.para_separar(D.carregar(st), series, "EXAME-1") == ["a"]
    assert D.para_separar(D.carregar(st), series, "OUTRO") == []
    assert D.para_separar(D.carregar(st), series, "") == []


def test_confirmada_vale_em_todo_exame_e_pendente_em_nenhum(tmp_path):
    st = Settings(tmp_path / "s.json")
    r = D.sugerir("CT", ["ABDOMEN TRIFASICO"], "separar", "Fases", "EXAME-1", "x")
    series = [_S("a", "CT", "ABDOMEN TRIFASICO")]
    for status, no_dele, no_outro in (("confirmada", ["a"], ["a"]),
                                      ("pendente", [], []),
                                      ("ignorada", ["a"], [])):
        r["status"] = status
        D.salvar(st, [r])
        assert D.para_separar(D.carregar(st), series, "EXAME-1") == no_dele, status
        assert D.para_separar(D.carregar(st), series, "OUTRO") == no_outro, status


def test_o_exame_aberto_so_aplica_a_regra_ignorada_dele(env, tmp_path):
    app, w, uid = _abre(env, tmp_path, one_series=True)
    D.salvar(w.settings, [{"acao": "separar", "modalidade": "MR", "contem": "dyn",
                           "nome": "Fases", "status": "ignorada", "estudo": "outro-exame",
                           "exame": "x"}])
    w.open_study(uid)
    app.processEvents()
    tab = w.all_viewer_tabs()[-1]
    assert not [g for g in tab.groups.values() if g["id"] < 0], "regra de outro exame não age aqui"
    w.close()


def test_a_tabela_das_preferencias_guarda_ignorar_e_remove(env, tmp_path):
    from ipe.ui.preferences import PreferencesDialog
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    st = Settings(paths.settings_file)
    D.salvar(st, [
        {"acao": "juntar", "modalidade": "MR", "contem": "vibrant", "nome": "Mama",
         "status": "pendente", "estudo": "E1", "exame": "ACC1 10/02/2026"},
        {"acao": "separar", "modalidade": "CT", "contem": "trifasico", "nome": "Fases",
         "status": "confirmada", "estudo": "", "exame": ""}])
    dlg = PreferencesDialog(st)
    assert dlg.din_table.rowCount() == 2
    assert dlg.din_table.item(0, 5).text() == "ACC1 10/02/2026"
    dlg.din_table.setCurrentCell(0, 0)
    dlg._din_ignorar()
    regras = dlg.regras_dinamicas()
    assert regras[0]["status"] == "ignorada" and regras[0]["estudo"] == "E1"
    # remover tira a regra da lista
    dlg.din_table.removeRow(1)
    assert len(dlg.regras_dinamicas()) == 1
    dlg.close()
