"""0.83: Duplicar nas configurações de impressão, e o painel contando o que chegou pronto
pela impressora DICOM."""
from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from ipe.core import film_stats as F
from ipe.core.config import Settings
from ipe.printing import config as C
from ipe.printing import dispatch as D
from ipe.printing import layout as L
from ipe.printing import rules as R
from ipe.ui import print_settings as PS


def test_nome_de_copia():
    assert PS.nome_de_copia("Mamo", ["Mamo"]) == "Mamo (cópia)"
    assert PS.nome_de_copia("Mamo", ["Mamo", "Mamo (cópia)"]) == "Mamo (cópia 2)"
    assert PS.nome_de_copia("Mamo (cópia)", ["Mamo", "Mamo (cópia)"]) == "Mamo (cópia 2)"


def _aceita(dlg):
    """Editor que só dá OK (o duplicar abre a cópia para conferir)."""
    if hasattr(dlg, "_ok"):
        dlg._ok()
    else:
        dlg.accept()
    return dlg.result()


def test_duplicar_em_cada_aba(env, monkeypatch):
    paths, _db, _repo = env
    _app = QApplication.instance() or QApplication([])
    s = Settings(paths.settings_file)
    C.save_servers(s, [C.ServerConfig(name="Mamografia", ae_title="PRNMG", port=11113, keep_days=30)])
    D.save_destinations(s, [D.Destination(name="PDF sala", kind="pdf", folder="/tmp/x", template="Clínica")])
    R.save_rules(s, [R.Rule(name="MG para PDF", calling_ae="MG*", destination="PDF sala"),
                     R.Rule(name="Resto", destination="PDF sala")])
    L.save_templates(s, [L.SheetTemplate(name="Clínica", clinic="IMEB", rows=2, cols=3)])
    s.save()
    from ipe.ui.prints_tab import DestinationEditor
    for cls in (PS.ServerEditor, DestinationEditor, PS.RuleEditor, PS.TemplateEditor):
        monkeypatch.setattr(cls, "exec", _aceita)
    j = PS.PrintSettingsDialog(s, None)

    j.t_serv.selectRow(0)
    j._duplicar_servidor()
    assert [x.name for x in j.servers] == ["Mamografia", "Mamografia (cópia)"]
    assert j.servers[1].port != j.servers[0].port and j.servers[1].ae_title == "PRNMG"
    assert j.servers[1].keep_days == 30                      # campo que o editor não mostra

    j.w_dest.list.setCurrentRow(0)
    j._duplicar_destino()
    assert [d.name for d in j.dests] == ["PDF sala", "PDF sala (cópia)"]
    assert j.dests[1].folder == "/tmp/x" and j.dests[1].template == "Clínica"

    j.w_regra.list.setCurrentRow(0)
    j._duplicar_regra()                                      # entra logo abaixo da original
    assert [r.name for r in j.rules] == ["MG para PDF", "MG para PDF (cópia)", "Resto"]
    assert j.rules[1].calling_ae == "MG*" and j.w_regra.list.currentRow() == 1

    j.w_modelo.list.setCurrentRow(0)
    j._duplicar_modelo()
    assert [m.name for m in j.templates][-1] == "Clínica (cópia)"
    assert (j.templates[-1].clinic, j.templates[-1].rows, j.templates[-1].cols) == ("IMEB", 2, 3)

    j._salvar()
    s2 = Settings(paths.settings_file)
    assert len(C.all_servers(s2)) == 2 and len(R.all_rules(s2)) == 3
    assert C.all_servers(s2)[1].keep_days == 30


def test_editar_destino_nao_perde_o_modelo(env):
    paths, _db, _repo = env
    _app = QApplication.instance() or QApplication([])
    s = Settings(paths.settings_file)
    from ipe.ui.prints_tab import DestinationEditor
    dlg = DestinationEditor(D.Destination(name="A", kind="pdf", folder="/tmp", template="Clínica"), s)
    dlg.name.setText("B")
    assert dlg.destination().template == "Clínica" and dlg.destination().name == "B"


def test_duplicar_impressora_dicom(env):
    paths, _db, _repo = env
    _app = QApplication.instance() or QApplication([])
    s = Settings(paths.settings_file)
    s.set("printing.dicom_printers", [{"name": "DRYVIEW", "ae_title": "DRY", "host": "10.0.0.5", "port": 104}])
    from ipe.ui.film.dialogs import DicomPrintDialog
    dlg = DicomPrintDialog(s, "LOCAL", 1, 0)
    dlg.list.setCurrentRow(0)
    dlg._duplicate()
    assert [p["name"] for p in dlg.printers] == ["DRYVIEW", "DRYVIEW (cópia)"]
    assert dlg.list.currentRow() == 1 and dlg.f_host.text() == "10.0.0.5"
    dlg.save()
    assert len(s.get("printing.dicom_printers")) == 2


def test_painel_conta_a_impressao_dicom(env, sample_dir):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    s = Settings(paths.settings_file)
    estudo = next(e for e in repo.search_studies() if e.patient_id == "FANT003")
    exame = F.hora_do_exame(estudo.study_date, estudo.study_time)
    from ipe.printing import origins as O
    O.save_origins(s, [O.Origin(calling_ae="NM1", remote_host="10.0.0.9", server="Medicina",
                                name="Gama câmara")])
    s.save()
    chegou = exame + timedelta(hours=1)
    jid = repo.add_print_job(uid="a", source="scp", calling_ae="NM1", remote_host="10.0.0.9",
                             server="Medicina", sheets=2, images=8, patient_name="CINTILO^PEDRO",
                             patient_id="FANT003", study_uid="1.2.3.folhas", received_at=chegou,
                             status="new")
    repo.update_print_job(jid, status="sent", destination="DRYVIEW", sent_at=chegou + timedelta(hours=2))
    repo.add_print_job(uid="b", source="scp", calling_ae="CT9", sheets=1, images=4, received_at=datetime.now(),
                       status="new")

    rows = repo.print_job_stats_rows()
    assert len(rows) == 2
    um = next(r for r in rows if r["patient_name"])
    assert um["modalities"] == ["NM"] and um["printed_at"] == chegou + timedelta(hours=2)

    from ipe.ui.film_dashboard import COLUNAS, FilmDashboard
    d = FilmDashboard(repo, s)
    d.c_periodo.setCurrentIndex(d.c_periodo.findData("tudo"))
    app.processEvents()
    assert d.k_filmes.l_valor.text() == "2" and "impressão DICOM: 2" in d.k_filmes.l_detalhe.text()
    assert d.k_impressos.l_valor.text() == "50%"
    col = {c: i for i, c in enumerate(COLUNAS)}
    linhas = {d.t_filmes.item(i, col["Criado por"]).text(): i for i in range(d.t_filmes.rowCount())}
    assert set(linhas) == {"Gama câmara", "CT9"}              # nome cadastrado, ou o AE
    i = linhas["Gama câmara"]
    assert d.t_filmes.item(i, col["Origem"]).text() == "Impressão DICOM"
    assert d.t_filmes.item(i, col["Modalidade"]).text() == "NM"
    assert d.t_filmes.item(i, col["Exame → filme"]).text() == "1,0 h"
    assert d.t_filmes.item(i, col["Filme → impressão"]).text() == "2,0 h"
    # filtro por origem
    d.c_tipo.setCurrentIndex(d.c_tipo.findData("filme"))
    assert d.t_filmes.rowCount() == 0
    d.c_tipo.setCurrentIndex(d.c_tipo.findData("dicom"))
    assert d.t_filmes.rowCount() == 2
    # duplo clique na impressão DICOM abre o exame das folhas
    abertos = []
    d.abrir_exame.connect(abertos.append)
    linhas = {d.t_filmes.item(i, col["Criado por"]).text(): i for i in range(d.t_filmes.rowCount())}
    d._abrir_linha(d.t_filmes.model().index(linhas["Gama câmara"], 0))
    assert abertos == ["1.2.3.folhas"]
    d.deleteLater()
    _ = Qt, QDialog
