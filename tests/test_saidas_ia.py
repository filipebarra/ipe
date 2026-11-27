"""0.100.124: SEG, tabelas e série com overlay colorido das IAs (para PACS que não mostram SEG)."""
import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).parent))
from test_estruturas import _volume_do_banco, exame  # noqa: E402,F401

from ipe.ai import saidas_ia as SI  # noqa: E402


class _Cfg(dict):
    def get(self, k, d=None):
        return super().get(k, d)


class _Repo:
    def __init__(self, info):
        self.info = info

    def series_info(self, u):
        return self.info.get(u)


def test_classes_e_filtro():
    repo = _Repo({"a": {"modality": "SEG", "description": "Órgãos · TotalSegmentator"},
                  "b": {"modality": "OT", "description": "Volumetria · TotalSegmentator"},
                  "c": {"modality": "OT", "description": "Órgãos · overlay colorido · Ipê"},
                  "d": {"modality": "SR", "description": "x"}})
    assert [SI.classe(repo.series_info(u)) for u in "abcd"] == ["seg", "tabela", "overlay", "outra"]
    assert SI.filtrar(repo, _Cfg(), list("abcd")) == ["a", "b", "d"]          # padrão: SEG e tabelas, sem overlay
    cfg = _Cfg({SI.CHAVE_SEG: False, SI.CHAVE_OVERLAY: True})
    assert SI.filtrar(repo, cfg, list("abcd")) == ["b", "c", "d"]


def test_destinos_somam_sem_repetir():
    cfg = _Cfg({SI.CHAVE_DESTINOS: [2, 3]})
    assert SI.ids_de_destino(cfg, [1, 2]) == [1, 2, 3]


def _corte(caminho, k, estudo, serie, forma=(32, 32)):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.PatientName, ds.PatientID, ds.Modality = "Teste", "1", "CT"
    ds.StudyInstanceUID, ds.SeriesInstanceUID = estudo, serie
    ds.InstanceNumber = k
    ds.ImagePositionPatient = [0, 0, float(k)]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.PixelSpacing = [1, 1]
    ds.Rows, ds.Columns = forma
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
    ds.RescaleSlope, ds.RescaleIntercept = 1, 0
    ds.PixelData = np.full(forma, 40, np.int16).tobytes()
    ds.save_as(caminho, enforce_file_format=True)
    return str(ds.SOPInstanceUID)


def test_colar_pinta_miolo_e_contorno():
    rgb = np.zeros((20, 20, 3), np.uint8)
    m = np.ones((8, 8), bool)
    SI._colar(rgb, m, 4, 4, (255, 0, 0))
    assert tuple(rgb[4, 4]) == (255, 0, 0)                  # contorno cheio
    assert 0 < rgb[8, 8, 0] < 255                           # miolo translúcido
    assert rgb[0, 0].sum() == 0
    SI._colar(rgb, m, 18, 18, (0, 255, 0))                  # recorte que sai da imagem não quebra


def test_reamostrar():
    m = np.ones((4, 4), bool)
    assert SI._reamostrar(m, 2.0, 2.0).shape == (8, 8)
    assert SI._reamostrar(m, 1.0, 1.0) is m


def test_overlay_de_ponta_a_ponta(exame, tmp_path):  # noqa: F811
    """SEG gravada no banco → série colorida: um corte por imagem, na posição do original, com cor onde há máscara."""
    from pathlib import Path
    from types import SimpleNamespace

    from ipe.imaging import estruturas as ES
    from ipe.imaging.seg_writer import build_seg
    from ipe.importer.scanner import Importer
    paths, db, repo, estudo, serie, _v = exame
    vol, frames = _volume_do_banco(repo, serie)
    g = ES.Grade.do_volume(vol)
    a = ES.Estrutura("Tumor", (255, 0, 0), tipo="lesão")
    ES.pintar(a, g, g.para_mm([32, 32, 10])[0], 7.0)
    ds = build_seg(vol, [(SimpleNamespace(mask=a.mascara, offset=a.offset), a.nome, a.cor, a.tipo)],
                   vol.source_path, frames)
    pasta = tmp_path / "seg"
    pasta.mkdir()
    ds.save_as(pasta / "seg.dcm", enforce_file_format=True)
    Importer(db, Path(paths.storage)).import_paths([pasta])
    nova = SI.overlay_de_seg(repo, db, Path(paths.storage), str(ds.SeriesInstanceUID))
    assert nova
    insts = repo.instances_for_series(nova)
    assert len(insts) >= 5
    info = repo.series_info(nova)
    assert SI.classe(info) == "overlay" and "· Ipê" in info["description"]
    meio = pydicom.dcmread(insts[len(insts) // 2]["path"])
    px = meio.pixel_array
    assert px.shape[-1] == 3 and (px[..., 0].astype(int) - px[..., 1].astype(int) > 60).any()   # vermelho do tumor


class _Rede:
    def __init__(self):
        self.enviados = []

    def send(self, no, _x, estudos, rotulo, series_uids=None):
        self.enviados.append((no["id"], list(series_uids)))

    def run_async(self, trabalho, pronto, *a):
        try:
            r, e = trabalho(), None
        except Exception as ex:  # noqa: BLE001
            r, e = None, ex
        pronto(r, e)


class _RepoNos(_Repo):
    def nodes(self, only_active=True, todos=False):
        return [{"id": 1, "name": "PACS"}, {"id": 2, "name": "Outro"}]


def test_enviar_junta_destinos_e_filtra(monkeypatch):
    from ipe.automation import destinos as DEST
    repo = _RepoNos({"a": {"modality": "SEG", "description": "x"}, "b": {"modality": "OT", "description": "y"}})
    cfg = _Cfg({SI.CHAVE_SEG: False, SI.CHAVE_DESTINOS: [2]})
    monkeypatch.setattr(SI, "_CTX", {"settings": cfg, "db": None, "storage": None})
    net = _Rede()
    n = DEST.enviar(net, repo, "est", ["a", "b"], [1], "teste")
    assert n == 2 and net.enviados == [(1, ["b"]), (2, ["b"])]          # SEG desmarcada não vai; destinos somados


def test_enviar_com_overlay_cria_antes_de_mandar(monkeypatch):
    from ipe.automation import destinos as DEST
    repo = _RepoNos({"a": {"modality": "SEG", "description": "x"}, "z": {"modality": "OT", "description": "x · overlay colorido · Ipê"}})
    cfg = _Cfg({SI.CHAVE_OVERLAY: True, SI.CHAVE_SEG: False})
    monkeypatch.setattr(SI, "_CTX", {"settings": cfg, "db": object(), "storage": "/x"})
    monkeypatch.setattr(SI, "completar", lambda repo, db, st, s, series, *a: list(series) + ["z"])
    net = _Rede()
    DEST.enviar(net, repo, "est", ["a"], [1], "teste")
    assert net.enviados == [(1, ["z"])]                                 # só o colorido: a SEG está desmarcada


def test_preferencias_guardam_as_opcoes(env):
    from PySide6.QtWidgets import QApplication, QWidget

    from ipe.core.config import Settings
    from ipe.ui.preferences import PreferencesDialog
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    pai = QWidget()
    pai.repo = repo
    st = Settings(paths.settings_file)
    c = PreferencesDialog(st, pai).cad_ia
    assert c.c_out_seg.isChecked() and c.c_out_tab.isChecked() and not c.c_out_ovl.isChecked()
    c.c_out_ovl.setChecked(True)
    c.c_out_seg.setChecked(False)
    c.save()
    assert st.get(SI.CHAVE_OVERLAY) is True and st.get(SI.CHAVE_SEG) is False


def test_escolha_da_ferramenta_sobrepoe_a_global():
    repo = _Repo({"a": {"modality": "SEG", "description": "x"}, "b": {"modality": "OT", "description": "y"}})
    cfg = _Cfg({SI.CHAVE_SEG: False, SI.chave_ferramenta("abdome", "seg"): "sim",
                SI.chave_ferramenta("coluna", "tabelas"): "nao", SI.CHAVE_DESTINOS: [9]})
    assert SI.filtrar(repo, cfg, ["a", "b"]) == ["b"]                        # global: sem SEG
    assert SI.filtrar(repo, cfg, ["a", "b"], "abdome") == ["a", "b"]         # o abdome quer a SEG
    assert SI.filtrar(repo, cfg, ["a", "b"], "coluna") == []                 # a coluna: sem SEG (global) e sem tabelas
    assert SI.efetivo(cfg, "overlay", "abdome") is False
    cfg[SI.chave_ferramenta("abdome", "overlay")] = "sim"
    assert SI.efetivo(cfg, "overlay", "abdome") is True and SI.efetivo(cfg, "overlay", "coluna") is False
    assert SI.ids_de_destino(cfg, [1], "abdome") == [1, 9]
    cfg[SI.chave_ferramenta("abdome", "destinos")] = "so_esta"
    assert SI.ids_de_destino(cfg, [1], "abdome") == [1] and SI.ids_de_destino(cfg, [1], "coluna") == [1, 9]


def test_enviar_respeita_a_ferramenta(monkeypatch):
    from ipe.automation import destinos as DEST
    repo = _RepoNos({"a": {"modality": "SEG", "description": "x"}, "b": {"modality": "OT", "description": "y"}})
    cfg = _Cfg({SI.CHAVE_SEG: False, SI.CHAVE_DESTINOS: [2], SI.chave_ferramenta("abdome", "seg"): "sim",
                SI.chave_ferramenta("abdome", "destinos"): "so_esta"})
    monkeypatch.setattr(SI, "_CTX", {"settings": cfg, "db": None, "storage": None})
    net = _Rede()
    DEST.enviar(net, repo, "est", ["a", "b"], [1], "t", "abdome")
    assert net.enviados == [(1, ["a", "b"])]                               # SEG por escolha dela; sem o destino global
    net.enviados.clear()
    DEST.enviar(net, repo, "est", ["a", "b"], [1], "t", "coluna")
    assert net.enviados == [(1, ["b"]), (2, ["b"])]


def test_preferencias_por_ia(env):
    from PySide6.QtWidgets import QApplication, QWidget

    from ipe.core.config import Settings
    from ipe.ui.preferences import PreferencesDialog
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    pai = QWidget()
    pai.repo = repo
    st = Settings(paths.settings_file)
    c = PreferencesDialog(st, pai).cad_ia
    assert {"abdome", "coluna", "implante", "mama", "dce", "cefalometria", "neuro", "linfonodos"} <= set(c._saidas)
    c._saidas["abdome"]["overlay"].setCurrentIndex(c._saidas["abdome"]["overlay"].findData(SI.SIM))
    c._saidas["coluna"]["destinos"].setCurrentIndex(c._saidas["coluna"]["destinos"].findData(SI.SO_ESTA))
    c.save()
    assert st.get(SI.chave_ferramenta("abdome", "overlay")) == "sim"
    assert st.get(SI.chave_ferramenta("coluna", "destinos")) == "so_esta"
    assert st.get(SI.chave_ferramenta("coluna", "seg")) == "global"


def test_tabela_ot_para_toda_ia(exame):  # noqa: F811
    """0.100.133: IA sem tabela própria ganha uma OT feita dos achados; a opção "Tabelas" (global e por IA) manda."""
    from pathlib import Path

    from ipe.ai import achados as AC
    from ipe.ai import tabela_ot as TO
    paths, db, repo, estudo, serie, _v = exame
    repo.gravar_achados(estudo, "enfisema", [{"series_uid": serie, "rotulo": "E", "tipo": "Enfisema", "local": "pulmões",
                                              "numeros": {"laa": AC.numero(12.5, "%", "%LAA−950 total")}}])
    root = Path(paths.storage)
    saida = {"series": []}
    TO.completar(repo, db, root, _Cfg(), estudo, "enfisema", "Enfisema: % abaixo de −950 HU (IA)", saida)
    assert len(saida["series"]) == 1
    info = repo.series_info(saida["series"][0])
    assert SI.classe(info) == "tabela" and info["description"].startswith("Enfisema ·")
    px = pydicom.dcmread(repo.instances_for_series(saida["series"][0])[0]["path"]).pixel_array
    assert px.shape[-1] == 3 and px.shape[1] == 1400
    # refazer não duplica
    TO.completar(repo, db, root, _Cfg(), estudo, "enfisema", "Enfisema: % abaixo de −950 HU (IA)", {"series": []})
    assert sum(1 for s in repo.series_for_study(estudo) if (s.description or "").startswith("Enfisema ·")) == 1
    # a ferramenta que já trouxe a sua tabela não ganha outra; "Não" por IA desliga
    atual = [s.series_uid for s in repo.series_for_study(estudo) if (s.description or "").startswith("Enfisema ·")]
    assert TO.completar(repo, db, root, _Cfg(), estudo, "enfisema", "x", {"series": list(atual)})["series"] == atual
    off = _Cfg({SI.chave_ferramenta("enfisema", "tabelas"): SI.NAO})
    assert TO.completar(repo, db, root, off, estudo, "enfisema", "x", {"series": []})["series"] == []
    glob_off = _Cfg({SI.CHAVE_TABELAS: False})
    assert TO.completar(repo, db, root, glob_off, estudo, "enfisema", "x", {"series": []})["series"] == []
    sim = _Cfg({SI.CHAVE_TABELAS: False, SI.chave_ferramenta("enfisema", "tabelas"): SI.SIM})
    assert len(TO.completar(repo, db, root, sim, estudo, "enfisema", "Enfisema: y", {"series": []})["series"]) == 1
