"""Regras de encaminhamento: o que fazer com cada trabalho que chega.

As regras são olhadas na ordem. A primeira que combinar manda o trabalho para o destino
dela; se ela disser "continuar", as seguintes também são olhadas (dá para gravar um PDF
e imprimir no filme de uma vez). Sem nenhuma regra, o trabalho fica esperando na lista.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field


@dataclass
class Rule:
    name: str = "Regra"
    enabled: bool = True
    server: str = ""            # nome do servidor de impressão ("" = qualquer)
    origin: str = ""            # origem cadastrada (id de printing.origins); "" = qualquer
    calling_ae: str = ""        # AE de origem, aceita * (ex.: "MG*") — alternativa à origem
    label: str = ""             # texto no rótulo da sessão, aceita *
    modality: str = ""          # 0.84: modalidade do exame ("MG", "MG|US", "C*"); "" = qualquer
    film_size: str = ""         # ex.: 14INX17IN ("" = qualquer)
    min_sheets: int = 0         # a partir de quantas folhas
    max_sheets: int = 0         # 0 = sem limite
    hour_from: int = 0          # faixa de horário (iguais = o dia todo)
    hour_to: int = 0
    destination: str = ""       # nome do destino
    template: str = ""          # modelo de folha ("" = o do servidor, ou como veio)
    stop: bool = True           # parar nas regras seguintes
    # 0.85: escolha por listas (nenhum marcado = qualquer). Os campos de um valor só acima continuam
    # valendo para regras antigas e para as "outras condições"; quando os dois existem, valem os dois.
    calling_aes: list = field(default_factory=list)   # AE title de quem mandou (exato)
    servers: list = field(default_factory=list)       # meu servidor que recebeu (nome)
    modalities: list = field(default_factory=list)    # MG, CT…

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in Rule.__dataclass_fields__}

    @staticmethod
    def from_dict(d: dict) -> "Rule":
        known = Rule.__dataclass_fields__
        dados = {k: v for k, v in (d or {}).items() if k in known}
        for k in ("calling_aes", "servers", "modalities"):
            v = dados.get(k)
            dados[k] = [str(x) for x in v if str(x).strip()] if isinstance(v, (list, tuple)) else []
        return Rule(**dados)

    # ---------------------------------------------------------------- o que a regra pede (0.85)
    def aes(self) -> list[str]:
        return [a.strip().upper() for a in self.calling_aes if str(a).strip()]

    def servidores(self) -> list[str]:
        out = [s for s in self.servers if s]
        if self.server and self.server not in out:
            out.append(self.server)
        return out

    def modalidades(self) -> list[str]:
        out = [m.strip().upper() for m in self.modalities if str(m).strip()]
        for m in (self.modality or "").replace(",", "|").split("|"):
            if m.strip() and m.strip().upper() not in out:
                out.append(m.strip().upper())
        return out

    def label_text(self, origin_name: str = "") -> str:
        quando = []
        if self.aes():
            quando.append("de " + ", ".join(self.aes()))
        if self.servidores():
            quando.append("recebido em " + ", ".join(self.servidores()))
        if self.origin:
            quando.append(f"da origem {origin_name or self.origin}")
        if self.calling_ae:
            quando.append(f"do AE {self.calling_ae}")
        if self.modalidades():
            quando.append("modalidade " + "|".join(self.modalidades()))
        if self.label:
            quando.append(f"rótulo com {self.label}")
        if self.film_size:
            quando.append(f"filme de {self.film_size}")
        if self.min_sheets:
            quando.append(f"{self.min_sheets}+ folhas")
        if self.max_sheets:
            quando.append(f"até {self.max_sheets} folhas")
        if self.hour_from != self.hour_to:
            quando.append(f"das {self.hour_from}h às {self.hour_to}h")
        cond = ", ".join(quando) or "qualquer trabalho"
        return f"{self.name}: {cond} → {self.destination or '(sem destino)'}"


def _combina(padrao: str, valor: str) -> bool:
    if not padrao:
        return True
    return fnmatch.fnmatch((valor or "").upper(), padrao.upper())


def _na_faixa(hora: int, de: int, ate: int) -> bool:
    if de == ate:
        return True
    if de < ate:
        return de <= hora < ate
    return hora >= de or hora < ate          # faixa que vira a noite (ex.: 19h às 7h)


def matches(rule: Rule, job, server_name: str = "", origin_id: str = "", modality: str | None = None) -> bool:
    """A regra vale para este trabalho?

    `origin_id` é a origem cadastrada de quem mandou. Regra presa a uma origem só combina com
    aquela origem — é o que permite encaminhar por aparelho em vez de por padrão de texto.
    `modality`: a do exame (ver printing.modalidade); sem ela, vale a que o trabalho guardou.
    Regra com modalidade não combina com trabalho de modalidade desconhecida.
    """
    if not rule.enabled:
        return False
    if rule.servidores() and server_name not in rule.servidores():
        return False
    if rule.aes() and (getattr(job, "calling_ae", "") or "").strip().upper() not in rule.aes():
        return False
    if rule.origin and rule.origin != origin_id:
        return False
    if rule.modalidades():
        from ipe.printing.modalidade import combina
        mod = modality if modality is not None else getattr(job, "modality", "")
        if not combina("|".join(rule.modalidades()), mod):
            return False
    if not _combina(rule.calling_ae, getattr(job, "calling_ae", "")):
        return False
    if not _combina(rule.label, getattr(job, "label", "")):
        return False
    if rule.film_size and rule.film_size.upper() != (getattr(job, "film_size", "") or "").upper():
        return False
    folhas = int(getattr(job, "sheets", 0) or 0)
    if rule.min_sheets and folhas < rule.min_sheets:
        return False
    if rule.max_sheets and folhas > rule.max_sheets:
        return False
    return _na_faixa(job.when().hour, int(rule.hour_from), int(rule.hour_to))


def all_rules(settings) -> list[Rule]:
    return [Rule.from_dict(d) for d in (settings.get("printing.rules", []) or [])]


def save_rules(settings, rules: list[Rule]) -> None:
    settings.set("printing.rules", [r.to_dict() for r in rules])
    settings.save()


def choose(settings, job, server_name: str = "", origin_id: str = "",
           modality: str | None = None) -> list[tuple[str, str]]:
    """Destinos para este trabalho, na ordem: [(nome do destino, modelo de folha)]."""
    saida: list[tuple[str, str]] = []
    for r in all_rules(settings):
        if not matches(r, job, server_name, origin_id, modality):
            continue
        if r.destination:
            saida.append((r.destination, r.template))
        if r.stop:
            break
    return saida
