"""Levar exames entre o servidor central e este computador (0.99.28, etapa 4 do plano do modo de uso).

Pedido dele: no modo servidor, o banco pessoal pode ficar **neste computador** (funciona sem internet,
intranet ou VPN, e serve de banco de casos) ou **no servidor** (segue o usuário em qualquer estação).

- `trazer`: do servidor para o banco deste computador (o mesmo banco do modo local, em Locais ▸ Banco
  deste computador). Com `mover`, o exame sai do servidor depois de chegar aqui (só o dono ou o
  administrador; o servidor confere).
- `enviar`: de um banco local (este computador, um HD externo…) para o servidor — também é a migração
  do banco de um computador que passou a ser cliente.

As imagens vão por DICOMweb; laudos, medidas, anotações, imagens-chave etc. vão no pacote do exame
(db/pacote.py), juntados sem apagar o que já existe do outro lado.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class Resultado:
    exames: int = 0
    imagens: int = 0
    dados: int = 0                       # linhas de laudos/medidas/… juntadas
    recusados: list[str] = field(default_factory=list)       # exames que o servidor não deixou mexer
    erros: list[str] = field(default_factory=list)
    feitos: list[str] = field(default_factory=list)          # exames que chegaram ao destino

    def resumo(self, verbo: str) -> str:
        t = f"{self.exames} exame(s) {verbo} ({self.imagens} imagem(ns)"
        t += f", {self.dados} registro(s) de laudos, medidas e anotações)." if self.dados else ")."
        if self.recusados:
            t += f" {len(self.recusados)} ficaram de fora (banco de outro usuário ou sem permissão)."
        if self.erros:
            t += f" {len(self.erros)} com erro: " + "; ".join(self.erros[:3])
        return t


def _importar_arquivos(db, storage, arquivos):
    from ipe.db.repository import Repository
    from ipe.importer.scanner import Importer
    from ipe.importer.thumbnails import generate_thumbnails
    r = Importer(db, Path(storage), copy_to_storage=True).import_paths([Path(a) for a in arquivos])
    try:
        generate_thumbnails(Repository(db), r.new_series)
    except Exception:  # noqa: BLE001
        log.exception("miniaturas")
    return r


def trazer(cliente, uids, destino_db, destino_storage, dono: str, mover: bool = False,
           progress=None, cancel=None) -> Resultado:
    """Do servidor para este computador. `cliente` é o ClientRepository (cache + servidor)."""
    from ipe.central.remote import RemoteError
    from ipe.db.repository import Repository
    destino = Repository(destino_db)
    res = Resultado()
    for i, uid in enumerate(uids):
        if cancel and cancel():
            break
        if progress:
            progress(i, len(uids), uid)
        try:
            pac = cliente.client.rpc("dados_do_exame", uid)
        except RemoteError as e:
            res.recusados.append(uid) if "banco pessoal" in str(e) else res.erros.append(str(e))
            continue
        try:
            cliente.download(uid)
            arquivos = [f for f in cliente.local.files_for_study(uid) if Path(f).exists()]
            if not arquivos:
                res.erros.append(f"{uid}: nenhuma imagem")
                continue
            r = _importar_arquivos(destino_db, destino_storage, arquivos)
            res.imagens += r.added
            if pac:
                pac = {**pac, "dono": dono, "visivel_para": ""}
                res.dados += sum(destino.receber_dados_do_exame(pac).values())
            else:
                destino.set_study_scope([uid], dono, "")
            res.exames += 1
            res.feitos.append(uid)
            if mover:
                try:
                    cliente.client.rpc("retirar_do_servidor", uid)
                    cliente.remove_cached(uid)
                except RemoteError as e:      # cadeado, exame de outro…: fica copiado, não movido
                    res.recusados.append(uid)
                    res.erros.append(f"ficou também no servidor: {e}")
        except RemoteError as e:
            res.recusados.append(uid) if "dono" in str(e) or "banco" in str(e) else res.erros.append(str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("trazer do servidor")
            res.erros.append(str(e))
    return res


def do_cache_para_este_computador(cliente, uids, destino_db, destino_storage, dono: str) -> Resultado:
    """Exames recém-importados no modo cliente que o usuário quer **só neste computador**: saem do cache
    (sem subir ao servidor) e entram no banco deste computador, no banco pessoal dele."""
    from ipe.db.repository import Repository
    destino = Repository(destino_db)
    res = Resultado()
    for uid in uids:
        try:
            arquivos = [f for f in cliente.local.files_for_study(uid) if Path(f).exists()]
            if not arquivos:
                continue
            res.imagens += _importar_arquivos(destino_db, destino_storage, arquivos).added
            destino.set_study_scope([uid], dono, "")
            cliente.remove_cached(uid)
            res.exames += 1
            res.feitos.append(uid)
        except Exception as e:  # noqa: BLE001
            log.exception("cache para este computador")
            res.erros.append(str(e))
    return res


def enviar(client, origem, uids, meu, usuario: str, progress=None, cancel=None) -> Resultado:
    """De um banco local (`origem`: Repository) para o servidor (`client`: RemoteClient).
    `meu`: True = no banco pessoal de quem envia; False = no compartilhado; "como_estao" = cada exame no
    banco em que estava aqui (migração feita pelo administrador)."""
    como_estao = meu == "como_estao"
    from ipe.central.remote import RemoteError
    res = Resultado()
    for i, uid in enumerate(uids):
        if cancel and cancel():
            break
        if progress:
            progress(i, len(uids), uid)
        try:
            try:
                tem = set(client.rpc("sop_uids_for_study", uid) or [])
            except RemoteError as e:
                if "banco pessoal" in str(e):
                    res.recusados.append(uid)
                    continue
                raise
            todo = [p for sop, p in origem.files_with_sops(uid) if sop not in tem and Path(p).exists()]
            pac = origem.dados_do_exame(uid)
            if todo:
                r = client.store(todo, banco="meu" if meu is True else "")
                res.imagens += int(r.get("sent") or 0)
            if pac:
                res.dados += sum((client.rpc("receber_dados_do_exame", pac) or {}).values())
            vp = (pac or {}).get("visivel_para", "") if meu else ""
            dono_aqui = (pac or {}).get("dono", "") or ""
            if tem or vp or (como_estao and dono_aqui):   # ajusta o banco no servidor
                info = client.rpc("study_info", uid) or {}
                quer = dono_aqui if como_estao else (usuario if meu else "")
                if (info.get("dono") or "").lower() != quer.lower() or vp:
                    if not client.rpc("set_study_scope", [uid], quer, vp) and quer:
                        res.recusados.append(uid)
            res.exames += 1
            res.feitos.append(uid)
        except RemoteError as e:
            res.erros.append(str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("enviar ao servidor")
            res.erros.append(str(e))
    return res
