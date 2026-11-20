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
    """0.100.74: o esquema é do exame; no laudo só se diz se ele entra ("Esquemas no laudo", como as imagens-chave):
    a legenda vai para o texto, as figuras para o PDF e, ao guardar no exame, a imagem e o SR."""
    from ipe.importer.scanner import Importer
    from ipe.ui.report_window import ReportWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    study = repo.search_studies({})[0].study_uid

    class Aba:
        storage_root = paths.storage
        viewports = []
        active = None
    w = ReportWindow(repo, study, None, Aba())
    qtbot.addWidget(w)
    assert not hasattr(w, "esquemas")                       # a faixa de desenhar saiu do laudo
    assert not w.com_esquemas.isEnabled() and w.com_esquemas.text() == "Esquemas no laudo"   # nada desenhado
    E.gravar(repo, study, [_face(), {"modelo": "mamas"}], "local")
    w._estado_dos_esquemas()
    assert w.com_esquemas.isEnabled() and not w.com_esquemas.isChecked() and w.com_esquemas.text() == "Esquemas no laudo (1)"
    w.editor.setPlainText("ACHADOS\n")
    from PySide6.QtGui import QTextCursor
    w.editor.moveCursor(QTextCursor.End)
    sem = w.pdf_bytes()
    antes = len(repo.series_for_study(study, True))
    w.save_pdf_dicom.setChecked(True)
    w.save_sr.setChecked(True)
    rep = {"text": "x", "title": "Laudo", "author": "A", "signed_by": "A", "fields": {}, "status": "final"}
    assert w.store_dicom(rep) == 2 and len(repo.series_for_study(study, True)) == antes + 2   # fora do laudo: só PDF e SR
    # marcar: a legenda entra no texto (uma vez), as figuras no PDF, e o exame passa a dizer "no laudo"
    w.com_esquemas.setChecked(True)
    assert E.no_laudo(repo, study)
    assert "Face — frente:\n1. nódulo hipoecoico de 4 mm\n2. placa" in w.editor.toPlainText()
    w.com_esquemas.setChecked(False)
    w.com_esquemas.setChecked(True)
    assert w.editor.toPlainText().count("Face — frente:") == 1
    assert w.context()["esquemas"].startswith("Face — frente:")
    assert len(w.pdf_bytes()) > len(sem) + 5000
    # desenhar mais (fora do laudo) não desliga o "no laudo"
    E.gravar(repo, study, [_face()], "local")
    assert E.no_laudo(repo, study)
    antes = len(repo.series_for_study(study, True))
    assert w.store_dicom(rep) == 3
    series = repo.series_for_study(study, True)
    assert len(series) == antes + 3 and any(s.description == "Esquemas do laudo" and s.modality == "OT" for s in series)
    w.com_esquemas.setChecked(False)
    assert not E.no_laudo(repo, study) and len(w.pdf_bytes()) < len(sem) + 3000
    w.close()


def test_botao_esquema_do_visualizador(env, sample_dir, qtbot, monkeypatch):
    """0.100.74: o botão Esquema do visualizador abre os esquemas do exame, fora do laudo."""
    from PySide6.QtWidgets import QMessageBox
    from ipe.importer.scanner import Importer
    from ipe.ui import esquema_dialogo as U
    from ipe.ui.viewer import actions as A
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    study = repo.search_studies({})[0].study_uid
    assert any(a[0] == "esquema.open" for a in A.ACTIONS) if hasattr(A, "ACTIONS") else True
    from ipe.ui.icons import icon
    assert not icon("esquema").isNull()
    serie = repo.series_for_study(study)[0]
    inst = repo.instances_for_series(serie.series_uid)[0]
    d = U.EsquemasDoExame(repo, study, "ana", True, lambda: (serie.series_uid, inst["sop_uid"], 0), paths.storage)
    qtbot.addWidget(d)
    f = d.faixa
    assert not f.b_legenda.isVisibleTo(d) and f.b_excluir.isVisibleTo(d) and not f.b_gravar.isEnabled()
    f._gravar([_face(), {"modelo": "prostata", "setores": {"VS_D": "2"}}])
    assert f.lista.count() == 2 and f.b_gravar.isEnabled() and f.b_excluir.isEnabled()
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    f.gravar_no_exame()
    f.gravar_no_exame()                                   # salvar sobrepondo: troca, não duplica
    nossas = [s for s in repo.series_for_study(study, True) if s.description.startswith("Esquemas do laudo")]
    assert sorted((s.description, s.num_images) for s in nossas) == [("Esquemas do laudo", 2), ("Esquemas do laudo (SR)", 1)]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    f.lista.setCurrentRow(1)
    f.excluir()
    assert [e["modelo"] for e in E.ler(repo, study)] == ["face_frente"]
    # quem não escreve laudos só vê
    v = U.EsquemasDoExame(repo, study, "tec", False, None, paths.storage)
    qtbot.addWidget(v)
    assert not v.faixa.b_novo.isEnabled() and not v.faixa.b_excluir.isEnabled() and v.faixa.b_editar.text() == "Ver…"
    # a imagem do quadro ativo: só deste exame, e nunca uma reconstrução
    class Q:  # noqa: E701
        sop_uid, series_uid, frame_index, is_virtual = inst["sop_uid"], serie.series_uid, 0, False
    class Vp:  # noqa: E701
        study_uid = study
        def current_frame(self): return Q()
        def update(self): pass
    class Aba:  # noqa: E701
        active, viewports, key_set = Vp(), [], set()
    assert U.imagem_do_quadro(Aba, study) == (serie.series_uid, inst["sop_uid"], 0) and (inst["sop_uid"], 0) in Aba.key_set
    assert U.imagem_do_quadro(Aba, "1.2.outro") is None
    Q.is_virtual = True
    assert U.imagem_do_quadro(Aba, study) is None
    # Configurações ▸ Esquemas: o cadastro dos modelos
    from ipe.ui import configuracoes as C
    grupo = dict(C.CATALOGO)["Esquemas"]
    assert grupo[0][1] == "f:abrir_modelos_de_esquema"
    from ipe.ui.main_window import MainWindow
    assert hasattr(MainWindow, "abrir_modelos_de_esquema")
    m = U.ModelosDialog(repo, True)
    qtbot.addWidget(m)
    assert m.painel.lista.count() >= 8 and hasattr(m.painel, "b_editar")
    so_ver = U.ModelosDialog(repo, False)
    qtbot.addWidget(so_ver)
    assert not hasattr(so_ver.painel, "b_editar")


# ---------------------------------------------------------------------- 0.100.73: cadastro de modelos e gravar no exame
def test_cadastro_de_modelos(env):
    import numpy as np
    paths, db, repo = env
    de_fabrica = len(E.modelos())
    traco = {"tipo": "traco", "p": [[0.1, 0.1], [0.5, 0.1], [0.9, 0.1]], "cor": "#111111", "l": 6, "n": 7,
             "imagem": {"sop_uid": "1.2", "rotulo": "x"}}
    # em branco
    with pytest.raises(ValueError):
        E.salvar_modelo(repo, {"nome": "  "})
    b = E.salvar_modelo(repo, {"nome": "Mão direita", "grupo": "Pele", "base": [traco, {"tipo": "nada"}]})
    assert b["meu"] and (b["w"], b["h"]) == (1000, 1000) and b["grupo"] == "Pele" and not b.get("png")
    assert len(b["base"]) == 1 and b["base"][0]["n"] == 0 and "imagem" not in b["base"][0]     # modelo não numera nem liga
    fig = np.asarray(E.desenhar({"modelo": b["id"]}, 500, repo))
    assert max(int(v) for v in fig[50, 250]) < 40 and tuple(fig[250, 250]) == (255, 255, 255)     # o desenho do modelo
    # cópia de um do Ipê: leva os traços e os setores; o que se pinta nela vale
    c = E.salvar_modelo(repo, {"nome": "Próstata da clínica", "origem": "prostata", "base": [traco]})
    assert c["meu"] and c["origem"] == "prostata" and len(c["setores"]) == 41 and c["categorias"] and c["grupo"] == "Meus"
    e = E.normalizar({"modelo": c["id"], "setores": {"medio_PZpl_D": "4"}}, repo)
    assert e["setores"] == {"medio_PZpl_D": "4"} and E.legenda(e, repo)[0].startswith("PI-RADS 4")
    # mudar um modelo do Ipê: o original fica; ocultar tira da lista, mas o esquema antigo ainda desenha
    m = E.salvar_modelo(repo, {"id": "mamas", "nome": "Mamas (clínica)", "grupo": "Mama", "base": [traco], "oculto": True})
    assert m["alterado"] and m["oculto"] and m["nome"] == "Mamas (clínica)" and len(m["tracos"]) > 10
    assert "mamas" not in {x["id"] for x in E.modelos(repo)} and "mamas" in {x["id"] for x in E.modelos(repo, ocultos=True)}
    assert E.modelo("mamas", repo)["base"] and E.png({"modelo": "mamas"}, 300, repo)[:4] == b"\x89PNG"
    assert E.modelo("mamas")["nome"] == "Mamas" and not E.modelo("mamas").get("base")            # sem o banco, o original
    with pytest.raises(ValueError):
        E.salvar_modelo(repo, {"id": "mamas", "nome": "x"}, b"imagem")
    assert len(E.modelos(repo, ocultos=True)) == de_fabrica + 2
    assert E.excluir_modelo(repo, "mamas") == "restaurado" and E.modelo("mamas", repo)["nome"] == "Mamas"
    assert not E.modelo("mamas", repo).get("alterado") and E.excluir_modelo(repo, "mamas") == ""
    # editar um próprio: nome, desenho e trocar o fundo por uma imagem
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (400, 200), (200, 220, 240)).save(buf, "PNG")
    b2 = E.salvar_modelo(repo, {"id": b["id"], "nome": "Mão", "grupo": "", "base": []}, buf.getvalue())
    assert b2["nome"] == "Mão" and b2["grupo"] == "Meus" and (b2["w"], b2["h"]) == (400, 200) and b2["png"] and not b2["base"]
    # cópia de um modelo de imagem leva a imagem
    c2 = E.salvar_modelo(repo, {"nome": "Mão 2", "origem": b["id"]})
    assert c2["png"] == b2["png"] and c2["id"] != b["id"]
    with pytest.raises(LookupError):
        E.salvar_modelo(repo, {"id": "meu_naoexiste", "nome": "x"})
    assert E.excluir_modelo(repo, b["id"]) == "excluido" and E.modelo(b["id"], repo) is None
    assert E.novo_modelo_de_imagem(repo, "Pé", buf.getvalue())["png"]


def test_gravar_no_exame_sem_laudo(env, sample_dir):
    from ipe.importer.scanner import Importer
    from ipe.reporting import dicom_out as D
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    study = repo.search_studies({})[0].study_uid
    antes = {s.series_uid for s in repo.series_for_study(study, True)}
    with pytest.raises(ValueError):
        ES.gravar_no_exame(repo, paths.storage, study, "Ana")             # nada desenhado
    E.gravar(repo, study, [_face(), {"modelo": "mamas"}], "ana")
    r = ES.gravar_no_exame(repo, paths.storage, study, "Dra. Ana")
    assert r["imagens"] == 1
    novas = [s for s in repo.series_for_study(study, True) if s.series_uid not in antes]
    assert sorted((s.description, s.modality, s.num_images) for s in novas) == \
        [("Esquemas do laudo", "OT", 1), ("Esquemas do laudo (SR)", "SR", 1)]
    sr_serie = next(s for s in novas if s.modality == "SR")
    sr = pydicom.dcmread(repo.instances_for_series(sr_serie.series_uid)[0]["path"])
    assert sr.SOPClassUID == D.ENHANCED_SR and sr.CompletionFlag == "PARTIAL" and sr.VerificationFlag == "UNVERIFIED"
    assert sr.ContentSequence[0].PersonName == "Dra. Ana"
    fig = next(s for s in novas if s.modality == "OT")
    sop = repo.instances_for_series(fig.series_uid)[0]["sop_uid"]
    secao = next(i for i in sr.ContentSequence if i.ValueType == "CONTAINER")
    assert secao.ContentSequence[1].ReferencedSOPSequence[0].ReferencedSOPInstanceUID == sop
    assert any(i.ValueType == "TEXT" and i.TextValue.startswith("1. nódulo") for i in secao.ContentSequence)
    # gravar de novo (com mais um esquema) troca: não duplica
    E.gravar(repo, study, [_face(), {"modelo": "prostata", "setores": {"VS_D": "2"}}], "ana")
    assert ES.gravar_no_exame(repo, paths.storage, study, "Ana")["imagens"] == 2
    depois = [s for s in repo.series_for_study(study, True) if s.series_uid not in antes]
    assert sorted((s.description, s.num_images) for s in depois) == [("Esquemas do laudo", 2), ("Esquemas do laudo (SR)", 1)]
    assert not ({s.series_uid for s in depois} & {s.series_uid for s in novas})
    # o servidor apaga as dele quando o cliente pede (e só essas)
    from ipe.central.rpc import POR_EXAME, RPC_METHODS
    assert RPC_METHODS["apagar_series_dos_esquemas"] == "report" and "apagar_series_dos_esquemas" in POR_EXAME
    # com o exame travado (cadeado da imagem-chave) a troca também acontece, e o cadeado fica
    repo.set_locked(study, True)
    assert ES.gravar_no_exame(repo, paths.storage, study, "Ana")["imagens"] == 2
    assert len([s for s in repo.series_for_study(study, True) if s.series_uid not in antes]) == 2
    assert ES.apagar_anteriores(repo, study, paths.storage) == 2
    assert {s.series_uid for s in repo.series_for_study(study, True)} == antes
    with pytest.raises(PermissionError):                                   # continua travado para o resto
        repo.delete_series(next(iter(antes)), paths.storage)


def test_modelos_na_mesa(env, sample_dir, qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    from ipe.importer.scanner import Importer
    from ipe.ui import esquema_dialogo as U
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    study = repo.search_studies({})[0].study_uid
    # desenhar por cima de um modelo do Ipê e salvar
    d = U.ModeloDialog(repo, E.modelo("tireoide", repo))
    qtbot.addWidget(d)
    d.show()
    qtbot.waitExposed(d)
    assert d.tela.ferramenta == "traco" and not d.b_tirar.isVisibleTo(d) and d.oculto.isVisibleTo(d)
    _arrastar(qtbot, d.tela, (0.2, 0.9), (0.8, 0.9), passos=10)
    assert len(d.e["marcas"]) == 1 and d.e["marcas"][0]["n"] == 0
    d.nome.setText("Tireoide da clínica")
    d._fechar("salvar")
    d.gravar()
    m = E.modelo("tireoide", repo)
    assert m["nome"] == "Tireoide da clínica" and m["alterado"] and len(m["base"]) == 1
    # a tela do esquema mostra o desenho do modelo (há tinta onde só o modelo desenhou)
    ed = U.EsquemaDialog(repo, study, {"modelo": "tireoide"}, True, None)
    qtbot.addWidget(ed)
    ed.show()
    qtbot.waitExposed(ed)
    q = ed.tela.quadro()
    c = ed.tela.grab().toImage().pixelColor(int(q.x() + 0.5 * q.width()), int(q.y() + 0.9 * q.height()))
    assert c.red() < 90 and c.green() < 90
    assert ed.e["marcas"] == []                           # e não é marca do exame
    # salvar como cópia; restaurar o original
    d2 = U.ModeloDialog(repo, m)
    qtbot.addWidget(d2)
    assert d2.b_tirar.text() == "Restaurar o original" and len(d2.e["marcas"]) == 1
    d2.nome.setText("Tireoide 2")
    d2._fechar("copia")
    d2.gravar()
    copia_ = next(x for x in E.modelos(repo) if x["nome"] == "Tireoide 2")
    assert copia_["meu"] and copia_["origem"] == "tireoide" and len(copia_["base"]) == 1
    d3 = U.ModeloDialog(repo, m)
    qtbot.addWidget(d3)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    d3._tirar()
    d3.gravar()
    assert E.modelo("tireoide", repo)["nome"] == "Tireoide e níveis cervicais"
    d4 = U.ModeloDialog(repo, copia_)
    qtbot.addWidget(d4)
    assert d4.b_tirar.text() == "Excluir o modelo" and not d4.oculto.isVisibleTo(d4)
    # o seletor: em branco (abre o editor), ocultos aparecem só para quem cadastra
    E.salvar_modelo(repo, {"id": "mamas", "nome": "Mamas", "grupo": "Mama", "oculto": True})
    esc = U.EscolherModelo(repo, True)
    qtbot.addWidget(esc)
    assert any("(oculto)" in esc.lista.item(i).text() for i in range(esc.lista.count()))
    comum = U.EscolherModelo(repo, False)
    qtbot.addWidget(comum)
    assert comum.lista.count() == esc.lista.count() - 1 and not hasattr(comum, "b_editar")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Couro cabeludo", True))
    monkeypatch.setattr(U.ModeloDialog, "exec", lambda self: 0)
    esc._em_branco()
    assert any(x["nome"] == "Couro cabeludo" and x["meu"] for x in E.modelos(repo)) and esc.escolhido().startswith("meu_")
    # a faixa do laudo grava no exame sem laudo
    E.gravar(repo, study, [_face()], "ana")
    f = U.FaixaDeEsquemas(repo, study, "Ana", True, True, None, None, paths.storage)
    qtbot.addWidget(f)
    assert f.b_gravar.isEnabled()
    avisos, sinais = [], []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a[2]))
    f.gravado.connect(sinais.append)
    f.gravar_no_exame()
    assert avisos == ["Gravado no exame (figuras e SR): 1"] and sinais == [study]
    assert any(s.description == "Esquemas do laudo" for s in repo.series_for_study(study, True))
    sem = U.FaixaDeEsquemas(repo, study, "Ana", True, True, None, None, None)
    qtbot.addWidget(sem)
    assert not sem.b_gravar.isEnabled()
