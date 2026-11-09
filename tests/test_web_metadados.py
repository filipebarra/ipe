"""0.99.99: os metadados das séries no servidor — lidos em paralelo, guardados (a mesma série sai na hora) e o
exame inteiro aquecido assim que a primeira série é pedida; mudar um arquivo invalida o guardado."""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mpr import NZ, _esperar, servidor  # noqa: E402,F401  (fixture)

from ipe.central import web as WEB  # noqa: E402


def _login(srv):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["token"]


def _series(srv):
    st = srv.repo.search_studies()[0].study_uid
    return st, [r.series_uid for r in srv.repo.series_for_study(st)]


def test_guardado_aquecido_e_invalidado(servidor):
    st, series = _series(servidor)
    grande = next(s for s in series if len(WEB.CAMINHOS.da_serie(servidor.repo, s)) == NZ)
    outra = next(s for s in series if s != grande)
    WEB._META.clear()
    tk = _login(servidor)
    req = urllib.request.Request(f"http://127.0.0.1:{servidor.port}/dicomweb/studies/{st}/series/{outra}/metadata",
                                 headers={"Authorization": f"Bearer {tk}"})
    assert len(json.loads(urllib.request.urlopen(req).read())) == 1
    # a outra série do exame foi lida sozinha, em segundo plano
    assert _esperar(lambda: (st, grande, "/dicomweb") in WEB._META, 20)
    a = WEB.metadados_prontos(servidor.repo, st, grande, "/dicomweb")
    meta = json.loads(a[0])
    assert len(meta) == NZ and all("7FE00010" in d and "00020010" in d for d in meta)
    # o mesmo de novo: o guardado (o mesmo objeto)
    assert WEB.metadados_prontos(servidor.repo, st, grande, "/dicomweb")[0] is a[0]
    # um arquivo mudou: lê de novo
    um = next(iter(WEB.CAMINHOS.da_serie(servidor.repo, grande).values()))
    os.utime(um, (time.time() + 5, time.time() + 5))
    b = WEB.metadados_prontos(servidor.repo, st, grande, "/dicomweb")
    assert b[0] is not a[0] and json.loads(b[0]) == meta


def test_paralelo_igual_ao_sequencial(servidor, monkeypatch):
    st, series = _series(servidor)
    grande = next(s for s in series if len(WEB.CAMINHOS.da_serie(servidor.repo, s)) == NZ)
    par = WEB.metadados_da_serie(servidor.repo, st, grande, "/x")
    monkeypatch.setattr(WEB, "_LEITORES", 1)
    seq = WEB.metadados_da_serie(servidor.repo, st, grande, "/x")
    assert par == seq and len(par) == NZ
