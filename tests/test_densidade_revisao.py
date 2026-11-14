"""0.100.43: revisão da densidade mamária — o programa sugere (rede da NYU e % de área), o médico confirma ou corrige,
e a concordância sai no fim. Exames fabricados (fantomas), nada de paciente."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_densidade_tela import _grava  # noqa: E402

from ipe.imaging import densidade_revisao as R  # noqa: E402


def _exame(pasta, fracao=0.3):
    return [_grava(pasta, f"{lado}{vista}.dcm", vista=vista, lado=lado, fracao=fracao).path
            for lado in ("R", "L") for vista in ("CC", "MLO")]


def test_escolhe_as_quatro_incidencias_e_o_aparelho(tmp_path):
    cabs = [R.cabecalho(p) for p in _exame(tmp_path)]
    vistas, aparelho, avisos = R.escolher_vistas(cabs)
    assert set(vistas) == {"R-CC", "L-CC", "R-MLO", "L-MLO"}
    assert avisos == []
    assert aparelho == "?"                                  # o fantoma não diz o fabricante


def test_falta_de_incidencia_vira_aviso(tmp_path):
    cabs = [R.cabecalho(p) for p in _exame(tmp_path)[:3]]
    vistas, _ap, avisos = R.escolher_vistas(cabs)
    assert len(vistas) == 3 and "L-MLO" in avisos[0]


def test_tomo_e_bruta_ficam_fora(tmp_path):
    c = R.cabecalho(_exame(tmp_path)[0])
    assert R.escolher_vistas([dict(c, tomo=True)])[0] == {}
    assert R.escolher_vistas([dict(c, processamento=True)])[0] == {}
    assert R.cabecalho(_grava(tmp_path, "tc.dcm", modalidade="CT").path) is None


def test_sugestao_do_exame_sem_a_rede(tmp_path, monkeypatch):
    from ipe.ai import densidade_nyu as N
    monkeypatch.setattr(N, "disponivel", lambda dados=None: (False, "sem o modelo"))
    vistas, _a, _v = R.escolher_vistas([R.cabecalho(p) for p in _exame(tmp_path, fracao=0.3)])
    s = R.sugerir(vistas)
    assert s["area_pd"] is not None and s["area"] in R.CATEGORIAS
    assert set(s["area_por_mama"]) == {"R", "L"}
    assert s["fcm_pd"] is not None and s["fcm"] in R.CATEGORIAS            # 0.100.44: o fuzzy também
    assert abs(s["fcm_pd"] - s["area_pd"]) < 10 and len(s["imagens"]) == 4
    assert s["nyu"] is None and s["nyu_aviso"] == "sem o modelo"     # a rede falha sozinha, com o motivo


def test_sugestao_com_a_rede(tmp_path, monkeypatch):
    import numpy as np

    from ipe.ai import densidade_nyu as N
    monkeypatch.setattr(N, "disponivel", lambda dados=None: (True, ""))
    monkeypatch.setattr(N, "do_exame", lambda vistas, dados=None: (np.array([0.05, 0.15, 0.7, 0.1]), ""))
    vistas, _a, _v = R.escolher_vistas([R.cabecalho(p) for p in _exame(tmp_path)])
    s = R.sugerir(vistas)
    assert s["nyu"] == "c" and s["nyu_probs"] == [0.05, 0.15, 0.7, 0.1]


def test_controle_e_fixo_por_exame_e_respeita_a_fracao():
    uids = [f"1.2.{i}" for i in range(2000)]
    marcados = [u for u in uids if R.de_controle(u, "med", 0.10)]
    assert 150 < len(marcados) < 250
    assert marcados == [u for u in uids if R.de_controle(u, "med", 0.10)]   # o mesmo sorteio ao reabrir
    assert not any(R.de_controle(u, "med", 0.0) for u in uids[:50])


def test_kappa_ponderado():
    assert R.kappa_ponderado(list("abcd"), list("abcd")) == pytest.approx(1.0)
    # um erro de uma categoria pesa menos que um de três
    perto = R.kappa_ponderado(list("abcdabcd"), list("abcdabdd"))
    longe = R.kappa_ponderado(list("abcdabcd"), list("abcdabca"))
    assert 0 < longe < perto < 1
    assert R.kappa_ponderado([], []) is None
    assert R.kappa_ponderado(list("cccc"), list("cccc")) is None     # sem variação nenhuma


def test_concordancia_separa_controle_e_aparelho():
    revs = [
        {"categoria": "c", "nyu": "c", "area": "b", "controle": False, "aparelho": "GE"},
        {"categoria": "b", "nyu": "b", "area": "b", "controle": False, "aparelho": "GE"},
        {"categoria": "d", "nyu": "c", "area": "", "controle": True, "aparelho": "Hologic"},
        {"categoria": "x", "nyu": "a", "area": "a", "controle": False, "aparelho": "GE"},
    ]
    c = R.concordancia(revs)
    assert c["revisados"] == 4 and c["avaliaveis"] == 3 and c["nao_avaliaveis"] == 1
    nyu = c["metodos"]["nyu"]
    assert nyu["total"]["n"] == 3 and nyu["total"]["exato"] == pytest.approx(2 / 3)
    assert nyu["total"]["denso"] == pytest.approx(1.0)                 # c × d: os dois densos
    assert nyu["controle"]["n"] == 1 and nyu["vista"]["n"] == 2
    assert set(nyu["aparelhos"]) == {"GE", "Hologic"}
    assert c["metodos"]["area"]["total"]["n"] == 2                    # sem a sugestão, fica fora da conta
    txt = R.texto_da_concordancia(c)
    assert "Rede (NYU) (n = 3)" in txt and "controle" in txt
    assert R.linhas_csv([dict(revs[0], study_uid="1", nyu_probs=[0.1, 0.2, 0.6, 0.1])])[1][7:11] == \
        ["0.1", "0.2", "0.6", "0.1"]


def test_revisao_no_banco(env):
    _paths, _db, repo = env
    rid = repo.salvar_revisao_densidade("1.2.3", {"categoria": "c", "controle": True, "nyu": "b",
                                                  "nyu_probs": [0.1, 0.6, 0.2, 0.1], "area_pd": 41.5, "area": "b",
                                                  "aparelho": "GE Senographe Pristina", "avisos": ["um aviso"]},
                                         usuario="med")
    # rever o mesmo exame troca a resposta, não duplica
    assert repo.salvar_revisao_densidade("1.2.3", {"categoria": "d"}, usuario="med") == rid
    repo.salvar_revisao_densidade("1.2.3", {"categoria": "b"}, usuario="outro")
    meus = repo.revisoes_densidade("med")
    assert len(meus) == 1 and meus[0]["categoria"] == "d" and meus[0]["nyu"] == ""
    assert len(repo.revisoes_densidade(todos=True)) == 2


def test_janela_da_revisao(env, tmp_path, monkeypatch):
    """A fila, a sugestão, a resposta por tecla, o controle e a concordância — com um "main" de mentira."""
    from types import SimpleNamespace

    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication

    from ipe.ai import densidade_nyu as N
    from ipe.core.config import Settings
    from ipe.ui import densidade_revisao as J
    app = QApplication.instance() or QApplication([])
    _paths, _db, repo = env
    monkeypatch.setattr(N, "disponivel", lambda dados=None: (False, "sem o modelo"))
    exames = {}
    for k in range(3):
        pasta = tmp_path / f"ex{k}"
        pasta.mkdir()
        exames[f"9.{k}"] = _exame(pasta, fracao=0.2 + 0.2 * k)
    linhas = [SimpleNamespace(study_uid=u, patient_name="EXEMPLO^FANTOMA", study_date=f"2026110{k + 1}",
                              description="MAMOGRAFIA", modalities="MG") for k, u in enumerate(exames)]
    monkeypatch.setattr(repo, "search_studies", lambda **kw: linhas, raising=False)
    monkeypatch.setattr(repo, "files_for_study", lambda uid, series_uids=None: exames[uid], raising=False)
    abertos, fechados = [], []
    abas = {}

    class Main:
        def all_viewer_tabs(self):
            return list(abas.values())

        def open_study(self, uid):
            abertos.append(uid)
            abas[uid] = SimpleNamespace(study_uid=uid)

        def fechar_aba(self, tab):
            fechados.append(tab.study_uid)
            abas.pop(tab.study_uid, None)

    j = J.RevisaoDensidadeJanela(Main(), repo, Settings(tmp_path / "s.json"))
    j.sp_controle.setValue(0)
    j.de.setDate(QDate(2026, 11, 1))
    j.montar_fila()
    assert [r.study_uid for r in j.fila] == ["9.2", "9.1", "9.0"]      # o mais novo primeiro
    assert abertos == ["9.2"]
    for _ in range(100):
        app.processEvents()
        if all(u in j.sugestoes for u in ("9.2", "9.1")):
            break
        j._threads and next(iter(j._threads.values())).wait(200)
    assert "9.1" in j.sugestoes                                      # o próximo já vem adiantado
    assert "% de área" in j.lb_sugestao.text()
    j.responder("c")
    assert j.i == 1 and abertos == ["9.2", "9.1"] and fechados == ["9.2"]
    rev = repo.revisoes_densidade(j.usuario)
    assert len(rev) == 1, repo.revisoes_densidade(todos=True)
    assert rev[0]["categoria"] == "c" and rev[0]["area"] in R.CATEGORIAS and not rev[0]["controle"]
    assert "% de área (Otsu) (n = 1)" in j.lb_conc.text()
    assert R.guardada(repo, "9.2")["categoria"] == "c"                  # e no exame, junto da medida
    j.ir(0)                                                          # voltar mostra a resposta dada
    assert "2px solid" in j.botoes["c"].styleSheet()
    # controle: com 100%, a sugestão fica escondida até a resposta
    j.sp_controle.setValue(100)
    j.ir(2)
    assert "controle" in j.lb_sugestao.text()
    j.close()


# ---------------------------------------------------------------- 0.100.44: o botão da densidade do exame
def test_medida_guardada_e_confirmacao(env, tmp_path, monkeypatch):
    from ipe.ai import densidade_nyu as N
    _paths, _db, repo = env
    monkeypatch.setattr(N, "disponivel", lambda dados=None: (False, "sem o modelo"))
    arquivos = _exame(tmp_path)
    monkeypatch.setattr(repo, "files_for_study", lambda uid, series_uids=None: arquivos, raising=False)
    m = R.medir_exame(repo, "5.5")
    R.guardar_medida(repo, "5.5", m)
    g = R.guardada(repo, "5.5")
    assert g["estado"] == "auto" and g["area_pd"] == m["area_pd"] and "categoria" not in g
    R.confirmar(repo, "5.5", g, "b", "med")
    g = R.guardada(repo, "5.5")
    assert g["categoria"] == "b" and g["estado"] == "editado" and g["revisor"] == "med"   # a rede não deu b
    assert repo.revisoes_densidade("med")[0]["fcm"] == m["fcm"]
    # medir de novo não apaga a confirmação
    R.guardar_medida(repo, "5.5", R.medir_exame(repo, "5.5"))
    assert R.guardada(repo, "5.5")["categoria"] == "b"
    assert "heterogeneamente" in R.frase_do_laudo("c")


def test_janela_do_exame(env, tmp_path, monkeypatch):
    """Abre, mede (não havia medida), marca a categoria da rede de saída, confirma e manda ao laudo."""
    import numpy as np
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication

    from ipe.ai import densidade_nyu as N
    from ipe.ui import densidade_exame as J
    app = QApplication.instance() or QApplication([])
    _paths, _db, repo = env
    monkeypatch.setattr(N, "disponivel", lambda dados=None: (True, ""))
    monkeypatch.setattr(N, "do_exame", lambda vistas, dados=None: (np.array([0.05, 0.15, 0.7, 0.1]), ""))
    arquivos = _exame(tmp_path)
    monkeypatch.setattr(repo, "files_for_study", lambda uid, series_uids=None: arquivos, raising=False)
    textos = []

    class Aba(QObject):
        status_message = Signal(str)

        def __init__(self):
            super().__init__()
            self.repo, self.study_uid, self.active = repo, "7.7", None

        def open_report(self, uid):
            pass

        def mandar_texto_ao_laudo(self, texto):
            textos.append(texto)

    aba = Aba()
    d = J.DensidadeExameJanela(aba)
    d.medidor.wait(60000)
    for _ in range(50):
        app.processEvents()
        if d.medida is not None:
            break
    assert d.medida["nyu"] == "c"
    assert "C — heterogeneamente densa" in d.lb_rede.text() and "<b>70%</b>" in d.lb_probs.text()
    assert "(Otsu)" in d.lb_area.text() and "(fuzzy)" in d.lb_area.text()
    assert d.categoria() == "c"                                      # de saída, a da rede
    d.radios["d"].setChecked(True)
    assert d.confirmar(True)
    assert R.guardada(repo, "7.7")["categoria"] == "d"
    assert textos and "extremamente densas" in textos[0]             # sem laudo BI-RADS aberto: vai como texto
    assert "Confirmado: D" in d.lb_confirmado.text()
    d.close()
    # reabrir mostra o que já foi medido e confirmado, sem medir de novo
    d2 = J.DensidadeExameJanela(aba)
    assert d2.medidor is None and d2.categoria() == "d"
    d2.close()


def test_medida_aparece_mesmo_sem_guardar(env, tmp_path, monkeypatch):
    """0.100.45: servidor antigo recusa guardar ("método não permitido"): a medida aparece, com o aviso."""
    from ipe.ai import densidade_nyu as N
    from ipe.ui import densidade_exame as J
    _paths, _db, repo = env
    monkeypatch.setattr(N, "disponivel", lambda dados=None: (False, "sem o modelo"))
    arquivos = _exame(tmp_path)
    monkeypatch.setattr(repo, "files_for_study", lambda uid, series_uids=None: arquivos, raising=False)

    def recusa(*a, **k):
        raise PermissionError("método não permitido: salvar_revisao_ia")
    monkeypatch.setattr(repo, "salvar_revisao_ia", recusa, raising=False)
    saiu = {}
    t = J.Medidor(repo, "8.8")
    t.pronto.connect(lambda u, m, e: saiu.update(m=m, e=e))
    t.run()
    assert saiu["e"] == "" and saiu["m"]["area_pd"] is not None
    assert any("atualize o servidor" in a for a in saiu["m"]["avisos"])
