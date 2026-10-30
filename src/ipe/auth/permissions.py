"""Permissões e perfis. O administrador pode ajustar a tabela de cada perfil
(fica no banco, em app_setting "roles")."""

from __future__ import annotations

PERMISSIONS: dict[str, str] = {
    "view": "Abrir e ver exames",
    "import": "Importar arquivos",
    "query": "Buscar no PACS",
    "retrieve": "Baixar do PACS",
    "send": "Enviar para nós DICOM",
    "export": "Exportar (CD/pendrive, imagens)",
    "export_identified": "Exportar com dados do paciente (sem anonimizar)",
    "delete": "Apagar exames",
    "case_lists": "Listas de casos e modo reunião",
    "print": "Filmes e impressão",
    "report": "Escrever laudos (rascunho) e editar modelos",
    "sign_report": "Assinar (liberar) laudos",
    "configure": "Configurar rede, automação e preferências do computador",
    "users": "Gerenciar usuários e ver o registro de acesso",
}

ROLES: dict[str, str] = {
    "admin": "Administrador",
    "medico": "Médico",
    "residente": "Residente",
    "tecnico": "Técnico",
}

_ALL = set(PERMISSIONS)
DEFAULT_ROLE_PERMS: dict[str, set[str]] = {
    "admin": set(_ALL),
    "medico": _ALL - {"configure", "users"},
    "residente": {"view", "import", "query", "retrieve", "export", "case_lists", "print", "report"},
    "tecnico": {"view", "import", "query", "retrieve", "send", "export", "export_identified", "print"},
}


def role_permissions(repo=None) -> dict[str, set[str]]:
    """Tabela perfil -> permissões (padrão, com os ajustes do administrador)."""
    out = {k: set(v) for k, v in DEFAULT_ROLE_PERMS.items()}
    custom = repo.get_app_setting("roles", None) if repo is not None else None
    if isinstance(custom, dict):
        for role, perms in custom.items():
            if role in out and isinstance(perms, list):
                out[role] = {p for p in perms if p in PERMISSIONS}
    out["admin"] = set(_ALL)            # o administrador sempre pode tudo
    return out


def permissions_for(role: str, repo=None) -> set[str]:
    return set(role_permissions(repo).get(role, set()))
