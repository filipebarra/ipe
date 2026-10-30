"""Memória do layout: o exame abre como ele deixou da última vez, sem configurar nada.

Pedido dele: "quando eu abrir uma ressonância de ombro, eu vou ajustar o layout e quando fechar
o sistema vai memorizar o layout. pode ficar interno, eu nao preciso saber nem configurar nada".
"""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.ui.viewer import memoria_layout as ML


# --------------------------------------------------------------------- a etiqueta

def test_a_etiqueta_junta_o_que_e_o_mesmo_exame():
    """Lado, contraste e número não fazem um exame ser outro tipo de exame."""
    a = ML.chave({"MR"}, "RM OMBRO DIREITO")
    assert a == "MR|RM OMBRO"
    assert ML.chave({"MR"}, "RM Ombro esquerdo") == a
    assert ML.chave({"MR"}, "RM ombro direito c/ contraste") == a
    assert ML.chave({"MR"}, "RM OMBRO 3") == a
    assert ML.chave({"MR"}, "RM OMBRÔ") == a                   # acento não separa


def test_a_etiqueta_separa_o_que_e_diferente():
    assert ML.chave({"MR"}, "RM OMBRO") != ML.chave({"MR"}, "RM JOELHO")
    assert ML.chave({"MR"}, "RM OMBRO") != ML.chave({"CT"}, "TC OMBRO")
    assert ML.chave({"CT", "PT"}, "PET-CT") != ML.chave({"CT"}, "PET-CT")


def test_etiqueta_sem_descricao_nao_quebra():
    assert ML.chave({"MR"}, "") == "MR|"
    assert ML.chave(set(), None) == "|"


# --------------------------------------------------------------------- guardar e ler

def test_guarda_e_devolve(tmp_path):
    st = Settings(tmp_path / "s.json")
    assert ML.lembrado(st, "MR|OMBRO") is None
    assert ML.lembrar(st, "MR|OMBRO", (2, 2))
    assert ML.lembrado(st, "MR|OMBRO") == (2, 2)
    assert not ML.lembrar(st, "MR|OMBRO", (2, 2))              # igual: não é mudança
    assert ML.lembrar(st, "MR|OMBRO", (1, 3))
    assert ML.lembrado(st, "MR|OMBRO") == (1, 3)


def test_recusa_o_que_nao_e_layout(tmp_path):
    st = Settings(tmp_path / "s.json")
    assert not ML.lembrar(st, "MR|X", (0, 2))
    assert not ML.lembrar(st, "MR|X", (9, 9))
    assert not ML.lembrar(st, "", (2, 2))
    assert not ML.lembrar(st, "MR|X", None)
    st.set(ML.CHAVE, {"MR|X": "2x2"})                          # lixo no arquivo não derruba
    assert ML.lembrado(st, "MR|X") is None


def test_nao_cresce_para_sempre(tmp_path):
    st = Settings(tmp_path / "s.json")
    for i in range(ML.MAX + 25):
        ML.lembrar(st, f"MR|EXAME{i}", (1, 2))
    guardados = st.get(ML.CHAVE)
    assert len(guardados) == ML.MAX
    assert "MR|EXAME0" not in guardados and f"MR|EXAME{ML.MAX + 24}" in guardados


def test_esquecer(tmp_path):
    st = Settings(tmp_path / "s.json")
    ML.lembrar(st, "MR|OMBRO", (2, 2))
    ML.esquecer(st, "MR|OMBRO")
    assert ML.lembrado(st, "MR|OMBRO") is None
    ML.lembrar(st, "MR|A", (2, 2))
    ML.esquecer(st)
    assert st.get(ML.CHAVE) == {}


# --------------------------------------------------------------------- no programa

@pytest.fixture()
def janela(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer import hanging as H
    s = Settings(paths.settings_file)
    # a memória vale onde nenhum protocolo vale: só a RM de mama fica com protocolo (desde a 0.88 a
    # TC de tórax também tem um de fábrica, e com ele a memória nem entra)
    s.set("hanging_protocols", [p for p in H.DEFAULT_PROTOCOLS if p["name"] == "RM de mama"])
    s.set("hanging_fabrica", H.FABRICA_VERSAO)
    s.save()
    w = MainWindow(paths, s)
    w.show()
    w.browser.refresh()
    yield app, w
    w.close()


def _abrir_tc(app, w):
    """Uma TC de tórax: nenhum protocolo de fábrica combina com ela, então a memória é quem vale."""
    uid = next(r.study_uid for r in w.repo.search_studies()
               if (w.repo.study_info(r.study_uid) or {}).get("modalities", "") == "CT")
    w.open_study(uid)
    app.processEvents()
    return uid, w.all_viewer_tabs()[-1]


def test_o_ciclo_inteiro(janela):
    """Abre, ajusta, fecha, abre de novo: tem de voltar como ele deixou."""
    app, w = janela
    uid, tab = _abrir_tc(app, w)
    etiqueta = tab.etiqueta_do_layout()
    assert etiqueta and etiqueta.startswith("CT|")
    assert tab.layout_lembrado() is None                        # primeira vez: não sabe nada
    tab.set_layout(2, 3)
    w.fechar_aba(tab)
    app.processEvents()
    assert ML.lembrado(w.settings, etiqueta) == (2, 3), "não guardou ao fechar"
    _uid2, tab2 = _abrir_tc(app, w)
    app.processEvents()
    assert tab2._layout == (2, 3), "não abriu com o layout lembrado"


def test_mamografia_fica_de_fora(janela):
    """Mamografia tem etapas próprias; duas coisas decidindo o mesmo arranjo é uma a mais."""
    app, w = janela
    uid = next(r.study_uid for r in w.repo.search_studies()
               if (w.repo.study_info(r.study_uid) or {}).get("modalities", "") == "MG")
    w.open_study(uid)
    app.processEvents()
    tab = w.all_viewer_tabs()[-1]
    assert tab.etiqueta_do_layout() == ""
    tab.set_layout(1, 1)
    w.fechar_aba(tab)
    app.processEvents()
    assert w.settings.get(ML.CHAVE, {}) == {}


def test_um_exame_nao_ensina_o_outro(janela):
    app, w = janela
    uid, tab = _abrir_tc(app, w)
    etiqueta = tab.etiqueta_do_layout()
    tab.set_layout(2, 2)
    w.fechar_aba(tab)
    app.processEvents()
    outro = next(r.study_uid for r in w.repo.search_studies()
                 if (w.repo.study_info(r.study_uid) or {}).get("modalities", "") == "US")
    w.open_study(outro)
    app.processEvents()
    tab2 = w.all_viewer_tabs()[-1]
    assert tab2.etiqueta_do_layout() != etiqueta
    assert tab2.layout_lembrado() is None


def test_o_protocolo_escrito_manda_sobre_a_memoria(janela):
    """Escolha explícita ganha de hábito observado — e nem grava, para não juntar lixo."""
    app, w = janela
    uid = next(r.study_uid for r in w.repo.search_studies()
               if "MAMA" in (w.repo.study_info(r.study_uid) or {}).get("description", "").upper()
               and "MR" in (w.repo.study_info(r.study_uid) or {}).get("modalities", ""))
    w.open_study(uid)                       # a RM de mama tem protocolo de fábrica
    app.processEvents()
    tab = w.all_viewer_tabs()[-1]
    assert tab._layout == (2, 2)
    assert tab.etiqueta_do_layout() == "", "exame com protocolo não entra na memória"
    tab.set_layout(1, 1)
    w.fechar_aba(tab)
    app.processEvents()
    assert w.settings.get(ML.CHAVE, {}) == {}
    w.open_study(uid)
    app.processEvents()
    assert w.all_viewer_tabs()[-1]._layout == (2, 2), "o protocolo deixou de mandar"


def test_sair_do_programa_tambem_guarda(janela):
    """O X do programa é tão “fechar o exame” quanto o X da aba."""
    app, w = janela
    uid, tab = _abrir_tc(app, w)
    etiqueta = tab.etiqueta_do_layout()
    tab.set_layout(1, 3)
    w._really_quit = True
    w.close()
    app.processEvents()
    assert ML.lembrado(w.settings, etiqueta) == (1, 3)


# ---------------------------------------------------------------- vários monitores (0.61)
def test_cada_tela_tem_a_sua_memoria():
    """Com duas telas o arranjo de uma não serve para a outra: ele põe sagitais numa e axiais
    noutra. E a memória de uma tela só não serve para quando ele abre em três."""
    assert ML.sufixo_das_telas(1, 0) == ""
    assert ML.sufixo_das_telas(2, 0) == "|2t1"
    assert ML.sufixo_das_telas(2, 1) == "|2t2"
    assert ML.sufixo_das_telas(3, 2) == "|3t3"
    assert ML.sufixo_das_telas(2, 9) == "|2t2"          # índice fora da conta não inventa tela
    assert ML.sufixo_das_telas(0, 0) == "" and ML.sufixo_das_telas(None, None) == ""


def test_memoria_de_duas_telas_nao_atropela_a_de_uma(tmp_path):
    s = Settings(tmp_path / "settings.json")
    base = ML.chave({"MR"}, "RM OMBRO DIREITO")
    ML.lembrar(s, base, (1, 1))
    ML.lembrar(s, base + ML.sufixo_das_telas(2, 0), (2, 2))
    ML.lembrar(s, base + ML.sufixo_das_telas(2, 1), (1, 3))
    assert ML.lembrado(s, base) == (1, 1)
    assert ML.lembrado(s, base + ML.sufixo_das_telas(2, 0)) == (2, 2)
    assert ML.lembrado(s, base + ML.sufixo_das_telas(2, 1)) == (1, 3)
    assert ML.lembrado(s, base + ML.sufixo_das_telas(3, 0)) is None
