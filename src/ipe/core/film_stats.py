"""Painel de filmes e impressões: as contas (sem Qt).

Pedido dele (19/10/2026): *"crie um dashboard com informações sobre os filmes salvos e impressão.
inclua data de criação, modalidade, usuário, se foi impresso ou não, tempo entre exame, filme e
impressão. % de impressão dos filmes feitos."*

Três tempos por filme, todos em horas:
- **exame → filme**: da data/hora do estudo até o filme ser salvo pela primeira vez;
- **filme → impressão**: do filme salvo até a **última** impressão (é a única hora guardada);
- **exame → impressão**: a soma dos dois, que é o que o paciente sente.

Tempo negativo (relógio do aparelho adiantado, exame com hora errada) não entra nas medianas: é
erro de dado, não um filme feito antes do exame. A tela mostra quantos ficaram de fora.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

SEM_USUARIO = "(não registrado)"     # filmes salvos antes da 0.77, quando o usuário não era gravado
SEM_MODALIDADE = "(sem modalidade)"
#: de onde veio o filme: montado no compositor, ou chegou pronto pela impressora DICOM (0.83)
TIPOS = {"filme": "Compositor", "dicom": "Impressão DICOM"}


def hora_do_exame(study_date: str, study_time: str = "") -> datetime | None:
    """`20261009` + `083015.123` -> datetime. Sem hora, meio-dia não: meia-noite, e a tela diz."""
    d = (study_date or "").strip()
    if len(d) != 8 or not d.isdigit():
        return None
    t = "".join(ch for ch in (study_time or "").split(".")[0] if ch.isdigit())
    t = (t + "000000")[:6] if t else "000000"
    try:
        return datetime.strptime(d + t, "%Y%m%d%H%M%S")
    except ValueError:
        try:
            return datetime.strptime(d, "%Y%m%d")
        except ValueError:
            return None


def _horas(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 3600.0


@dataclass
class Linha:
    """Um filme, já com os três tempos calculados."""
    id: int
    nome: str
    paciente: str
    criado: datetime
    criado_por: str
    modalidades: list[str]
    folhas: int
    imagens: int
    impresso: bool
    impresso_em: datetime | None
    impresso_por: str
    impressoes: int
    destino: str
    exame: datetime | None
    exame_descricao: str
    accession: str
    h_exame_filme: float | None
    h_filme_impressao: float | None
    h_exame_impressao: float | None
    tipo: str = "filme"                 # filme (compositor) | dicom (chegou pronto)
    study_uid: str = ""                 # dicom: o exame criado com as folhas (o duplo clique abre)

    @property
    def origem(self) -> str:
        return TIPOS.get(self.tipo, self.tipo)

    @property
    def modalidade(self) -> str:
        return "/".join(self.modalidades) if self.modalidades else SEM_MODALIDADE


def linhas(rows: list[dict]) -> list[Linha]:
    out = []
    for r in rows:
        criado = r.get("created_at")
        if criado is None:
            continue
        exame = hora_do_exame(r.get("study_date", ""), r.get("study_time", ""))
        imp = r.get("printed_at")
        out.append(Linha(
            id=r["id"], nome=r.get("name", ""), paciente=r.get("patient_name", ""), criado=criado,
            criado_por=r.get("created_by") or SEM_USUARIO, modalidades=list(r.get("modalities") or []),
            folhas=int(r.get("sheets") or 0), imagens=int(r.get("images") or 0),
            impresso=imp is not None, impresso_em=imp,
            impresso_por=r.get("printed_by") or (SEM_USUARIO if imp is not None else ""),
            impressoes=int(r.get("print_count") or (1 if imp else 0)),
            destino=r.get("print_destination") or "", exame=exame,
            exame_descricao=r.get("study_description", ""), accession=r.get("accession", ""),
            h_exame_filme=_horas(exame, criado), h_filme_impressao=_horas(criado, imp),
            h_exame_impressao=_horas(exame, imp), tipo=r.get("tipo") or "filme",
            study_uid=r.get("study_uid") or ""))
    return out


# --------------------------------------------------------------------------- filtro
@dataclass
class Filtro:
    desde: date | None = None
    ate: date | None = None              # inclusive
    modalidade: str = ""                 # "" = todas; casa com qualquer modalidade do filme
    usuario: str = ""                    # "" = todos; quem montou o filme (ou o aparelho que mandou)
    tipo: str = ""                       # "" = todos; filme | dicom

    def aceita(self, l: Linha) -> bool:
        d = l.criado.date()
        if self.desde and d < self.desde:
            return False
        if self.ate and d > self.ate:
            return False
        if self.modalidade:
            mods = l.modalidades or [SEM_MODALIDADE]
            if self.modalidade not in mods:
                return False
        if self.usuario and l.criado_por != self.usuario:
            return False
        if self.tipo and l.tipo != self.tipo:
            return False
        return True


def periodo(chave: str, hoje: date | None = None) -> tuple[date | None, date | None]:
    """Atalhos de período da tela: 'hoje', '7d', '30d', '90d', '12m', 'ano', 'tudo'."""
    hoje = hoje or date.today()
    dias = {"hoje": 0, "7d": 6, "30d": 29, "90d": 89, "12m": 364}
    if chave in dias:
        return hoje - timedelta(days=dias[chave]), hoje
    if chave == "ano":
        return date(hoje.year, 1, 1), hoje
    return None, None


# --------------------------------------------------------------------------- resumo
def _mediana(v: list[float]) -> float | None:
    return statistics.median(v) if v else None


def _p90(v: list[float]) -> float | None:
    if not v:
        return None
    s = sorted(v)
    return s[min(len(s) - 1, int(round(0.9 * (len(s) - 1))))]


@dataclass
class Tempo:
    """Mediana e percentil 90 de um intervalo, com quantos filmes entraram e quantos ficaram fora."""
    mediana: float | None
    p90: float | None
    n: int
    negativos: int


def _tempo(valores: list[float | None]) -> Tempo:
    v = [x for x in valores if x is not None]
    bons = [x for x in v if x >= 0]
    return Tempo(_mediana(bons), _p90(bons), len(bons), len(v) - len(bons))


@dataclass
class Grupo:
    """Uma linha das tabelas por modalidade e por usuário."""
    nome: str
    filmes: int = 0
    impressos: int = 0
    folhas_impressas: int = 0
    reimpressoes: int = 0
    exame_filme: Tempo | None = None
    filme_impressao: Tempo | None = None

    @property
    def pct(self) -> float | None:
        return 100.0 * self.impressos / self.filmes if self.filmes else None


@dataclass
class Resumo:
    filmes: int
    impressos: int
    nao_impressos: int
    folhas: int
    imagens: int
    folhas_impressas: int
    impressoes: int                     # vezes que se imprimiu (conta reimpressões)
    reimpressos: int                    # filmes impressos mais de uma vez
    exame_filme: Tempo
    filme_impressao: Tempo
    exame_impressao: Tempo
    impressos_24h: int                  # impressos em até 24 h do exame
    parados: list[Linha]                # sem impressão há mais de `dias_parado` dias
    por_modalidade: list[Grupo]
    por_usuario: list[Grupo]
    por_mes: list[tuple[str, int, int]] = field(default_factory=list)   # (AAAA-MM, impressos, não)
    por_destino: list[tuple[str, int]] = field(default_factory=list)

    @property
    def pct(self) -> float | None:
        return 100.0 * self.impressos / self.filmes if self.filmes else None


def _agrupa(ls: list[Linha], chave) -> list[Grupo]:
    grupos: dict[str, list[Linha]] = {}
    for l in ls:
        for k in chave(l):
            grupos.setdefault(k, []).append(l)
    out = []
    for nome, g in grupos.items():
        imp = [l for l in g if l.impresso]
        out.append(Grupo(nome, len(g), len(imp), sum(l.folhas for l in imp),
                         sum(1 for l in imp if l.impressoes > 1),
                         _tempo([l.h_exame_filme for l in g]),
                         _tempo([l.h_filme_impressao for l in imp])))
    return sorted(out, key=lambda x: (-x.filmes, x.nome))


def resumo(ls: list[Linha], agora: datetime | None = None, dias_parado: int = 2) -> Resumo:
    agora = agora or datetime.now()
    imp = [l for l in ls if l.impresso]
    meses: dict[str, list[int]] = {}
    for l in ls:
        m = meses.setdefault(l.criado.strftime("%Y-%m"), [0, 0])
        m[0 if l.impresso else 1] += 1
    destinos: dict[str, int] = {}
    for l in imp:
        destinos[l.destino or "(não registrado)"] = destinos.get(l.destino or "(não registrado)", 0) + 1
    limite = agora - timedelta(days=dias_parado)
    parados = sorted((l for l in ls if not l.impresso and l.criado <= limite), key=lambda l: l.criado)
    return Resumo(
        filmes=len(ls), impressos=len(imp), nao_impressos=len(ls) - len(imp),
        folhas=sum(l.folhas for l in ls), imagens=sum(l.imagens for l in ls),
        folhas_impressas=sum(l.folhas for l in imp), impressoes=sum(l.impressoes for l in imp),
        reimpressos=sum(1 for l in imp if l.impressoes > 1),
        exame_filme=_tempo([l.h_exame_filme for l in ls]),
        filme_impressao=_tempo([l.h_filme_impressao for l in imp]),
        exame_impressao=_tempo([l.h_exame_impressao for l in imp]),
        impressos_24h=sum(1 for l in imp if l.h_exame_impressao is not None
                          and 0 <= l.h_exame_impressao <= 24),
        parados=parados,
        por_modalidade=_agrupa(ls, lambda l: l.modalidades or [SEM_MODALIDADE]),
        por_usuario=_agrupa(ls, lambda l: [l.criado_por]),
        por_mes=sorted((k, v[0], v[1]) for k, v in meses.items()),
        por_destino=sorted(destinos.items(), key=lambda kv: -kv[1]),
    )


# --------------------------------------------------------------------------- texto
def duracao(horas: float | None) -> str:
    """Horas para texto curto: 35 min, 5,2 h, 3,1 d. `None` vira travessão."""
    if horas is None:
        return "—"
    if horas < 1:
        return f"{round(horas * 60):.0f} min"
    if horas < 48:
        return f"{horas:.1f} h".replace(".", ",")
    return f"{horas / 24:.1f} d".replace(".", ",")


def porcentagem(p: float | None) -> str:
    return "—" if p is None else f"{p:.0f}%"
