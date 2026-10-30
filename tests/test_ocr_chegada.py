"""OCR na chegada da impressão (0.81): identificou, segue a regra; não identificou, espera você.

Nomes inventados; nada de paciente real.
"""

import socket
import time

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QDialog

from ipe.core.config import Settings
from ipe.printing import arrival as A
from ipe.printing import config as C
from ipe.printing import dispatch as D
from ipe.printing import held as H
from ipe.printing import jobs as J
from ipe.printing import ocr
from ipe.printing import origins as O
from ipe.printing import rules as R
from ipe.printing.dicom_print import PageImage, PrinterConfig, dicom_print

ESTUDOS = [
    {"study_uid": "1.2.3", "patient_name": "MOREIRA^LUCIANA BEATRIZ PEREIRA", "patient_id": "7781234",
     "when": None, "modalities": "MG", "description": "Mamografia"},
    {"study_uid": "1.2.4", "patient_name": "TAVARES^OTAVIO HENRIQUE", "patient_id": "5512090",
     "when": None, "modalities": "CT", "description": "TC"},
    {"study_uid": "1.2.5", "patient_name": "QUEIROZ^MARINA ALVES", "patient_id": "6610333",
     "when": None, "modalities": "MG", "description": "Mamografia"},
]
CABECALHO_BOM = "MOREIRA LUCIANA BEATRIZ PEREIRA  7781234\nVIBRANT  DFOV 36"
CABECALHO_RUIM = "SE 3  IM 12  DFOV 36\nMIP AX"


class _Repo:
    def studies_for_ocr(self):
        return list(ESTUDOS)


def _job(tmp_path):
    pasta = tmp_path / "prints" / "j1"
    pasta.mkdir(parents=True)
    return J.PrintJob(uid="j1", calling_ae="MG1"), pasta


# ------------------------------------------------------------------ a decisão
def test_ocr_que_identifica_preenche_o_trabalho(tmp_path):
    job, pasta = _job(tmp_path)
    achado = A.identify(job, pasta, _Repo(), ler=lambda j, f: CABECALHO_BOM)
    assert achado is not None
    assert job.patient_name == "MOREIRA^LUCIANA BEATRIZ PEREIRA" and job.patient_id == "7781234"
    assert job.id_source == "ocr"
    assert J.load(pasta).id_source == "ocr"           # gravado no disco também


def test_ocr_que_nao_identifica_deixa_o_trabalho_como_estava(tmp_path):
    job, pasta = _job(tmp_path)
    assert A.identify(job, pasta, _Repo(), ler=lambda j, f: CABECALHO_RUIM) is None
    assert job.patient_name == "" and job.id_source == ""


def test_ocr_que_quebra_nao_derruba_o_recebimento(tmp_path):
    job, pasta = _job(tmp_path)

    def explode(j, f):
        raise RuntimeError("leitor quebrado")
    assert A.identify(job, pasta, _Repo(), ler=explode) is None


def test_dois_parecidos_sem_folga_nao_decide():
    achados = [{"score": 0.95}, {"score": 0.9}]
    assert ocr.escolher(achados) is None
    assert ocr.escolher([{"score": 0.95}, {"score": 0.8}]) is not None
    assert ocr.escolher([{"score": 0.85}]) is None


# ------------------------------------------------------------------ a fila
@pytest.fixture()
def cfg(env):
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    s.set("printing.hold_unknown_origin", True)
    s.set(A.CHAVE, True)
    o, _ = O.see(s, "MG1", "10.0.0.9", "Mamografia")
    o.enabled, o.name = True, "Mamógrafo"
    O.save_origins(s, [o])
    C.save_servers(s, [C.ServerConfig(name="Mamografia", enabled=True, ae_title="PRN", port=11112)])
    R.save_rules(s, [R.Rule(name="Mamo", server="Mamografia", destination="PDF")])
    return s


def _linha(**kw):
    base = {"uid": "j1", "calling_ae": "MG1", "remote_host": "10.0.0.9", "server": "Mamografia",
            "status": "new", "source": "scp", "sheets": 1, "images": 1, "id_source": ""}
    base.update(kw)
    return base


def test_sem_paciente_fica_parado_mesmo_com_regra(cfg):
    assert H.reason(cfg, _linha()) == H.SEM_PACIENTE
    assert H.reason(cfg, _linha(id_source="label", patient_name="ALGUEM")) == H.SEM_PACIENTE
    for origem in ("ocr", "manual", "exame"):
        assert H.reason(cfg, _linha(id_source=origem)) == H.PRONTO
    assert H.releasable(cfg, [_linha()]) == []
    assert "confirmar o paciente" in H.resumo(H.groups(cfg, [_linha()]))


def test_desligado_volta_ao_comportamento_antigo(cfg):
    cfg.set(A.CHAVE, False)
    assert H.reason(cfg, _linha()) == H.PRONTO


def test_mesmo_aparelho_separa_quem_espera_paciente(cfg):
    gs = H.groups(cfg, [_linha(uid="a"), _linha(uid="b", id_source="ocr")])
    assert sorted(g.motivo for g in gs) == sorted([H.SEM_PACIENTE, H.PRONTO])
    assert [r["uid"] for r in H.releasable(cfg, [_linha(uid="a"), _linha(uid="b", id_source="ocr")])] == ["b"]


# ------------------------------------------------------------------ ponta a ponta
def _porta() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _esperar(app, cond, segundos=45):
    fim = time.monotonic() + segundos
    while not cond() and time.monotonic() < fim:
        app.processEvents()
        time.sleep(0.05)
    return cond()


@pytest.fixture()
def janela(env, tmp_path, monkeypatch):
    paths, _db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.db.repository import Repository
    monkeypatch.setattr(Repository, "studies_for_ocr", lambda self: list(ESTUDOS))
    monkeypatch.setattr(ocr, "available", lambda: True)
    settings = Settings(paths.settings_file)
    porta = _porta()
    pasta = tmp_path / "pdf"
    C.save_servers(settings, [C.ServerConfig(name="Mamografia", enabled=True, ae_title="PRNMG",
                                             port=porta, to_database=False)])
    D.save_destinations(settings, [D.Destination(name="PDF", kind="pdf", folder=str(pasta), dpi=72)])
    R.save_rules(settings, [R.Rule(name="Mamo", server="Mamografia", destination="PDF")])
    settings.set("dicom", dict(settings.get("dicom", {}), enabled=False, http_enabled=False))
    settings.set("printing.hold_unknown_origin", False)
    settings.set(A.CHAVE, True)
    settings.save()
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, settings)
    w.start_services()

    def imprimir():
        px = np.full((120, 90), 70, np.uint8)
        assert dicom_print(PrinterConfig(name="p", ae_title="PRNMG", host="127.0.0.1", port=porta),
                           [PageImage(pixels=px)], local_ae="MG_SELENIA").pages == 1
    try:
        yield app, w, repo, pasta, imprimir
    finally:
        w.net.shutdown()
        w.close()


def test_chegada_identificada_segue_a_regra(janela, monkeypatch):
    app, _w, repo, pasta, imprimir = janela
    monkeypatch.setattr(A, "_ler", lambda job, folder: CABECALHO_BOM)
    imprimir()
    assert _esperar(app, lambda: list(pasta.glob("*.pdf"))), "identificado e não encaminhou"
    linha = repo.print_jobs()[0]
    assert linha["status"] == "sent" and linha["id_source"] == "ocr"
    assert linha["patient_id"] == "7781234"


def test_chegada_sem_identificar_espera_e_segue_depois_de_confirmar(janela, monkeypatch):
    app, w, repo, pasta, imprimir = janela
    monkeypatch.setattr(A, "_ler", lambda job, folder: CABECALHO_RUIM)
    imprimir()
    assert _esperar(app, lambda: bool(repo.print_jobs()))
    for _ in range(20):                                  # dá tempo de uma regra (errada) agir
        app.processEvents()
        time.sleep(0.05)
    linha = repo.print_jobs()[0]
    assert linha["status"] == "new" and not list(pasta.glob("*.pdf")), "saiu sem paciente"
    aba = w.show_prints()
    aba.refresh()
    assert aba._situacao(dict(linha, kind="scp")) == "Esperando paciente"

    # você confirma o paciente na janela "Identificar paciente"
    from ipe.ui import prints_tab as PT

    def aceitar(dlg):
        dlg.nome.setText("TAVARES^OTAVIO HENRIQUE")
        dlg.ident.setText("5512090")
        return QDialog.Accepted
    monkeypatch.setattr(PT.IdentifyDialog, "exec", aceitar)
    linhas = [i for i, r in enumerate(aba.rows) if r.get("uid") == linha["uid"]]
    aba.table.selectRow(linhas[0])
    aba.identify_selected()
    assert _esperar(app, lambda: list(pasta.glob("*.pdf"))), "confirmado e não seguiu a regra"
    final = repo.print_jobs()[0]
    assert final["status"] == "sent" and final["id_source"] == "manual"
    assert final["patient_name"] == "TAVARES^OTAVIO HENRIQUE"
