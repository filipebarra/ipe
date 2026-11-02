"""Configurar um servidor sem janela pela linha de comando (0.99.8).

  ipe config                         mostra as configurações principais do servidor
  ipe config dicom.ae_title PACSIA   muda uma chave (o valor é lido como JSON se der:
                                             8043, true, ["A","B"]; senão é texto)
  ipe node list                      os nós DICOM cadastrados
  ipe node add NOME AE HOST PORTA [--move] [--sem-busca] [--sem-envio]
  ipe node add NOME --web URL [--usuario U --senha S]
  ipe node remove NOME

O resto (regras de automação, gestão automática, identidades) é configurado pela janela, que
pode rodar no próprio servidor com a mesma pasta de dados (veja LEIAME-LINUX.txt).
"""

from __future__ import annotations

import json
import sys

# o que `ipe config` mostra sem argumentos: o que um servidor costuma precisar
PRINCIPAIS = [
    "dicom.enabled", "dicom.ae_title", "dicom.port", "dicom.accept", "dicom.extra_ae_titles",
    "dicom.http_enabled", "dicom.http_port", "dicom.http_allow_remote", "dicom.http_allowed_ips",
    "central.port", "central.certfile", "central.keyfile",
    "print_scp.enabled", "print_scp.ae_title", "print_scp.port", "print_scp.accept",
]


# chaves que não estão no settings.json de fábrica: o servidor usa estes valores
PADRAO_SERVIDOR = {"central.port": 8043, "central.certfile": "", "central.keyfile": ""}


def _valor(texto: str):
    try:
        return json.loads(texto)
    except ValueError:
        return texto


def _settings():
    from ipe.core.config import Settings, get_paths
    return Settings(get_paths().settings_file)


def _repo():
    from ipe.core.config import get_paths
    from ipe.db.repository import Repository
    from ipe.db.session import Database
    return Repository(Database(get_paths().database))


def add_parsers(sub) -> None:
    c = sub.add_parser("config", help="ver ou mudar configurações (para servidor sem janela)")
    c.add_argument("chave", nargs="?", default="")
    c.add_argument("valor", nargs="?", default=None)
    n = sub.add_parser("node", help="nós DICOM pela linha de comando (list, add, remove)")
    nsub = n.add_subparsers(dest="acao", required=True)
    nsub.add_parser("list")
    a = nsub.add_parser("add")
    a.add_argument("nome")
    a.add_argument("ae", nargs="?", default="")
    a.add_argument("host", nargs="?", default="")
    a.add_argument("porta", nargs="?", type=int, default=104)
    a.add_argument("--web", default="", metavar="URL", help="nó DICOMweb (…/dicom-web)")
    a.add_argument("--usuario", default="")
    a.add_argument("--senha", default="")
    a.add_argument("--move", action="store_true", help="baixar por C-MOVE (padrão: C-GET)")
    a.add_argument("--sem-busca", action="store_true", help="não usar na busca")
    a.add_argument("--sem-envio", action="store_true", help="não usar no envio")
    r = nsub.add_parser("remove")
    r.add_argument("nome")


def run_config(args) -> int:
    s = _settings()
    if not args.chave:
        for k in PRINCIPAIS:
            v = s.get(k)
            print(f"{k:28} {json.dumps(PADRAO_SERVIDOR.get(k) if v is None else v, ensure_ascii=False)}")
        print(f"\nArquivo: {s.path}" if hasattr(s, "path") else "")
        return 0
    if args.valor is None:
        print(json.dumps(s.get(args.chave), ensure_ascii=False, indent=2))
        return 0
    s.set(args.chave, _valor(args.valor))
    s.save()
    print(f"{args.chave} = {json.dumps(s.get(args.chave), ensure_ascii=False)}")
    print("Reinicie o servidor para valer (sudo systemctl restart dicomviewer).")
    return 0


def run_node(args) -> int:
    repo = _repo()
    if args.acao == "list":
        nos = repo.nodes(todos=True)
        if not nos:
            print("Nenhum nó cadastrado.")
        for n in nos:
            onde = n["base_url"] if n["kind"] == "dicomweb" else f'{n["ae_title"]}@{n["host"]}:{n["port"]}'
            usos = ",".join(u for u, k in (("busca", "use_in_search"), ("envio", "use_in_send")) if n.get(k))
            print(f'{n["name"]:20} {n["kind"]:8} {onde:40} {n["retrieve"]:4} {usos}'
                  + ("" if n["active"] else "  (inativo)"))
        return 0
    if args.acao == "remove":
        n = next((x for x in repo.nodes(todos=True) if x["name"] == args.nome), None)
        if n is None:
            print(f"Nó {args.nome} não existe.", file=sys.stderr)
            return 1
        repo.delete_node(n["id"])
        print(f"Nó {args.nome} removido.")
        return 0
    # add (ou atualiza o de mesmo nome)
    atual = next((x for x in repo.nodes(todos=True) if x["name"] == args.nome), None)
    if args.web:
        dados = {"name": args.nome, "kind": "dicomweb", "base_url": args.web,
                 "username": args.usuario, "password": args.senha}
    else:
        if not (args.ae and args.host):
            print("Informe AE, HOST e PORTA (ou --web URL).", file=sys.stderr)
            return 2
        if len(args.ae) > 16:
            print("AE Title tem no máximo 16 caracteres.", file=sys.stderr)
            return 2
        dados = {"name": args.nome, "kind": "dimse", "ae_title": args.ae, "host": args.host,
                 "port": args.porta, "retrieve": "move" if args.move else "get"}
    dados.update(use_in_search=not args.sem_busca, use_in_send=not args.sem_envio, active=True)
    if atual:
        dados["id"] = atual["id"]
    repo.save_node(dados)
    print(f"Nó {args.nome} {'atualizado' if atual else 'cadastrado'}.")
    if not args.web:
        print("Lembre de cadastrar este servidor no outro lado também "
              "(AE, IP e porta), senão ele recusa as conexões.")
    return 0
