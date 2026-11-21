"""Os achados de IA do exame viajam com a exportação (0.100.86).

Os achados (a %LAA por lobo do enfisema, a composição em L3, os nódulos…) ficam no banco do Ipê, não nos arquivos
DICOM — a SEG leva só as máscaras. Na exportação DICOM (e na cópia anonimizada no banco) eles vão num arquivo
`IPE_ACHADOS.json` na raiz; ao importar a pasta (ou o .zip) em outro Ipê, voltam para o banco, ligados ao exame e à
série pelos UIDs — os novos, quando a exportação gerou UIDs novos.

Anonimizado: sai o que é de pessoa (quem revisou, a nota livre); ficam os números, o estado (sugerido, confirmado,
corrigido, descartado), o modelo e o porquê da série.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

ARQUIVO = "IPE_ACHADOS.json"
VERSAO = 1
CAMPOS = ("ferramenta", "rotulo", "tipo", "local", "posicao", "numeros", "corrigidos", "modelo", "versao",
          "elegibilidade", "segmento", "estado")


def para_exportar(repo, estudos: dict[str, set[str]], opts, salt: str) -> list[dict]:
    """`estudos`: {study_uid: {series_uid exportadas}}. Os achados de séries que não saíram ficam de fora."""
    from ipe.exporter.anonymize import new_uid
    anon = bool(getattr(opts, "enabled", False))
    trocar = anon and bool(getattr(opts, "new_uids", True))

    def uid(u: str) -> str:
        return new_uid(u, salt) if (trocar and u) else u
    out = []
    for st, series in estudos.items():
        try:
            achados = repo.achados(st)
        except Exception:  # noqa: BLE001 - repositório sem achados (cliente antigo): nada a levar
            log.debug("achados de %s", st, exc_info=True)
            continue
        for a in achados:
            if a.get("series_uid") and a["series_uid"] not in series:
                continue
            d = {k: a.get(k) for k in CAMPOS}
            d["study_uid"], d["series_uid"] = uid(st), uid(a.get("series_uid") or "")
            if not anon:
                d["revisor"], d["nota"] = a.get("revisor") or "", a.get("nota") or ""
                d["revisado_em"] = str(a.get("revisado_em") or "")
            out.append(d)
    return out


def gravar(pasta: Path, achados: list[dict]) -> Path | None:
    if not achados:
        return None
    arq = Path(pasta) / ARQUIVO
    arq.write_text(json.dumps({"ipe_achados": VERSAO, "achados": achados}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return arq


def procurar(caminhos) -> list[Path]:
    """Os IPE_ACHADOS.json dentro dos caminhos importados (pasta, arquivo ou o que um compactado virou)."""
    out = []
    for p in caminhos:
        p = Path(p)
        if p.is_file() and p.name.upper() == ARQUIVO.upper():
            out.append(p)
        elif p.is_dir():
            out += [x for x in p.rglob("*") if x.is_file() and x.name.upper() == ARQUIVO.upper()]
    return out


def ler(arq: Path) -> list[dict]:
    try:
        dados = json.loads(Path(arq).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("achados de IA: não deu para ler %s", arq)
        return []
    itens = dados.get("achados") if isinstance(dados, dict) else None
    return [it for it in itens if isinstance(it, dict)] if isinstance(itens, list) else []


def importar(db, arq: Path) -> int:
    """Põe no banco os achados do arquivo cujo exame já está no banco. Devolve quantos entraram."""
    return importar_itens(db, ler(arq))


def importar_itens(db, itens: list[dict]) -> int:
    """Não repete o que já existe (mesma ferramenta, rótulo e tipo no exame); exame que não está no banco: fica
    de fora."""
    from datetime import datetime

    from sqlalchemy import select

    from ipe.db.models import AchadoIA, Study
    if not isinstance(itens, list):
        return 0
    n = 0
    with db.session() as s:
        existe = {}
        for it in itens:
            if not isinstance(it, dict) or not it.get("study_uid"):
                continue
            st = it["study_uid"]
            if st not in existe:
                if s.scalar(select(Study.id).where(Study.study_uid == st)) is None:
                    existe[st] = None
                else:
                    existe[st] = {(a.ferramenta, a.rotulo, a.tipo) for a in
                                  s.scalars(select(AchadoIA).where(AchadoIA.study_uid == st))}
            ja = existe[st]
            chave = (it.get("ferramenta") or "", it.get("rotulo") or "", it.get("tipo") or "")
            if ja is None or chave in ja:
                continue
            ja.add(chave)

            def j(v):
                return json.dumps(v, ensure_ascii=False) if v not in (None, "", {}) else ""
            estado = it.get("estado") if it.get("estado") in ("sugerido", "confirmado", "corrigido",
                                                              "descartado") else "sugerido"
            quando = None
            if estado != "sugerido":
                try:
                    quando = datetime.fromisoformat(str(it.get("revisado_em") or "")) if it.get("revisado_em") else None
                except ValueError:
                    quando = None
            s.add(AchadoIA(study_uid=st, series_uid=it.get("series_uid") or "", ferramenta=chave[0],
                           rotulo=chave[1], tipo=chave[2], local=it.get("local") or "",
                           posicao=j(it.get("posicao")), numeros=j(it.get("numeros")) or "{}",
                           corrigidos=j(it.get("corrigidos")), modelo=it.get("modelo") or "",
                           versao=it.get("versao") or "", elegibilidade=it.get("elegibilidade") or "",
                           segmento=int(it.get("segmento") or 0), estado=estado,
                           revisor=it.get("revisor") or "", revisado_em=quando, nota=it.get("nota") or ""))
            n += 1
        s.commit()
    if n:
        log.info("achados de IA importados: %d", n)
    return n
