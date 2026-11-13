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
  ipe set-language en|pt-BR|es idioma do programa (o instalador usa)
  ipe set-data-dir PASTA      pasta do banco deste computador (o instalador usa)
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
    lc = sub.add_parser("link-cifrado", help="monta um link ipe:// cifrado com o token da API (0.99.31)")
    lc.add_argument("query", help='o que vai no link, ex.: "accession=123&node=PACS"')
    lc.add_argument("--comando", default="open", choices=["open", "retrieve"])
    lc.add_argument("--token", default="", help="o token da API (padrão: o deste computador)")
    m = sub.add_parser("set-mode", help="quem usa este computador (usado pelo instalador)")
    m.add_argument("mode", choices=["single", "multi"])
    lg = sub.add_parser("set-language", help="idioma do programa: en, pt-BR ou es (usado pelo instalador)")
    lg.add_argument("lang")
    dd = sub.add_parser("set-data-dir", help="pasta do banco deste computador (usado pelo instalador, 0.99.67)")
    dd.add_argument("folder")
    sub.add_parser("info", help="mostrar caminhos")
    # 0.100.34: o banco principal no PostgreSQL (servidor sem janela, montado por roteiro)
    bc = sub.add_parser("banco", help="banco principal: o PostgreSQL do Ipê ou um servidor PostgreSQL próprio")
    bsub = bc.add_subparsers(dest="banco_cmd", required=True)
    bsub.add_parser("status", help="qual banco está em uso")
    bp = bsub.add_parser("postgres", help="usar um servidor PostgreSQL (pergunta a senha)")
    bp.add_argument("--host", default="localhost")
    bp.add_argument("--porta", type=int, default=5432)
    bp.add_argument("--banco", default="ipe")
    bp.add_argument("--usuario", default="ipe")
    bp.add_argument("--ssl", default="prefer", choices=["disable", "prefer", "require", "verify-full"])
    bp.add_argument("--copiar", action="store_true", help="copiar o banco em uso neste computador para ele")
    be = bsub.add_parser("embutido", help="usar o PostgreSQL que vem com o Ipê, neste computador (o padrão)")
    be.add_argument("--copiar", action="store_true", help="copiar o banco em uso (o servidor próprio) para ele")
    bt = bsub.add_parser("testar-embutido", help="liga o PostgreSQL embutido numa pasta descartável e desliga")
    bt.add_argument("pasta", nargs="?", default="")
    return p


def _cmd_banco(args) -> int:
    """`ipe-cli banco status | postgres … [--copiar] | embutido [--copiar] | testar-embutido` (0.100.34)."""
    import getpass
    import os

    from ipe.core import banco_config as BC
    from ipe.core.config import get_paths
    from ipe.db.session import endereco_configurado, mascarar, precisa_migrar
    paths = get_paths()

    def copiar_para(url) -> bool:
        try:
            origem = BC.origem_atual(paths.database)
        except Exception as e:  # noqa: BLE001
            print(f"O banco em uso não abriu: {e}", file=sys.stderr)
            return False
        if isinstance(origem, str) and BC.mesmo_banco(origem, url):
            print("Este já é o banco em uso: nada a copiar.")
            return True
        try:
            feito = BC.copiar(origem, url, lambda tb, n, tot: print(f"  {tb}: {tot}") if n == tot else None)
        except BC.ErroBanco as e:
            print(f"Cópia não feita: {e}", file=sys.stderr)
            return False
        print(f"Copiadas {sum(feito.values())} linhas em {len(feito)} tabelas.")
        return True

    if args.banco_cmd == "status":
        url = endereco_configurado()
        if url:
            print(f"Banco: servidor próprio {mascarar(url)}")
        else:
            print(f"Banco: PostgreSQL do Ipê em {paths.data / 'postgres'}")
        if precisa_migrar(paths.database):
            print(f"(o banco antigo {paths.database} será migrado para o PostgreSQL ao abrir o Ipê)")
        if os.environ.get("IPE_DATABASE_URL"):
            print("(pela variável IPE_DATABASE_URL, que passa na frente do banco.json)")
        if url:
            t = BC.testar(url)
            print(f"Conexão: ok, PostgreSQL {t.versao}" if t.ok else f"Conexão: FALHOU — {t.erro}")
            return 0 if t.ok else 1
        return 0
    if args.banco_cmd == "testar-embutido":
        from ipe.core import pg_embutido as PE
        pasta = Path(args.pasta) if args.pasta else PE.pasta_temporaria() / "postgres"
        try:
            versao = PE.testar_pacote(pasta)
        except Exception as e:  # noqa: BLE001
            print(f"PostgreSQL embutido: FALHOU — {e}", file=sys.stderr)
            return 1
        print(f"PostgreSQL embutido: ok, {versao}")
        return 0
    if args.banco_cmd == "embutido":
        from ipe.core import pg_embutido as PE
        if not PE.disponivel():
            print("Este pacote do Ipê não traz o PostgreSQL embutido.", file=sys.stderr)
            return 1
        try:
            url = BC.url_embutido(paths.data / "postgres")
        except Exception as e:  # noqa: BLE001
            print(f"O PostgreSQL embutido não ligou: {e}", file=sys.stderr)
            return 1
        t = BC.testar(url)
        print(f"PostgreSQL embutido: {t.versao}; " + ("banco vazio." if t.vazio else "o banco já tem exames."))
        if args.copiar and not copiar_para(url):
            return 1
        BC.gravar({"tipo": "embutido"})
        print("Gravado em", BC.arquivo(), "— vale ao abrir o Ipê (ou o servidor) de novo.")
        return 0
    cfg = {"tipo": "postgresql", "host": args.host, "porta": args.porta, "banco": args.banco,
           "usuario": args.usuario, "ssl": args.ssl}
    senha = os.environ.get("IPE_DB_SENHA") or getpass.getpass(f"Senha de {args.usuario} no PostgreSQL: ")
    url = BC.url(cfg, senha)
    t = BC.testar(url)
    if not t.ok:
        print(f"Não conectou: {t.erro}", file=sys.stderr)
        return 1
    print(f"Conectou: PostgreSQL {t.versao}; banco vazio." if t.vazio else
          f"Conectou: PostgreSQL {t.versao}; o banco já tem exames.")
    if args.copiar and not copiar_para(url):
        return 1
    BC.gravar(dict(cfg, senha=senha))
    print("Gravado em", BC.arquivo(), "— vale ao abrir o Ipê (ou o servidor) de novo.")
    return 0


def _e_link(texto: str) -> bool:
    """ipe://, dicomviewer:// ou um apelido configurado (0.100.32). Os dois primeiros sem ler configuração."""
    t = str(texto or "").lower()
    if t.startswith(("ipe:", "dicomviewer:")):
        return True
    if "://" not in t[:40] or t.startswith(("-", "/", ".")):
        return False
    from ipe.network.external import e_link
    return e_link(texto)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    minimized = "--minimized" in argv
    argv = [a for a in argv if a != "--minimized"]
    if argv and _e_link(argv[0]):
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
        s.set("auth.modo_confirmado", True)      # o instalador já perguntou: o primeiro uso não pergunta de novo
        s.save()
        print(f"Modo de acesso: {args.mode}")
        return 0

    if args.cmd == "set-language":
        from ipe.core import i18n
        from ipe.core.config import Settings, get_paths
        lang = i18n.normalize(args.lang)
        if not lang:
            print(f"Unknown language: {args.lang} (use en, pt-BR or es)", file=sys.stderr)
            return 2
        s = Settings(get_paths().settings_file)
        s.set("language", lang)
        s.save()
        print(f"Language: {lang}")
        return 0

    if args.cmd == "set-data-dir":
        from ipe.core.config import Settings, definir_pasta_do_banco, get_paths
        paths = get_paths()
        s = Settings(paths.settings_file)
        ok, msg = definir_pasta_do_banco(s, paths, args.folder)
        try:
            print(msg)
        except UnicodeEncodeError:              # console do Windows sem UTF-8: o código de saída é o que vale
            print(msg.encode("ascii", "replace").decode())
        return 0 if ok else 3

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

    if args.cmd == "link-cifrado":
        from ipe.core.config import Settings, get_paths
        from ipe.network import link_cifrado as LC
        token = args.token or (Settings(get_paths().settings_file).get("dicom", {}) or {}).get("http_token", "")
        try:
            print(f"ipe://{args.comando}?c={LC.montar(args.query, token)}")
        except LC.LinkInvalido as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 1
        return 0

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

    if args.cmd == "banco":
        return _cmd_banco(args)

    if args.cmd == "info":
        from ipe import __version__
        from ipe.core.config import get_paths
        p = get_paths()
        # A versão vem primeiro de propósito: é o jeito de saber **qual** instalação é esta
        # quando há mais de um pacote gerado na pasta dist.
        print(f"Versão:        {__version__}")
        from ipe.db.session import endereco_configurado, mascarar
        print(f"Banco:         {mascarar(endereco_configurado()) or p.database}\nArmazenamento: {p.storage}\n"
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
