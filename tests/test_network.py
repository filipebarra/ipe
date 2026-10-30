"""Rede DICOM em loopback: um "PACS" (outra instância do programa) e este computador."""
import socket
import threading
from pathlib import Path

import pytest

from ipe.db.repository import Repository
from ipe.db.session import Database
from ipe.importer.scanner import Importer
from ipe.network.client import DicomClient, DicomError, Target
from ipe.network.server import DicomServer
from ipe.network.sink import IncomingSink


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Node:
    """Banco + armazenamento + nó DICOM, como uma instância do programa."""

    def __init__(self, base: Path, ae: str, accept: str = "any"):
        self.storage = base / "Storage"
        self.storage.mkdir(parents=True)
        self.db = Database(base / "db.sqlite")
        self.repo = Repository(self.db)
        self.sink = IncomingSink(self.db, self.repo, self.storage)
        self.port = free_port()
        self.ae = ae
        self.server = DicomServer(self.repo, self.sink, {"ae_title": ae, "port": self.port,
                                                         "accept": accept, "timeout": 10})

    def as_node(self, **kw) -> dict:
        d = {"name": self.ae, "ae_title": self.ae, "host": "127.0.0.1", "port": self.port,
             "retrieve": "get", "move_destination": "", "use_in_search": True}
        d.update(kw)
        return d

    def close(self):
        self.server.stop()
        self.sink.stop()


@pytest.fixture()
def pair(tmp_path, sample_dir):
    pacs = Node(tmp_path / "pacs", "PACS")
    Importer(pacs.db, pacs.storage).import_paths([sample_dir])
    me = Node(tmp_path / "me", "DICOMVIEWER", accept="known")
    # cada um conhece o outro
    pacs.repo.save_node(me.as_node())
    me.repo.save_node(pacs.as_node())
    assert pacs.server.start() and me.server.start()
    yield pacs, me
    pacs.close()
    me.close()


def target(pacs, me, **kw):
    return Target.build(pacs.as_node(**kw), me.ae, kw.pop("identity", None) if "identity" in kw else None)


def test_echo_find_and_get(pair):
    pacs, me = pair
    c = DicomClient(timeout=10)
    t = Target.build(pacs.as_node(), me.ae)
    assert c.echo(t)[0]
    studies = c.find_studies(t, accession="ACC1001")
    assert len(studies) == 1 and studies[0]["modalities"] == "CT" and studies[0]["num_images"] == 60
    assert studies[0]["patient_name"] == "TESTE, Ana Maria"
    expected = [r for r in pacs.repo.search_studies() if r.patient_name.upper().startswith("TESTE")]
    assert len(c.find_studies(t, name="TESTE")) == len(expected) >= 2     # curinga automático
    assert len(c.find_studies(t, date_from="20000101", date_to="20991231", modality="MR")) == 1
    series = c.find_series(t, studies[0]["study_uid"])
    assert len(series) == 1 and series[0]["num_images"] == 60
    seen = []
    n = c.get(t, studies[0]["study_uid"], None, me.sink, progress=lambda d, tot, m: seen.append((d, tot)))
    assert n == 60 and seen[-1][1] == 60
    assert me.sink.flush(30)
    assert me.repo.counts()["instances"] == 60
    info = me.repo.study_info(studies[0]["study_uid"])
    assert info["accession"] == "ACC1001"
    assert me.repo.series_for_study(studies[0]["study_uid"])[0].thumbnail     # miniatura gerada


def test_move_and_series_level(pair):
    pacs, me = pair
    c = DicomClient(timeout=10)
    t = Target.build(pacs.as_node(retrieve="move"), me.ae)
    st = c.find_studies(t, accession="ACC2001")[0]
    series = c.find_series(t, st["study_uid"])
    assert len(series) == 2
    me.sink.expected_studies.add(st["study_uid"])
    n = c.move(t, st["study_uid"], [series[0]["series_uid"]])
    assert n == series[0]["num_images"]
    assert me.sink.flush(30)
    got = me.repo.series_for_study(st["study_uid"])
    assert len(got) == 1 and got[0].num_images == series[0]["num_images"]
    # destino desconhecido pelo PACS: mensagem clara
    t2 = Target.build(pacs.as_node(move_destination="OUTRO"), me.ae)
    with pytest.raises(DicomError, match="não conhece o destino"):
        c.move(t2, st["study_uid"], None)


def test_store_and_acl(pair):
    pacs, me = pair
    c = DicomClient(timeout=10)
    # PACS manda para mim (C-STORE): sou "known", o PACS está cadastrado
    uid = pacs.repo.find_study_uids(accession="ACC3001")[0]
    files = pacs.repo.files_for_study(uid)
    sent, failed = c.store(Target.build(me.as_node(), "PACS"), files)
    assert (sent, failed) == (len(files), 0)
    assert me.sink.flush(30) and me.repo.study_info(uid) is not None
    # AE desconhecido é recusado
    ok, msg = c.echo(Target.build(me.as_node(), "INTRUSO"))
    assert not ok and "recusou" in msg
    # identidade: calling AE diferente, aceito se cadastrado
    me.repo.save_node({"name": "WS2", "ae_title": "WS-MAMA2", "host": "127.0.0.1", "port": 1})
    me.server.refresh_acl()
    assert c.echo(Target.build(me.as_node(), "DICOMVIEWER", {"ae_title": "WS-MAMA2"}))[0]


def test_local_find_levels(pair, tmp_path):
    pacs, _me = pair
    from pydicom.dataset import Dataset
    from ipe.network import local_query
    q = Dataset()
    q.QueryRetrieveLevel = "IMAGE"
    q.StudyInstanceUID = pacs.repo.find_study_uids(accession="ACC3001")[0]
    q.SeriesInstanceUID = ""
    q.SOPInstanceUID = ""
    res = list(local_query.find(pacs.db, q))
    assert len(res) == 4 and all(r.SOPInstanceUID for r in res)
    q2 = Dataset()
    q2.QueryRetrieveLevel = "PATIENT"
    q2.PatientID = ""
    q2.PatientName = "TESTE*"
    assert len(list(local_query.find(pacs.db, q2))) >= 1
