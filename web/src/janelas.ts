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
export const MAX_JANELAS = 8;   // 0.100.55: tantas quantas os monitores (era 3)

export type Recado = { tipo: "abrir"; study: string } | { tipo: "fechar" } | { tipo: "sair" } | { tipo: "aberto"; study: string; janela: number }
  | { tipo: "ato"; study: string; janela: number; ato: unknown };

let canal: BroadcastChannel | null = null;
export function canalJanelas(): BroadcastChannel | null {
  if (!canal && "BroadcastChannel" in window) canal = new BroadcastChannel(CANAL);
  return canal;
}

// ---------------------------------------------------------------- 0.100.19: a configuração de monitores (como no Ipê)
/** O que cada janela de visualização apresenta. A ordem da lista é a ordem das janelas (Janela 1, 2, 3). */
export type Papel = "viewer" | "compare" | "off";
export interface ConfJanela { papel: Papel; layout: [number, number] | null; tela: string }
export interface TelaVista { chave: string; rotulo: string; left: number; top: number; w: number; h: number; atual?: boolean; principal?: boolean }
export interface ConfMonitores { separadas: boolean; janelas: ConfJanela[]; telas: TelaVista[] }
const CHAVE_MON = "ipe.web.monitores";

export function lerMonitores(): ConfMonitores {
  let c: Partial<ConfMonitores> | null = null;
  try { c = JSON.parse(localStorage.getItem(CHAVE_MON) || "null") as Partial<ConfMonitores> | null; } catch { c = null; }
  if (!c || !Array.isArray(c.janelas)) {
    // a escolha antiga (0.100.18): só o número de janelas
    let n = 0;
    try { n = Math.max(0, Math.min(MAX_JANELAS, Math.round(Number(localStorage.getItem(CHAVE) || 0)) || 0)); } catch { n = 0; }
    c = { separadas: n > 0, janelas: Array.from({ length: Math.max(1, n) }, () => ({ papel: "viewer" as Papel, layout: null, tela: "" })), telas: [] };
  }
  const n = Math.max(1, Math.min(MAX_JANELAS, c.janelas?.length || 1));
  const janelas = Array.from({ length: n }, (_x, k) => {
    const j = (c!.janelas![k] || {}) as Partial<ConfJanela>;
    const papel: Papel = j.papel === "compare" || j.papel === "off" ? j.papel : "viewer";
    const l = Array.isArray(j.layout) && j.layout.length === 2 ? [Number(j.layout[0]) || 1, Number(j.layout[1]) || 1] as [number, number] : null;
    return { papel: k === 0 && papel === "off" ? "viewer" : papel, layout: l, tela: typeof j.tela === "string" ? j.tela : "" };
  });
  return { separadas: !!c.separadas, janelas, telas: Array.isArray(c.telas) ? c.telas : [] };
}

export function guardarMonitores(c: ConfMonitores): void {
  try { localStorage.setItem(CHAVE_MON, JSON.stringify(c)); } catch { /* sem armazenamento */ }
}

/** As janelas em uso, na ordem (a k-ésima é a "Janela k"). */
export function janelasAtivas(c = lerMonitores()): ConfJanela[] {
  return c.separadas ? c.janelas.filter((j) => j.papel !== "off") : [];
}

/** Quantas janelas de visualização separadas (0 = o exame abre nesta mesma janela). */
export function quantasJanelas(): number {
  return janelasAtivas().length;
}

/** O que a Janela k apresenta (nas janelas de visualização). */
export function configDaJanela(k: number): ConfJanela | null {
  return janelasAtivas()[k - 1] || null;
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

type Tela = { availLeft: number; availTop: number; availWidth: number; availHeight: number; label?: string; isPrimary?: boolean };
type Detalhes = { screens: Tela[]; currentScreen: Tela };
async function detalhes(): Promise<Detalhes | null> {
  const pedir = (window as unknown as { getScreenDetails?: () => Promise<Detalhes> }).getScreenDetails;
  if (!pedir) return null;
  try {
    return await Promise.race([pedir.call(window), new Promise<null>((r) => setTimeout(() => r(null), 6000))]);
  } catch {
    return null;            // sem permissão: as janelas ficam onde abriram, e o médico as arrasta uma vez
  }
}
async function outrasTelas(): Promise<Tela[]> {
  const sd = await detalhes();
  return sd ? sd.screens.filter((s) => s !== sd.currentScreen).sort((a, b) => a.availLeft - b.availLeft) : [];
}

/** O navegador tem a API de várias telas (Chrome e Edge, em HTTPS ou no próprio computador)? */
export function podeVerMonitores(): boolean {
  return typeof (window as unknown as { getScreenDetails?: unknown }).getScreenDetails === "function";
}

/** Pede ao navegador os monitores (ele pergunta uma vez) e devolve a lista, da esquerda para a direita. */
export async function detectarMonitores(): Promise<TelaVista[]> {
  const sd = await detalhes();
  if (!sd) return [];
  return [...sd.screens].sort((a, b) => a.availLeft - b.availLeft || a.availTop - b.availTop).map((t, i) => {
    const w = (t as Tela & { width?: number }).width || t.availWidth, h = (t as Tela & { height?: number }).height || t.availHeight;
    const orient = h > w ? tr("retrato") : tr("paisagem");
    return {
      chave: `${t.availLeft},${t.availTop},${t.availWidth}x${t.availHeight}`,
      rotulo: `${i + 1} — ${t.label || tr("Monitor")} ${w}×${h} (${orient})${t.isPrimary ? ` · ${tr("principal")}` : ""}${t === sd.currentScreen ? ` · ${tr("o desta janela")}` : ""}`,
      left: t.availLeft, top: t.availTop, w: t.availWidth, h: t.availHeight, atual: t === sd.currentScreen, principal: !!t.isPrimary };
  });
}

/** 0.100.55: o navegador já deu a permissão de ver os monitores? (então o painel detecta sozinho, sem perguntar) */
async function permissaoDada(): Promise<boolean> {
  try {
    const st = await navigator.permissions.query({ name: "window-management" as PermissionName });
    return st.state === "granted";
  } catch { return false; }
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
  const conf = lerMonitores();
  const telaDa = (k: number): TelaVista | null => {
    const chave = janelasAtivas(conf)[k - 1]?.tela;
    return (chave && conf.telas.find((t) => t.chave === chave)) || null;
  };
  const abrir = (k: number) => {
    const t = telaDa(k);
    const g = t ? { x: t.left, y: t.top, w: t.w, h: t.h } : lerGeo(k);
    const geo = g ? `left=${g.x},top=${g.y},width=${g.w},height=${g.h}` : `left=${80 * k},top=${40 * k},width=1280,height=900`;
    const w = window.open(`${location.pathname}#/exame/${study}/j${k}`, `ipe-visor-${k}`, `popup=yes,${geo}`);
    if (!w) { bloqueadas++; return; }
    abertas.set(k, w);
    novas.push([k, w]);
  };
  const fim = () => {
    if (bloqueadas) aoBloquear(bloqueadas);
    // sem posição guardada, cada janela nova vai para um monitor (se o navegador deixar)
    // a janela com monitor escolhido vai para ele (o navegador só deixa com a permissão de gerenciar janelas)
    for (const [k, w] of novas) {
      const t = telaDa(k);
      if (t) { try { w.moveTo(t.left, t.top); w.resizeTo(t.w, t.h); } catch { /* o navegador não deixou */ } }
    }
    const semLugar = novas.filter(([k]) => !lerGeo(k) && !telaDa(k));
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

/** O painel "Monitores" da lista: onde os exames abrem, a ordem das janelas, o que cada uma apresenta, o layout e o
 *  monitor de cada uma. Fica guardado neste navegador. */
export function painelMonitores(aoMudar: () => void): HTMLElement {
  const c = lerMonitores();
  const raiz = document.createElement("div");
  raiz.className = "painel-monitores";
  const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", texto = ""): HTMLElementTagNameMap[K] => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (texto) e.textContent = texto;
    return e;
  };
  const gravar = () => { guardarMonitores(c); aoMudar(); };
  const desenhar = () => {
    raiz.replaceChildren();
    raiz.append(el("div", "titulo-painel", tr("Monitores e janelas")));
    const onde = el("select");
    onde.setAttribute("aria-label", tr("Onde os exames abrem"));
    onde.append(new Option(tr("Abrir os exames nesta janela"), "0", false, !c.separadas),
      new Option(tr("Abrir os exames em janelas separadas (a lista continua aqui)"), "1", false, c.separadas));
    onde.onchange = () => { c.separadas = onde.value === "1"; gravar(); desenhar(); };
    raiz.append(onde);
    if (!c.separadas) return;
    const LAYOUTS: [number, number][] = [[1, 1], [1, 2], [2, 1], [2, 2], [1, 3], [2, 3], [3, 3]];
    const seletorLayout = (j: ConfJanela, rotulo: string) => {
      const layout = el("select");
      layout.setAttribute("aria-label", `${tr("Layout")}: ${rotulo}`);
      layout.append(new Option(tr("Padrão"), "", false, !j.layout));
      for (const [r, cc] of LAYOUTS) {
        layout.append(new Option(`${r} × ${cc}`, `${r},${cc}`, false, !!j.layout && j.layout[0] === r && j.layout[1] === cc));
      }
      layout.onchange = () => { j.layout = layout.value ? layout.value.split(",").map(Number) as [number, number] : null; gravar(); };
      layout.disabled = j.papel === "off";
      return layout;
    };
    const nota = el("div", "dica");
    if (c.telas.length) {
      // 0.100.55: com os monitores detectados, uma linha por monitor (resolução e orientação) e o que vai em cada um
      const tab = el("div", "tabela-monitores por-monitor");
      for (const t of [tr("Monitor"), tr("Apresenta"), tr("Layout")]) tab.append(el("div", "th", t));
      const outros = c.telas.filter((t) => !t.atual);
      const papelDe = (t: TelaVista): Papel | "lista" => {
        if (t.atual) return "lista";
        const j = c.janelas.find((x) => x.tela === t.chave);
        return j ? j.papel : "off";
      };
      const refazer = (mudado: TelaVista, papel: Papel) => {
        // as janelas na ordem dos monitores, da esquerda para a direita (Janela 1 = o primeiro monitor em uso)
        const antigas = new Map(c.janelas.map((x) => [x.tela, x] as const));
        const novas: ConfJanela[] = [];
        for (const t of outros) {
          const p = t === mudado ? papel : papelDe(t);
          if (p === "off" || p === "lista") continue;
          novas.push({ papel: p, layout: antigas.get(t.chave)?.layout ?? null, tela: t.chave });
        }
        c.janelas = novas.length ? novas : [{ papel: "viewer", layout: null, tela: "" }];
        gravar();
        desenhar();
      };
      c.telas.forEach((t) => {
        const nome = el("div", "ordem");
        nome.append(el("b", "", t.rotulo));
        const papel = el("select");
        papel.setAttribute("aria-label", `${tr("Apresenta")}: ${tr("Monitor")} ${t.rotulo.split(" ")[0]}`);
        const atual = papelDe(t);
        if (t.atual) {
          papel.append(new Option(tr("A lista (esta janela)"), "lista", false, true));
          papel.disabled = true;
          tab.append(nome, papel, el("div"));
          return;
        }
        const k = c.janelas.findIndex((x) => x.tela === t.chave);
        papel.append(new Option(tr("Exame (visualização)"), "viewer", false, atual === "viewer"),
          new Option(tr("Exame anterior (comparação)"), "compare", false, atual === "compare"),
          new Option(tr("Não usar"), "off", false, atual === "off"));
        papel.onchange = () => refazer(t, papel.value as Papel);
        const j = k >= 0 ? c.janelas[k] : { papel: "off" as Papel, layout: null, tela: t.chave };
        if (k >= 0) nome.append(el("small", "", ` · ${tr("Janela")} ${k + 1}`));
        tab.append(nome, papel, seletorLayout(j, t.rotulo));
      });
      raiz.append(tab);
      if (!outros.length) {
        nota.textContent = tr("Só um monitor: as janelas de visualização abrem neste mesmo monitor (arraste-as para onde quiser — a posição fica guardada).");
        raiz.append(seletorQuantas());
      } else {
        nota.textContent = `${c.telas.length} ${tr("monitor(es) detectado(s), numerados da esquerda para a direita.")}`;
      }
    } else {
      raiz.append(seletorQuantas());
      const tab = el("div", "tabela-monitores");
      for (const t of [tr("Ordem"), tr("Apresenta"), tr("Layout")]) tab.append(el("div", "th", t));
      c.janelas.forEach((j, k) => {
        const ordem = el("div", "ordem");
        ordem.append(el("b", "", `${tr("Janela")} ${k + 1}`));
        const sobe = el("button", "link", "▲"), desce = el("button", "link", "▼");
        sobe.type = desce.type = "button";
        sobe.title = tr("Trocar com a janela de cima");
        desce.title = tr("Trocar com a janela de baixo");
        sobe.disabled = k === 0;
        desce.disabled = k === c.janelas.length - 1;
        const trocar = (a: number, b: number) => { [c.janelas[a], c.janelas[b]] = [c.janelas[b], c.janelas[a]]; gravar(); desenhar(); };
        sobe.onclick = () => trocar(k, k - 1);
        desce.onclick = () => trocar(k, k + 1);
        ordem.append(sobe, desce);
        const papel = el("select");
        papel.setAttribute("aria-label", `${tr("Apresenta")}: ${tr("Janela")} ${k + 1}`);
        papel.append(new Option(tr("Exame (visualização)"), "viewer", false, j.papel === "viewer"),
          new Option(tr("Exame anterior (comparação)"), "compare", false, j.papel === "compare"),
          new Option(tr("Não usar"), "off", false, j.papel === "off"));
        papel.onchange = () => { j.papel = papel.value as Papel; gravar(); desenhar(); };
        tab.append(ordem, papel, seletorLayout(j, `${tr("Janela")} ${k + 1}`));
      });
      raiz.append(tab);
      nota.textContent = podeVerMonitores()
        ? tr("O navegador pergunta uma vez se o Ipê Web pode gerenciar janelas em todas as telas — aí o Ipê vê quantos monitores há, a resolução e a orientação de cada um.")
        : tr("Este navegador não informa os monitores: só o Chrome e o Edge, e só com o Ipê Web em HTTPS (ou aberto no próprio servidor). Escolha quantas janelas quer e arraste cada uma para o monitor dela uma vez — a posição fica guardada.");
    }
    if (podeVerMonitores()) {
      const b = el("button", "", c.telas.length ? tr("Detectar de novo") : tr("Detectar os monitores"));
      b.type = "button";
      b.onclick = () => void detectar(true);
      raiz.append(b);
    }
    raiz.append(nota, el("div", "dica", tr("A Janela 1 começa nas primeiras séries, a 2 nas seguintes. Na mamografia, a Janela 2 é a segunda tela do protocolo. Permita os pop-ups deste endereço para abrir mais de uma janela por clique.")));
  };
  /** Sem a lista dos monitores: quantas janelas de visualização (1 a 8). */
  const seletorQuantas = () => {
    const q = el("select");
    q.setAttribute("aria-label", tr("Quantas janelas de visualização"));
    for (let n = 1; n <= MAX_JANELAS; n++) q.append(new Option(`${n} ${tr(n === 1 ? "janela de visualização" : "janelas de visualização")}`, String(n), false, c.janelas.length === n));
    q.onchange = () => {
      const n = Number(q.value);
      while (c.janelas.length < n) c.janelas.push({ papel: "viewer", layout: null, tela: "" });
      c.janelas = c.janelas.slice(0, n);
      gravar();
      desenhar();
    };
    return q;
  };
  /** Pede os monitores ao navegador; `perguntar` = o médico clicou (sem isso, só se a permissão já foi dada). */
  const detectar = async (perguntar: boolean) => {
    if (!perguntar && !(await permissaoDada())) return;
    const telas = await detectarMonitores();
    if (!telas.length) {
      if (perguntar) {
        const n = raiz.querySelector(".dica");
        if (n) n.textContent = tr("O navegador não deu a lista de monitores (a permissão foi negada?).");
      }
      return;
    }
    const mudou = JSON.stringify(telas.map((t) => t.chave)) !== JSON.stringify(c.telas.map((t) => t.chave));
    c.telas = telas;
    const chaves = new Set(telas.filter((t) => !t.atual).map((t) => t.chave));
    // primeira vez (ou monitores trocados): cada monitor que não é o da lista vira uma janela de visualização
    if (mudou && !c.janelas.some((j) => j.tela && chaves.has(j.tela))) {
      const outros = telas.filter((t) => !t.atual);
      c.janelas = outros.length ? outros.map((t, k) => ({ papel: (c.janelas[k]?.papel ?? "viewer") === "off" ? "viewer" : (c.janelas[k]?.papel ?? "viewer"), layout: c.janelas[k]?.layout ?? null, tela: t.chave }))
        : [{ papel: "viewer", layout: null, tela: "" }];
    } else {
      for (const j of c.janelas) if (j.tela && !chaves.has(j.tela)) j.tela = "";
    }
    gravar();
    desenhar();
  };
  desenhar();
  if (podeVerMonitores()) void detectar(false);
  return raiz;
}

