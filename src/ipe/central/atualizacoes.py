"""Atualização dos clientes pelo servidor central (0.99.56, onda B1 do plano ViewerHub/Eden).

O administrador publica no servidor o pacote de uma versão (de preferência o **instalador do Windows**,
``Ipe-setup-x.y.z.exe``) num de dois **canais**:

- **teste** — vai primeiro para os computadores e as pessoas dos perfis marcados "teste" (core/perfis.py);
- **estável** — vai para todos. **Promover** copia o que está no teste para o estável.

Ao entrar no modo cliente, o programa pergunta ao servidor qual a versão do seu canal; se for mais nova que
a dele, oferece atualizar: baixa, confere o SHA-256 e, sendo o instalador do Windows, fecha o programa e
roda o instalador sem perguntas (``/SILENT``). Outro tipo de pacote (zip, tgz) é baixado e a pasta aberta,
para instalar à mão. Nada é instalado sem o "sim" de quem está no computador.

Os pacotes ficam na pasta ``Atualizacoes`` ao lado da pasta das imagens do servidor; cada canal tem um
``<canal>.json`` com a versão, o nome, o SHA-256, o tamanho, as notas, quando e quem publicou.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

CANAIS = ("estavel", "teste")
_VERSAO = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def versao_tupla(v: str) -> tuple[int, ...]:
    m = _VERSAO.search(str(v or ""))
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def mais_nova(candidata: str, atual: str) -> bool:
    return versao_tupla(candidata) > versao_tupla(atual)


def versao_do_nome(nome: str) -> str:
    m = _VERSAO.search(str(nome or ""))
    return ".".join(m.groups()) if m else ""


def sha256_de(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


class Atualizacoes:
    """A pasta dos pacotes no servidor."""

    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)

    def _meta(self, canal: str) -> Path:
        if canal not in CANAIS:
            raise ValueError(f"canal desconhecido: {canal}")
        return self.pasta / f"{canal}.json"

    def info(self, canal: str) -> dict | None:
        p = self._meta(canal)
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return d if (self.pasta / canal / d.get("nome", "")).exists() else None

    def todas(self) -> dict:
        return {c: self.info(c) for c in CANAIS}

    def caminho(self, canal: str) -> Path | None:
        d = self.info(canal)
        return (self.pasta / canal / d["nome"]) if d else None

    def publicar(self, origem: Path, nome: str, versao: str = "", canal: str = "teste", notas: str = "",
                 por: str = "") -> dict:
        self._meta(canal)
        nome = Path(nome or origem.name).name
        if not nome or nome.startswith("."):
            raise ValueError("nome de pacote inválido")
        versao = versao or versao_do_nome(nome)
        if not versao:
            raise ValueError("não achei a versão (x.y.z) no nome do pacote: informe a versão")
        dest = self.pasta / canal
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        alvo = dest / nome
        shutil.copyfile(origem, alvo)
        d = {"canal": canal, "versao": versao, "nome": nome, "sha256": sha256_de(alvo),
             "tamanho": alvo.stat().st_size, "notas": notas or "", "por": por or "",
             "publicado_em": datetime.now().strftime("%Y-%m-%d %H:%M")}
        self._meta(canal).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("atualização %s publicada no canal %s por %s", versao, canal, por)
        return d

    def promover(self, por: str = "") -> dict:
        """O que está no teste vai também para o estável."""
        d, p = self.info("teste"), self.caminho("teste")
        if not d or p is None:
            raise ValueError("não há pacote no canal de teste")
        return self.publicar(p, d["nome"], d["versao"], "estavel", d.get("notas", ""), por or d.get("por", ""))

    def retirar(self, canal: str) -> bool:
        self._meta(canal)
        ok = self._meta(canal).exists()
        shutil.rmtree(self.pasta / canal, ignore_errors=True)
        try:
            self._meta(canal).unlink()
        except FileNotFoundError:
            pass
        return ok


# ------------------------------------------------------------------ do lado do cliente
def ha_versao_nova(info: dict | None, atual: str) -> bool:
    return bool(info and info.get("versao") and mais_nova(info["versao"], atual))


def conferir_pacote(caminho: Path, info: dict) -> None:
    if info.get("sha256") and sha256_de(caminho) != info["sha256"]:
        raise ValueError("o pacote baixado não confere (SHA-256 diferente): baixe de novo")


def instalador_do_windows(caminho: Path) -> bool:
    return Path(caminho).suffix.lower() == ".exe"


def rodar_instalador(caminho: Path, popen=None) -> bool:
    """Roda o instalador do Windows sem perguntas, desligado deste processo. Devolve se rodou (quem chama
    fecha o programa em seguida)."""
    if not instalador_do_windows(caminho):
        return False
    # 0.99.70: /REABRIR=1 = o instalador (0.99.70 em diante) abre o programa de novo no fim
    args = [str(caminho), "/SILENT", "/CLOSEAPPLICATIONS", "/NORESTART", "/REABRIR=1"]
    popen = popen or subprocess.Popen
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess,
                                                                                    "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    popen(args, close_fds=True, **kw)
    return True


def abrir_pasta(pasta: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(pasta))  # noqa: S606
        else:
            from ipe.core.runtime import ambiente_do_sistema
            subprocess.Popen(["xdg-open", str(pasta)], env=ambiente_do_sistema())
    except Exception:  # noqa: BLE001
        log.exception("abrir a pasta da atualização")
