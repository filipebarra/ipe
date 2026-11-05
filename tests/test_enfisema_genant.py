"""0.99.77 — enfisema (%LAA−950 por pulmão e lobo) e fratura vertebral pela classificação de Genant."""
import numpy as np
import pytest

from ipe.ai import achados as AC
from ipe.ai import enfisema as EN
from ipe.ai import genant as GE
from ipe.imaging.volume import Volume

PX, N, NZ, DZ = 2.0, 120, 60, 1.0


def _hu(laa_sup_d=0.30, laa_inf=0.02, seed=0):
    """Tórax: corpo (40 HU), dois pulmões (−850 HU) com áreas de −980 HU — no pulmão direito, 30% nos cortes
    de cima e 2% nos de baixo; no esquerdo, 2% em tudo —, e a traqueia (−999 HU) no meio."""
    rng = np.random.default_rng(seed)
    c = (np.arange(N) - N / 2 + 0.5) * PX
    yy, xx = np.meshgrid(c, c, indexing="ij")
    corpo = (xx / 110) ** 2 + (yy / 80) ** 2 <= 1
    pd = ((xx + 50) / 38) ** 2 + (yy / 55) ** 2 <= 1          # i < N/2: direito (como no simulador)
    pe = ((xx - 50) / 38) ** 2 + (yy / 55) ** 2 <= 1
    traq = xx ** 2 + (yy + 30) ** 2 <= 7 ** 2
    hu = np.full((NZ, N, N), -1024, np.int16)
    for k in range(NZ):
        s = hu[k]
        s[corpo] = 40
        s[pd | pe] = -850
        cima = k >= 2 * NZ // 3
        sorteio = rng.random((N, N))
        s[pd & (sorteio < (laa_sup_d if cima else laa_inf))] = -980
        s[pe & (sorteio < laa_inf)] = -980
        s[traq] = -999
    return hu


class _T:
    def __init__(self, hu, desc="TORAX SEM CONTRASTE"):
        o = -(N / 2 - 0.5) * PX
        self.vol = Volume(hu, np.array([o, o, 0.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                          np.array([0, 0, DZ]), PX, PX, None, "")
        self.frames = []
        self.series_uid = "1.2.3"
        self.study_uid = "1.2"
        self.descricao_serie = desc
        self.versao = "simulado"


def _rotulos(hu, tarefas):
    from ipe.ai import totalseg_worker as W
    return W._simular(hu, tarefas)


# ------------------------------------------------------------------ enfisema
def test_enfisema_por_lobo_e_distribuicao():
    hu = _hu()
    t = _T(hu)
    res = EN.calcular(t, _rotulos(hu, EN.tarefas()))
    r = res.regioes
    assert set(r) >= {"LSD", "LM", "LID", "LSE", "LIE", "D", "E", "total"}
    assert r["LSD"]["laa"] == pytest.approx(30, abs=4) and r["LID"]["laa"] == pytest.approx(2, abs=1.5)
    assert r["LSE"]["laa"] == pytest.approx(2, abs=1.5) and r["D"]["laa"] > r["E"]["laa"]
    assert r["total"]["perc15"] <= -850 and r["LSD"]["perc15"] < -950 and r["total"]["vol_ml"] > 100
    assert res.distribuicao == "predomínio nos lobos superiores" and res.razao_sup_inf > 1.5
    assert res.traqueia_hu == pytest.approx(-999, abs=1)
    assert res.laa is not None and res.laa.any() and not any("traqueia" in a for a in res.avisos)
    it = EN.itens_para_o_banco(res, t, "x")[0]
    assert it["tipo"] == EN.TIPO and it["numeros"]["laa_LSD"]["v"] == pytest.approx(r["LSD"]["laa"], abs=0.1)
    f = EN.frase({**it, "estado": "confirmado"})
    assert f.startswith("Áreas de baixa atenuação pulmonar (< −950 HU) em") and "predomínio nos lobos superiores" \
        in f and "LSD" in f and "Perc15" in f
    assert "%LAA−950" in EN.resumo(res)


def test_enfisema_avisos_de_tecnica():
    hu = _hu(laa_sup_d=0.02)
    rot = _rotulos(hu, EN.tarefas())
    hu[hu == -999] = -900                     # ar da traqueia fora do lugar: calibração
    t = _T(hu, desc="TORAX ARTERIAL")
    t.vol = Volume(hu, t.vol.origin, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 2.5]), PX, PX,
                   None, "")
    res = EN.calcular(t, rot)
    txt = " ".join(res.avisos)
    assert "traqueia em -900" in txt.replace("−", "-") and "cortes de 2.5" in txt and "contraste" in txt
    assert EN.filtro_duro("B70f") and EN.filtro_duro("LUNG") and not EN.filtro_duro("B30f")
    assert not EN.filtro_duro("STANDARD")
    vazio = EN.calcular(_T(np.full((NZ, N, N), 40, np.int16)), {})
    assert not vazio.regioes and "não achou os pulmões" in vazio.avisos[0]


# ------------------------------------------------------------------ Genant
def test_genant_graus_e_achados():
    from test_coluna import _coluna_sintetica
    obj = _coluna_sintetica({"T11": (25, 25), "T12": (15, 25), "L1": (25, 25), "L2": (16, 16), "L3": (25, 25),
                             "L4": (25, 25)})
    res = GE.avaliar(obj)
    graus = {m.nome: m.grau for m in res.medidas}
    assert graus["T12"] >= 2 and graus["L2"] == 2 and graus["L1"] == 0
    t = _T(np.zeros((2, 2, 2), np.int16))
    itens = GE.itens_para_o_banco(res, t, "x")
    frat = [i for i in itens if i["tipo"] == GE.TIPO]
    assert [i["rotulo"] for i in frat] == ["T12", "L2"]
    assert frat[0]["numeros"]["forma"]["v"] == "cunha" and frat[1]["numeros"]["forma"]["v"] == "esmagamento"
    resumo = next(i for i in itens if i["tipo"] == GE.TIPO_RESUMO)
    assert resumo["numeros"]["alteradas"]["v"] == 2 and resumo["numeros"]["nivel"]["v"] in ("T12", "L2")
    f = GE.frase({**frat[0], "estado": "confirmado"})
    assert f.startswith("Redução de altura do corpo vertebral de T12 de") and "do tipo cunha" in f and "Genant" in f
    assert GE.frase({**resumo, "estado": "confirmado"}) == ""            # as alteradas têm frase própria
    # já revisada não volta como sugestão
    assert [i["rotulo"] for i in GE.itens_para_o_banco(res, t, "x", {"T12"}) if i["tipo"] == GE.TIPO] == ["L2"]
    normal = GE.avaliar(_coluna_sintetica({"L1": (25, 25), "L2": (25, 25), "L3": (25, 25)}))
    r = next(i for i in GE.itens_para_o_banco(normal, t, "x") if i["tipo"] == GE.TIPO_RESUMO)
    assert "sem redução de altura de 20% ou mais" in GE.frase({**r, "estado": "confirmado"})
    assert "nenhuma com perda" in GE.resumo(normal)


def test_contrato_e_tela(env, tmp_path, monkeypatch):
    from ipe.ai import ferramentas as FE
    for tipo, mod in (("enfisema", EN), ("genant", GE)):
        assert FE.modulo(tipo) is mod
        for nome in ("FERRAMENTA", "TITULO", "MIN_CORTES", "MODALIDADES", "CHAVE_SAIDA", "CHAVE_AUTO",
                     "CHAVE_DESTINOS", "NOME_CADIA", "TITULO_CADIA", "EXPLICACAO_CADIA", "config", "exame_serve",
                     "escolher_serie", "ja_feita", "tarefas", "calcular", "gravar", "resumo", "n_itens",
                     "mensagem", "frase"):
            assert hasattr(mod, nome), (tipo, nome)
    assert [t["nome"] for t in GE.tarefas("CT")] == ["total", "vertebrae_body"]
    assert not GE.tarefas("CT")[0].get("fast")                # resolução cheia para medir altura
    assert [t["nome"] for t in GE.tarefas("MR")] == ["vertebrae_mr", "total_mr"]
    # gravar no banco: o achado do enfisema e a SEG das áreas de baixa atenuação
    paths, db, repo = env
    hu = _hu()
    t = _T(hu)
    res = EN.calcular(t, _rotulos(hu, EN.tarefas()))
    monkeypatch.setattr("ipe.imaging.seg_writer.build_seg", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    t.study_uid = "9.9"
    with pytest.raises(RuntimeError):
        EN.gravar(t, res, "v", db, paths.storage, repo=repo)
    res.laa = None
    out = EN.gravar(t, res, "v", db, paths.storage, repo=repo)
    a = repo.achados("9.9", "enfisema")
    assert len(out["achados"]) == 1 and a[0]["tipo"] == EN.TIPO and a[0]["estado"] == "sugerido"
    assert AC.texto_do_laudo(a, EN.frase) == ""                        # nada vai sozinho ao laudo


def test_tela_enfisema(env, tmp_path, monkeypatch):
    import time

    from pydicom.uid import generate_uid
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    hu = _hu()
    pat = {"name": "TORAX^Enfisema", "id": "ENF1", "birth": "19500101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261105", "accession": "ENF01", "description": "TC TORAX",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 3, "description": "AX PULMAO 1MM"}
    pasta = tmp_path / "enf"
    o = -(N / 2 - 0.5) * PX
    for k in range(NZ):
        ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, series, "CT")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [o, o, DZ * k]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [PX, PX]
        ds.SliceThickness = DZ
        ds.ConvolutionKernel = "B30f"
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        _mono(ds, hu[k], signed=True)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "ENF01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.app_na_barra("enfisema") and "genant.auto" in tab.actions_by_id
        vp = next(v for v in tab.viewports if v.frames)
        tab.ferramenta_ia("enfisema", vp, simular=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Enfisema pronto"), avisos
        assert EN.ja_feita(repo, study["uid"]), [s.description for s in repo.series_for_study(study["uid"])]
        ach = repo.achados(study["uid"], "enfisema")
        assert len(ach) == 1 and ach[0]["numeros"]["laa_LSD"]["v"] > 20
        assert "filtro" not in ach[0]["elegibilidade"].split("Atenção")[-1]          # B30f é suave
        seg = [o for o in tab.overlay_objects if o.source == "SEG" and "Enfisema" in (o.label or "")]
        assert seg and all(o.so_series == series["uid"] for o in seg)
        tab.ferramenta_ia_botao("enfisema")                     # com resultado, abre a revisão
        assert tab.achados_painel.isVisible()
    finally:
        w.close()
