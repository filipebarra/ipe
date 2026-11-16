"""0.100.57: densidade e calcificações vasculares automáticas na chegada e no banco; confirmar; SR no exame."""
import sys
import time
from pathlib import Path

import numpy as np
import pydicom
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mamografia import servidor_mg  # noqa: E402,F401


@pytest.fixture()
def redes(monkeypatch):
    """As duas redes de mentira: NYU diz C; a SCU-Net acha uma "artéria" de 6 mm em toda imagem."""
    from ipe.ai import calc_vascular as C
    from ipe.ai import densidade_nyu as N
    monkeypatch.setattr(N, "disponivel", lambda dados=None: (True, ""))
    monkeypatch.setattr(N, "do_exame", lambda vistas, dados=None: (np.array([0.05, 0.15, 0.7, 0.1]), ""))
    monkeypatch.setattr(C, "disponivel", lambda dados=None: (True, ""))

    def mapa(img, dados=None, stop=None):
        p = np.zeros(img.shape, np.float32)
        p[img.shape[0] // 2: img.shape[0] // 2 + 60, img.shape[1] // 3: img.shape[1] // 3 + 3] = 0.9
        return p
    monkeypatch.setattr(C, "mapa", mapa)


class _Prefs(dict):
    def get(self, k, padrao=None):
        return super().get(k, padrao)

    def set_do_computador(self, k, v):
        self[k] = v

    def save(self):
        pass


def _esperar(cond, s=60):
    fim = time.time() + s
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_chegada_confirmar_e_sr(servidor_mg, redes):
    from ipe.ai import calc_vascular as C
    from ipe.ai import mama_sr as MS
    from ipe.automation import mama_auto as MA
    from ipe.imaging import densidade_revisao as R
    srv = servidor_mg
    repo = srv.repo
    atual, anterior = srv.estudos
    assert MA.e_mamografia(repo.study_info(atual)) and MA.local(repo)
    assert MA.falta(repo, atual) == ["densidade", "calc_vascular"]
    prontos = []
    fila = MA.Fila(repo, aviso=lambda u, out: prontos.append((u, out)))
    assert fila.pedir(atual) and not fila.pedir(atual)          # a mesma não entra duas vezes
    assert _esperar(lambda: prontos)
    u, out = prontos[0]
    assert u == atual and out["densidade"] == "C" and not out["erros"], out
    assert MA.falta(repo, atual) == []
    pend = MA.pendentes(repo, atual)
    assert set(pend) == {"densidade", "calc_vascular"}
    # sem confirmar tudo, nada de SR
    assert MS.depois_de_confirmar(repo, srv.db, srv.storage, atual) is None
    R.confirmar(repo, atual, R.guardada(repo, atual), "d", "dra.teste")
    assert MS.depois_de_confirmar(repo, srv.db, srv.storage, atual) is None   # falta a calcificação
    C.confirmar(repo, atual, C.guardada(repo, atual), "leve", "dra.teste")
    assert MA.pendentes(repo, atual) == {}
    r = MS.depois_de_confirmar(repo, srv.db, srv.storage, atual, "Dra. Teste")
    assert r and len(r["series"]) == 3 and r["marcadas"] >= 1
    nossas = {s.description: s for s in repo.series_for_study(atual) if s.description in MS.NOSSAS}
    assert set(nossas) == set(MS.NOSSAS)
    sr = pydicom.dcmread(repo.files_for_study(atual, [nossas[MS.DESC_SR].series_uid])[0])
    assert sr.SOPClassUID == MS.COMPREHENSIVE_SR and sr.Modality == "SR"
    nomes = [i.ConceptNameCodeSequence[0].CodeMeaning for i in sr.ContentSequence]
    assert "Breast density" in nomes and "Breast arterial calcification" in nomes
    dens = next(i for i in sr.ContentSequence if i.ConceptNameCodeSequence[0].CodeMeaning == "Breast density")
    assert any(getattr(x, "TextValue", "").startswith("D") for x in dens.ContentSequence)
    bac = next(i for i in sr.ContentSequence if i.ConceptNameCodeSequence[0].CodeMeaning == "Breast arterial calcification")
    imgs = [x for x in bac.ContentSequence if x.ValueType == "CONTAINER"]
    assert len(imgs) == r["marcadas"]
    refs = {x.ReferencedSOPSequence[0].ReferencedSOPInstanceUID for c in imgs for x in c.ContentSequence
            if x.ValueType == "IMAGE"}
    marcadas = {pydicom.dcmread(f, stop_before_pixels=True).SOPInstanceUID
                for f in repo.files_for_study(atual, [nossas[MS.DESC_MARCADAS].series_uid])}
    assert marcadas <= refs
    ev = sr.CurrentRequestedProcedureEvidenceSequence[0]
    assert ev.StudyInstanceUID == atual and len(ev.ReferencedSeriesSequence) >= 3
    sc = pydicom.dcmread(repo.files_for_study(atual, [nossas[MS.DESC_RESUMO].series_uid])[0])
    assert sc.BurnedInAnnotation == "YES" and sc.pixel_array.shape[2] == 3
    import os
    if os.environ.get("IPE_MAMA_FOTO"):                    # para olhar: o resumo e uma marcada
        from PIL import Image
        Image.fromarray(sc.pixel_array).save(os.environ["IPE_MAMA_FOTO"] + "_resumo.png")
        f = repo.files_for_study(atual, [nossas[MS.DESC_MARCADAS].series_uid])[0]
        Image.fromarray(pydicom.dcmread(f).pixel_array).save(os.environ["IPE_MAMA_FOTO"] + "_marcada.png")
    # confirmar de novo (outro grau): o SR é refeito, sem duplicar as séries
    C.confirmar(repo, atual, C.guardada(repo, atual), "moderada", "dra.teste")
    r2 = MS.depois_de_confirmar(repo, srv.db, srv.storage, atual)
    assert r2 and r2["sr"] != r["sr"]
    assert sum(1 for s in repo.series_for_study(atual) if s.description in MS.NOSSAS) == 3
    # a varredura do banco: só o anterior falta; uma vez por versão
    prefs = _Prefs()
    fila2 = MA.Fila(repo, settings=prefs)
    assert MA.varrer_banco(fila2, prefs) == 1
    assert _esperar(lambda: fila2.vazia() and prefs.get(MA.CHAVE_VARREDURA) == MA.VARREDURA)
    assert MA.falta(repo, anterior) == []
    assert MA.varrer_banco(MA.Fila(repo, settings=prefs), prefs) == 0


def test_desligado_e_cliente(servidor_mg, monkeypatch):
    from ipe.automation import mama_auto as MA
    monkeypatch.delenv("IPE_SEM_MAMA_AUTO")
    assert not MA.ligado(_Prefs({MA.CHAVE: False})) and MA.ligado(_Prefs())

    class Cliente:
        def is_cached(self, uid):
            return True
    assert not MA.local(Cliente())


def test_abrir_pede_confirmacao_em_sequencia(qtbot, servidor_mg, redes):
    """Ao abrir a mamografia: abre a densidade; fechada ela, as calcificações. Só uma vez por aba."""
    from PySide6.QtWidgets import QDialog

    from ipe.automation import mama_auto as MA
    from ipe.ui.viewer.mamografia_aba import MamografiaMixin
    repo = servidor_mg.repo
    atual, _ant = servidor_mg.estudos
    MA.medir(repo, atual)
    abertas = []

    class Aba(MamografiaMixin):
        settings = _Prefs()
        study_uid = atual

        def __init__(self):
            self.repo = repo

        def _janela(self, nome):
            d = QDialog()
            qtbot.addWidget(d)
            abertas.append((nome, d))
            d.show()
            return d

        def densidade_do_exame(self):
            return self._janela("densidade")

        def calc_vascular_do_exame(self):
            return self._janela("calc")
    a = Aba()
    a.confirmar_mama_pendente()
    assert [n for n, _d in abertas] == ["densidade"]
    abertas[0][1].reject()
    assert [n for n, _d in abertas] == ["densidade", "calc"]
    a.confirmar_mama_pendente()                    # de novo na mesma aba: nada
    assert len(abertas) == 2
    b = Aba()
    b.settings = _Prefs({MA.CHAVE_ABRIR: False})
    b.confirmar_mama_pendente()
    assert len(abertas) == 2


def test_navegador_pede_confirmacao_e_grava_sr(servidor_mg, redes):
    """No Ipê Web: abrir a mamografia medida na chegada abre a densidade; confirmada, as calcificações; confirmadas
    as duas, o servidor grava o SR."""
    from ipe.ai import mama_sr as MS
    from ipe.automation import mama_auto as MA
    from ipe.central import web as WEB
    if not WEB.site_instalado():
        pytest.skip("site não construído")
    pw = pytest.importorskip("playwright.sync_api")
    from test_web_mamografia import _abrir
    srv = servidor_mg
    atual, _ant = srv.estudos
    MA.medir(srv.repo, atual)
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, srv, atual)
        pg.wait_for_selector(".painel-densidade input[value=c]", timeout=20000)
        pg.click(".painel-densidade button:has-text('Confirmar')")
        pg.wait_for_selector(".painel-calcvasc input[value=leve]", timeout=20000)
        pg.check(".painel-calcvasc input[value=leve]")
        pg.click(".painel-calcvasc button:has-text('Confirmar')")
        assert _esperar(lambda: sum(1 for s in srv.repo.series_for_study(atual) if s.description in MS.NOSSAS) == 3, 30)
        b.close()
    assert not erros, erros


def test_motor_poe_na_fila_so_mamografia(servidor_mg, monkeypatch):
    from types import SimpleNamespace

    from ipe.automation import mama_auto as MA
    from ipe.automation.engine import AutomationEngine
    monkeypatch.delenv("IPE_SEM_MAMA_AUTO")
    pedidos = []
    eng = SimpleNamespace(settings=_Prefs(), repo=servidor_mg.repo,
                          mama=SimpleNamespace(pedir=lambda u: pedidos.append(u) or True))
    atual, _ant = servidor_mg.estudos
    assert AutomationEngine.mama_ia(eng, atual) and pedidos == [atual]
    assert not AutomationEngine.mama_ia(eng, "1.2.3", {"modalities": "CT"})
    eng.settings = _Prefs({MA.CHAVE: False})
    assert not AutomationEngine.mama_ia(eng, atual)
