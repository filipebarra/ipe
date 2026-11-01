"""0.99.14: roteiro de medida guiada — MRPI, MRPI 2.0, Evans e ângulo calosal."""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import roteiros as R
from ipe.imaging.measure import Annotation
from ipe.importer.scanner import Importer


# ------------------------------------------------------------------ as contas
def test_mrpi_e_mrpi2():
    a = R.Andamento(R.MRPI)
    for pid, vals in (("ponte", [600]), ("mesencefalo", [150]), ("pcm", [9, 11]), ("pcs", [4]),
                      ("v3", [6, 7, 8]), ("cornos", [35])):
        p = next(x for x in R.MRPI.passos if x.id == pid)
        for v in vals:
            a.registrar(p, v)
    res = {r.nome: r.valor for r in a.resultados()}
    assert res["Ponte / mesencéfalo"] == pytest.approx(4.0)
    assert res["Pedúnculo cerebelar médio"] == pytest.approx(10.0)          # média dos dois lados
    assert res["MRPI"] == pytest.approx(10.0)
    assert res["3º ventrículo (média)"] == pytest.approx(7.0)
    assert res["MRPI 2.0"] == pytest.approx(2.0)
    assert a.pronto()
    texto = R.texto_do_laudo(a)
    assert "MRPI: 10,00 (referência: acima de 13,55" in texto and "MRPI 2.0: 2,00" in texto


def test_mrpi_sem_os_opcionais_nao_mostra_mrpi2():
    a = R.Andamento(R.MRPI)
    for pid, v in (("ponte", 500), ("mesencefalo", 100), ("pcm", 10), ("pcs", 5)):
        a.registrar(next(x for x in R.MRPI.passos if x.id == pid), v)
    nomes = [r.nome for r in a.resultados()]
    assert a.pronto() and "MRPI" in nomes and "MRPI 2.0" not in nomes
    assert a.proximo().id == "v3"                    # o opcional ainda é oferecido


def test_falta_um_passo_obrigatorio():
    a = R.Andamento(R.MRPI)
    a.registrar(R.MRPI.passos[0], 500)
    assert not a.pronto() and a.proximo().id == "mesencefalo"
    assert next(r for r in a.resultados() if r.nome == "MRPI").valor is None


def test_evans_e_calosal():
    a = R.Andamento(R.EVANS)
    a.registrar(R.EVANS.passos[0], 42)
    a.registrar(R.EVANS.passos[1], 130)
    assert a.resultados()[-1].valor == pytest.approx(42 / 130)
    c = R.Andamento(R.CALOSAL)
    c.registrar(R.CALOSAL.passos[0], 72)
    assert "72 °" in R.texto_do_laudo(c) and "90°" in R.texto_do_laudo(c)


def test_avisos_de_plano_e_espessura():
    p = R.MRPI.passos[0]                              # ponte: sagital
    assert R.avisos_da_medida(p, "Sagital", 1.0) == []
    av = R.avisos_da_medida(p, "Axial", 5.0)
    assert any("plano axial" in x for x in av) and any("5,0" in x or "5.0" in x for x in av)


def test_refazer_tira_a_mais_antiga():
    a = R.Andamento(R.EVANS)
    p = R.EVANS.passos[0]
    a.registrar(p, 40)
    a.registrar(p, 44)                                # limite 1: a nova substitui
    assert a.valores["cornos"] == [44.0]


# ------------------------------------------------------------------ a janela, com medidas de verdade
@pytest.fixture()
def aba(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer import hanging as H
    s = Settings(paths.settings_file)
    s.set("hanging_protocols", [dict(p, enabled=False) for p in H.DEFAULT_PROTOCOLS])
    s.set("hanging_fabrica", H.FABRICA_VERSAO)
    w = MainWindow(paths, s)
    w.resize(1300, 800)
    w.show()
    w.browser.refresh()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"     # TC: axial
    app.processEvents()
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    yield app, w, tab
    w.close()


def _medir(vp, kind, pts):
    ann = Annotation(kind, vp.frame_key(), pts, study_uid=vp.study_uid, series_uid=vp.series_uid, done=False)
    vp.annotations.append(ann)
    vp._finish(ann)
    return ann


def test_painel_captura_as_medidas_e_anda_sozinho(aba):
    app, w, tab = aba
    painel = tab.abrir_roteiro("evans")
    vp = tab.viewports[0]
    assert tab.left_tool == "measure"                  # o passo liga a régua
    sp = vp.measure_spacing() or (1.0, 1.0)
    _medir(vp, "line", [(10, 10), (10 + 40 / sp[1], 10)])          # 40 mm
    assert painel.andamento.valores["cornos"] == [pytest.approx(40.0)]
    assert painel.passo_atual().id == "cranio"        # andou sozinho
    _medir(vp, "line", [(5, 50), (5 + 125 / sp[1], 50)])
    assert painel.andamento.pronto()
    assert "Índice de Evans: 0,32" in painel.texto()
    assert not painel.andamento.avisos.get("cornos")  # TC axial: o plano é o pedido


def test_medida_no_plano_errado_vira_observacao(aba):
    app, w, tab = aba
    painel = tab.abrir_roteiro("mrpi")
    vp = tab.viewports[0]
    assert tab.left_tool == "polygon"
    _medir(vp, "polygon", [(10, 10), (40, 10), (40, 40), (10, 40)])
    assert painel.andamento.feitas(R.MRPI.passos[0]) == 1
    assert any("o roteiro pede sagital" in a for a in painel.andamento.avisos["ponte"])
    assert "Observações" in painel.texto() or not painel.andamento.pronto()
    # medida de outro tipo não é capturada pelo passo de área
    _medir(vp, "line", [(1, 1), (20, 1)])
    assert painel.andamento.feitas(R.MRPI.passos[1]) == 0


def test_aplicacao_indices_aparece_no_cranio():
    from ipe.ui.viewer import aplicacoes as AP
    assert AP.avaliar(AP.APLICACOES["indices"], AP.Contexto({"MR"}, {"cranio"}, set()))[0]
    assert not AP.avaliar(AP.APLICACOES["indices"], AP.Contexto({"MR"}, {"mama"}, set()))[0]


# ------------------------------------------------------------------ 0.99.19: bulbos olfatórios (planimetria)
def test_bulbos_somam_os_cortes_e_trocam_o_mesmo_corte():
    a = R.Andamento(R.BULBOS)
    d, e = R.BULBOS.passos[0], R.BULBOS.passos[1]
    a.registrar(d, 10 * 2.0, chave=("s", 1))
    a.registrar(d, 12 * 2.0, chave=("s", 2))
    a.registrar(d, 15 * 2.0, chave=("s", 1))          # refez o corte 1: troca
    assert a.valores["bulbo_d"] == [30.0, 24.0]
    a.registrar(e, 50.0, chave=("s", 5))
    assert a.pronto() and a.proximo().id == "sulco_d"
    res = {r.nome: r.valor for r in a.resultados()}
    assert res["Volume do bulbo olfatório direito"] == pytest.approx(54.0)
    assert res["Volume dos bulbos olfatórios (soma)"] == pytest.approx(104.0)
    a.registrar(R.BULBOS.passos[2], 6.5)
    t = R.texto_do_laudo(a)
    assert "Volume do bulbo olfatório direito: 54 mm³." in t and "sulco olfatório direito: 6,5 mm" in t
    assert "8 mm" in t


def test_painel_planimetria_area_vezes_distancia(aba):
    app, w, tab = aba
    painel = tab.abrir_roteiro("bulbos")
    vp = tab.viewports[0]
    assert tab.left_tool == "polygon"
    from ipe.ui.viewer.roteiro_painel import distancia_entre_cortes
    dz = distancia_entre_cortes(vp)
    assert dz and dz > 0
    sp = vp.measure_spacing() or (1.0, 1.0)
    lado = 5.0 / sp[1]                                    # quadrado de 5 mm × 5 mm (se o pixel for quadrado)
    _medir(vp, "polygon", [(10, 10), (10 + lado, 10), (10 + lado, 10 + lado), (10, 10 + lado)])
    v1 = painel.andamento.valores["bulbo_d"][0]
    assert v1 == pytest.approx(25.0 * dz * (sp[1] / sp[0]) ** 0, rel=0.1)
    assert painel.passo_atual().id == "bulbo_d"            # continua no mesmo passo (vários cortes)
    vp.go_to(min(vp.index + 1, len(vp.frames) - 1))
    _medir(vp, "polygon", [(10, 10), (10 + lado, 10), (10 + lado, 10 + lado), (10, 10 + lado)])
    assert len(painel.andamento.valores["bulbo_d"]) == 2
    _medir(vp, "polygon", [(10, 10), (10 + 2 * lado, 10), (10 + 2 * lado, 10 + lado), (10, 10 + lado)])
    assert len(painel.andamento.valores["bulbo_d"]) == 2       # o mesmo corte: troca
    assert "mm³ (2 cortes)" in painel.lista.item(0).text()
