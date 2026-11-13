"""0.100.33: sessão preparada do PET/CT — junto com a carga tumoral ficam guardadas as referências do
PERCIST/Deauville (fígado e mediastino) e o registro com o PET/CT anterior; o exame preparado abre na Leitura PET."""
from types import SimpleNamespace

import numpy as np
import pytest
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import generate_uid

from test_carga_pet import _fantoma
from test_modelos_extras import DZ, PX, _serie

from ipe.ai import carga_pet as CP
from ipe.ai import pet_preparo as PP


@pytest.fixture(autouse=True)
def _figado_do_fantoma(monkeypatch):
    from ipe.imaging import pet_onco as PO
    monkeypatch.setattr(PO, "DIAM_FIGADO_MM", 12.0)        # o fígado do fantoma não comporta a esfera de 3 cm


class _Cfg(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


def _exame(tmp_path, env, nome: str, data: str, desloc=(0, 0, 0), pid="PREP1"):
    """O fantoma da carga tumoral; `desloc` (k, j, i) empurra a anatomia (o paciente deitou noutro lugar)."""
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    ct, pet = _fantoma("fdg")
    if any(desloc):
        ct = np.roll(ct, desloc, axis=(0, 1, 2))
        pet = np.roll(pet, desloc, axis=(0, 1, 2))
    pat = {"name": "EXEMPLO^Preparo", "id": pid, "birth": "19550101", "sex": "M"}
    study = {"uid": generate_uid(), "date": data, "accession": f"PP{nome}", "description": "PET-CT ONCO",
             "for": generate_uid()}
    rf = Dataset()
    rf.Radiopharmaceutical = "Fluorodeoxyglucose"
    _serie(tmp_path / nome, pat, study, "CT STD", "CT", ct, 2)
    _serie(tmp_path / nome, pat, study, "PET AC", "PT", np.rint(pet * 100).astype(np.int16), 3,
           {"Units": "GML", "RescaleSlope": 0.01, "RadiopharmaceuticalInformationSequence": Sequence([rf])})
    Importer(db, paths.storage).import_paths([tmp_path / nome])
    return study["uid"]


def _rodar(env, study, cfg=None):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    cfg = cfg if cfg is not None else _Cfg({PP.CHAVE_TEMPO: 20})
    serie, motivo = CP.escolher_serie(repo, study)
    assert serie, motivo
    t = TS.Trabalho(repo, FrameCache(64), cfg, study, serie, simular=True)
    FE.preparar_trabalho(t, CP)
    t.preparar()
    try:
        t.rodar_aqui()
        res, versao = FE.rodar_conta(t, CP, cfg)
        saida = FE.gravar(t, CP, res, versao, db, paths.storage, repo, cfg)
    finally:
        t.limpar()
    return res, saida


def test_aorta_descendente_abaixo_do_arco():
    """Aorta de corpo inteiro: ascendente (na frente) só nos 6 cm de cima; o centro tem que cair na descendente."""
    pet = SimpleNamespace(dz=-3.0, dy=4.0, dx=4.0,
                          voxel_to_patient=lambda i, j, k: np.array([4.0 * i, 4.0 * j, 300.0 - 3.0 * k]))
    m = np.zeros((120, 40, 40), bool)
    m[10:110, 26:31, 18:23] = True            # descendente (posterior: j maior), de z=270 a z=-27
    m[10:30, 10:15, 18:23] = True             # ascendente (anterior), só nos 6 cm de cima
    k, j, i = PP.centro_da_aorta_descendente(m, pet)
    assert 10 + 80 / 3 <= k <= 10 + 130 / 3 + 1 and 26 <= j <= 30 and 18 <= i <= 22
    # de cabeça para baixo na pilha (o corte 0 é o pé): o topo continua sendo a cabeça
    pet2 = SimpleNamespace(dz=3.0, dy=4.0, dx=4.0,
                           voxel_to_patient=lambda i, j, k: np.array([4.0 * i, 4.0 * j, 3.0 * k]))
    k2, j2, _i2 = PP.centro_da_aorta_descendente(m[::-1], pet2)
    assert 119 - (10 + 130 / 3 + 1) <= k2 <= 119 - (10 + 80 / 3) and 26 <= j2 <= 30
    # campo parcial (aorta curta, as duas no mesmo corte): fica com a de trás
    curta = np.zeros((20, 40, 40), bool)
    curta[2:18, 26:31, 18:23] = True
    curta[2:18, 10:15, 18:23] = True
    _k, j3, _i = PP.centro_da_aorta_descendente(curta, pet)
    assert 26 <= j3 <= 30
    assert PP.centro_da_aorta_descendente(np.zeros((5, 5, 5), bool), pet) is None


def test_referencias_e_registro_com_o_anterior(env, tmp_path, monkeypatch):
    paths, db, repo = env
    anterior = _exame(tmp_path, env, "ant", "20260508", desloc=(2, 3, -2))
    atual = _exame(tmp_path, env, "atu", "20261108")
    assert PP.exame_anterior(repo, atual)[0] == anterior and PP.exame_anterior(repo, anterior)[0] == ""
    # o registro de verdade tem os seus testes (test_registro_rigido); o fantoma daqui é de blocos lisos, sem
    # textura para a correlação. Aqui: quem é registrado com quem, e o que fica guardado.
    from ipe.imaging import registro_rigido as RR
    pedidos = []
    M = np.eye(4)
    M[:3, 3] = [-2 * PX, 3 * PX, 2 * DZ]

    def registrar(va, vb, metrica, tempo_max=0, progresso=None):
        pedidos.append((va.shape, vb.shape, metrica, tempo_max))
        assert progresso() is True
        return SimpleNamespace(M=M, translacao=M[:3, 3].copy(), rotacao_total=0.0, valor=0.93,
                               qualidade=lambda: "boa")
    monkeypatch.setattr(RR, "registrar", registrar)
    res, saida = _rodar(env, atual)
    assert pedidos == [((40, 48, 48), (40, 48, 48), "ncc", 20.0)]
    p = res.preparo
    assert p is not None and p.anterior_uid == anterior and p.anterior_data == "20260508"
    # referências: o fígado do fantoma tem SUV 2,0 e a aorta 1,5
    # (a esfera do fígado pega a borda da lesão hepática do fantoma, que ocupa quase todo o lobo)
    assert p.figado and 2.0 <= p.figado["media"] < 3.0 and p.figado["como"] == "auto"
    assert p.figado["diam_mm"] == 12.0 and len(p.figado["centro_mm"]) == 3
    assert p.mediastino and abs(p.mediastino["media"] - 1.5) < 0.1 and p.mediastino["diam_mm"] == 10.0
    # registro: a anatomia do anterior está deslocada (i −2, j +3, k +2 voxels)
    assert p.M is not None and p.qualidade == "boa" and p.valor == 0.93
    t = np.asarray(p.translacao)
    assert np.allclose(t, M[:3, 3])
    # gravado: onde a janela PET… lê as referências, e como o registro do botão
    assert saida["preparo"] == {"refs": ["figado", "mediastino"], "registro": True}
    refs = (repo.lesion_track("PREP1")["data"]["refs"])[atual]
    assert refs["figado"]["como"] == "auto" and refs["mediastino"]["media"] == p.mediastino["media"]
    desl, _rel = repo.get_registration(atual, anterior)
    assert np.allclose(desl, t, atol=1e-6)
    assert repo.get_registration_matriz(atual, anterior) is not None
    txt = PP.texto(p)
    assert txt == "Sessão preparada: referências de fígado e mediastino; registrado com o exame de 08/05/2026 (boa)."
    assert "Sessão preparada" in CP.mensagem(res, 1.0)
    assert PP.preparado(repo, atual) and not PP.preparado(repo, anterior)


def test_nao_troca_o_que_foi_feito_a_mao(env, tmp_path):
    paths, db, repo = env
    anterior = _exame(tmp_path, env, "ant2", "20260101", pid="PREP2")
    atual = _exame(tmp_path, env, "atu2", "20260701", pid="PREP2")
    manual = {"media": 9.9, "dp": 0.1, "max": 10.0, "n": 5, "centro": [1, 1, 1], "diam_mm": 30.0, "como": "clique"}
    repo.save_lesion_track("PREP2", data={"refs": {atual: {"figado": manual}}})
    repo.save_registration(atual, anterior, [11.0, 0.0, 0.0], 0.0, method="manual")
    res, saida = _rodar(env, atual)
    assert saida["preparo"] == {"refs": ["mediastino"], "registro": False}
    refs = repo.lesion_track("PREP2")["data"]["refs"][atual]
    assert refs["figado"]["media"] == 9.9 and refs["mediastino"]["como"] == "auto"
    assert repo.get_registration(atual, anterior)[0][0] == 11.0            # o registro à mão continua
    assert res.preparo.M is None and "já existia" in PP.texto(res.preparo)
    # rodar de novo troca a referência automática (não a feita à mão)
    res2, saida2 = _rodar(env, atual)
    assert saida2["preparo"]["refs"] == ["mediastino"]


def test_desligado_e_sem_anterior(env, tmp_path):
    paths, db, repo = env
    so = _exame(tmp_path, env, "so", "20261108", pid="PREP3")
    res, saida = _rodar(env, so, _Cfg({PP.CHAVE_PREPARAR: False}))
    assert res.preparo is None and "preparo" not in saida
    assert repo.lesion_track("PREP3")["data"].get("refs") is None
    res, saida = _rodar(env, so)
    assert res.preparo.figado and res.preparo.anterior_uid == "" and saida["preparo"]["registro"] is False
    assert PP.texto(res.preparo) == "Sessão preparada: referências de fígado e mediastino."


def test_registro_fraco_nao_e_guardado(env, tmp_path, monkeypatch):
    paths, db, repo = env
    anterior = _exame(tmp_path, env, "ant4", "20260101", pid="PREP4")
    atual = _exame(tmp_path, env, "atu4", "20260701", pid="PREP4")
    from ipe.imaging import registro_rigido as RR
    ruim = SimpleNamespace(M=np.eye(4), translacao=np.zeros(3), rotacao_total=0.0, valor=0.2, qualidade=lambda: "fraca")
    monkeypatch.setattr(RR, "registrar", lambda *a, **k: ruim)
    res, saida = _rodar(env, atual)
    assert res.preparo.M is None and saida["preparo"]["registro"] is False
    assert repo.get_registration(atual, anterior) is None
    assert any("fraco" in a for a in res.avisos)


def test_abre_na_leitura_pet(env, tmp_path):
    """O exame preparado, sem estado guardado, abre na Leitura PET; com a opção desligada, não."""
    from PySide6.QtWidgets import QApplication

    from ipe.ui.viewer.viewer_tab import ViewerTab
    QApplication.instance() or QApplication([])
    chamadas = []
    falso = SimpleNamespace(settings=_Cfg(), estado_pode=lambda: True, _arranjo_de_protocolo=False,
                            series=[SimpleNamespace(modality="CT"), SimpleNamespace(modality="PT")],
                            repo=SimpleNamespace(achados=lambda uid, f: [{"tipo": "x"}] if f == "carga_pet" else []),
                            study_uid="1.2", leitura_pet=lambda: chamadas.append(1))
    assert ViewerTab.abrir_sessao_preparada(falso) is True
    QApplication.processEvents()
    assert chamadas == [1]
    falso.settings = _Cfg({PP.CHAVE_ABRIR: False})
    assert ViewerTab.abrir_sessao_preparada(falso) is False
    falso.settings = _Cfg()
    falso.repo = SimpleNamespace(achados=lambda uid, f: [])
    assert ViewerTab.abrir_sessao_preparada(falso) is False                     # sem a carga tumoral feita
    falso.repo = SimpleNamespace(achados=lambda uid, f: [{"tipo": "x"}])
    falso._arranjo_de_protocolo = True
    assert ViewerTab.abrir_sessao_preparada(falso) is False                     # protocolo de exibição manda


def test_opcoes_na_tela_de_cad_ia():
    assert [c[0] for c in CP.CAIXAS] == [PP.CHAVE_PREPARAR, PP.CHAVE_ABRIR]
    assert CP.config(None, PP.CHAVE_PREPARAR) is True and CP.config(None, PP.CHAVE_ABRIR) is True
    assert PP.config(None, PP.CHAVE_TEMPO) == 60
