"""Altura, peso e sexo do paciente para as contas que precisam deles (0.99.80).

Pedido dele: *"como eu coloco o peso do paciente? sugiro um popup aparecer quando eu clicar para calcular e
também a opção de acrescentar na tela de achados de IA"*.

O ponto de partida é o arquivo (PatientSize em metros, PatientWeight em kg, PatientSex). O que o médico
digita vale por cima e fica guardado **por exame** (`repo.guardar_biometria`, na configuração do banco `biometria.<StudyInstanceUID>`), de
modo que rodar de novo a IA no mesmo exame usa os mesmos valores. O original não muda.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

PREFIXO = "biometria."
ALTURA = (1.0, 2.3)        # m
PESO = (20.0, 350.0)       # kg
GLICEMIA = (20.0, 800.0)   # mg/dL (0.99.88)
GLICEMIA_REF = 100.0       # o SUV corrigido é normalizado para 100 mg/dL


def _glicemia(v) -> float | None:
    """mg/dL; aceita mmol/L (valor abaixo de 35 vira × 18)."""
    try:
        g = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if 1.0 <= g < 35.0:
        g *= 18.0
    return round(g, 1) if GLICEMIA[0] <= g <= GLICEMIA[1] else None


def fator_glicemia(glicemia_mgdl) -> float | None:
    """SUV corrigido pela glicemia (SUVglic) = SUV × glicemia ÷ 100 mg/dL — a correção linear das diretrizes
    (EANM/PERCIST): a captação de FDG do tumor compete com a glicose do sangue, e um paciente com 160 mg/dL
    tem o SUV subestimado em relação ao mesmo tumor com 100 mg/dL."""
    g = _glicemia(glicemia_mgdl)
    return round(g / GLICEMIA_REF, 4) if g else None


def _altura(v) -> float | None:
    try:
        a = float(v)
    except (TypeError, ValueError):
        return None
    if a > 3:                       # alguns aparelhos gravam em cm
        a /= 100.0
    return a if ALTURA[0] <= a <= ALTURA[1] else None


def _peso(v) -> float | None:
    try:
        p = float(v)
    except (TypeError, ValueError):
        return None
    return p if PESO[0] <= p <= PESO[1] else None


def do_arquivo(path) -> dict:
    """{"altura_m", "peso_kg", "sexo"} do cabeçalho DICOM (None quando falta ou é absurdo)."""
    out = {"altura_m": None, "peso_kg": None, "sexo": ""}
    if not path:
        return out
    try:
        import pydicom
        ds = pydicom.dcmread(str(path), stop_before_pixels=True, force=True,
                             specific_tags=["PatientSize", "PatientWeight", "PatientSex"])
        out["altura_m"] = _altura(ds.get("PatientSize"))
        out["peso_kg"] = _peso(ds.get("PatientWeight"))
        out["sexo"] = str(ds.get("PatientSex", "") or "").upper()[:1]
    except Exception:  # noqa: BLE001
        log.debug("biometria do arquivo", exc_info=True)
    if out["sexo"] not in ("M", "F"):
        out["sexo"] = ""
    return out


def guardado(repo, study_uid: str) -> dict:
    if repo is None or not study_uid:
        return {}
    try:
        v = repo.biometria(study_uid)
    except Exception:  # noqa: BLE001
        return {}
    return v if isinstance(v, dict) else {}


def ler(repo, study_uid: str, path=None) -> dict:
    """O que vale para o exame: o digitado por cima do arquivo. "fonte" diz de onde veio cada valor."""
    arq = do_arquivo(path)
    g = guardado(repo, study_uid)
    out = {"fonte": {}}
    out["glicemia_mgdl"] = _glicemia(g.get("glicemia_mgdl"))   # só digitada: não vem no DICOM
    for k in ("altura_m", "peso_kg", "sexo"):
        if g.get(k) not in (None, ""):
            out[k] = g[k]
            out["fonte"][k] = "digitado"
        else:
            out[k] = arq.get(k)
            out["fonte"][k] = "arquivo" if arq.get(k) not in (None, "") else ""
    return out


_SEM = object()


def guardar(repo, study_uid: str, altura_m=None, peso_kg=None, sexo=None, glicemia_mgdl=_SEM) -> dict:
    v = {"altura_m": _altura(altura_m) if altura_m not in (None, "") else None,
         "peso_kg": _peso(peso_kg) if peso_kg not in (None, "") else None,
         "sexo": (sexo or "").upper()[:1] if (sexo or "").upper()[:1] in ("M", "F") else ""}
    # a glicemia guardada não se perde quando só a altura e o peso são editados (e vice-versa, em glicemia())
    v["glicemia_mgdl"] = (guardado(repo, study_uid).get("glicemia_mgdl") if glicemia_mgdl is _SEM
                          else _glicemia(glicemia_mgdl) if glicemia_mgdl not in (None, "") else None)
    if repo is not None and study_uid:
        repo.guardar_biometria(study_uid, v)
    return v


def glicemia(repo, study_uid: str) -> float | None:
    return _glicemia(guardado(repo, study_uid).get("glicemia_mgdl"))


def guardar_glicemia(repo, study_uid: str, glicemia_mgdl) -> float | None:
    g = dict(guardado(repo, study_uid))
    g["glicemia_mgdl"] = _glicemia(glicemia_mgdl) if glicemia_mgdl not in (None, "", 0) else None
    if repo is not None and study_uid:
        repo.guardar_biometria(study_uid, g)
    return g["glicemia_mgdl"]


def imc(altura_m, peso_kg) -> float | None:
    a, p = _altura(altura_m), _peso(peso_kg)
    if not a or not p:
        return None
    return round(p / a ** 2, 1)
