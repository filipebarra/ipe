"""Lote a partir de planilha (0.100.97) — achar, baixar, rodar IAs, enviar, imprimir e exportar, exame por exame.

Pedido dele (22/11/2026): *"crie uma importação em lote, lendo CSV ou qualquer planilha. na planilha tem que
identificar a coluna (ID, acesso, data...). eu seleciono de qual(is) nós baixar, o que fazer (só importar, rodar
IAs...) e depois enviar para algum nó, imprimir resultados (das IAs), exportar resultados em lote das IAs"*. Tomou o
lugar do lote da mama (0.100.69), que virou um modelo pronto ("Densidade e calcificações da mama").

Para cada linha da planilha:

1. **acha o exame** pela melhor chave da linha — Study UID → nº de acesso → ID + data (com tolerância de dias). Linha
   só com o ID, sem data, não é feita ("linha sem data"). Filtros: modalidade(s) e "descrição contém". Vários exames:
   o de mais imagens, o mais próximo da data ou todos. Nascimento diferente → o exame é de outra pessoa e fica de fora;
2. **de onde**: primeiro o banco do Ipê; se não está, os nós marcados, na ordem — baixa do primeiro que tiver;
3. **o que fazer**, cada um opcional: as IAs escolhidas (a que não serve para o exame pula, com o motivo), a conferência
   do protocolo de RM, enviar a nós (originais, resultados ou ambos), imprimir as séries de conferência, exportar
   (as séries de conferência em PNG/PDF e os DICOM gerados);
4. **apaga** o que veio de fora, se pedido — o que já estava no banco nunca é apagado.

A saída é a planilha original com as colunas do Ipê, uma aba por IA com os números, o Resumo e o LEIA-ME. Com
"anonimizar", os dados do paciente saem da planilha (Caso 0001…) e a correspondência vai para um arquivo à parte.

Pode parar e continuar (o andamento fica em `<saída>.andamento.json`); "simular" só procura e conta; a janela de
horário faz o lote esperar fora dela. Sem Qt e sem rede: quem procura, baixa, roda e grava entra por funções
(`Servicos`) — `automation/lote_ipe.py` liga no Ipê, os testes ligam em dublês.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from ipe.automation.planilha import _sem_acento, gravar_xlsx, para_data, para_id
from ipe.core.i18n import tr

log = logging.getLogger(__name__)

# ====================================================================== colunas da planilha
#: (tipo, nome) — o tipo de cada coluna da planilha de entrada
TIPOS_COLUNA = [
    ("ignorar", "Outra informação (manter)"),
    ("id", "ID do paciente"),
    ("acesso", "Nº de acesso"),
    ("data", "Data do exame"),
    ("uid", "Study Instance UID"),
    ("nascimento", "Data de nascimento"),
    ("nome", "Nome do paciente"),
    ("modalidade", "Modalidade"),
    ("descricao", "Descrição do exame"),
    ("tirar", "Outro dado do paciente (sai da saída anonimizada)"),
]
#: as colunas que identificam o paciente: saem da planilha anonimizada
IDENTIFICAM = ("id", "acesso", "uid", "nascimento", "nome", "tirar")


def adivinhar_colunas(cabecalho: list) -> list[str]:
    """O tipo de cada coluna pelo título (pt, en, es). Cada tipo (menos ignorar/tirar) vai para uma coluna só."""
    nomes = [_sem_acento(str(c or "")).strip() for c in cabecalho]
    regras = [
        ("uid", lambda n: "study instance uid" in n or n in ("studyinstanceuid", "study uid", "uid do exame", "uid")),
        ("acesso", lambda n: "acess" in n or "accession" in n or n in ("acc", "acc no", "acc.", "pedido",
                                                                         "numero do pedido", "n do pedido")),
        ("nascimento", lambda n: "nasc" in n or "birth" in n or n in ("dn", "dob")),
        ("id", lambda n: n in ("id", "patient id", "patientid", "id do paciente", "id paciente", "prontuario",
                               "registro", "pid", "mrn", "id del paciente") or "prontu" in n or "patient id" in n
                          or n.startswith("id ") or n.endswith(" id")),
        ("data", lambda n: ("data" in n or "date" in n or "fecha" in n) and "nasc" not in n and "birth" not in n
                           and "laudo" not in n),
        ("nome", lambda n: n in ("paciente", "nome", "patient", "patient name", "nome do paciente", "nombre",
                                 "nombre del paciente", "name")),
        ("modalidade", lambda n: n in ("modalidade", "modality", "modalidad", "mod")),
        ("descricao", lambda n: n in ("descricao", "descricao do exame", "exame", "study description", "description",
                                      "descripcion", "estudio", "procedimento")),
    ]
    tipos = ["ignorar"] * len(nomes)
    for tipo, teste in regras:
        for i, n in enumerate(nomes):
            if n and tipos[i] == "ignorar" and teste(n):
                tipos[i] = tipo
                break
    return tipos


# ====================================================================== a configuração (e os modelos salvos)
VARIOS = {"mais_imagens": "O de mais imagens", "mais_proximo": "O mais próximo da data", "todos": "Todos"}
ENVIAR = {"originais": "Os originais", "resultados": "Os resultados das IAs", "ambos": "Originais e resultados"}


@dataclass
class Config:
    # planilha
    aba: str = ""
    colunas: list = field(default_factory=list)           # tipo de cada coluna (TIPOS_COLUNA)
    # achar o exame
    tolerancia_dias: int = 0
    modalidades: list = field(default_factory=list)       # vazio = qualquer uma
    descricao_contem: str = ""
    varios: str = "mais_imagens"
    conferir_nascimento: bool = True
    # de onde
    nos: list = field(default_factory=list)               # ids dos nós, na ordem (o banco do Ipê vem sempre antes)
    # o que fazer
    ias: list = field(default_factory=list)               # tipos de IA (lote_ias.IAS)
    refazer_ias: bool = False                             # rodar de novo a IA que o exame já tem
    protocolo_rm: bool = False
    enviar_nos: list = field(default_factory=list)
    enviar_o_que: str = "resultados"
    imprimir: str = ""                                     # "" = não; "dest:<nome>" ou "dicom:<nome>"
    exportar_pasta: str = ""                               # "" = não exportar arquivos (a planilha sai sempre)
    exportar_imagens: str = "png"                          # png | pdf | "" (nenhuma)
    exportar_dicom: bool = False
    apagar_depois: bool = True
    # saída e execução
    anonimizar: bool = False
    janela_de: str = ""                                    # "HH:MM" — vazio = a qualquer hora
    janela_ate: str = ""
    refazer_erros: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Config":
        base = cls()
        for k, v in (d or {}).items():
            if hasattr(base, k):
                setattr(base, k, v)
        return base

    def acoes(self) -> list[str]:
        """O que este lote faz, em palavras (para o diário e o LEIA-ME)."""
        out = [tr("importar")]
        if self.ias:
            out.append(tr("IAs: {}").format(", ".join(self.ias)))
        if self.protocolo_rm:
            out.append(tr("conferir o protocolo de RM"))
        if self.enviar_nos:
            out.append(tr("enviar"))
        if self.imprimir:
            out.append(tr("imprimir"))
        if self.exportar_pasta:
            out.append(tr("exportar"))
        if self.apagar_depois:
            out.append(tr("apagar o que veio de fora"))
        return out


#: modelos que já vêm no Ipê
MODELOS_PRONTOS = {
    "Densidade e calcificações da mama": Config(modalidades=["MG"], varios="mais_imagens",
                                                ias=["densidade", "calc_vascular"], apagar_depois=True),
}
CHAVE_MODELOS = "lote.modelos"


def modelos(settings) -> dict[str, Config]:
    out = dict(MODELOS_PRONTOS)
    try:
        for nome, d in (settings.get(CHAVE_MODELOS, {}) or {}).items():
            out[nome] = Config.from_dict(d)
    except Exception:  # noqa: BLE001
        log.debug("modelos do lote", exc_info=True)
    return out


def salvar_modelo(settings, nome: str, cfg: Config) -> None:
    d = dict(settings.get(CHAVE_MODELOS, {}) or {})
    c = cfg.to_dict()
    c["aba"], c["colunas"] = "", []                  # a planilha muda de um lote para o outro
    d[nome] = c
    settings.set(CHAVE_MODELOS, d)
    try:
        settings.save()
    except Exception:  # noqa: BLE001
        pass


def apagar_modelo(settings, nome: str) -> None:
    d = dict(settings.get(CHAVE_MODELOS, {}) or {})
    d.pop(nome, None)
    settings.set(CHAVE_MODELOS, d)
    try:
        settings.save()
    except Exception:  # noqa: BLE001
        pass


# ====================================================================== as linhas
@dataclass
class Linha:
    n: int                      # índice nos dados (0 = primeira linha depois do cabeçalho)
    pid: str = ""
    acesso: str = ""
    data: str = ""              # AAAAMMDD
    uid: str = ""
    nascimento: str = ""
    nome: str = ""
    modalidade: str = ""
    descricao: str = ""
    caso: str = ""              # "Caso 0001" (na ordem da planilha)

    @property
    def chave(self) -> str:
        h = hashlib.sha1(f"{self.pid}|{self.acesso}|{self.data}|{self.uid}".encode()).hexdigest()[:10]
        return f"{self.n}:{h}"

    def criterio(self, cfg: Config) -> dict | None:
        """Como procurar o exame desta linha — None se a linha não tem chave que sirva."""
        mods = [m.upper() for m in (cfg.modalidades or [])]
        if self.modalidade:
            mods = sorted({m.strip().upper() for m in self.modalidade.replace("\\", "/").split("/") if m.strip()})
        base = {"modalidades": mods, "descricao": (self.descricao or cfg.descricao_contem or "").strip()}
        if self.uid:
            return dict(base, uid=self.uid, pid=self.pid)
        if self.acesso:
            return dict(base, acesso=self.acesso, pid=self.pid)
        if self.pid and self.data:
            d = datetime.strptime(self.data, "%Y%m%d").date()
            tol = max(0, int(cfg.tolerancia_dias or 0))
            return dict(base, pid=self.pid, data_de=(d - timedelta(days=tol)).strftime("%Y%m%d"),
                        data_ate=(d + timedelta(days=tol)).strftime("%Y%m%d"))
        return None


def montar_linhas(dados: list[list], tipos: list[str]) -> list[Linha]:
    """As linhas de dados (sem o cabeçalho) viram `Linha`; as vazias são puladas."""
    idx = {t: i for i, t in enumerate(tipos) if t not in ("ignorar", "tirar")}

    def cel(linha, t):
        i = idx.get(t, -1)
        return linha[i] if 0 <= i < len(linha) else None
    out = []
    for n, linha in enumerate(dados):
        if not any(v not in (None, "") for v in linha):
            continue
        out.append(Linha(n, pid=para_id(cel(linha, "id")), acesso=para_id(cel(linha, "acesso")),
                         data=para_data(cel(linha, "data")), uid=para_id(cel(linha, "uid")),
                         nascimento=para_data(cel(linha, "nascimento")), nome=str(cel(linha, "nome") or "").strip(),
                         modalidade=str(cel(linha, "modalidade") or "").strip(),
                         descricao=str(cel(linha, "descricao") or "").strip()))
    for i, l in enumerate(out, start=1):
        l.caso = f"Caso {i:04d}"
    return out


# ====================================================================== situações
FEITO = "feito"
FEITO_COM_FALHAS = "feito, com falhas"
ACHADO = "achado (simulação)"
SEM_DATA = "linha sem data"
SEM_CHAVE = "linha sem ID, acesso ou UID"
NAO_ACHADO = "não encontrado"
OUTRA_PESSOA = "nascimento não confere"
SEM_DOWNLOAD = "erro ao baixar"
ERRO = "erro"
#: ao retomar, estas não são refeitas (as outras são, se "tentar de novo")
PRONTAS = (FEITO, FEITO_COM_FALHAS, OUTRA_PESSOA, SEM_DATA, SEM_CHAVE)


# ====================================================================== o que o lote precisa do Ipê
@dataclass
class Servicos:
    """Funções (a janela liga no Ipê; os testes, em dublês).

    - `local(criterio)` → exames do banco do Ipê: [{"study_uid", "patient_id", "birth_date", "accession",
      "study_date", "study_time", "description", "modalities", "num_images"}]
    - `no(no_id, criterio)` → o mesmo, de um nó (C-FIND)
    - `tem(study_uid)` → o exame já está no banco do Ipê?
    - `baixar(no_id, exame, parar)` → (deu certo, mensagem)
    - `ias(study_uid, tipos, refazer, parar)` → {tipo: {"situacao", "motivo", "campos": {título: valor},
      "series": [uid das séries de conferência]}}
    - `protocolo(study_uid)` → {título: valor}
    - `enviar(study_uid, no_id, series)` → mensagem (series None = o exame inteiro)
    - `imprimir(study_uid, series, destino, titulo)` → mensagem
    - `exportar(study_uid, series, pasta, nome, formato_imagem, dicom, anonimizar)` → mensagem
    - `apagar(study_uid)`
    - `nome_no(no_id)` → nome para mostrar
    """
    local: callable
    no: callable
    tem: callable
    baixar: callable
    ias: callable
    protocolo: callable
    enviar: callable
    imprimir: callable
    exportar: callable
    apagar: callable
    nome_no: callable = lambda no_id: str(no_id)


@dataclass
class Andamento:
    total: int = 0
    feitos: int = 0
    nesta_rodada: int = 0
    contagem: dict = field(default_factory=dict)
    atual: str = ""                     # "linha 12" — nunca o nome do paciente
    esperando: str = ""                 # "fora da janela de horário (20:00–06:00)"
    inicio: float = 0.0

    def falta_s(self) -> float | None:
        if self.nesta_rodada < 3:
            return None
        por_linha = (time.time() - self.inicio) / self.nesta_rodada
        return por_linha * max(0, self.total - self.feitos)


def em_janela(agora: datetime, de: str, ate: str) -> bool:
    """Dentro da janela de horário? Vazia = sempre. "20:00"–"06:00" atravessa a meia-noite."""
    if not de or not ate:
        return True
    try:
        h1, m1 = (int(x) for x in de.split(":"))
        h2, m2 = (int(x) for x in ate.split(":"))
    except ValueError:
        return True
    a, b, t = h1 * 60 + m1, h2 * 60 + m2, agora.hour * 60 + agora.minute
    if a == b:
        return True
    return a <= t < b if a < b else (t >= a or t < b)


def _data_br(d) -> str:
    d = str(d or "")[:8]
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 and d.isdigit() else (d or "?")


def _mesmo_id(a: str, b: str) -> bool:
    a, b = str(a or "").strip(), str(b or "").strip()
    return a == b or (a.lstrip("0") == b.lstrip("0") and a.lstrip("0") != "")


def _confere_nascimento(da_lista: str, do_exame: str) -> bool:
    a, b = para_data(da_lista), para_data(do_exame)
    return not (a and b and a != b)


def filtrar(exames: list[dict], crit: dict) -> list[dict]:
    """O que o banco ou o nó devolveu, só o que bate de verdade com a linha (o PACS às vezes devolve mais)."""
    out = []
    for e in exames:
        if crit.get("uid") and str(e.get("study_uid") or "") != crit["uid"]:
            continue
        if crit.get("acesso") and str(e.get("accession") or "").strip() != crit["acesso"]:
            continue
        if crit.get("pid") and not crit.get("uid") and not crit.get("acesso") \
                and not _mesmo_id(e.get("patient_id", ""), crit["pid"]):
            continue
        d = str(e.get("study_date") or "")[:8]
        if crit.get("data_de") and d and not (crit["data_de"] <= d <= crit["data_ate"]):
            continue
        mods = crit.get("modalidades") or []
        tem = {m.strip().upper() for m in str(e.get("modalities") or "").replace("\\", "/").split("/") if m.strip()}
        if mods and tem and not (tem & set(mods)):
            continue
        desc = crit.get("descricao") or ""
        if desc and _sem_acento(desc) not in _sem_acento(e.get("description") or ""):
            continue
        out.append(e)
    return out


def escolher(exames: list[dict], como: str, data: str) -> list[dict]:
    if not exames:
        return []
    if como == "todos":
        return sorted(exames, key=lambda e: (str(e.get("study_date") or ""), str(e.get("study_time") or "")))
    if como == "mais_proximo" and data:
        alvo = datetime.strptime(data, "%Y%m%d").date()

        def dist(e):
            try:
                return abs((datetime.strptime(str(e.get("study_date"))[:8], "%Y%m%d").date() - alvo).days)
            except (TypeError, ValueError):
                return 10 ** 6
        return [min(exames, key=lambda e: (dist(e), -int(e.get("num_images") or 0)))]
    return [max(exames, key=lambda e: (int(e.get("num_images") or 0), str(e.get("study_time") or "")))]


# ====================================================================== o lote
class Lote:
    def __init__(self, cabecalho: list, dados: list[list], linhas: list[Linha], cfg: Config, servicos: Servicos,
                 saida, simular: bool = False, limite: int = 0, gravar_a_cada: int = 10) -> None:
        self.cabecalho = [("" if c is None else c) for c in cabecalho]
        self.dados = dados
        self.linhas = linhas
        self.cfg = cfg
        self.s = servicos
        self.saida = Path(saida)
        self.simular = simular
        self.limite = limite
        self.gravar_a_cada = gravar_a_cada
        self.arquivo_andamento = self.saida.with_name(self.saida.name + ".andamento.json")
        self.resultados: dict[str, dict] = {}
        self.titulos_ia: dict[str, str] = {}
        if not simular:
            self.carregar()

    # ------------------------------------------------------------ andamento em disco
    def carregar(self) -> None:
        try:
            d = json.loads(self.arquivo_andamento.read_text(encoding="utf-8"))
            self.resultados = d.get("linhas", {})
            self.titulos_ia = d.get("titulos_ia", {})
        except (OSError, ValueError):
            self.resultados = {}

    def guardar(self) -> None:
        if self.simular:
            return
        tmp = self.arquivo_andamento.with_name(self.arquivo_andamento.name + ".gravando")
        tmp.write_text(json.dumps({"versao": 2, "linhas": self.resultados, "titulos_ia": self.titulos_ia,
                                   "config": self.cfg.to_dict()}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.arquivo_andamento)

    def pronta(self, l: Linha) -> bool:
        r = self.resultados.get(l.chave)
        if not r:
            return False
        return r.get("situacao") in PRONTAS or not self.cfg.refazer_erros

    def por_fazer(self, com_limite: bool = True) -> list[Linha]:
        out = [l for l in self.linhas if not self.pronta(l)]
        return out[:self.limite] if (com_limite and self.limite) else out

    def contagem(self) -> dict:
        c: dict[str, int] = {}
        for l in self.linhas:
            r = self.resultados.get(l.chave)
            if r:
                c[r.get("situacao", ERRO)] = c.get(r.get("situacao", ERRO), 0) + 1
        return c

    # ------------------------------------------------------------ uma linha
    def uma(self, l: Linha, parar=None) -> dict:
        crit = l.criterio(self.cfg)
        if crit is None:
            if (l.pid or l.nome) and not l.data:
                return {"situacao": SEM_DATA, "observacao": tr("Só o ID, sem data: a data é obrigatória.")}
            return {"situacao": SEM_CHAVE}
        exames = filtrar(self.s.local(crit), crit)
        origem = ""
        erros: list[str] = []
        brutos: dict = {}
        if not exames:
            for no in self.cfg.nos:
                if parar is not None and parar.is_set():
                    raise InterruptedError
                try:
                    brutos[no] = self.s.no(no, crit) or []
                    exames = filtrar(brutos[no], crit)
                except Exception as e:  # noqa: BLE001 - um nó fora do ar não para o lote: tenta o próximo
                    log.warning("lote: busca em %s: %s", no, e)
                    erros.append(tr("erro ao buscar em {}: {}").format(self.s.nome_no(no), str(e)[:200]))
                    exames = []
                if exames:
                    origem = no
                    break
        if not exames:
            onde = [tr("banco do Ipê")] + [self.s.nome_no(n) for n in self.cfg.nos]
            obs = [tr("Procurado em: {}.").format(", ".join(onde))] + erros
            obs.append(self._por_que_nao(crit, brutos, parar))
            return {"situacao": NAO_ACHADO, "observacao": " ".join(x for x in obs if x)}
        escolhidos = escolher(exames, self.cfg.varios, l.data)
        r: dict = {"achados": len(exames), "exames": []}
        if len(exames) > 1 and len(escolhidos) == 1:
            r["observacao"] = tr("{} exames batem com a linha: ficou {}.").format(
                len(exames), tr(VARIOS.get(self.cfg.varios, "")).lower())
        for ex in escolhidos:
            if parar is not None and parar.is_set():
                raise InterruptedError
            r["exames"].append(self._um_exame(l, ex, origem, parar))
        sits = [e.get("situacao") for e in r["exames"]]
        if all(s == OUTRA_PESSOA for s in sits):
            r["situacao"] = OUTRA_PESSOA
        elif self.simular:
            r["situacao"] = ACHADO
        elif all(s == SEM_DOWNLOAD for s in sits):
            r["situacao"] = SEM_DOWNLOAD
        elif any(s in (FEITO, FEITO_COM_FALHAS) for s in sits):
            r["situacao"] = FEITO if all(s in (FEITO, OUTRA_PESSOA) for s in sits) else FEITO_COM_FALHAS
        else:
            r["situacao"] = ERRO
        return r

    def _por_que_nao(self, crit: dict, brutos: dict, parar=None) -> str:
        """0.100.98: quando não acha, diz por quê — o nó devolveu exames que o filtro tirou, ou o ID tem exames
        em outras datas (busca de novo só pelo ID, sem data nem modalidade, no primeiro nó)."""
        out = []
        for no, lista in brutos.items():
            if lista:
                ex = lista[0]
                out.append(tr("{} devolveu {} exame(s) que não bateram (ex.: ID {}, {}, {}).").format(
                    self.s.nome_no(no), len(lista), ex.get("patient_id", ""), _data_br(ex.get("study_date", "")),
                    ex.get("modalities", "") or "?"))
        if out or not crit.get("data_de") or not self.cfg.nos or (parar is not None and parar.is_set()):
            return " ".join(out)
        no = self.cfg.nos[0]
        so_id = {"pid": crit["pid"], "modalidades": [], "descricao": ""}
        try:
            outros = filtrar(self.s.no(no, so_id) or [], so_id)
        except Exception as e:  # noqa: BLE001
            return tr("erro ao buscar só pelo ID em {}: {}").format(self.s.nome_no(no), str(e)[:200])
        if not outros:
            return tr("{} não tem nenhum exame com o ID {}.").format(self.s.nome_no(no), crit["pid"])
        alvo = crit["data_de"]

        def dist(e):
            d = str(e.get("study_date") or "")[:8]
            return abs(int(d) - int(alvo)) if d.isdigit() and alvo.isdigit() else 10 ** 9
        perto = sorted(outros, key=dist)[:3]
        return tr("O ID tem {} exame(s) em {}, em outras datas ou modalidades — os mais próximos: {}.").format(
            len(outros), self.s.nome_no(no), "; ".join(f"{_data_br(e.get('study_date', ''))} "
                                                         f"{e.get('modalities', '') or '?'} "
                                                         f"{(e.get('description') or '')[:30]}".strip()
                                                         for e in perto))

    def _um_exame(self, l: Linha, ex: dict, origem: str, parar) -> dict:
        uid = str(ex.get("study_uid") or "")
        e = {"study_uid": uid, "accession": ex.get("accession", ""), "data_exame": ex.get("study_date", ""),
             "descricao": ex.get("description", ""), "modalidades": ex.get("modalities", ""),
             "imagens": ex.get("num_images", None),
             "de_onde": tr("já estava no Ipê") if not origem else self.s.nome_no(origem)}
        if self.cfg.conferir_nascimento and not _confere_nascimento(l.nascimento, ex.get("birth_date", "")):
            return dict(e, situacao=OUTRA_PESSOA,
                        observacao=tr("A data de nascimento do exame achado é outra: não foi baixado nem usado."))
        if self.simular:
            return dict(e, situacao=ACHADO)
        baixou = False
        falhas: list[str] = []
        try:
            if origem and not self.s.tem(uid):
                ok, msg = self.s.baixar(origem, ex, parar)
                if parar is not None and parar.is_set():
                    raise InterruptedError
                if not ok:
                    return dict(e, situacao=SEM_DOWNLOAD, observacao=msg)
                baixou = True
            series_conf: list[str] = []
            if self.cfg.ias:
                res = self.s.ias(uid, list(self.cfg.ias), bool(self.cfg.refazer_ias), parar) or {}
                if parar is not None and parar.is_set():
                    raise InterruptedError
                e["ias"] = {}
                for tipo, x in res.items():
                    if x.get("titulo"):
                        self.titulos_ia[tipo] = x["titulo"]
                    e["ias"][tipo] = {"situacao": x.get("situacao", ""), "motivo": x.get("motivo", ""),
                                      "campos": x.get("campos") or {}}
                    series_conf += [s for s in (x.get("series") or []) if s not in series_conf]
                    if x.get("situacao") == "erro":
                        falhas.append(f"{x.get('titulo') or tipo}: {x.get('motivo', '')}")
                e["series_conferencia"] = series_conf
            if self.cfg.protocolo_rm:
                try:
                    e["protocolo"] = self.s.protocolo(uid) or {}
                except Exception as x:  # noqa: BLE001
                    falhas.append(tr("protocolo: {}").format(x))
            nome = l.caso if self.cfg.anonimizar else (l.pid or l.acesso or uid[-12:])
            nome = f"{nome}_{str(ex.get('study_date') or '')[:8]}".strip("_")
            if self.cfg.enviar_nos:
                msgs = []
                o_que = self.cfg.enviar_o_que
                for no in self.cfg.enviar_nos:
                    try:
                        if o_que in ("originais", "ambos"):
                            msgs.append(self.s.enviar(uid, no, None))
                        if o_que in ("resultados", "ambos") and series_conf:
                            msgs.append(self.s.enviar(uid, no, series_conf))
                    except Exception as x:  # noqa: BLE001
                        falhas.append(tr("envio para {}: {}").format(self.s.nome_no(no), x))
                e["enviado"] = "; ".join(m for m in msgs if m)
            if self.cfg.imprimir:
                if series_conf:
                    try:
                        e["impresso"] = self.s.imprimir(uid, series_conf, self.cfg.imprimir, nome)
                    except Exception as x:  # noqa: BLE001
                        falhas.append(tr("impressão: {}").format(x))
                else:
                    e["impresso"] = tr("sem série de conferência para imprimir")
            if self.cfg.exportar_pasta:
                try:
                    e["exportado"] = self.s.exportar(uid, series_conf, self.cfg.exportar_pasta, nome,
                                                     self.cfg.exportar_imagens, bool(self.cfg.exportar_dicom),
                                                     bool(self.cfg.anonimizar))
                except Exception as x:  # noqa: BLE001
                    falhas.append(tr("exportação: {}").format(x))
            e["situacao"] = FEITO_COM_FALHAS if falhas else FEITO
            if falhas:
                e["observacao"] = "; ".join(falhas)[:500]
            return e
        finally:
            if baixou and self.cfg.apagar_depois and not (parar is not None and parar.is_set()):
                try:
                    self.s.apagar(uid)
                    e["apagado"] = True
                except Exception as x:  # noqa: BLE001
                    log.warning("lote: apagar %s: %s", uid, x)
                    e["observacao"] = " ".join(v for v in (e.get("observacao", ""),
                                                           tr("Não foi possível apagar o exame do Ipê.")) if v)

    # ------------------------------------------------------------ o lote inteiro
    def rodar(self, parar=None, avisar=None, agora=datetime.now) -> Andamento:
        """Faz as linhas que faltam, uma por vez. `avisar(andamento, linha, resultado)` a cada linha (e a cada
        meio minuto fora da janela de horário). Para em `parar` (threading.Event) no fim da linha em curso."""
        fila = self.por_fazer()
        a = Andamento(total=len(self.linhas), inicio=time.time())
        a.feitos = a.total - len(self.por_fazer(com_limite=False))
        a.contagem = self.contagem()
        desde_gravar = 0
        try:
            for l in fila:
                while not self.simular and not em_janela(agora(), self.cfg.janela_de, self.cfg.janela_ate):
                    a.esperando = tr("fora da janela de horário ({}–{})").format(self.cfg.janela_de,
                                                                                 self.cfg.janela_ate)
                    if avisar is not None:
                        avisar(a, None, None)
                    if parar is None:
                        time.sleep(30)
                    elif parar.wait(30):
                        break
                a.esperando = ""
                if parar is not None and parar.is_set():
                    break
                a.atual = tr("linha {}").format(l.n + 2)
                try:
                    r = self.uma(l, parar)
                except InterruptedError:
                    break
                except Exception as e:  # noqa: BLE001 - uma linha ruim não para o lote
                    log.exception("lote: linha %s", l.n + 2)
                    r = {"situacao": ERRO, "observacao": str(e)[:300]}
                self.resultados[l.chave] = r
                a.feitos += 1
                a.nesta_rodada += 1
                a.contagem = self.contagem()
                desde_gravar += 1
                self.guardar()
                if not self.simular and desde_gravar >= max(1, self.gravar_a_cada):
                    self.gravar_planilha()
                    desde_gravar = 0
                if avisar is not None:
                    try:
                        avisar(a, l, r)
                    except Exception:  # noqa: BLE001
                        log.debug("lote: aviso", exc_info=True)
        finally:
            a.atual = ""
            self.guardar()
            if not self.simular:
                self.gravar_planilha()
        return a

    # ------------------------------------------------------------ a planilha de saída
    def _cols_originais(self) -> list[int]:
        largura = max([len(self.cabecalho)] + [len(x) for x in self.dados]) if self.dados else len(self.cabecalho)
        tipos = list(self.cfg.colunas) + ["ignorar"] * largura
        if not self.cfg.anonimizar:
            return list(range(largura))
        return [i for i in range(largura) if tipos[i] not in IDENTIFICAM]

    COLUNAS = [("situacao", "Ipê: situação"), ("observacao", "Ipê: observação"), ("exame", "Ipê: exame"),
               ("study_uid", "Ipê: Study UID"), ("accession", "Ipê: nº de acesso"),
               ("data_exame", "Ipê: data do exame"), ("descricao", "Ipê: descrição do exame"),
               ("modalidades", "Ipê: modalidades"), ("imagens", "Ipê: imagens"), ("de_onde", "Ipê: de onde veio"),
               ("ias", "Ipê: IAs"), ("protocolo", "Ipê: protocolo de RM"), ("enviado", "Ipê: enviado"),
               ("impresso", "Ipê: impresso"), ("exportado", "Ipê: exportado")]
    _SO_SEM_ANONIMIZAR = ("study_uid", "accession")

    def _colunas_ipe(self) -> list[tuple[str, str]]:
        return [(k, t) for k, t in self.COLUNAS if not (self.cfg.anonimizar and k in self._SO_SEM_ANONIMIZAR)]

    def _texto_ias(self, e: dict) -> str:
        partes = []
        for tipo, x in (e.get("ias") or {}).items():
            t = tr(self.titulos_ia.get(tipo, tipo))
            s = tr(x.get("situacao", ""))
            partes.append(f"{t}: {s}" + (f" ({x['motivo']})" if x.get("motivo") else ""))
        return "; ".join(partes)

    def _texto_protocolo(self, e: dict) -> str:
        p = e.get("protocolo")
        if not p:
            return ""
        return "; ".join(f"{k}: {v}" for k, v in p.items() if v not in (None, ""))

    def tabela(self) -> list[list]:
        cols = self._cols_originais()
        cab = ([tr("Caso")] if self.cfg.anonimizar else []) + [self.cabecalho[i] if i < len(self.cabecalho) else ""
                                                               for i in cols]
        cab += [tr(t) for _k, t in self._colunas_ipe()]
        out = [cab]
        por_n = {l.n: l for l in self.linhas}
        for n, linha in enumerate(self.dados):
            l = por_n.get(n)
            if l is None:
                continue
            orig = ([l.caso] if self.cfg.anonimizar else []) + [linha[i] if i < len(linha) else None for i in cols]
            r = self.resultados.get(l.chave) or {}
            exames = r.get("exames") or [{}]
            for k, e in enumerate(exames, start=1):
                vals = {"situacao": tr(e.get("situacao") or r.get("situacao") or ""),
                        "observacao": " ".join(x for x in (r.get("observacao", "") if k == 1 else "",
                                                          e.get("observacao", "")) if x),
                        "exame": f"{k}/{len(exames)}" if e else "",
                        "study_uid": e.get("study_uid", ""), "accession": e.get("accession", ""),
                        "data_exame": e.get("data_exame", ""), "descricao": e.get("descricao", ""),
                        "modalidades": e.get("modalidades", ""), "imagens": e.get("imagens"),
                        "de_onde": e.get("de_onde", ""), "ias": self._texto_ias(e),
                        "protocolo": self._texto_protocolo(e), "enviado": e.get("enviado", ""),
                        "impresso": e.get("impresso", ""), "exportado": e.get("exportado", "")}
                if not r:
                    vals = {}
                out.append(orig + [vals.get(k2) for k2, _t in self._colunas_ipe()])
        return out

    def abas_ia(self) -> list[tuple[str, list[list]]]:
        """Uma aba por IA: uma linha por exame, as colunas são os números que a IA deu."""
        abas: list[tuple[str, list[list]]] = []
        tipos = list(self.cfg.ias)
        if self.cfg.protocolo_rm:
            tipos.append("_protocolo")
        por_n = {l.n: l for l in self.linhas}
        for tipo in tipos:
            campos: list[str] = []
            linhas = []
            for n in sorted(por_n):
                l = por_n[n]
                r = self.resultados.get(l.chave) or {}
                for e in r.get("exames") or []:
                    if tipo == "_protocolo":
                        if "protocolo" not in e:
                            continue
                        x = {"situacao": "feita", "motivo": "", "campos": e["protocolo"]}
                    else:
                        x = (e.get("ias") or {}).get(tipo)
                        if x is None:
                            continue
                    for c in x.get("campos") or {}:
                        if c not in campos:
                            campos.append(c)
                    linhas.append((l, e, x))
            if not linhas:
                continue
            ident = [tr("Caso")] if self.cfg.anonimizar else [tr("Linha"), tr("ID do paciente"), tr("Study UID")]
            cab = ident + [tr("Data do exame"), tr("Situação"), tr("Motivo")] + [tr(c) for c in campos]
            dados = [cab]
            for l, e, x in linhas:
                idv = [l.caso] if self.cfg.anonimizar else [l.n + 2, l.pid, e.get("study_uid", "")]
                dados.append(idv + [e.get("data_exame", ""), tr(x.get("situacao", "")), x.get("motivo", "")]
                             + [(x.get("campos") or {}).get(c) for c in campos])
            titulo = tr("Protocolo de RM") if tipo == "_protocolo" else tr(self.titulos_ia.get(tipo, tipo))
            abas.append((f"IA · {titulo}"[:31], dados))
        return abas

    def resumo(self) -> list[list]:
        c = self.contagem()
        linhas = [[tr("Resumo do lote"), ""], [tr("Linhas na planilha"), len(self.linhas)],
                  [tr("Com resposta"), sum(c.values())]]
        linhas += [[tr(k), v] for k, v in sorted(c.items(), key=lambda kv: -kv[1])]
        ias: dict[str, dict[str, int]] = {}
        for l in self.linhas:
            for e in (self.resultados.get(l.chave) or {}).get("exames") or []:
                for tipo, x in (e.get("ias") or {}).items():
                    d = ias.setdefault(tipo, {})
                    d[x.get("situacao", "")] = d.get(x.get("situacao", ""), 0) + 1
        for tipo, d in ias.items():
            linhas += [["", ""], [tr(self.titulos_ia.get(tipo, tipo)), ""]]
            linhas += [[tr(k), v] for k, v in sorted(d.items(), key=lambda kv: -kv[1])]
        linhas += [["", ""], [tr("Gravado em"), time.strftime("%d/%m/%Y %H:%M")]]
        return linhas

    def leia_me(self) -> list[list]:
        t = [
            tr("Lote a partir de planilha — Ipê (não destinado a uso diagnóstico)."),
            "",
            tr("O que este lote fez: {}.").format(", ".join(self.cfg.acoes())),
            tr("Resultados: uma linha por exame (uma linha da planilha pode ter mais de um exame, com \"Todos\")."),
            tr("Abas \"IA · …\": os números de cada IA, sem confirmação de um médico — confira uma amostra antes de "
               "usar na análise."),
            tr("Situação: feito; feito, com falhas; não encontrado; nascimento não confere (o exame achado é de "
               "outra pessoa e não foi usado); erro ao baixar; linha sem data; erro."),
        ]
        if self.cfg.anonimizar:
            t.append(tr("Planilha anonimizada: os dados do paciente saíram; a correspondência Caso → paciente está "
                        "no arquivo \"-chave\", que não deve sair da instituição."))
        return [[x] for x in t]

    def chave_anonimizacao(self) -> list[list]:
        out = [[tr("Caso"), tr("Linha"), tr("ID do paciente"), tr("Nome"), tr("Nascimento"), tr("Nº de acesso"),
                tr("Study UID"), tr("Data do exame")]]
        for l in self.linhas:
            exames = (self.resultados.get(l.chave) or {}).get("exames") or [{}]
            for e in exames:
                out.append([l.caso, l.n + 2, l.pid, l.nome, l.nascimento, e.get("accession") or l.acesso,
                            e.get("study_uid") or l.uid, e.get("data_exame") or l.data])
        return out

    @property
    def arquivo_chave(self) -> Path:
        return self.saida.with_name(self.saida.stem + "-chave" + self.saida.suffix)

    def gravar_planilha(self) -> Path:
        gravar_xlsx(self.saida, [(tr("Resultados"), self.tabela())] + self.abas_ia()
                    + [(tr("Resumo"), self.resumo()), ("LEIA-ME", self.leia_me())])
        if self.cfg.anonimizar:
            gravar_xlsx(self.arquivo_chave, [(tr("Chave"), self.chave_anonimizacao())])
        return self.saida

