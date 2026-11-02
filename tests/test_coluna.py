"""0.99.2: níveis da coluna — vértebras e discos com nome, visíveis em qualquer corte.

Pedido dele: identificar automaticamente os discos em TC e RM, para "ler e laudar: ver o nível em
qualquer corte". O trabalhador roda no modo simular: o fantoma tem faixas de osso (300) e de disco
(150) ao longo do eixo; as faixas de osso viram L1, L2… de cima para baixo.
"""
import time

import numpy as np
import pydicom
import pytest
from pydicom.uid import generate_uid

from ipe.ai import coluna as COL
from ipe.ai import totalseg as TS
from ipe.core.sample_data import _base, _mono, _save
from ipe.importer.scanner import Importer

NZ, NY, NX = 64, 40, 48
DZ = 2.0


def _fantoma():
    vol = np.zeros((NZ, NY, NX), np.int16)
    faixas, discos = [], []
    k = 2
    for n in range(6):                                  # L1…L5 e S1
        vol[k:k + 7, 10:30, 14:34] = 300
        faixas.append((k, k + 7))
        k += 7
        if n < 5:
            vol[k:k + 3, 12:28, 16:32] = 150
            discos.append((k, k + 3))
            k += 3
    return vol, faixas, discos


def _exame(env, tmp_path, descricao="TC COLUNA LOMBAR", serie="AX OSSO"):
    paths, db, repo = env
    vol, _f, _d = _fantoma()
    pat = {"name": "COLUNA^Teste", "id": "COL1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261026", "accession": "COL01", "description": descricao,
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 2, "description": serie}
    pasta = tmp_path / "coluna"
    for k in range(NZ):
        ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, series, "CT")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [-24.0, -20.0, 100.0 - k * DZ]          # de cima para baixo
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = DZ
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        _mono(ds, vol[k], signed=True)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    return study["uid"], series["uid"]


def _trabalho(env, uid, serie):
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    t = TS.Trabalho(repo, FrameCache(128), None, uid, serie, simular=True)
    t.tarefas_proprias, t.min_cortes = COL.tarefas, COL.MIN_CORTES
    t.preparar()
    t.rodar_aqui()
    return t


@pytest.fixture()
def medir(monkeypatch):
    """0.99.7: as medidas foram desligadas (só nomeia); os testes delas ligam de propósito."""
    monkeypatch.setattr(COL, "MEDIR_DISPONIVEL", True)
    monkeypatch.setitem(COL.PADROES, COL.CHAVE_MEDIR, True)


# ------------------------------------------------------------------ regras
def test_deslocar_e_nomes():
    assert COL.deslocar("L4", 1) == "L5" and COL.deslocar("L5", 1) == "S1" and COL.deslocar("S1", 1) == "S2"
    assert COL.deslocar("L4-L5", 1) == "L5-S1" and COL.deslocar("T12-L1", -1) == "T11-T12"
    assert COL.nome_da_vertebra("vertebrae_L4") == "L4" and COL.nome_da_vertebra("sacrum") == "S1"
    assert COL.nome_da_vertebra("liver") is None
    assert [t["nome"] for t in COL.tarefas("CT")] == ["total", "vertebrae_body"]
    assert [t["nome"] for t in COL.tarefas("MR")] == ["vertebrae_mr", "total_mr"]


def test_avisos_da_contagem():
    assert any("lombares" in a for a in COL.avisos(["T12", "L1", "L2", "L3", "L4", "S1"]))
    assert any("faltou L3" in a for a in COL.avisos(["L1", "L2", "L4", "L5", "S1"]))
    assert any("ancorar" in a for a in COL.avisos(["T5", "T6", "T7"]))
    assert COL.avisos(["L1", "L2", "L3", "L4", "L5", "S1"]) == []


# ------------------------------------------------------------------ nomes na grade
def test_nomeia_vertebras_e_discos(env, tmp_path):
    uid, serie = _exame(env, tmp_path)
    t = _trabalho(env, uid, serie)
    try:
        rotulos, _v, _s = t.ler_rotulos()
        niveis = COL.nomear(t.vol, rotulos)
        assert niveis.nomes("vertebra") == ["L1", "L2", "L3", "L4", "L5", "S1"]
        assert niveis.nomes("disco") == ["L1-L2", "L2-L3", "L3-L4", "L4-L5", "L5-S1"]
        assert niveis.avisos == []
        _vol, faixas, discos = _fantoma()
        # o volume vem empilhado pela posição (de baixo para cima): o corte k do arquivo é NZ-1-k nele
        d = next(n for n in niveis.itens if n.nome == "L4-L5")
        assert d.offset[0] == NZ - discos[3][1] and d.mascara.shape[0] == 3       # o disco certo, inteiro
        v = next(n for n in niveis.itens if n.nome == "L4")
        assert v.offset[0] == NZ - faixas[3][1] and v.voxels == 7 * 20 * 20
    finally:
        t.limpar()


def test_seg_volta_com_os_nomes_em_qualquer_plano(env, tmp_path):
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    t = _trabalho(env, uid, serie)
    try:
        rotulos, versao, _s = t.ler_rotulos()
        niveis = COL.nomear(t.vol, rotulos)
        saida = COL.gravar(t, niveis, versao, db, paths.storage)
        assert saida["seg_path"] and TS.series_locais(repo, uid)            # local, como as outras
        obj = COL.objeto_do_seg(saida["seg_path"], uid)
        assert obj.source == "Coluna" and all(mv.so_rotulo for mv in obj.volumes)
        assert [mv.label for mv in obj.volumes][:3] == ["L1", "L1-L2", "L2"]
        _vol, _f, discos = _fantoma()
        # axial no meio do disco L4-L5: só ele (e nenhuma vértebra) é cortado
        k = discos[3][0] + 1
        pos = np.array([-24.0, -20.0, 100.0 - k * DZ])
        ax = [mv.label for mv in obj.volumes
              if mv.fatia(pos, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]),
                          (1.0, 1.0), (NY, NX)) is not None]
        assert ax == ["L4-L5"]
        # sagital no meio: todos os níveis aparecem
        pos_s = np.array([0.0, -20.0, 100.0])
        sag = [mv.label for mv in obj.volumes
               if mv.fatia(pos_s, np.array([0, 1.0, 0]), np.array([0, 0, -1.0]), np.array([1.0, 0, 0]),
                           (DZ, 1.0), (NZ, NY)) is not None]
        assert len(sag) == 11
    finally:
        t.limpar()


# ------------------------------------------------------------------ tela: identificar e renumerar
def test_tela_identifica_e_renumera(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1200, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "COL01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        vp = next(v for v in tab.viewports if v.frames)
        menu = [a.text() for a in vp.build_context_menu().actions()]
        assert any(t.startswith("Identificar vértebras e discos") for t in menu)
        assert not any(t.startswith("Numeração da coluna") for t in menu)  # ainda não há níveis
        assert any(a.text().startswith("Identificar vértebras") and a.isEnabled()
                   for a in w.browser.series_menu(uid, [serie]).actions())
        tab.segmentar_orgaos(vp, simular=True, tipo="coluna")
        fim = time.time() + 60
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Níveis identificados"), avisos
        col = [o for o in tab.overlay_objects if o.source == "Coluna"]
        assert len(col) == 1 and "L4-L5" in [mv.label for mv in col[0].volumes]
        menu = [a.text() for a in vp.build_context_menu().actions()]
        assert any(t.startswith("Numeração da coluna") for t in menu)
        assert tab.renumerar_coluna(vp, 1) == 1
        assert "L5-S1" in [mv.label for mv in col[0].volumes] and "L1" not in [mv.label for mv in col[0].volumes]
        # guardado no SEG: relido, já vem renumerado
        relido = COL.objeto_do_seg(col[0].caminho, uid)
        assert [mv.label for mv in relido.volumes][:2] == ["L2", "L2-L3"]
    finally:
        w.close()


# ------------------------------------------------------------------ automático na chegada
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
        self.envios.append((node["name"], list(series_uids or [])))


def test_automatico_na_chegada_so_quando_ligado(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.automation.engine import AutomationEngine
    from ipe.core.config import Settings
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, _serie = _exame(env, tmp_path)
    st = Settings(paths.settings_file)
    rede = _Rede()
    eng = AutomationEngine(repo, db, rede, st, paths)
    eng._seg_simular = True
    assert not eng.segmentar_coluna(uid)                   # desligado (padrão)
    st.set(COL.CHAVE_AUTO, True)
    no = repo.save_node({"name": "PACS-COL", "kind": "dimse", "ae_title": "P", "host": "127.0.0.1",
                         "port": 104, "active": True, "use_in_send": True})
    st.set(COL.CHAVE_DESTINOS, [no])
    prontos = []
    eng.segmentacao_pronta.connect(lambda u, s: prontos.append(s))
    st.set(TS.CHAVE_AUTO, True)                            # o abdome ligado não pega exame de coluna
    eng.study_arrived(uid, "received")
    assert COL.ja_identificado(repo, uid) and not TS.ja_segmentado(repo, uid)
    assert prontos and prontos[0].get("niveis") is not None
    assert len(rede.envios) == 1 and rede.envios[0][0] == "PACS-COL"
    assert any(r["kind"] == "segmentacao" and r["name"] == "Níveis da coluna" and r["status"] == "ok"
               for r in repo.job_runs())
    assert not eng.segmentar_coluna(uid)                   # já feito: não refaz


def test_aba_cad_ia_tem_a_coluna(env):
    from PySide6.QtWidgets import QApplication, QWidget

    from ipe.core.config import Settings
    from ipe.ui.preferences import PreferencesDialog
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    pai = QWidget()
    pai.repo = repo
    st = Settings(paths.settings_file)
    d = PreferencesDialog(st, pai)
    c = d.cad_ia
    assert [c.l_ferramentas.item(k).text().split("\n")[0] for k in range(3)] == \
        ["Segmentação abdominal", "Níveis da coluna", "Implante de silicone"]
    c.c_col_auto.setChecked(True)
    assert "automático" in c.l_ferramentas.item(1).text()
    c.e_col_mr.setText("SAG T2|SAG")
    c.save()
    assert st.get(COL.CHAVE_AUTO) is True and st.get(COL.CHAVE_PRIOR_MR) == "SAG T2|SAG"


def test_instalador_baixa_os_modelos_da_coluna():
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    for arq in ("instalar_segmentacao.bat", "instalar_segmentacao.sh"):
        texto = (raiz / arq).read_text(encoding="utf-8")
        assert "vertebrae_mr" in texto and "vertebrae_body" in texto, arq


# ------------------------------------------------------------------ 0.99.3: medir os discos
def test_disco_em_cunha_altura_anterior_media_posterior(medir):
    from types import SimpleNamespace

    from ipe.imaging import overlays as O
    M = np.diag([1.0, 1.0, -1.0])                       # i → x, j → y (posterior), k → −z (para baixo)

    def mv(m, lab, org):
        return O.MaskVolume(m, np.array(org, float), M, (255, 255, 0), lab)
    disco = np.zeros((13, 20, 20), bool)
    for j in range(20):                                  # anterior (j = 0) 12 mm, posterior 6 mm
        disco[:int(round(12 - 6 * j / 19)), j, :] = True
    obj = SimpleNamespace(volumes=[mv(np.ones((10, 20, 20), bool), "L4", (0, 0, 0)),
                                   mv(disco, "L4-L5", (0, 0, -10)),
                                   mv(np.ones((10, 20, 20), bool), "L5", (0, 0, -23))])
    (m,) = COL.medir_discos(obj)
    assert m.anterior == pytest.approx(12, abs=1) and m.media == pytest.approx(9, abs=1)
    assert m.posterior == pytest.approx(7, abs=1) and m.anterior > m.media > m.posterior
    assert m.volume_ml == pytest.approx(disco.sum() / 1000)
    assert m.profundidade == pytest.approx(20, abs=1)
    # sem as vértebras vizinhas: só o volume
    (s,) = COL.medir_discos(SimpleNamespace(volumes=[mv(disco, "L4-L5", (0, 0, -10))]))
    assert s.media is None and "só o volume" in s.nota


def test_tarefas_da_rm_para_medir_usam_o_modelo_de_15_mm(env, medir):
    from ipe.core.config import Settings
    paths, _db, _repo = env
    st = Settings(paths.settings_file)
    assert COL.tarefas("MR", st)[1] == {"nome": "total_mr", "rotulo": "discos (1,5 mm)"}
    st.set(COL.CHAVE_MEDIR, False)
    assert COL.tarefas("MR", st)[1]["roi"] == ["intervertebral_discs"]
    assert [t["nome"] for t in COL.tarefas("CT", st)] == ["total", "vertebrae_body"]


def test_mede_os_discos_do_fantoma_e_grava_a_tabela(env, tmp_path, medir):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    t = _trabalho(env, uid, serie)
    try:
        rotulos, versao, _s = t.ler_rotulos()
        saida = COL.gravar(t, COL.nomear(t.vol, rotulos), versao, db, paths.storage)
        tab = COL.gravar_tabela(repo, db, paths.storage, uid, saida["seg_path"])
        med = {m.nome: m for m in tab["medidas"]}
        assert list(med) == ["L1-L2", "L2-L3", "L3-L4", "L4-L5", "L5-S1"]
        for m in med.values():                           # 3 cortes de 2 mm; 16 × 16 mm
            assert m.media == pytest.approx(6.0) and m.anterior == pytest.approx(6.0)
            assert m.volume_ml == pytest.approx(3 * 16 * 16 * 2 / 1000)
        assert med["L2-L3"].vs_acima == pytest.approx(100)
        tabelas = [s for s in repo.series_for_study(uid) if s.description == COL.DESC_TABELA]
        assert len(tabelas) == 1 and tabelas[0].series_uid in TS.series_locais(repo, uid)
        img = pydicom.dcmread(repo.instances_for_series(tabelas[0].series_uid)[0]["path"])
        assert img.BurnedInAnnotation == "YES" and img.pixel_array.std() > 10
    finally:
        t.limpar()


def test_renumerar_refaz_a_tabela(env, tmp_path, monkeypatch, medir):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.show()
    try:
        assert w.handle_external({"accession": "COL01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        vp = next(v for v in tab.viewports if v.frames)
        tab.segmentar_orgaos(vp, simular=True, tipo="coluna")
        fim = time.time() + 60
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert "Medidas: 5 discos medidos" in avisos[-1], avisos
        col = next(o for o in tab.overlay_objects if o.source == "Coluna")
        assert any(f.startswith("📏 L4-L5: altura 6,0 mm") for f in col.findings)
        antes = [s.series_uid for s in repo.series_for_study(uid) if s.description == COL.DESC_TABELA]
        tab.renumerar_coluna(vp, 1)
        depois = [s.series_uid for s in repo.series_for_study(uid) if s.description == COL.DESC_TABELA]
        assert len(antes) == len(depois) == 1 and antes != depois       # a tabela velha saiu, a nova entrou
        assert any(f.startswith("📏 L5-S1: altura 6,0 mm") for f in col.findings)
        assert not any(f.startswith("📏 L1-L2") for f in col.findings)
    finally:
        w.close()


# ------------------------------------------------------------------ 0.99.4: medir as vértebras
def _coluna_sintetica(alturas: dict):
    """Vértebras com corpo (30 mm de fundo), canal (12 mm) e arco posterior, e discos de 8 mm entre elas.
    `alturas`: {nome: (anterior, posterior)} em mm; o meio fica na média das duas."""
    from types import SimpleNamespace

    from ipe.imaging import overlays as O
    M = np.diag([1.0, 1.0, -1.0])                       # i → x, j → y (posterior), k → −z (para baixo)
    vols, z = [], 0.0
    nomes = list(alturas)
    for n, nome in enumerate(nomes):
        ha, hp = alturas[nome]
        alt = int(max(ha, hp))
        m = np.zeros((alt, 60, 20), bool)
        for j in range(30):                              # corpo: altura da frente (j=0) para trás (j=29)
            h = int(round(ha + (hp - ha) * j / 29))
            m[(alt - h) // 2:(alt - h) // 2 + h, j, :] = True
        m[alt // 2 - 6:alt // 2 + 6, 42:56, 7:13] = True  # arco posterior, depois do canal
        vols.append(O.MaskVolume(m, np.array([0.0, 0.0, -z]), M, (0, 0, 255), nome))
        z += alt
        if n + 1 < len(nomes):
            d = np.ones((8, 30, 20), bool)
            vols.append(O.MaskVolume(d, np.array([0.0, 0.0, -z]), M, (255, 255, 0), f"{nome}-{nomes[n + 1]}"))
            z += 8
    return SimpleNamespace(volumes=vols, findings=[])


def test_vertebra_em_cunha_e_esmagada(medir):
    obj = _coluna_sintetica({"T11": (25, 25), "T12": (15, 25), "L1": (25, 25), "L2": (16, 16), "L3": (25, 25)})
    med = {m.nome: m for m in COL.medir_vertebras(obj)}
    assert list(med) == ["T11", "T12", "L1", "L2", "L3"]
    n = med["L1"]
    assert n.anterior == pytest.approx(25, abs=1) and n.posterior == pytest.approx(25, abs=1)
    assert n.profundidade == pytest.approx(30, abs=1.5) and n.grau == 0
    c = med["T12"]                                      # cunha: frente 15, atrás 25 → ~40%
    assert c.forma == "cunha" and c.anterior < c.media < c.posterior
    assert 33 <= c.perda <= 45 and c.grau >= 2
    e = med["L2"]                                       # esmagamento: 16 contra 25 das vizinhas → ~36%
    assert e.forma == "esmagamento" and e.grau == 2 and 30 <= e.perda <= 40
    assert "T12" in COL.resumo_vertebras(list(med.values()))
    COL.anexar_medidas(obj)
    assert any(f.startswith("📏 T12: corpo") and "cunha" in f for f in obj.findings)
    assert any(f.startswith("📏 T12-L1") for f in obj.findings)


def test_vertebra_sem_canal_nao_inventa_corpo(medir):
    from types import SimpleNamespace

    from ipe.imaging import overlays as O
    M = np.diag([1.0, 1.0, -1.0])
    bloco = O.MaskVolume(np.ones((20, 40, 20), bool), np.zeros(3), M, (0, 0, 255), "L3")
    vizinha = O.MaskVolume(np.ones((20, 40, 20), bool), np.array([0.0, 0.0, -30.0]), M, (0, 0, 255), "L4")
    (m, _) = COL.medir_vertebras(SimpleNamespace(volumes=[bloco, vizinha]))
    assert m.anterior is None and "arco posterior" in m.nota


def test_tabela_das_vertebras_no_exame(env, tmp_path, medir):
    """A tabela das vértebras sai junto com a dos discos (o fantoma não tem canal: a tabela diz por quê)."""
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    obj = _coluna_sintetica({"T12": (25, 25), "L1": (14, 25), "L2": (25, 25)})
    cab = {"paciente": "TESTE", "id": "1", "data": "26/10/2026", "serie": "SAG T2", "modalidade": "MR"}
    rgb = COL.desenhar_tabela_vertebras(COL.medir_vertebras(obj), cab, COL.resolucao_mm(obj), [])
    assert rgb.shape[1] == 1600 and rgb.std() > 10
    uid, serie = _exame(env, tmp_path)
    t = _trabalho(env, uid, serie)
    try:
        rotulos, versao, _s = t.ler_rotulos()
        saida = COL.gravar(t, COL.nomear(t.vol, rotulos), versao, db, paths.storage)
        tab = COL.gravar_tabela(repo, db, paths.storage, uid, saida["seg_path"])
        descr = [s.description for s in repo.series_for_study(uid)]
        assert COL.DESC_TABELA_VERT in descr and COL.DESC_TABELA in descr and len(tab["series"]) == 2
        assert COL.tem_tabela(repo, uid)
        COL.gravar_tabela(repo, db, paths.storage, uid, saida["seg_path"])     # refazer troca, não duplica
        descr = [s.description for s in repo.series_for_study(uid)]
        assert descr.count(COL.DESC_TABELA_VERT) == 1 and descr.count(COL.DESC_TABELA) == 1
    finally:
        t.limpar()


def test_serie_coronal_e_vertebra_cortada_nao_medem(medir):
    obj = _coluna_sintetica({"L1": (25, 25), "L2": (25, 25), "L3": (25, 25)})
    obj.volumes[0].cortada = True                         # a série pegou só um pedaço de L1
    med = {m.nome: m for m in COL.medir_vertebras(obj)}
    assert med["L1"].anterior is None and "borda" in med["L1"].nota and med["L2"].anterior is not None
    for mv in obj.volumes:                                # coronal: 5,5 mm por voxel no ântero-posterior
        mv.matriz = np.diag([1.0, 5.5, -1.0])
        mv._inv = np.linalg.inv(mv.matriz)
    assert "sagital" in COL.aviso_da_serie(obj)
    assert all(m.anterior is None for m in COL.medir_vertebras(obj))
    assert all(m.media is None and m.volume_ml > 0 for m in COL.medir_discos(obj))
    assert COL._cortada((40, 100, 100), (0, 10, 10), (10, 20, 20), np.diag([1.0, 1.0, -2.0]))
    assert not COL._cortada((40, 100, 100), (5, 10, 10), (10, 20, 20), np.diag([1.0, 1.0, -2.0]))


# ------------------------------------------------------------------ 0.99.5: medida robusta e duas sagitais
def _com_pedaco_solto(obj, nome, desloc_mm):
    """Junta à máscara de `nome` um pedaço solto `desloc_mm` abaixo (o que a IA às vezes faz)."""
    from ipe.imaging import overlays as O
    mv = next(v for v in obj.volumes if v.label == nome)
    k, j, i = mv.mascara.shape
    extra = int(desloc_mm) + 4
    nova = np.zeros((k + extra, j, i), bool)
    nova[:k] = mv.mascara
    nova[k + extra - 4:, 0:30, 5:15] = True                  # 4 mm de "osso" solto, longe do corpo
    idx = next(n for n, v in enumerate(obj.volumes) if v is mv)
    obj.volumes[idx] = O.MaskVolume(nova, mv.origem, mv.matriz, mv.color, nome)
    return obj


def test_pedaco_solto_e_buraco_nao_mudam_a_altura(medir):
    obj = _com_pedaco_solto(_coluna_sintetica({"L1": (25, 25), "L2": (25, 25), "L3": (25, 25)}), "L2", 30)
    mv = next(v for v in obj.volumes if v.label == "L2")
    mv.mascara[10:18, 0:4, :] = False                         # buraco de 8 mm dentro do corpo, na frente
    med = {m.nome: m for m in COL.medir_vertebras(obj)}
    assert med["L2"].anterior == pytest.approx(25, abs=1.5) and med["L2"].media == pytest.approx(25, abs=1)
    assert not med["L2"].duvidosa and med["L2"].perda < 10


def test_nome_que_pegou_duas_vertebras_fica_duvidoso(medir):
    from types import SimpleNamespace

    from ipe.imaging import overlays as O
    obj = _coluna_sintetica({"L1": (25, 25), "L2": (25, 25), "L3": (25, 25)})
    l2 = next(v for v in obj.volumes if v.label == "L2")
    dupla = np.concatenate([l2.mascara, l2.mascara])            # dois corpos colados (o disco não saiu)
    idx = next(n for n, v in enumerate(obj.volumes) if v is l2)
    obj.volumes[idx] = O.MaskVolume(dupla, l2.origem, l2.matriz, l2.color, "L2")
    m = next(x for x in COL.medir_vertebras(obj) if x.nome == "L2")
    assert m.duvidosa and "duvidosa" in m.nota and m.grau == 0 and m.perda is None
    # fratura de verdade (vértebra plana) não deixa as vizinhas "duvidosas"
    v = {x.nome: x for x in COL.medir_vertebras(_coluna_sintetica(
        {"L1": (25, 25), "L2": (5, 5), "L3": (25, 25), "L4": (25, 25)}))}
    assert not any(x.duvidosa for x in v.values()) and v["L2"].grau == 3 and v["L2"].forma == "esmagamento"
    assert isinstance(SimpleNamespace, type)


def test_duas_sagitais_concordam_discordam_e_pareiam_pela_posicao(medir):
    alturas = {"T12": (25, 25), "L1": (15, 25), "L2": (25, 25), "L3": (25, 25)}
    a = _coluna_sintetica(alturas)
    b = _coluna_sintetica({"T12": (25, 25), "L1": (16, 25), "L2": (25, 25), "L3": (25, 25)})
    v = {x.nome: x for x in COL.medir_vertebras(a, (b,))}
    assert all(x.seq == 2 and x.concorda for x in v.values() if x.nome != "T12" or x.posterior)
    assert v["L1"].grau >= 2 and v["L1"].forma == "cunha"
    # a outra sagital vê L1 sem fratura: discordam, não gradua, mostra as duas
    c = _coluna_sintetica({"T12": (25, 25), "L1": (25, 25), "L2": (25, 25), "L3": (25, 25)})
    v = {x.nome: x for x in COL.medir_vertebras(a, (c,))}
    assert v["L1"].grau == 0 and "anterior" in v["L1"].alt and "discordam" in v["L1"].nota
    assert " | " in COL.texto_da_vertebra(v["L1"])
    # a outra contou um nível acima (o mesmo osso com outro nome): pareia pela posição e avisa
    d = _coluna_sintetica({"T12": (25, 25), "L1": (16, 25), "L2": (25, 25), "L3": (25, 25)})
    for mv in d.volumes:
        mv.label = COL.deslocar(mv.label, 1)
    v = {x.nome: x for x in COL.medir_vertebras(a, (d,))}
    assert v["L1"].seq == 2 and v["L1"].concorda and v["L1"].grau >= 2
    assert "contaram diferente" in COL.contagem_difere(a, (d,))
    assert COL.contagem_difere(a, (b,)) == ""
    # o disco também junta as duas
    discos = {x.nome: x for x in COL.medir_discos(a, (b,))}
    assert discos["L1-L2"].seq == 2 and discos["L1-L2"].concorda


def test_segunda_serie_escolhe_outra_sagital(medir):
    from types import SimpleNamespace as NS
    sag = "0\\1\\0\\0\\0\\-1"
    ax = "1\\0\\0\\0\\1\\0"
    series = [NS(series_uid="t2", modality="MR", description="Sag T2 LOMB"),
              NS(series_uid="t1", modality="MR", description="Sag T1 LOMB"),
              NS(series_uid="stir", modality="MR", description="Sag STIR LOMB"),
              NS(series_uid="ax", modality="MR", description="Ax T2 DISCO LOMB"),
              NS(series_uid="cor", modality="MR", description="COR T2 LOMB"),
              NS(series_uid="loc", modality="MR", description="LOC LOMB")]
    ori = {"t2": sag, "t1": sag, "stir": sag, "ax": ax, "cor": "1\\0\\0\\0\\0\\-1", "loc": sag}
    repo = NS(series_for_study=lambda _u: series,
              instances_for_series=lambda u: [{"orientation": ori[u], "path": "/nao/existe"}] * 15)
    assert COL.eh_sagital(repo, "t2") and not COL.eh_sagital(repo, "ax") and not COL.eh_sagital(repo, "cor")
    assert COL.segunda_serie(repo, "x", "t2") == "stir"          # a ordem da lista de prioridade da RM
    assert COL.segunda_serie(repo, "x", "t1") == "t2"
    assert COL.quer_conferencia(None, "MR") and not COL.quer_conferencia(None, "CT")


def test_tela_mede_nas_duas_series(env, tmp_path, monkeypatch, medir):
    """Identificar pela tela com duas sagitais: roda a segunda, grava a SEG de conferência (que não
    aparece na tela) e as tabelas com as duas (fantoma de TC; a escolha da segunda é forçada)."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    # a mesma série de novo, como se fosse outra sagital do exame
    import shutil
    pasta2 = tmp_path / "copia"
    pasta2.mkdir()
    nova = generate_uid()
    for i, inst in enumerate(repo.instances_for_series(serie)):
        ds = pydicom.dcmread(inst["path"])
        ds.SeriesInstanceUID, ds.SOPInstanceUID = nova, generate_uid()
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        ds.SeriesNumber, ds.SeriesDescription = 5, "SAG T1"
        ds.save_as(pasta2 / f"c{i}.dcm")
    Importer(db, paths.storage).import_paths([pasta2])
    assert shutil
    monkeypatch.setattr(COL, "quer_conferencia", lambda _s, _m: True)
    monkeypatch.setattr(COL, "segunda_serie", lambda _r, _u, primeira, _s=None: nova if primeira != nova else None)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.show()
    try:
        assert w.handle_external({"accession": "COL01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        vp = next(v for v in tab.viewports if v.frames and v.current_frame().series_uid == serie) \
            if any(v.frames and v.current_frame().series_uid == serie for v in tab.viewports) else None
        if vp is None:
            vp = next(v for v in tab.viewports if v.frames)
            tab.load_series_into(vp, serie)
        tab.segmentar_orgaos(vp, simular=True, tipo="coluna")
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and not avisos[-1].startswith("ERRO"), avisos
        assert "Conferido na segunda sagital (SAG T1)" in avisos[-1] and "conferido em duas sagitais" in avisos[-1]
        descr = [s.description for s in repo.series_for_study(uid)]
        assert descr.count(COL.DESC_CONF) == 1 and descr.count(COL.MARCA) == 1
        assert descr.count(COL.DESC_TABELA_VERT) == 1 and descr.count(COL.DESC_TABELA) == 1
        cols = [o for o in tab.overlay_objects if o.source == "Coluna"]
        assert len(cols) == 1                                  # a conferência não vira rótulo na tela
        assert len(getattr(cols[0], "conferencias", ())) == 1
        assert all(m.seq == 2 for m in COL.medir_discos(cols[0], cols[0].conferencias) if m.media)
        # repetir troca, não acumula
        avisos.clear()
        tab.segmentar_orgaos(vp, simular=True, tipo="coluna")
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        descr = [s.description for s in repo.series_for_study(uid)]
        assert descr.count(COL.DESC_CONF) == 1 and descr.count(COL.MARCA) == 1
    finally:
        w.close()



# ------------------------------------------------------------------ 0.99.7: só nomeia
def test_sem_medidas_so_nomeia(env, tmp_path):
    """Pedido dele: "apenas nomeie as vértebras; desconsidere a altura do disco e da vértebra"."""
    from ipe.core.config import Settings
    paths, db, repo = env
    st = Settings(paths.settings_file)
    st.set(COL.CHAVE_MEDIR, True)                        # mesmo com a opção antiga gravada
    assert not COL.config(st, COL.CHAVE_MEDIR) and not COL.quer_conferencia(st, "MR")
    assert COL.tarefas("MR", st)[1]["roi"] == ["intervertebral_discs"], "a RM volta aos discos de 3 mm"
    uid, serie = _exame(env, tmp_path)
    t = _trabalho(env, uid, serie)
    try:
        rotulos, versao, _s = t.ler_rotulos()
        saida = COL.gravar(t, COL.nomear(t.vol, rotulos), versao, db, paths.storage)
        obj = COL.objeto_do_seg(saida["seg_path"], uid)
        assert COL.anexar_medidas(obj) == [] and not any(str(f).startswith("📏") for f in obj.findings)
        assert "L4" in obj.findings and "L4-L5" in obj.findings
    finally:
        t.limpar()
