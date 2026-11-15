"""0.100.51: calcificações vasculares da mama (SCU-Net). Imagens fabricadas, nada de paciente."""
import sys
from pathlib import Path

import numpy as np
import pydicom
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_densidade_revisao import _exame  # noqa: E402
from test_densidade_tela import _grava  # noqa: E402

from ipe.ai import calc_vascular as C  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def test_modelo_no_repositorio_com_licenca():
    import hashlib
    f = RAIZ / "modelos" / C.ARQUIVO
    assert f.is_file()
    assert hashlib.sha256(f.read_bytes()).hexdigest().startswith("8aa966780481298e")
    assert "MIT License" in (RAIZ / "modelos" / "LICENSE-SCU-Net.txt").read_text()
    assert C.caminho() == f or C.caminho() is not None
    from ipe import creditos
    assert any("SCU-Net" in c.nome for c in creditos.CREDITOS)


def test_preparo_igual_ao_dos_autores():
    a = (np.random.default_rng(1).random((300, 700)) * 255).astype(np.uint8)
    cv2 = pytest.importorskip("cv2")
    assert (C.mediana5(a) == cv2.medianBlur(a, 5)).all()
    import builtins
    real = builtins.__import__

    def sem_cv2(nome, *a_, **k):
        if nome == "cv2":
            raise ImportError
        return real(nome, *a_, **k)
    builtins.__import__ = sem_cv2
    try:
        assert (C.mediana5(a, faixa=37) == cv2.medianBlur(a, 5)).all()       # o caminho sem OpenCV dá o mesmo
    finally:
        builtins.__import__ = real
    assert C.inicios(3328) == [0, 480, 960, 1440, 1920, 2400, 2816]          # get_slices dos autores
    assert C.inicios(512) == [0] and C.inicios(300) == [0]
    m = np.random.default_rng(2).random((37, 53)) > 0.8
    assert (C.descompactar(C.compactar(m), m.shape) == m).all()
    assert C.grau_pela_area(0) == "ausente" and C.grau_pela_area(5) == "leve"
    assert C.grau_pela_area(30) == "moderada" and C.grau_pela_area(500) == "acentuada"


def test_rede_roda_e_junta_os_pedacos():
    pytest.importorskip("onnxruntime")
    rng = np.random.default_rng(3)
    img = np.zeros((900, 1100), np.uint8)
    img[100:850, 150:1050] = (90 + rng.random((750, 900)) * 60).astype(np.uint8)
    p = C.mapa(C.mediana5(img))
    assert p.shape == img.shape and 0 <= float(p.min()) and float(p.max()) <= 1
    assert float(p[:90, :140].max()) < 0.5                                    # fundo: nada marcado


def test_protese_achada_e_descartada():
    pytest.importorskip("cv2")
    rng = np.random.default_rng(4)
    h, w = 1600, 1200
    y, x = np.mgrid[0:h, 0:w]
    mama = ((y - 800) / 700) ** 2 + ((x - 1200) / 1000) ** 2 < 1
    import cv2
    tecido = cv2.resize(rng.random((40, 30)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    img = np.where(mama, 60 + tecido * 120 + rng.random((h, w)) * 20, 0).clip(0, 255).astype(np.float32)
    assert C.regiao_da_protese(img.astype(np.uint8), 0.1) is None              # sem prótese
    prot = ((y - 800) / 350) ** 2 + ((x - 1050) / 300) ** 2 < 1
    img[prot] = 230
    reg = C.regiao_da_protese(img.astype(np.uint8), 0.1)
    assert reg is not None and reg[800, 1050] and reg[800, 1050 - 300 - 20]   # dentro e na faixa da borda
    assert not reg[800, 350]


def test_exame_guardar_confirmar_previa(env, tmp_path, monkeypatch):
    _p, _db, repo = env
    arquivos = _exame(tmp_path)
    monkeypatch.setattr(repo, "files_for_study", lambda uid, series_uids=None: arquivos, raising=False)
    monkeypatch.setattr(C, "disponivel", lambda dados=None: (True, ""))

    def mapa(img, dados=None, stop=None):                 # uma "artéria" de 30 px (6 mm) na direita, nada na esquerda
        p = np.zeros(img.shape, np.float32)
        if img[:, :20].mean() > img[:, -20:].mean():       # mama direita encostada à esquerda da imagem
            p[100:130, 40:42] = 0.9
            p[200, 60] = 0.9                               # um pontinho isolado: fora da conta
        return p
    monkeypatch.setattr(C, "mapa", mapa)
    m = C.medir_exame(repo, "7.7")
    assert set(m["vistas"]) == {"R-CC", "L-CC", "R-MLO", "L-MLO"} and len(m["imagens"]) == 4
    v = m["vistas"]["R-CC"]
    assert v["sop"] and v["chave"] == "R-CC" and not v["extra"]
    assert v["area_mm2"] == pytest.approx(60 * 0.04) and v["area_total_mm2"] == pytest.approx(61 * 0.04)
    assert m["por_mama"]["L"] == 0 and m["sugestao"] == "ausente"            # 2,4 mm² < 5: provisório
    C.guardar_medida(repo, "7.7", m)
    g = C.guardada(repo, "7.7")
    assert g["estado"] == "auto" and "arquivo" not in g["vistas"]["R-CC"]
    C.confirmar(repo, "7.7", g, "leve", "med")
    g = C.guardada(repo, "7.7")
    assert g["grau"] == "leve" and g["estado"] == "editado" and g["revisor"] == "med"
    C.guardar_medida(repo, "7.7", m)                                          # medir de novo mantém o grau
    assert C.guardada(repo, "7.7")["grau"] == "leve"
    with pytest.raises(ValueError):
        C.confirmar(repo, "7.7", g, "muita", "med")
    cam = C.arquivo_da_imagem(repo, "7.7", g["vistas"]["R-CC"])
    assert cam == C.arquivos_das_vistas(repo, "7.7")["R-CC"]
    rgb = C.previa(pydicom.dcmread(cam), g["vistas"]["R-CC"], 120)
    assert rgb.ndim == 3 and (rgb[..., 0] > 200).any() and (rgb[..., 1] < 100).any()   # o vermelho aparece
    assert C.previa_png(pydicom.dcmread(cam), g["vistas"]["R-CC"])[:4] == b"\x89PNG"
    assert C.frase_do_laudo("moderada") == "Calcificações vasculares moderadas."


def test_sem_modelo_avisa(env, tmp_path, monkeypatch):
    _p, _db, repo = env
    arquivos = _exame(tmp_path)
    monkeypatch.setattr(repo, "files_for_study", lambda uid, series_uids=None: arquivos, raising=False)
    monkeypatch.setattr(C, "disponivel", lambda dados=None: (False, "sem o modelo"))
    m = C.medir_exame(repo, "7.7")
    assert m["aviso"] == "sem o modelo" and m["sugestao"] is None


def test_janela(env, tmp_path, monkeypatch):
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication

    from ipe.ui import calc_vascular_exame as J
    app = QApplication.instance() or QApplication([])
    _p, _db, repo = env
    arquivos = _exame(tmp_path)
    monkeypatch.setattr(repo, "files_for_study", lambda uid, series_uids=None: arquivos, raising=False)
    monkeypatch.setattr(C, "disponivel", lambda dados=None: (True, ""))

    def mapa(img, dados=None, stop=None):
        p = np.zeros(img.shape, np.float32)
        p[50:250, 30:34] = 0.9                                                 # 200 px × 4 = 32 mm² por vista
        return p
    monkeypatch.setattr(C, "mapa", mapa)
    textos = []

    class Aba(QObject):
        status_message = Signal(str)

        def __init__(self):
            super().__init__()
            self.repo, self.study_uid, self.active = repo, "7.7", None

        def mandar_texto_ao_laudo(self, texto):
            textos.append(texto)
    d = J.CalcVascularJanela(Aba())
    d.medidor.wait(60000)
    for _ in range(50):
        app.processEvents()
        if d.medida is not None:
            break
    assert d.medida["sugestao"] == "moderada" and d.grau() == "moderada"
    assert "mama direita 32 mm²" in d.lb_rede.text()
    q = d.quadros["R-CC"]
    assert not q.imagem.pixmap().isNull() and "32 mm²" in q.legenda.text() and not q.bt_prox.isVisible()
    d.radios["acentuada"].setChecked(True)
    assert d.confirmar(True)
    assert C.guardada(repo, "7.7")["grau"] == "acentuada" and textos == ["Calcificações vasculares acentuadas."]
    d.close()
    d2 = J.CalcVascularJanela(Aba())
    assert d2.medidor is None and d2.grau() == "acentuada"
    d2.close()


def test_botao_na_barra_da_mamografia():
    from ipe.ui.viewer import aplicacoes as A
    assert "calc_vascular" in A.APLICACOES and A.APLICACOES["calc_vascular"].modalidades == frozenset({"MG"})
    assert "calc_vascular.medir" in (RAIZ / "src/ipe/ui/viewer/barra.py").read_text()


def test_todas_as_imagens_e_rolar(env, tmp_path, monkeypatch):
    """0.100.52: repetição, compressão localizada e outra incidência entram; a janela rola entre as da incidência."""
    from pydicom.dataset import Dataset
    from pydicom.sequence import Sequence
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication

    from ipe.ui import calc_vascular_exame as J
    app = QApplication.instance() or QApplication([])
    _p, _db, repo = env
    arquivos = _exame(tmp_path)
    rep = _grava(tmp_path, "RCC2.dcm", vista="CC", lado="R")                   # repetição da CC direita
    spot = _grava(tmp_path, "RCCspot.dcm", vista="CC", lado="R")               # compressão localizada
    ds = pydicom.dcmread(spot.path)
    mod = Dataset()
    mod.CodeMeaning = "Spot Compression"
    ds.ViewModifierCodeSequence = Sequence([mod])
    ds.InstanceNumber = 3
    ds.save_as(spot.path)
    ml = _grava(tmp_path, "RML.dcm", vista="ML", lado="R")                      # perfil
    todos = arquivos + [rep.path, spot.path, ml.path]
    monkeypatch.setattr(repo, "files_for_study", lambda uid, series_uids=None: todos, raising=False)
    monkeypatch.setattr(C, "disponivel", lambda dados=None: (True, ""))
    lista = C.imagens_do_exame(repo, "7.7")
    assert [x["chave"] for x in lista].count("R-CC") == 3 and lista[-1]["chave"] == "R-ML"
    assert sum(x["extra"] for x in lista) == 1 and "compressão localizada" in next(x for x in lista if x["extra"])["modificadores"]

    def mapa(img, dados=None, stop=None):
        p = np.zeros(img.shape, np.float32)
        p[50:150, 30:34] = 0.9                                                 # 16 mm² por imagem
        return p
    monkeypatch.setattr(C, "mapa", mapa)
    m = C.medir_exame(repo, "7.7")
    assert len(m["imagens"]) == 7 and "R-ML" in m["vistas"]
    assert any("Compressão localizada" in a for a in m["avisos"])
    C.guardar_medida(repo, "7.7", m)

    class Aba(QObject):
        status_message = Signal(str)

        def __init__(self):
            super().__init__()
            self.repo, self.study_uid, self.active = repo, "7.7", None

        def mandar_texto_ao_laudo(self, texto):
            pass
    d = J.CalcVascularJanela(Aba())
    assert set(d.quadros) == {"R-CC", "L-CC", "R-MLO", "L-MLO", "R-ML"}
    q = d.quadros["R-CC"]
    assert len(q.imagens) == 3 and not q.bt_prox.isHidden() and "(1/3)" in q.legenda.text()
    vistos = set()
    for _ in range(3):
        vistos.add(q.atual()["sop"])
        assert not q.imagem.pixmap().isNull()
        q.ir(1)
    assert len(vistos) == 3 and "(1/3)" in q.legenda.text()                    # deu a volta
    while not q.atual()["extra"]:
        q.ir(1)
    assert "fora da conta" in q.legenda.text()
    assert d.quadros["R-ML"].bt_prox.isHidden()
    d.close()
    app.processEvents()
