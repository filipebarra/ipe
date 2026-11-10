#!/usr/bin/env bash
# Ipê — instalação no Linux a partir do portátil (0.100.6).
#
#   ./install.sh                     instala (ou atualiza) para este usuário, sem administrador
#   ./install.sh --system            instala para todos os usuários (pede a senha do sudo): /opt/ipe
#   ./install.sh --uninstall         remove o programa deste usuário
#   ./install.sh --uninstall --system
#
# Instala o programa, o comando `ipe-viewer`, o ícone e o atalho no menu de aplicativos. Os exames, o banco e as
# configurações ficam onde sempre ficaram (~/.local/share/DicomViewer e ~/.config/DicomViewer): atualizar ou remover
# o programa não mexe neles. O comando se chama `ipe-viewer` porque `ipe` já é o nome de outro programa (um editor
# de desenhos) nas distribuições.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOME=ipe-viewer
MODO=usuario
ACAO=instalar

ajuda() {
  sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
}

for a in "$@"; do
  case "$a" in
    --system) MODO=sistema ;;
    --uninstall) ACAO=remover ;;
    -h|--help) ajuda ;;
    *) echo "Opção desconhecida: $a (use --help)" >&2; exit 2 ;;
  esac
done

if [ "$MODO" = sistema ]; then
  if [ "$(id -u)" != 0 ]; then
    exec sudo bash "${BASH_SOURCE[0]}" "$@"
  fi
  PROG=/opt/ipe
  BIN=/usr/local/bin
  APPS=/usr/share/applications
  ICONES=/usr/share/icons/hicolor
else
  DADOS="${XDG_DATA_HOME:-$HOME/.local/share}"
  PROG="$DADOS/ipe/programa"
  BIN="$HOME/.local/bin"
  APPS="$DADOS/applications"
  ICONES="$DADOS/icons/hicolor"
fi

atualizar_menus() {
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$APPS" 2>/dev/null || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t -f "$ICONES" 2>/dev/null || true
}

if [ "$ACAO" = remover ]; then
  if [ -L "$BIN/$NOME" ] && [ "$(readlink "$BIN/$NOME")" = "$PROG/Ipe" ]; then rm -f "$BIN/$NOME"; fi
  rm -f "$APPS/$NOME.desktop" "$ICONES/256x256/apps/$NOME.png"
  rm -rf "$PROG"
  atualizar_menus
  echo "Ipê removido de $PROG."
  echo "Os exames e as configurações continuam em ${XDG_DATA_HOME:-$HOME/.local/share}/DicomViewer e ~/.config/DicomViewer."
  exit 0
fi

if [ ! -x "$AQUI/Ipe" ]; then
  echo "Rode este script de dentro da pasta Ipe do portátil (não achei $AQUI/Ipe)." >&2
  exit 1
fi
if [ "$AQUI" = "$PROG" ]; then
  echo "O Ipê já está instalado nesta pasta ($PROG)." >&2
  exit 1
fi

mkdir -p "$(dirname "$PROG")" "$BIN" "$APPS" "$ICONES/256x256/apps"
# copia ao lado e troca de uma vez: uma atualização interrompida não deixa o programa pela metade
rm -rf "$PROG.novo"
cp -a "$AQUI" "$PROG.novo"
rm -rf "$PROG"
mv "$PROG.novo" "$PROG"
ln -sfn "$PROG/Ipe" "$BIN/$NOME"
if [ -f "$AQUI/ipe.png" ]; then
  install -m 644 "$AQUI/ipe.png" "$ICONES/256x256/apps/$NOME.png"
fi
cat > "$APPS/$NOME.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Ipê
GenericName=DICOM viewer
GenericName[pt_BR]=Visualizador DICOM
GenericName[es]=Visor DICOM
Comment=Medical image viewer (DICOM)
Comment[pt_BR]=Visualizador de imagens médicas (DICOM)
Comment[es]=Visor de imágenes médicas (DICOM)
Exec="$PROG/Ipe" open %F
Icon=$NOME
Terminal=false
Categories=Graphics;MedicalSoftware;Science;
MimeType=application/dicom;
Keywords=DICOM;PACS;radiology;radiologia;
DESK
chmod 644 "$APPS/$NOME.desktop"
atualizar_menus

echo "Ipê instalado em $PROG."
echo "Abra pelo menu de aplicativos (Ipê) ou pelo comando: $NOME"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "Aviso: $BIN não está no PATH; abra uma nova sessão ou rode $BIN/$NOME." ;;
esac
