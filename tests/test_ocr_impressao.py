"""OCR da folha de impressão DICOM (0.80): leitor embutido e o paciente achado no banco.

Relato dele (20/10/2026): *"estou testando o dicomprint. não estou conseguindo usar o OCR para
identificar os pacientes"* — o botão vivia apagado: dependia do Tesseract instalado à parte.
Os textos abaixo imitam o que o leitor devolveu em duas folhas reais da AW (nome grudado, letra
trocada, cabeçalho repetido), com nomes inventados.
"""
from datetime import datetime

import numpy as np
import pytest

from ipe.printing import ocr

TEM_LEITOR = ocr._tem_rapidocr()

GRUDADO = ("M3DVIBRANT:VIBR..P1VIBRANQOREIRALUCIANABETRIZ PEREIRA:M3DVIBRANT:VIBR..Ph1VBRANSMOREIRA"
           "LUCIANABETRIZ PEREIRA\nMIP L cut  Ex:0ct 07 2026:MIP R cut\nDFOV20.4cm  DFOV20.4cm")
LIMPO = ("3D  S 98  MOREIRA LUCIANA BEATRIZPEREIRA:3D  S 98  MOREIRA LUCIANABEATRIZ PEREIRA\n"
         "DFOV22.4cm  Ex:Jan 24 2022: DFOV22.4cm\nMIP L cut  MIP Rcut")


def _banco(n_falsos: int = 3000) -> list[dict]:
    reais = [("MOREIRA, LUCIANA BEATRIZ PEREIRA", "7781234"), ("MOREIRA, PAULO HENRIQUE", "1000001"),
             ("PEREIRA, LUCIANA", "1000002"), ("SANTOS, BEATRIZ MOREIRA", "1000003")]
    out = [{"patient_name": n, "patient_id": i, "study_uid": f"r{k}", "when": datetime(2026, 10, 7),
            "modalities": "MR", "description": "RM MAMAS"} for k, (n, i) in enumerate(reais)]
    import random
    rnd = random.Random(7)
    # banco de verdade repete sobrenome (MOREIRA, PEREIRA), não a mesma pessoa embaralhada
    nomes = ["SILVA", "SANTOS", "OLIVEIRA", "SOUZA", "LIMA", "PEREIRA", "COSTA", "MOREIRA", "ANA",
             "MARIA", "JOSE", "PAULA", "CARLOS", "ALMEIDA", "FERNANDA", "LUCAS", "BEATRIZ"]
    for k in range(n_falsos):
        out.append({"patient_name": f"{rnd.choice(nomes)}, {' '.join(rnd.sample(nomes, 3))}",
                    "patient_id": str(9000000 + k), "study_uid": f"f{k}", "when": datetime(2025, 1, 1)})
    return out


def test_compactar_tira_espaco_acento_e_pontuacao():
    assert ocr.compactar("Moreira, Luciána  Beatriz") == "MOREIRALUCIANABEATRIZ"


@pytest.mark.parametrize("texto", [LIMPO, GRUDADO])
def test_acha_o_paciente_certo_mesmo_grudado_e_com_letra_trocada(texto):
    import time
    t0 = time.time()
    achados = ocr.combinar(texto, _banco())
    assert time.time() - t0 < 5, "a comparação tem de sair em segundos, mesmo com milhares de pacientes"
    assert achados and achados[0]["patient_name"] == "MOREIRA, LUCIANA BEATRIZ PEREIRA"
    assert achados[0]["ocr"] and achados[0]["score"] >= 0.9
    if len(achados) > 1:
        assert achados[0]["score"] - achados[1]["score"] >= 0.1, "o certo tem de ganhar com folga"


def test_quem_so_tem_sobrenomes_em_comum_nao_passa_na_frente():
    achados = ocr.combinar(LIMPO, _banco(0))
    nomes = [a["patient_name"] for a in achados]
    assert nomes[0] == "MOREIRA, LUCIANA BEATRIZ PEREIRA"
    assert "PEREIRA, LUCIANA" not in nomes[:1] and "MOREIRA, PAULO HENRIQUE" not in nomes


def test_id_lido_conta_muito():
    achados = ocr.combinar("PACIENTE  ID 7781234  MOREIRA L", _banco(0))
    assert achados and achados[0]["patient_id"] == "7781234"


def test_texto_curto_ou_vazio_nao_inventa():
    assert ocr.combinar("", _banco(0)) == [] and ocr.combinar("3D S98", _banco(0)) == []


def test_guess_pega_o_pedaco_com_cara_de_nome():
    assert ocr.guess(LIMPO)[0] == "MOREIRA LUCIANA BEATRIZPEREIRA"
    assert ocr.guess("Nome: SILVA JOSE  ID: 1234567")[1] == "1234567"


def test_linhas_em_ordem_de_leitura():
    caixas = [([[300, 5], [400, 5], [400, 25], [300, 25]], "B", 0.9),
              ([[5, 44], [90, 44], [90, 60], [5, 60]], "C", 0.9),
              ([[5, 4], [200, 4], [200, 24], [5, 24]], "A", 0.9)]
    assert ocr.linhas_em_ordem(caixas) == ["A  B", "C"]


def _folha(texto: str) -> np.ndarray:
    """Folha A4 preta com o cabeçalho em letra branca, como a AW grava."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("L", (1810, 2560), 0)
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("DejaVuSans.ttf", 30)
    except OSError:
        f = ImageFont.load_default()
    d.text((20, 15), texto, fill=255, font=f)
    d.rectangle((40, 500, 1700, 2400), fill=90)          # a imagem do exame, embaixo
    return np.asarray(img)


@pytest.mark.skipif(not TEM_LEITOR, reason="RapidOCR não instalado")
def test_le_o_cabecalho_de_uma_folha_e_acha_no_banco():
    texto = ocr.read_header(_folha("MOREIRA LUCIANA BEATRIZ PEREIRA    Ex: Oct 07 2026    ID 7781234"))
    assert "MOREIRA" in ocr.compactar(texto) and "7781234" in texto
    achados = ocr.combinar(texto, _banco(500))
    assert achados[0]["patient_name"] == "MOREIRA, LUCIANA BEATRIZ PEREIRA"


# ------------------------------------------------------------------ a janela
def _janela(ler, estudos=None, candidatos=None):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from ipe.ui.prints_tab import IdentifyDialog
    return IdentifyDialog("", "", candidatos or [], ler, None,
                          estudos_fn=(lambda: estudos) if estudos is not None else None)


def test_janela_le_acha_e_ja_escolhe_o_mais_provavel(monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: True)
    dlg = _janela(lambda: LIMPO, _banco(300))
    assert dlg.b_ocr.isEnabled()
    dlg._ocr(lambda: LIMPO)
    assert dlg.lido.toPlainText().startswith("3D") and not dlg.lido.isHidden()
    assert dlg.lista.count() >= 1 and dlg.lista.item(0).text().startswith("OCR ")
    assert dlg.lista.currentRow() == 0, "com folga clara, o mais provável já vem escolhido"
    assert dlg.nome.text() == "MOREIRA, LUCIANA BEATRIZ PEREIRA" and dlg.ident.text() == "7781234"
    assert dlg.escolhido == "r0"


def test_janela_sem_paciente_no_banco_usa_o_texto_lido(monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: True)
    dlg = _janela(lambda: LIMPO, [])
    dlg._ocr(lambda: LIMPO)
    assert dlg.nome.text() == "MOREIRA LUCIANA BEATRIZPEREIRA" and not dlg.escolhido


def test_sem_leitor_o_botao_diz_o_que_fazer(monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: False)
    dlg = _janela(lambda: "")
    assert not dlg.b_ocr.isEnabled() and "instalar.bat" in dlg.b_ocr.toolTip()


def test_banco_entrega_os_exames_para_comparar(env, sample_dir):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    estudos = repo.studies_for_ocr()
    assert estudos and all({"study_uid", "patient_name", "patient_id", "when"} <= set(e) for e in estudos)
    alguem = estudos[0]
    achados = ocr.combinar(f"  {alguem['patient_name'].replace('^', ' ')}  ", estudos)
    assert achados and achados[0]["patient_name"] == alguem["patient_name"]
