// 0.100.4: a lupa do Ipê no navegador — segurar o botão do mouse que tem a lupa abre um círculo em volta do
// cursor com a imagem aumentada; a roda, com a lupa aberta, muda o aumento (1,5× a 8×, lembrado). Nas pilhas o
// círculo é tirado dos **pixels da imagem** (como o Ipê: "a imagem em resolução original"), não da tela — numa
// mamografia de 3000 pixels num quadro de 800, a tela já jogou fora o detalhe que a lupa precisa mostrar. Nos
// quadros de volume (MPR, fusão) a lupa aumenta o que está na tela.
import { type Types, utilities as csUtils } from "@cornerstonejs/core";

const CHAVE = "ipe.web.lupa";
const TAMANHO = 240;

function lerAumento(): number {
  try {
    const v = Number(localStorage.getItem(CHAVE));
    if (v >= 1.5 && v <= 8) return v;
  } catch { /* sem armazenamento */ }
  return 3;
}

let aumento = lerAumento();

export function aumentoDaLupa(): number {
  return aumento;
}

type Imagem = { w: number; h: number; dados: ArrayLike<number>; comp: number };

/** Os pixels da imagem mostrada numa pilha (ou null se não há como). */
function pixelsDaPilha(vp: Types.IStackViewport): Imagem | null {
  try {
    const im = vp.getImageData() as unknown as { dimensions: number[]; scalarData?: ArrayLike<number>;
      imageData?: { getPointData(): { getScalars(): { getData(): ArrayLike<number>; getNumberOfComponents(): number } } } };
    const sc = im.imageData?.getPointData().getScalars();
    const dados = im.scalarData ?? sc?.getData();
    if (!dados) return null;
    return { w: im.dimensions[0], h: im.dimensions[1], dados, comp: sc?.getNumberOfComponents() ?? 1 };
  } catch {
    return null;
  }
}

export class Lupa {
  private c: HTMLCanvasElement;
  private ponto: [number, number] = [0, 0];
  private img: Imagem | null;

  constructor(private vp: Types.IViewport, private cel: HTMLElement, private pilha: boolean) {
    this.c = document.createElement("canvas");
    this.c.className = "lupa";
    const dpr = window.devicePixelRatio || 1;
    this.c.width = this.c.height = Math.round(TAMANHO * dpr);
    this.c.style.width = this.c.style.height = `${TAMANHO}px`;
    cel.append(this.c);
    this.img = pilha ? pixelsDaPilha(vp as Types.IStackViewport) : null;
  }

  /** Leva a lupa ao ponto (coordenadas do canvas do quadro) e redesenha. */
  mover(x: number, y: number): void {
    this.ponto = [x, y];
    const r = this.vp.canvas.getBoundingClientRect(), rc = this.cel.getBoundingClientRect();
    this.c.style.left = `${r.left - rc.left + x - TAMANHO / 2}px`;
    this.c.style.top = `${r.top - rc.top + y - TAMANHO / 2}px`;
    this.desenhar();
  }

  /** A roda: muda o aumento (e lembra). */
  roda(delta: number): void {
    aumento = Math.max(1.5, Math.min(8, aumento + (delta < 0 ? 0.5 : -0.5)));
    try { localStorage.setItem(CHAVE, String(aumento)); } catch { /* sem armazenamento */ }
    this.desenhar();
  }

  fechar(): void {
    this.c.remove();
  }

  /** Para os testes: o valor (na imagem) do pixel sob o centro da lupa e o aumento. */
  estado(): { aumento: number; centro: number[] | null; origem: string } {
    const ij = this.paraImagem(this.ponto[0], this.ponto[1]);
    return { aumento, centro: ij ? [Math.floor(ij[0]), Math.floor(ij[1])] : null, origem: this.img ? "imagem" : "tela" };
  }

  private paraImagem(x: number, y: number): number[] | null {
    const id = (this.vp as Types.IStackViewport).getCurrentImageId?.();
    if (!id) return null;
    const w = this.vp.canvasToWorld([x, y] as Types.Point2);
    return csUtils.worldToImageCoords(id, w as Types.Point3) as unknown as number[] | null;
  }

  private desenhar(): void {
    const ctx = this.c.getContext("2d")!;
    const n = this.c.width;
    const dpr = n / TAMANHO;
    const [cx, cy] = this.ponto;
    ctx.clearRect(0, 0, n, n);
    ctx.save();
    ctx.beginPath();
    ctx.arc(n / 2, n / 2, n / 2 - 1, 0, Math.PI * 2);
    ctx.clip();
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, n, n);
    const pronto = this.img ? this.daImagem(ctx, n, dpr, cx, cy) : false;
    if (!pronto) {
      // da tela: o canvas do quadro, aumentado em volta do ponto
      const fonte = this.vp.canvas;
      const k = fonte.width / fonte.clientWidth;
      const lado = (TAMANHO / aumento) * k;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(fonte, cx * k - lado / 2, cy * k - lado / 2, lado, lado, 0, 0, n, n);
    }
    ctx.restore();
    ctx.lineWidth = 2 * dpr;
    ctx.strokeStyle = "rgb(255, 210, 60)";
    ctx.beginPath();
    ctx.arc(n / 2, n / 2, n / 2 - ctx.lineWidth, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "rgb(255, 210, 60)";
    ctx.font = `${12 * dpr}px system-ui, sans-serif`;
    ctx.fillText(`${aumento.toLocaleString(undefined, { maximumFractionDigits: 1 })}×`, n * 0.72, n * 0.93);
  }

  /** A lupa tirada dos pixels da imagem: cada pixel da lupa vai ao pixel da imagem, com a janela e a inversão
   * do quadro. */
  private daImagem(ctx: CanvasRenderingContext2D, n: number, dpr: number, cx: number, cy: number): boolean {
    const img = this.img!;
    const vp = this.vp as Types.IStackViewport;
    const o = this.paraImagem(cx, cy);
    const ox = this.paraImagem(cx + 1, cy);
    const oy = this.paraImagem(cx, cy + 1);
    if (!o || !ox || !oy) return false;
    // um pixel da tela (em volta do ponto) em pixels da imagem; a lupa divide isso pelo aumento
    const ax = [(ox[0] - o[0]) / aumento, (ox[1] - o[1]) / aumento];
    const ay = [(oy[0] - o[0]) / aumento, (oy[1] - o[1]) / aumento];
    const props = vp.getProperties();
    const lo = props.voiRange?.lower ?? 0, hi = props.voiRange?.upper ?? 1;
    const larg = Math.max(1e-6, hi - lo);
    const inverte = !!props.invert;
    const saida = ctx.createImageData(n, n);
    const d = saida.data;
    const { w, h, dados, comp } = img;
    for (let v = 0; v < n; v++) {
      const sy = (v + 0.5) / dpr - TAMANHO / 2;
      for (let u = 0; u < n; u++) {
        const sx = (u + 0.5) / dpr - TAMANHO / 2;
        const px = Math.floor(o[0] + sx * ax[0] + sy * ay[0]);
        const py = Math.floor(o[1] + sx * ax[1] + sy * ay[1]);
        const k = (v * n + u) * 4;
        if (px < 0 || py < 0 || px >= w || py >= h) { d[k + 3] = 255; continue; }
        const idx = (py * w + px) * comp;
        if (comp >= 3) {
          d[k] = dados[idx]; d[k + 1] = dados[idx + 1]; d[k + 2] = dados[idx + 2];
        } else {
          let g = ((dados[idx] - lo) / larg) * 255;
          g = g < 0 ? 0 : g > 255 ? 255 : g;
          if (inverte) g = 255 - g;
          d[k] = d[k + 1] = d[k + 2] = g;
        }
        d[k + 3] = 255;
      }
    }
    // o círculo de recorte do contexto vale para drawImage, não para putImageData: passa por um canvas
    const tmp = document.createElement("canvas");
    tmp.width = tmp.height = n;
    tmp.getContext("2d")!.putImageData(saida, 0, 0);
    ctx.drawImage(tmp, 0, 0);
    return true;
  }
}
