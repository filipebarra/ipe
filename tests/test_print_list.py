"""Lista de impressões: receber da modalidade, virar exame no banco e encaminhar (PDF, imagens,
impressora DICOM)."""
import socket
import time
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.network.print_scp import PrintScpServer
from ipe.printing import dispatch as D
from ipe.printing import jobs as J
from ipe.printing.dicom_print import PageImage, PrinterConfig, dicom_print



def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _pagina(valor: int) -> PageImage:
    px = np.full((100, 80), valor, dtype=np.uint8)
    px[5:15, 5:30] = 255 - valor
    return PageImage(pixels=px, film_size="14INX17IN")


def _espera(app, cond, segundos=10.0) -> bool:
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def test_recebe_encaminha_e_vira_exame(env, tmp_path):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    settings = Settings(paths.settings_file)
    porta = free_port()
    settings.set("print_scp", {"enabled": True, "ae_title": "DICOMPRINT", "port": porta,
                               "accept": "any", "timeout": 15, "to_database": True,
                               "auto_destination": ""})
    settings.set("dicom", dict(settings.get("dicom", {}), enabled=False, http_enabled=False))
    settings.save()

    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, settings)
    w.start_services()
    try:
        assert w.net.print_server.running, w.net.print_server.error
        cfg = PrinterConfig(name="p", ae_title="DICOMPRINT", host="127.0.0.1", port=porta)
        paginas = [_pagina(60), _pagina(180)]
        assert dicom_print(cfg, paginas, local_ae="TC_SALA2").pages == 2

        assert _espera(app, lambda: len(repo.print_jobs()) == 1), "o trabalho não entrou na lista"
        linha = repo.print_jobs()[0]
        assert linha["calling_ae"] == "TC_SALA2" and linha["sheets"] == 2 and linha["images"] == 2
        assert linha["status"] == "new" and linha["film_size"] == "14INX17IN"

        # virou exame no banco: as folhas montadas entram como Secondary Capture
        assert linha["study_uid"]
        w.net.sink.flush(30)
        estudos = [e for e in repo.search_studies() if e.study_uid == linha["study_uid"]]
        assert estudos and "OT" in estudos[0].modalities and estudos[0].num_images == 2

        # a aba aparece com o trabalho (recebido) na primeira linha
        aba = w.show_prints()
        app.processEvents()
        assert aba.table.rowCount() == 1
        assert aba.table.item(0, 0).text() == "Recebido"
        aba.table.selectRow(0)
        app.processEvents()

        # PDF
        pasta_pdf = tmp_path / "saida-pdf"
        dest = D.Destination(name="PDF na pasta", kind="pdf", folder=str(pasta_pdf), dpi=100)
        assert aba.send_rows(aba.selected(), dest, avisar=False) == (1, 0)
        pdfs = list(pasta_pdf.glob("*.pdf"))
        assert len(pdfs) == 1 and pdfs[0].stat().st_size > 1000
        assert repo.print_jobs()[0]["status"] == "sent"
        assert repo.print_jobs()[0]["destination"] == "PDF na pasta"

        # imagens
        pasta_img = tmp_path / "saida-img"
        aba.table.selectRow(0)
        dest_i = D.Destination(name="PNG na pasta", kind="images", folder=str(pasta_img), dpi=72)
        assert aba.send_rows(aba.selected(), dest_i, avisar=False) == (1, 0)
        pngs = sorted(pasta_img.glob("*.png"))
        assert len(pngs) == 2                       # uma imagem por folha

        # reenviar para uma impressora DICOM de verdade (outro nó), como veio
        recebidos = []
        porta2 = free_port()
        outra = PrintScpServer({"ae_title": "FILMPRN", "port": porta2, "accept": "any", "timeout": 15},
                               tmp_path / "outra", lambda job, folder: recebidos.append((job, folder)))
        assert outra.start()
        try:
            settings.set("printing.dicom_printers", [PrinterConfig(
                name="Filme da sala", ae_title="FILMPRN", host="127.0.0.1", port=porta2).__dict__])
            settings.save()
            aba.table.selectRow(0)
            dest_d = D.Destination(name="Impressora de filme", kind="dicom",
                                   dicom_printer="Filme da sala")
            assert aba.send_rows(aba.selected(), dest_d, avisar=False) == (1, 0)
            assert _espera(app, lambda: len(recebidos) == 1)
            job2, pasta2 = recebidos[0]
            assert job2.sheets == 2 and job2.images == 2
            px = J.box_pixels(pasta2, job2.films[0].boxes[0])
            assert np.array_equal(px, paginas[0].pixels)     # as imagens chegaram iguais
        finally:
            outra.stop()
    finally:
        w.net.shutdown()
        w.close()


def test_encaminhamento_automatico(env, tmp_path):
    """Com um destino fixo escolhido, o que chega sai sozinho para lá."""
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    settings = Settings(paths.settings_file)
    porta = free_port()
    pasta = tmp_path / "automatico"
    settings.set("printing.destinations", [D.Destination(name="PDF automático", kind="pdf",
                                                         folder=str(pasta), dpi=72).to_dict()])
    settings.set("print_scp", {"enabled": True, "ae_title": "DICOMPRINT", "port": porta,
                               "accept": "any", "timeout": 15, "to_database": False,
                               "auto_destination": "PDF automático"})
    settings.set("dicom", dict(settings.get("dicom", {}), enabled=False, http_enabled=False))
    settings.set("printing.hold_unknown_origin", False)   # aqui o teste é do destino fixo
    settings.save()
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, settings)
    w.start_services()
    try:
        cfg = PrinterConfig(name="p", ae_title="DICOMPRINT", host="127.0.0.1", port=porta)
        assert dicom_print(cfg, [_pagina(120)], local_ae="RM1").pages == 1
        assert _espera(app, lambda: list(pasta.glob("*.pdf"))), "não encaminhou sozinho"
        assert repo.print_jobs()[0]["status"] == "sent"
        assert repo.print_jobs()[0]["destination"] == "PDF automático"
    finally:
        w.net.shutdown()
        w.close()


def test_filme_montado_aqui_vira_pdf(env, sample_dir, tmp_path):
    """O filme salvo no compositor aparece na mesma lista e vai pelos mesmos caminhos."""
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    settings = Settings(paths.settings_file)
    settings.set("dicom", dict(settings.get("dicom", {}), enabled=False, http_enabled=False))

    from ipe.printing.film import Cell, Film, Sheet
    estudo = repo.search_studies()[0]
    serie = repo.series_for_study(estudo.study_uid)[0]
    inst = repo.instances_for_series(serie.series_uid)[0]
    filme = Film(name="Aula de mama", sheets=[Sheet(1, 1, "A4")])
    filme.sheets[0].cells[0] = Cell(estudo.study_uid, serie.series_uid, inst["sop_uid"], 0)
    film_id = repo.save_film(filme.name, filme.to_dict(), [estudo.study_uid], "Fulano")

    from ipe.ui.prints_tab import PrintsTab
    aba = PrintsTab(repo, settings)
    app.processEvents()
    assert aba.table.rowCount() == 1 and aba.table.item(0, 0).text() == "Montado aqui"
    aba.table.selectRow(0)
    pasta = tmp_path / "pdf-filme"
    ok, falhas = aba.send_rows(aba.selected(), D.Destination(name="PDF", kind="pdf",
                                                             folder=str(pasta), dpi=72), avisar=False)
    assert (ok, falhas) == (1, 0) and len(list(pasta.glob("*.pdf"))) == 1
    assert repo.films()[0]["printed_at"] is not None
    aba.deleteLater()
    _ = film_id
