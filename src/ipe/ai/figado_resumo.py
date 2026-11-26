"""0.100.102: o resumo da RM do fígado gravado no exame como imagem (Secondary Capture, OT) — gordura, ferro e
rigidez numa tabela, como o "Densidade e calcificações (Ipê)" da mamografia.

Pedido dele (23/11/2026): *"a quantificação de gordura, ferro e rigidez não está gerando uma imagem OT, como essa da
densidade mamária. Eu queria isso"*.

- Gravado ao fim da IA de fígado (medida automática, sem conferência) e refeito a cada revisão de um achado do fígado
  (confirmar, corrigir, descartar, voltar a sugerido), no Ipê de mesa e no Ipê Web: a imagem mostra sempre os números
  que valem (os corrigidos por cima dos da IA) e quem conferiu.
- Uma série só ("Fígado na RM: resumo (Ipê)", número 989): a anterior é apagada ao gravar a nova.
- Traz o nome do paciente escrito: BurnedInAnnotation = YES (sai na anonimização como as outras telas).

Sem Qt (roda no servidor).
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np

from ipe.ai import achados as AC
from ipe.ai import figado_rm as F

log = logging.getLogger(__name__)

DESC_RESUMO = "Fígado na RM: resumo (Ipê)"
SERIE_RESUMO = 989

#: (tipo do achado, título da faixa, chaves na ordem em que aparecem)
SECOES = (
    (F.TIPO_GORDURA, "GORDURA HEPÁTICA (PDFF)",
     ("pdff_mediana", "pdff_media", "pdff_p25", "pdff_p75", "pdff_segmentos")),
    (F.TIPO_DIXON, "GORDURA PELA DUPLA ECO (EM FASE / FORA DE FASE)", ("ff_sinal", "razao_ef_ff")),
    (F.TIPO_FERRO, "FERRO HEPÁTICO (R2*)",
     ("r2_mediana", "r2_p25", "r2_p75", "t2_ms", "r2_15", "lic", "lic_formula", "lic_wood", "lic_hankins", "campo_t",
      "lic_grau", "baco_r2")),
    (F.TIPO_RIGIDEZ, "RIGIDEZ HEPÁTICA (ELASTOGRAFIA POR RM)",
     ("kpa_media", "kpa_mediana", "kpa_p25", "kpa_p75", "area_cm2", "cortes", "fracao_confiavel",
      "heterogeneidade", "faixa", "outra_aquisicao")),
)
ESTADOS = {"sugerido": "não conferido pelo médico", "confirmado": "confirmado", "corrigido": "corrigido",
           "descartado": "descartado pelo médico"}
REFERENCIAS = ("Fígado e baço: TotalSegmentator (total_mr); valores dos mapas do aparelho. PDFF: graus de Tang et al. "
               "(Radiology 2015).",
               "Ferro: R2* → LIC (Wood 2005 e Hankins 2009; 3 T → 1,5 T para Wood, Alam 2016). Rigidez: faixas de Venkatesh, Yin & Ehman "
               "(JMRI 2013).")


def _do_exame(repo, study_uid: str) -> dict[str, dict]:
    """O achado que vale de cada tipo (o revisado mais recente, senão o sugerido mais recente)."""
    out: dict[str, dict] = {}
    for a in sorted(repo.achados(study_uid, F.FERRAMENTA), key=lambda x: x.get("id") or 0):
        t = a.get("tipo", "")
        atual = out.get(t)
        if atual is None or a.get("estado") != "sugerido" or atual.get("estado") == "sugerido":
            out[t] = a
    return out


def _quando(v) -> str:
    s = str(v or "")[:16].replace("T", " ")
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}{s[10:]}"
    return s


def linhas(achados: dict[str, dict]) -> list[tuple[str, str, str]]:
    """(tipo, esquerda, direita) para a tabela: "faixa", "linha" ou "longa" (valor numa linha própria)."""
    out: list[tuple[str, str, str]] = []
    for tipo, titulo, chaves in SECOES:
        a = achados.get(tipo)
        if not a:
            continue
        out.append(("faixa", titulo, ""))
        if a.get("estado") == "descartado":
            out.append(("linha", "Situação", ESTADOS["descartado"]))
            continue
        res = F.resultado_do_achado(a)
        if res:
            out.append(("linha", "Resultado", res))
        nums = AC.numeros_validos(a)
        corrigidos = set((a.get("corrigidos") or {}).keys())
        for k in chaves:
            d = nums.get(k)
            if not d or d.get("v") in (None, ""):
                continue
            nome = str(d.get("n") or k) + (" (corrigido)" if k in corrigidos else "")
            valor = AC._fmt(d)
            out.append(("longa" if len(valor) > 48 else "linha", nome, valor))
        for escala, valor, _dica in F.escalas_do_achado(a):
            if not any(escala == x[1] for x in out):
                out.append(("linha", escala, valor))
        quem = ESTADOS.get(a.get("estado") or "sugerido", a.get("estado") or "")
        if a.get("estado") in ("confirmado", "corrigido"):
            quem = f"{quem} · {a.get('revisor') or '—'} {_quando(a.get('revisado_em'))}".strip()
        out.append(("linha", "Conferência", quem))
    return out


def situacao(achados: dict[str, dict]) -> str:
    est = [a.get("estado") or "sugerido" for a in achados.values()]
    if est and all(e in ("confirmado", "corrigido", "descartado") for e in est):
        return "conferido pelo médico"
    if any(e in ("confirmado", "corrigido") for e in est):
        return "conferido em parte pelo médico"
    return "medida automática, sem conferência do médico"


def tabela(achados: dict[str, dict], cab: dict) -> np.ndarray:
    """A imagem do resumo (RGB), no mesmo desenho da mamografia."""
    from PIL import Image, ImageDraw

    from ipe.ai.mama_sr import _fonte
    lin = linhas(achados)
    larg, alt_l, topo = 1400, 40, 190
    alt = topo + sum(2 * alt_l if t == "longa" else alt_l for t, _a, _b in lin) + 130
    im = Image.new("RGB", (larg, alt), (255, 255, 255))
    g = ImageDraw.Draw(im)
    g.rectangle([0, 0, larg, 120], fill=(38, 54, 89))
    g.text((40, 26), "RM do fígado — gordura, ferro e rigidez", font=_fonte(36), fill=(255, 255, 255))
    g.text((40, 78), f"{cab.get('paciente', '')}  ·  {cab.get('id', '')}  ·  {cab.get('data', '')}",
           font=_fonte(22), fill=(219, 225, 242))
    g.text((40, 140), f"Ipê · {situacao(achados)} · {datetime.now().strftime('%d/%m/%Y %H:%M')}",
           font=_fonte(20), fill=(90, 90, 90))
    y = topo
    for tipo, a, b in lin:
        if tipo == "faixa":
            g.rectangle([30, y + 4, larg - 30, y + alt_l - 2], fill=(219, 225, 242))
            g.text((44, y + 10), a, font=_fonte(22), fill=(38, 54, 89))
            y += alt_l
        elif tipo == "longa":
            g.text((60, y + 9), a, font=_fonte(22), fill=(30, 30, 30))
            g.text((90, y + alt_l + 7), b, font=_fonte(20), fill=(30, 30, 30))
            g.line([60, y + 2 * alt_l - 1, larg - 60, y + 2 * alt_l - 1], fill=(230, 230, 230))
            y += 2 * alt_l
        else:
            g.text((60, y + 9), a, font=_fonte(22), fill=(30, 30, 30))
            g.text((larg - 60, y + 9), b, font=_fonte(22), fill=(30, 30, 30), anchor="ra")
            g.line([60, y + alt_l - 1, larg - 60, y + alt_l - 1], fill=(230, 230, 230))
            y += alt_l
    g.text((40, alt - 98), REFERENCIAS[0], font=_fonte(18), fill=(110, 110, 110))
    g.text((40, alt - 70), REFERENCIAS[1], font=_fonte(18), fill=(110, 110, 110))
    g.text((40, alt - 42), "Apoio à leitura — a decisão é do médico.", font=_fonte(18), fill=(110, 110, 110))
    return np.asarray(im)


def _origem(repo, study_uid: str, achados: dict[str, dict]) -> str | None:
    """Um arquivo do exame para copiar o cabeçalho (o da série que a IA usou, de preferência)."""
    series = [a.get("series_uid") for a in achados.values() if a.get("series_uid")]
    for su in series:
        try:
            arqs = [f for f in repo.files_for_study(study_uid, [su]) if f]
        except Exception:  # noqa: BLE001
            arqs = []
        if arqs:
            return arqs[0]
    arqs = [f for f in repo.files_for_study(study_uid) if f]
    return arqs[0] if arqs else None


def _apagar_anteriores(repo, study_uid: str, storage_root) -> int:
    n = 0
    for se in repo.series_for_study(study_uid):
        if (se.description or "") == DESC_RESUMO:
            try:
                repo.delete_series(se.series_uid, Path(storage_root))
                n += 1
            except Exception:  # noqa: BLE001
                log.warning("não apaguei o resumo anterior do fígado %s", se.series_uid, exc_info=True)
    return n


def gravar(repo, db, storage_root, study_uid: str) -> str | None:
    """Grava (ou refaz) o resumo; devolve o SeriesInstanceUID, ou None se o exame não tem achado do fígado."""
    import pydicom

    from ipe.imaging.derived import save_secondary_capture
    achados = _do_exame(repo, study_uid)
    if not achados:
        _apagar_anteriores(repo, study_uid, storage_root)
        return None
    origem = _origem(repo, study_uid, achados)
    if not origem:
        raise ValueError("o exame não tem imagens neste computador")
    src = pydicom.dcmread(origem, stop_before_pixels=True, force=True)
    d = str(src.get("StudyDate", "") or "")
    cab = {"paciente": str(src.get("PatientName", "") or "").replace("^", " ").strip(),
           "id": str(src.get("PatientID", "") or ""),
           "data": f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else d}
    rgb = tabela(achados, cab)
    _apagar_anteriores(repo, study_uid, storage_root)
    uid, _sops = save_secondary_capture(rgb, origem, db, Path(storage_root), description=DESC_RESUMO,
                                        series_number=SERIE_RESUMO, extra={"BurnedInAnnotation": "YES"},
                                        parametros="Resumo: gordura, ferro e rigidez hepáticos (" +
                                                   situacao(achados) + ")")
    return uid


def depois_de_revisar(repo, db, storage_root, achado: dict | None) -> str | None:
    """Chamado depois de revisar um achado: se for do fígado, refaz o resumo. Nunca levanta. No Ipê cliente, quem
    refaz é o servidor (é lá que estão os achados e as imagens)."""
    if not achado or achado.get("ferramenta") != F.FERRAMENTA:
        return None
    try:
        cliente = getattr(repo, "client", None)
        if cliente is not None and hasattr(cliente, "rpc") and hasattr(repo, "upload_study"):
            return cliente.rpc("refazer_resumo_do_figado", achado["study_uid"])
        if db is None or storage_root is None:
            return None
        return gravar(repo, db, storage_root, achado["study_uid"])
    except Exception:  # noqa: BLE001
        log.exception("refazer o resumo do fígado")
        return None
