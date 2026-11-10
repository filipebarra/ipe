"""0.100.7: fim da leitura — ao assinar o laudo, o KO, o GSPS, o laudo desta assinatura (PDF e SR) e as séries do
Ipê vão sozinhos ao PACS (um "PACS" de teste em loopback). O laudo de antes, as séries de outro aparelho, as ocultas e
as cópias que ficam só neste computador não vão."""
import sys
import time
from pathlib import Path

import pydicom
import pytest
from pydicom.uid import generate_uid

sys.path.insert(0, str(Path(__file__).parent))
from test_ko_gsps import _medida, _vol  # noqa: E402
from test_network import Node  # noqa: E402

from ipe.exporter import fim_leitura as FL  # noqa: E402


def _objeto_ipe(pasta: Path, src: str, modalidade: str, descricao: str, numero: int) -> str:
    """Uma série "do Ipê" (Manufacturer Ipe) no exame, copiando a imagem de origem."""
    ds = pydicom.dcmread(src)
    ds.SeriesInstanceUID = generate_uid()
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.Modality, ds.SeriesDescription, ds.SeriesNumber, ds.Manufacturer = modalidade, descricao, numero, "Ipe"
    pasta.mkdir(parents=True, exist_ok=True)
    ds.save_as(pasta / f"{ds.SOPInstanceUID}.dcm", enforce_file_format=True)
    return str(ds.SeriesInstanceUID)


@pytest.fixture
def exame(env, tmp_path):
    from test_registro_rigido import _serie
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    estudo = generate_uid()
    serie = _serie(tmp_path / "a", _vol(), estudo, generate_uid(), "Ax T1", "20261101")
    Importer(db, paths.storage).import_paths([tmp_path / "a"])
    insts = sorted(repo.instances_for_series(serie), key=lambda i: i["instance_number"])
    return paths, db, repo, estudo, serie, insts


def test_escolher_o_que_vai(exame, tmp_path):
    from ipe.importer.scanner import Importer
    paths, db, repo, estudo, serie, insts = exame
    src = insts[0]["path"]
    velho_pdf = _objeto_ipe(tmp_path / "o", src, "DOC", "Laudo (PDF)", 990)
    seg = _objeto_ipe(tmp_path / "o", src, "SEG", "Carga tumoral PET (Ipe)", 981)
    oculta = _objeto_ipe(tmp_path / "o", src, "SEG", "Rascunho (Ipe)", 982)
    from ipe.imaging.mammo import SUFIXO_SEM_IMPLANTE
    sem_implante = _objeto_ipe(tmp_path / "o", src, "MG", "L CC" + SUFIXO_SEM_IMPLANTE, 983)
    Importer(db, paths.storage).import_paths([tmp_path / "o"])
    repo.set_series_hidden([oculta], True)
    antes = FL.antes(repo, estudo)
    novo_pdf = _objeto_ipe(tmp_path / "n", src, "DOC", "Laudo (PDF)", 990)
    novo_sr = _objeto_ipe(tmp_path / "n", src, "SR", "Laudo (SR)", 991)
    novo_ko = _objeto_ipe(tmp_path / "n", src, "KO", "Imagens-chave (Ipe)", 998)
    Importer(db, paths.storage).import_paths([tmp_path / "n"])
    novas = FL.antes(repo, estudo) - antes
    tudo = {**FL.PADRAO, "ligado": True}
    vai = set(FL.escolher(repo, estudo, novas, tudo))
    assert vai == {novo_pdf, novo_sr, novo_ko, seg}
    assert serie not in vai and velho_pdf not in vai and oculta not in vai and sem_implante not in vai
    # só o laudo
    so_laudo = {**tudo, "ko": False, "gsps": False, "ipe": False}
    assert set(FL.escolher(repo, estudo, novas, so_laudo)) == {novo_pdf, novo_sr}
    assert FL.resumo(repo, estudo, sorted(vai)).count("(") == 3


def _pacs(tmp_path):
    p = Node(tmp_path / "pacs", "PACS")
    assert p.server.start()
    return p


def _esperar(f, t=15.0):
    fim = time.time() + t
    while time.time() < fim:
        if f():
            return True
        time.sleep(0.2)
    return f()


def _cfg(repo, pacs, settings, **kw):
    no = repo.save_node(pacs.as_node())
    FL.guardar(settings, {**FL.PADRAO, "ligado": True, "destino": no, **kw})
    return no


def test_assinar_na_janela_manda_ao_pacs(exame, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ipe.core.config import Settings
    from ipe.ui.report_window import ReportWindow
    paths, db, repo, estudo, serie, insts = exame
    QApplication.instance() or QApplication([])
    st = Settings(paths.settings_file)
    pacs = _pacs(tmp_path)
    try:
        _cfg(repo, pacs, st)
        repo.toggle_key_image(estudo, serie, insts[2]["sop_uid"], 0)
        _medida(repo, estudo, serie, insts[2]["sop_uid"], "line", [(10, 10), (30, 30)])
        enviados = []

        class Rede:
            def send(self, node, identity, study_uids, label, series_uids=None):
                enviados.append((node["name"], label, list(series_uids or [])))
                enviados.append(FL.enviar_direto(repo, st, node, study_uids[0], series_uids))

        monkeypatch.setattr(ReportWindow, "_rede", lambda self: Rede())
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
        rw = ReportWindow(repo, estudo, st, SimpleNamespace(storage_root=paths.storage, cache=None,
                                                            overlay_objects=[], anonymize=False))
        rw.editor.setPlainText("TC sem alterações.\nIMPRESSÃO: normal.")
        rw.sign()
        assert repo.reports(estudo)[0]["status"] == "final"
        assert len(enviados) == 2 and enviados[0][0] == "PACS" and "Fim da leitura" in enviados[0][1]
        assert enviados[1] == (4, 0)
        assert "enviando ao PACS" in rw.status.text()
        # o PACS recebeu o laudo (PDF e SR), o KO e o GSPS — e não a série de imagens
        mods = lambda: sorted(s.modality for s in pacs.repo.series_for_study(estudo))  # noqa: E731
        assert _esperar(lambda: mods() == ["DOC", "KO", "PR", "SR"]), mods()
        assert repo.access_log(limit=10, action="fim_da_leitura", study_uid=estudo)
    finally:
        pacs.close()


def test_desligado_nao_manda(exame, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ipe.core.config import Settings
    from ipe.ui.report_window import ReportWindow
    paths, db, repo, estudo, serie, insts = exame
    QApplication.instance() or QApplication([])
    st = Settings(paths.settings_file)
    chamadas = []
    monkeypatch.setattr(ReportWindow, "_rede", lambda self: chamadas.append(1))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    rw = ReportWindow(repo, estudo, st, SimpleNamespace(storage_root=paths.storage, cache=None,
                                                        overlay_objects=[], anonymize=False))
    rw.editor.setPlainText("Normal.")
    rw.sign()
    assert repo.reports(estudo)[0]["status"] == "final" and chamadas == []
    assert "PACS" not in rw.status.text()


def test_laudo_do_navegador_manda_pelo_servidor(exame, tmp_path):
    """O caminho do site: o servidor grava KO/GSPS e manda numa linha de fundo (sem a fila da janela)."""
    from ipe.central import laudo_web as LW
    from ipe.core.config import Settings
    paths, db, repo, estudo, serie, insts = exame
    st = Settings(paths.settings_file)
    pacs = _pacs(tmp_path)
    try:
        _cfg(repo, pacs, st, ko=True, gsps=False, ipe=False)
        repo.toggle_key_image(estudo, serie, insts[1]["sop_uid"], 0)
        rid = repo.save_report({"study_uid": estudo, "title": "TC", "text": "Normal.", "author": "Dra. X"})
        rep = repo.sign_report(rid, "Dra. X", "final")
        info = repo.study_info(estudo) or {}
        msgs = LW.depois_de_assinar(repo, paths.storage, rep, info, {"pdf": False, "sr": True, "usuario": "dra"}, st)
        assert any("enviando ao PACS" in m for m in msgs), msgs
        assert _esperar(lambda: sorted(s.modality for s in pacs.repo.series_for_study(estudo)) == ["KO", "SR"])
        assert _esperar(lambda: repo.access_log(limit=10, action="fim_da_leitura", study_uid=estudo))
        log = repo.access_log(limit=10, action="fim_da_leitura", study_uid=estudo)[0]
        assert "0 falha" in str(log.get("detail", log)) or "falha" in str(log)
    finally:
        pacs.close()


def test_sem_destino_avisa(exame, tmp_path):
    from ipe.central import laudo_web as LW
    from ipe.core.config import Settings
    paths, db, repo, estudo, serie, insts = exame
    st = Settings(paths.settings_file)
    FL.guardar(st, {**FL.PADRAO, "ligado": True, "destino": None})
    rid = repo.save_report({"study_uid": estudo, "title": "TC", "text": "Normal.", "author": "X"})
    rep = repo.sign_report(rid, "X", "final")
    msgs = LW.depois_de_assinar(repo, paths.storage, rep, {}, {"pdf": False, "sr": False}, st)
    assert any("escolha o destino" in m for m in msgs)
