"""Perfis de ocultação dos dados do paciente na tela (0.99.42; pesquisa de visualizadores, item 7 — Weasis).

Até a 0.99.41, "Ocultar dados do paciente" tinha um jeito só: tudo some e fica "Paciente oculto". Para
aula e para artigo isso tira coisa demais (o intervalo entre os exames, o sexo, a idade) ou de menos
(a data real do exame). Agora há perfis:

| Perfil | Nome | ID | Nascimento | Sexo / idade | Datas | Instituição, acesso, médico | Aparelho |
|---|---|---|---|---|---|---|---|
| **Ocultar tudo** (o de antes) | "Paciente oculto" | — | — | — | — | — | mostra |
| **Tela** | pseudônimo | pseudônimo | — | mostra | mostra | — | mostra |
| **Ensino** | pseudônimo | — | — | mostra | **deslocadas** | — | mostra |
| **Publicação** | "Paciente" | — | — | mostra | — | — | — |

- **Pseudônimo**: `PACIENTE-` + 6 caracteres, o mesmo para o mesmo paciente durante a sessão, nunca gravado
  em disco (o segredo é sorteado a cada vez que o programa abre).
- **Datas deslocadas**: todas as datas do mesmo paciente andam para trás o mesmo número de dias (30 a 329,
  sorteado por paciente na sessão) — o intervalo entre o atual e o anterior continua o mesmo.

Ocultar na tela **não muda os arquivos**: o que sai do programa passa pela anonimização da exportação.

Sem Qt.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, timedelta

PERFIS = {
    "oculto": "Ocultar tudo",
    "tela": "Tela (pseudônimo)",
    "ensino": "Ensino (datas deslocadas)",
    "publicacao": "Publicação (sem datas)",
}
PADRAO = "oculto"
CHAVE = "privacidade.perfil"
SELOS = {"oculto": "🔒 Dados ocultos", "tela": "🔒 Tela", "ensino": "🔒 Ensino", "publicacao": "🔒 Publicação"}

#: o que cada perfil faz com cada campo: mostrar | vazio | pseudonimo | deslocar | rotulo
REGRAS = {
    "oculto": {"nome": "rotulo", "id": "vazio", "nascimento": "vazio", "sexo": "vazio", "idade": "vazio",
               "datas": "vazio", "instituicao": "vazio", "acesso": "vazio", "medico": "vazio", "aparelho": "mostrar"},
    "tela": {"nome": "pseudonimo", "id": "pseudonimo", "nascimento": "vazio", "sexo": "mostrar",
             "idade": "mostrar", "datas": "mostrar", "instituicao": "vazio", "acesso": "vazio", "medico": "vazio",
             "aparelho": "mostrar"},
    "ensino": {"nome": "pseudonimo", "id": "vazio", "nascimento": "vazio", "sexo": "mostrar", "idade": "mostrar",
               "datas": "deslocar", "instituicao": "vazio", "acesso": "vazio", "medico": "vazio",
               "aparelho": "mostrar"},
    "publicacao": {"nome": "publicacao", "id": "vazio", "nascimento": "vazio", "sexo": "mostrar",
                   "idade": "mostrar", "datas": "vazio", "instituicao": "vazio", "acesso": "vazio",
                   "medico": "vazio", "aparelho": "vazio"},
}
#: campo do study_info -> regra
CAMPOS = {"patient_name": "nome", "patient_id": "id", "birth_date": "nascimento", "sex": "sexo",
          "patient_age": "idade", "study_date": "datas", "study_time": "datas", "institution": "instituicao",
          "accession": "acesso", "referring": "medico", "operators": "medico", "station": "aparelho",
          "manufacturer": "aparelho", "model": "aparelho"}

_SEGREDO = secrets.token_hex(16)


def normalizar(perfil: str | None) -> str:
    return perfil if perfil in PERFIS else PADRAO


def perfil_de(settings) -> str:
    try:
        return normalizar(settings.get(CHAVE, PADRAO) if settings is not None else PADRAO)
    except Exception:  # noqa: BLE001
        return PADRAO


def _h(*partes) -> str:
    return hashlib.sha256(("|".join([_SEGREDO, *map(str, partes)])).encode("utf-8")).hexdigest()


def chave_do_paciente(info: dict) -> str:
    return str(info.get("patient_id") or info.get("patient_name") or "")


def pseudonimo(chave: str) -> str:
    return "PACIENTE-" + _h("p", chave)[:6].upper()


def dias_de_deslocamento(chave: str) -> int:
    """30 a 329 dias, o mesmo para o mesmo paciente na sessão."""
    return 30 + int(_h("d", chave)[:8], 16) % 300


def deslocar_data(aaaammdd: str, dias: int) -> str:
    """Data DICOM (AAAAMMDD) andando `dias` para trás; vazia ou ilegível fica vazia."""
    s = str(aaaammdd or "").strip()[:8]
    if len(s) != 8 or not s.isdigit():
        return ""
    try:
        d = date(int(s[:4]), int(s[4:6]), int(s[6:8])) - timedelta(days=int(dias))
    except ValueError:
        return ""
    return d.strftime("%Y%m%d")


def mascarar_info(info: dict | None, perfil: str, rotulo: str = "") -> dict:
    """Cópia do study_info com cada campo tratado pelo perfil. `rotulo`: o nome do caso (reunião)."""
    info = dict(info or {})
    regras = REGRAS[normalizar(perfil)]
    chave = chave_do_paciente(info)
    out = dict(info)
    for campo, tipo in CAMPOS.items():
        if campo not in info:
            continue
        acao = regras[tipo]
        v = info.get(campo, "")
        if acao == "mostrar":
            continue
        if acao == "vazio":
            out[campo] = ""
        elif acao == "rotulo":
            out[campo] = rotulo or "Paciente oculto"
        elif acao == "publicacao":
            out[campo] = rotulo or "Paciente"
        elif acao == "pseudonimo":
            out[campo] = rotulo if (rotulo and campo == "patient_name") else pseudonimo(chave) + \
                ("" if campo == "patient_name" else "-ID")
        elif acao == "deslocar":
            out[campo] = deslocar_data(v, dias_de_deslocamento(chave)) if campo == "study_date" else v
    return out


def selo(perfil: str) -> str:
    return SELOS[normalizar(perfil)]
