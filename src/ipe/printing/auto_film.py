"""Montar o filme sozinho quando um exame chega pela rede.

Pensado para o ultrassom, que manda as imagens por C-STORE (e não por impressão): assim que
o exame termina de chegar, o programa monta as imagens num layout que você escolheu e deixa
o filme pronto na lista de impressões — ou já manda para o destino.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ipe.printing.film import Cell, Film, Sheet, pick_frames

log = logging.getLogger(__name__)


@dataclass
class AutoFilm:
    """Regra única de montagem automática (Configurações de impressão → Automático)."""
    enabled: bool = False
    modalities: str = "US"        # separadas por vírgula ("" = qualquer)
    rows: int = 2
    cols: int = 2
    paper: str = "A4"
    max_images: int = 8           # 0 = todas
    destination: str = ""         # "" = só deixa o filme pronto na lista
    template: str = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in AutoFilm.__dataclass_fields__}

    @staticmethod
    def from_dict(d: dict) -> "AutoFilm":
        known = AutoFilm.__dataclass_fields__
        return AutoFilm(**{k: v for k, v in (d or {}).items() if k in known})

    def wants(self, modalidades: str) -> bool:
        if not self.enabled:
            return False
        alvo = [m.strip().upper() for m in (self.modalities or "").split(",") if m.strip()]
        if not alvo:
            return True
        tem = {m.strip().upper() for m in (modalidades or "").split(",") if m.strip()}
        return bool(tem & set(alvo))


def config(settings) -> AutoFilm:
    """A configuração única de antes da 0.86. Continua sendo a **grade padrão** das imagens que
    chegam à porta da impressora sem nenhuma regra que combine."""
    return AutoFilm.from_dict(settings.get("printing.auto_film", {}) or {})


def save(settings, cfg: AutoFilm) -> None:
    settings.set("printing.auto_film", cfg.to_dict())
    settings.save()


# --------------------------------------------------------------------------- regras (0.86)
@dataclass
class AutoRule:
    """Uma regra do filme automático: de quem, por qual AE meu, de que modalidade — e como montar.

    Pedido dele (0.86): *"faça isso agora para a aba automático"* — as mesmas três listas das regras
    de impressão (origem, meu AE que recebeu, modalidade), cada regra com a sua grade e destino.
    Lista vazia = qualquer. A primeira regra ligada que combinar monta o filme (um por exame).
    """
    name: str = "Regra"
    enabled: bool = True
    calling_aes: list = field(default_factory=list)   # AE de quem mandou
    my_aes: list = field(default_factory=list)        # AE meu que foi chamado (nó, identidade, impressora)
    modalities: list = field(default_factory=list)
    description: str = ""                             # descrição do exame contém (aceita * e |)
    rows: int = 2
    cols: int = 2
    paper: str = "A4"
    max_images: int = 8                               # 0 = todas
    destination: str = ""                             # "" = só deixa o filme pronto na lista
    template: str = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in AutoRule.__dataclass_fields__}

    @staticmethod
    def from_dict(d: dict) -> "AutoRule":
        known = AutoRule.__dataclass_fields__
        dados = {k: v for k, v in (d or {}).items() if k in known}
        for k in ("calling_aes", "my_aes", "modalities"):
            v = dados.get(k)
            dados[k] = [str(x).strip().upper() for x in v if str(x).strip()] if isinstance(v, (list, tuple)) else []
        return AutoRule(**dados)

    def as_film_cfg(self) -> AutoFilm:
        return AutoFilm(enabled=True, rows=self.rows, cols=self.cols, paper=self.paper,
                        max_images=self.max_images, destination=self.destination, template=self.template)

    def label_text(self) -> str:
        quando = []
        if self.calling_aes:
            quando.append("de " + ", ".join(self.calling_aes))
        if self.my_aes:
            quando.append("chamando " + ", ".join(self.my_aes))
        if self.modalities:
            quando.append("modalidade " + "|".join(self.modalities))
        if self.description:
            quando.append(f"descrição com {self.description}")
        cond = ", ".join(quando) or "qualquer exame"
        imgs = f"até {self.max_images} imagens" if self.max_images else "todas as imagens"
        depois = self.destination or "fica na lista"
        return f"{self.name}: {cond} → {self.rows}×{self.cols} {self.paper}, {imgs} → {depois}"


CHAVE_REGRAS = "printing.auto_film_rules"


def all_rules(settings) -> list[AutoRule]:
    """As regras. Sem regra gravada ainda, a configuração antiga vira a primeira (a migração não grava:
    só ao salvar a aba é que a lista nova passa a existir)."""
    gravadas = settings.get(CHAVE_REGRAS, None) if settings is not None else None
    if gravadas is not None:
        return [AutoRule.from_dict(d) for d in gravadas or []]
    antiga = config(settings) if settings is not None else AutoFilm()
    if not antiga.enabled and not (settings.get("printing.auto_film", None) if settings is not None else None):
        return []
    mods = [m.strip().upper() for m in (antiga.modalities or "").split(",") if m.strip()]
    return [AutoRule(name="Filme automático", enabled=antiga.enabled, modalities=mods, rows=antiga.rows,
                     cols=antiga.cols, paper=antiga.paper, max_images=antiga.max_images,
                     destination=antiga.destination, template=antiga.template)]


def save_rules(settings, regras: list[AutoRule]) -> None:
    settings.set(CHAVE_REGRAS, [r.to_dict() for r in regras])
    settings.save()


def _lista_mods(modalidades) -> set[str]:
    if isinstance(modalidades, (list, tuple, set)):
        partes = modalidades
    else:
        partes = str(modalidades or "").replace("\\", ",").replace("/", ",").replace("|", ",").split(",")
    return {m.strip().upper() for m in partes if str(m).strip()}


def combina(regra: AutoRule, calling_ae: str = "", my_ae: str = "", modalidades="", descricao: str = "") -> bool:
    if not regra.enabled:
        return False
    if regra.calling_aes and (calling_ae or "").strip().upper() not in regra.calling_aes:
        return False
    if regra.my_aes and (my_ae or "").strip().upper() not in regra.my_aes:
        return False
    if regra.modalities and not (_lista_mods(modalidades) & set(regra.modalities)):
        return False
    if regra.description:
        import fnmatch
        texto = (descricao or "").upper()
        termos = [t.strip().upper() for t in regra.description.split("|") if t.strip()]
        if not any(fnmatch.fnmatch(texto, t if "*" in t or "?" in t else f"*{t}*") for t in termos):
            return False
    return True


def escolher(settings, calling_ae: str = "", my_ae: str = "", modalidades="", descricao: str = "") -> AutoRule | None:
    """A primeira regra ligada que combina (ou None)."""
    for r in all_rules(settings):
        if combina(r, calling_ae, my_ae, modalidades, descricao):
            return r
    return None


def alguma_ligada(settings) -> bool:
    return any(r.enabled for r in all_rules(settings))


def escolhe_imagens(repo, study_uid: str, quantas: int) -> list[tuple[str, str, int]]:
    """(série, SOP, quadro) espalhados pelo exame — poucos e representativos."""
    saida: list[tuple[str, str, int]] = []
    series = repo.series_for_study(study_uid)
    if not series:
        return saida
    por_serie = max(1, (quantas // len(series)) if quantas else 0) if quantas else 0
    for s in series:
        inst = repo.instances_for_series(s.series_uid)
        if not inst:
            continue
        if len(inst) == 1 and int(inst[0].get("frames") or 1) > 1:
            n = int(inst[0]["frames"])
            for k in pick_frames(n, count=por_serie or None):
                saida.append((s.series_uid, inst[0]["sop_uid"], k))
        else:
            for k in pick_frames(len(inst), count=por_serie or None):
                saida.append((s.series_uid, inst[k]["sop_uid"], 0))
    if quantas and len(saida) > quantas:
        passo = len(saida) / quantas
        saida = [saida[int(i * passo)] for i in range(quantas)]
    return saida


def build(repo, study_uid: str, cfg: AutoFilm) -> Film | None:
    """Monta o filme do exame; devolve None quando não há imagem nenhuma."""
    itens = escolhe_imagens(repo, study_uid, int(cfg.max_images or 0))
    if not itens:
        return None
    info = repo.study_info(study_uid) or {}
    nome = info.get("patient_name", "") or "Exame"
    filme = Film(name=f"{nome} — {info.get('description', '') or 'automático'}".strip(" —"),
                 sheets=[Sheet(max(1, int(cfg.rows)), max(1, int(cfg.cols)), cfg.paper or "A4")])
    filme.add_cells([Cell(study_uid, serie, sop, quadro) for serie, sop, quadro in itens])
    return filme


def montar_para_estudo(repo, settings, study_uid: str, remetente: dict | None = None):
    """Monta e salva o filme do exame se alguma regra pedir. Devolve (id do filme, regra) ou (None, None).

    `remetente`: {"calling_ae", "my_ae"} de quem mandou o exame (o nó DICOM anota na chegada)."""
    info = repo.study_info(study_uid) or {}
    rem = remetente or {}
    regra = escolher(settings, rem.get("calling_ae", ""), rem.get("my_ae", ""),
                     info.get("modalities", "") or info.get("modality", ""), info.get("description", ""))
    if regra is None:
        return None, None
    if repo.films(study_uid):
        return None, None                            # já tem filme deste exame: não repete
    filme = build(repo, study_uid, regra.as_film_cfg())
    if filme is None:
        return None, None
    film_id = repo.save_film(filme.name, filme.to_dict(), [study_uid], info.get("patient_name", ""))
    log.info("Filme automático montado para %s pela regra %r (%d imagens)", study_uid, regra.name,
             filme.image_count())
    return film_id, regra


def run_for_study(repo, settings, study_uid: str, remetente: dict | None = None) -> int | None:
    """Monta e salva o filme do exame, se alguma regra pedir. Devolve o id do filme."""
    return montar_para_estudo(repo, settings, study_uid, remetente)[0]


#: multiframe (cine do US, por exemplo) mandado à impressora: no máximo estes quadros, espalhados
QUADROS_POR_ARQUIVO = 16


def films_from_images(repo, imagens, cfg: AutoFilm) -> list[tuple[str, Film]]:
    """Filmes das imagens comuns mandadas à porta da impressão (0.81) — um por exame.

    Diferente do filme automático do US, aqui quem escolheu as imagens foi a modalidade: entram
    **todas**, na ordem em que chegaram, com a grade e o papel da aba Automático.
    `imagens`: [(estudo, série, SOP, quadros)].
    """
    por_estudo: dict[str, list[Cell]] = {}
    for estudo, serie, sop, quadros in imagens or []:
        if not estudo or not sop:
            continue
        n = max(1, int(quadros or 1))
        indices = [0] if n == 1 else pick_frames(n, count=min(n, QUADROS_POR_ARQUIVO))
        por_estudo.setdefault(estudo, []).extend(Cell(estudo, serie, sop, k) for k in indices)
    saida = []
    for estudo, celulas in por_estudo.items():
        info = repo.study_info(estudo) or {}
        nome = info.get("patient_name", "") or "Exame"
        filme = Film(name=f"{nome} — {info.get('description', '') or 'enviado à impressora'}".strip(" —"),
                     sheets=[Sheet(max(1, int(cfg.rows)), max(1, int(cfg.cols)), cfg.paper or "A4")])
        filme.add_cells(celulas)
        saida.append((estudo, filme))
    return saida
