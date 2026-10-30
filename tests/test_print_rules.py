"""Fases C, D e E da impressão: regras, modelos de folha com logo, identificação e filme automático."""
import socket
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.printing import auto_film as AF
from ipe.printing import config as C
from ipe.printing import dispatch as D
from ipe.printing import jobs as J
from ipe.printing import layout as L
from ipe.printing import rules as R
from ipe.printing.dicom_print import PageImage, PrinterConfig, dicom_print



def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _job(ae="MG_SELENIA", folhas=1, rotulo="", quando=None, servidor="Mamografia"):
    quando = quando or datetime(2026, 9, 20, 14, 30)
    j = J.PrintJob(uid="1.2.3", received_at=quando.isoformat(timespec="seconds"), calling_ae=ae,
                   label=rotulo, server=servidor)
    j.films = [J.FilmBox(film_size="8INX10IN") for _ in range(folhas)]
    return j


# ---------------------------------------------------------------- fase C: regras
def test_regras_escolhem_o_destino(tmp_path):
    s = Settings(tmp_path / "settings.json")
    R.save_rules(s, [
        R.Rule(name="Mamo de manhã", server="Mamografia", calling_ae="MG*", hour_from=7, hour_to=12,
               destination="PDF manhã"),
        R.Rule(name="Mamo o dia todo", calling_ae="MG*", destination="Filme da sala", stop=False),
        R.Rule(name="Tudo mais", destination="PDF geral"),
    ])
    # 14h30: a primeira regra não vale (horário), a segunda manda e deixa continuar
    assert R.choose(s, _job(), "Mamografia") == [("Filme da sala", ""), ("PDF geral", "")]
    # de manhã, a primeira pega e para
    assert R.choose(s, _job(quando=datetime(2026, 9, 20, 9, 0)), "Mamografia") == [("PDF manhã", "")]
    # outro aparelho cai na última
    assert R.choose(s, _job(ae="TC1"), "TC") == [("PDF geral", "")]
    # servidor diferente não combina com a regra presa ao servidor
    assert R.choose(s, _job(quando=datetime(2026, 9, 20, 9, 0)), "TC") == [("Filme da sala", ""),
                                                                           ("PDF geral", "")]


def test_regras_por_folhas_rotulo_e_madrugada(tmp_path):
    s = Settings(tmp_path / "settings.json")
    r = R.Rule(min_sheets=3, destination="x")
    assert not R.matches(r, _job(folhas=2)) and R.matches(r, _job(folhas=3))
    r = R.Rule(max_sheets=2, destination="x")
    assert R.matches(r, _job(folhas=2)) and not R.matches(r, _job(folhas=5))
    r = R.Rule(label="*URGENTE*", destination="x")
    assert R.matches(r, _job(rotulo="CASO URGENTE 12")) and not R.matches(r, _job(rotulo="ROTINA"))
    r = R.Rule(hour_from=19, hour_to=7, destination="x")          # faixa que vira a noite
    assert R.matches(r, _job(quando=datetime(2026, 9, 20, 23, 0)))
    assert R.matches(r, _job(quando=datetime(2026, 9, 20, 3, 0)))
    assert not R.matches(r, _job(quando=datetime(2026, 9, 20, 12, 0)))
    r = R.Rule(film_size="8INX10IN", destination="x")
    assert R.matches(r, _job())
    assert not R.matches(r, _job_com_filme("14INX17IN"))
    assert not R.matches(R.Rule(enabled=False, destination="x"), _job())


def _job_com_filme(tamanho):
    j = _job()
    j.films = [J.FilmBox(film_size=tamanho)]
    return j


# ---------------------------------------------------------------- vários servidores
def test_varios_servidores(env, tmp_path):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    settings = Settings(paths.settings_file)
    # banco antigo (um servidor só) vira uma lista de um
    settings.set("print_scp", {"enabled": True, "ae_title": "ANTIGO", "port": 11113})
    assert [s.ae_title for s in C.all_servers(settings)] == ["ANTIGO"]

    p1, p2 = free_port(), free_port()
    C.save_servers(settings, [
        C.ServerConfig(name="Mamografia", enabled=True, ae_title="PRNMG", port=p1, to_database=False),
        C.ServerConfig(name="Tomografia", enabled=True, ae_title="PRNTC", port=p2, to_database=False),
    ])
    settings.set("dicom", dict(settings.get("dicom", {}), enabled=False, http_enabled=False))
    settings.save()
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, settings)
    w.start_services()
    try:
        assert len(w.net.print_servers) == 2 and all(s.running for s in w.net.print_servers)
        assert "2 impressoras" in w.net.print_status_text()
        px = np.full((60, 50), 90, np.uint8)
        dicom_print(PrinterConfig(name="a", ae_title="PRNMG", host="127.0.0.1", port=p1),
                    [PageImage(pixels=px)], local_ae="MG1")
        dicom_print(PrinterConfig(name="b", ae_title="PRNTC", host="127.0.0.1", port=p2),
                    [PageImage(pixels=px)], local_ae="TC1")
        fim = time.monotonic() + 10
        while len(repo.print_jobs()) < 2 and time.monotonic() < fim:
            app.processEvents()
            time.sleep(0.05)
        linhas = {r["calling_ae"]: r["server"] for r in repo.print_jobs()}
        assert linhas == {"MG1": "Mamografia", "TC1": "Tomografia"}
    finally:
        w.net.shutdown()
        w.close()


# ---------------------------------------------------------------- fase D: modelos
def test_modelo_de_folha_com_logo(env, tmp_path):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from PySide6.QtGui import QColor, QImage
    logo = QImage(60, 30, QImage.Format_RGB32)
    logo.fill(QColor(200, 30, 30))
    caminho_logo = tmp_path / "logo.png"
    assert logo.save(str(caminho_logo))

    pasta = tmp_path / "trabalho"
    pasta.mkdir()
    job = J.PrintJob(uid="9.9", received_at=datetime.now().isoformat(timespec="seconds"),
                     calling_ae="MG_SALA1", patient_name="MARIA SOUZA", patient_id="44821")
    from pydicom.dataset import Dataset
    caixas = []
    for i in range(4):
        item = Dataset()
        item.SamplesPerPixel, item.PhotometricInterpretation = 1, "MONOCHROME2"
        item.Rows, item.Columns = 80, 60
        item.BitsAllocated = item.BitsStored = 8
        item.HighBit, item.PixelRepresentation = 7, 0
        item.PixelData = np.full((80, 60), 50 + 40 * i, np.uint8).tobytes()
        box = J.write_box(pasta, item, i + 1, job)
        box.position = i + 1
        caixas.append(box)
    job.films = [J.FilmBox(display_format="STANDARD\\2,2", film_size="8INX10IN", boxes=caixas)]

    modelo = L.SheetTemplate(name="IMEB", clinic="Clínica Exemplo", subtitle="Brasília — (61) 0000-0000",
                             logo=str(caminho_logo), remount=True, rows=2, cols=2)
    img = L.render_job_sheet(job, pasta, 0, modelo, dpi=100)
    assert img.width() > 700 and img.height() > img.width()          # 8×10 pol em retrato
    # o logo vermelho está no cabeçalho
    achou = any(QColor(img.pixel(x, 30)).red() > 120 and QColor(img.pixel(x, 30)).green() < 90
                for x in range(10, 120))
    assert achou, "o logo não apareceu no cabeçalho"
    # e o miolo tem as quatro imagens (quatro tons diferentes)
    meio_y, meio_x = img.height() // 2, img.width() // 2
    tons = {QColor(img.pixel(meio_x // 2, meio_y // 2)).red(),
            QColor(img.pixel(meio_x + meio_x // 2, meio_y // 2)).red(),
            QColor(img.pixel(meio_x // 2, meio_y + meio_y // 2)).red(),
            QColor(img.pixel(meio_x + meio_x // 2, meio_y + meio_y // 2)).red()}
    assert len(tons) == 4

    # o mesmo modelo sai no PDF
    settings = Settings(paths.settings_file)
    L.save_templates(settings, [modelo])
    saida = tmp_path / "pdf"
    msg = D.send(job, pasta, D.Destination(name="PDF", kind="pdf", folder=str(saida), dpi=72),
                 settings, template="IMEB")
    assert "PDF" in msg and len(list(saida.glob("*.pdf"))) == 1
    _ = app


def test_previa_do_modelo():
    app = QApplication.instance() or QApplication([])
    img = L.preview(L.SheetTemplate(name="m", clinic="Clínica", remount=True, rows=2, cols=3), dpi=50)
    assert img.width() > 200 and img.height() > 200
    _ = app


# ---------------------------------------------------------------- fase E: identificação e US
def test_sugere_exames_do_mesmo_horario(env, sample_dir):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    estudo = repo.search_studies()[0]
    from ipe.printing.matching import candidates, describe
    quando = datetime.strptime(estudo.study_date + (estudo.study_time[:4] or "1200"), "%Y%m%d%H%M")
    job = J.PrintJob(uid="1", received_at=(quando).isoformat(timespec="seconds"), calling_ae="TC1")
    achados = candidates(repo, job)
    assert achados and achados[0]["study_uid"] == estudo.study_uid
    assert describe(achados[0])
    # trabalho de outro dia não casa com nada
    longe = J.PrintJob(uid="2", received_at=datetime(2001, 1, 1, 9).isoformat(), calling_ae="TC1")
    assert candidates(repo, longe) == []


def test_filme_automatico_do_us(env, sample_dir, tmp_path):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    settings = Settings(paths.settings_file)
    estudo = repo.search_studies()[0]
    modalidade = (estudo.modalities or "OT").split(",")[0].strip()
    AF.save(settings, AF.AutoFilm(enabled=True, modalities=modalidade, rows=2, cols=2, max_images=4))
    film_id = AF.run_for_study(repo, settings, estudo.study_uid)
    assert film_id is not None
    dados = repo.film_data(film_id)
    from ipe.printing.film import Film
    filme = Film.from_dict(dados)
    assert 1 <= filme.image_count() <= 4 and filme.sheets[0].rows == 2
    # não monta duas vezes o mesmo exame
    assert AF.run_for_study(repo, settings, estudo.study_uid) is None
    # modalidade de fora não entra
    AF.save(settings, AF.AutoFilm(enabled=True, modalities="XX"))
    assert AF.run_for_study(repo, settings, "outro") is None
    _ = app, tmp_path


def test_regra_encaminha_sozinho_com_modelo(env, tmp_path):
    """Ponta a ponta: chega da modalidade, a regra manda para o PDF com o modelo da clínica."""
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    settings = Settings(paths.settings_file)
    porta = free_port()
    pasta = tmp_path / "pdf-regra"
    C.save_servers(settings, [C.ServerConfig(name="Mamografia", enabled=True, ae_title="PRNMG",
                                             port=porta, to_database=False)])
    D.save_destinations(settings, [D.Destination(name="PDF da mama", kind="pdf",
                                                 folder=str(pasta), dpi=72)])
    L.save_templates(settings, [L.SheetTemplate(name="Clínica", clinic="Clínica Exemplo")])
    R.save_rules(settings, [R.Rule(name="Mamo", server="Mamografia", calling_ae="MG*",
                                   destination="PDF da mama", template="Clínica")])
    settings.set("dicom", dict(settings.get("dicom", {}), enabled=False, http_enabled=False))
    settings.set("printing.hold_unknown_origin", False)   # aqui o teste é da regra, não da origem
    settings.save()
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, settings)
    w.start_services()
    try:
        px = np.full((120, 90), 70, np.uint8)
        assert dicom_print(PrinterConfig(name="p", ae_title="PRNMG", host="127.0.0.1", port=porta),
                           [PageImage(pixels=px)], local_ae="MG_SELENIA").pages == 1
        fim = time.monotonic() + 15
        while not list(pasta.glob("*.pdf")) and time.monotonic() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert list(pasta.glob("*.pdf")), "a regra não encaminhou"
        linha = repo.print_jobs()[0]
        assert linha["status"] == "sent" and linha["destination"] == "PDF da mama"
        assert linha["server"] == "Mamografia"
    finally:
        w.net.shutdown()
        w.close()


def test_tabela_de_servidores_com_caixa(env, tmp_path):
    """A lista de servidores é uma tabela: a caixa liga/desliga e as colunas mostram o essencial."""
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    settings = Settings(paths.settings_file)
    D.save_destinations(settings, [D.Destination(name="PDF", kind="pdf", folder=str(tmp_path))])
    L.save_templates(settings, [L.SheetTemplate(name="IMEB", clinic="IMEB")])
    C.save_servers(settings, [
        C.ServerConfig(name="Mamografia", enabled=True, ae_title="PRNMG", port=11113,
                       auto_destination="PDF", template="IMEB"),
        C.ServerConfig(name="Ultrassom", enabled=False, ae_title="PRNUS", port=11115, accept="known",
                       to_database=False)])
    from PySide6.QtCore import Qt
    from ipe.ui.print_settings import PrintSettingsDialog
    dlg = PrintSettingsDialog(settings, None)
    app.processEvents()
    assert dlg.t_serv.rowCount() == 2 and dlg.t_serv.columnCount() == 9
    assert dlg.t_serv.item(0, 0).checkState() == Qt.Checked
    assert dlg.t_serv.item(1, 0).checkState() == Qt.Unchecked
    assert dlg.t_serv.item(0, 1).text() == "Mamografia" and dlg.t_serv.item(0, 3).text() == "11113"
    assert dlg.t_serv.item(0, 5).text() == "PDF" and dlg.t_serv.item(0, 6).text() == "IMEB"
    assert dlg.t_serv.item(1, 4).text() == "só cadastrados" and dlg.t_serv.item(1, 7).text() == "não"
    # clicar na caixa liga o segundo e desliga o primeiro
    dlg.t_serv.item(1, 0).setCheckState(Qt.Checked)
    dlg.t_serv.item(0, 0).setCheckState(Qt.Unchecked)
    app.processEvents()
    assert [s.enabled for s in dlg.servers] == [False, True]
    dlg._salvar()
    assert [s.enabled for s in C.all_servers(settings)] == [False, True]
    # excluir também funciona pela tabela
    dlg2 = PrintSettingsDialog(settings, None)
    dlg2.t_serv.selectRow(1)
    assert dlg2._servidor_atual() == 1
    del dlg2.servers[1]
    dlg2._encher_servidores()
    assert dlg2.t_serv.rowCount() == 1
    dlg.deleteLater()
    dlg2.deleteLater()
