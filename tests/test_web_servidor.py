"""0.99.91 (W0): o lado do servidor do visualizador web — site estático, metadados, quadros, miniatura,
configuração, auditoria e cabeçalhos."""
import json
import urllib.error
import urllib.request

import numpy as np
import pydicom
import pytest

from ipe.auth.backend import LocalAuth
from ipe.central import web as WEB
from ipe.central.server import CentralServer
from ipe.importer.scanner import Importer


@pytest.fixture()
def servidor(env, sample_dir, tmp_path, monkeypatch):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    site = tmp_path / "site"
    (site / "assets").mkdir(parents=True)
    (site / "index.html").write_text("<!doctype html><title>Ipê web</title>", encoding="utf-8")
    (site / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (site / "assets" / "codec.wasm").write_bytes(b"\0asm\1\0\0\0")
    monkeypatch.setattr(WEB, "PASTA", site)
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    yield paths, db, repo, srv
    srv.stop()


def _url(srv, p):
    return f"http://127.0.0.1:{srv.port}{p}"


def _pedir(srv, p, token=None, data=None, headers=None):
    h = dict(headers or {})
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(_url(srv, p), data=data, headers=h, method="POST" if data is not None else "GET")
    return urllib.request.urlopen(req)


def _token(srv):
    r = _pedir(srv, "/api/login", data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
               headers={"Content-Type": "application/json"})
    return json.loads(r.read())["token"]


def test_site_estatico_sem_login_e_cabecalhos(servidor):
    *_, srv = servidor
    r = _pedir(srv, "/web/")
    assert r.status == 200 and b"Ipe" in r.read().replace("ê".encode(), b"e")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Content-Type-Options"] == "nosniff"
    assert _pedir(srv, "/web/assets/app.js").headers["Content-Type"].startswith("text/javascript")
    assert _pedir(srv, "/web/assets/codec.wasm").headers["Content-Type"] == "application/wasm"
    assert b"<title>" in _pedir(srv, "/web/exame").read()           # rota do site: o index
    with pytest.raises(urllib.error.HTTPError) as e:
        _pedir(srv, "/web/../../etc/passwd")
    assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        _pedir(srv, "/web/assets/nao_tem.js")
    assert e.value.code == 404


def test_dados_pedem_login_sem_janela_do_navegador(servidor):
    *_, srv = servidor
    with pytest.raises(urllib.error.HTTPError) as e:
        _pedir(srv, "/api/web/config", headers={"X-Ipe-Web": "1"})
    assert e.value.code == 401 and "WWW-Authenticate" not in e.value.headers
    with pytest.raises(urllib.error.HTTPError) as e:
        _pedir(srv, "/dicomweb/studies")
    assert e.value.headers.get("WWW-Authenticate")                       # outros visualizadores: Basic


def test_metadados_quadros_e_miniatura(servidor):
    paths, db, repo, srv = servidor
    tok = _token(srv)
    uid = repo.find_study_uids(accession="ACC1001")[0]
    se = repo.series_for_study(uid)[0]
    meta = json.loads(_pedir(srv, f"/dicomweb/studies/{uid}/series/{se.series_uid}/metadata", tok).read())
    assert len(meta) == len(repo.instances_for_series(se.series_uid))
    m0 = meta[0]
    sop = m0["00080018"]["Value"][0]
    assert m0["00020010"]["Value"][0] and "BulkDataURI" in m0["7FE00010"]
    assert m0["00280010"]["Value"][0] == m0["00280010"]["Value"][0]                 # Rows presente
    # o quadro 1 tem os mesmos bytes dos pixels do arquivo
    r = _pedir(srv, f"/dicomweb/studies/{uid}/series/{se.series_uid}/instances/{sop}/frames/1", tok)
    ctype = r.headers["Content-Type"]
    assert ctype.startswith("multipart/related") and 'type="application/octet-stream"' in ctype
    corpo = r.read()
    bound = ctype.split("boundary=")[1]
    cab, resto = corpo.split(b"\r\n\r\n", 1)
    assert b"transfer-syntax=1.2.840.10008.1.2.1" in cab
    dados = resto[: resto.rindex(f"\r\n--{bound}--".encode())]
    caminho = next(i["path"] for i in repo.instances_for_series(se.series_uid) if i["sop_uid"] == sop)
    ds = pydicom.dcmread(caminho)
    assert dados == ds.PixelData[: len(dados)] and len(dados) == ds.Rows * ds.Columns * ds.BitsAllocated // 8
    with pytest.raises(urllib.error.HTTPError) as e:
        _pedir(srv, f"/dicomweb/studies/{uid}/series/{se.series_uid}/instances/{sop}/frames/9", tok)
    assert e.value.code == 400
    png = _pedir(srv, f"/dicomweb/studies/{uid}/series/{se.series_uid}/thumbnail", tok)
    assert png.headers["Content-Type"] == "image/png"


def test_quadro_jpeg_ls_vai_como_esta(tmp_path):
    from pydicom.uid import JPEGLSLossless
    from ipe.core.sample_data import _base, _mono, _save
    pat = {"name": "JLS^T", "id": "J1", "birth": "19800101", "sex": "F"}
    study = {"uid": pydicom.uid.generate_uid(), "date": "20261108", "accession": "J1", "description": "MG",
             "for": pydicom.uid.generate_uid()}
    series = {"uid": pydicom.uid.generate_uid(), "number": 1, "description": "L CC"}
    ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, series, "CT")
    px = (np.arange(64 * 64, dtype=np.uint16).reshape(64, 64) % 4000)
    _mono(ds, px.astype(np.int16), signed=True)
    try:
        ds.compress(JPEGLSLossless, encoding_plugin="pyjpegls")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"sem codificador JPEG-LS aqui: {e}")
    caminho = _save(ds, tmp_path)
    (dados, ts), = WEB.quadros(str(caminho), [1])
    assert ts == JPEGLSLossless and dados[:2] == b"\xff\xd8"                 # o código JPEG-LS, sem descomprimir


def test_config_com_as_preferencias_do_usuario(servidor):
    paths, db, repo, srv = servidor
    from ipe.core.config import Settings
    st = Settings(paths.settings_file)
    st.set("viewer.wl_presets", {"1": ["Pulmão", 1500, -600]})
    st.set("language", "pt-BR")
    srv.settings = st
    tok = _token(srv)
    cfg = json.loads(_pedir(srv, "/api/web/config", tok).read())
    assert cfg["lang"] == "pt" and cfg["viewer.wl_presets"]["1"][0] == "Pulmão"
    assert cfg["usuario"]["username"] == "admin" and cfg["versao"]
    uid_admin = repo.user_by_name("admin")["id"] if hasattr(repo, "user_by_name") else None
    if uid_admin:
        repo.save_user_prefs(uid_admin, {"viewer": {"wl_presets": {"1": ["Meu", 400, 40]}}})
        cfg = json.loads(_pedir(srv, "/api/web/config", tok).read())
        assert cfg["viewer.wl_presets"]["1"][0] == "Meu"


def test_auditoria_de_abertura(servidor):
    paths, db, repo, srv = servidor
    tok = _token(srv)
    uid = repo.find_study_uids(accession="ACC1001")[0]
    _pedir(srv, "/api/web/abriu", tok, data=json.dumps({"study_uid": uid}).encode())
    assert any(uid in (x.get("detail") or x.get("details") or "") for x in repo.access_log(user="admin",
                                                                                           action="web_abriu"))


def test_link_do_visualizador_web_nas_configuracoes(env):
    from PySide6.QtWidgets import QApplication

    from ipe.core.config import Settings
    from ipe.ui.central_dialog import CentralDialog
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    st = Settings(paths.settings_file)
    st.set("central.port", 9443)
    d = CentralDialog(st)
    assert ":9443/web/" in d.web_link.text() and d.web_link.text().count("http://") >= 1
