"""0.85: regra de encaminhamento por listas — origem (AE title), meu AE que recebeu e modalidade.

Pedido dele: "quero criar regras podendo selecionar origem (aetitle), qual ae meu recebeu,
modalidade e daí criar regras diferentes"."""
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.printing import config as C
from ipe.printing import dispatch as D
from ipe.printing import held as H
from ipe.printing import origins as O
from ipe.printing import rules as R
from ipe.ui import print_settings as PS


def _s(paths):
    s = Settings(paths.settings_file)
    C.save_servers(s, [C.ServerConfig(name="Mamografia", ae_title="PRNMG", port=11113),
                       C.ServerConfig(name="Tomografia", ae_title="PRNCT", port=11114)])
    O.save_origins(s, [O.Origin(calling_ae="HOLOGIC1", remote_host="10.0.0.5", server="Mamografia",
                                name="Mamógrafo sala 1", modality="MG"),
                       O.Origin(calling_ae="CT_SALA2", remote_host="10.0.0.6", server="Tomografia",
                                name="TC sala 2")])
    D.save_destinations(s, [D.Destination(name="DRYVIEW", kind="pdf", folder="/tmp/a"),
                            D.Destination(name="PDF", kind="pdf", folder="/tmp/b")])
    s.save()
    return s


def test_regra_por_listas(env):
    paths, _db, _repo = env
    s = _s(paths)
    R.save_rules(s, [
        R.Rule(name="Mamo no filme", calling_aes=["HOLOGIC1"], servers=["Mamografia"], modalities=["MG"],
               destination="DRYVIEW"),
        R.Rule(name="TC ou RM em PDF", servers=["Tomografia"], modalities=["CT", "MR"], destination="PDF"),
    ])
    base = {"received_at": datetime.now(), "sheets": 1}
    mamo = dict(base, calling_ae="hologic1", server="Mamografia", modality="MG")
    assert H.alvos(s, mamo) == [("DRYVIEW", "")]                 # AE sem diferenciar maiúscula
    assert H.alvos(s, dict(mamo, server="Tomografia")) == []      # outro AE meu recebeu
    assert H.alvos(s, dict(mamo, modality="US")) == []            # outra modalidade
    assert H.alvos(s, dict(mamo, calling_ae="OUTRO")) == []       # outra origem
    tc = dict(base, calling_ae="CT_SALA2", server="Tomografia")
    assert H.alvos(s, dict(tc, modality="CT")) == [("PDF", "")]
    assert H.alvos(s, dict(tc, modality="MR")) == [("PDF", "")]
    assert H.alvos(s, dict(tc, modality="")) == []                # modalidade desconhecida
    # gravada e lida de volta
    lidas = R.all_rules(Settings(paths.settings_file))
    assert lidas[0].calling_aes == ["HOLOGIC1"] and lidas[1].modalities == ["CT", "MR"]
    assert "de HOLOGIC1" in lidas[0].label_text() and "recebido em Mamografia" in lidas[0].label_text()


def test_regra_antiga_continua_valendo(env):
    paths, _db, _repo = env
    s = _s(paths)
    velha = R.Rule.from_dict({"name": "antiga", "server": "Mamografia", "modality": "MG|US",
                              "destination": "PDF"})
    assert velha.servidores() == ["Mamografia"] and velha.modalidades() == ["MG", "US"]
    assert R.matches(velha, H.job_of({"received_at": datetime.now()}), "Mamografia", "", "US")
    assert not R.matches(velha, H.job_of({"received_at": datetime.now()}), "Tomografia", "", "US")
    # aberta no editor e salva: os campos antigos viram as listas
    _app = QApplication.instance() or QApplication([])
    ed = PS.RuleEditor(velha, s)
    assert ed.l_servers.marcados() == ["Mamografia"] and ed.l_mods.marcados() == ["MG", "US"]
    nova = ed.rule()
    assert (nova.server, nova.modality, nova.servers, nova.modalities) == \
        ("", "", ["Mamografia"], ["MG", "US"])


def test_editor_com_as_tres_listas(env):
    paths, _db, _repo = env
    _app = QApplication.instance() or QApplication([])
    s = _s(paths)
    ed = PS.RuleEditor(None, s)
    aes = [ed.l_aes.item(i).text() for i in range(ed.l_aes.count())]
    assert aes == ["CT_SALA2 — TC sala 2", "HOLOGIC1 — Mamógrafo sala 1"]
    srv = [ed.l_servers.item(i).text() for i in range(ed.l_servers.count())]
    assert srv == ["PRNMG (porta 11113) — Mamografia", "PRNCT (porta 11114) — Tomografia"]
    mods = [ed.l_mods.item(i).text() for i in range(ed.l_mods.count())]
    assert mods[:3] == ["MG", "CT", "MR"]
    assert not ed.caixa_outras.isVisibleTo(ed)                    # regra nova: "outras" fechadas
    ed.name.setText("Mamo")
    ed.l_aes.marcar(["HOLOGIC1"])
    ed.l_servers.marcar(["Mamografia"])
    ed.l_mods.marcar(["MG"])
    ed.novo_ae.setText("ge_novo")                                 # AE que ainda não mandou nada
    ed._mais_ae()
    assert "GE_NOVO" in ed.l_aes.marcados()
    ed.dest.setCurrentIndex(ed.dest.findData("DRYVIEW"))
    assert "modalidade MG" in ed.resumo.text()
    r = ed.rule()
    assert (r.calling_aes, r.servers, r.modalities, r.destination) == \
        (["HOLOGIC1", "GE_NOVO"], ["Mamografia"], ["MG"], "DRYVIEW")
    # regra com rótulo abre com "outras condições" à vista
    ed2 = PS.RuleEditor(R.Rule(label="MAMA*"), s)
    assert ed2.caixa_outras.isVisibleTo(ed2)


def test_tabela_de_regras(env):
    paths, _db, _repo = env
    app = QApplication.instance() or QApplication([])
    s = _s(paths)
    R.save_rules(s, [R.Rule(name="Mamo", calling_aes=["HOLOGIC1"], servers=["Mamografia"], modalities=["MG"],
                            destination="DRYVIEW"),
                     R.Rule(name="Resto", destination="PDF", label="X*", stop=False)])
    j = PS.PrintSettingsDialog(s, None)
    t = j.w_regra.list
    cab = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    assert cab[:5] == ["Ligada", "Nome", "Origem (AE)", "Recebido por", "Modalidade"]
    assert [t.item(0, c).text() for c in range(1, 5)] == ["Mamo", "HOLOGIC1", "PRNMG (Mamografia)", "MG"]
    assert [t.item(1, c).text() for c in range(2, 5)] == ["qualquer"] * 3
    assert "rótulo com X*" in t.item(1, 5).text() and t.item(1, 8).text() == "não"
    # a caixa desliga a regra; ▼ muda a ordem
    t.item(0, 0).setCheckState(Qt.Unchecked)
    app.processEvents()
    assert j.rules[0].enabled is False
    t.setCurrentRow(0)
    j._mover(1)
    assert [r.name for r in j.rules] == ["Resto", "Mamo"] and t.currentRow() == 1
    j._salvar()
    assert [(r.name, r.enabled) for r in R.all_rules(s)] == [("Resto", True), ("Mamo", False)]
