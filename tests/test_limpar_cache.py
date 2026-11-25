"""0.100.120: Limpar o cache do Ipê."""
import os
import time
from types import SimpleNamespace

import pytest

from ipe.core import limpar_cache as LC


def _velha(p, horas=10):
    t = time.time() - horas * 3600
    os.utime(p, (t, t))


def test_pastas_temporarias_so_as_velhas_e_do_ipe(tmp_path):
    velha = tmp_path / "dv_totalseg_x"
    velha.mkdir()
    (velha / "a.bin").write_bytes(b"x" * 1000)
    _velha(velha)
    nova = tmp_path / "ipe_dce_y"
    nova.mkdir()                                     # de agora: uma IA pode estar usando
    alheia = tmp_path / "outra_coisa"
    alheia.mkdir()
    _velha(alheia)
    arq = tmp_path / "dv_arquivo"
    arq.write_text("x")                              # arquivo, não pasta
    assert LC.pastas_temporarias(base=tmp_path) == [velha]
    n, b, f = LC.apagar([velha])
    assert (n, b, f) == (1, 1000, 0) and not velha.exists() and nova.exists() and alheia.exists()


def test_atualizacoes_baixadas(tmp_path):
    pasta = tmp_path / "Atualizacoes"
    pasta.mkdir()
    (pasta / "Ipe-0.100.119-win.exe").write_bytes(b"y" * 10)
    paths = SimpleNamespace(data=tmp_path)
    lista = LC.atualizacoes_baixadas(paths)
    assert len(lista) == 1
    assert LC.apagar(lista)[:2] == (1, 10) and LC.atualizacoes_baixadas(paths) == []
    assert LC.atualizacoes_baixadas(SimpleNamespace(data=tmp_path / "nada")) == []


class _Rpc:
    def __init__(self, remoto):
        self.remoto = remoto

    def rpc(self, nome, uid):
        assert nome == "series_for_study"
        return [SimpleNamespace(series_uid=u, num_images=n) for u, n in self.remoto.items()]


class _Local:
    def __init__(self, local):
        self.local = local

    def series_for_study(self, uid):
        return [SimpleNamespace(series_uid=u, num_images=n) for u, n in self.local.items()]


def _repo(remoto, local, trava=False):
    apagados = []

    def remove(uid):
        if trava:
            raise PermissionError("cadeado")
        apagados.append(uid)
    return SimpleNamespace(client=_Rpc(remoto), local=_Local(local), remove_cached=remove, apagados=apagados)


def test_exame_do_cache_so_sai_se_o_servidor_tem_tudo():
    r = _repo({"s1": 100, "s2": 50}, {"s1": 100, "s2": 50})
    assert LC.apagar_exame_do_cache(r, "U") == "ok" and r.apagados == ["U"]
    r = _repo({"s1": 100}, {"s1": 100, "s2": 5})              # série que só existe aqui
    assert LC.apagar_exame_do_cache(r, "U") == "so_aqui" and r.apagados == []
    r = _repo({"s1": 90}, {"s1": 100})                        # servidor com menos imagens
    assert LC.apagar_exame_do_cache(r, "U") == "so_aqui"
    r = _repo({}, {"s1": 1})                                  # servidor não conhece
    assert LC.apagar_exame_do_cache(r, "U") == "so_aqui"
    r = _repo({"s1": 1}, {"s1": 1}, trava=True)
    assert LC.apagar_exame_do_cache(r, "U") == "protegido"


def test_sem_servidor_nao_ha_exames_no_cache():
    assert LC.exames_do_cache(SimpleNamespace(remote=False)) == []


def test_frame_cache_zera_a_conta():
    import numpy as np

    from ipe.imaging.series import FrameCache
    c = FrameCache(64)
    img = SimpleNamespace(pixels=np.zeros((100, 100), np.uint16))
    c.put(("a", 0), img)
    assert c.usado_bytes() == 20000
    c.clear()
    assert c.usado_bytes() == 0


def test_dialogo_limpa_a_memoria_e_as_pastas(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox, QWidget
    QApplication.instance() or QApplication([])
    import numpy as np

    from ipe.imaging.series import FrameCache
    from ipe.ui.limpar_cache_dialogo import LimparCacheDialog
    base = tmp_path / "tmp"
    base.mkdir()
    velha = base / "ipe_flames_z"
    velha.mkdir()
    _velha(velha)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(base))
    pasta_at = tmp_path / "Atualizacoes"
    pasta_at.mkdir()
    (pasta_at / "x.exe").write_bytes(b"1")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: 0)

    class Janela(QWidget):
        pass
    j = Janela()
    j.cache = FrameCache(64)
    j.cache.put(("a", 0), SimpleNamespace(pixels=np.zeros((10, 10), np.uint8)))
    j.repo = SimpleNamespace(remote=False)
    j.paths = SimpleNamespace(data=tmp_path)
    j.all_viewer_tabs = lambda: []
    d = LimparCacheDialog(j)
    assert not d.c_exames.isVisible() and d.c_temp.isEnabled() and d.c_atual.isEnabled()
    d.limpar()
    assert j.cache.usado_bytes() == 0 and not velha.exists() and not list(pasta_at.iterdir())
