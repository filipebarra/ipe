"""O pipeline do estudo de densidade: sorteio, medida e análise.

Testado ponta a ponta contra um dataset falso com **rótulo conhecido** — a faixa é sorteada, a
fração densa do fantoma é desenhada de acordo, e a análise tem que reencontrar a separação.
"""

import csv
import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools"))

import estudo_densidade as E  # noqa: E402

from test_densidade import _mamo  # noqa: E402

FRACAO = {"A": 0.10, "B": 0.32, "C": 0.58, "D": 0.82}


def _dataset(tmp_path, pacientes=8, maquinas=("21", "49")):
    """Quatro incidências por paciente, com a fração densa combinando com a faixa sorteada."""
    imagens = tmp_path / "imagens"
    imagens.mkdir()
    linhas = []
    rng = np.random.default_rng(3)
    for i in range(pacientes):
        faixa = "ABCD"[i % 4]
        maq = maquinas[i % len(maquinas)]
        pid = f"P{i:03d}"
        (imagens / pid).mkdir()
        for lado in ("R", "L"):
            for vista in ("CC", "MLO"):
                iid = f"{pid}_{lado}{vista}"
                f = float(np.clip(FRACAO[faixa] + rng.normal(0, 0.02), 0.03, 0.95))
                ds, _ = _mamo(lado=lado, incidencia=vista, fracao=f)
                ds.save_as(str(imagens / pid / f"{iid}.dcm"), enforce_file_format=True)
                linhas.append({"image_id": iid, "patient_id": pid, "site_id": "1",
                               "machine_id": maq, "laterality": lado, "view": vista,
                               "age": "55", "implant": "0", "density": faixa})
    planilha = tmp_path / "train.csv"
    with open(planilha, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    return planilha, imagens


# ------------------------------------------------------------------ escolher
def test_sorteio_equilibra_faixa_e_aparelho(tmp_path, capsys):
    planilha, _ = _dataset(tmp_path, pacientes=16)
    saida = tmp_path / "est"
    assert E.main(["escolher", "--csv", str(planilha), "--saida", str(saida),
                   "--por-grupo", "1"]) == 0
    sub = list(csv.DictReader(open(saida / "subconjunto.csv", newline="", encoding="utf-8")))
    faixas = {r["density"] for r in sub}
    assert faixas == {"A", "B", "C", "D"}          # todas as faixas representadas
    por_paciente = {r["patient_id"] for r in sub}
    assert len(sub) == 4 * len(por_paciente)       # paciente inteiro, nunca imagem solta
    lista = (saida / "arquivos.txt").read_text().strip().split("\n")
    assert len(lista) == len(sub) and lista[0].endswith(".dcm")


def test_sorteio_ignora_linha_sem_rotulo(tmp_path):
    planilha, _ = _dataset(tmp_path, pacientes=4)
    linhas = list(csv.DictReader(open(planilha, newline="", encoding="utf-8")))
    for r in linhas:
        r["density"] = ""
    with open(planilha, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    assert E.main(["escolher", "--csv", str(planilha), "--saida", str(tmp_path / "e")]) == 1


# ------------------------------------------------------------------ medir
def test_medida_preenche_a_planilha(tmp_path):
    planilha, imagens = _dataset(tmp_path, pacientes=4)
    saida = tmp_path / "est"
    assert E.main(["medir", "--csv", str(planilha), "--imagens", str(imagens),
                   "--saida", str(saida), "--processos", "2"]) == 0
    res = list(csv.DictReader(open(saida / "resultados.csv", newline="", encoding="utf-8")))
    assert len(res) == 16
    assert all(r["pd"] for r in res)
    assert set(res[0].keys()) == set(E.COLUNAS)
    # o PD medido tem que acompanhar a faixa desenhada
    por_faixa = {f: np.mean([float(r["pd"]) for r in res if r["density"] == f]) for f in "ABCD"}
    assert por_faixa["A"] < por_faixa["B"] < por_faixa["C"] < por_faixa["D"]


def test_medida_continua_de_onde_parou(tmp_path, capsys):
    planilha, imagens = _dataset(tmp_path, pacientes=4)
    saida = tmp_path / "est"
    E.main(["medir", "--csv", str(planilha), "--imagens", str(imagens), "--saida", str(saida),
            "--processos", "2"])
    antes = (saida / "resultados.csv").read_text()
    E.main(["medir", "--csv", str(planilha), "--imagens", str(imagens), "--saida", str(saida),
            "--processos", "2"])
    assert (saida / "resultados.csv").read_text() == antes      # não mediu de novo
    assert "16 já medidas" in capsys.readouterr().out


def test_arquivo_que_nao_foi_baixado_nao_derruba(tmp_path, capsys):
    planilha, imagens = _dataset(tmp_path, pacientes=4)
    for p in list(imagens.rglob("*.dcm"))[:6]:
        p.unlink()
    saida = tmp_path / "est"
    assert E.main(["medir", "--csv", str(planilha), "--imagens", str(imagens),
                   "--saida", str(saida), "--processos", "2"]) == 0
    assert "6 linhas sem o arquivo" in capsys.readouterr().out


# ------------------------------------------------------------------ analisar
def test_analise_responde_as_duas_perguntas(tmp_path, capsys):
    planilha, imagens = _dataset(tmp_path, pacientes=8)
    saida = tmp_path / "est"
    E.main(["medir", "--csv", str(planilha), "--imagens", str(imagens), "--saida", str(saida),
            "--processos", "4"])
    assert E.main(["analisar", "--saida", str(saida)]) == 0
    saiu = capsys.readouterr().out
    assert "PD% por faixa" in saiu and "CC x MLO" in saiu and "D x E" in saiu
    assert "Por aparelho" in saiu
    auc = float(saiu.split("AUC = ")[1].split("\n")[0])
    assert auc > 0.95          # no fantoma a separação é limpa; serve de controle da bancada


def test_analise_sem_resultados_avisa(tmp_path, capsys):
    assert E.main(["analisar", "--saida", str(tmp_path / "vazio")]) == 1
    assert "rode `medir` antes" in capsys.readouterr().out


# ------------------------------------------------------------------ contas
def test_auc_conhecida():
    assert E._auc(np.array([2.0, 3.0]), np.array([0.0, 1.0])) == 1.0
    assert E._auc(np.array([0.0, 1.0]), np.array([2.0, 3.0])) == 0.0
    assert E._auc(np.array([1.0, 2.0]), np.array([1.0, 2.0])) == pytest.approx(0.5)
    assert np.isnan(E._auc(np.array([]), np.array([1.0])))


def test_correlacao_com_poucos_pares_nao_inventa():
    r, d, n = E._r([(1.0, 2.0)])
    assert np.isnan(r) and n == 1


def test_postos_fazem_media_nos_empates():
    assert list(E._postos(np.array([10.0, 10.0, 20.0]))) == [1.5, 1.5, 3.0]
