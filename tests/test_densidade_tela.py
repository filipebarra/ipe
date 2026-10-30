"""Densidade mamária na tela: mede o que está nos quadros, e mostra a máscara que produziu o número.

Não há regra de seleção aqui **de propósito**: quem escolhe as imagens é o médico, pondo-as no
quadro. O ponto da tela é poder **ver a máscara** — foi vendo a mesma mama dar 108,8 cm² numa
imagem e 38,4 cm² na outra que o defeito da máscara apareceu.
"""

from types import SimpleNamespace

import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from ipe.imaging import density as D
from ipe.ui import densidade_dialog as T

FFDM = "1.2.840.10008.5.1.4.1.1.1.2"
TC = "1.2.840.10008.5.1.4.1.1.2"


def _grava(pasta, nome, modalidade="MG", vista="CC", lado="R", fracao=0.3, quebrada=False,
           linhas=300, colunas=240):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = FFDM if modalidade == "MG" else TC
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = "1.2.3.4"
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = modalidade
    ds.SeriesDescription = "MAMOGRAFIA DIGITAL" if modalidade == "MG" else "Processed Images"
    ds.ImageLaterality, ds.ViewPosition = lado, vista
    ds.ImagerPixelSpacing = [0.2, 0.2]
    ds.BodyPartThickness = 50
    ds.BreastImplantPresent = "NO"
    ds.Rows, ds.Columns = linhas, colunas
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit, ds.PixelRepresentation, ds.SamplesPerPixel = 15, 0, 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    y, x = np.mgrid[0:linhas, 0:colunas]
    cx = 0.0 if lado == "R" else colunas - 1.0
    rr = ((y - linhas / 2.0) / (linhas * 0.42)) ** 2 + ((x - cx) / (colunas * 0.85)) ** 2
    mama = rr < 1.0
    img = np.full((linhas, colunas), 300.0)
    img[mama] = 1200.0
    dentro = np.nonzero(mama)
    ordem = np.argsort(rr[dentro])
    n = int(round(fracao * len(ordem)))
    img[dentro[0][ordem[:n]], dentro[1][ordem[:n]]] = 2600.0
    ds.PixelData = img.astype(np.uint16).tobytes()
    caminho = pasta / nome
    ds.save_as(str(caminho), enforce_file_format=True)
    if quebrada:                                   # pixel cortado no meio: o arquivo não abre
        bruto = caminho.read_bytes()
        caminho.write_bytes(bruto[: len(bruto) - linhas * colunas])
    return SimpleNamespace(path=str(caminho), frame_index=0, sop_uid=ds.SOPInstanceUID,
                           series_uid=ds.SeriesInstanceUID, is_virtual=False)


class _Quadro:
    """Viewport de mentira: só sabe dizer qual imagem está mostrando."""

    def __init__(self, frame=None) -> None:
        self.frame = frame

    def current_frame(self):
        return self.frame


class _Aba:
    """Aba de visualizador de mentira: os quadros visíveis e o lugar dos overlays."""

    def __init__(self, quadros=()) -> None:
        self.study_uid = "1.2.3.4"
        self.viewports = list(quadros)
        self.overlay_objects: list = []
        self.aplicou = 0
        self.foi_para = None

    def _shown(self):
        return self.viewports

    def _apply_overlays(self) -> None:
        self.aplicou += 1

    def go_to_image(self, estudo, serie, sop, quadro) -> None:
        self.foi_para = (estudo, serie, sop, quadro)


def _aba(*frames):
    return _Aba([_Quadro(f) for f in frames])


# --------------------------------------------------------------- o motor
def test_mede_todas_as_imagens_que_lhe_derem(tmp_path):
    a = _grava(tmp_path, "a.dcm", vista="CC")
    b = _grava(tmp_path, "b.dcm", vista="MLO")
    medidas = D.medir_imagens([a.path, b.path])
    assert len(medidas) == 2                       # sem regra: mede o que veio
    assert {m.incidencia for m in medidas} == {"CC", "MLO"}
    assert all(m.pd > 0 and m.mama_cm2 > 0 for m in medidas)


def test_imagem_que_nao_e_mamografia_e_medida_mas_avisada(tmp_path):
    """Recusar seria adivinhar pelo usuário; medir calado seria pior."""
    c = _grava(tmp_path, "c.dcm", modalidade="CT")
    m = D.medir_imagens([c.path])[0]
    assert any("não é mamografia" in a for a in m.avisos)
    assert m.mama_cm2 > 0                          # o número sai; o aviso diz o que ele vale


def test_imagem_que_nao_abre_entra_com_aviso(tmp_path):
    a = _grava(tmp_path, "a.dcm", quebrada=True)
    medidas = D.medir_imagens([a.path])
    assert len(medidas) == 1                       # sumir em silêncio seria pior
    assert medidas[0].avisos and medidas[0].mama_cm2 == 0


def test_mascaras_so_saem_quando_pedidas(tmp_path):
    a = _grava(tmp_path, "a.dcm")
    assert D.medir_imagens([a.path])[0].mascara_mama is None
    com = D.medir_imagens([a.path], mascaras=True)[0]
    assert com.mascara_mama is not None and com.mascara_densa is not None
    assert com.mascara_densa.sum() < com.mascara_mama.sum()


def test_contorno_e_so_a_borda():
    m = np.zeros((40, 40), bool)
    m[10:30, 10:30] = True
    borda = D.contorno(m, 2)
    assert borda[10, 10] and not borda[20, 20]     # canto sim, miolo não
    assert borda.sum() < m.sum() / 2


def test_o_andamento_chega_ao_fim(tmp_path):
    a = _grava(tmp_path, "a.dcm")
    passos = []
    D.medir_imagens([a.path], progresso=lambda i, n: passos.append((i, n)))
    assert passos[-1] == (1, 1)


# ------------------------------------------------- quais imagens estão na tela
def test_pega_os_quadros_visiveis_sem_repetir(tmp_path):
    a = _grava(tmp_path, "a.dcm")
    b = _grava(tmp_path, "b.dcm", vista="MLO")
    aba = _aba(a, b, a, None)                      # a mesma imagem em dois quadros, e um vazio
    achados = T.imagens_na_tela(aba)
    assert [f.path for _k, f in achados] == [a.path, b.path]
    assert [k for k, _f in achados] == [1, 2]


def test_quadro_virtual_fica_de_fora(tmp_path):
    a = _grava(tmp_path, "a.dcm")
    mpr = SimpleNamespace(path="", frame_index=0, sop_uid="x", series_uid="y", is_virtual=True)
    assert [f.path for _k, f in T.imagens_na_tela(_aba(mpr, a))] == [a.path]


# ---------------------------------------------------------------- a tela
def test_tela_vazia_diz_por_que(tmp_path):
    QApplication.instance() or QApplication([])
    d = T.DensidadeDialog(_aba(None))
    assert not d.bt_medir.isEnabled()
    assert "MPR" in d.lb_tela.text() or "vazios" in d.lb_tela.text()


def test_tabela_e_resumo_saem_depois_de_medir(tmp_path):
    QApplication.instance() or QApplication([])
    a = _grava(tmp_path, "a.dcm", vista="CC", lado="R")
    b = _grava(tmp_path, "b.dcm", vista="MLO", lado="L", fracao=0.6)
    aba = _aba(a, b)
    d = T.DensidadeDialog(aba)
    assert d.bt_medir.isEnabled() and "2" in d.lb_tela.text()
    d.medido(D.medir_imagens([a.path, b.path], mascaras=True))
    assert d.tabela.rowCount() == 2
    assert d.bt_csv.isEnabled()
    assert d.tabela.item(0, 0).text() == "1"       # a linha diz de que quadro veio
    texto = d.lb_resumo.text()
    assert "%" in texto and "direita" in texto and "esquerda" in texto
    assert d.medidas[0].serie_uid == a.series_uid  # dá para voltar à imagem medida


def test_uma_imagem_so_tambem_mede(tmp_path):
    """Independente de qual e de quantas: uma imagem na tela dá uma linha."""
    QApplication.instance() or QApplication([])
    a = _grava(tmp_path, "a.dcm")
    d = T.DensidadeDialog(_aba(a))
    d.medido(D.medir_imagens([a.path], mascaras=True))
    assert d.tabela.rowCount() == 1 and d.medidas[0].pd > 0


def test_a_faixa_e_referencia_escrita_ao_lado(tmp_path):
    QApplication.instance() or QApplication([])
    d = T.DensidadeDialog(_aba(None))
    assert "BI-RADS" in d.lb_nota.text() and "radiologista" in d.lb_nota.text()


def test_o_aviso_sai_por_extenso_abaixo_da_tabela(tmp_path):
    QApplication.instance() or QApplication([])
    c = _grava(tmp_path, "c.dcm", modalidade="CT")
    d = T.DensidadeDialog(_aba(c))
    d.medido(D.medir_imagens([c.path], mascaras=True))
    assert "não é mamografia" in d.lb_avisos.text()


def test_mascara_entra_e_sai_do_visualizador(tmp_path):
    QApplication.instance() or QApplication([])
    a = _grava(tmp_path, "a.dcm")
    aba = _aba(a)
    d = T.DensidadeDialog(aba)
    d.medido(D.medir_imagens([a.path], mascaras=True))
    d.ck_mascara.setChecked(True)
    assert [o.source for o in aba.overlay_objects] == ["Densidade"]
    assert len(aba.overlay_objects[0].masks) == 2  # contorno da mama + tecido denso
    d.ck_mascara.setChecked(False)
    assert aba.overlay_objects == []


def test_mascara_sem_medida_avisa_em_vez_de_desenhar(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    avisos = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: avisos.append(a[2]) or QMessageBox.Ok)
    aba = _aba(None)
    d = T.DensidadeDialog(aba)
    d.ck_mascara.setChecked(True)
    assert avisos and not d.ck_mascara.isChecked()
    assert aba.overlay_objects == []


def test_mascara_em_grade_menor_e_desenhada_do_tamanho_da_imagem():
    """Sem dizer sobre que imagem ela é, a máscara sai do tamanho da própria grade.

    Foi o defeito da 0.39.0 na tela do usuário: a máscara aparecia pela metade, encostada no canto
    de cima. E o teste anterior *consagrava* o defeito, porque conferia o tamanho da máscara em vez
    do tamanho da imagem.
    """
    from ipe.imaging import overlays as O
    m = np.zeros((50, 40), bool)
    m[10:20, 10:20] = True
    sem = O.MaskFrame(mask=m, color=(255, 0, 0), label="x", ref=("sop", -1))
    com = O.MaskFrame(mask=m, color=(255, 0, 0), label="x", ref=("sop", -1), alvo=(200, 160))
    args = (None, None, None, None, (0.1, 0.1), 1.0, "sop", 0)
    assert O.mask_rect(sem, *args) == (0.0, 0.0, 40.0, 50.0)
    assert O.mask_rect(com, *args) == (0.0, 0.0, 160.0, 200.0)


def test_a_mascara_cai_na_imagem_certa_e_esticada(tmp_path):
    """A máscara é medida numa grade menor: tem que ser esticada sobre a imagem, não colada."""
    QApplication.instance() or QApplication([])
    from ipe.imaging import overlays as O
    a = _grava(tmp_path, "a.dcm", linhas=2100, colunas=1600)   # grande: a conta reduz a grade
    d = T.DensidadeDialog(_aba(a))
    d.medido(D.medir_imagens([a.path], mascaras=True))
    mf = d.objeto_de_mascara().masks[0]
    assert mf.ref == (a.sop_uid, -1)
    assert mf.mask.shape[0] < 2100                             # a máscara é menor que a imagem
    alvo = O.mask_rect(mf, None, None, None, None, (0.2, 0.2), 1.0, a.sop_uid, 0)
    assert alvo == (0.0, 0.0, 1600.0, 2100.0)                  # e é desenhada sobre a imagem
    assert O.mask_rect(mf, None, None, None, None, (0.2, 0.2), 1.0, "outro", 0) is None


def test_duplo_clique_leva_a_imagem_medida(tmp_path):
    QApplication.instance() or QApplication([])
    a = _grava(tmp_path, "a.dcm")
    aba = _aba(a)
    d = T.DensidadeDialog(aba)
    d.medido(D.medir_imagens([a.path], mascaras=True))
    d.tabela.setCurrentCell(0, 0)
    d.ir_para_imagem()
    assert aba.foi_para == ("1.2.3.4", a.series_uid, a.sop_uid, 0)


def test_csv_tem_uma_linha_por_imagem(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    from PySide6.QtWidgets import QFileDialog
    a = _grava(tmp_path, "a.dcm")
    d = T.DensidadeDialog(_aba(a))
    d.medido(D.medir_imagens([a.path]))
    saida = tmp_path / "saida.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(saida), ""))
    d.exportar()
    linhas = saida.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(linhas) == 2 and linhas[0].count(";") == len(d.COLUNAS) - 1


def test_a_tela_nao_mede_sozinha_ao_abrir(tmp_path):
    """Nada roda por conta própria: quem manda medir é o médico."""
    QApplication.instance() or QApplication([])
    a = _grava(tmp_path, "a.dcm")
    d = T.DensidadeDialog(_aba(a))
    assert d.medidas == [] and d.tabela.rowCount() == 0


def test_medir_de_novo_le_a_tela_outra_vez(tmp_path):
    """Trocou o quadro, mandou medir: mede o que está lá agora, não o de quando abriu."""
    QApplication.instance() or QApplication([])
    a = _grava(tmp_path, "a.dcm")
    b = _grava(tmp_path, "b.dcm", vista="MLO")
    aba = _aba(a)
    d = T.DensidadeDialog(aba)
    assert len(d.quadros) == 1
    aba.viewports.append(_Quadro(b))
    d.ler_a_tela()
    assert [f.path for _k, f in d.quadros] == [a.path, b.path]


# ------------------------------------------------ segundo método e discordância
def test_fcm_acha_a_mesma_fracao_num_caso_facil():
    """Duas populações bem separadas: o agrupamento e o limiar têm que chegar ao mesmo lugar."""
    rng = np.random.default_rng(0)
    arr = np.concatenate([rng.normal(300, 30, 20000),
                          rng.normal(900, 60, 8000)]).reshape(200, 140)
    reg = np.ones(arr.shape, bool)
    m_fcm, t_fcm, k = D.denso_fcm(arr, reg)
    m_otsu, _t = D.denso(arr, reg)
    assert k == 2
    assert abs(m_fcm.mean() - 8000 / 28000) < 0.02
    assert abs(m_fcm.mean() - m_otsu.mean()) < 0.03


def test_fcm_e_limiar_quase_nao_se_distinguem():
    """E isso é o achado, não o defeito.

    Medido no acervo do IMEB: r = 0,994 entre os dois, diferença média de 0,7 ponto percentual, só
    1 imagem em 60 passando de 5 pontos. O segundo método entrega **precisão, não acerto**: mostra
    que a segmentação é estável, não que está certa. Este teste trava essa conclusão — se um dia os
    dois passarem a divergir em caso fácil, é sinal de que um deles quebrou.
    """
    rng = np.random.default_rng(3)
    arr = np.concatenate([rng.normal(400, 120, 20000),
                          rng.normal(700, 200, 12000)]).reshape(200, 160)
    reg = np.ones(arr.shape, bool)
    m_fcm, _t, _k = D.denso_fcm(arr, reg)
    m_otsu, _to = D.denso(arr, reg)
    assert abs(m_fcm.mean() - m_otsu.mean()) < 0.01


def test_medir_devolve_os_dois_metodos(tmp_path):
    a = _grava(tmp_path, "a.dcm")
    m = D.medir_imagens([a.path], metodos=(D.LIMIAR, D.FCM))[0]
    assert set(m.medidas) == {D.LIMIAR, D.FCM}
    assert m.metodo == D.LIMIAR and m.pd == m.medidas[D.LIMIAR].pd
    assert m.medidas[D.FCM].pd > 0


def test_a_tela_avisa_quando_os_metodos_discordam(tmp_path):
    QApplication.instance() or QApplication([])
    a = _grava(tmp_path, "a.dcm")
    d = T.DensidadeDialog(_aba(a))
    medidas = D.medir_imagens([a.path], metodos=(D.LIMIAR, D.FCM), mascaras=True)
    medidas[0].medidas[D.FCM].pd = medidas[0].medidas[D.LIMIAR].pd + 12.0   # discordância forçada
    d.medido(medidas)
    assert "discordam" in d.lb_discorda.text()
    medidas[0].medidas[D.FCM].pd = medidas[0].medidas[D.LIMIAR].pd + 1.0
    d.medido(medidas)
    assert d.lb_discorda.text() == ""


def test_a_mascara_segue_o_metodo_escolhido(tmp_path):
    QApplication.instance() or QApplication([])
    a = _grava(tmp_path, "a.dcm")
    aba = _aba(a)
    d = T.DensidadeDialog(aba)
    d.medido(D.medir_imagens([a.path], metodos=(D.LIMIAR, D.FCM), mascaras=True))
    d.ck_mascara.setChecked(True)
    primeira = aba.overlay_objects[0].masks[1].mask.sum()
    d.c_mascara.setCurrentIndex(1)                      # troca para o agrupamento nebuloso
    assert d.metodo_da_mascara() == D.FCM
    segunda = aba.overlay_objects[0].masks[1].mask.sum()
    assert primeira > 0 and segunda > 0


# --------------------------------------------------------------- a rede da NYU
def test_a_rede_diz_por_que_nao_rodou_sem_as_quatro_incidencias():
    from ipe.ai import densidade_nyu as N
    p, aviso = N.prever({"L-CC": np.zeros((10, 10), np.float32)})
    assert p.size == 0 and "quatro incidências" in aviso and "R-CC" in aviso


def test_a_rede_diz_por_que_nao_rodou_sem_o_arquivo(tmp_path):
    from ipe.ai import densidade_nyu as N
    pode, motivo = N.disponivel(dados=tmp_path)
    if pode:                       # numa máquina que já tenha o modelo instalado, não há o que testar
        return
    assert "modelo" in motivo or "onnxruntime" in motivo


def test_o_nome_da_incidencia_para_a_rede():
    from ipe.ai import densidade_nyu as N
    assert N.chave("L", "MLO") == "L-MLO" and N.chave("R", "cc") == "R-CC"
    assert N.chave("R", "SIO") == "R-MLO"                # oblíqua conta como MLO
    assert N.chave("", "CC") == "" and N.chave("L", "XCCL") == ""


def test_a_rede_recebe_a_parede_toracica_sempre_a_esquerda():
    """Espelhar por engano troca a resposta da rede: nas imagens da NYU a mama começa na coluna 0."""
    from ipe.ai import densidade_nyu as N
    arr = np.zeros((400, 300), np.float32)
    arr[100:300, 200:299] = 1000.0                       # mama encostada na direita
    pronta = N.preparar(arr, parede_a_esquerda=False)
    assert pronta.shape == (N.ALTURA, N.LARGURA)
    esq = pronta[:, :N.LARGURA // 4].mean()
    dire = pronta[:, -N.LARGURA // 4:].mean()
    assert esq > dire                                    # depois do espelho, a mama está à esquerda
