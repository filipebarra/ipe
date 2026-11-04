"""0.99.54 — onda B5 (IA no texto do laudo) e a base de segredos cifrados."""
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.core import laudo_ia as LI
from ipe.core import segredos as SG
from ipe.core.config import Settings


@pytest.fixture(autouse=True)
def _chave(tmp_path, monkeypatch):
    monkeypatch.setattr(SG, "PASTA", tmp_path / "chave")
    monkeypatch.setenv("IPE_SEGREDO_ARQUIVO", "1")


def test_segredos():
    c = SG.guardar("minha senha ç")
    assert c.startswith("enc1:k:") and "minha" not in c
    assert SG.abrir(c) == "minha senha ç" and SG.guardar(c) == c
    assert SG.abrir("texto antigo") == "texto antigo" and SG.guardar("") == ""
    assert SG.guardar("x") != SG.guardar("x")                         # nonce novo a cada vez
    ruim = c[:-6] + ("A" if c[-6] != "A" else "B") + c[-5:]
    with pytest.raises(SG.SegredoInvalido):
        SG.abrir(ruim)
    assert SG.abrir_ou_vazio(ruim) == ""


def test_conferencia_local():
    t = ("US DE ABDOME\nFígado medindo 15 com contornos regulares.\nNódulo de de 12 mm no rim direito esquerdo.\n"
         "Útero de dimensões normais.\nLesão de 900 mm.\nComparação: ___\nIMPRESSÃO:\nCisto no rim esquerdo.")
    av = LI.conferir(t, None, {"sex": "M"})
    msgs = [a["msg"] for a in av]
    assert "medida sem unidade" in msgs and "palavra repetida" in msgs and "lateralidade dupla" in msgs
    assert "órgão feminino em paciente do sexo masculino" in msgs and "campo não preenchido" in msgs
    assert "medida grande demais — conferir a unidade" in msgs
    assert av[0]["nivel"] == "erro"
    t2 = "Achados no lado direito.\nIMPRESSÃO:\nAlteração à esquerda."
    assert any("lado esquerdo" in a["msg"] for a in LI.conferir(t2))
    assert any(a["msg"] == "impressão / conclusão vazia" for a in LI.conferir("Corpo.\nCONCLUSÃO:\n"))
    f = {"kind": "mg", "cat_right": "4A", "cat_left": "1", "recommendation": "Recomenda-se rastreamento de rotina."}
    msgs = [a["msg"] for a in LI.conferir("BI-RADS® 2: benigno.", f)]
    assert any("formulário dá 4A" in m for m in msgs) and any("histopatológico" in m for m in msgs)
    assert LI.conferir("Mamografia sem alterações. BI-RADS® 1: Negativo.", {"kind": "mg", "cat_right": "1"}) == []
    assert "✖ medida sem unidade" in LI.texto_dos_avisos(LI.conferir("medindo 12 x 8"))


def test_anonimizar_e_provedores():
    info = {"patient_name": "SILVA^MARIA JOSE", "patient_id": "123456", "accession": "ACC9",
            "birth_date": "19700105", "sex": "F"}
    t, mapa = LI.anonimizar("Paciente Maria Jose Silva, ID 123456, nascida 05/01/1970, ACC9.", info)
    assert "Maria" not in t and "123456" not in t and "1970" not in t and "ACC9" not in t
    assert LI.restaurar(t, mapa).count("123456") == 1
    chamadas = []

    def falso(url, corpo, cab, tempo):
        chamadas.append((url, corpo, cab))
        txt = corpo["messages"][-1]["content"]
        assert "123456" not in txt and "Sexo do paciente: feminino" in txt
        if "/api/chat" in url:
            return {"message": {"content": "Texto revisado do [ID]."}}
        if "/chat/completions" in url:
            return {"choices": [{"message": {"content": "```\nImpressão.\n```"}}]}
        return {"content": [{"type": "text", "text": "Nenhum erro encontrado"}]}
    base = {"chave": "k", "tempo": 5}
    assert LI.pedir("refinar", "Laudo do 123456.", {**base, "provedor": "ollama", "url": "http://localhost:11434",
                                                    "modelo": "m"}, info, post=falso) == "Texto revisado do 123456."
    assert LI.pedir("impressao", "x", {**base, "provedor": "openai", "url": "http://h:1234", "modelo": "m"},
                    info, post=falso) == "Impressão."
    assert chamadas[-1][0] == "http://h:1234/v1/chat/completions" and chamadas[-1][2]["Authorization"] == "Bearer k"
    assert LI.pedir("erros", "x", {**base, "provedor": "anthropic", "url": "", "modelo": "claude"}, info,
                    post=falso) == "Nenhum erro encontrado"
    assert chamadas[-1][0] == "https://api.anthropic.com/v1/messages" and chamadas[-1][2]["x-api-key"] == "k"
    with pytest.raises(RuntimeError):
        LI.conversar({"provedor": ""}, "s", "u")
    assert LI.remoto({"url": "https://api.anthropic.com"}) and not LI.remoto({"url": "http://localhost:11434"})


def test_na_janela_do_laudo(env, sample_dir, monkeypatch):
    from ipe.importer.scanner import Importer
    from ipe.ui.laudo_ia_ui import LaudoIAConfigDialog, ResultadoDialog
    from ipe.ui.report_window import ReportWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    QApplication.instance() or QApplication([])
    st = Settings(paths.settings_file)
    uid = repo.search_studies()[0].study_uid
    rw = ReportWindow(repo, uid, st)
    try:
        rw.editor.setPlainText("Nódulo medindo 12 no fígado.")
        perguntas = []
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (perguntas.append(a[2]), QMessageBox.No)[1])
        rw.sign()
        assert "medida sem unidade" in perguntas[0] and not any(r["status"] != "draft" for r in repo.reports(uid))
        # configurar: chave guardada cifrada
        dlg = LaudoIAConfigDialog(st, testar=lambda *a: {"message": {"content": "OK"}})
        dlg.prov.setCurrentIndex(list(LI.PROVEDORES).index("ollama"))
        dlg.chave.setText("segredo")
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
        assert dlg.testar() == "OK"
        dlg._salvar()
        assert st.get("laudo_ia.chave").startswith("enc1:") and LI.config(st)["chave"] == "segredo"
        # refinar: a proposta só entra pelo botão
        monkeypatch.setattr(LI, "_post", lambda url, corpo, cab, tempo: {"message": {"content": "Nódulo medindo 12 mm."}})
        monkeypatch.setattr(ResultadoDialog, "exec", lambda self: (self._usar(), 1)[1])
        rw.ia.pedir("refinar", esperar=True)
        assert rw.editor.toPlainText() == "Nódulo medindo 12 mm."
        rw.editor.undo()
        assert rw.editor.toPlainText() == "Nódulo medindo 12 no fígado."
        rw.ia.aplicar("impressao", "\nIMPRESSÃO: nódulo.")
        assert rw.editor.toPlainText().endswith("IMPRESSÃO: nódulo.") or "IMPRESSÃO" in rw.editor.toPlainText()
        # conferência desligada: assina sem perguntar da conferência
        st.set("laudo_ia.conferir_ao_assinar", False)
        perguntas.clear()
        rw.editor.setPlainText("Nódulo medindo 12 no fígado.")
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (perguntas.append(a[2]), QMessageBox.Yes)[1])
        rw.sign()
        assert len(perguntas) == 1 and repo.reports(uid)[-1]["status"] == "final"
    finally:
        rw.close()
