"""0.100.27: a instalação das IAs numa janela do Ipê, com o andamento, os erros e o veredito."""
import sys
import time

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.ui import instalador_janela as IJ


def _rodar(j, limite=30.0):
    app = QApplication.instance()
    fim = time.time() + limite
    while j.resultado is None and time.time() < fim:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    assert j.resultado is not None, "a instalação de teste não terminou"


@pytest.fixture
def app(tmp_path, monkeypatch):
    a = QApplication.instance() or QApplication([])
    monkeypatch.setattr(IJ, "pasta_do_log", lambda: tmp_path)
    IJ._ABERTAS.clear()
    yield a
    for j in list(IJ._ABERTAS.values()):
        j.proc.kill()
        j.proc.waitForFinished(2000)
    IJ._ABERTAS.clear()


def _py(codigo: str) -> list[str]:
    return [sys.executable, "-c", codigo]


def test_instalacao_que_da_certo(app, tmp_path):
    cod = ("import sys,time\nprint('[1/2] Preparando')\nsys.stdout.write('10%\\r50%\\r100%\\n')\n"
           "print('Collecting torch')\nprint('[2/2] Conferindo')\nprint('Pronto')")
    j = IJ.abrir("t", "Teste", _py(cod), conferir=lambda: (True, ""))
    assert j.isVisible() and not j.isModal()
    _rodar(j)
    txt = j.texto.toPlainText()
    assert j.resultado is True and "Instalado sem erros" in j.l_estado.text()
    assert "[1/2] Preparando" in txt and "Pronto" in txt and "=== Instalado sem erros" in txt
    assert "\n100%\n" in txt and "\n10%" not in txt and "\n50%" not in txt                    # a barra de progresso reescreve a linha
    assert j.l_passo.text().startswith("[2/2]") and not j.l_erros.isVisible()
    assert not j.b_parar.isEnabled() and j.b_fechar.text() == "Fechar"
    log = (tmp_path / "instalacao_ia.log").read_text(encoding="utf-8")
    assert "=== Teste" in log and "[2/2] Conferindo" in log


def test_erro_aparece_e_o_veredito_nao_mente(app):
    cod = "print('baixando');print('ERROR: No matching distribution found for X');print('[ERRO] Falhou')"
    j = IJ.abrir("t", "Teste", _py(cod), conferir=lambda: (False, "o ambiente não foi criado"))
    _rodar(j)
    assert j.resultado is False and len(j.erros) == 2
    assert "NÃO ficou instalado" in j.l_estado.text() and "o ambiente não foi criado" in j.l_estado.text()
    assert j.l_erros.isVisible() and "Linhas de erro:" in j.texto.toPlainText()
    # código de saída diferente de zero também é erro, mesmo sem linha de erro
    j2 = IJ.abrir("u", "Teste", _py("import sys; print('oi'); sys.exit(3)"), conferir=lambda: (True, ""))
    _rodar(j2)
    assert j2.resultado is False and "houve" in j2.l_estado.text()
    # instalado, mas com linha de erro no meio: avisa, não comemora
    j3 = IJ.abrir("v", "Teste", _py("print('[ERRO] um modelo não baixou')"), conferir=lambda: (True, ""))
    _rodar(j3)
    assert j3.resultado is False and "está instalado, mas houve 1" in j3.l_estado.text()


def test_comando_que_nao_existe(app):
    j = IJ.abrir("t", "Teste", ["programa-que-nao-existe-ipe"], conferir=lambda: (False, ""))
    _rodar(j)
    assert j.resultado is False and any("Não consegui rodar" in e for e in j.erros)


def test_uma_janela_por_instalacao_e_interromper(app, monkeypatch):
    j = IJ.abrir("t", "Teste", _py("import time; print('comecei', flush=True); time.sleep(60)"))
    assert IJ.abrir("t", "Teste", _py("print(1)")) is j           # rodando: a mesma janela volta para a frente
    fim = time.time() + 15
    while "comecei" not in j.texto.toPlainText() and time.time() < fim:
        app.processEvents()
        time.sleep(0.02)
    assert j.rodando()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    j.interromper()
    _rodar(j)
    assert j.resultado is False and "Interrompido" in j.l_estado.text()


def test_menus_usam_a_janela(app, monkeypatch, tmp_path):
    from ipe.ai import extras as EX
    from ipe.ai import totalseg as TS
    from ipe.ui import segmentacao as SEG
    chamadas = []
    monkeypatch.setattr(IJ, "abrir", lambda *a, **k: chamadas.append(a) or None)
    arq = tmp_path / ("instalar_segmentacao.bat" if sys.platform == "win32" else "instalar_segmentacao.sh")
    arq.write_text("echo oi")
    monkeypatch.setattr(SEG, "instalador", lambda: arq)
    assert SEG.abrir_instalador(None, perguntar=False)
    chave, titulo, cmd, env, conferir, _pai = chamadas[-1]
    assert chave == "segmentacao" and str(arq) in cmd and env.get("IPE_LANG")
    monkeypatch.setattr(TS, "instalado", lambda _s=None: False)
    assert conferir() == (False, "o ambiente da segmentação não foi criado")
    monkeypatch.setattr(EX, "comando_do_instalador", lambda m=(), s=None: ["python", "inst.py", *m])
    assert SEG.abrir_instalador_extras(None, ("flames",), None, perguntar=False)
    chave, titulo, cmd, env, conferir, _pai = chamadas[-1]
    assert chave == "extras" and cmd == ["python", "inst.py", "flames", "--sem-pausa"] and "IPE_PESOS" in env
    ok, falta = conferir()
    assert ok is False and "FLAMeS" in falta
