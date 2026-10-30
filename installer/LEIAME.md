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
5. compacta `dist\Ipe-<versão>-portatil.zip`;
6. se achar o Inno Setup, gera `dist\Ipe-<versão>-instalador.exe`.

## O que sai

| Arquivo | Para quê |
|---|---|
| `Ipe-<versão>-instalador.exe` | Instala no perfil do usuário, cria atalhos e registra o link `ipe://` |
| `Ipe-<versão>-portatil.zip` | Descompactar e rodar `Ipe.exe`; serve para pendrive e para testar |

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
