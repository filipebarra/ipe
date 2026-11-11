// 0.100.18: várias janelas, uma por monitor, como no Ipê — a lista fica nesta janela e os exames abrem em uma, duas ou
// três janelas de visualização (cada uma num monitor). Vale para qualquer exame. As janelas ficam abertas entre um
// exame e outro: fechar o exame deixa a janela à espera do próximo, no mesmo monitor.
//
// Onde cada janela abre: com a API de várias telas do navegador (Window Management; o Chrome e o Edge pedem a
// permissão uma vez, e só em HTTPS ou no próprio computador), cada janela vai para um monitor diferente do da lista,
// ocupando-o inteiro. Sem ela, a janela abre onde ficou da última vez (a posição e o tamanho ficam guardados).
import { tr } from "./i18n";

const CHAVE = "ipe.web.janelas";
const CANAL = "ipe-web-janelas";
export const MAX_JANELAS = 3;

export type Recado = { tipo: "abrir"; study: string } | { tipo: "fechar" } | { tipo: "sair" } | { tipo: "aberto"; study: string; janela: number };

let canal: BroadcastChannel | null = null;
export function canalJanelas(): BroadcastChannel | null {
  if (!canal && "BroadcastChannel" in window) canal = new BroadcastChannel(CANAL);
  return canal;
}

/** Quantas janelas de visualização separadas (0 = o exame abre nesta mesma janela). */
export function quantasJanelas(): number {
  try {
    const n = Number(localStorage.getItem(CHAVE) || 0);
    return Number.isFinite(n) ? Math.max(0, Math.min(MAX_JANELAS, Math.round(n))) : 0;
  } catch { return 0; }
}

export function guardarJanelas(n: number): void {
  try { localStorage.setItem(CHAVE, String(Math.max(0, Math.min(MAX_JANELAS, n)))); } catch { /* sem armazenamento */ }
}

/** O número desta janela de visualização (1, 2, 3), ou 0 se é a janela comum (a da lista). */
export function estaJanela(): number {
  const m = /\/j([1-9])$/.exec(location.hash);
  return m ? Number(m[1]) : 0;
}

type Geo = { x: number; y: number; w: number; h: number };
function lerGeo(k: number): Geo | null {
  try {
    const g = JSON.parse(localStorage.getItem(`ipe.web.janela.${k}`) || "null") as Geo | null;
    return g && g.w > 200 && g.h > 200 ? g : null;
  } catch { return null; }
}

/** Numa janela de visualização: guarda onde ela está, para abrir no mesmo lugar da próxima vez. */
export function lembrarPosicao(): void {
  const k = estaJanela();
  if (!k) return;
  const gravar = () => {
    try {
      localStorage.setItem(`ipe.web.janela.${k}`, JSON.stringify({ x: window.screenX, y: window.screenY, w: window.outerWidth, h: window.outerHeight }));
    } catch { /* sem armazenamento */ }
  };
  window.addEventListener("beforeunload", gravar);
  window.addEventListener("resize", gravar);
  window.setInterval(gravar, 5000);
}

const abertas = new Map<number, Window>();

type Tela = { availLeft: number; availTop: number; availWidth: number; availHeight: number };
async function outrasTelas(): Promise<Tela[]> {
  const pedir = (window as unknown as { getScreenDetails?: () => Promise<{ screens: Tela[]; currentScreen: Tela }> }).getScreenDetails;
  if (!pedir) return [];
  try {
    const sd = await Promise.race([pedir.call(window), new Promise<null>((r) => setTimeout(() => r(null), 4000))]);
    if (!sd) return [];
    return sd.screens.filter((s) => s !== sd.currentScreen).sort((a, b) => a.availLeft - b.availLeft);
  } catch {
    return [];              // sem permissão: as janelas ficam onde abriram, e o médico as arrasta uma vez
  }
}

/** Abre (ou reaproveita) as janelas de visualização com o exame. A primeira abre no próprio clique; as outras, uma
 *  de cada vez logo depois (o navegador só deixa uma janela por clique, a não ser que os pop-ups do endereço estejam
 *  permitidos — `aoBloquear` avisa quantas ele barrou). */
export function abrirNasJanelas(study: string, n = quantasJanelas(), aoBloquear: (quantas: number) => void = () => {}): void {
  const faltam: number[] = [];
  for (let k = 1; k <= n; k++) {
    const viva = abertas.get(k);
    if (!viva || viva.closed) faltam.push(k);   // as já abertas recebem o exame pelo canal (sem recarregar)
  }
  canalJanelas()?.postMessage({ tipo: "abrir", study } satisfies Recado);
  const novas: [number, Window][] = [];
  let bloqueadas = 0;
  const abrir = (k: number) => {
    const g = lerGeo(k);
    const geo = g ? `left=${g.x},top=${g.y},width=${g.w},height=${g.h}` : `left=${80 * k},top=${40 * k},width=1280,height=900`;
    const w = window.open(`${location.pathname}#/exame/${study}/j${k}`, `ipe-visor-${k}`, `popup=yes,${geo}`);
    if (!w) { bloqueadas++; return; }
    abertas.set(k, w);
    novas.push([k, w]);
  };
  const fim = () => {
    if (bloqueadas) aoBloquear(bloqueadas);
    // sem posição guardada, cada janela nova vai para um monitor (se o navegador deixar)
    const semLugar = novas.filter(([k]) => !lerGeo(k));
    if (semLugar.length) {
      void outrasTelas().then((telas) => {
        semLugar.forEach(([k, w]) => {
          const t = telas[(k - 1) % Math.max(1, telas.length)];
          if (!t || w.closed) return;
          try { w.moveTo(t.availLeft, t.availTop); w.resizeTo(t.availWidth, t.availHeight); } catch { /* o navegador não deixou */ }
        });
      });
    }
    for (const w of abertas.values()) { try { if (!w.closed) w.focus(); } catch { /* nada */ } }
  };
  const proxima = () => {
    const k = faltam.shift();
    if (k === undefined) { fim(); return; }
    abrir(k);
    if (faltam.length) window.setTimeout(proxima, 250); else fim();
  };
  proxima();
}

/** Fecha o exame em todas as janelas de visualização (elas ficam à espera do próximo). */
export function fecharNasJanelas(): void {
  canalJanelas()?.postMessage({ tipo: "fechar" } satisfies Recado);
}

/** Ao sair do Ipê Web: as janelas de visualização fecham. */
export function sairDasJanelas(): void {
  canalJanelas()?.postMessage({ tipo: "sair" } satisfies Recado);
  for (const w of abertas.values()) { try { w.close(); } catch { /* nada */ } }
  abertas.clear();
}

/** O seletor da lista: onde os exames abrem. */
export function seletorDeJanelas(aoMudar: () => void): HTMLElement {
  const s = document.createElement("select");
  s.className = "janelas";
  s.title = tr("Onde os exames abrem: nesta janela ou em janelas separadas, uma por monitor (a lista continua aqui)");
  s.setAttribute("aria-label", tr("Janelas de visualização"));
  const nomes = [tr("Abrir nesta janela"), tr("1 janela de visualização"), tr("2 janelas de visualização"), tr("3 janelas de visualização")];
  nomes.forEach((nome, i) => s.append(new Option(nome, String(i), false, i === quantasJanelas())));
  s.onchange = () => { guardarJanelas(Number(s.value)); aoMudar(); };
  return s;
}
