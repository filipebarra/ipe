"""0.100.56: exporta uma lista de casos como um **pacote de casos** — uma pasta com o Ipê Web (em "modo caso"), os
exames anonimizados em DICOMweb estático e o `casos/casos.json` com os textos de cada caso.

Cada caso tem duas partes: a **apresentação** (história clínica, as séries e os documentos da apresentação) e o
**resultado** (diagnóstico, laudo/resultado, biópsia/anatomopatológico, pontos de ensino, as séries e os documentos
do resultado e as marcações — setas, medidas, ROIs — que só aparecem quando se pede o resultado).

O pacote abre de três jeitos: pelo lançador do sistema (`Abrir casos.exe` etc., um servidorzinho local que abre o
navegador), copiado para qualquer site estático, ou servido pelo próprio servidor do Ipê. O navegador não abre um
visualizador completo por `file://` (bloqueia a leitura dos arquivos e os decodificadores), por isso o lançador.

Disposição:
    index.html, assets/…                         o Ipê Web (o mesmo do servidor, base relativa)
    casos/casos.json                             a lista, os textos e o que é de cada parte
    casos/dw/studies.json                        QIDO dos exames
    casos/dw/studies/<st>/series.json            QIDO das séries
    casos/dw/studies/<st>/series/<se>/metadata   DICOM JSON das instâncias
    casos/dw/studies/<st>/series/<se>/thumbnail  PNG
    casos/dw/studies/<st>/series/<se>/instances/<sop>/frames/<n>   o quadro (corpo multipart, HTJ2K sem perda)
    casos/api/medidas/<se>.json                  as marcações (com "resposta")
    casos/api/mamografia/<st>.json               o protocolo de mamografia resolvido (só MG)
    casos/api/documentos/<st>.json, casos/docs/<sop>.pdf
"""
from __future__ import annotations

import json
import logging
import secrets
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

log = logging.getLogger(__name__)

VERSAO_PACOTE = 1
BOUNDARY = "ipecasoframe"
#: o que não vai no pacote (não é imagem nem documento)
FORA = {"SR", "PR", "KO", "REG", "RWV", "FID", "PLAN", "RTPLAN", "RTDOSE", "RTSTRUCT", "SEG"}
LANCADORES = Path(__file__).resolve().parent / "lancadores"


class Cancelado(Exception):
    pass


@dataclass
class Resumo:
    pasta: Path
    casos: int = 0
    series: int = 0
    imagens: int = 0
    bytes: int = 0
    avisos: list[str] = field(default_factory=list)


class _Sessao:
    """Quem pede as contas do servidor (protocolo de mamografia) ao montar o pacote: vê tudo."""
    username = "caso"
    full_name = ""

    def can(self, _perm: str) -> bool:
        return True


def _v(vr: str, *values):
    vals = [v for v in values if v not in (None, "")]
    return {"vr": vr, "Value": vals} if vals else {"vr": vr}


def _remapear(obj, mapa: dict[str, str]):
    """Troca, em toda a estrutura, as UIDs originais pelas do pacote (as que não estão no mapa ficam)."""
    if isinstance(obj, str):
        return mapa.get(obj, obj)
    if isinstance(obj, list):
        return [_remapear(x, mapa) for x in obj]
    if isinstance(obj, dict):
        return {_remapear(k, mapa) if isinstance(k, str) else k: _remapear(v, mapa) for k, v in obj.items()}
    return obj


def _gravar(caminho: Path, dados: bytes | str) -> int:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    b = dados.encode("utf-8") if isinstance(dados, str) else dados
    caminho.write_bytes(b)
    return len(b)


def _json(caminho: Path, obj) -> int:
    return _gravar(caminho, json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def _quadros_comprimidos(caminho: str) -> list[tuple[bytes, str]]:
    """Todos os quadros da instância, comprimidos sem perda (HTJ2K, como o servidor manda) quando dá."""
    import pydicom

    from ipe.central import envio
    from ipe.central import web as WEB
    ds = pydicom.dcmread(caminho, stop_before_pixels=True, force=True)
    n = int(getattr(ds, "NumberOfFrames", 1) or 1)
    originais = WEB.quadros(caminho, list(range(1, n + 1)))
    qual = envio.codec()
    out = []
    for dados, ts in originais:
        r = None
        if qual and ts in envio.CONVERTE and envio._monocromatico(ds) and not (ts == envio.JPEG_LS and qual != "htj2k"):
            try:
                arr = envio._array_jpegls(ds, dados) if ts == envio.JPEG_LS else envio._array_nativo(ds, dados)
                r = envio.codificar(arr, qual)
            except Exception:  # noqa: BLE001
                r = None
        out.append(r if r else (dados, ts))
    return out


def exportar(repo, list_id: int, destino: Path, titulo: str = "", settings=None, progresso=None,
             cancelar=None) -> Resumo:
    """Monta o pacote em `destino` (pasta nova ou vazia). `progresso(feito, total, texto)`; `cancelar()` → True
    interrompe. Os exames saem anonimizados (nome "Caso N", datas deslocadas mantendo os intervalos, sem
    instituição nem médicos, texto gravado tarjado nas capturas)."""
    import pydicom

    from ipe.central import web as WEB
    from ipe.central.dicomweb import series_json, study_json
    from ipe.exporter.anonymize import AnonOptions, anonymize, new_uid
    from ipe.imaging.series import build_frames, read_frame
    from ipe.imaging.windowing import make_thumbnail
    from ipe.importer import anexos as AX

    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    info_lista = repo.case_list_info(list_id) or {}
    itens = repo.list_items(list_id)
    if not itens:
        raise ValueError("a lista não tem casos")
    res = Resumo(pasta=destino)
    sal = secrets.token_hex(16)                     # as UIDs novas não dão para voltar às originais
    base = destino / "casos"
    dw = base / "dw"
    # o que fazer: séries de cada caso (para o progresso)
    plano = []
    for n, it in enumerate(itens, 1):
        if not it.get("present", True):
            res.avisos.append(f"Caso {n}: o exame não está neste computador — ficou de fora")
            continue
        # ligado ao servidor: o exame precisa estar baixado neste computador
        if hasattr(repo, "is_cached") and hasattr(repo, "download"):
            try:
                if not repo.is_cached(it["study_uid"]):
                    if progresso:
                        progresso(0, 1, f"Caso {n}: baixando do servidor…")
                    repo.download(it["study_uid"], cancel=cancelar)
            except Exception:  # noqa: BLE001
                log.exception("pacote: baixar o exame")
        series = [s for s in repo.series_for_study(it["study_uid"]) if (s.modality or "").upper() not in FORA]
        mostrar = set(it.get("show_series") or [])
        resultado = set(it.get("result_series") or [])
        if mostrar:
            series = [s for s in series if s.series_uid in mostrar or s.series_uid in resultado]
        plano.append((n, it, series, resultado))
    total = sum(sum(max(1, s.num_images or 1) for s in ss) for _n, _i, ss, _r in plano) or 1
    feito = 0

    def andar(k: int, texto: str) -> None:
        nonlocal feito
        feito += k
        if cancelar and cancelar():
            raise Cancelado()
        if progresso:
            progresso(min(feito, total), total, texto)

    casos_json, estudos_qido = [], []
    tmp_raiz = Path(tempfile.mkdtemp(prefix="ipe_casos_"))
    try:
        for n, it, series, resultado in plano:
            study_orig = it["study_uid"]
            opts = AnonOptions(enabled=True, name="Caso {n}", patient_id="CASO{n:03d}", keep_sex=True, keep_age=True,
                               shift_dates=True, keep_descriptions=True, keep_institution=False,
                               remove_private=True, new_uids=True, burned="auto")
            mapa: dict[str, str] = {study_orig: new_uid(study_orig, sal)}
            study_novo = mapa[study_orig]
            series_qido, docs, info_paciente = [], [], {}
            n_imagens = 0
            parte_series: dict[str, str] = {}
            for se in series:
                se_novo = new_uid(se.series_uid, sal)
                mapa[se.series_uid] = se_novo
                instancias = repo.instances_for_series(se.series_uid)
                tmp = tmp_raiz / se_novo
                tmp.mkdir(parents=True, exist_ok=True)
                metas, anon_inst, n_img = [], [], 0
                for inst in instancias:
                    cam = inst.get("path") or ""
                    if not cam or not Path(cam).exists():
                        continue
                    try:
                        ds = pydicom.dcmread(cam, force=True)
                        anonymize(ds, opts, n, sal)
                    except Exception:  # noqa: BLE001
                        log.exception("pacote de casos: %s", cam)
                        res.avisos.append(f"Caso {n}: uma imagem não pôde ser lida — ficou de fora")
                        continue
                    sop_novo = str(ds.SOPInstanceUID)
                    mapa[inst["sop_uid"]] = sop_novo
                    if not info_paciente:
                        info_paciente = {"idade": str(ds.get("PatientAge", "") or ""),
                                         "sexo": str(ds.get("PatientSex", "") or ""),
                                         "data": str(ds.get("StudyDate", "") or ""),
                                         "descricao": str(ds.get("StudyDescription", "") or "")}
                    if (se.modality or "").upper() == "DOC" or "EncapsulatedDocument" in ds:
                        dados = bytes(ds.get("EncapsulatedDocument", b"") or b"")
                        mime = str(ds.get("MIMETypeOfEncapsulatedDocument", "") or "application/pdf")
                        if mime == "application/pdf" and dados.endswith(b"\x00"):
                            fim = dados.rfind(b"%%EOF")
                            if fim >= 0:
                                dados = dados[:fim + 5]
                        res.bytes += _gravar(base / "docs" / f"{sop_novo}.pdf", dados)
                        docs.append({"sop": sop_novo, "serie": se_novo,
                                     "titulo": str(ds.get("DocumentTitle", "") or se.description or "Documento"),
                                     "parte": "resultado" if se.series_uid in resultado else "apresentacao"})
                        continue
                    caminho_tmp = tmp / f"{sop_novo}.dcm"
                    ds.save_as(caminho_tmp, enforce_file_format=True)
                    url_serie = f"casos/dw/studies/{study_novo}/series/{se_novo}"
                    m = WEB._meta_da_instancia(sop_novo, str(caminho_tmp), url_serie)
                    if m is None:
                        continue
                    for k, (dados, ts) in enumerate(_quadros_comprimidos(str(caminho_tmp)), 1):
                        corpo = WEB.multipart_quadros([(dados, ts)], BOUNDARY)
                        res.bytes += _gravar(dw / "studies" / study_novo / "series" / se_novo / "instances" / sop_novo
                                             / "frames" / str(k), corpo)
                        n_img += 1
                    metas.append(m)
                    anon_inst.append({**inst, "sop_uid": sop_novo, "path": str(caminho_tmp)})
                    andar(1, f"Caso {n}: {se.description or se.modality}")
                if se.modality and (se.modality or "").upper() == "DOC":
                    continue
                if not metas:
                    continue
                pasta_se = dw / "studies" / study_novo / "series" / se_novo
                res.bytes += _json(pasta_se / "metadata", metas)
                try:
                    fr = build_frames(anon_inst, se_novo)
                    if fr:
                        res.bytes += _gravar(pasta_se / "thumbnail", make_thumbnail(read_frame(fr[len(fr) // 2]), 128))
                except Exception:  # noqa: BLE001
                    log.exception("miniatura do pacote")
                row = SimpleNamespace(study_uid=study_novo, series_uid=se_novo, modality=se.modality,
                                      series_number=se.series_number, description=se.description,
                                      num_images=len(metas))
                series_qido.append(series_json(row))
                parte_series[se_novo] = "resultado" if se.series_uid in resultado else "apresentacao"
                res.series += 1
                res.imagens += n_img
                n_imagens += len(metas)
                # as marcações do Ipê nesta série — no pacote, ficam para o resultado
                regs = []
                for k, r in enumerate(repo.annotations_for_series([se.series_uid]), 1):
                    if r.get("study_uid") != study_orig or r.get("sop_uid") not in mapa:
                        continue
                    try:
                        d = json.loads(r.get("data") or "{}")
                    except ValueError:
                        continue
                    meta = dict(d.get("meta") or {})
                    meta.pop("autor", None)
                    if meta:
                        d["meta"] = meta
                    else:
                        d.pop("meta", None)
                    regs.append({"id": n * 100000 + len(regs) + 1, "sop_uid": mapa[r["sop_uid"]],
                                 "frame_index": int(r.get("frame_index") or 0), "kind": r.get("kind"),
                                 "data": json.dumps(d), "resposta": True})
                res.bytes += _json(base / "api" / "medidas" / f"{se_novo}.json", regs)
                shutil.rmtree(tmp, ignore_errors=True)
            if not series_qido and not docs:
                res.avisos.append(f"Caso {n}: nenhuma imagem — ficou de fora")
                continue
            res.bytes += _json(dw / "studies" / study_novo / "series.json", series_qido)
            res.bytes += _json(base / "api" / "documentos" / f"{study_novo}.json", docs)
            modalidades = sorted({s.modality for s in series if s.modality})
            qido = study_json(SimpleNamespace(
                study_uid=study_novo, patient_name=f"Caso {n}", patient_id=f"CASO{n:03d}", birth_date="",
                sex=info_paciente.get("sexo", ""), study_date=info_paciente.get("data", ""), study_time="",
                accession="", description=info_paciente.get("descricao", ""), modalities="\\".join(modalidades),
                num_series=len(series_qido), num_images=n_imagens))
            if info_paciente.get("idade"):
                qido["00101010"] = _v("AS", info_paciente["idade"])
            estudos_qido.append(qido)
            # o protocolo de mamografia, resolvido como no servidor (só o exame do caso: sem anteriores)
            if "MG" in modalidades:
                try:
                    mg = WEB.mamografia(repo, _Sessao(), {"study": [study_orig]},
                                        lambda _s, uid: uid == study_orig, settings, None)
                    res.bytes += _json(base / "api" / "mamografia" / f"{study_novo}.json", _remapear(mg, mapa))
                except Exception:  # noqa: BLE001
                    log.exception("pacote: mamografia")
            casos_json.append({
                "n": n, "titulo": it.get("friendly_name") or f"Caso {n}", "study": study_novo,
                "idade": info_paciente.get("idade", ""), "sexo": info_paciente.get("sexo", ""),
                "modalidades": modalidades, "descricao": info_paciente.get("descricao", ""),
                "tags": list(it.get("tags") or []), "series": parte_series,
                "historia": str(it.get("clinical_summary") or ""),
                "resultado": {"diagnostico": str(it.get("hidden_diagnosis") or ""),
                              "laudo": str(it.get("result_text") or ""),
                              "patologia": str(it.get("pathology") or ""),
                              "ensino": str(it.get("note") or "")},
            })
            res.casos += 1
        if not casos_json:
            raise ValueError("nenhum caso pôde ir para o pacote")
        res.bytes += _json(dw / "studies.json", estudos_qido)
        from ipe import __version__
        cfg = WEB.configuracao(settings, None, {"username": "caso", "full_name": "", "role": "viewer",
                                                "perms": ["view"]})
        res.bytes += _json(base / "config.json", cfg)
        res.bytes += _json(base / "casos.json", {
            "formato": VERSAO_PACOTE, "versao_ipe": __version__,
            "titulo": titulo or info_lista.get("name") or "Casos", "casos": casos_json})
        _copiar_site(destino)
        _copiar_lancadores(destino)
        _leia_me(destino, titulo or info_lista.get("name") or "Casos")
        return res
    finally:
        shutil.rmtree(tmp_raiz, ignore_errors=True)


def _copiar_site(destino: Path) -> None:
    from ipe.central import web as WEB
    if not WEB.site_instalado():
        raise FileNotFoundError("o Ipê Web não está neste pacote do Ipê (web_dist)")
    for p in WEB.PASTA.rglob("*"):
        if p.is_file():
            alvo = destino / p.relative_to(WEB.PASTA)
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, alvo)


#: nome no pacote ← arquivo do lançador (feito no release; ver tools/lancador)
NOMES_LANCADORES = {
    "Abrir casos (Windows).exe": "ipe-casos-windows-amd64.exe",
    "Abrir casos (Mac Apple)": "ipe-casos-darwin-arm64",
    "Abrir casos (Mac Intel)": "ipe-casos-darwin-amd64",
    "Abrir casos (Linux)": "ipe-casos-linux-amd64",
}


def _copiar_lancadores(destino: Path) -> list[str]:
    feitos = []
    for nome, origem in NOMES_LANCADORES.items():
        src = LANCADORES / origem
        if src.is_file():
            shutil.copy2(src, destino / nome)
            try:
                (destino / nome).chmod(0o755)
            except OSError:
                pass
            feitos.append(nome)
    return feitos


LEIA_ME = """{titulo}

PT — Como abrir
- Windows: dois cliques em "Abrir casos (Windows).exe".
- Mac: dois cliques em "Abrir casos (Mac Apple)" (M1 ou mais novo) ou "Abrir casos (Mac Intel)". Se o Mac não deixar,
  botão direito ▸ Abrir.
- Linux: "Abrir casos (Linux)" (no terminal: ./"Abrir casos (Linux)").
O navegador abre sozinho com os casos. Deixe a janela preta aberta enquanto estiver vendo; feche-a para terminar.
Nada é instalado e nada sai do computador. Num site: copie a pasta inteira para uma hospedagem de arquivos estáticos e
abra o endereço da pasta. Os exames estão anonimizados. Material de ensino — não destinado a uso diagnóstico.

EN — How to open
- Windows: double-click "Abrir casos (Windows).exe".
- Mac: double-click "Abrir casos (Mac Apple)" (M1 or newer) or "Abrir casos (Mac Intel)". If macOS blocks it,
  right-click ▸ Open.
- Linux: "Abrir casos (Linux)" (in a terminal: ./"Abrir casos (Linux)").
The browser opens with the cases. Keep the black window open while viewing; close it to finish. Nothing is installed
and nothing leaves the computer. On a website: copy the whole folder to any static file hosting and open the folder's
address. The studies are anonymized. Teaching material — not for diagnostic use.

ES — Cómo abrir
- Windows: doble clic en "Abrir casos (Windows).exe".
- Mac: doble clic en "Abrir casos (Mac Apple)" (M1 o más nuevo) o "Abrir casos (Mac Intel)". Si macOS no lo permite,
  clic derecho ▸ Abrir.
- Linux: "Abrir casos (Linux)" (en una terminal: ./"Abrir casos (Linux)").
El navegador se abre con los casos. Deje la ventana negra abierta mientras mira; ciérrela para terminar. No se instala
nada y nada sale del equipo. En un sitio: copie la carpeta entera a un alojamiento de archivos estáticos y abra la
dirección de la carpeta. Los estudios están anonimizados. Material docente — no destinado a uso diagnóstico.

Ipê {versao}
"""


def _leia_me(destino: Path, titulo: str) -> None:
    from ipe import __version__
    (destino / "LEIA-ME.txt").write_text(LEIA_ME.format(titulo=titulo, versao=__version__), encoding="utf-8")
