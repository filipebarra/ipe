# Gerar o instalador do Ipê (Windows)

O programa é instalado **no perfil do usuário**: nada de administrador, nada em
*Arquivos de Programas*. É a mesma regra que o programa segue ao rodar.

## O que é preciso ter, uma vez

1. **Python 3.12** — https://www.python.org/downloads/ (marque *Add python.exe to PATH*).
2. **Inno Setup 6** — https://jrsoftware.org/isdl.php — só para gerar o instalador.
   Sem ele o processo ainda produz o **pacote portátil** (um ZIP que roda de qualquer pasta).

## Gerar

Duplo clique em `installer\build_windows.bat`. Ele faz tudo:

1. cria um ambiente separado (`.venv-build`) e instala as bibliotecas e o PyInstaller;
2. gera o ícone a partir do desenho que já existe no programa;
3. empacota em `dist\Ipe\`;
4. **confere o pacote**: roda o executável, exige que os três arquivos de idioma estejam lá,
   gera 180 exames de teste e importa todos num banco novo — se algum passo falhar, ele para
   e não gera instalador;
5. compacta `dist\Ipe-<versão>-windows-portable.zip`;
6. se achar o Inno Setup, gera `dist\Ipe-<versão>-installer.exe`.

## O que sai

| Arquivo | Para quê |
|---|---|
| `Ipe-<versão>-installer.exe` | Instala no perfil do usuário, cria atalhos e registra o link `ipe://` |
| `Ipe-<versão>-windows-portable.zip` | Descompactar e rodar `Ipe.exe`; serve para pendrive e para testar |

Dentro do pacote há **dois executáveis**:

- `Ipe.exe` — a interface, sem janela de console atrás;
- `ipe-cli.exe` — os comandos de linha (`info`, `import`, `server`, `register-url`).
  No Windows um programa de janela não tem saída padrão, e um `print` sem saída derruba o
  processo — por isso os dois.

## Ao desinstalar

O desinstalador tira o programa e o registro do link. **Banco, exames e configurações não
são apagados**: são seus e ficam na pasta de dados do usuário (veja em `ipe-cli info`).

## Atualizar

Rode o instalador da versão nova por cima. O banco é migrado sozinho na abertura — colunas
novas entram com valor inicial, sem perder o que já estava lá.

## Linux (0.100.6)

O release do GitHub monta os dois pacotes de Linux a partir da pasta do PyInstaller (`dist/Ipe`):

- **Portátil** (`Ipe-<versão>-linux-portable.tar.gz`) com `install.sh` e `ipe.png` dentro: o `install.sh`
  instala para o usuário (`~/.local/share/ipe/programa`, `~/.local/bin/ipe-viewer`, atalho e ícone no menu),
  `--system` em `/opt/ipe` (sudo) e `--uninstall` remove. Atualizar é rodar o `install.sh` da versão nova.
- **Pacote `.deb`** (`Ipe-<versão>-linux-amd64.deb`, pacote `ipe-viewer`): `bash installer/linux/build_deb.sh
  dist/Ipe <versão> dist`. Programa em `/opt/ipe`, comando `/usr/bin/ipe-viewer`, atalho e ícone; só precisa do
  `dpkg-deb`, sem root.

O nome é `ipe-viewer` (não `ipe`) porque o Debian/Ubuntu já tem um pacote e um comando `ipe` (o editor de desenhos
Ipe). O workflow instala os dois de verdade no runner antes de publicar. Os dados do usuário
(`~/.local/share/DicomViewer`, `~/.config/DicomViewer`) nunca são tocados.
