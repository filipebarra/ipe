"""0.100.11: o filme montado no visualizador web, impresso pelo servidor com as configurações de impressão do Ipê.

O navegador manda a **receita** do filme — o mesmo JSON do compositor (`printing/film.Film`): folhas, grade, papel,
e em cada célula a imagem (série, SOP, quadro), a janela, o zoom, o deslocamento, o giro, o espelho e o inverso. O
servidor desenha as folhas com o código do compositor, na resolução de cada saída, e manda para:

- **Baixar PDF** (o navegador recebe o PDF) e **Imprimir neste computador** (o navegador abre o PDF e chama a
  janela de imprimir dele — as impressoras de quem está no navegador);
- as **impressoras do computador do servidor**, pelo nome;
- as **impressoras DICOM** cadastradas no servidor;
- os **destinos de impressão** cadastrados (PDF ou imagens numa pasta, impressora do sistema, impressora DICOM).

A prévia de cada folha (PNG) vem do mesmo desenho, então o que se vê é o que sai. Cada impressão conta no painel de
filmes (o filme fica salvo, com quem imprimiu e para onde) e no registro de acesso. Só com a permissão de imprimir.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

PERMISSAO = "print"
MAX_CELULAS = 400


def _exigir(s) -> None:
    if PERMISSAO not in (getattr(s, "perms", None) or set()):
        raise PermissionError("seu perfil não permite imprimir (print)")


def _filme(c, s, d: dict):
    from ipe.printing.film import Film
    film = Film.from_dict(d or {})
    n = film.image_count()
    if not n:
        raise ValueError("o filme está vazio")
    if n > MAX_CELULAS:
        raise ValueError(f"filme grande demais ({n} imagens; até {MAX_CELULAS})")
    for uid in film.study_uids():
        if not c.pode_ver(s, uid):
            raise PermissionError("imagem de exame fora do seu acesso")
    return film


def _saida(c, film):
    from ipe.printing.filme_saida import Saida
    return Saida(film, c.repo, c.settings)


def opcoes(c, s) -> dict:
    from ipe.printing import dispatch as D
    from ipe.printing.film import LAYOUTS, OVERLAYS, PAPERS
    _exigir(s)
    st = c.settings
    destinos = [{"id": "baixar", "nome": "Baixar PDF", "grupo": "Neste computador"},
                {"id": "navegador", "nome": "Imprimir neste computador (impressoras do navegador)",
                 "grupo": "Neste computador"}]

    def nomes():
        from PySide6.QtPrintSupport import QPrinterInfo
        return list(QPrinterInfo.availablePrinterNames())
    try:
        sistema = c.ponte.chamar(nomes)
    except Exception:  # noqa: BLE001 - sem suporte a impressão neste servidor
        log.debug("impressoras do sistema", exc_info=True)
        sistema = []
    destinos += [{"id": f"sis:{n}", "nome": n, "grupo": "Impressoras do servidor"} for n in sistema]
    for d in (st.get("printing.dicom_printers", []) if st is not None else []) or []:
        nome = d.get("name") or "Impressora DICOM"
        destinos.append({"id": f"dicom:{nome}", "nome": f"{nome} ({d.get('ae_title', '')}@{d.get('host', '')})",
                         "grupo": "Impressoras DICOM"})
    for d in (D.all_destinations(st) if st is not None else []):
        destinos.append({"id": f"dest:{d.name}", "nome": d.label(), "grupo": "Destinos de impressão do Ipê"})
    return {"papeis": list(PAPERS), "tamanhos": {k: [v[0], v[1]] for k, v in PAPERS.items()}, "layouts": LAYOUTS,
            "textos": OVERLAYS, "destinos": destinos}


def previa(c, s, corpo: dict) -> bytes:
    _exigir(s)
    film = _filme(c, s, corpo.get("film"))
    i = int(corpo.get("folha") or 0)
    dpi = max(20, min(120, float(corpo.get("dpi") or 50)))
    if not 0 <= i < len(film.sheets):
        raise ValueError("folha fora do filme")
    return c.ponte.chamar(lambda: _saida(c, film).png(i, dpi), espera=120)


def pdf(c, s, corpo: dict) -> bytes:
    _exigir(s)
    film = _filme(c, s, corpo.get("film"))
    folhas = [int(x) for x in corpo.get("folhas") or []]
    dados = c.ponte.chamar(lambda: _saida(c, film).pdf(folhas), espera=300)
    _contar(c, s, film, "Navegador: PDF" if corpo.get("para") != "navegador" else "Navegador: impressora local")
    return dados


def _contar(c, s, film, destino: str) -> None:
    """O filme no painel de filmes (salvo, com a impressão) e no registro de acesso."""
    try:
        info = c.repo.study_info(film.study_uids()[0]) or {}
        fid = c.repo.save_film(film.name, film.to_dict(), film.study_uids(), info.get("patient_name", ""),
                               user=s.username)
        c.repo.mark_film_printed(fid, s.username, destino)
        c.repo.add_send("film", fid, destino, s.username, "navegador")
    except Exception:  # noqa: BLE001
        log.exception("contar a impressão do filme")
    for uid in film.study_uids():
        c.repo.audit("imprimir", f"{destino}: {film.name}", user=s.username, study_uid=uid)


def _local_ae(c) -> str:
    net = getattr(c, "net", None)
    if net is not None and getattr(net, "local_ae", ""):
        return net.local_ae
    st = c.settings
    return str((st.get("dicom", {}) or {}).get("ae_title", "") if st is not None else "") or "DICOMVIEWER"


def _dicom(c, film, cfg, folhas) -> str:
    from ipe.printing.dicom_print import dicom_print
    pages = c.ponte.chamar(lambda: _saida(c, film).paginas_dicom(cfg, folhas), espera=300)
    res = dicom_print(cfg, pages, _local_ae(c))
    extra = f" (avisos: {'; '.join(res.warnings)})" if res.warnings else ""
    return f"{res.pages} folha(s) enviada(s) para {cfg.name}{extra}"


def imprimir(c, s, corpo: dict) -> dict:
    from ipe.printing import dispatch as D
    from ipe.printing.dicom_print import PrinterConfig
    _exigir(s)
    film = _filme(c, s, corpo.get("film"))
    folhas = [int(x) for x in corpo.get("folhas") or []]
    alvo = str(corpo.get("destino") or "")
    st = c.settings
    if alvo.startswith("sis:"):
        nome = alvo[4:]
        n = c.ponte.chamar(lambda: _saida(c, film).impressora(nome, folhas), espera=300)
        msg, destino = f"{n} folha(s) na impressora {nome}", f"Impressora do servidor: {nome}"
    elif alvo.startswith("dicom:"):
        nome = alvo[6:]
        cfgs = [PrinterConfig.from_dict(d) for d in (st.get("printing.dicom_printers", []) or [])]
        cfg = next((x for x in cfgs if x.name == nome), None)
        if cfg is None:
            raise KeyError(f"impressora DICOM não encontrada: {nome}")
        msg, destino = _dicom(c, film, cfg, folhas), f"Impressora DICOM: {nome}"
    elif alvo.startswith("dest:"):
        d = D.find_destination(st, alvo[5:])
        if d is None:
            raise KeyError(f"destino de impressão não encontrado: {alvo[5:]}")
        if d.kind in ("pdf", "images"):
            if not d.folder:
                raise ValueError(f"o destino {d.name} não tem pasta")
            arqs = c.ponte.chamar(lambda: _saida(c, film).numa_pasta(d.folder, d.kind, d.fmt, d.dpi, folhas),
                                  espera=300)
            msg = f"{len(arqs)} arquivo(s) em {d.folder}"
        elif d.kind == "system":
            def no_sistema():
                from PySide6.QtPrintSupport import QPrinterInfo
                nome = d.printer or QPrinterInfo.defaultPrinterName()
                return nome, _saida(c, film).impressora(nome, folhas)
            nome, n = c.ponte.chamar(no_sistema, espera=300)
            msg = f"{n} folha(s) na impressora {nome}"
        elif d.kind == "dicom":
            cfgs = [PrinterConfig.from_dict(x) for x in (st.get("printing.dicom_printers", []) or [])]
            cfg = next((x for x in cfgs if x.name == d.dicom_printer), None)
            if cfg is None:
                raise KeyError(f"impressora DICOM não encontrada: {d.dicom_printer}")
            msg = _dicom(c, film, cfg, folhas)
        else:
            raise ValueError(f"tipo de destino desconhecido: {d.kind}")
        destino = f"Destino: {d.name}"
    else:
        raise ValueError("destino de impressão desconhecido")
    _contar(c, s, film, destino)
    return {"ok": True, "mensagem": msg}
