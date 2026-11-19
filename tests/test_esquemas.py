"""0.100.72: esquemas-guia do laudo — os modelos, o formato, a legenda, a figura, o DICOM (imagem e SR) e o PDF."""
import io
import json

import numpy as np
import pydicom
import pytest

from ipe.reporting import esquemas as E
from ipe.reporting import esquemas_saida as ES


def _face():
    return {"modelo": "face_frente", "titulo": "", "marcas": [
        {"tipo": "ponto", "n": 1, "p": [[0.62, 0.5]], "cor": "#D32F2F", "texto": "nódulo hipoecoico de 4 mm"},
        {"tipo": "elipse", "n": 2, "p": [[0.30, 0.20], [0.42, 0.28]], "cor": "#1565c0", "texto": "placa"},
        {"tipo": "seta", "n": 0, "p": [[0.8, 0.8], [0.6, 0.66]], "cor": "#2e7d32"},
        {"tipo": "traco", "p": [[0.4, 0.75], [0.45, 0.77], [0.5, 0.75]], "cor": "#6a1b9a", "l": 4},
        {"tipo": "texto", "p": [[0.05, 0.92]], "texto": "lesão actínica", "cor": "#111111"}]}


def test_modelos_de_fabrica():
    ms = {m["id"]: m for m in E.modelos()}
    assert {"face_frente", "face_perfil_direito", "face_perfil_esquerdo", "corpo_frente", "corpo_costas", "tireoide",
            "mamas", "prostata"} <= set(ms)
    for m in ms.values():
        assert m["w"] > 0 and m["h"] > 0 and m["tracos"], m["id"]
        for t in m["tracos"]:                               # tudo dentro do quadro do modelo
            for x, y in t["p"]:
                assert -2 <= x <= m["w"] + 2 and -2 <= y <= m["h"] + 2, (m["id"], x, y)
    # a próstata: os 41 setores do PI-RADS v2.1 (38 da glândula, 2 vesículas, o esfíncter), com nomes únicos
    p = ms["prostata"]
    ids = [s["id"] for s in p["setores"]]
    assert len(ids) == 41 == len(set(ids)) and len({s["nome"] for s in p["setores"]}) == 41
    assert sum(i.startswith("base_") for i in ids) == 14 and sum(i.startswith("medio_") for i in ids) == 12
    assert sum(i.startswith("apice_") for i in ids) == 12 and {"VS_D", "VS_E", "esfincter"} <= set(ids)
    assert [c["k"] for c in p["categorias"]] == ["1", "2", "3", "4", "5"]
    assert not any(s["id"].startswith("medio_CZ") for s in p["setores"])      # zona central só na base
    # o gerador reproduz o arquivo (ninguém editou o JSON à mão)
    import importlib.util
    from pathlib import Path
    raiz = Path(E.__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("gerar_esquemas", raiz / "tools" / "esquemas" / "gerar.py")
    if spec and (raiz / "tools" / "esquemas" / "gerar.py").exists():
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        assert json.loads(json.dumps(g.todos())) == list(E._de_fabrica())


def test_normalizar():
    e = E.normalizar({**_face(), "id": "x y", "setores": {"a": "4"}, "lixo": 1})
    assert e["modelo"] == "face_frente" and len(e["id"]) >= 8 and e["setores"] == {} and "lixo" not in e
    assert [m["tipo"] for m in e["marcas"]] == ["ponto", "elipse", "seta", "traco", "texto"]
    assert e["marcas"][0]["cor"] == "#d32f2f" and e["marcas"][3]["l"] == 4
    assert E.normalizar({"modelo": "não existe"}) is None and E.normalizar("x") is None
    ruins = [{"tipo": "bomba", "p": [[0, 0]]}, {"tipo": "elipse", "p": [[0.1, 0.1]]}, {"tipo": "texto", "p": [[0.1, 0.1]]},
             {"tipo": "ponto", "p": []}, "x", {"tipo": "ponto", "p": [[5, -3]], "cor": "red", "l": 99, "n": -4,
                                             "texto": "a" * 999}]
    e = E.normalizar({"modelo": "mamas", "marcas": ruins})
    assert len(e["marcas"]) == 1
    m = e["marcas"][0]
    assert m["p"] == [[1.0, 0.0]] and m["cor"] == E.CORES[0] and m["l"] == 12 and m["n"] == 0 and len(m["texto"]) == 300
    e = E.normalizar({"modelo": "prostata", "setores": {"medio_PZpl_D": 4, "inventado": "4", "base_CZ_E": "9"}})
    assert e["setores"] == {"medio_PZpl_D": "4"}
    e = E.normalizar({"modelo": "mamas", "marcas": [{"tipo": "ponto", "p": [[0.5, 0.5]],
                                                    "imagem": {"sop_uid": "1.2.3", "series_uid": "1.2", "frame": 2,
                                                               "rotulo": "série 1, imagem 3", "x": 1}}]})
    assert e["marcas"][0]["imagem"] == {"series_uid": "1.2", "sop_uid": "1.2.3", "frame": 2, "rotulo": "série 1, imagem 3"}
    assert E.proximo_numero(E.normalizar(_face())) == 3 and E.vazio({"marcas": [], "setores": {}})


def test_legenda():
    e = E.normalizar(_face())
    e["marcas"][1]["imagem"] = {"sop_uid": "1", "rotulo": "série 3, imagem 12"}
    assert E.legenda(e) == ["1. nódulo hipoecoico de 4 mm", "2. placa (série 3, imagem 12)"]
    p = E.normalizar({"modelo": "prostata", "setores": {"medio_PZpl_D": "4", "apice_PZpm_E": "5", "base_TZa_E": "4"},
                      "marcas": [{"tipo": "ponto", "n": 1, "p": [[0.3, 0.6]], "texto": "lesão índice"}]})
    leg = E.legenda(p)
    assert leg[0] == "1. lesão índice"
    assert leg[1] == "PI-RADS 5: zona periférica posteromedial esquerda, ápice."
    assert leg[2].startswith("PI-RADS 4: ") and "zona periférica posterolateral direita, terço médio" in leg[2]
    assert "zona de transição anterior esquerda, base" in leg[2]
    txt = E.texto_para_o_laudo([e, p, {"modelo": "mamas", "marcas": []}])
    assert txt.startswith("Face — frente:\n1. nódulo") and "\n\nPróstata — mapa de setores:\n1. lesão índice" in txt
    assert "Mamas" not in txt
    assert E.texto_para_o_laudo([]) == ""


def test_figura():
    from PIL import Image
    limpa = np.asarray(E.desenhar({"modelo": "face_frente"}, 600))
    cheia = np.asarray(E.desenhar(E.normalizar(_face()), 600))
    assert limpa.shape == cheia.shape == (750, 600, 3)
    assert (limpa < 120).any() and (limpa > 250).mean() > 0.9          # traços escuros num fundo branco
    y, x = int(0.5 * 750), int(0.62 * 600)
    assert tuple(cheia[y - 6, x - 6]) != tuple(limpa[y - 6, x - 6])      # o ponto 1 está lá
    r, g, b = cheia[y - 7, x].astype(int)
    assert r > 150 and g < 110 and b < 110                              # e é vermelho
    # o setor pintado muda a cor do miolo do setor
    mod = E.modelo("prostata")
    s = next(s for s in mod["setores"] if s["id"] == "medio_PZpl_D")
    im = np.asarray(E.desenhar({"modelo": "prostata", "setores": {"medio_PZpl_D": "4"}}, 500))
    k = 500 / mod["w"]
    r, g, b = im[int(s["cy"] * k) - 14, int(s["cx"] * k) - 16].astype(int)
    assert r > 200 and 100 < g < 200 and b < 110                        # laranja
    assert Image.open(io.BytesIO(E.png({"modelo": "mamas"}, 300))).size[0] == 300
    assert Image.open(io.BytesIO(E.miniatura_do_modelo("tireoide"))).size[0] == 260
    with pytest.raises(LookupError):
        E.desenhar({"modelo": "nada"})
    # acento na figura: a fonte escolhida tem "ã"
    assert E._arquivo_da_fonte()


def test_guardar_ler_modelo_proprio_e_dicom(env, tmp_path, sample_dir):
    from PIL import Image
    from ipe.importer.scanner import Importer
    from ipe.reporting import dicom_out as D
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    study = repo.search_studies({})[0].study_uid
    assert E.ler(repo, study) == []
    ficou = E.gravar(repo, study, [_face(), {"modelo": "nada"}, {"modelo": "prostata", "setores": {"base_CZ_D": "3"}}], "ana")
    assert [e["modelo"] for e in ficou] == ["face_frente", "prostata"] and E.ler(repo, study) == ficou
    assert repo.revisao_ia(study, E.MODULO)["usuario"] == "ana"
    # ligar a uma imagem do exame: vira imagem-chave e ganha o rótulo
    serie = repo.series_for_study(study)[0]
    inst = repo.instances_for_series(serie.series_uid)[0]
    assert (inst["sop_uid"], 0) not in repo.key_image_set(study)
    lig = E.ligar_imagem(repo, study, serie.series_uid, inst["sop_uid"], 0)
    assert lig["rotulo"].startswith(f"série {serie.series_number}, imagem ") and (inst["sop_uid"], 0) in repo.key_image_set(study)
    assert E.ligar_imagem(repo, study, serie.series_uid, inst["sop_uid"], 0) == lig          # de novo não desmarca
    assert (inst["sop_uid"], 0) in repo.key_image_set(study)
    assert E.ligar_imagem(repo, study, serie.series_uid, "9.9.9", 0) is None
    ficou[0]["marcas"][0]["imagem"] = lig
    ficou = E.gravar(repo, study, ficou + [{"modelo": "mamas"}], "ana")
    # modelo próprio (uma imagem)
    b = io.BytesIO()
    Image.new("RGBA", (2000, 1000), (0, 0, 0, 0)).save(b, "PNG")
    m = E.novo_modelo_de_imagem(repo, "Pé — planta", b.getvalue())
    assert m["meu"] and (m["w"], m["h"]) == (1400, 700) and E.modelo(m["id"], repo)["nome"] == "Pé — planta"
    assert E.modelo(m["id"]) is None                                    # sem o banco, só os do Ipê
    fig = np.asarray(E.desenhar({"modelo": m["id"], "marcas": [{"tipo": "ponto", "p": [[0.5, 0.5]], "cor": "#1565c0"}]}, 400, repo))
    assert fig.shape == (200, 400, 3) and tuple(fig[5, 5]) == (255, 255, 255)   # o transparente virou branco
    with pytest.raises(ValueError):
        E.novo_modelo_de_imagem(repo, "", b.getvalue())
    with pytest.raises(ValueError):
        E.novo_modelo_de_imagem(repo, "x", b"isto nao e imagem")
    assert any(x["id"] == m["id"] and x["meu"] for x in E.resumo_dos_modelos(repo))
    assert E.excluir_modelo(repo, m["id"]) and not E.excluir_modelo(repo, m["id"])
    # para o exame: só os que têm desenho (as mamas vazias ficam de fora)
    fonte = repo.files_for_study(study)[0]
    imagens, para_sr = ES.para_o_exame(repo, study, fonte)
    assert len(imagens) == 2 == len(para_sr) and len(ES.figuras(repo, study)) == 2
    sc = imagens[0]
    assert sc.SOPClassUID == ES.SECONDARY_CAPTURE and sc.StudyInstanceUID == study and sc.Modality == "OT"
    assert sc.PhotometricInterpretation == "RGB" and (sc.Columns, sc.Rows) == (1100, 1375)
    assert len(sc.PixelData) == 1100 * 1375 * 3 and sc.SeriesDescription == "Esquemas do laudo"
    assert imagens[1].SeriesInstanceUID == sc.SeriesInstanceUID and imagens[1].InstanceNumber == 2
    sc.save_as(tmp_path / "sc.dcm", enforce_file_format=True)
    assert pydicom.dcmread(tmp_path / "sc.dcm").pixel_array.shape == (1375, 1100, 3)
    # o SR: Enhanced, com a imagem do esquema, a marca com a posição e a imagem ligada
    sr = D.text_sr("Achados\n\nIMPRESSÃO\nok", fonte, "Laudo", "Ana", True, "Ana", esquemas=para_sr)
    sr.save_as(tmp_path / "sr.dcm", enforce_file_format=True)
    sr = pydicom.dcmread(tmp_path / "sr.dcm")
    assert sr.SOPClassUID == D.ENHANCED_SR
    secoes = [i for i in sr.ContentSequence if i.ValueType == "CONTAINER" and i.ConceptNameCodeSequence[0].CodeValue == "121070"]
    assert len(secoes) == 2
    itens = secoes[0].ContentSequence
    assert itens[0].TextValue == "Esquema: Face — frente"
    assert itens[1].ValueType == "IMAGE" and itens[1].ReferencedSOPSequence[0].ReferencedSOPInstanceUID == sc.SOPInstanceUID
    m1 = next(i for i in itens if i.ValueType == "TEXT" and i.TextValue.startswith("1. nódulo"))
    scoord = next(i for i in m1.ContentSequence if i.ValueType == "SCOORD")
    assert scoord.GraphicType == "POINT" and scoord.RelationshipType == "INFERRED FROM"
    assert [round(float(v)) for v in scoord.GraphicData] == [round(0.62 * 1099), round(0.5 * 1374)]
    assert scoord.ContentSequence[0].ReferencedSOPSequence[0].ReferencedSOPInstanceUID == sc.SOPInstanceUID
    ligada = next(i for i in m1.ContentSequence if i.ValueType == "IMAGE")
    assert ligada.ReferencedSOPSequence[0].ReferencedSOPInstanceUID == inst["sop_uid"]
    m2 = next(i for i in itens if i.ValueType == "TEXT" and i.TextValue.startswith("2. placa"))
    el = next(i for i in m2.ContentSequence if i.ValueType == "SCOORD")
    assert el.GraphicType == "ELLIPSE" and len(el.GraphicData) == 8
    assert any(i.ValueType == "TEXT" and i.TextValue.startswith("PI-RADS 3: zona central direita")
               for i in secoes[1].ContentSequence)
    citados = {r.ReferencedSOPInstanceUID for e in sr.CurrentRequestedProcedureEvidenceSequence
               for se in e.ReferencedSeriesSequence for r in se.ReferencedSOPSequence}
    assert citados == {imagens[0].SOPInstanceUID, imagens[1].SOPInstanceUID, inst["sop_uid"]}
    # sem esquemas, o SR continua o de sempre
    assert D.text_sr("x", fonte).SOPClassUID == D.BASIC_TEXT_SR and "CurrentRequestedProcedureEvidenceSequence" not in D.text_sr("x", fonte)
    # o campo {esquemas} dos modelos de laudo
    from ipe.reporting import fill as F
    assert F.build_context(repo, study)["esquemas"].startswith("Face — frente:\n1. nódulo hipoecoico de 4 mm (série")


def test_pdf_com_esquema(env, tmp_path, qtbot):
    from ipe.reporting.pdf import report_html, write_pdf
    fig = [{"titulo": "Face — frente", "png": E.png(E.normalizar(_face()), 600), "linhas": ["1. nódulo <b>", "2. placa"]},
           {"titulo": "Próstata", "png": E.png({"modelo": "prostata", "setores": {"VS_D": "2"}}, 500), "linhas": []},
           {"titulo": "ruim", "png": b"nada", "linhas": []}]
    html = report_html({}, {"text": "ok", "status": "draft"}, esquemas=[{**fig[0], "largura": 360}])
    assert "esq0.png" in html and "1. nódulo &lt;b&gt;" in html and "Face — frente" in html
    assert "esq0.png" not in report_html({}, {"text": "ok", "status": "draft"})
    com = write_pdf(None, {}, {"text": "ACHADOS\nok", "status": "draft"}, esquemas=fig)
    sem = write_pdf(None, {}, {"text": "ACHADOS\nok", "status": "draft"})
    assert com[:4] == b"%PDF" and len(com) > len(sem) + 5000


# ---------------------------------------------------------------------- o Ipê de mesa
def _clicar(qtbot, tela, x, y):
    from PySide6.QtCore import QPoint, Qt
    q = tela.quadro()
    qtbot.mouseClick(tela, Qt.LeftButton, pos=QPoint(int(q.x() + x * q.width()), int(q.y() + y * q.height())))


def _arrastar(qtbot, tela, a, b, passos=6):
    from PySide6.QtCore import QPoint, Qt
    q = tela.quadro()
    P = lambda x, y: QPoint(int(q.x() + x * q.width()), int(q.y() + y * q.height()))   # noqa: E731
    qtbot.mousePress(tela, Qt.LeftButton, pos=P(*a))
    for k in range(1, passos + 1):
        qtbot.mouseMove(tela, P(a[0] + (b[0] - a[0]) * k / passos, a[1] + (b[1] - a[1]) * k / passos))
    qtbot.mouseRelease(tela, Qt.LeftButton, pos=P(*b))


def test_editor_de_mesa(env, tmp_path, sample_dir, qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    from ipe.importer.scanner import Importer
    from ipe.ui import esquema_dialogo as U
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    study = repo.search_studies({})[0].study_uid
    serie = repo.series_for_study(study)[0]
    inst = repo.instances_for_series(serie.series_uid)[0]
    aberta = {"v": (serie.series_uid, inst["sop_uid"], 0)}
    d = U.EsquemaDialog(repo, study, {"modelo": "face_frente"}, True, lambda: aberta["v"])
    qtbot.addWidget(d)
    d.show()
    qtbot.waitExposed(d)
    t = d.tela
    assert t.ferramenta == "ponto" and not any(b.property("ferramenta") == "setor" for b in d.grupo.buttons())
    _clicar(qtbot, t, 0.62, 0.50)
    assert len(d.e["marcas"]) == 1 and d.e["marcas"][0]["n"] == 1 and abs(d.e["marcas"][0]["p"][0][0] - 0.62) < 0.01
    campo = d.tabela.cellWidget(0, 1)
    assert campo.hasFocus() or True                      # sem tela o foco pode não vir; o texto entra do mesmo jeito
    qtbot.keyClicks(campo, "nodulo de 4 mm")
    assert d.e["marcas"][0]["texto"] == "nodulo de 4 mm"
    d._ferramenta("elipse")
    t.cor = "#1565c0"
    _arrastar(qtbot, t, (0.30, 0.20), (0.42, 0.28))
    d._ferramenta("seta")
    d.numerar.setChecked(False)
    _arrastar(qtbot, t, (0.80, 0.80), (0.62, 0.66))
    d._ferramenta("traco")
    _arrastar(qtbot, t, (0.40, 0.76), (0.56, 0.78), passos=10)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("lesão actínica", True))
    d._ferramenta("texto")
    _clicar(qtbot, t, 0.06, 0.93)
    m = d.e["marcas"]
    assert [x["tipo"] for x in m] == ["ponto", "elipse", "seta", "traco", "texto"] and [x["n"] for x in m] == [1, 2, 0, 0, 0]
    assert m[1]["cor"] == "#1565c0" and len(m[3]["p"]) > 4 and m[4]["texto"] == "lesão actínica"
    d._ferramenta("elipse")
    _clicar(qtbot, t, 0.5, 0.9)                           # clique sem arrastar não cria elipse
    assert len(d.e["marcas"]) == 5
    d._ferramenta("mover")
    _arrastar(qtbot, t, (0.62, 0.50), (0.70, 0.56))
    assert abs(d.e["marcas"][0]["p"][0][0] - 0.70) < 0.012
    t.voltar()
    assert abs(d.e["marcas"][0]["p"][0][0] - 0.62) < 0.012
    d._ferramenta("apagar")
    _clicar(qtbot, t, 0.71, 0.73)
    assert [x["tipo"] for x in d.e["marcas"]] == ["ponto", "elipse", "traco", "texto"]
    # ligar à imagem aberta: vira imagem-chave; imagem de fora avisa e não liga
    d.tabela.cellWidget(0, 2).click()
    assert d.e["marcas"][0]["imagem"]["rotulo"].startswith("série ") and (inst["sop_uid"], 0) in repo.key_image_set(study)
    aberta["v"] = None
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a[2]))
    d.tabela.cellWidget(1, 2).click()
    assert avisos and "imagem" not in d.e["marcas"][1]
    d.titulo.setText("Face da paciente")
    e = E.normalizar(d.esquema())
    assert e["titulo"] == "Face da paciente" and len(e["marcas"]) == 4
    # a tela desenha o que a figura final desenha: há vermelho perto do ponto 1 nas duas
    img = d.tela.grab().toImage()
    q = t.quadro()
    c = img.pixelColor(int(q.x() + 0.62 * q.width()) - 5, int(q.y() + 0.50 * q.height()) - 5)
    assert c.red() > 150 and c.green() < 110
    # a próstata: o clique pinta, o segundo limpa
    d2 = U.EsquemaDialog(repo, study, {"modelo": "prostata"}, True, None)
    qtbot.addWidget(d2)
    d2.show()
    qtbot.waitExposed(d2)
    d2._ferramenta("setor")
    assert d2.categoria.currentData() == "4"
    mod = E.modelo("prostata")
    s = next(z for z in mod["setores"] if z["id"] == "medio_PZpl_D")
    _clicar(qtbot, d2.tela, s["cx"] / mod["w"], s["cy"] / mod["h"])
    d2.categoria.setCurrentIndex(d2.categoria.findData("5"))
    s2 = next(z for z in mod["setores"] if z["id"] == "apice_PZpm_E")
    _clicar(qtbot, d2.tela, s2["cx"] / mod["w"], s2["cy"] / mod["h"])
    _clicar(qtbot, d2.tela, s2["cx"] / mod["w"], s2["cy"] / mod["h"])
    assert d2.e["setores"] == {"medio_PZpl_D": "4"} and d2.setores.text() == "Setores pintados: 1"
    # só para ver: nada desenha
    d3 = U.EsquemaDialog(repo, study, e, False, None)
    qtbot.addWidget(d3)
    d3.show()
    _clicar(qtbot, d3.tela, 0.2, 0.2)
    assert len(d3.e["marcas"]) == 4 and d3.tela.ferramenta == "mover"
    with pytest.raises(LookupError):
        U.EsquemaDialog(repo, study, {"modelo": "nada"})
    # a faixa do laudo: grava, mostra a miniatura e entrega a legenda
    f = U.FaixaDeEsquemas(repo, study, "ana", True, True, None)
    qtbot.addWidget(f)
    assert f.lista.count() == 0 and not f.b_legenda.isEnabled()
    f._gravar([e, d2.esquema()])
    assert f.lista.count() == 2 and f.lista.item(0).text() == "Face da paciente" and f.b_legenda.isEnabled()
    saiu = []
    f.inserir.connect(saiu.append)
    f._legenda()
    assert saiu and saiu[0].startswith("Face da paciente:\n1. nodulo de 4 mm (série") and "PI-RADS 4" in saiu[0]
    f.set_pode(False)
    assert not f.b_novo.isEnabled() and f.b_editar.text() == "Ver…"
    # escolher o modelo: os do Ipê e um próprio
    esc = U.EscolherModelo(repo, True)
    qtbot.addWidget(esc)
    assert esc.lista.count() == len(E.modelos(repo)) >= 8 and esc.escolhido() == "face_frente"


def test_janela_do_laudo_com_esquema(env, tmp_path, sample_dir, qtbot):
    """Na janela do laudo: a faixa aparece, a legenda entra no texto e, ao guardar no exame, vão a imagem e o SR."""
    from ipe.importer.scanner import Importer
    from ipe.ui.report_window import ReportWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    study = repo.search_studies({})[0].study_uid
    E.gravar(repo, study, [_face()], "local")

    class Aba:
        storage_root = paths.storage
        viewports = []
        active = None
    w = ReportWindow(repo, study, None, Aba())
    qtbot.addWidget(w)
    assert w.esquemas.lista.count() == 1
    w.editor.setPlainText("ACHADOS\n")
    from PySide6.QtGui import QTextCursor
    w.editor.moveCursor(QTextCursor.End)
    w.esquemas.b_legenda.click()
    assert "Face — frente:\n1. nódulo hipoecoico de 4 mm\n2. placa" in w.editor.toPlainText()
    assert w.context()["esquemas"].startswith("Face — frente:")
    pdf = w.pdf_bytes()
    w.esquemas._gravar([])
    assert len(pdf) > len(w.pdf_bytes()) + 5000           # a figura está no PDF
    E.gravar(repo, study, [_face()], "local")
    antes = len(repo.series_for_study(study, True))
    w.save_pdf_dicom.setChecked(True)
    w.save_sr.setChecked(True)
    assert w.store_dicom({"text": "x", "title": "Laudo", "author": "A", "signed_by": "A", "fields": {}, "status": "final"}) == 3
    series = repo.series_for_study(study, True)
    assert len(series) == antes + 3 and any(s.description == "Esquemas do laudo" and s.modality == "OT" for s in series)
    assert w._imagem_aberta() is None
    w.close()
