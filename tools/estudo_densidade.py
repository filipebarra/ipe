#!/usr/bin/env python3
"""Estudo da densidade mamária contra rótulo de radiologista.

Para responder, em escala, a pergunta que as 71 mamografias do IMEB deixaram em aberto: o PD% que
`imaging/density.py` calcula **separa** as faixas a/b/c/d? E a discordância entre CC e MLO (r=0,46
em 17 mamas, de um aparelho só) é do método ou daquele aparelho?

Feito para o dataset da RSNA (*Open-Source Dataset for the RSNA Screening Mammography Cancer
Detection Challenge*, Radiology: AI, 2026 — mira.rsna.org/dataset/3), que traz **rótulo de
densidade dado por radiologista em imagem FOR PRESENTATION**, de várias marcas. Serve para
qualquer planilha com as mesmas colunas.

Não faz parte do programa: é ferramenta de pesquisa, roda na linha de comando, não abre janela e
não escreve nada no acervo.

    python tools/estudo_densidade.py planilhas --url "<url assinada>" --saida sub/
    python tools/estudo_densidade.py escolher  --csv sub/train.csv --por-grupo 40 --saida sub/
    python tools/estudo_densidade.py baixar    --url "<url assinada>" --saida sub/
    python tools/estudo_densidade.py medir     --csv sub/subconjunto.csv --imagens /dados/rsna --saida sub/
    python tools/estudo_densidade.py analisar  --saida sub/

`medir` pode ser interrompido e continuado: ele pula o que já está na planilha de resultados; e
`baixar` pula o que já está no disco.

O dataset da RSNA vem como **um zip só**, de centenas de GB, e o CSV está dentro dele. `planilhas`
e `baixar` leem esse zip **por faixas de bytes** (`tools/zip_remoto.py`), sem trazer o arquivo
inteiro: o índice do zip fica no fim, então dá para pegar só o CSV e depois só as imagens
sorteadas. A URL assinada é credencial — vale por alguns dias e serve para quem a tiver. Não a
deixe em script, em histórico de terminal compartilhado nem em repositório.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

COLUNAS = ["image_id", "patient_id", "site_id", "machine_id", "laterality", "view", "age",
           "implant", "density", "pd", "mama_cm2", "densa_cm2", "espessura_mm", "metodo",
           "peitoral", "avisos"]

#: as faixas como vêm no CSV da RSNA (maiúsculas) e como o programa as escreve
FAIXAS = ("A", "B", "C", "D")


# ------------------------------------------------------------------ zip remoto
def _zip(url: str):
    from zip_remoto import abrir
    print("lendo o índice do zip (não baixa o arquivo inteiro)...", flush=True)
    zf, remoto = abrir(url)
    gb = remoto.tamanho / (1 << 30)
    print(f"zip com {gb:,.1f} GB e {len(zf.namelist()):,} membros "
          f"({remoto.pedidos} pedidos até aqui)".replace(",", "."))
    return zf, remoto


def planilhas(args) -> int:
    """Traz só os `.csv` de dentro do zip — é o que o `escolher` precisa para sortear."""
    from zip_remoto import extrair
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    zf, _ = _zip(args.url)
    csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not csvs:
        print("nenhum .csv dentro do zip")
        return 1
    feitos, _faltando = extrair(zf, csvs, saida)
    for n in csvs:
        destino = saida / n
        print(f"  {n}  ({destino.stat().st_size / 1024:,.0f} kB)".replace(",", "."))
    # deixa os CSV também soltos na raiz da saída, que é onde o `escolher` vai procurar
    for n in csvs:
        raso = saida / Path(n).name
        if not raso.exists():
            raso.write_bytes((saida / n).read_bytes())
    print(f"{feitos} planilha(s) em {saida}")
    return 0


def baixar(args) -> int:
    """Traz só as imagens sorteadas pelo `escolher`."""
    from zip_remoto import casar, extrair
    saida = Path(args.saida)
    lista = Path(args.lista or (saida / "arquivos.txt"))
    if not lista.exists():
        print(f"não achei {lista}; rode `escolher` antes")
        return 1
    pedidos = [l.strip() for l in lista.read_text(encoding="utf-8").split("\n") if l.strip()]
    zf, remoto = _zip(args.url)
    nomes, faltando = casar(zf, pedidos)
    if faltando:
        print(f"{len(faltando)} da lista não existem no zip (ex.: {faltando[:2]})")
    if not nomes:
        return 1
    bytes_ = sum(zf.getinfo(n).file_size for n in nomes)
    print(f"{len(nomes)} imagens, {bytes_ / (1 << 30):,.1f} GB a baixar".replace(",", "."))
    destino = saida / "imagens"

    def andamento(i, n, _nome):
        if i % 25 == 0 or i == n:
            print(f"  {i}/{n}", flush=True)
    feitos, _ = extrair(zf, nomes, destino, andamento)
    print(f"{feitos} imagens em {destino}  ({remoto.pedidos} pedidos HTTP)")
    return 0


# ------------------------------------------------------------------ escolher
def escolher(args) -> int:
    """Sorteia um subconjunto equilibrado e escreve a lista de arquivos a baixar.

    O conjunto inteiro passa de 300 GB. Para responder as duas perguntas bastam alguns milhares de
    imagens — desde que **equilibradas por faixa e por aparelho**, senão o resultado mede a
    distribuição do dataset e não o método. Sorteia por paciente, para as quatro incidências da
    mesma mulher ficarem juntas: sem isso não dá para medir CC × MLO nem D × E.
    """
    linhas = list(csv.DictReader(open(args.csv, newline="", encoding="utf-8-sig")))
    com_rotulo = [r for r in linhas if (r.get("density") or "").strip().upper() in FAIXAS]
    print(f"{len(linhas)} linhas, {len(com_rotulo)} com rótulo de densidade")
    if not com_rotulo:
        print("Nenhuma linha com densidade: confira o CSV.")
        return 1

    por_paciente: dict[str, list] = defaultdict(list)
    for r in com_rotulo:
        por_paciente[r["patient_id"]].append(r)
    grupos: dict[tuple, list] = defaultdict(list)
    for pid, imgs in por_paciente.items():
        faixa = (imgs[0].get("density") or "").strip().upper()
        maq = (imgs[0].get("machine_id") or "?").strip()
        grupos[(faixa, maq)].append(pid)

    rng = np.random.default_rng(args.semente)
    escolhidos: list[str] = []
    for chave in sorted(grupos):
        pids = sorted(grupos[chave])
        rng.shuffle(pids)
        escolhidos.extend(pids[: args.por_grupo])
    print(f"{len(grupos)} grupos (faixa × aparelho); {len(escolhidos)} pacientes sorteados")

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    sub = [r for pid in escolhidos for r in por_paciente[pid]]
    with open(saida / "subconjunto.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sub[0].keys()))
        w.writeheader()
        w.writerows(sub)
    with open(saida / "arquivos.txt", "w", encoding="utf-8") as f:
        for r in sub:
            f.write(f"{r['patient_id']}/{r['image_id']}.dcm\n")
    tam = len(sub) * 0.05                      # ~50 MB por imagem no dataset da RSNA
    print(f"{len(sub)} imagens -> {saida/'subconjunto.csv'} e {saida/'arquivos.txt'}")
    print(f"aproximadamente {tam:.0f} GB para baixar (estimativa grosseira)")
    conta = defaultdict(int)
    for r in sub:
        conta[(r.get("density") or "").upper()] += 1
    print("por faixa:", dict(sorted(conta.items())))
    return 0


# ------------------------------------------------------------------ medir
def _uma(tarefa):
    """Mede uma imagem. Roda em processo separado, então devolve só tipos simples."""
    caminho, meta = tarefa
    import pydicom

    from ipe.imaging import density as D
    try:
        ds = pydicom.dcmread(caminho)
        r = D.medir(ds)
    except Exception as e:  # noqa: BLE001 - uma imagem ruim não pode parar o estudo
        return {**meta, "pd": "", "avisos": f"erro: {e}"}
    return {**meta,
            "pd": f"{r.pd:.2f}", "mama_cm2": f"{r.mama_cm2:.1f}", "densa_cm2": f"{r.densa_cm2:.1f}",
            "espessura_mm": f"{r.espessura_mm:.0f}", "metodo": r.metodo,
            "peitoral": "0" if any("peitoral" in a for a in r.avisos) else "1",
            "avisos": " | ".join(r.avisos)}


def medir(args) -> int:
    from concurrent.futures import ProcessPoolExecutor

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    destino = saida / "resultados.csv"
    prontos = set()
    if destino.exists():
        prontos = {r["image_id"] for r in csv.DictReader(open(destino, newline="", encoding="utf-8"))}
        print(f"{len(prontos)} já medidas; continuando de onde parou")

    raiz = Path(args.imagens)
    print("indexando os arquivos...", flush=True)
    indice = {p.stem: p for p in raiz.rglob("*.dcm")}
    print(f"{len(indice)} arquivos .dcm em {raiz}")

    tarefas, sem_arquivo = [], 0
    for r in csv.DictReader(open(args.csv, newline="", encoding="utf-8-sig")):
        iid = str(r.get("image_id", ""))
        if iid in prontos:
            continue
        caminho = indice.get(iid)
        if caminho is None:
            sem_arquivo += 1
            continue
        meta = {c: "" for c in COLUNAS}
        for c in ("image_id", "patient_id", "site_id", "machine_id", "laterality", "view",
                  "age", "implant", "density"):
            meta[c] = str(r.get(c, "") or "")
        tarefas.append((str(caminho), meta))
    if sem_arquivo:
        print(f"{sem_arquivo} linhas sem o arquivo correspondente (não baixadas)")
    if not tarefas:
        print("nada a medir")
        return 0

    novo = not destino.exists()
    with open(destino, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS, extrasaction="ignore")
        if novo:
            w.writeheader()
        feitos = 0
        with ProcessPoolExecutor(max_workers=args.processos or None) as pool:
            for linha in pool.map(_uma, tarefas, chunksize=4):
                w.writerow(linha)
                feitos += 1
                if feitos % 50 == 0:
                    f.flush()
                    print(f"  {feitos}/{len(tarefas)}", flush=True)
    print(f"{feitos} imagens medidas -> {destino}")
    return 0


# ------------------------------------------------------------------ analisar
def _r(pares):
    if len(pares) < 3:
        return float("nan"), float("nan"), len(pares)
    a = np.array([p[0] for p in pares], float)
    b = np.array([p[1] for p in pares], float)
    return float(np.corrcoef(a, b)[0, 1]), float(np.mean(np.abs(a - b))), len(pares)


def _postos(x):
    """Postos com **média nos empates** — sem isso o AUC de duas distribuições iguais não dá 0,5."""
    ordem = np.argsort(x, kind="mergesort")
    postos = np.empty(len(x), float)
    postos[ordem] = np.arange(1, len(x) + 1, dtype=float)
    xs = x[ordem]
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        if j > i:
            postos[ordem[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return postos


def _auc(pos, neg):
    """Área sob a curva ROC pela estatística de Mann-Whitney (sem sklearn)."""
    if not len(pos) or not len(neg):
        return float("nan")
    postos = _postos(np.concatenate([pos, neg]))
    soma = postos[: len(pos)].sum()
    return float((soma - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def analisar(args) -> int:
    destino = Path(args.saida) / "resultados.csv"
    if not destino.exists():
        print(f"não achei {destino}; rode `medir` antes")
        return 1
    linhas = [r for r in csv.DictReader(open(destino, newline="", encoding="utf-8"))
              if (r.get("pd") or "").strip()]
    if not linhas:
        print("nenhuma medida utilizável")
        return 1
    for r in linhas:
        r["pd"] = float(r["pd"])
        r["density"] = (r.get("density") or "").strip().upper()
    print(f"{len(linhas)} imagens medidas\n")

    print("PD% por faixa do radiologista")
    pd_por_faixa = {}
    for f in FAIXAS:
        v = np.array([r["pd"] for r in linhas if r["density"] == f])
        pd_por_faixa[f] = v
        if v.size:
            print(f"  {f}: n={v.size:5d}  mediana {np.median(v):5.1f}  "
                  f"quartis {np.percentile(v,25):5.1f}/{np.percentile(v,75):5.1f}")
    densas = np.concatenate([pd_por_faixa.get(f, np.array([])) for f in ("C", "D")])
    claras = np.concatenate([pd_por_faixa.get(f, np.array([])) for f in ("A", "B")])
    if densas.size and claras.size:
        print(f"\n  separar densa (C+D) de não densa (A+B): AUC = {_auc(densas, claras):.3f}")
        print("  (0,5 = não separa nada; acima de 0,85 é o que um método publicado costuma dar)")

    def agrupa(chave):
        d = defaultdict(list)
        for r in linhas:
            d[chave(r)].append(r)
        return d

    print("\nConcordância entre incidências da mesma mama")
    por_mama = agrupa(lambda r: (r["patient_id"], r["laterality"]))
    pares = []
    for v in por_mama.values():
        cc = [r["pd"] for r in v if r["view"] == "CC"]
        ml = [r["pd"] for r in v if r["view"] == "MLO"]
        if cc and ml:
            pares.append((float(np.mean(cc)), float(np.mean(ml))))
    r_, d_, n_ = _r(pares)
    print(f"  CC x MLO: r = {r_:.3f}  dif. média {d_:.1f} pp  ({n_} mamas)")

    por_paciente = agrupa(lambda r: r["patient_id"])
    pares = []
    for v in por_paciente.values():
        d = [r["pd"] for r in v if r["laterality"] == "R"]
        e = [r["pd"] for r in v if r["laterality"] == "L"]
        if d and e:
            pares.append((float(np.mean(d)), float(np.mean(e))))
    r_, d_, n_ = _r(pares)
    print(f"  D x E:    r = {r_:.3f}  dif. média {d_:.1f} pp  ({n_} exames)")

    print("\nPor aparelho (é aqui que se vê se o problema é do método ou de uma marca)")
    for maq, v in sorted(agrupa(lambda r: r["machine_id"]).items(),
                         key=lambda kv: -len(kv[1]))[:12]:
        mamas = defaultdict(list)
        for r in v:
            mamas[(r["patient_id"], r["laterality"])].append(r)
        pares = []
        for vv in mamas.values():
            cc = [r["pd"] for r in vv if r["view"] == "CC"]
            ml = [r["pd"] for r in vv if r["view"] == "MLO"]
            if cc and ml:
                pares.append((float(np.mean(cc)), float(np.mean(ml))))
        r_, d_, n_ = _r(pares)
        pct = 100 * sum(1 for r in v if r.get("peitoral") == "1" and r["view"] == "MLO") / \
            max(1, sum(1 for r in v if r["view"] == "MLO"))
        print(f"  {maq:>6}: n={len(v):5d}  CCxMLO r={r_:6.3f} ({n_:4d} mamas)  "
              f"peitoral em {pct:4.0f}% das MLO")

    avisos = defaultdict(int)
    for r in linhas:
        for a in (r.get("avisos") or "").split(" | "):
            if a.strip():
                avisos[a.strip()] += 1
    if avisos:
        print("\nAvisos")
        for a, n in sorted(avisos.items(), key=lambda kv: -kv[1])[:8]:
            print(f"  {n:5d}  {a}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("planilhas", help="trazer só os CSV de dentro do zip remoto")
    pl.add_argument("--url", required=True, help="URL assinada do zip (é credencial: não guarde)")
    pl.add_argument("--saida", default="estudo")
    pl.set_defaults(fn=planilhas)

    b = sub.add_parser("baixar", help="trazer só as imagens sorteadas, de dentro do zip remoto")
    b.add_argument("--url", required=True, help="URL assinada do zip (é credencial: não guarde)")
    b.add_argument("--saida", default="estudo")
    b.add_argument("--lista", default="", help="padrão: <saida>/arquivos.txt")
    b.set_defaults(fn=baixar)

    e = sub.add_parser("escolher", help="sortear um subconjunto equilibrado e listar o que baixar")
    e.add_argument("--csv", required=True, help="planilha do dataset (com a coluna density)")
    e.add_argument("--saida", default="estudo")
    e.add_argument("--por-grupo", type=int, default=40, help="pacientes por faixa e aparelho")
    e.add_argument("--semente", type=int, default=7)
    e.set_defaults(fn=escolher)

    m = sub.add_parser("medir", help="rodar a medida nas imagens baixadas (pode continuar depois)")
    m.add_argument("--csv", required=True)
    m.add_argument("--imagens", required=True, help="pasta com os .dcm (procura nas subpastas)")
    m.add_argument("--saida", default="estudo")
    m.add_argument("--processos", type=int, default=0, help="0 = um por núcleo")
    m.set_defaults(fn=medir)

    a = sub.add_parser("analisar", help="ler os resultados e responder as perguntas")
    a.add_argument("--saida", default="estudo")
    a.set_defaults(fn=analisar)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
