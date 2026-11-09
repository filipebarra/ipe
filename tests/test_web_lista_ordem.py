"""0.100.2: a lista de exames do site ordena por qualquer coluna — clicar no título ordena (crescente; a data e as
imagens começam do maior), clicar de novo inverte, e a escolha fica lembrada no navegador."""
import sys
from pathlib import Path

import numpy as np
import pytest
from pydicom.uid import generate_uid

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mpr import _esperar  # noqa: E402

from ipe.central import web as WEB  # noqa: E402

EXAMES = [  # paciente, data, descrição, imagens
    ("EXEMPLO^BRUNO", "20260310", "TC ABDOME", 3),
    ("EXEMPLO^ANA", "20261101", "TC TORAX", 1),
    ("EXEMPLO^CARLA", "20250705", "RM CRANIO", 2),
]


@pytest.fixture()
def servidor_lista(env, tmp_path):
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    for n, (nome, data, desc, imgs) in enumerate(EXAMES):
        pat = {"name": nome, "id": f"ORD{n}", "birth": "19700101", "sex": "F"}
        st = {"uid": generate_uid(), "date": data, "accession": f"ORD{n}", "description": desc, "for": generate_uid()}
        se = {"uid": generate_uid(), "number": 1, "description": "AX"}
        for k in range(imgs):
            ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, st, se, "CT")
            ds.InstanceNumber = k + 1
            ds.ImagePositionPatient, ds.ImageOrientationPatient, ds.PixelSpacing = [0, 0, k], [1, 0, 0, 0, 1, 0], [1, 1]
            _mono(ds, np.zeros((8, 8), np.int16), signed=True)
            _save(ds, tmp_path / "ord")
    Importer(db, paths.storage).import_paths([tmp_path / "ord"])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    yield srv
    srv.stop()


def _pacientes(pg):
    return [t.replace("^", " ").split()[-1] for t in pg.locator("table.lista tbody tr td:nth-child(2)").all_inner_texts()]


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_ordenar_colunas(servidor_lista):
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1300, "height": 800})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{servidor_lista.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        assert _esperar(lambda: pg.locator("table.lista tbody tr").count() == 3)
        # de fábrica: a data, do mais recente
        assert _pacientes(pg) == ["ANA", "BRUNO", "CARLA"]
        assert pg.get_attribute("table.lista th:has(button[data-coluna='Data'])", "aria-sort") == "descending"
        col = lambda c: pg.click(f"table.lista th button[data-coluna='{c}']")  # noqa: E731
        col("Data")
        assert _pacientes(pg) == ["CARLA", "BRUNO", "ANA"]
        col("Paciente")
        assert _pacientes(pg) == ["ANA", "BRUNO", "CARLA"]
        assert pg.get_attribute("table.lista th:has(button[data-coluna='Paciente'])", "aria-sort") == "ascending"
        assert "▲" in pg.inner_text("table.lista th:has(button[data-coluna='Paciente'])")
        col("Paciente")
        assert _pacientes(pg) == ["CARLA", "BRUNO", "ANA"]
        col("Descrição")
        assert _pacientes(pg) == ["CARLA", "BRUNO", "ANA"]          # RM CRANIO, TC ABDOME, TC TORAX
        col("Imagens")                                              # começa do maior
        assert _pacientes(pg) == ["BRUNO", "CARLA", "ANA"]
        # a escolha fica lembrada: depois de buscar de novo e de recarregar
        pg.click("form.filtros button[type=submit]")
        assert _esperar(lambda: _pacientes(pg) == ["BRUNO", "CARLA", "ANA"])
        pg.reload()
        if pg.locator("#usuario").count():
            pg.fill("#usuario", "admin")
            pg.fill("#senha", "admin123")
            pg.click("button[type=submit]")
        assert _esperar(lambda: _pacientes(pg) == ["BRUNO", "CARLA", "ANA"])
        b.close()
    assert not erros, erros
