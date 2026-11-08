// Os metadados DICOM JSON de cada imagem do site (por imageId) — o mesmo que o carregador recebeu.
import type { DicomJson } from "./api";

export const META = new Map<string, DicomJson>();

/** O que o imageId do WADO-RS diz: exame, série, instância e quadro (1 = o primeiro). */
export function partesDoImageId(imageId: string): { study: string; series: string; sop: string; quadro: number } | null {
  const m = imageId.match(/\/studies\/([^/]+)\/series\/([^/]+)\/instances\/([^/]+)\/frames\/(\d+)/);
  return m ? { study: m[1], series: m[2], sop: m[3], quadro: Number(m[4]) } : null;
}
