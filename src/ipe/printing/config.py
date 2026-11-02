"""Configuração da impressão: os servidores de impressora DICOM deste computador.

Dá para ter mais de um — por exemplo, um AE/porta para a mamografia e outro para a TC,
cada um com o seu destino e a sua pasta no banco.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_AE = "DICOMPRINT"
DEFAULT_PORT = 11113


@dataclass
class ServerConfig:
    """Um servidor de impressão (uma "impressora" que as modalidades enxergam na rede)."""
    name: str = "Impressora do programa"
    enabled: bool = False
    ae_title: str = DEFAULT_AE
    port: int = DEFAULT_PORT
    accept: str = "rede"             # rede = qualquer AE da rede local (0.99.24); any = de qualquer lugar;
    #                                  known = só nós cadastrados
    timeout: int = 60
    to_database: bool = True         # a folha recebida também vira exame no banco
    auto_destination: str = ""       # destino fixo ("" = usa as regras; nenhuma regra = segura)
    template: str = ""               # modelo de folha aplicado ao encaminhar ("" = como veio)
    keep_days: int = 0               # 0 = guardar para sempre

    def to_dict(self) -> dict:
        return {"name": self.name, "enabled": self.enabled, "ae_title": self.ae_title,
                "port": self.port, "accept": self.accept, "timeout": self.timeout,
                "to_database": self.to_database, "auto_destination": self.auto_destination,
                "template": self.template, "keep_days": self.keep_days}

    @staticmethod
    def from_dict(d: dict) -> "ServerConfig":
        known = ServerConfig.__dataclass_fields__
        return ServerConfig(**{k: v for k, v in (d or {}).items() if k in known})

    def label(self) -> str:
        estado = "ligado" if self.enabled else "desligado"
        return f"{self.name} — AE {self.ae_title}, porta {self.port} ({estado})"


def all_servers(settings) -> list[ServerConfig]:
    """Os servidores cadastrados. Bancos antigos (um servidor só) viram uma lista de um."""
    bruto = settings.get("print_scp", {}) or {}
    lista = bruto.get("servers")
    if lista is None:
        antigo = ServerConfig(
            name="Impressora do programa", enabled=bool(bruto.get("enabled", False)),
            ae_title=bruto.get("ae_title", DEFAULT_AE), port=int(bruto.get("port", DEFAULT_PORT)),
            accept=bruto.get("accept", "any"), timeout=int(bruto.get("timeout", 60)),
            to_database=bool(bruto.get("to_database", True)),
            auto_destination=bruto.get("auto_destination", ""),
            keep_days=int(bruto.get("keep_days", 0)))
        return [antigo]
    return [ServerConfig.from_dict(d) for d in lista]


def save_servers(settings, servers: list[ServerConfig]) -> None:
    bruto = dict(settings.get("print_scp", {}) or {})
    bruto["servers"] = [s.to_dict() for s in servers]
    settings.set("print_scp", bruto)
    settings.save()


def find_server(settings, name: str) -> ServerConfig | None:
    for s in all_servers(settings):
        if s.name == name:
            return s
    return None


def next_free_port(servers: list[ServerConfig]) -> int:
    usadas = {s.port for s in servers}
    porta = DEFAULT_PORT
    while porta in usadas:
        porta += 1
    return porta
