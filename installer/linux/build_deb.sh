#!/usr/bin/env bash
# Monta o pacote .deb do Ipê (0.100.6) a partir da pasta do PyInstaller (dist/Ipe).
#
#   installer/linux/build_deb.sh dist/Ipe 0.100.6 dist
#
# Gera dist/Ipe-<versão>-linux-amd64.deb, com o programa em /opt/ipe, o comando /usr/bin/ipe-viewer, o atalho no
# menu e o ícone. O pacote se chama `ipe-viewer` (o nome `ipe` já é de outro programa no Debian/Ubuntu). Só precisa
# do dpkg-deb; não precisa de root (--root-owner-group).
set -euo pipefail

ORIGEM="${1:?pasta do PyInstaller (dist/Ipe)}"
VERSAO="${2:?versão}"
SAIDA="${3:-.}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ_REPO="$(cd "$AQUI/../.." && pwd)"
NOME=ipe-viewer
ARQ=amd64

[ -x "$ORIGEM/Ipe" ] || { echo "não achei $ORIGEM/Ipe" >&2; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PKG="$TMP/pkg"
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" \
  "$PKG/usr/share/icons/hicolor/256x256/apps" "$PKG/usr/share/doc/$NOME"

cp -a "$ORIGEM" "$PKG/opt/ipe"
rm -f "$PKG/opt/ipe/install.sh"                    # o instalador do portátil não faz sentido no pacote
ln -s /opt/ipe/Ipe "$PKG/usr/bin/$NOME"
install -m 644 "$AQUI/ipe.png" "$PKG/usr/share/icons/hicolor/256x256/apps/$NOME.png"
cat > "$PKG/usr/share/applications/$NOME.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=Ipê
GenericName=DICOM viewer
GenericName[pt_BR]=Visualizador DICOM
GenericName[es]=Visor DICOM
Comment=Medical image viewer (DICOM)
Comment[pt_BR]=Visualizador de imagens médicas (DICOM)
Comment[es]=Visor de imágenes médicas (DICOM)
Exec=/opt/ipe/Ipe open %F
Icon=ipe-viewer
Terminal=false
Categories=Graphics;MedicalSoftware;Science;
MimeType=application/dicom;
Keywords=DICOM;PACS;radiology;radiologia;
DESK
if [ -f "$RAIZ_REPO/LICENSE" ]; then
  install -m 644 "$RAIZ_REPO/LICENSE" "$PKG/usr/share/doc/$NOME/copyright"
fi

# permissões de pacote: pastas 755, arquivos 644, executáveis continuam executáveis
find "$PKG" -type d -exec chmod 755 {} +
find "$PKG" -type f ! -perm -u+x -exec chmod 644 {} +
find "$PKG" -type f -perm -u+x -exec chmod 755 {} +

TAMANHO=$(du -sk --exclude=DEBIAN "$PKG" | cut -f1)
cat > "$PKG/DEBIAN/control" <<CTRL
Package: $NOME
Version: $VERSAO
Architecture: $ARQ
Maintainer: Filipe Barra <filipebarra@users.noreply.github.com>
Installed-Size: $TAMANHO
Depends: libc6, libegl1, libgl1, libfontconfig1, libxkbcommon0, libxkbcommon-x11-0, libdbus-1-3, libxcb-cursor0
Section: science
Priority: optional
Homepage: https://github.com/filipebarra/ipe
Description: Ipê — DICOM viewer (workstation, PACS client and web server)
 Medical image viewer for radiology: 2D, MPR, MIP and 3D, PET/CT fusion,
 mammography hanging protocols and tomosynthesis, breast dynamic MRI,
 measurements, structured reports and an optional central server with a web
 viewer. Not intended for primary diagnosis without local validation.
CTRL
for f in postinst postrm; do
  cat > "$PKG/DEBIAN/$f" <<'SH'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
exit 0
SH
  chmod 755 "$PKG/DEBIAN/$f"
done

mkdir -p "$SAIDA"
DEST="$SAIDA/Ipe-$VERSAO-linux-$ARQ.deb"
dpkg-deb --root-owner-group -Zxz --build "$PKG" "$DEST" >/dev/null
echo "$DEST"
