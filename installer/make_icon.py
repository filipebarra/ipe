"""Gera `installer/ipe.ico` a partir do ícone que o programa já desenha.

O ícone é vetorial e vive em `ui/icons.py`; aqui ele só é rasterizado nos tamanhos que o
Windows usa. Assim não há arquivo de imagem de terceiros no projeto, e o ícone do atalho é
o mesmo da janela.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TAMANHOS = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QApplication

    from ipe.ui.icons import _draw

    QApplication.instance() or QApplication([])
    destino = Path(__file__).resolve().parent / "ipe.ico"
    pngs = []
    for lado in TAMANHOS:
        pm = QPixmap(lado, lado)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.scale(lado / 64.0, lado / 64.0)
        _draw("app", p)
        p.end()
        pngs.append((lado, pm))
    # o Qt não grava .ico: monta o arquivo na mão (cabeçalho ICO + PNG por tamanho)
    import struct
    from PySide6.QtCore import QBuffer, QByteArray
    blocos = []
    for lado, pm in pngs:
        # o QByteArray precisa ficar vivo enquanto o QBuffer existir: passar um temporário
        # derruba o processo com falha de segmentação
        dados = QByteArray()
        buf = QBuffer(dados)
        buf.open(QBuffer.WriteOnly)
        pm.save(buf, "PNG")
        buf.close()
        blocos.append((lado, bytes(dados)))
    cabecalho = struct.pack("<HHH", 0, 1, len(blocos))
    offset = len(cabecalho) + 16 * len(blocos)
    entradas, corpo = b"", b""
    for lado, dados in blocos:
        entradas += struct.pack("<BBBBHHII", lado if lado < 256 else 0, lado if lado < 256 else 0,
                                0, 0, 1, 32, len(dados), offset)
        corpo += dados
        offset += len(dados)
    destino.write_bytes(cabecalho + entradas + corpo)
    print(f"{destino} — {len(blocos)} tamanhos, {destino.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
