// Cronômetro da carga das imagens (0.99.96): quanto chegou pela rede, em quanto tempo, quanto o navegador levou para
// decodificar e em que sintaxe — para saber se o que pesa é a rede ou a decodificação.

import { Enums, eventTarget } from "@cornerstonejs/core";

const NOMES_TS: Record<string, string> = {
  "1.2.840.10008.1.2": "sem compressão",
  "1.2.840.10008.1.2.1": "sem compressão",
  "1.2.840.10008.1.2.4.80": "JPEG-LS",
  "1.2.840.10008.1.2.4.81": "JPEG-LS (perda)",
  "1.2.840.10008.1.2.4.90": "JPEG 2000",
  "1.2.840.10008.1.2.4.91": "JPEG 2000 (perda)",
  "1.2.840.10008.1.2.4.201": "HTJ2K",
  "1.2.840.10008.1.2.4.202": "HTJ2K",
  "1.2.840.10008.1.2.4.203": "HTJ2K (perda)",
  "1.2.840.10008.1.2.4.50": "JPEG",
  "1.2.840.10008.1.2.4.70": "JPEG sem perda",
  "1.2.840.10008.1.2.5": "RLE",
};

export interface Resumo {
  imagens: number;
  pedidos: number;
  /** bytes que vieram pela rede (o que veio do cache do navegador não conta) */
  bytesRede: number;
  /** pedidos respondidos pelo cache do navegador (304 ou sem rede) */
  doCache: number;
  /** da primeira à última resposta, em segundos */
  segundos: number;
  mbPorSegundo: number;
  redeMediaMs: number;
  decodificacaoMediaMs: number;
  sintaxes: Record<string, number>;
}

export class Cronometro {
  private pedidos: { bytes: number; ms: number; ini: number; fim: number; cache: boolean }[] = [];
  private decod: number[] = [];
  private sintaxes: Record<string, number> = {};
  private imagens = 0;
  private obs: PerformanceObserver | null = null;
  private readonly carregou = (e: Event) => {
    const im = (e as CustomEvent).detail?.image as {
      decodeTimeInMS?: number; transferSyntaxUID?: string; imageQualityStatus?: number;
    } | undefined;
    if (!im) return;
    this.imagens++;
    if (typeof im.decodeTimeInMS === "number") this.decod.push(im.decodeTimeInMS);
    const n = NOMES_TS[im.transferSyntaxUID || ""] || im.transferSyntaxUID || "?";
    this.sintaxes[n] = (this.sintaxes[n] || 0) + 1;
  };

  constructor() {
    eventTarget.addEventListener(Enums.Events.IMAGE_LOADED, this.carregou);
    try {
      this.obs = new PerformanceObserver((lista) => {
        for (const e of lista.getEntries() as PerformanceResourceTiming[]) {
          if (!e.name.includes("/frames/")) continue;
          const cache = e.transferSize === 0 || (e.transferSize > 0 && e.transferSize < 1000 && e.encodedBodySize > 1000);
          this.pedidos.push({ bytes: cache ? 0 : e.encodedBodySize || e.transferSize, ms: e.duration,
            ini: e.startTime, fim: e.responseEnd, cache });
        }
      });
      this.obs.observe({ type: "resource", buffered: false });
    } catch { /* navegador sem PerformanceObserver: só a decodificação */ }
    try { performance.setResourceTimingBufferSize(20000); } catch { /* nada */ }
  }

  resumo(): Resumo {
    const p = this.pedidos;
    const ini = p.length ? Math.min(...p.map((x) => x.ini)) : 0;
    const fim = p.length ? Math.max(...p.map((x) => x.fim)) : 0;
    const bytes = p.reduce((a, x) => a + x.bytes, 0);
    const seg = Math.max(0.001, (fim - ini) / 1000);
    const media = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
    return {
      imagens: this.imagens, pedidos: p.length, bytesRede: bytes, doCache: p.filter((x) => x.cache).length,
      segundos: p.length ? seg : 0, mbPorSegundo: p.length ? bytes / 1e6 / seg : 0,
      redeMediaMs: media(p.map((x) => x.ms)), decodificacaoMediaMs: media(this.decod), sintaxes: { ...this.sintaxes },
    };
  }

  texto(tr: (s: string) => string): string {
    const r = this.resumo();
    const sint = Object.entries(r.sintaxes).map(([k, v]) => `${tr(k)} ${v}`).join(", ") || "—";
    return [
      `${tr("Imagens")}: ${r.imagens} · ${tr("pedidos")}: ${r.pedidos} (${tr("do cache do navegador")}: ${r.doCache})`,
      `${tr("Rede")}: ${(r.bytesRede / 1e6).toFixed(1)} MB ${tr("em")} ${r.segundos.toFixed(1)} s = ${r.mbPorSegundo.toFixed(1)} MB/s · ` +
        `${tr("por pedido")} ${r.redeMediaMs.toFixed(0)} ms`,
      `${tr("Decodificação")}: ${r.decodificacaoMediaMs.toFixed(1)} ms ${tr("por imagem")} · ${sint}`,
    ].join("\n");
  }

  parar(): void {
    eventTarget.removeEventListener(Enums.Events.IMAGE_LOADED, this.carregou);
    this.obs?.disconnect();
  }
}
