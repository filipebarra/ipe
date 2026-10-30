"""0.86: filme automático por regras — origem (AE de quem mandou), meu AE chamado e modalidade,
cada regra com a sua grade, papel, quantidade de imagens e destino."""
import socket
from pathlib import Path

import pydicom
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.printing import auto_film as AF
from ipe.printing import config as C
from ipe.printing import dispatch as D


def test_combina_e_escolhe(env):
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    AF.save_rules(s, [
        AF.AutoRule(name="Desligada", enabled=False, rows=9),
        AF.AutoRule(name="US da sala 1", calling_aes=["LOGIQ1"], my_aes=["US_FILME"], modalities=["US"], rows=3),
        AF.AutoRule(name="US de mama", modalities=["US"], description="MAMA|AXILA", rows=2, cols=1),
        AF.AutoRule(name="Qualquer US", modalities=["US"], rows=1, cols=1),
    ])
    assert AF.escolher(s, "logiq1", "us_filme", "US", "").name == "US da sala 1"
    assert AF.escolher(s, "LOGIQ1", "DICOMVIEWER", "US", "US MAMAS").name == "US de mama"   # outro AE meu
    assert AF.escolher(s, "OUTRO", "", "US", "US AXILA DIREITA").name == "US de mama"
    assert AF.escolher(s, "OUTRO", "", "US", "TIREOIDE").name == "Qualquer US"
    assert AF.escolher(s, "OUTRO", "", "CT", "") is None
    assert AF.escolher(s, "OUTRO", "", "CT\\US", "") is not None                         # várias modalidades
    assert "chamando US_FILME" in AF.all_rules(s)[1].label_text()


def test_configuracao_antiga_vira_a_primeira_regra(env):
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    assert AF.all_rules(s) == []                                     # nunca configurado: nada monta
    AF.save(s, AF.AutoFilm(enabled=True, modalities="US, MG", rows=3, cols=2, max_images=6,
                           destination="PDF"))
    [r] = AF.all_rules(s)
    assert (r.enabled, r.modalities, r.rows, r.cols, r.max_images, r.destination) == \
        (True, ["US", "MG"], 3, 2, 6, "PDF")
    AF.save(s, AF.AutoFilm(enabled=False))
    assert [x.enabled for x in AF.all_rules(s)] == [False] and not AF.alguma_ligada(s)


def test_monta_pela_regra_do_remetente(env, sample_dir):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    s = Settings(paths.settings_file)
    estudo = repo.search_studies()[0]
    mod = (estudo.modalities or "OT").split(",")[0].strip()
    AF.save_rules(s, [AF.AutoRule(name="Sala 1", calling_aes=["SALA1"], modalities=[mod], rows=3, cols=1,
                                  max_images=2, destination="DRY"),
                      AF.AutoRule(name="Outras", modalities=[mod], rows=1, cols=2, max_images=1)])
    fid, regra = AF.montar_para_estudo(repo, s, estudo.study_uid, {"calling_ae": "SALA1", "my_ae": "X"})
    from ipe.printing.film import Film
    filme = Film.from_dict(repo.film_data(fid))
    assert regra.name == "Sala 1" and regra.destination == "DRY"
    assert filme.sheets[0].rows == 3 and filme.image_count() <= 2
    assert AF.montar_para_estudo(repo, s, estudo.study_uid, {"calling_ae": "SALA1"}) == (None, None)  # não repete
    outro = repo.search_studies()[1]
    fid2, regra2 = AF.montar_para_estudo(repo, s, outro.study_uid, None)    # sem remetente: cai na geral
    if (outro.modalities or "").split(",")[0].strip() == mod:
        assert regra2.name == "Outras" and Film.from_dict(repo.film_data(fid2)).sheets[0].cols == 2


def _porta():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


def test_no_dicom_anota_quem_mandou_e_qual_ae_meu(tmp_path, sample_dir):
    from pynetdicom import AE
    from pynetdicom.presentation import StoragePresentationContexts

    from ipe.db.repository import Repository
    from ipe.db.session import Database
    from ipe.network.server import DicomServer
    from ipe.network.sink import IncomingSink
    storage = tmp_path / "Storage"
    storage.mkdir()
    db = Database(tmp_path / "db.sqlite")
    repo = Repository(db)
    sink = IncomingSink(db, repo, storage)
    porta = _porta()
    srv = DicomServer(repo, sink, {"ae_title": "DICOMVIEWER", "port": porta, "accept": "any", "timeout": 10})
    assert srv.start()
    try:
        arq = sorted(Path(sample_dir).rglob("*.dcm"))[0]
        ds = pydicom.dcmread(arq)
        ae = AE(ae_title="LOGIQ1")
        ae.requested_contexts = [c for c in StoragePresentationContexts
                                 if c.abstract_syntax == ds.SOPClassUID][:1] or StoragePresentationContexts[:20]
        assoc = ae.associate("127.0.0.1", porta, ae_title="US_FILME")     # um AE "meu" que não é o do nó
        assert assoc.is_established
        st = assoc.send_c_store(ds)
        assoc.release()
        assert getattr(st, "Status", 1) == 0
        rem = sink.remetentes[str(ds.StudyInstanceUID)]
        assert rem["calling_ae"] == "LOGIQ1" and rem["my_ae"] == "US_FILME" and rem["remote_host"]
    finally:
        srv.stop()
        sink.stop()


def test_aba_automatico_com_tabela_e_editor(env, monkeypatch):
    paths, _db, repo = env
    app = QApplication.instance() or QApplication([])
    s = Settings(paths.settings_file)
    s.set("dicom", dict(s.get("dicom", {}) or {}, ae_title="DICOMVIEWER", port=11112))
    C.save_servers(s, [C.ServerConfig(name="Ultrassom", ae_title="PRNUS", port=11115)])
    D.save_destinations(s, [D.Destination(name="DRY", kind="pdf", folder="/tmp/x")])
    AF.save(s, AF.AutoFilm(enabled=True, modalities="US", rows=2, cols=2))      # vem da versão anterior
    repo.save_node({"name": "Logiq sala 1", "ae_title": "LOGIQ1", "host": "10.0.0.9", "port": 104})
    from ipe.ui import print_settings as PS
    j = PS.PrintSettingsDialog(s, None, repo=repo)
    t = j.w_auto.list
    assert t.rowCount() == 1 and t.item(0, 1).text() == "Filme automático" and t.item(0, 4).text() == "US"
    # o editor mostra quem já mandou e os AEs meus
    ed = PS.AutoRuleEditor(None, s, repo=repo)
    assert "LOGIQ1 — Logiq sala 1" in [ed.l_aes.item(i).text() for i in range(ed.l_aes.count())]
    meus = [ed.l_meus.item(i).data(Qt.UserRole) for i in range(ed.l_meus.count())]
    assert meus == ["DICOMVIEWER", "PRNUS"]
    ed.name.setText("Sala 1")
    ed.l_aes.marcar(["LOGIQ1"])
    ed.novo_meu.setText("us_filme")
    ed._mais(ed.novo_meu, ed.l_meus, "(outro nome)")
    ed.l_mods.marcar(["US"])
    ed.rows.setValue(3)
    ed.dest.setCurrentIndex(ed.dest.findData("DRY"))
    nova = ed.regra()
    assert (nova.calling_aes, nova.my_aes, nova.modalities, nova.rows, nova.destination) == \
        (["LOGIQ1"], ["US_FILME"], ["US"], 3, "DRY")
    assert "chamando US_FILME" in ed.resumo.text()
    # pela aba: nova regra, sobe para o topo, salva
    monkeypatch.setattr(PS.AutoRuleEditor, "exec", lambda self: 1)
    monkeypatch.setattr(PS.AutoRuleEditor, "regra", lambda self: nova)
    j._nova_auto()
    assert t.rowCount() == 2 and t.item(1, 2).text() == "LOGIQ1" and t.item(1, 3).text() == "US_FILME"
    j._mover_auto(-1)
    t.item(1, 0).setCheckState(Qt.Unchecked)                      # desliga a antiga
    app.processEvents()
    j.af_rows.setValue(4)
    j._salvar()
    lidas = AF.all_rules(Settings(paths.settings_file))
    assert [(r.name, r.enabled) for r in lidas] == [("Sala 1", True), ("Filme automático", False)]
    assert AF.config(Settings(paths.settings_file)).rows == 4     # grade padrão da porta da impressora
