#!/bin/bash
# Compila o lançador do pacote de casos para cada sistema, em src/ipe/casos/lancadores (o pacote do Ipê leva).
set -e
cd "$(dirname "$0")"
OUT=../../src/ipe/casos/lancadores
mkdir -p "$OUT"
for alvo in windows/amd64 darwin/arm64 darwin/amd64 linux/amd64; do
  os=${alvo%/*}; arch=${alvo#*/}
  ext=""; [ "$os" = windows ] && ext=".exe"
  CGO_ENABLED=0 GOOS=$os GOARCH=$arch go build -trimpath -ldflags "-s -w" -o "$OUT/ipe-casos-$os-$arch$ext" .
done
ls -la "$OUT"
