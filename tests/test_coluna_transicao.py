"""0.99.23: vértebra de transição e a numeração da coluna.

Pedido dele: o erro das duas S1 ao subir um nível e, sobretudo, *"como vamos lidar com as vértebras de
transição?"*. Escolhas: lombarizada / sacralizada; contar pela C2 e pela última costela; Castellvi como
sugestão. Ele não tem exames com transição: os fantomas aqui são geométricos — corpos de 20 mm, discos
de 8 mm, apófises a 28–40 mm da linha média, sacro largo embaixo.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from ipe.ai import coluna as COL
from ipe.imaging.volume import Volume

D = 2.0                       # mm por voxel nos três eixos
NX, NY = 60, 30               # ±60 mm no direita-esquerda


def _volume(nz, nx=NX):
    return Volume(np.zeros((nz, NY, nx), np.int16), np.array([-(nx // 2) * D, 0.0, 0.0]),
                  np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, -D]), D, D, None, "")


def _coluna(modelos, *, sacro="sacrum", disco=4, rudimentar=False, costelas=(), apofise=None, nx=NX,
            nao_encosta=False):
    """`modelos`: nome que a IA dá a cada corpo livre, de cima para baixo. Devolve (vol, rotulos).
    `costelas`: índices dos corpos com costela (dos dois lados). `apofise`: "direita"/"esquerda"/"ambas"
    — apófise da última livre descendo até encostar na asa sacral."""
    nz = len(modelos) * (10 + disco) + 40
    vol = _volume(nz, nx)
    vert = np.zeros(vol.data.shape, np.uint8)
    disc = np.zeros(vol.data.shape, np.uint8)
    rib = np.zeros(vol.data.shape, np.uint8)
    c = nx // 2
    classes, cl_rib = {}, {}
    k = 0
    for n, nome in enumerate(modelos):
        cid = n + 1
        vert[k:k + 10, 8:22, c - 12:c + 12] = cid
        classes[cid] = f"vertebrae_{nome}"
        if n in costelas:
            for lado, sl in (("left", slice(c + 16, c + 26)), ("right", slice(c - 26, c - 16))):
                rid = len(cl_rib) + 1
                rib[k + 3:k + 7, 12:18, sl] = rid
                cl_rib[rid] = f"rib_{lado}_{n + 1}"
        k += 10
        ultima = n == len(modelos) - 1
        h = 1 if (ultima and rudimentar) else disco
        disc[k:k + h, 9:21, c - 11:c + 11] = 1
        if ultima and apofise:
            lados = {"direita": [-1], "esquerda": [1], "ambas": [-1, 1]}[apofise]
            for s in lados:
                xs = slice(c + 14, c + 21) if s > 0 else slice(c - 21, c - 14)
                fim = k + h - (2 if nao_encosta else 0)
                vert[k - 10:fim, 10:18, xs] = cid
        k += h
    sid = len(modelos) + 1
    vert[k:k + 30, 6:24, c - 25:c + 25] = sid
    classes[sid] = sacro
    rotulos = {"vert": (vert, classes), "disc": (disc, {1: "intervertebral_discs"})}
    if cl_rib:
        rotulos["rib"] = (rib, cl_rib)
    return vol, rotulos


CERV = [f"C{i}" for i in range(2, 8)]
TOR = [f"T{i}" for i in range(1, 13)]
LOMB = [f"L{i}" for i in range(1, 6)]


# ------------------------------------------------------------------ o defeito das duas S1
def test_subir_um_nivel_nao_da_duas_s1():
    vol, rot = _coluna(["T12"] + LOMB, sacro="vertebrae_S1")
    niv = COL.nomear(vol, rot)
    assert niv.nomes("vertebra") == ["T12"] + LOMB + ["S1"]
    obj = COL.objeto(vol, niv)
    COL.renumerar(obj, 1)
    niveis = [COL.nivel_de(mv) for mv in obj.volumes if "-" not in COL.nivel_de(mv)]
    assert niveis == ["L1", "L2", "L3", "L4", "L5", "S1", "S2"] and len(set(niveis)) == len(niveis)
    rot_ = {COL.nivel_de(mv): mv.label for mv in obj.volumes}
    assert rot_["S1"] == "S1 lombarizada" and rot_["S2"] == "Sacro (S2)" and "S1-S2" in rot_
    assert obj.numeracao.tipo_lombossacral == "lombarizada"
    # mais um: passaria de S2 — recusa sem mexer em nada
    with pytest.raises(COL.ForaDaColuna):
        COL.renumerar(obj, 1)
    assert "S2" in [COL.nivel_de(mv) for mv in obj.volumes] and "L1" in [COL.nivel_de(mv) for mv in obj.volumes]
    with pytest.raises(COL.ForaDaColuna):
        COL.deslocar("C1", -1)


# ------------------------------------------------------------------ contar pela C2
def test_c2_conta_seis_lombares_e_a_sexta_e_s1_lombarizada():
    # a IA pôs "L5" em duas vértebras: contando da C2, a de baixo é S1 lombarizada e o sacro é S2
    vol, rot = _coluna(CERV + TOR + LOMB + ["L5"])
    niv = COL.nomear(vol, rot)
    assert niv.numeracao.ancora == "c2"
    vs = niv.nomes("vertebra")
    assert vs[-3:] == ["L5", "S1", "S2"] and len(set(vs)) == len(vs)
    assert "S1-S2" in niv.nomes("disco") and "L5-S1" in niv.nomes("disco")
    assert niv.numeracao.tipo_lombossacral == "lombarizada"
    assert any("lombarizada" in a for a in niv.avisos)
    rot_ = {n.nome: (n.rotulo or n.nome) for n in niv.itens}
    assert rot_["S1"] == "S1 lombarizada" and rot_["S2"] == "Sacro (S2)"
    frase = COL.frase_do_laudo(niv.numeracao)
    assert "S1 lombarizada" in frase and "a partir de C2" in frase


def test_c2_conta_quatro_lombares_e_l5_fundida_ao_sacro():
    vol, rot = _coluna(CERV + TOR + ["L1", "L2", "L3", "L4"])
    niv = COL.nomear(vol, rot)
    assert niv.numeracao.tipo_lombossacral == "fundida"
    sacro = next(n for n in niv.itens if n.sacro)
    assert sacro.nome == "L5" and sacro.rotulo == "Sacro (L5 sacralizada)"
    assert niv.nomes("disco")[-1] == "L4-L5"
    assert "fundida ao sacro" in COL.frase_do_laudo(niv.numeracao)


def test_c2_conserta_a_numeracao_errada_da_ia():
    # a IA começou a lombar uma antes (chamou T12 de L1); a C2 manda
    errados = CERV + TOR[:-1] + ["L1", "L2", "L3", "L4", "L5", "L5"]
    vol, rot = _coluna(errados)
    niv = COL.nomear(vol, rot)
    assert niv.nomes("vertebra")[-7:] == ["T12", "L1", "L2", "L3", "L4", "L5", "S1"]
    assert niv.numeracao.tipo_lombossacral == ""


def test_falta_vertebra_no_caminho_nao_conta_pela_c2():
    vol, rot = _coluna(CERV + TOR + LOMB)
    vert, cl = rot["vert"]
    alvo = next(i for i, c in cl.items() if c == "vertebrae_T6")
    vert[vert == alvo] = 0                                # a IA não achou a T6
    niv = COL.nomear(vol, rot)
    assert niv.numeracao.ancora == "modelo"
    assert any("falta vértebra" in e for e in niv.numeracao.evidencias)


# ------------------------------------------------------------------ última costela
def test_ultima_costela_e_a_t12_sem_c2():
    # TC lombar: a IA chamou a T12 de L1 (contagem deslocada); a costela mais baixa diz que é T12
    vol, rot = _coluna(["T11", "L1", "L2", "L3", "L4", "L5"], costelas=(0, 1), sacro="vertebrae_S1")
    niv = COL.nomear(vol, rot)
    assert niv.numeracao.ancora == "costela"
    assert niv.nomes("vertebra") == ["T11", "T12", "L1", "L2", "L3", "L4", "L5"]
    assert niv.numeracao.ultima_costela == "T12"
    # abaixo da T12 só há quatro livres: a L5 é a que está fundida ao sacro
    assert niv.numeracao.tipo_lombossacral == "fundida"


def test_c2_e_costela_em_l1_e_transicao_toracolombar():
    vol, rot = _coluna(CERV + TOR + LOMB, costelas=tuple(range(6, 6 + 13)))   # T1…T12 e L1 com costela
    niv = COL.nomear(vol, rot)
    assert niv.numeracao.ancora == "c2_costela"
    assert niv.numeracao.ultima_costela == "L1" and niv.numeracao.toracolombar == "costela_l1"
    assert niv.numeracao.costelas_pares == 13
    assert any("L1 com costela" in a for a in niv.avisos) and any("13 pares" in a for a in niv.avisos)
    assert next(n for n in niv.itens if n.nome == "L1").rotulo == "L1 com costela"


def test_t12_sem_costela():
    vol, rot = _coluna(CERV + TOR + LOMB, costelas=tuple(range(6, 6 + 11)))   # T1…T11
    niv = COL.nomear(vol, rot)
    assert niv.numeracao.toracolombar == "t12_sem_costela" and niv.numeracao.costelas_pares == 11


# ------------------------------------------------------------------ disco rudimentar e Castellvi
def test_disco_rudimentar_e_apofise_encostada_sugerem_castellvi():
    vol, rot = _coluna(["T12"] + LOMB, rudimentar=True, apofise="direita")
    niv = COL.nomear(vol, rot)
    num = niv.numeracao
    assert any("rudimentar" in e for e in num.evidencias)
    assert num.castellvi == "IIa" and num.castellvi_lado == "à direita" and num.castellvi_fonte == "sugestão"
    assert num.tipo_lombossacral == "possivel"
    assert next(n for n in niv.itens if n.nome == "L5").rotulo == "L5 transição?"
    assert "Castellvi IIa à direita" in COL.frase_do_laudo(num)


def test_apofise_alta_sem_contato_e_castellvi_i_dos_dois_lados():
    vol, rot = _coluna(["T12"] + LOMB, apofise="ambas", nao_encosta=True)
    num = COL.nomear(vol, rot).numeracao
    assert num.castellvi == "Ib", num.castellvi_motivo


def test_serie_estreita_nao_avalia_castellvi():
    vol, rot = _coluna(["T12"] + LOMB, apofise="direita", nx=40)          # ±40 mm: não pega as apófises
    num = COL.nomear(vol, rot).numeracao
    assert num.castellvi == "" and "não avaliável" in num.castellvi_motivo


# ------------------------------------------------------------------ outra série como âncora
def test_outra_serie_com_c2_numera_a_lombar():
    vol, rot = _coluna(CERV + TOR + LOMB + ["L5"])
    ancora = COL.nomear(vol, rot)
    assert ancora.numeracao.ancora == "c2"
    # a lombar: só os corpos de baixo (mesmas coordenadas), com a IA errando por um
    k0 = 17 * 14                                           # começa na T12 (17 corpos acima)
    lvol = Volume(vol.data[k0:], vol.origin + np.array([0, 0, -k0 * D]), vol.row_dir, vol.col_dir,
                  vol.slice_vec, D, D, None, "")
    lrot = {}
    for t, (lab, cl) in rot.items():
        lrot[t] = (lab[k0:].copy(), dict(cl))
    v, cl = lrot["vert"]
    ren = {"vertebrae_T12": "vertebrae_L1", "vertebrae_L1": "vertebrae_L2", "vertebrae_L2": "vertebrae_L3",
           "vertebrae_L3": "vertebrae_L4", "vertebrae_L4": "vertebrae_L5", "vertebrae_L5": "vertebrae_L5"}
    lrot["vert"] = (v, {i: ren.get(c, c) for i, c in cl.items()})
    princ = COL.nomear(lvol, lrot)
    assert princ.numeracao.ancora == "modelo"
    novo = COL.com_ancora(lvol, lrot, princ, ancora, "SAG COLUNA TOTAL")
    assert novo.numeracao.ancora == "outra_serie"
    assert novo.nomes("vertebra")[0] == "T12" and novo.nomes("vertebra")[-2:] == ["S1", "S2"]
    assert novo.numeracao.tipo_lombossacral == "lombarizada"
    assert "SAG COLUNA TOTAL" in novo.numeracao.evidencias[0]


# ------------------------------------------------------------------ ajustar (a janela)
def test_ajustar_lombarizada_nenhuma_e_castellvi_do_medico():
    vol, rot = _coluna(["T12"] + LOMB)
    obj = COL.objeto(vol, COL.nomear(vol, rot))
    COL.ajustar(obj, lombossacral="lombarizada", castellvi="IIIa", castellvi_lado="à esquerda", quem="filipe")
    assert COL.ultima_livre(obj) == "S1" and obj.numeracao.tipo_lombossacral == "lombarizada"
    assert obj.numeracao.castellvi == "IIIa" and obj.numeracao.castellvi_fonte == "médico"
    assert obj.numeracao.confirmado_por == "filipe" and obj.numeracao.ancora == "medico"
    assert "S1 lombarizada" in [mv.label for mv in obj.volumes]
    assert "Castellvi IIIa à esquerda" in COL.frase_do_laudo(obj.numeracao)
    COL.ajustar(obj, lombossacral="", castellvi="")
    assert COL.ultima_livre(obj) == "L5" and obj.numeracao.tipo_lombossacral == ""
    assert "S1" in [mv.label for mv in obj.volumes]                  # o sacro volta a S1
    COL.ajustar(obj, lombossacral="sacralizada")
    assert COL.ultima_livre(obj) == "L5" and "L5 sacralizada" in [mv.label for mv in obj.volumes]


def test_ajustar_esta_vertebra_e_a():
    vol, rot = _coluna(["T12"] + LOMB)
    obj = COL.objeto(vol, COL.nomear(vol, rot))
    COL.ajustar(obj, passo=COL.POS["L5"] - COL.POS["L4"])            # a "L4" é a L5
    assert COL.ultima_livre(obj) == "S1"


# ------------------------------------------------------------------ SEG e memória por paciente
def test_seg_guarda_nivel_sacro_e_numeracao(env, tmp_path):
    import test_coluna as TC
    paths, db, repo = env
    uid, serie = TC._exame(env, tmp_path)
    t = TC._trabalho(env, uid, serie)
    try:
        rotulos, versao, _s = t.ler_rotulos()
        niveis = COL.nomear(t.vol, rotulos)
        saida = COL.gravar(t, niveis, versao, db, paths.storage)
        obj = COL.objeto_do_seg(saida["seg_path"], uid)
        assert any(getattr(mv, "sacro", False) and mv.nivel == "S1" for mv in obj.volumes)
        COL.ajustar(obj, lombossacral="lombarizada", castellvi="IIa", castellvi_lado="à direita", quem="x")
        COL.salvar_no_seg(saida["seg_path"], obj)
        relido = COL.objeto_do_seg(saida["seg_path"], uid)
        assert [mv.label for mv in relido.volumes if getattr(mv, "sacro", False)] == ["Sacro (S2)"]
        assert "S1 lombarizada" in [mv.label for mv in relido.volumes]
        assert relido.numeracao.castellvi == "IIa" and relido.numeracao.tipo_lombossacral == "lombarizada"
        # o próximo exame do mesmo paciente avisa se sair diferente
        COL.guardar_conferencia(repo, uid, relido.numeracao, "x")
        uid2, _s2 = TC._exame(env, tmp_path / "b")
        aviso = COL.aviso_das_anteriores(repo, uid2, COL.Numeracao(ancora="modelo"))
        assert "S1 lombarizada" in aviso and "26/10/2026" in aviso
        assert COL.aviso_das_anteriores(repo, uid2, relido.numeracao) == ""
    finally:
        t.limpar()


def test_janela_ajusta_grava_e_manda_a_frase(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    import test_coluna as TC
    from ipe.ui.viewer.coluna_numeracao import NumeracaoDialog
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = TC._exame(env, tmp_path)
    t = TC._trabalho(env, uid, serie)
    try:
        rotulos, versao, _s = t.ler_rotulos()
        saida = COL.gravar(t, COL.nomear(t.vol, rotulos), versao, db, paths.storage)
    finally:
        t.limpar()
    obj = COL.objeto_do_seg(saida["seg_path"], uid)
    # a vértebra sob o clique: o centro da L3
    l3 = next(mv for mv in obj.volumes if mv.nivel == "L3")
    centro = l3.origem + (np.array(l3.mascara.shape[::-1]) - 1) / 2 @ l3.matriz.T
    assert l3.contem(centro)
    dlg = NumeracaoDialog(None, obj, clicada="L3", repo=repo, study_uid=uid)
    assert dlg.c_vert.currentText() == "L3"
    dlg.c_ls.setCurrentIndex(4)                                       # S1 lombarizada
    assert "S1 lombarizada" in dlg.t_frase.toPlainText()
    assert COL.ultima_livre(obj) == "L5"                              # prévia não mexe no objeto
    frases = []
    dlg.laudo.connect(frases.append)
    feito = []
    dlg.aplicado.connect(lambda: feito.append(1))
    assert dlg.aplicar() and feito
    assert COL.ultima_livre(obj) == "S1"
    dlg.b_laudo.click()
    assert frases and "S1 lombarizada" in frases[0]
    dlg.close()
    app.processEvents()


def test_menu_tem_ajustar_e_tab_grava(env, tmp_path, monkeypatch):
    import time

    from PySide6.QtWidgets import QApplication, QMessageBox

    import test_coluna as TC
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = TC._exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.show()
    try:
        assert w.handle_external({"accession": "COL01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        vp = next(v for v in tab.viewports if v.frames)
        tab.segmentar_orgaos(vp, simular=True, tipo="coluna")
        fim = time.time() + 60
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and "Numeração:" in avisos[-1], avisos
        sub = next(a.menu() for a in vp.build_context_menu().actions() if a.text() == "Numeração da coluna")
        assert any(a.text().startswith("Ajustar a numeração") for a in sub.actions())
        dlg = tab.abrir_numeracao_coluna(vp, None)
        dlg.c_ls.setCurrentIndex(4)
        assert dlg.aplicar()
        col = tab.objetos_da_coluna(vp)[0]
        relido = COL.objeto_do_seg(col.caminho, uid)
        assert relido.numeracao.tipo_lombossacral == "lombarizada"
        r = repo.revisao_ia(uid, COL.MODULO_REVISAO)
        assert r is not None and r["estado"] == "aceito"
        # subir até sair da coluna: recusa e diz
        msgs = []
        tab.status_message.connect(msgs.append)
        assert tab.renumerar_coluna(vp, 1) == 0 and "Não renumerei" in msgs[-1]
        dlg.close()
    finally:
        w.close()


def test_serie_ancora_e_a_que_pega_da_c2_ate_a_lombar(env, tmp_path):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pat = {"name": "ANCORA^Teste", "id": "ANC1", "birth": "19700101", "sex": "F"}
    for_ = generate_uid()
    study = {"uid": generate_uid(), "date": "20261101", "accession": "ANC01", "description": "RM COLUNA",
             "for": for_}
    series = {}
    for nome, n, z0, num in (("SAG LOMBAR", 30, 100.0, 2), ("SAG COLUNA TOTAL", 330, 700.0, 3),
                             ("SAG CERVICAL", 60, 700.0, 4)):
        se = {"uid": generate_uid(), "number": num, "description": nome}
        series[nome] = se["uid"]
        for k in range(n):
            ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, se, "CT")
            ds.InstanceNumber = k + 1
            ds.ImagePositionPatient = [-8.0, -8.0, z0 - k * 2.0]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.PixelSpacing = [2.0, 2.0]
            ds.SliceThickness = 2.0
            _mono(ds, np.zeros((8, 8), np.int16), signed=True)
            _save(ds, tmp_path / nome)
    Importer(db, paths.storage).import_paths([tmp_path])
    uid = study["uid"]
    assert COL.serie_ancora(repo, uid, series["SAG LOMBAR"]) == series["SAG COLUNA TOTAL"]
    # a cervical não chega à lombar; e a total não é âncora dela mesma
    assert COL.serie_ancora(repo, uid, series["SAG COLUNA TOTAL"]) is None
