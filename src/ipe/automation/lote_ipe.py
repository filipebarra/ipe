"""O lote a partir de planilha ligado no Ipê (0.100.97): quem procura no banco e nos nós, baixa, roda as IAs, envia,
imprime, exporta e apaga.

`servicos(...)` devolve o `lote.Servicos` de verdade. Roda numa linha de fundo; o que precisa da linha da tela (a fila
de IA, o desenho das folhas para imprimir) vai por `chamar(fn)` (a ponte do Ipê).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from ipe.automation import lote as L
from ipe.automation import lote_ias as LI

log = logging.getLogger(__name__)

ESPERA_DOWNLOAD_S = 30 * 60
ESPERA_ENVIO_S = 30 * 60


def pronto(repo) -> tuple[bool, str]:
    """Este Ipê pode rodar o lote? (as imagens precisam estar aqui: no cliente de um servidor, o lote é do servidor)"""
    from ipe.automation import mama_auto as MA
    if not MA.local(repo):
        return False, ("Este Ipê é cliente de um servidor: as imagens não ficam aqui. O lote roda no servidor.")
    return True, ""


def _linha(r) -> dict:
    return {"study_uid": r.study_uid, "patient_id": r.patient_id, "birth_date": r.birth_date,
            "accession": r.accession, "study_date": r.study_date, "study_time": r.study_time,
            "description": r.description, "modalities": r.modalities, "num_images": r.num_images}


def _esperar(job, parar, limite_s: float, net) -> tuple[bool, str]:
    fim = time.time() + limite_s
    while job.active:
        if parar is not None and parar.is_set():
            net.cancel(job)
            return False, "parado"
        if time.time() > fim:
            net.cancel(job)
            return False, f"passou de {int(limite_s // 60)} minutos"
        time.sleep(0.25)
    return job.status == "done", (job.message or job.status)


def servicos(repo, db, net, settings, storage_root, engine=None, chamar=None, identidade=None,
             parar=None) -> L.Servicos:
    chamar = chamar or (lambda fn: fn())
    executor = LI.Executor(repo, db, storage_root, settings, engine, chamar)
    storage_root = Path(storage_root)

    def nos() -> dict:
        try:
            lista = list(repo.nodes(todos=True))
        except Exception:  # noqa: BLE001
            return {}
        central = getattr(net, "central_repo", None)       # 0.100.128: com o HD ativo, os nós do servidor também valem
        if central is not None and central is not repo:
            try:
                lista += [n for n in central.nos_do_servidor() if n["id"] not in {x["id"] for x in lista}]
            except Exception:  # noqa: BLE001
                pass
        return {str(n["id"]): n for n in lista}

    def nome_no(no_id) -> str:
        n = nos().get(str(no_id))
        return n.get("name", str(no_id)) if n else str(no_id)

    def local(crit: dict) -> list[dict]:
        if crit.get("uid"):
            info = repo.study_info(crit["uid"])
            if not info:
                return []
            linhas = repo.search_studies(text=info.get("patient_id") or info.get("accession") or "", limit=500,
                                         banco="todos")
            return [_linha(r) for r in linhas if r.study_uid == crit["uid"]]
        texto = crit.get("acesso") or crit.get("pid") or ""
        mods = crit.get("modalidades") or []
        linhas = repo.search_studies(text=texto, modality=mods[0] if len(mods) == 1 else "",
                                     date_from=crit.get("data_de", ""), date_to=crit.get("data_ate", ""),
                                     limit=500, banco="todos")
        return [_linha(r) for r in linhas]

    def no(no_id, crit: dict) -> list[dict]:
        n = nos().get(str(no_id))
        if n is None:
            raise KeyError(f"nó {no_id} não existe mais")
        cli, alvo = net.cliente(n), net.target(n, identidade)
        mods = crit.get("modalidades") or []
        mod = mods[0] if len(mods) == 1 else ""
        if crit.get("uid"):
            return cli.find_studies(alvo, study_uid=crit["uid"], limit=10)
        if crit.get("acesso"):
            return cli.find_studies(alvo, accession=crit["acesso"], modality=mod, limit=50)
        pid = crit["pid"]
        datas = {"date_from": crit.get("data_de", ""), "date_to": crit.get("data_ate", "")}
        achados = cli.find_studies(alvo, patient_id=pid, modality=mod, limit=100, **datas)
        if not achados and mod:
            # 0.100.98: nem todo PACS filtra por ModalitiesInStudy — de novo sem a modalidade (o filtro fica aqui)
            achados = cli.find_studies(alvo, patient_id=pid, limit=100, **datas)
        if not L.filtrar(achados, crit) and pid.lstrip("0"):
            # o PACS pode guardar o ID com (ou sem) zeros à esquerda: busca pelo fim e o filtro fica com o mesmo número
            try:
                achados = achados + cli.find_studies(alvo, patient_id="*" + pid.lstrip("0"), limit=100, **datas)
            except Exception as e:  # noqa: BLE001 - PACS que não aceita curinga no começo
                log.info("lote: busca por *%s: %s", pid.lstrip("0"), e)
        return achados

    def tem(uid: str) -> bool:
        return repo.study_info(uid) is not None and bool([f for f in repo.files_for_study(uid) if f])

    def baixar(no_id, exame: dict, parar_=None) -> tuple[bool, str]:
        n = nos().get(str(no_id))
        if n is None:
            return False, f"nó {no_id} não existe mais"
        uid = exame["study_uid"]
        job = net.retrieve(n, identidade, uid, f"Lote: {exame.get('accession') or uid[-12:]}",
                           sem_regras=bool(serv.sem_regras_no_baixado))
        ok, msg = _esperar(job, parar_, ESPERA_DOWNLOAD_S, net)
        if ok and not [f for f in repo.files_for_study(uid) if f]:
            return False, "o nó não mandou nenhuma imagem"
        return ok, msg

    def ias(uid: str, tipos: list[str], refazer: bool, parar_=None) -> dict:
        return executor.rodar(uid, tipos, refazer, parar_, precisa_series=True)

    def protocolo(uid: str) -> dict:
        from ipe.imaging import protocolo_rm as P
        r = P.conferir_exame(repo, settings, uid) or {}
        return {"Situação": P.resumo(r) if r.get("estado") != "sem_rm" else "sem RM",
                "Referência": r.get("referencia") or None, "Divergências": r.get("n_erros"),
                "Avisos": r.get("n_avisos")}

    def enviar(uid: str, no_id, series: list[str] | None) -> str:
        n = nos().get(str(no_id))
        if n is None:
            raise KeyError(f"nó {no_id} não existe mais")
        job = net.send(n, None, [uid], f"Lote → {n.get('name', '')}", series_uids=series or None)
        ok, msg = _esperar(job, parar, ESPERA_ENVIO_S, net)
        if not ok:
            raise RuntimeError(msg)
        return f"{n.get('name', '')}: {'resultados' if series else 'exame'}"

    def _com_nome(series: list[str]) -> list[str]:
        """As séries (entre `series`) que trazem o nome do paciente escrito na imagem (BurnedInAnnotation = YES)."""
        import pydicom
        out = []
        for s in series:
            arqs = [i["path"] for i in repo.instances_for_series(s) if i.get("path")]
            try:
                ds = pydicom.dcmread(arqs[0], stop_before_pixels=True, specific_tags=["BurnedInAnnotation"])
                if str(ds.get("BurnedInAnnotation", "") or "").upper() == "YES":
                    out.append(s)
            except Exception:  # noqa: BLE001 - sem como saber: trata como se tivesse
                out.append(s)
        return out

    def _imagens(uid: str, series: list[str]) -> list[tuple]:
        out = []
        for s in series:
            for inst in repo.instances_for_series(s):
                out.append((uid, s, inst["sop_uid"], int(inst.get("frames") or 1)))
        return out

    def imprimir(uid: str, series: list[str], destino: str, titulo: str) -> str:
        from ipe.printing import dispatch as D
        from ipe.printing.auto_film import AutoFilm, films_from_images
        from ipe.printing.dicom_print import PrinterConfig, dicom_print
        from ipe.printing.filme_saida import Saida
        filmes = films_from_images(repo, _imagens(uid, series),
                                   AutoFilm(rows=1, cols=1, paper="A4", max_images=0))
        if not filmes:
            return "nada para imprimir"
        film = filmes[0][1]
        film.name = titulo
        ae = str((settings.get("dicom", {}) or {}).get("ae_title", "") or "DICOMVIEWER")

        def dicom(cfg) -> str:
            pages = chamar(lambda: Saida(film, repo, settings).paginas_dicom(cfg, None))
            res = dicom_print(cfg, pages, ae)
            return f"{res.pages} folha(s) em {cfg.name}"
        if destino.startswith("dicom:"):
            nome = destino[6:]
            cfg = next((PrinterConfig.from_dict(x) for x in (settings.get("printing.dicom_printers", []) or [])
                        if x.get("name") == nome), None)
            if cfg is None:
                raise KeyError(f"impressora DICOM não encontrada: {nome}")
            msg = dicom(cfg)
        elif destino.startswith("dest:"):
            d = D.find_destination(settings, destino[5:])
            if d is None:
                raise KeyError(f"destino de impressão não encontrado: {destino[5:]}")
            if d.kind in ("pdf", "images"):
                arqs = chamar(lambda: Saida(film, repo, settings).numa_pasta(d.folder, d.kind, d.fmt, d.dpi, None))
                msg = f"{len(arqs)} arquivo(s) em {d.folder}"
            elif d.kind == "system":
                def no_sistema():
                    from PySide6.QtPrintSupport import QPrinterInfo
                    nome = d.printer or QPrinterInfo.defaultPrinterName()
                    return nome, Saida(film, repo, settings).impressora(nome, None)
                nome, k = chamar(no_sistema)
                msg = f"{k} folha(s) na impressora {nome}"
            elif d.kind == "dicom":
                cfg = next((PrinterConfig.from_dict(x) for x in (settings.get("printing.dicom_printers", []) or [])
                            if x.get("name") == d.dicom_printer), None)
                if cfg is None:
                    raise KeyError(f"impressora DICOM não encontrada: {d.dicom_printer}")
                msg = dicom(cfg)
            else:
                raise ValueError(f"tipo de destino desconhecido: {d.kind}")
        else:
            raise ValueError("destino de impressão desconhecido")
        try:
            info = repo.study_info(uid) or {}
            fid = repo.save_film(film.name, film.to_dict(), film.study_uids(), info.get("patient_name", ""),
                                 user="lote")
            repo.mark_film_printed(fid, "lote", destino)
        except Exception:  # noqa: BLE001
            log.debug("lote: contar o filme", exc_info=True)
        repo.audit("imprimir", f"lote: {destino}", user="lote", study_uid=uid)
        return msg

    def exportar(uid: str, series: list[str], pasta: str, nome: str, formato: str, dicom: bool,
                 anonimizar: bool) -> str:
        from ipe.exporter import core as EX
        base = Path(pasta) / nome
        partes = []
        fora = _com_nome(series) if anonimizar else []
        img = [s for s in series if s not in fora]
        if fora:
            partes.append(f"{len(fora)} série(s) com o nome do paciente na imagem ficaram de fora")
        if formato and img:
            dest = base / "conferencia"
            res = EX.export_images(repo, [EX.ExportItem(uid, img)], dest, fmt="png", anonymous_names=anonimizar)
            arqs = sorted(dest.rglob("*.png"))
            if formato == "pdf" and arqs:
                from PIL import Image
                ims = [Image.open(a).convert("RGB") for a in arqs]
                pdf = base / f"{nome}.pdf"
                pdf.parent.mkdir(parents=True, exist_ok=True)
                ims[0].save(pdf, save_all=True, append_images=ims[1:], resolution=150)
                for a in arqs:
                    a.unlink()
                for d in sorted(dest.rglob("*"), reverse=True):
                    if d.is_dir():
                        d.rmdir()
                if dest.exists():
                    dest.rmdir()
                partes.append(f"PDF com {len(ims)} imagem(ns)")
            else:
                partes.append(f"{res.images} PNG")
        if dicom and img:
            opts = None
            if anonimizar:
                from ipe.exporter.anonymize import AnonOptions
                opts = AnonOptions(enabled=True, name=nome, patient_id=nome)
            res = EX.export_dicom(repo, [EX.ExportItem(uid, img)], base / "dicom", opts, dicomdir=False, viewer=False)
            partes.append(f"{res.files} DICOM")
        repo.audit("exportar", f"lote: {base}", user="lote", study_uid=uid)
        return "; ".join(partes) or "nada para exportar"

    def apagar(uid: str) -> None:
        repo.delete_study(uid, storage_root)

    def chegada(uid: str) -> None:
        """0.100.101: as regras da chegada (as mesmas de um exame baixado: IA automática, roteamento, impressão)."""
        chamar(lambda: engine.study_arrived(uid, "retrieved"))

    serv = L.Servicos(local=local, no=no, tem=tem, baixar=baixar, ias=ias, protocolo=protocolo, enviar=enviar,
                      imprimir=imprimir, exportar=exportar, apagar=apagar, nome_no=nome_no,
                      chegada=chegada if engine is not None and hasattr(engine, "study_arrived") else None)
    return serv
