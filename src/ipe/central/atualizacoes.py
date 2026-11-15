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

0.100.47: **um pacote por sistema** em cada canal (Windows, Linux, macOS chip Apple, macOS Intel; a plataforma sai
do nome do pacote). O cliente diz o seu sistema e só recebe o pacote dele; se o servidor não tem, nada é baixado
e o aviso oferece o GitHub.
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


#: 0.100.47: um pacote por sistema em cada canal (antes era um só, e um Mac ligado a um servidor que publicara o
#: pacote do Linux baixava o pacote do Linux)
PLATAFORMAS = ("windows", "linux", "macos-arm64", "macos-x86_64")
ROTULO = {"windows": "Windows", "linux": "Linux", "macos-arm64": "macOS (chip Apple)",
          "macos-x86_64": "macOS (Intel)"}


def plataforma_do_nome(nome: str) -> str:
    """Para que sistema é o pacote, pelo nome do arquivo ("" = não dá para saber)."""
    n = Path(str(nome or "")).name.lower()
    if "macos" in n or "darwin" in n or n.endswith((".dmg", ".pkg")):
        return "macos-x86_64" if ("x86_64" in n or "intel" in n or "x64" in n) else "macos-arm64"
    if n.endswith((".exe", ".msi")) or "windows" in n or "win64" in n:
        return "windows"
    if "linux" in n or n.endswith((".deb", ".rpm", ".appimage", ".tar.gz", ".tgz")):
        return "linux"
    if n.endswith(".zip"):
        return "windows"
    return ""


def plataforma_deste(plataforma: str | None = None, maquina: str | None = None) -> str:
    """O sistema deste computador, no vocabulário de PLATAFORMAS."""
    plataforma = plataforma or sys.platform
    if plataforma.startswith("win"):
        return "windows"
    if plataforma == "darwin":
        from ipe.core.atualizar_github import arquitetura_mac
        return f"macos-{arquitetura_mac(maquina)}"
    return "linux"


def serve_para(info: dict | None, plataforma: str) -> bool:
    """O pacote descrito em `info` é para este sistema? (um servidor antigo não diz a plataforma: vale o nome)"""
    if not info or not info.get("nome"):
        return False
    p = info.get("plataforma") or plataforma_do_nome(info["nome"])
    return p == plataforma


class Atualizacoes:
    """A pasta dos pacotes no servidor: ``<canal>/<plataforma>/<pacote>`` e ``<canal>.json`` (formato 2:
    ``{"formato": 2, "pacotes": {plataforma: {...}}}``). O formato 1 (um pacote só, ``<canal>/<pacote>``) ainda é
    lido; a plataforma dele sai do nome."""

    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)

    def _meta(self, canal: str) -> Path:
        if canal not in CANAIS:
            raise ValueError(f"canal desconhecido: {canal}")
        return self.pasta / f"{canal}.json"

    def _ler(self, canal: str) -> dict:
        """{plataforma: (dados, caminho)} dos pacotes que existem de fato."""
        p = self._meta(canal)
        if not p.exists():
            return {}
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        out = {}
        if isinstance(d, dict) and isinstance(d.get("pacotes"), dict):
            for plat, x in d["pacotes"].items():
                arq = self.pasta / canal / plat / str(x.get("nome", ""))
                if x.get("nome") and arq.is_file():
                    out[plat] = (dict(x, plataforma=plat), arq)
        elif isinstance(d, dict) and d.get("nome"):                  # formato 1 (até a 0.100.46)
            arq = self.pasta / canal / d["nome"]
            if arq.is_file():
                plat = plataforma_do_nome(d["nome"]) or "windows"
                out[plat] = (dict(d, plataforma=plat), arq)
        return out

    def _gravar(self, canal: str, pacotes: dict) -> None:
        self._meta(canal).write_text(json.dumps({"formato": 2, "pacotes": pacotes}, ensure_ascii=False, indent=1),
                                     encoding="utf-8")

    def info(self, canal: str, plataforma: str | None = None) -> dict | None:
        """O pacote do canal para `plataforma`. Sem plataforma (clientes até a 0.100.46, quase todos Windows):
        o do Windows — nunca o de outro sistema."""
        e = self._ler(canal).get(plataforma or "windows")
        return e[0] if e else None

    def plataformas(self, canal: str) -> dict:
        return {plat: e[0] for plat, e in self._ler(canal).items()}

    def todas(self) -> dict:
        """Por canal, o pacote do Windows ou, sem ele, o primeiro (o que as telas até a 0.100.46 mostram)."""
        out = {}
        for c in CANAIS:
            ps = self.plataformas(c)
            out[c] = ps.get("windows") or (next(iter(ps.values())) if ps else None)
        return out

    def todas_por_plataforma(self) -> dict:
        return {c: self.plataformas(c) for c in CANAIS}

    def caminho(self, canal: str, plataforma: str | None = None) -> Path | None:
        e = self._ler(canal).get(plataforma or "windows")
        return e[1] if e else None

    def publicar(self, origem: Path, nome: str, versao: str = "", canal: str = "teste", notas: str = "",
                 por: str = "", plataforma: str = "") -> dict:
        self._meta(canal)
        nome = Path(nome or origem.name).name
        if not nome or nome.startswith("."):
            raise ValueError("nome de pacote inválido")
        versao = versao or versao_do_nome(nome)
        if not versao:
            raise ValueError("não achei a versão (x.y.z) no nome do pacote: informe a versão")
        plataforma = plataforma or plataforma_do_nome(nome)
        if plataforma not in PLATAFORMAS:
            raise ValueError("não sei para que sistema é o pacote (Windows, Linux ou macOS): use o nome original "
                             "do pacote ou informe a plataforma")
        existentes = self._ler(canal)
        pacotes = {}
        for plat, (d, arq) in existentes.items():                     # os outros sistemas ficam
            if plat == plataforma:
                continue
            certo = self.pasta / canal / plat / arq.name
            if arq != certo:                                           # formato 1: muda para a pasta do sistema
                certo.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(arq), str(certo))
            pacotes[plat] = {k: v for k, v in d.items() if k != "plataforma"}
        velho = existentes.get(plataforma)
        if velho and velho[1].parent == self.pasta / canal:            # formato 1, mesmo sistema: sai
            velho[1].unlink(missing_ok=True)
        dest = self.pasta / canal / plataforma
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        alvo = dest / nome
        shutil.copyfile(origem, alvo)
        d = {"canal": canal, "versao": versao, "nome": nome, "sha256": sha256_de(alvo),
             "tamanho": alvo.stat().st_size, "notas": notas or "", "por": por or "",
             "publicado_em": datetime.now().strftime("%Y-%m-%d %H:%M")}
        pacotes[plataforma] = d
        self._gravar(canal, pacotes)
        log.info("atualização %s (%s) publicada no canal %s por %s", versao, plataforma, canal, por)
        return dict(d, plataforma=plataforma)

    def promover(self, por: str = "") -> dict:
        """O que está no teste (todos os sistemas) vai também para o estável."""
        teste = self._ler("teste")
        if not teste:
            raise ValueError("não há pacote no canal de teste")
        feitos = {}
        for plat, (d, arq) in teste.items():
            feitos[plat] = self.publicar(arq, d["nome"], d["versao"], "estavel", d.get("notas", ""),
                                         por or d.get("por", ""), plat)
        principal = feitos.get("windows") or next(iter(feitos.values()))
        return dict(principal, plataformas=sorted(feitos))

    def retirar(self, canal: str, plataforma: str | None = None) -> bool:
        self._meta(canal)
        if plataforma:
            existentes = self._ler(canal)
            if plataforma not in existentes:
                return False
            arq = existentes.pop(plataforma)[1]
            if arq.parent == self.pasta / canal:
                arq.unlink(missing_ok=True)
            else:
                shutil.rmtree(arq.parent, ignore_errors=True)
            if existentes:
                for plat, (d, a) in list(existentes.items()):
                    certo = self.pasta / canal / plat / a.name
                    if a != certo:
                        certo.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(a), str(certo))
                self._gravar(canal, {p: {k: v for k, v in d.items() if k != "plataforma"}
                                     for p, (d, _a) in existentes.items()})
                return True
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
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(pasta)], env=ambiente_do_sistema())
    except Exception:  # noqa: BLE001
        log.exception("abrir a pasta da atualização")
