"""Linha de comando.

  ipe                          abre a interface
  ipe open --accession 123     abre o estudo (ou passa para a janela já aberta)
  ipe open --study-uid 1.2.3   idem, por StudyInstanceUID
  ipe open --patient-id X      abre o estudo mais recente do paciente
  ipe open C:\\pasta\\exame      importa e mostra
  ipe import <pastas/arquivos> importa sem abrir a interface
  ipe sample <pasta>           gera exames de teste sintéticos
  ipe info                     mostra onde ficam banco, arquivos e configurações
  ipe open --accession 123 --node PACS   busca e baixa do nó se não estiver no banco
  ipe open --accession 123 --janela viewer  abre só o visualizador nesta chamada
  ipe retrieve --accession 123           só baixa (sem abrir)
  ipe "ipe://open?accession=123"  link (ex.: botão no RIS web); dicomviewer:// também vale
  ipe register-url             faz o sistema abrir links ipe:// (e dicomviewer://) com o programa
  ipe unregister-url           tira esse registro (o desinstalador usa)
  ipe server [--port 8043]     servidor central sem janela (login, DICOMweb, nó DICOM)
  ipe server --create-admin admin   cria o primeiro administrador
  ipe config [chave [valor]]   ver ou mudar configurações (servidor sem janela)
  ipe node list|add|remove     nós DICOM pela linha de comando
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ipe", description="Visualizador DICOM")
    sub = p.add_subparsers(dest="cmd")
    o = sub.add_parser("open", help="abrir estudo")
    o.add_argument("paths", nargs="*", help="pastas ou arquivos para importar e abrir")
    o.add_argument("--accession", default="")
    o.add_argument("--study-uid", default="")
    o.add_argument("--patient-id", default="")
    o.add_argument("--node", default="", help="nó onde buscar se o estudo não estiver no banco")
    o.add_argument("--janela", default="", choices=["", "viewer", "completo"],
                   help="viewer = abre só o visualizador nesta chamada (sem o banco de dados); "
                        "completo = abre o programa inteiro. Sem isto, vale a configuração de Rede")
    r = sub.add_parser("retrieve", help="baixar do PACS sem abrir")
    r.add_argument("--accession", default="")
    r.add_argument("--study-uid", default="")
    r.add_argument("--patient-id", default="")
    r.add_argument("--node", default="")
    sub.add_parser("register-url", help="registrar o link ipe:// no sistema")
    sub.add_parser("unregister-url", help="tirar o registro do link (usado ao desinstalar)")
    i = sub.add_parser("import", help="importar sem interface")
    i.add_argument("paths", nargs="+")
    i.add_argument("--reference", action="store_true",
                   help="não copiar: só referenciar os arquivos no local original")
    sv = sub.add_parser("server", help="servidor central sem janela (intranet)")
    sv.add_argument("--port", type=int, default=0, help="porta HTTP (padrão: a das configurações ou 8043)")
    sv.add_argument("--create-admin", default="", metavar="USUARIO",
                    help="cria o administrador (pede a senha) se ainda não houver usuários")
    sv.add_argument("--no-dicom", action="store_true", help="não liga o nó DICOM")
    from ipe.central.admin_cli import add_parsers
    add_parsers(sub)
    s = sub.add_parser("sample", help="gerar exames sintéticos de teste")
    s.add_argument("folder")
    m = sub.add_parser("set-mode", help="quem usa este computador (usado pelo instalador)")
    m.add_argument("mode", choices=["single", "multi"])
    sub.add_parser("info", help="mostrar caminhos")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    minimized = "--minimized" in argv
    argv = [a for a in argv if a != "--minimized"]
    if argv and argv[0].lower().startswith(("ipe:", "dicomviewer:")):
        from ipe.app import run_gui
        from ipe.network.external import ExternalError, parse_url
        try:
            payload = parse_url(argv[0])
        except ExternalError as e:
            print(f"Link inválido: {e}", file=sys.stderr)
            return 2
        payload["source"] = "link"
        return run_gui(payload)
    args = _parser().parse_args(argv)

    if args.cmd == "unregister-url":
        from ipe.network.external import unregister_url_scheme
        print(unregister_url_scheme())
        return 0

    if args.cmd == "set-mode":
        from ipe.core.config import Settings, get_paths
        s = Settings(get_paths().settings_file)
        s.set("auth.mode", args.mode)
        s.save()
        print(f"Modo de acesso: {args.mode}")
        return 0

    if args.cmd == "register-url":
        from ipe.network.external import register_url_scheme
        print(register_url_scheme())
        return 0

    if args.cmd == "import":
        from ipe.core.config import get_paths
        from ipe.core.logging_setup import setup_logging
        from ipe.db.repository import Repository
        from ipe.db.session import Database
        from ipe.importer.scanner import Importer
        from ipe.importer.thumbnails import generate_thumbnails
        paths = get_paths()
        setup_logging(paths.logs)
        db = Database(paths.database)

        def progress(done: int, total: int, _cur: str) -> None:
            print(f"\r{done}/{total}", end="", flush=True)

        r = Importer(db, paths.storage, copy_to_storage=not args.reference).import_paths(
            [Path(p) for p in args.paths], progress=progress)
        print()
        generate_thumbnails(Repository(db), r.new_series)
        print(r.summary())
        return 0 if not r.errors else 1

    if args.cmd == "server":
        from ipe.central.headless import run_server
        return run_server(args)

    if args.cmd == "config":
        from ipe.central.admin_cli import run_config
        return run_config(args)

    if args.cmd == "node":
        from ipe.central.admin_cli import run_node
        return run_node(args)

    if args.cmd == "sample":
        from ipe.core.sample_data import make_sample_data
        files = make_sample_data(Path(args.folder))
        print(f"{len(files)} arquivos gerados em {args.folder}")
        return 0

    if args.cmd == "info":
        from ipe import __version__
        from ipe.core.config import get_paths
        p = get_paths()
        # A versão vem primeiro de propósito: é o jeito de saber **qual** instalação é esta
        # quando há mais de um pacote gerado na pasta dist.
        print(f"Versão:        {__version__}")
        print(f"Banco:         {p.database}\nArmazenamento: {p.storage}\n"
              f"Configurações: {p.settings_file}\nLogs:          {p.logs}")
        return 0

    from ipe.app import run_gui
    external = None
    if args.cmd in ("open", "retrieve"):
        external = {"command": args.cmd, "accession": args.accession, "study_uid": args.study_uid,
                    "patient_id": args.patient_id, "node": args.node, "source": "cmd",
                    "janela": getattr(args, "janela", ""),
                    "paths": [str(Path(p).resolve()) for p in getattr(args, "paths", [])]}
    return run_gui(external, minimized=minimized)


if __name__ == "__main__":
    sys.exit(main())
