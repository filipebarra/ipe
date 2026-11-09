// Menus suspensos do Ipê Web (0.99.97): o menu do botão direito na imagem e os menus dos ícones da barra.
// Um menu por vez; submenus abrem ao passar o mouse (ou com a seta para a direita); Esc ou clicar fora fecha.

export interface ItemMenu {
  rotulo?: string;
  /** caminho SVG (24×24, traço) do ícone, opcional */
  icone?: string;
  /** texto à direita (o valor atual, uma dica) */
  dica?: string;
  acao?: () => void;
  sub?: ItemMenu[];
  marcado?: boolean;
  perigo?: boolean;
  desligado?: boolean;
  separador?: boolean;
  /** título de seção (não clicável) */
  titulo?: string;
}

let aberto: HTMLElement[] = [];
let fechar: (() => void) | null = null;

export function icone(d: string, tam = 16): SVGSVGElement {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("width", String(tam));
  svg.setAttribute("height", String(tam));
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.7");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", d);
  svg.append(p);
  return svg;
}

export function fecharMenus(): void {
  for (const m of aberto) m.remove();
  aberto = [];
  fechar?.();
  fechar = null;
}

function posicionar(m: HTMLElement, x: number, y: number, ancora?: DOMRect): void {
  document.body.append(m);
  const r = m.getBoundingClientRect();
  const W = window.innerWidth, H = window.innerHeight;
  let left = x, top = y;
  if (ancora) {
    left = ancora.right - 2;
    top = ancora.top - 6;
    if (left + r.width > W - 4) left = ancora.left - r.width + 2;
  } else if (left + r.width > W - 4) {
    left = Math.max(4, W - r.width - 4);
  }
  if (top + r.height > H - 4) top = Math.max(4, H - r.height - 4);
  m.style.left = `${left}px`;
  m.style.top = `${top}px`;
}

function construir(itens: ItemMenu[], nivel: number, rotulo: string): HTMLElement {
  const m = document.createElement("div");
  m.className = "menu";
  m.setAttribute("role", "menu");
  m.setAttribute("aria-label", rotulo);
  m.tabIndex = -1;
  for (const it of itens) {
    if (it.separador) {
      const s = document.createElement("div");
      s.className = "menu-sep";
      s.setAttribute("role", "separator");
      m.append(s);
      continue;
    }
    if (it.titulo) {
      const t = document.createElement("div");
      t.className = "menu-titulo";
      t.textContent = it.titulo;
      m.append(t);
      continue;
    }
    const b = document.createElement("button");
    b.type = "button";
    b.className = "menu-item" + (it.perigo ? " perigo" : "") + (it.marcado ? " marcado" : "");
    b.setAttribute("role", it.marcado !== undefined ? "menuitemradio" : "menuitem");
    if (it.marcado !== undefined) b.setAttribute("aria-checked", String(!!it.marcado));
    if (it.desligado) b.disabled = true;
    const ic = document.createElement("span");
    ic.className = "menu-icone";
    if (it.icone) ic.append(icone(it.icone));
    else if (it.marcado) ic.textContent = "●";
    const rot = document.createElement("span");
    rot.className = "menu-rotulo";
    rot.textContent = it.rotulo || "";
    b.append(ic, rot);
    if (it.dica) {
      const d = document.createElement("span");
      d.className = "menu-dica";
      d.textContent = it.dica;
      b.append(d);
    }
    if (it.sub) {
      b.setAttribute("aria-haspopup", "menu");
      b.append(icone("M9 6l6 6-6 6", 12));
      const abrirSub = () => {
        for (const x of aberto.slice(nivel + 1)) x.remove();
        aberto = aberto.slice(0, nivel + 1);
        for (const irmao of m.querySelectorAll(".menu-item.aberto")) irmao.classList.remove("aberto");
        b.classList.add("aberto");
        const sm = construir(it.sub!, nivel + 1, it.rotulo || "");
        aberto.push(sm);
        posicionar(sm, 0, 0, b.getBoundingClientRect());
        return sm;
      };
      b.addEventListener("mouseenter", () => { abrirSub(); });
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        const sm = abrirSub();
        (sm.querySelector(".menu-item:not([disabled])") as HTMLElement | null)?.focus();
      });
      b.addEventListener("keydown", (e) => {
        if (e.key === "ArrowRight") {
          e.preventDefault();
          const sm = abrirSub();
          (sm.querySelector(".menu-item:not([disabled])") as HTMLElement | null)?.focus();
        }
      });
    } else {
      b.addEventListener("mouseenter", () => {
        for (const x of aberto.slice(nivel + 1)) x.remove();
        aberto = aberto.slice(0, nivel + 1);
        for (const irmao of m.querySelectorAll(".menu-item.aberto")) irmao.classList.remove("aberto");
      });
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        fecharMenus();
        it.acao?.();
      });
    }
    m.append(b);
  }
  m.addEventListener("keydown", (e) => {
    const botoes = [...m.querySelectorAll<HTMLElement>(".menu-item:not([disabled])")];
    const i = botoes.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") { e.preventDefault(); botoes[(i + 1) % botoes.length]?.focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); botoes[(i - 1 + botoes.length) % botoes.length]?.focus(); }
    else if (e.key === "ArrowLeft" && nivel > 0) {
      e.preventDefault();
      m.remove();
      aberto = aberto.slice(0, nivel);
      (aberto[nivel - 1]?.querySelector(".menu-item.aberto") as HTMLElement | null)?.focus();
    } else if (e.key === "Escape") { e.preventDefault(); fecharMenus(); }
  });
  return m;
}

/** Abre um menu em (x, y) da página — ou logo abaixo de `ancora` (um botão da barra). */
export function abrirMenu(itens: ItemMenu[], x: number, y: number, rotulo = "Menu", ancora?: HTMLElement): HTMLElement {
  fecharMenus();
  const m = construir(itens, 0, rotulo);
  aberto = [m];
  if (ancora) {
    const r = ancora.getBoundingClientRect();
    posicionar(m, r.left, r.bottom + 4);
  } else {
    posicionar(m, x, y);
  }
  const fora = (e: MouseEvent) => {
    if (aberto.some((a) => a.contains(e.target as Node))) return;
    if (ancora && ancora.contains(e.target as Node)) return;
    fecharMenus();
  };
  const esc = (e: KeyboardEvent) => { if (e.key === "Escape") fecharMenus(); };
  // no próximo ciclo: o mesmo clique que abriu não fecha
  setTimeout(() => {
    document.addEventListener("mousedown", fora, true);
    document.addEventListener("keydown", esc, true);
  }, 0);
  const rolar = () => fecharMenus();
  window.addEventListener("resize", rolar);
  fechar = () => {
    document.removeEventListener("mousedown", fora, true);
    document.removeEventListener("keydown", esc, true);
    window.removeEventListener("resize", rolar);
  };
  (m.querySelector(".menu-item:not([disabled])") as HTMLElement | null)?.focus({ preventScroll: true });
  return m;
}

/** Abre um painel livre (a grade de layout, por exemplo) abaixo de um botão, com as mesmas regras de fechar. */
export function abrirPainel(conteudo: HTMLElement, ancora: HTMLElement, rotulo: string): HTMLElement {
  fecharMenus();
  const m = document.createElement("div");
  m.className = "menu painel";
  m.setAttribute("role", "dialog");
  m.setAttribute("aria-label", rotulo);
  m.append(conteudo);
  aberto = [m];
  const r = ancora.getBoundingClientRect();
  posicionar(m, r.left, r.bottom + 4);
  const fora = (e: MouseEvent) => {
    if (m.contains(e.target as Node) || ancora.contains(e.target as Node)) return;
    fecharMenus();
  };
  const esc = (e: KeyboardEvent) => { if (e.key === "Escape") fecharMenus(); };
  setTimeout(() => {
    document.addEventListener("mousedown", fora, true);
    document.addEventListener("keydown", esc, true);
  }, 0);
  fechar = () => {
    document.removeEventListener("mousedown", fora, true);
    document.removeEventListener("keydown", esc, true);
  };
  return m;
}
