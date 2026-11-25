"""0.100.97: lote a partir de planilha — do PACS (em laço) até a planilha, pela janela. Só dados inventados."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from ipe.automation import lote as L  # noqa: E402
from ipe.automation import planilha as P  # noqa: E402


# ---------------------------------------------------------------- com o PACS de verdade (em laço) e a janela
@pytest.fixture()
def cena(env, tmp_path, monkeypatch):
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from pydicom.uid import generate_uid
    from test_gestao import No
    from test_web_mamografia import _serie
    from ipe.ai import calc_vascular as CV
    from ipe.ai import densidade_nyu as N
    from ipe.core.config import Settings
    from ipe.network.service import NetworkService
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    ex = {"uid": generate_uid(), "date": "20240309", "accession": "MGL1", "description": "MAMOGRAFIA DIGITAL",
          "for": generate_uid()}
    for k, (lado, view) in enumerate((("R", "CC"), ("L", "CC"), ("R", "MLO"), ("L", "MLO"))):
        _serie(tmp_path / "mg", ex, lado, view, k + 1, "right" if lado == "R" else "left")
    pacs = No(tmp_path / "pacs", "PACS")
    pacs.importar(tmp_path / "mg")
    assert pacs.server.start()
    info = pacs.repo.study_info(ex["uid"])
    st = Settings(paths.settings_file)
    st.set("dicom", dict(st.get("dicom", {}), enabled=False, http_enabled=False, ae_title="IPE"))
    net = NetworkService(db, repo, paths.storage, st)
    no = dict(pacs.como_no(), active=True)
    no.pop("id")
    no["id"] = repo.save_node(no)
    monkeypatch.setattr(N, "disponivel", lambda dados=None: (True, ""))
    monkeypatch.setattr(N, "do_exame", lambda vistas, dados=None: (np.array([0.05, 0.15, 0.7, 0.1]), ""))
    monkeypatch.setattr(CV, "disponivel", lambda dados=None: (True, ""))

    def mapa(img, dados=None, stop=None):
        p = np.zeros(img.shape, np.float32)
        p[img.shape[0] // 2: img.shape[0] // 2 + 60, img.shape[1] // 3: img.shape[1] // 3 + 3] = 0.9
        return p
    monkeypatch.setattr(CV, "mapa", mapa)
    yield {"app": app, "repo": repo, "db": db, "net": net, "st": st, "storage": paths.storage, "no": no, "ex": ex,
           "pid": info["patient_id"], "nasc": info.get("birth_date", ""), "pacs": pacs, "tmp": tmp_path}
    net.shutdown()
    pacs.close()


def _girar(app, cond, s=90):
    fim = time.time() + s
    while time.time() < fim:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_do_pacs_ate_a_planilha_pela_janela(cena, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from ipe.automation import lote_ipe as LP
    from ipe.printing import dispatch as D
    from ipe.ui.lote_dialogo import LoteDialog
    c = cena
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: avisos.append(a[2])))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: avisos.append(a[2])))
    pdfs, exp = c["tmp"] / "impressos", c["tmp"] / "exportados"
    pdfs.mkdir()
    exp.mkdir()
    D.save_destinations(c["st"], [D.Destination(name="Pasta PDF", kind="pdf", folder=str(pdfs))])
    lista = c["tmp"] / "lista.xlsx"
    P.gravar_xlsx(lista, [("LEIA-ME", [["Lista de teste"]]),
                          ("Pareamento", [["Prontuário", "Paciente", "Nascimento", "Data mamografia", "Agatston"],
                                          [c["pid"], "FANTOMA", "", "09/03/2024", 120],
                                          ["000000", "NINGUEM", "", "09/03/2024", 0],
                                          [c["pid"], "FANTOMA", "", "", 5]])])
    d = LoteDialog(c["repo"], c["db"], c["net"], c["st"], c["storage"], None)
    from PySide6.QtCore import Qt
    # 0.100.117: janela normal (minimiza no Ubuntu), não diálogo preso à janela principal
    assert d.windowType() == Qt.Window and d.windowFlags() & Qt.WindowMinimizeButtonHint
    d.iniciar()
    assert "Escolha a planilha" in avisos[-1]
    assert d.abrir_arquivo(str(lista))
    assert d.c_aba.currentText() == "Pareamento"                 # a aba com a chave, não o LEIA-ME
    assert d.tipos() == ["id", "nome", "nascimento", "data", "ignorar"]
    assert d.e_saida.text().endswith("lista-Ipe.xlsx")
    assert "3 linhas; 2 com chave" in d.l_lista.text() and "1 só com o ID" in d.l_lista.text()
    # o modelo pronto da mama: MG, densidade e calcificações
    d.c_modelo.setCurrentIndex(d.c_modelo.findData("Densidade e calcificações da mama"))
    d.usar_modelo()
    cfg = d.config()
    assert cfg.ias == ["densidade", "calc_vascular"] and cfg.modalidades == ["MG"] and cfg.apagar_depois
    d.l_nos.item(0).setCheckState(Qt.Checked)
    d.c_imprimir.setCurrentIndex(d.c_imprimir.findData("dest:Pasta PDF"))
    d.e_exportar.setText(str(exp))
    d.c_formato.setCurrentIndex(d.c_formato.findData("png"))
    # simular: acha sem baixar
    d.iniciar(simular=True)
    assert _girar(c["app"], lambda: d.linha_de_fundo is None), d.diario.toPlainText()
    assert c["repo"].study_info(c["ex"]["uid"]) is None and not Path(d.e_saida.text()).exists()
    assert "Linha 2: achado (simulação)" in d.diario.toPlainText()
    d.iniciar()
    assert d.b_parar.isEnabled() and not d.b_iniciar.isEnabled()
    assert _girar(c["app"], lambda: d.linha_de_fundo is None, 180), d.diario.toPlainText()
    texto = d.diario.toPlainText()
    assert "Linha 2: feito — IAs: 2 de 2" in texto, texto
    assert "Linha 3: não encontrado" in texto and "Linha 4: linha sem data" in texto
    assert "FANTOMA" not in texto and "Terminado." in d.l_estado.text() and d.barra.value() == 3
    saida = Path(d.e_saida.text())
    assert P.abas(saida)[:3] == ["Resultados", "IA · Densidade mamária", "IA · Calcificações vasculares"]
    t = P.ler_xlsx(saida, "Resultados")
    assert t[0][:5] == ["Prontuário", "Paciente", "Nascimento", "Data mamografia", "Agatston"] and t[1][4] == 120
    r = dict(zip(t[0], t[1]))
    assert r["Ipê: situação"] == "feito" and r["Ipê: Study UID"] == c["ex"]["uid"] and r["Ipê: nº de acesso"] == "MGL1"
    assert r["Ipê: de onde veio"] == "PACS" and "arquivo" in str(r["Ipê: impresso"])
    dens = P.ler_xlsx(saida, "IA · Densidade mamária")
    linha = dict(zip(dens[0], dens[1]))
    assert linha["Categoria (rede NYU)"] == "C" and linha["Prob. C"] == 0.7 and linha["Situação"] == "feita"
    bac = dict(zip(*P.ler_xlsx(saida, "IA · Calcificações vasculares")[:2]))
    assert bac["Área, mama pior (mm²)"] > 0 and bac["Imagens medidas"] == 4
    assert list(pdfs.glob("*.pdf")), "a série de conferência não foi impressa"
    assert list(exp.rglob("*.png")), "a série de conferência não foi exportada"
    assert c["repo"].study_info(c["ex"]["uid"]) is None             # baixado só para o lote: apagado
    # zeros à esquerda: o PACS guarda o ID de outro jeito e acha assim mesmo; outro número, não
    serv = LP.servicos(c["repo"], c["db"], c["net"], c["st"], c["storage"])
    crit = {"pid": "000" + c["pid"], "data_de": "20240309", "data_ate": "20240309", "modalidades": ["MG"]}
    assert [e["study_uid"] for e in L.filtrar(serv.no(str(c["no"]["id"]), crit), crit)] == [c["ex"]["uid"]]
    crit["pid"] = "9" + c["pid"]
    assert L.filtrar(serv.no(str(c["no"]["id"]), crit), crit) == []
    # de novo, sem refazer: nada a fazer
    d.k_refazer.setChecked(False)
    d.iniciar()
    assert "já têm resposta" in avisos[-1]
    d.close()


def test_cliente_de_servidor_nao_roda_aqui():
    from ipe.automation import lote_ipe as LP

    class Cliente:
        def is_cached(self, uid):
            return False
    ok, motivo = LP.pronto(Cliente())
    assert not ok and "cliente de um servidor" in motivo


def test_cliente_so_avisa_a_copia_quando_chega_inteiro():
    """0.100.107: o servidor só apaga o exame dele depois que o cliente diz que copiou — e o cliente só diz isso
    quando o exame chegou inteiro (tenta de novo o que faltou)."""
    import threading
    from types import SimpleNamespace

    from ipe.ui.lote_dialogo import LoteDialog
    avisos, faltas = [], [["s2"], ["s2"], []]

    class Repo:
        client = SimpleNamespace(rpc=lambda *a: avisos.append(a))

        def baixar_em_segundo_plano(self, uid):
            t = threading.Thread(target=lambda: None)
            t.start()
            return t, None, None

        def missing_series(self, uid):
            return faltas.pop(0)

        def is_cached(self, uid):
            return True
    eu = SimpleNamespace(repo=Repo(), parar=threading.Event(), remoto_id="L1", _avisar=lambda t: None)
    LoteDialog._copiar(eu, "1.2.3")
    assert avisos == [("lote_copiado", "L1", "1.2.3", -1)] and not faltas      # na 3ª tentativa
    avisos.clear()
    faltas.extend([["s1"]] * 3)
    LoteDialog._copiar(eu, "1.2.3")
    assert avisos == []                                                    # nunca chegou inteiro: não avisa
