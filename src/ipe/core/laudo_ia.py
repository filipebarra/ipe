"""IA no texto do laudo (0.99.54, onda B5 do plano ViewerHub/Eden).

Duas partes, as duas só **sugerem** — nada muda o laudo sem o médico aceitar:

1. **Conferência local** (sem rede, sempre disponível, também antes de assinar): campos não preenchidos
   ("___", "{campo}"), medida sem unidade ou implausível, palavra repetida, "direita esquerda", órgão que
   não combina com o sexo do paciente, categoria BI-RADS do texto diferente da do formulário, conduta que
   não combina com a categoria, conclusão que fala de um lado que o corpo do laudo não cita, seção de
   impressão vazia.
2. **Modelo de linguagem** (opcional, configurado em Configurações ▸ Laudos ▸ IA no texto do laudo):
   *refinar o texto* (gramática e clareza, sem mudar achados), *gerar a impressão* a partir dos achados e
   *apontar erros*. Provedores: **Ollama** (local, no próprio computador ou na rede), um servidor
   **compatível com OpenAI** (LM Studio, vLLM, llama.cpp…) ou a **API da Anthropic**. Antes de sair do
   programa, o texto perde o nome, o ID, o accession e a data de nascimento do paciente (trocados por
   marcadores que voltam na resposta). A chave da API é guardada cifrada (core/segredos.py).
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
import urllib.error
import urllib.request

from ipe.reporting import birads as BR

log = logging.getLogger(__name__)

PROVEDORES = {"": "Desligada", "ollama": "Ollama (local)", "openai": "Compatível com OpenAI (LM Studio, vLLM…)",
              "anthropic": "API da Anthropic (Claude)"}
URL_PADRAO = {"ollama": "http://localhost:11434", "openai": "http://localhost:1234/v1",
              "anthropic": "https://api.anthropic.com"}
MODELO_PADRAO = {"ollama": "llama3.1", "openai": "local-model", "anthropic": "claude-sonnet-5-5"}
ACOES = {"refinar": "Refinar o texto", "impressao": "Gerar a impressão", "erros": "Apontar erros"}
SISTEMA = ("Você é um radiologista revisor experiente, escrevendo em português do Brasil. Nunca invente "
           "achados, medidas, lateralidade, categorias ou recomendações que não estejam no texto. Responda só "
           "com o que foi pedido, sem comentários antes ou depois.")
PEDIDOS = {
    "refinar": ("Revise a redação do laudo radiológico abaixo: corrija gramática, concordância, pontuação e "
                "clareza. Não acrescente, não tire e não mude achados, medidas, lateralidade, categorias, datas "
                "nem conclusões. Mantenha a estrutura e as seções. Devolva só o laudo revisado."),
    "impressao": ("A partir dos achados do laudo radiológico abaixo, escreva a seção de IMPRESSÃO (conclusão), "
                  "concisa, em tópicos curtos, do mais para o menos importante, sem inventar nada. Se houver "
                  "categoria BI-RADS no laudo, mantenha a mesma. Devolva só o texto da impressão, sem o título."),
    "erros": ("Revise o laudo radiológico abaixo e aponte possíveis erros: lateralidade trocada, incoerência "
              "entre achados e conclusão, medidas sem unidade ou implausíveis, categoria (BI-RADS etc.) "
              "incoerente com os achados ou a conduta, órgão que não combina com o sexo do paciente, termos "
              "trocados ou frases ambíguas. Liste em tópicos curtos, citando o trecho. Se não houver nada, "
              "responda exatamente: Nenhum erro encontrado."),
}

SO_FEMININO = r"\b(utero|uterin\w*|ovario\w*|endometri\w*|colo uterino|anexos? uterin\w*|tubas? uterin\w*)\b"
SO_MASCULINO = r"\b(prostat\w*|testicul\w*|vesiculas? semina\w*|escrot\w*|epididim\w*)\b"


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()


# ------------------------------------------------------------------ conferência local
def _aviso(nivel: str, msg: str, trecho: str = "") -> dict:
    return {"nivel": nivel, "msg": msg, "trecho": trecho.strip()[:80]}


def _secoes(texto: str) -> tuple[str, str]:
    """(corpo, impressão) — a impressão é o que vem depois de IMPRESSÃO/CONCLUSÃO/OPINIÃO."""
    m = re.search(r"^\s*(IMPRESS[AÃ]O|CONCLUS[AÃ]O|OPINI[AÃ]O|IMPRESS[AÃ]O DIAGN[OÓ]STICA)\s*:?\s*$|"
                  r"^\s*(IMPRESS[AÃ]O|CONCLUS[AÃ]O)\s*:", texto, re.I | re.M)
    if not m:
        return texto, ""
    return texto[:m.start()], texto[m.end():]


def conferir(texto: str, fields: dict | None = None, info: dict | None = None) -> list[dict]:
    """Avisos da conferência local, do mais grave para o menos ("erro" antes de "atencao")."""
    av: list[dict] = []
    t = texto or ""
    tl = _sem_acento(t)
    for m in re.finditer(r"_{3,}|\{[a-z_]+\}", t):
        ini = t.rfind("\n", 0, m.start()) + 1
        av.append(_aviso("erro", "campo não preenchido", t[ini:t.find("\n", m.end()) if "\n" in t[m.end():] else None]))
    num = r"\d+(?:[.,]\d+)?"
    for m in re.finditer(rf"\bmedindo\s+(?:cerca de\s+)?({num}(?:\s*[x×]\s*{num})*)(?!\s*(?:mm|cm|m\b|ml|cc|%))",
                         t, re.I):
        av.append(_aviso("erro", "medida sem unidade", m.group(0)))
    for m in re.finditer(rf"({num})\s*(mm|cm)\b", t, re.I):
        v = float(m.group(1).replace(",", "."))
        if (m.group(2).lower() == "mm" and v > 400) or (m.group(2).lower() == "cm" and v > 60):
            av.append(_aviso("atencao", "medida grande demais — conferir a unidade", m.group(0)))
    for m in re.finditer(r"\b(\w{2,})\s+\1\b", t, re.I):
        if not m.group(1).isdigit():
            av.append(_aviso("atencao", "palavra repetida", m.group(0)))
    for m in re.finditer(r"\b(direit[oa]s?\s+esquerd[oa]s?|esquerd[oa]s?\s+direit[oa]s?)\b", tl):
        av.append(_aviso("erro", "lateralidade dupla", m.group(0)))
    sexo = str((info or {}).get("sex") or "").upper()[:1]
    if sexo == "M":
        for m in re.finditer(SO_FEMININO, tl):
            av.append(_aviso("erro", "órgão feminino em paciente do sexo masculino", m.group(0)))
    elif sexo == "F":
        for m in re.finditer(SO_MASCULINO, tl):
            av.append(_aviso("erro", "órgão masculino em paciente do sexo feminino", m.group(0)))
    corpo, imp = _secoes(t)
    if re.search(r"^\s*(IMPRESS[AÃ]O|CONCLUS[AÃ]O)", t, re.I | re.M) and not imp.strip():
        av.append(_aviso("erro", "impressão / conclusão vazia"))
    if imp.strip():
        cl, il = _sem_acento(corpo), _sem_acento(imp)
        for lado, padrao in (("direito", r"\bdireit[oa]s?\b"), ("esquerdo", r"\besquerd[oa]s?\b")):
            if re.search(padrao, il) and not re.search(padrao, cl) and cl.strip():
                av.append(_aviso("atencao", f"a conclusão cita o lado {lado}, que o corpo do laudo não cita"))
    f = fields or {}
    if f.get("kind"):
        cat = BR.final_category(f)
        no_texto = {c.upper() for c in re.findall(r"BI-?RADS[®\s:]*(?:categoria\s*)?([0-6](?:\s?[ABC])?)\b", t, re.I)}
        no_texto = {c.replace(" ", "") for c in no_texto}
        if cat and no_texto and cat not in no_texto:
            av.append(_aviso("erro", f"o texto cita BI-RADS {', '.join(sorted(no_texto))}, mas o formulário dá "
                                     f"{cat}"))
        rec = _sem_acento(f.get("recommendation") or "")
        if cat == "3" and rec and "rotina" in rec:
            av.append(_aviso("erro", "BI-RADS 3 com conduta de rastreamento de rotina"))
        if cat in ("4A", "4B", "4C", "5") and rec and "histopatol" not in rec and "biops" not in rec:
            av.append(_aviso("atencao", f"BI-RADS {cat} sem recomendação de diagnóstico histopatológico"))
    vistos, out = set(), []
    for a in sorted(av, key=lambda a: a["nivel"] != "erro"):
        k = (a["msg"], a["trecho"])
        if k not in vistos:
            vistos.add(k)
            out.append(a)
    return out


def texto_dos_avisos(av: list[dict]) -> str:
    return "\n".join(("✖ " if a["nivel"] == "erro" else "⚠ ") + a["msg"] + (f" — “{a['trecho']}”" if a["trecho"] else "")
                     for a in av)


# ------------------------------------------------------------------ privacidade
def anonimizar(texto: str, info: dict | None) -> tuple[str, dict[str, str]]:
    """Troca nome, ID, accession e nascimento por marcadores; devolve (texto, {marcador: original})."""
    info = info or {}
    mapa: dict[str, str] = {}
    out = texto or ""
    nome = str(info.get("patient_name") or "").replace("^", " ").strip()
    candidatos = [("[PACIENTE]", nome)] + [(f"[NOME{i}]", p) for i, p in enumerate(nome.split(), 1) if len(p) > 3]
    candidatos += [("[ID]", str(info.get("patient_id") or "")), ("[ACCESSION]", str(info.get("accession") or ""))]
    nasc = str(info.get("birth_date") or "")
    if len(nasc) == 8 and nasc.isdigit():
        candidatos += [("[NASCIMENTO]", f"{nasc[6:8]}/{nasc[4:6]}/{nasc[:4]}"), ("[NASCIMENTO]", nasc)]
    for marca, valor in candidatos:
        if valor and len(valor) >= 3:
            rx = re.compile(re.escape(valor), re.I)
            if rx.search(out):
                out = rx.sub(marca, out)
                mapa.setdefault(marca, valor)
    return out, mapa


def restaurar(texto: str, mapa: dict[str, str]) -> str:
    for marca, valor in mapa.items():
        texto = texto.replace(marca, valor)
    return texto


# ------------------------------------------------------------------ modelo de linguagem
def config(settings) -> dict:
    from ipe.core import segredos as SG

    def g(k, d=""):
        try:
            return settings.get(f"laudo_ia.{k}", d) if settings is not None else d
        except Exception:  # noqa: BLE001
            return d
    prov = str(g("provedor", "") or "")
    return {"provedor": prov, "url": str(g("url", "") or URL_PADRAO.get(prov, "")),
            "modelo": str(g("modelo", "") or MODELO_PADRAO.get(prov, "")),
            "chave": SG.abrir_ou_vazio(str(g("chave", "") or "")), "tempo": float(g("tempo", 120) or 120),
            "conferir_ao_assinar": bool(g("conferir_ao_assinar", True))}


def remoto(cfg: dict) -> bool:
    u = (cfg.get("url") or "").lower()
    return not any(h in u for h in ("://localhost", "://127.", "://[::1]"))


def _post(url: str, corpo: dict, cab: dict, tempo: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **cab}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:  # noqa: S310 (endereço configurado pelo usuário)
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"o servidor respondeu {e.code}: {detalhe}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"sem conexão com {url}: {e.reason}") from None


def conversar(cfg: dict, sistema: str, usuario: str, post=None) -> str:
    """Uma pergunta ao modelo configurado; devolve o texto da resposta."""
    post = post or _post
    prov, url, modelo = cfg.get("provedor"), (cfg.get("url") or "").rstrip("/"), cfg.get("modelo")
    if prov == "ollama":
        r = post(url + "/api/chat", {"model": modelo, "stream": False, "options": {"temperature": 0.2},
                                     "messages": [{"role": "system", "content": sistema},
                                                  {"role": "user", "content": usuario}]}, {}, cfg.get("tempo", 120))
        return str(((r or {}).get("message") or {}).get("content") or "").strip()
    if prov == "openai":
        base = url if url.endswith("/v1") else url + "/v1"
        cab = {"Authorization": f"Bearer {cfg['chave']}"} if cfg.get("chave") else {}
        r = post(base + "/chat/completions", {"model": modelo, "temperature": 0.2,
                                              "messages": [{"role": "system", "content": sistema},
                                                           {"role": "user", "content": usuario}]}, cab,
                 cfg.get("tempo", 120))
        return str((((r or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if prov == "anthropic":
        if not cfg.get("chave"):
            raise RuntimeError("falta a chave da API da Anthropic (Configurações ▸ Laudos ▸ IA no texto do laudo)")
        r = post((url or URL_PADRAO["anthropic"]) + "/v1/messages",
                 {"model": modelo, "max_tokens": 2000, "system": sistema,
                  "messages": [{"role": "user", "content": usuario}]},
                 {"x-api-key": cfg["chave"], "anthropic-version": "2023-06-01"}, cfg.get("tempo", 120))
        return "".join(b.get("text", "") for b in (r or {}).get("content", []) if b.get("type") == "text").strip()
    raise RuntimeError("a IA do texto do laudo está desligada (Configurações ▸ Laudos ▸ IA no texto do laudo)")


def pedir(acao: str, texto: str, cfg: dict, info: dict | None = None, post=None) -> str:
    """Refinar / gerar a impressão / apontar erros. O texto vai sem os dados do paciente e volta com eles."""
    if acao not in PEDIDOS:
        raise ValueError(acao)
    limpo, mapa = anonimizar(texto, info)
    sexo = str((info or {}).get("sex") or "").upper()[:1]
    extra = {"M": "\nSexo do paciente: masculino.", "F": "\nSexo do paciente: feminino."}.get(sexo, "")
    resp = conversar(cfg, SISTEMA, f"{PEDIDOS[acao]}{extra}\n\n---\n{limpo}\n---", post=post)
    resp = re.sub(r"^```\w*\n|\n```$", "", resp.strip())
    return restaurar(resp, mapa)
