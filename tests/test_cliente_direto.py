"""0.100.38: o download do modo cliente mais rápido — o servidor manda as colunas de cada imagem junto, o cliente grava
o arquivo direto no lugar e a linha no banco sem reler o cabeçalho; as amostras de todas as séries vêm num pedido só.
O resultado tem que ser o mesmo do caminho de sempre (o importador lendo cada arquivo), e um servidor de versão
anterior continua funcionando."""
import threading

import pytest
from sqlalchemy import select

from test_central import central  # noqa: F401  (fixture)
from ipe.central.client_repo import ClientRepository
from ipe.central.remote import RemoteClient
from ipe.db.models import Instance, Series
from ipe.db.repository import Repository
from ipe.db.session import Database


def _cliente(srv, pasta):
    client = RemoteClient(f"http://127.0.0.1:{srv.port}")
    client.login("admin", "admin123")
    db = Database(pasta / "cache.sqlite")
    return ClientRepository(Repository(db), client, pasta / "Storage"), db


def _linhas(db):
    with db.session() as s:
        q = select(Instance, Series.series_uid).join(Series, Instance.series_fk == Series.id)
        return {i.sop_uid: (su, i.sop_class_uid, i.instance_number, i.transfer_syntax, i.rows, i.columns,
                            i.number_of_frames, i.image_position, i.image_orientation, i.slice_location,
                            i.acquisition_time, i.file_size, i.in_storage)
                for i, su in s.execute(q)}


@pytest.mark.parametrize("htj2k", [True, False])
def test_direto_grava_o_mesmo_que_o_importador(central, tmp_path, monkeypatch, htj2k):  # noqa: F811
    paths, db, repo, srv = central
    uid = repo.find_study_uids(accession="ACC1001")[0]
    if htj2k:                                        # as cópias de envio prontas, como nos exames recentes
        from ipe.central import envio
        for f in repo.files_for_study(uid):
            envio.arquivo_para_rede(f)
    monkeypatch.setattr(ClientRepository, "rede_htj2k", lambda self: htj2k)
    a, db_a = _cliente(srv, tmp_path / "a")
    b, db_b = _cliente(srv, tmp_path / "b")
    monkeypatch.setattr(ClientRepository, "DIRETO", True)
    lidos = []
    from ipe.importer import scanner
    ler = scanner.Importer._ler_cabecalho
    monkeypatch.setattr(scanner.Importer, "_ler_cabecalho", lambda self, f, r: (lidos.append(f), ler(self, f, r))[1])
    ev = threading.Event()
    n = a.download(uid, primeiro_lote=ev)
    series = repo.series_for_study(uid)
    assert n == sum(s.num_images for s in series)
    assert len(lidos) == len(series)                 # só a amostra de cada série passou pelo importador
    monkeypatch.setattr(ClientRepository, "DIRETO", False)
    assert b.download(uid, primeiro_lote=threading.Event()) == n
    la, lb = _linhas(db_a), _linhas(db_b)
    assert len(la) == n and la == lb                 # as mesmas colunas, imagem por imagem
    # os arquivos estão no lugar de sempre e são os mesmos
    for cache, d in ((a, db_a), (b, db_b)):
        with d.session() as s:
            caminhos = list(s.scalars(select(Instance.file_path)))
        assert all(str(cache.storage) in c for c in caminhos)
        assert not any((cache.storage / ".chegando").rglob("*.dcm"))
        assert not any(cache.storage.rglob("*.parte"))
    import filecmp
    with db_a.session() as s:
        pa = dict(s.execute(select(Instance.sop_uid, Instance.file_path)).all())
    with db_b.session() as s:
        pb = dict(s.execute(select(Instance.sop_uid, Instance.file_path)).all())
    assert all(filecmp.cmp(pa[k], pb[k], shallow=False) for k in pa)
    # o exame abre do cache: a série lê as imagens na ordem
    assert {s.series_uid: s.num_images for s in a.local.series_for_study(uid)} == \
        {s.series_uid: s.num_images for s in series}


def test_sem_amostras_a_serie_nasce_pelo_importador(central, tmp_path):  # noqa: F811
    """Download sem a etapa das amostras (linha de comando): a 1ª leva de cada série cria paciente, exame e série
    pelo arquivo; as seguintes entram direto."""
    paths, db, repo, srv = central
    uid = repo.find_study_uids(accession="ACC1001")[0]
    a, db_a = _cliente(srv, tmp_path / "a")
    n = a.download(uid)
    assert n == sum(s.num_images for s in repo.series_for_study(uid)) == len(_linhas(db_a))
    assert a.download(uid) == 0                      # nada falta


def test_servidor_de_versao_anterior(central, tmp_path, monkeypatch):  # noqa: F811
    """Servidor antes da 0.100.38: não conhece …/amostras nem manda as colunas — o cliente cai no caminho de
    sempre (uma amostra por série, importador lendo cada arquivo)."""
    from ipe.central import dicomweb as DW
    from ipe.central import server as SRV
    paths, db, repo, srv = central
    uid = repo.find_study_uids(accession="ACC1001")[0]
    rota = SRV._Handler._dicomweb

    def antiga(self, method, path, q, s):
        if path.rstrip("/").endswith("/amostras"):
            return self._error(404, "rota DICOMweb desconhecida")
        if self.headers.get("X-Ipe-Cliente"):
            del self.headers["X-Ipe-Cliente"]
        return rota(self, method, path, q, s)
    monkeypatch.setattr(SRV._Handler, "_dicomweb", antiga)
    assert DW.META == "X-Ipe-Meta"
    a, db_a = _cliente(srv, tmp_path / "a")
    ev = threading.Event()
    n = a.download(uid, primeiro_lote=ev)
    series = repo.series_for_study(uid)
    assert ev.is_set() and n == sum(s.num_images for s in series) == len(_linhas(db_a))
    assert not any((a.storage / ".chegando").rglob("*.dcm"))


def test_importador_em_lotes_ignora_repetidas_e_move(env, sample_dir, tmp_path):
    """O importador em lotes: uma consulta por lote para saber o que já está no banco; reimportar não duplica;
    `mover` leva o arquivo para o armazenamento sem deixar a cópia."""
    import shutil

    from ipe.importer.scanner import Importer
    paths, db, repo = env
    r1 = Importer(db, paths.storage).import_paths([sample_dir], batch_size=7)
    assert r1.added > 0 and r1.duplicates == 0
    r2 = Importer(db, paths.storage).import_paths([sample_dir], batch_size=7)
    assert r2.added == 0 and r2.duplicates == r1.added
    with db.session() as s:
        assert len(list(s.scalars(select(Instance.id)))) == r1.added
    # mover
    db2 = Database(tmp_path / "m" / "dicomviewer.sqlite")
    copia = tmp_path / "copia"
    shutil.copytree(sample_dir, copia)
    r3 = Importer(db2, tmp_path / "m" / "Storage", mover=True).import_paths([copia])
    assert r3.added == r1.added and not any(copia.rglob("*.dcm"))
    assert len(list((tmp_path / "m" / "Storage").rglob("*.dcm"))) == r1.added
