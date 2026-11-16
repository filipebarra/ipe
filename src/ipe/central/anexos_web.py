"""0.100.55: anexar PDF e imagens ao exame pelo Ipê Web — o mesmo que arrastar no Ipê de mesa (`importer/anexos.py`).

O navegador manda os arquivos (base64 num JSON); o servidor converte em DICOM dentro do exame (PDF → Encapsulated PDF,
série "Documentos anexados"; imagem → Secondary Capture, série "Imagens anexadas"), grava no banco do servidor e manda
pelas regras de roteamento que valem para o exame, como o Ipê de mesa. Pede a permissão de importar.

Os documentos (PDF) do exame também são listados e abertos daqui (o visualizador do navegador não mostra a série DOC).
"""
from __future__ import annotations

import base64
import logging
import re
import shutil
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

LIMITE_BYTES = 80 << 20       # por pedido (o corpo do JSON fica ~1/3 maior)
LIMITE_ARQUIVOS = 40


def _exame(c, s, study: str) -> None:
    if not s.can("view"):
        raise PermissionError("sem permissão")
    if not study or not c.pode_ver(s, study):
        raise PermissionError("exame não visível")


def _fonte(c, study: str):
    """Um arquivo do exame (paciente e exame copiados dele) ou os dados do banco."""
    from pydicom.dataset import Dataset
    for f in c.repo.files_for_study(study):
        if f and Path(f).exists():
            return str(f)
    info = c.repo.study_info(study) or {}
    if not info:
        raise KeyError("exame não encontrado")
    ds = Dataset()
    for kw, k in (("PatientName", "patient_name"), ("PatientID", "patient_id"), ("PatientBirthDate", "birth_date"),
                  ("PatientSex", "sex"), ("PatientAge", "patient_age"), ("StudyDate", "study_date"),
                  ("StudyTime", "study_time"), ("AccessionNumber", "accession"), ("StudyDescription", "description"),
                  ("ReferringPhysicianName", "referring"), ("InstitutionName", "institution")):
        if info.get(k):
            setattr(ds, kw, info[k])
    ds.StudyInstanceUID = study
    return ds


def _nome_seguro(nome: str, i: int) -> str:
    base = Path(str(nome or "").replace("\\", "/")).name
    base = re.sub(r"[^\w .()\-]+", "_", base).strip(" .") or f"arquivo{i}"
    return base[:120]


def _rotear(c, s, study: str, series: list[str]) -> int:
    """As regras de roteamento que valem para o exame (a origem não conta), como `_rotear_anexos` do Ipê de mesa."""
    net = getattr(c, "net", None)
    if net is None or not series:
        return 0
    from ipe.automation.rules import route_matches
    info = c.repo.study_info(study) or {}
    n = 0
    try:
        regras = c.repo.rules("route")
    except Exception:  # noqa: BLE001
        return 0
    for r in regras:
        cfg = dict(r.get("config") or {})
        cfg.pop("origins", None)
        if not r.get("active") or not cfg.get("node_id") or not route_matches(cfg, info, ""):
            continue
        node = c.repo.node(cfg["node_id"])
        if node is None:
            continue
        try:
            net.send(node, c.repo.identity(cfg.get("identity_id")), [study], f"Anexo → {node['name']}",
                     series_uids=series, dono=s.username)
            n += 1
        except Exception:  # noqa: BLE001
            log.exception("enviar o anexo (web)")
    return n


def anexar(c, s, corpo: dict) -> dict:
    """{study, arquivos: [{nome, dados (base64)}]} → {n, series, avisos, enviados}."""
    from ipe.importer import anexos as AX
    from ipe.importer.scanner import Importer
    from ipe.importer.thumbnails import generate_thumbnails
    study = str(corpo.get("study") or "")
    _exame(c, s, study)
    if not s.can("import"):
        raise PermissionError("anexar pede a permissão de importar")
    arquivos = list(corpo.get("arquivos") or [])
    if not arquivos:
        raise ValueError("nenhum arquivo")
    if len(arquivos) > LIMITE_ARQUIVOS:
        raise ValueError(f"no máximo {LIMITE_ARQUIVOS} arquivos de uma vez")
    tmp = Path(tempfile.mkdtemp(prefix="ipe_anexos_web_"))
    try:
        entrada = tmp / "entrada"
        entrada.mkdir()
        caminhos, total, avisos = [], 0, []
        for i, a in enumerate(arquivos, 1):
            nome = _nome_seguro(a.get("nome", ""), i)
            if AX.tipo(Path(nome)) not in ("pdf", "imagem"):
                avisos.append(f"{nome}: formato não aceito — salve como PDF")
                continue
            dados = base64.b64decode(str(a.get("dados") or ""), validate=False)
            total += len(dados)
            if total > LIMITE_BYTES:
                raise ValueError("arquivos grandes demais (até 80 MB de uma vez)")
            p = entrada / f"{i:03d}_{nome}"
            p.write_bytes(dados)
            caminhos.append(p)
        out = {"n": 0, "series": [], "avisos": avisos, "enviados": 0}
        if not caminhos:
            return out
        dss, av = AX.criar(caminhos, _fonte(c, study), s.full_name or s.username)
        # o nome que aparece é o do arquivo, sem o número que pusemos na frente
        out["avisos"] += [re.sub(r"^\d{3}_", "", x) for x in av]
        if not dss:
            return out
        for ds in dss:
            for kw in ("ImageComments", "DocumentTitle", "DerivationDescription"):
                if kw in ds:
                    setattr(ds, kw, re.sub(r"(^|\s)\d{3}_", r"\1", str(ds.get(kw))))
        saida = tmp / "dicom"
        AX.gravar(dss, saida)
        r = Importer(c.db, c.storage).import_paths([saida])
        try:
            generate_thumbnails(c.repo, r.new_series)
        except Exception:  # noqa: BLE001
            log.exception("miniaturas (anexo web)")
        out["n"] = len(dss)
        out["series"] = sorted({str(d.SeriesInstanceUID) for d in dss})
        c.repo.audit("anexou_documento", (", ".join(re.sub(r"^\d{3}_", "", p.name) for p in caminhos)
                                          + " — pelo navegador")[:400], user=s.username, study_uid=study)
        out["enviados"] = _rotear(c, s, study, out["series"])
        if getattr(c, "on_import", None):
            try:
                c.on_import([study])
            except Exception:  # noqa: BLE001
                pass
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def documentos(c, s, study: str) -> dict:
    """Os documentos encapsulados (PDF) do exame: [{sop, serie, titulo, data}]."""
    import pydicom
    _exame(c, s, study)
    out = []
    for se in c.repo.series_for_study(study):
        if (getattr(se, "modality", "") or "") != "DOC":
            continue
        for inst in c.repo.instances_for_series(se.series_uid):
            caminho = inst.get("path") or inst.get("file_path") or ""
            titulo = ""
            try:
                ds = pydicom.dcmread(caminho, stop_before_pixels=True, force=True,
                                     specific_tags=["DocumentTitle", "SeriesDescription"])
                titulo = str(ds.get("DocumentTitle", "") or "")
            except Exception:  # noqa: BLE001
                pass
            out.append({"sop": inst.get("sop_uid") or inst.get("sop_instance_uid") or "", "serie": se.series_uid,
                        "titulo": titulo or (se.description or "Documento")})
    return {"documentos": out}


def documento(c, s, study: str, sop: str) -> tuple[bytes, str, str]:
    """(bytes, MIME, título) de um documento do exame."""
    from ipe.importer import anexos as AX
    _exame(c, s, study)
    for se in c.repo.series_for_study(study):
        if (getattr(se, "modality", "") or "") != "DOC":
            continue
        for inst in c.repo.instances_for_series(se.series_uid):
            if (inst.get("sop_uid") or inst.get("sop_instance_uid")) == sop:
                caminho = inst.get("path") or inst.get("file_path") or ""
                c.repo.audit("abriu_documento", "pelo navegador", user=s.username, study_uid=study)
                return AX.documento_de(caminho)
    raise KeyError("documento não encontrado")
