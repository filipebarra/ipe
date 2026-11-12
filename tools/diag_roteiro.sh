#!/usr/bin/env bash
# Diagnóstico do macOS (0.100.27): abre o Ipê com o roteiro automático (ipe/diag.py), tira fotos da tela a cada
# etapa, digita no campo do servidor quando o programa pede, e diz se o programa fechou sozinho.
#   bash tools/diag_roteiro.sh <nome> <comando…>      (comando "ABRIR_APP" = open dist/Ipe.app, como o usuário)
nome="$1"; shift
D="$PWD/diag/$nome"; mkdir -p "$D"
export IPE_DIAG_JANELA=1 IPE_DIAG_DIR="$D" IPE_DIAG_PASTA="$PWD/amostras" IPE_DIAG_DIGITAR=16 IPE_DIAG_VER=10 IPE_DIAG_ABRIR=40
: > "$HOME/Library/Logs/DicomViewer/queda.log" 2>/dev/null || true
if [ "$1" = "ABRIR_APP" ]; then
  open -n dist/Ipe.app --stdout "$D/saida.log" --stderr "$D/erro.log" \
    --env IPE_DIAG_JANELA=1 --env IPE_DIAG_DIR="$D" --env IPE_DIAG_PASTA="$IPE_DIAG_PASTA" \
    --env IPE_DIAG_DIGITAR=16 --env IPE_DIAG_VER=10 --env IPE_DIAG_ABRIR=40
  vivo() { pgrep -f "Ipe.app/Contents/MacOS/Ipe" >/dev/null; }
else
  "$@" > "$D/saida.log" 2>&1 &
  P=$!
  vivo() { kill -0 $P 2>/dev/null; }
fi
digitou=0; foto=0
for i in $(seq 1 150); do
  sleep 2
  n=$(ls "$D"/etapa_* 2>/dev/null | wc -l | tr -d ' ')
  if [ $((i % 20)) = 0 ]; then screencapture -x "$D/tela-t$i.png" 2>/dev/null || true; fi
  if [ "$n" != "$foto" ]; then screencapture -x "$D/tela-$n.png" 2>/dev/null || true; foto=$n; fi
  if [ -f "$D/digite.txt" ] && [ $digitou = 0 ]; then
    sleep 2
    screencapture -x "$D/tela-antes-de-digitar.png" 2>/dev/null || true
    osascript -e 'tell application "System Events" to keystroke "http://abcdefghijklmnopqrstuvwxyz.0123456789"' 2> "$D/osascript.log" || true
    sleep 2
    screencapture -x "$D/tela-depois-de-digitar.png" 2>/dev/null || true
    digitou=1
  fi
  if ls "$D"/etapa_*_fim.txt >/dev/null 2>&1; then echo "[$nome] ROTEIRO COMPLETO"; break; fi
  if ! vivo; then echo "[$nome] O PROGRAMA FECHOU SOZINHO (etapas feitas: $n)"; break; fi
done
screencapture -x "$D/tela-final.png" 2>/dev/null || true
sleep 3
echo "--- [$nome] onde está (se empacou)"; tail -60 "$D/onde_esta.log" 2>/dev/null
if [ -d dist/Ipe.app ]; then echo "--- Info.plist"; plutil -p dist/Ipe.app/Contents/Info.plist | grep -i "background\|UIElement\|Executable\|PackageType"; fi
echo "--- [$nome] GITHUB (busca de atualização): $(cat "$D/github.txt" 2>/dev/null)"
echo "--- [$nome] resultado"; cat "$D/resultado.json" 2>/dev/null; echo
echo "--- [$nome] saída"; tail -40 "$D/saida.log" 2>/dev/null; tail -40 "$D/erro.log" 2>/dev/null
echo "--- [$nome] queda.log"; tail -120 "$HOME/Library/Logs/DicomViewer/queda.log" 2>/dev/null
cp "$HOME/Library/Logs/DicomViewer/queda.log" "$D/queda.log" 2>/dev/null || true
echo "--- [$nome] relatórios de queda do sistema"
for f in "$HOME"/Library/Logs/DiagnosticReports/*; do
  [ -f "$f" ] || continue
  case "$f" in *Ipe*|*ython*) echo "== $f"; head -150 "$f"; cp "$f" "$D/" ;; esac
done
pkill -f "Ipe.app/Contents/MacOS/Ipe" 2>/dev/null || true
[ -n "$P" ] && kill $P 2>/dev/null || true
exit 0
