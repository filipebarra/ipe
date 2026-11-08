// Imagens disponíveis no navegador (0.99.95): enquanto o exame abre, cada série vai sendo baixada e decodificada em
// segundo plano (a que está nos quadros primeiro); a tira e o cabeçalho mostram quanto já está pronto para rolar.

import { Enums, cache, eventTarget, imageLoadPoolManager, imageLoader } from "@cornerstonejs/core";

import { partesDoImageId } from "./meta";

/** acima disto (fração do cache do navegador) a pré-carga para: o que falta vem quando for mostrado */
const LIMITE_CACHE = 0.8;
const PRIORIDADE = 5;

export class Disponiveis {
  /** série -> nº de imagens (quadros); antes dos metadados, o nº de instâncias da busca */
  private total = new Map<string, number>();
  /** série -> imageIds já no cache */
  private prontas = new Map<string, Set<string>>();
  private falhas = new Map<string, number>();
  private parado = false;
  private agendado = false;
  /** a pré-carga parou porque o cache do navegador encheu */
  cheio = false;
  aoMudar: () => void = () => {};
  private readonly add = (e: Event) => {
    const im = (e as CustomEvent).detail?.image as { imageId?: string } | undefined;
    if (im?.imageId) this.marcar(im.imageId, true);
  };
  private readonly rem = (e: Event) => {
    const id = (e as CustomEvent).detail?.imageId as string | undefined;
    if (id) this.marcar(id, false);
  };
  private readonly falhou = (e: Event) => {
    const id = (e as CustomEvent).detail?.imageId as string | undefined;
    const p = id ? partesDoImageId(id) : null;
    if (p && this.total.has(p.series)) {
      this.falhas.set(p.series, (this.falhas.get(p.series) || 0) + 1);
      this.avisar();
    }
  };

  constructor() {
    eventTarget.addEventListener(Enums.Events.IMAGE_CACHE_IMAGE_ADDED, this.add);
    eventTarget.addEventListener(Enums.Events.IMAGE_CACHE_IMAGE_REMOVED, this.rem);
    eventTarget.addEventListener(Enums.Events.IMAGE_LOAD_FAILED, this.falhou);
  }

  /** Antes dos metadados: o tamanho que a busca diz. */
  estimar(series: string, n: number): void {
    if (!this.total.has(series)) this.total.set(series, Math.max(0, n));
    this.avisar();
  }

  /** Com os metadados: o total certo e o que já está no cache. */
  conhecer(series: string, imageIds: string[]): void {
    this.total.set(series, imageIds.length);
    const s = this.prontas.get(series) ?? new Set<string>();
    for (const id of imageIds) if (cache.getImage(id)) s.add(id);
    this.prontas.set(series, s);
    this.avisar();
  }

  private marcar(imageId: string, tem: boolean): void {
    const p = partesDoImageId(imageId);
    if (!p || !this.total.has(p.series)) return;
    const s = this.prontas.get(p.series) ?? new Set<string>();
    if (tem) s.add(imageId);
    else s.delete(imageId);
    this.prontas.set(p.series, s);
    this.avisar();
  }

  private avisar(): void {
    if (this.agendado) return;
    this.agendado = true;
    requestAnimationFrame(() => {
      this.agendado = false;
      this.aoMudar();
    });
  }

  /** 0–100 da série (as que falharam contam como resolvidas), ou null se não se sabe o total. */
  porcentagem(series: string): number | null {
    const t = this.total.get(series);
    if (!t) return null;
    const feitas = Math.min(t, (this.prontas.get(series)?.size || 0) + (this.falhas.get(series) || 0));
    return Math.floor((100 * feitas) / t);
  }

  /** Do exame inteiro. */
  geral(): { feitas: number; total: number; porcentagem: number } {
    let feitas = 0, total = 0;
    for (const [s, t] of this.total) {
      total += t;
      feitas += Math.min(t, (this.prontas.get(s)?.size || 0) + (this.falhas.get(s) || 0));
    }
    return { feitas, total, porcentagem: total ? Math.floor((100 * feitas) / total) : 100 };
  }

  /** Põe na fila de pré-carga (a de menor prioridade do Cornerstone3D: o que está na tela passa na frente). */
  preCarregar(imageIds: string[]): void {
    for (const id of imageIds) {
      if (cache.getImage(id)) continue;
      imageLoadPoolManager.addRequest(async () => {
        if (this.parado || this.cheio) return;
        if (cache.getCacheSize() > LIMITE_CACHE * cache.getMaxCacheSize()) {
          this.cheio = true;
          this.avisar();
          return;
        }
        if (cache.getImage(id) || cache.getImageLoadObject(id)) return;
        try {
          await imageLoader.loadAndCacheImage(id, { priority: PRIORIDADE, requestType: Enums.RequestType.Prefetch } as never);
        } catch { /* conta no IMAGE_LOAD_FAILED */ }
      }, Enums.RequestType.Prefetch, { imageId: id }, PRIORIDADE);
    }
  }

  parar(): void {
    this.parado = true;
    try { imageLoadPoolManager.clearRequestStack(Enums.RequestType.Prefetch); } catch { /* nada */ }
    eventTarget.removeEventListener(Enums.Events.IMAGE_CACHE_IMAGE_ADDED, this.add);
    eventTarget.removeEventListener(Enums.Events.IMAGE_CACHE_IMAGE_REMOVED, this.rem);
    eventTarget.removeEventListener(Enums.Events.IMAGE_LOAD_FAILED, this.falhou);
  }
}
