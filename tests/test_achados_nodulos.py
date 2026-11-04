"""0.99.46: a base dos achados de IA revisáveis e os nódulos pulmonares (TotalSegmentator lung_nodules).

Fantoma: tórax de 1 mm, pulmão em −850 HU (metade direita e esquerda são "lobos"), três nódulos —
um sólido de 10 mm (45 HU) no pulmão direito, um em vidro fosco de 8 mm (−601 HU) no esquerdo e um
de 2 mm (abaixo do mínimo) — e o simulador do trabalhador marca os nódulos pelo HU.
"""
import math
import time

import numpy as np
import pytest

from ipe.ai import achados as AC
from ipe.ai import nodulos as N
from ipe.imaging.volume import Volume

X = np.arange(-60, 61)
Y = np.arange(-50, 51)
Z = np.arange(60, -1, -1)
NODULOS = (((-30, 0, 30), 5.0, 45), ((30, 10, 25), 4.0, -601), ((-30, -25, 45), 1.0, 45))


def _hu():
    zz, yy, xx = np.meshgrid(Z, Y, X, indexing="ij")
    hu = np.full(xx.shape, 30, np.int16)                                 # parede/mediastino
    pulmao = ((np.abs(xx) > 10) & (np.abs(xx) < 55) & (np.abs(yy) < 40))
    hu[pulmao] = -850
    for (cx, cy, cz), r, v in NODULOS:
        hu[((xx - cx) ** 2 + (yy - cy) ** 2 + (zz - cz) ** 2) <= r * r] = v
    return hu


def _rotulos(hu):
    from ipe.ai import totalseg_worker as W
    out = W._simular(hu, N.tarefas())
    return out


class _T:
    def __init__(self):
        hu = _hu()
        self.vol = Volume(hu, np.array([X[0], Y[0], Z[0]], float), np.array([1.0, 0, 0]),
                          np.array([0, 1.0, 0]), np.array([0, 0, -1.0]), 1.0, 1.0, None, "")
        self.frames = []
        self.series_uid = "1.2.3"
        self.study_uid = "1.2"
        self.descricao_serie = "AX PULMAO 1mm"
        self.versao = "simulado"


def test_numero_e_formatos():
    a = {"rotulo": "N1", "local": "lobo médio", "estado": "sugerido",
         "numeros": {"diametro_mm": AC.numero(6.24, "mm", "Diâmetro maior"),
                     "volume_mm3": AC.numero(98.0, "mm³", "Volume")}, "corrigidos": {}}
    assert AC.resumo_curto(a) == "N1 · lobo médio · 6,2 mm · 98 mm³"
    a["corrigidos"] = {"diametro_mm": 7.0}
    assert AC.numeros_validos(a)["diametro_mm"]["v"] == 7.0
    assert AC.texto_do_laudo([a]) == ""                         # sugerido não vai ao laudo
    a["estado"] = "corrigido"
    assert "7,0 mm" in AC.texto_do_laudo([a])


def test_calcular_candidatos():
    t = _T()
    res = N.calcular(t, _rotulos(t.vol.data))
    assert len(res.candidatos) == 2 and res.descartados_pequenos == 1
    grande, fosco = res.candidatos
    assert grande.rotulo == "N1" and fosco.rotulo == "N2"
    assert grande.lobo == "lung_upper_lobe_right" and fosco.lobo == "lung_upper_lobe_left"
    d = grande.numeros
    assert d["diametro_mm"]["v"] == pytest.approx(11, abs=1.2)
    vol_esf = 4 / 3 * math.pi * 5 ** 3
    assert d["volume_mm3"]["v"] == pytest.approx(vol_esf, rel=0.12)
    assert d["consistencia"]["v"] == "sólido" and d["hu_medio"]["v"] == 45
    assert fosco.numeros["consistencia"]["v"] == "vidro fosco" and fosco.numeros["solido_mm3"]["v"] == 0
    assert np.allclose(grande.centro, (-30, 0, 30), atol=0.6)
    assert not res.avisos                                      # 1 mm: sem aviso de corte grosso


def test_diametro_minimo_configuravel():
    t = _T()

    class S(dict):
        def get(self, k, d=None):
            return super().get(k, d)
    res = N.calcular(t, _rotulos(t.vol.data), S({N.CHAVE_DIAMETRO_MIN: 0.0}))
    assert len(res.candidatos) == 3


def test_corte_grosso_avisa():
    t = _T()
    t.vol.slice_vec = np.array([0, 0, -5.0])
    txt, avisos = N.elegibilidade(t)
    assert "5,0" in avisos[0].replace(".", ",") or "5.0" in avisos[0]
    assert "AX PULMAO" in txt


def test_frase_do_laudo():
    a = {"rotulo": "N1", "local": "lobo inferior direito", "estado": "confirmado", "corrigidos": {},
         "numeros": {"medio_mm": AC.numero(6.2, "mm", "Diâmetro médio"),
                     "volume_mm3": AC.numero(120.0, "mm³", "Volume"),
                     "consistencia": AC.numero("sólido", "", "Consistência")}}
    assert N.frase(a) == "Nódulo sólido no lobo inferior direito, diâmetro médio de 6,2 mm e volume de 120 mm³ (N1)."


def test_conciliar_com_os_revisados():
    from types import SimpleNamespace as NS
    novos = [NS(centro=[0, 0, 0], rotulo="N1", numeros={}), NS(centro=[50, 0, 0], rotulo="N2", numeros={}),
             NS(centro=[0, 0, 30], rotulo="N3", numeros={})]
    revisados = [{"rotulo": "N1", "posicao": [51, 1, 0], "estado": "confirmado"},
                 {"rotulo": "N2", "posicao": [100, 0, 0], "estado": "descartado"}]
    sug, todos = AC.conciliar(novos, revisados)
    assert [c.rotulo for c in todos] == ["N3", "N1", "N4"]
    assert [c.rotulo for c in sug] == ["N3", "N4"]


def test_repositorio_troca_so_os_sugeridos(env):
    paths, db, repo = env
    itens = [{"rotulo": "N1", "tipo": N.TIPO, "posicao": [1, 2, 3], "numeros": {}},
             {"rotulo": "N2", "tipo": N.TIPO, "posicao": [4, 5, 6], "numeros": {}}]
    ids = repo.gravar_achados("ex1", "nodulos", itens)
    repo.revisar_achado(ids[0], "confirmado", "dra. ana")
    with pytest.raises(ValueError):
        repo.revisar_achado(ids[1], "talvez")
    repo.gravar_achados("ex1", "nodulos", [{"rotulo": "N9", "tipo": N.TIPO, "numeros": {}}])
    todos = repo.achados("ex1")
    assert {a["rotulo"] for a in todos} == {"N1", "N9"}
    conf = next(a for a in todos if a["rotulo"] == "N1")
    assert conf["estado"] == "confirmado" and conf["revisor"] == "dra. ana" and conf["revisado_em"]
    assert conf["posicao"] == [1, 2, 3]
    volta = repo.revisar_achado(conf["id"], "sugerido")
    assert volta["revisado_em"] is None


def test_pacote_leva_os_achados_sem_a_lesao(env):
    from ipe.db import pacote as P
    paths, db, repo = env
    from ipe.core.sample_data import make_sample_data
    from ipe.importer.scanner import Importer
    d = paths.storage.parent / "amostra"
    make_sample_data(d)
    Importer(db, paths.storage).import_paths([d])
    uid = repo.find_study_uids(accession="ACC1001")[0]
    ids = repo.gravar_achados(uid, "nodulos", [{"rotulo": "N1", "posicao": [1, 2, 3], "numeros": {}}])
    repo.revisar_achado(ids[0], "confirmado", "x", lesao_id=7)
    p = P.exportar(db, uid)
    assert p["achado_ia"][0]["rotulo"] == "N1" and p["achado_ia"][0]["lesao_id"] is None


# ------------------------------------------------------------------ na tela
def _exame(env, tmp_path):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    hu = _hu()
    pat = {"name": "TORAX^Teste", "id": "NOD1", "birth": "19600101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261104", "accession": "NOD01", "description": "TC TORAX",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 3, "description": "AX PULMAO 1mm"}
    pasta = tmp_path / "nod"
    for k in range(hu.shape[0]):
        ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, series, "CT")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [float(X[0]), float(Y[0]), float(Z[k])]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 1.0
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        _mono(ds, hu[k], signed=True)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    return study["uid"], series["uid"]


def test_tela_nodulos_revisar_e_acompanhar(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, suid = _exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "NOD01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.app_na_barra("nodulos")
        vp = next(v for v in tab.viewports if v.frames)
        tab.nodulos_automatico(vp, simular=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Nódulos pulmonares prontos"), avisos
        assert N.ja_feita(repo, uid)
        ach = repo.achados(uid, "nodulos")
        assert [a["rotulo"] for a in ach] == ["N1", "N2"] and all(a["estado"] == "sugerido" for a in ach)
        assert ach[0]["series_uid"] == suid and "AX PULMAO" in ach[0]["elegibilidade"]
        p = tab.achados_painel
        assert p.isVisible() and p.t.rowCount() == 2
        # nada ao laudo antes de revisar
        assert p.texto_do_laudo() == ""
        p.t.selectRow(0)
        assert p.ir_ate()
        assert abs(vp.patient_to_pixel(np.asarray(ach[0]["posicao"]))[2]) < 1.0
        p.confirmar()
        p.t.selectRow(1)
        p.aplicar_correcao(p.atual(), {"diametro_mm": 9.5, "consistencia": "parcialmente sólido"}, "conferido")
        estados = {a["rotulo"]: a for a in repo.achados(uid)}
        assert estados["N1"]["estado"] == "confirmado" and estados["N2"]["estado"] == "corrigido"
        assert estados["N2"]["corrigidos"]["diametro_mm"] == 9.5
        txt = p.texto_do_laudo()
        assert "N1" in txt and "parcialmente sólido" in txt
        # o confirmado vira lesão acompanhada
        p.escolher(estados["N1"]["id"])
        lid = p.acompanhar()
        assert lid
        le = repo.lesions("NOD1")
        assert le and le[0]["name"] == "N1 (IA)" and le[0]["location"] == "lobo superior direito"
        ligadas = [a for v in tab.viewports for a in v.annotations if (a.meta or {}).get("lesion") == lid]
        assert ligadas and ligadas[0].meta.get("ml") and ligadas[0].meta.get("mm") == pytest.approx(
            estados["N1"]["numeros"]["diametro_mm"]["v"], abs=1.5)
        assert repo.achado(estados["N1"]["id"])["lesao_id"] == lid
        assert not p.b_les.isEnabled()
        # o botão, com achados no exame, abre a lista
        p.close()
        tab.nodulos_botao()
        assert tab.achados_painel.isVisible()
        # rodar de novo mantém o revisado
        avisos.clear()
        tab.nodulos_automatico(vp, simular=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        depois = repo.achados(uid)
        assert len(depois) == 2                              # nenhum volta duplicado
        rot = {a["rotulo"]: a["estado"] for a in depois}
        assert rot == {"N1": "confirmado", "N2": "corrigido"}
    finally:
        w.close()


def test_automatico_na_chegada(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.automation.engine import AutomationEngine
    from ipe.core.config import Settings
    from test_cefalometria import _Rede
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, _s = _exame(env, tmp_path)
    st = Settings(paths.settings_file)
    eng = AutomationEngine(repo, db, _Rede(), st, paths)
    eng._seg_simular = True
    assert eng.ias_genericas(uid) == []
    st.set(N.CHAVE_AUTO, True)
    eng.study_arrived(uid, "received")
    assert N.ja_feita(repo, uid)
    assert len(repo.achados(uid, "nodulos")) == 2
    assert any(r["name"] == N.TITULO and r["status"] == "ok" for r in repo.job_runs())


def test_aba_cad_ia_tem_os_nodulos(env):
    from PySide6.QtWidgets import QApplication

    from ipe.core.config import Settings
    from ipe.ui.cad_ia import CadIaTab
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    st = Settings(paths.settings_file)
    t = CadIaTab(st, repo)
    nomes = [t.l_ferramentas.item(k).text().split("\n")[0] for k in range(t.l_ferramentas.count())]
    assert "Nódulos pulmonares" in nomes
    w = t._gen["nodulos"]
    w["auto"].setChecked(True)
    w["opcoes"][N.CHAVE_DIAMETRO_MIN].setValue(4.0)
    t.save()
    assert st.get(N.CHAVE_AUTO) is True and st.get(N.CHAVE_DIAMETRO_MIN) == 4.0


def test_instalador_baixa_lung_nodules():
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    for nome in ("instalar_segmentacao.sh", "instalar_segmentacao.bat"):
        txt = (raiz / nome).read_text(encoding="utf-8", errors="replace")
        assert "lung_nodules" in txt and " total " in txt
