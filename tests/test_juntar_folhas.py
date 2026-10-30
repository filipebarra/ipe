"""0.99.6: folhas que chegam em sessões separadas viram páginas de um trabalho só."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.printing import jobs as J
from ipe.printing import juntar as JUN
from ipe.printing.dicom_print import dicom_print
from tests.test_print_receive import Printer, _pagina


def _receber(prn, ae, n):
    dicom_print(prn.config(), [_pagina(30 + 30 * n)], local_ae=ae)
    return prn.wait(n)


def test_regras_de_juntar():
    t = datetime(2026, 10, 27, 10, 0)
    a = {"id": 1, "source": "scp", "status": "new", "calling_ae": "MG01", "remote_host": "10.0.0.5", "server": "Sala",
         "received_at": t, "patient_id": "123", "patient_name": "MARIA", "folder": ""}
    b = dict(a, id=2, received_at=t + timedelta(seconds=30))
    assert JUN.pode_juntar(a, b, 90)
    assert not JUN.pode_juntar(a, dict(b, received_at=t + timedelta(seconds=200)), 90), "fora da janela"
    assert not JUN.pode_juntar(a, dict(b, calling_ae="CT01"), 90), "outra origem"
    assert not JUN.pode_juntar(a, dict(b, patient_id="999"), 90), "OCR leu outro paciente"
    assert JUN.pode_juntar(a, dict(b, patient_id="", patient_name=""), 90), "OCR não leu: junta"
    assert not JUN.pode_juntar(dict(a, status="sent"), b, 90), "o anterior já saiu"
    assert JUN.mesmo_paciente({"patient_name": "SILVA^ANA"}, {"patient_name": "silva ana"}) is True


def test_folhas_da_mesma_origem_viram_paginas(env, tmp_path, monkeypatch):
    from ipe.network.service import NetworkService
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    st = Settings(paths.settings_file)
    st.set(JUN.CHAVE, True)
    net = NetworkService(db, repo, paths.storage, st)
    prn = Printer(tmp_path)
    net.print_root = prn.root
    emitidos = []
    net.print_received.connect(emitidos.append)
    cfg = SimpleNamespace(to_database=True, name="Sala")
    try:
        pacientes = [("SOUZA^ANA", "111"), ("SOUZA^ANA", "111"), ("", ""), ("LIMA^JOAO", "222")]
        for n, (nome, pid) in enumerate(pacientes, start=1):
            job, folder = _receber(prn, "MG01", n)
            job.patient_name, job.patient_id, job.id_source = nome, pid, "ocr" if pid else ""
            job.server = "Sala"
            net._on_print_job(job, folder, cfg)
        net.sink.flush(30)
        linhas = [r for r in repo.print_jobs() if r["source"] == "scp"]
        assert len(linhas) == 2, [(r["patient_name"], r["sheets"]) for r in linhas]
        ana = next(r for r in linhas if r["patient_id"] == "111")
        joao = next(r for r in linhas if r["patient_id"] == "222")
        assert ana["sheets"] == 3 and joao["sheets"] == 1, "a folha sem OCR foi junto com a anterior"
        job = J.load(ana["folder"])
        assert len(job.juntados) == 2 and job.ultima_folha_em
        for film in job.films:                                  # as caixas copiadas existem
            assert J.box_pixels(ana["folder"], film.boxes[0]) is not None
        # um exame só com as três páginas
        st_ana = [s for s in repo.series_for_study(ana["study_uid"])]
        assert sum(s.num_images for s in st_ana) == 3
        assert emitidos[1].get("juntadas") == 1 and emitidos[-1]["patient_id"] == "222"
        # outra modalidade, mesmo paciente: não junta
        job, folder = _receber(prn, "CT01", 5)
        job.patient_name, job.patient_id, job.server = "SOUZA^ANA", "111", "Sala"
        net._on_print_job(job, folder, cfg)
        assert len([r for r in repo.print_jobs() if r["source"] == "scp"]) == 3
        # desligado: cada folha fica separada
        st.set(JUN.CHAVE, False)
        job, folder = _receber(prn, "CT01", 6)
        job.patient_name, job.patient_id, job.server = "SOUZA^ANA", "111", "Sala"
        net._on_print_job(job, folder, cfg)
        assert len([r for r in repo.print_jobs() if r["source"] == "scp"]) == 4
    finally:
        prn.stop()
        net.shutdown()


def test_botao_juntar_na_lista(env, tmp_path, monkeypatch):
    from ipe.network.service import NetworkService
    from ipe.ui.prints_tab import PrintsTab
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    st = Settings(paths.settings_file)
    st.set(JUN.CHAVE, False)                                    # chegam separadas
    net = NetworkService(db, repo, paths.storage, st)
    prn = Printer(tmp_path)
    net.print_root = prn.root
    cfg = SimpleNamespace(to_database=False, name="Sala")
    try:
        for n in (1, 2):
            job, folder = _receber(prn, "US01", n)
            net._on_print_job(job, folder, cfg)
        aba = PrintsTab(repo, st, net)
        aba.refresh()
        aba.table.selectAll()
        app.processEvents()
        assert aba.b_juntar.isEnabled()
        novo = aba.juntar_selecionados(confirmar=False)
        assert novo["sheets"] == 2 and len([r for r in repo.print_jobs() if r["source"] == "scp"]) == 1
    finally:
        prn.stop()
        net.shutdown()


def test_encaminhamento_espera_a_janela_e_recomeca_a_cada_folha(env, monkeypatch):
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        w.settings.set(JUN.CHAVE, True)
        w.settings.set(JUN.CHAVE_SEGUNDOS, 30)
        saidas = []
        monkeypatch.setattr(w, "_auto_forward", lambda row: saidas.append(row))
        rid = repo.add_print_job(uid="x1", source="scp", calling_ae="MG01", status="new", sheets=1)
        row = repo.print_job(rid)
        w._encaminhar_quando_parar(row)
        t = w._esperando_juntar[rid]
        assert t.isActive() and t.interval() == 30_000 and not saidas
        w._encaminhar_quando_parar(row)                         # chegou mais uma folha: recomeça
        assert w._esperando_juntar[rid] is t and t.isActive()
        t.timeout.emit()
        assert len(saidas) == 1 and rid not in w._esperando_juntar
        w.settings.set(JUN.CHAVE, False)
        w._encaminhar_quando_parar(row)
        assert len(saidas) == 2, "desligado: encaminha na hora"
    finally:
        w.close()
