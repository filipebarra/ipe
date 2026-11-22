"""As IAs no lote a partir de planilha (0.100.97): quais existem, rodar num exame e esperar, e o que vai para a planilha.

- **Mamografia** (densidade da NYU e calcificações vasculares): medidas aqui mesmo, na linha do lote (como no lote da
  mama da 0.100.69). As séries de conferência (a tabela e as imagens com as calcificações marcadas) são gravadas no
  exame **sem conferência** (como "aceitar sem conferir") só quando o lote vai imprimir, exportar ou enviar.
- **As outras** (TotalSegmentator e as do contrato comum: enfisema, fígado, composição, cálcio…): pedidas à fila de IA
  do Ipê (`AutomationEngine.pedir`), na linha da tela, e o lote espera a tarefa terminar. A série de conferência é a
  série nova que a IA gravou (o que apareceu no exame enquanto ela rodou); numa IA que o exame já tinha, as séries
  com o nome dela.
- **O que vai para a planilha**: os números dos achados de IA (com a unidade no título da coluna); nas IAs sem achados,
  o resumo da tarefa.

Sem janelas. `chamar(fn)` roda `fn` na linha da tela (a ponte do Ipê); nos testes, direto.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

MAMA = {"densidade": "Densidade mamária", "calc_vascular": "Calcificações vasculares"}
ESPERA_IA_S = 60 * 60            # uma IA que passa de uma hora num exame é dada como erro
GRAUS_BAC = {"ausente": "Ausente", "leve": "Leve", "moderada": "Moderada", "acentuada": "Acentuada"}
VISTAS = ("R-CC", "L-CC", "R-MLO", "L-MLO")

# situações de uma IA num exame
FEITA, JA_FEITA, NAO_SERVE, ERRO = "feita", "já feita", "não serve", "erro"


def catalogo(engine=None) -> list[tuple[str, str]]:
    """(tipo, título) de todas as IAs que o lote sabe rodar."""
    out = [(k, v) for k, v in MAMA.items()]
    if engine is not None:
        for tipo in engine.tipos_manuais():
            try:
                f = engine._ferramenta(tipo)
            except Exception:  # noqa: BLE001
                f = None
            if f is not None:
                out.append((tipo, f[0]))
    else:
        from ipe.ai import ferramentas as FE
        out += [(t, FE.modulo(t).TITULO) for t in FE.tipos()]
    return out


# ====================================================================== números → colunas
def _num(v, casas: int = 2):
    try:
        return round(float(v), casas)
    except (TypeError, ValueError):
        return None


def campos_densidade(d: dict | None) -> dict:
    if not d:
        return {}
    out = {"Categoria (rede NYU)": (d.get("nyu") or "").upper() or None}
    for letra, p in zip("ABCD", d.get("nyu_probs") or []):
        out[f"Prob. {letra}"] = _num(p, 4)
    avisos = [d.get("nyu_aviso") or ""] + list(d.get("avisos") or [])
    out["Aviso"] = " ".join(a for a in avisos if a) or None
    out["Aparelho"] = d.get("aparelho") or None
    out["Medido em"] = d.get("quando") or None
    out["Versão"] = d.get("versao")
    return out


def campos_calc(c: dict | None) -> dict:
    if not c:
        return {}
    out: dict = {}
    if c.get("sugestao"):
        out["Grau (pela área)"] = GRAUS_BAC.get(c["sugestao"], c["sugestao"])
    out["Área, mama pior (mm²)"] = _num(c.get("area_mm2"))
    pm = c.get("por_mama") or {}
    out["Área direita (mm²)"], out["Área esquerda (mm²)"] = _num(pm.get("R")), _num(pm.get("L"))
    vistas = c.get("vistas") or {}
    for k in VISTAS:
        if k in vistas:
            out[f"Área {k} (mm²)"] = _num(vistas[k].get("area_mm2"))
    e = c.get("escalas") or {}
    if e:
        out["CSBI estimado (0-3)"] = (e.get("csbi") or {}).get("grau")
        out["Vasos calcificados"] = (e.get("csbi") or {}).get("vasos")
        out["Margolies estimado (total)"] = (e.get("margolies") or {}).get("total")
        out["Margolies estimado (categoria)"] = {"negativa": "Negativa", "leve": "Leve",
                                                 "moderada_acentuada": "Moderada a acentuada"} \
            .get((e.get("margolies") or {}).get("categoria"), None)
        out["Loberant estimado (0-3)"] = (e.get("loberant") or {}).get("grau")
        out["BAC-SS estimado (maior mama)"] = (e.get("bacss") or {}).get("maior")
    imagens = c.get("imagens") or []
    out["Prótese"] = "sim" if any(v.get("protese") for v in imagens) else ("não" if imagens else None)
    out["Imagens medidas"] = len(imagens) or None
    out["Avisos"] = " ".join(a for a in [c.get("aviso") or ""] + list(c.get("avisos") or []) if a) or None
    out["Aparelho"] = c.get("aparelho") or None
    out["Medido em"] = c.get("quando") or None
    out["Versão"] = c.get("versao")
    return out


def campos_achados(achados: list[dict]) -> dict:
    """Os números dos achados de uma IA → {coluna: valor}. Com vários achados (nódulos, lesões), cada um ganha o
    prefixo "1 ·", "2 ·"… na ordem em que a IA gravou; a coluna leva a unidade."""
    from ipe.ai import achados as AC
    vale = [a for a in achados if a.get("estado") != "descartado"]
    out: dict = {}
    rotulos = [str(a.get("rotulo") or "") for a in vale]
    distintos = all(rotulos) and len(set(rotulos)) == len(rotulos)     # PDFF, R2*, rigidez…: o nome é o prefixo
    if len(vale) > 1 and not distintos:
        out["Achados"] = len(vale)
    for i, a in enumerate(vale, start=1):
        pre = "" if len(vale) == 1 else (f"{rotulos[i - 1]} · " if distintos else f"{i} · ")
        if a.get("rotulo") and (not distintos or len(vale) == 1):
            out[f"{pre}Achado"] = a["rotulo"]
        if a.get("local"):
            out[f"{pre}Local"] = a["local"]
        for k, d in AC.numeros_validos(a).items():
            nome = d.get("n") or k
            u = d.get("u") or ""
            v = d.get("v")
            if isinstance(v, (list, tuple)):
                v = " × ".join(f"{float(x):.1f}" for x in v)
            elif isinstance(v, float):
                v = round(v, 3)
            out[f"{pre}{nome}" + (f" ({u})" if u else "")] = v
        if a.get("estado") in AC.VALEM:
            out[f"{pre}Revisão"] = AC.ESTADOS.get(a["estado"], a["estado"])
    return out


def _descricoes(mod) -> list[str]:
    """As descrições das séries que a IA grava (as constantes DESC* do módulo, sem a marca da ferramenta)."""
    from ipe.ai.series_ia import MARCAS_IA
    out = []
    for nome in dir(mod):
        if nome.startswith("DESC"):
            v = getattr(mod, nome)
            if isinstance(v, str) and v:
                for m in MARCAS_IA:
                    v = v.replace(m, "")
                v = v.strip(" ·-")
                if len(v) >= 4:
                    out.append(v.lower())
    return out


def series_de_conferencia(repo, study_uid: str, uids: list[str] | None = None, mod=None) -> list[str]:
    """As séries de imagem (não SEG, não SR) entre `uids` — ou, sem `uids`, as do exame com o nome da IA `mod`."""
    out = []
    for se in repo.series_for_study(study_uid):
        mod_se = (getattr(se, "modality", "") or "").upper()
        if mod_se in ("SEG", "SR", "KO", "PR", "RTSTRUCT"):
            continue
        if uids is not None:
            if se.series_uid in uids:
                out.append(se.series_uid)
            continue
        if mod is not None:
            desc = (getattr(se, "description", "") or "").lower()
            if any(desc.startswith(d) or d in desc for d in _descricoes(mod)):
                out.append(se.series_uid)
    return out


# ====================================================================== rodar
class Executor:
    """Roda as IAs de um exame e devolve, por tipo: {"titulo", "situacao", "motivo", "campos", "series"}."""

    def __init__(self, repo, db, storage_root, settings, engine=None, chamar=None) -> None:
        self.repo, self.db, self.storage = repo, db, storage_root
        self.settings, self.engine = settings, engine
        self.chamar = chamar or (lambda fn: fn())

    def rodar(self, study_uid: str, tipos: list[str], refazer: bool = False, parar=None,
              precisa_series: bool = False) -> dict:
        out: dict = {}
        mama = [t for t in tipos if t in MAMA]
        if mama:
            out.update(self._mama(study_uid, mama, refazer, parar, precisa_series))
        for tipo in tipos:
            if tipo in MAMA:
                continue
            if parar is not None and parar.is_set():
                break
            try:
                out[tipo] = self._uma(study_uid, tipo, refazer, parar)
            except Exception as e:  # noqa: BLE001 - uma IA quebrada não derruba as outras
                log.warning("lote: IA %s em %s: %s", tipo, study_uid, e)
                out[tipo] = {"titulo": tipo, "situacao": ERRO, "motivo": str(e)[:300], "campos": {}, "series": []}
        return out

    # ------------------------------------------------------------ mamografia
    def _mama(self, uid: str, tipos: list[str], refazer: bool, parar, precisa_series: bool) -> dict:
        from ipe.ai import calc_vascular as C
        from ipe.ai import densidade_nyu as N
        from ipe.automation import mama_auto as MA
        from ipe.imaging import densidade_revisao as R
        out = {}
        info = self.repo.study_info(uid) or {}
        tem_mg = "MG" in str(info.get("modalities") or "").upper()
        if not tem_mg:
            return {t: {"titulo": MAMA[t], "situacao": NAO_SERVE, "motivo": "o exame não tem MG", "campos": {},
                        "series": []} for t in tipos}
        disp = {"densidade": N.disponivel(), "calc_vascular": C.disponivel()}
        fazer = []
        for t in tipos:
            ok, motivo = disp[t]
            if not ok:
                out[t] = {"titulo": MAMA[t], "situacao": ERRO, "motivo": f"modelo não instalado: {motivo}",
                          "campos": {}, "series": []}
                continue
            ja = (R if t == "densidade" else C).guardada(self.repo, uid)
            if refazer or ja is None or t in MA.falta(self.repo, uid):
                fazer.append(t)
        erros = []
        if fazer:
            r = MA.medir(self.repo, uid, parar, o_que=fazer)
            erros = r.get("erros") or []
        d, c = R.guardada(self.repo, uid), C.guardada(self.repo, uid)
        series: list[str] = []
        if precisa_series and (d or c):
            try:
                from ipe.ai import mama_sr as SR
                g = SR.gravar_sem_conferir(self.repo, self.db, self.storage, uid)
                series = series_de_conferencia(self.repo, uid, list((g or {}).get("series") or []))
            except Exception as e:  # noqa: BLE001
                erros.append(f"séries de conferência: {e}")
        for t in tipos:
            if t in out:
                continue
            g = d if t == "densidade" else c
            meu_erro = [x for x in erros if x.startswith("densidade" if t == "densidade" else "calcifica")]
            if g is None:
                out[t] = {"titulo": MAMA[t], "situacao": ERRO,
                          "motivo": "; ".join(meu_erro) or "não foi possível medir", "campos": {}, "series": []}
                continue
            campos = campos_densidade(g) if t == "densidade" else campos_calc(g)
            out[t] = {"titulo": MAMA[t], "situacao": FEITA if t in fazer else JA_FEITA,
                      "motivo": "; ".join(meu_erro), "campos": campos, "series": series}
        return out

    # ------------------------------------------------------------ as da fila de IA
    def _uma(self, uid: str, tipo: str, refazer: bool, parar) -> dict:
        from ipe.ai import ferramentas as FE
        from ipe.ai import tarefas as TA
        from ipe.ai import totalseg as TS
        if self.engine is None:
            raise RuntimeError("a fila de IA do Ipê não está ligada")
        f = self.engine._ferramenta(tipo)
        if f is None:
            raise KeyError(f"IA desconhecida: {tipo}")
        titulo, escolher, ja_feita = f
        mod = FE.modulo(tipo)
        base = {"titulo": titulo, "campos": {}, "series": []}
        serie, motivo = escolher(self.repo, uid, self.settings)
        if serie is None:
            return dict(base, situacao=NAO_SERVE, motivo=str(motivo or ""))
        if bool(ja_feita(self.repo, uid)) and not refazer:
            return dict(base, situacao=JA_FEITA, motivo="", campos=self._campos(uid, tipo, mod, ""),
                        series=series_de_conferencia(self.repo, uid, mod=mod) if mod is not None else [])
        if not TS.instalado(self.settings) and not getattr(self.engine, "_seg_simular", False):
            return dict(base, situacao=ERRO, motivo="o pacote de IA (segmentação) não está instalado")
        antes = {se.series_uid for se in self.repo.series_for_study(uid)}
        try:
            tid = self.chamar(lambda: self.engine.pedir(uid, tipo, quem="lote"))
        except ValueError:
            tid = None                       # já estava na fila (a automática da chegada): espera ela
        fim = time.time() + ESPERA_IA_S
        tarefa = None
        while True:
            if parar is not None and parar.is_set():
                if tid is not None:
                    TA.REGISTRO.cancelar(tid)
                return dict(base, situacao=ERRO, motivo="lote parado")
            if tid is not None:
                tarefa = next((t for t in TA.REGISTRO.tarefas() if t.id == tid), None)
                if tarefa is not None and not tarefa.ativa:
                    break
            elif not [t for t in TA.REGISTRO.ativas(uid) if t.ferramenta == titulo] \
                    and (uid, tipo) not in getattr(self.engine, "_seg_fila", []):
                break
            if time.time() > fim:
                if tid is not None:
                    TA.REGISTRO.cancelar(tid)
                return dict(base, situacao=ERRO, motivo="a IA passou de uma hora neste exame")
            time.sleep(1.0)
        if tarefa is not None and tarefa.estado != TA.PRONTO:
            sit = NAO_SERVE if tarefa.estado == TA.VAZIO else ERRO
            return dict(base, situacao=sit, motivo=tarefa.mensagem or TA.ROTULO.get(tarefa.estado, tarefa.estado))
        novas = [se.series_uid for se in self.repo.series_for_study(uid) if se.series_uid not in antes]
        return dict(base, situacao=FEITA, motivo="",
                    campos=self._campos(uid, tipo, mod, tarefa.mensagem if tarefa is not None else ""),
                    series=series_de_conferencia(self.repo, uid, novas))

    def _campos(self, uid: str, tipo: str, mod, resumo: str) -> dict:
        if mod is not None:
            achados = self.repo.achados(uid, getattr(mod, "FERRAMENTA", tipo))
            if achados:
                return campos_achados(achados)
        return {"Resumo": resumo} if resumo else {}
