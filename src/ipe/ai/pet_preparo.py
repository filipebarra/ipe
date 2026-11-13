"""Sessão preparada do PET/CT (0.100.33; backlog PET/CT, item 6).

Quando a carga tumoral roda (na chegada do exame ou pelo botão Carga), o exame fica pronto para a leitura:

1. **Referências do PERCIST/Deauville**: fígado (esfera de 3 cm no lobo direito, a mesma do limiar) e mediastino
   (esfera de 1 cm na aorta descendente), guardadas onde a janela *PET…* guarda as medidas à mão — o Deauville, o
   limiar do PERCIST e a comparação do fígado com o exame anterior já saem prontos. Referência medida à mão nunca
   é trocada.
2. **Registro com o PET/CT anterior**: rígido (rotação + translação), TC com TC, com o exame anterior mais recente do
   mesmo paciente. Fica guardado como o registro feito pelo botão: ao abrir o anterior num quadro ao lado, os dois já
   rolam juntos. Registro que já existe (feito à mão ou ajustado) nunca é trocado.
3. **Abrir pronto**: o exame preparado abre na *Leitura PET* (TC com fusão, PET e o MIP girando), se ainda não tem um
   estado de análise guardado.

Sem Qt. A conta roda na linha da ferramenta (fora da tela); a gravação, na linha principal.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

CHAVE_PREPARAR = "carga_pet.preparar"
CHAVE_ABRIR = "carga_pet.abrir_leitura"
CHAVE_TEMPO = "carga_pet.registro_s"
PADROES = {CHAVE_PREPARAR: True, CHAVE_ABRIR: True, CHAVE_TEMPO: 60}
#: a aorta ascendente só existe nos ~7 cm de cima; daqui para baixo, só a descendente
ABAIXO_DO_ARCO_MM = (80.0, 130.0)
MIN_NCC = 0.5                        # abaixo disso o registro não é guardado ("fraca")


def config(settings, chave):
    v = settings.get(chave, None) if settings is not None else None
    return PADROES[chave] if v is None else v


@dataclass
class Preparo:
    figado: dict | None = None
    mediastino: dict | None = None
    anterior_uid: str = ""
    anterior_data: str = ""
    M: list | None = None                 # 4 × 4, ponto deste exame → ponto do anterior
    translacao: list | None = None
    rotacao: float = 0.0
    valor: float | None = None
    qualidade: str = ""
    avisos: list = field(default_factory=list)

    @property
    def feito(self) -> bool:
        return bool(self.figado or self.mediastino or self.M)


# ------------------------------------------------------------------ referências
def centro_da_aorta_descendente(aorta: np.ndarray, pet) -> tuple[int, int, int] | None:
    """(k, j, i) no meio da aorta descendente: de 8 a 13 cm abaixo do topo da aorta (passado o arco), onde só há a
    descendente. Se a máscara é curta (campo parcial), a parte mais posterior do corte do meio."""
    ks = np.flatnonzero(aorta.any(axis=(1, 2)))
    if ks.size < 3:
        return None
    # qual ponta é a cabeça: o z do paciente de cada corte
    z = np.array([float(pet.voxel_to_patient(0, 0, int(k))[2]) for k in (ks[0], ks[-1])])
    topo, base = (ks[0], ks[-1]) if z[0] >= z[1] else (ks[-1], ks[0])
    sentido = 1 if base >= topo else -1
    dz = abs(float(pet.dz)) or 1.0
    extensao = abs(int(base) - int(topo)) * dz
    if extensao >= ABAIXO_DO_ARCO_MM[1] + 20:
        k0 = int(topo + sentido * round(ABAIXO_DO_ARCO_MM[0] / dz))
        k1 = int(topo + sentido * round(ABAIXO_DO_ARCO_MM[1] / dz))
        faixa = range(min(k0, k1), max(k0, k1) + 1)
        pts = np.argwhere(aorta[faixa.start:faixa.stop])
        if pts.size:
            c = pts.mean(axis=0)
            return int(round(c[0] + faixa.start)), int(round(c[1])), int(round(c[2]))
    k = int(round((int(topo) + int(base)) / 2))
    pts = np.argwhere(aorta[k])
    if not pts.size:
        return None
    # posterior = y do paciente maior (LPS): entre os voxels do corte, a metade de trás
    ys = np.array([float(pet.voxel_to_patient(int(i), int(j), k)[1]) for j, i in pts])
    tras = pts[ys >= np.median(ys)]
    c = tras.mean(axis=0)
    return k, int(round(c[0])), int(round(c[1]))


def _completar(r: dict, pet, sul_razao) -> dict:
    k, j, i = r["centro"]
    r = dict(r)
    r["centro_mm"] = [round(float(x), 1) for x in pet.voxel_to_patient(i, j, k)]
    r["sul_razao"] = sul_razao
    r["como"] = "auto"
    return r


def referencias(suv: np.ndarray, pet, org: dict, figado_ref: dict | None = None, sul_razao=None) -> tuple:
    """(fígado, mediastino) no formato da janela PET… — {media, dp, max, n, centro, diam_mm, centro_mm, como}."""
    from ipe.imaging import pet_onco as PO
    espac = (abs(float(pet.dz)), float(pet.dy), float(pet.dx))
    figado = None
    if figado_ref and figado_ref.get("diam_mm") and figado_ref.get("centro"):
        figado = _completar(figado_ref, pet, sul_razao)
    elif "liver" in org:
        c = PO.centro_da_mascara(org["liver"])
        if c is not None:
            r = PO.referencia(suv, espac, c, PO.DIAM_FIGADO_MM, mascara=org["liver"], busca_mm=40.0)
            figado = _completar(r, pet, sul_razao) if r else None
    mediastino = None
    if "aorta" in org:
        c = centro_da_aorta_descendente(org["aorta"], pet)
        if c is not None:
            r = PO.referencia(suv, espac, c, PO.DIAM_MEDIASTINO_MM, mascara=org["aorta"], busca_mm=8.0)
            if r is None:
                # a esfera de 1 cm não coube inteira na máscara (PET de voxel grande, aorta fina): a média da
                # própria máscara em 3 cm de aorta em volta do ponto — sem pegar o que está fora dela
                n = max(1, int(round(15.0 / espac[0])))
                fatia = np.zeros_like(org["aorta"])
                fatia[max(0, c[0] - n):c[0] + n + 1] = org["aorta"][max(0, c[0] - n):c[0] + n + 1]
                v = suv[fatia].astype(np.float64)
                if v.size >= 3:
                    r = {"media": round(float(v.mean()), 3), "dp": round(float(v.std()), 3),
                         "max": round(float(v.max()), 3), "n": int(v.size), "centro": [int(x) for x in c],
                         "diam_mm": PO.DIAM_MEDIASTINO_MM, "pela_mascara": True}
            mediastino = _completar(r, pet, sul_razao) if r else None
    return figado, mediastino


# ------------------------------------------------------------------ o exame anterior
def exame_anterior(repo, study_uid: str, escolher=None) -> tuple[str, str, str]:
    """(uid do exame, uid da TC, data AAAAMMDD) do PET/CT anterior mais recente do mesmo paciente; ("", "", "")."""
    from ipe.ai import carga_pet as CP
    escolher = escolher or CP.escolher_serie
    info = repo.study_info(study_uid) or {}
    pid = str(info.get("patient_id", "") or "")
    data = str(info.get("study_date", "") or "")
    if not pid or not data:
        return "", "", ""
    cands = []
    for r in repo.studies_of_patient(pid):
        uid = getattr(r, "study_uid", "")
        d = str(getattr(r, "study_date", "") or "")
        if not uid or uid == study_uid or not d or d >= data:
            continue
        mods = (getattr(r, "modalities", "") or "").upper()
        if "PT" not in mods or "CT" not in mods:
            continue
        cands.append((d, uid))
    for d, uid in sorted(cands, reverse=True):
        serie, _motivo = escolher(repo, uid)
        if serie:
            return uid, serie, d
    return "", "", ""


def registrar_com_anterior(t, repo, settings=None, registrar=None, montar=None) -> dict | None:
    """Registro rígido da TC deste exame (t.vol) com a TC do PET/CT anterior. None se não há anterior; se o registro
    entre os dois exames já existe, devolve só {"anterior_uid", "anterior_data", "ja_havia": True}."""
    uid_b, serie_b, data_b = exame_anterior(repo, t.study_uid)
    if not uid_b:
        return None
    out = {"anterior_uid": uid_b, "anterior_data": data_b}
    if repo.get_registration(t.study_uid, uid_b) is not None:
        out["ja_havia"] = True
        return out
    from ipe.imaging import registro_rigido as RR
    if montar is None:
        from ipe.imaging.series import build_frames
        from ipe.imaging.volume import build_volume

        def montar(serie):
            return build_volume(build_frames(repo.instances_for_series(serie), serie), t.cache)
    vb = montar(serie_b)
    tempo = float(config(settings, CHAVE_TEMPO) or 60)
    r = (registrar or RR.registrar)(t.vol, vb, "ncc", tempo_max=tempo,
                                    progresso=lambda *_a: not getattr(t, "cancelado", False))
    out.update(M=np.asarray(r.M, float).tolist(), translacao=[float(x) for x in r.translacao],
               rotacao=float(r.rotacao_total), valor=float(r.valor), qualidade=r.qualidade())
    return out


def preparar(t, res, org: dict, suv: np.ndarray, settings=None) -> Preparo:
    """Chamado no fim da conta da carga tumoral (linha da ferramenta). Nunca derruba a conta."""
    p = Preparo()
    try:
        from ipe.imaging import pet_onco as PO
        sul = (PO.fatores_do_arquivo(res.pet_frames[0].path) or {}).get("sul_razao") if res.pet_frames else None
        p.figado, p.mediastino = referencias(suv, res.pet_vol, org, res.refs.get("figado_ref"), sul)
        if p.figado is None:
            p.avisos.append("referência do fígado não medida")
        if p.mediastino is None:
            p.avisos.append("referência do mediastino não medida")
    except Exception as e:  # noqa: BLE001
        log.exception("sessão preparada: referências")
        p.avisos.append(f"referências: {e}")
    try:
        r = registrar_com_anterior(t, t.repo, settings)
        if r:
            p.anterior_uid, p.anterior_data = r["anterior_uid"], r["anterior_data"]
            if r.get("M") is not None:
                p.valor, p.qualidade, p.rotacao = r["valor"], r["qualidade"], r["rotacao"]
                if r["valor"] >= MIN_NCC:
                    p.M, p.translacao = r["M"], r["translacao"]
                else:
                    p.avisos.append("registro com o anterior fraco: não guardado")
    except InterruptedError:
        p.avisos.append("registro com o anterior interrompido")
    except Exception as e:  # noqa: BLE001
        log.exception("sessão preparada: registro")
        p.avisos.append(f"registro com o anterior: {e}")
    return p


# ------------------------------------------------------------------ gravação (linha principal)
def gravar(repo, study_uid: str, p: Preparo | None) -> dict:
    """Guarda as referências (sem trocar as medidas à mão) e o registro (sem trocar um que já exista).
    Devolve {"refs": [...], "registro": bool}."""
    feito = {"refs": [], "registro": False}
    if p is None:
        return feito
    info = repo.study_info(study_uid) or {}
    pid = str(info.get("patient_id", "") or "")
    if pid and (p.figado or p.mediastino):
        dados = dict((repo.lesion_track(pid) or {}).get("data") or {})
        refs = dict(dados.get("refs") or {})
        do_exame = dict(refs.get(study_uid) or {})
        for tipo, r in (("figado", p.figado), ("mediastino", p.mediastino)):
            atual = do_exame.get(tipo)
            if r and (not atual or atual.get("como") == "auto"):
                do_exame[tipo] = r
                feito["refs"].append(tipo)
        if feito["refs"]:
            refs[study_uid] = do_exame
            dados["refs"] = refs
            repo.save_lesion_track(pid, data=dados)
    if p.M is not None and p.anterior_uid and repo.get_registration(study_uid, p.anterior_uid) is None:
        repo.save_registration(study_uid, p.anterior_uid, p.translacao, 0.0, method="rigido", matriz=np.asarray(p.M))
        feito["registro"] = True
    return feito


def _data(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d or "") == 8 else (d or "")


def texto(p: Preparo | None) -> str:
    """Uma frase inteira (para traduzir de uma vez) para a mensagem da ferramenta; "" se nada foi preparado."""
    if p is None or not (p.feito or p.anterior_uid):
        return ""
    quais = {(True, True): "fígado e mediastino", (True, False): "fígado", (False, True): "mediastino"}.get(
        (bool(p.figado), bool(p.mediastino)), "")
    quando = _data(p.anterior_data)
    if p.M is not None:
        if quais:
            return f"Sessão preparada: referências de {quais}; registrado com o exame de {quando} ({p.qualidade})."
        return f"Sessão preparada: registrado com o exame de {quando} ({p.qualidade})."
    if p.anterior_uid and p.valor is None:
        if quais:
            return f"Sessão preparada: referências de {quais}; o registro com o exame de {quando} já existia."
        return f"Sessão preparada: o registro com o exame de {quando} já existia."
    return f"Sessão preparada: referências de {quais}." if quais else ""


def preparado(repo, study_uid: str) -> bool:
    """O exame tem a carga tumoral feita (é o que marca a sessão como preparada)."""
    try:
        return bool(repo.achados(study_uid, "carga_pet"))
    except Exception:  # noqa: BLE001
        return False
