"""Imagens comuns (C-STORE) mandadas à porta da impressão viram filme e seguem a regra (0.81)."""

import socket
import time
from pathlib import Path

import pydicom
from pynetdicom import AE, StoragePresentationContexts
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.printing import auto_film as AF
from ipe.printing import config as C
from ipe.printing import dispatch as D
from ipe.printing import rules as R


def _porta() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _mandar(porta: int, arquivos: list[Path], ae_titulo="US_SALA1") -> int:
    ae = AE(ae_title=ae_titulo)
    ae.requested_contexts = StoragePresentationContexts[:120]
    assoc = ae.associate("127.0.0.1", porta, ae_title="PRNUS")
    assert assoc.is_established, "a porta da impressão recusou imagens"
    ok = 0
    for f in arquivos:
        st = assoc.send_c_store(pydicom.dcmread(f))
        ok += int(getattr(st, "Status", 1) == 0)
    assoc.release()
    return ok


def test_imagens_na_porta_da_impressao_viram_filme_e_seguem_a_regra(env, sample_dir, tmp_path):
    paths, _db, repo = env
    app = QApplication.instance() or QApplication([])
    settings = Settings(paths.settings_file)
    porta = _porta()
    pasta = tmp_path / "pdf"
    C.save_servers(settings, [C.ServerConfig(name="Ultrassom", enabled=True, ae_title="PRNUS",
                                             port=porta, to_database=False)])
    D.save_destinations(settings, [D.Destination(name="PDF", kind="pdf", folder=str(pasta), dpi=72)])
    R.save_rules(settings, [R.Rule(name="US", server="Ultrassom", destination="PDF")])
    AF.save(settings, AF.AutoFilm(enabled=False, rows=2, cols=2, max_images=1))
    settings.set("dicom", dict(settings.get("dicom", {}), enabled=False, http_enabled=False))
    settings.set("printing.hold_unknown_origin", False)
    settings.save()
    arquivos = sorted(p for p in Path(sample_dir).rglob("*.dcm"))[:5]
    assert arquivos
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, settings)
    w.start_services()
    try:
        assert _mandar(porta, arquivos) == len(arquivos)
        fim = time.monotonic() + 60
        while not list(pasta.glob("*.pdf")) and time.monotonic() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert list(pasta.glob("*.pdf")), "o filme das imagens não seguiu a regra"
        filmes = repo.films()
        assert filmes, "nenhum filme montado"
        from ipe.printing.film import Film
        total = sum(Film.from_dict(repo.film_data(f["id"])).image_count() for f in filmes)
        assert total == len(arquivos)            # todas, não o máximo do filme automático do US
    finally:
        w.net.shutdown()
        w.close()


def test_sem_on_store_a_porta_continua_so_impressao(tmp_path):
    from ipe.network.print_scp import PrintScpServer
    porta = _porta()
    srv = PrintScpServer({"ae_title": "PRN", "port": porta}, tmp_path, lambda j, f: None)
    assert srv.start()
    try:
        ae = AE(ae_title="X")
        ae.requested_contexts = StoragePresentationContexts[:10]
        assoc = ae.associate("127.0.0.1", porta, ae_title="PRN")
        if assoc.is_established:
            assert not assoc.accepted_contexts
            assoc.release()
    finally:
        srv.stop()
