// 0.100.53: a barra de cima em telas menores. Pedido dele: em 1366 × 768 os botões da direita (Laudo, Enviar, CAD/IA…)
// ficavam escondidos, alcançáveis só rolando a barra de lado. Agora a barra mostra o que cabe, na ordem, e o resto vai
// para o botão "»" no fim, que abre um menu com esses botões (o mesmo rótulo, o mesmo ícone, a mesma ação).
import { abrirMenu, icone, type ItemMenu } from "./menu";
import { tr } from "./i18n";

const ESCONDIDO = "transbordou";

function visivelNoLayout(b: HTMLElement): boolean {
  if (b.classList.contains(ESCONDIDO)) return true;               // escondido por nós: conta como da barra
  const st = getComputedStyle(b);
  return st.display !== "none" && st.visibility !== "hidden" && !b.hidden;
}

/** Os botões da barra, na ordem, que fazem parte dela agora (os que o exame não usa ficam de fora). */
function botoes(nav: HTMLElement, mais: HTMLElement): HTMLButtonElement[] {
  return [...nav.querySelectorAll<HTMLButtonElement>("button")].filter((b) => b !== mais && !mais.contains(b)
    && !b.closest(".so-cel") && visivelNoLayout(b));
}

function rotuloDe(b: HTMLButtonElement): string {
  return b.getAttribute("aria-label") || b.title || (b.textContent || "").trim() || "?";
}

function acionar(b: HTMLButtonElement): void {
  if (b.disabled) return;
  // as ferramentas do botão esquerdo escolhem no mousedown; os outros botões, no clique
  if (b.onmousedown) b.dispatchEvent(new MouseEvent("mousedown", { button: 0, bubbles: true, cancelable: true }));
  else b.click();
}

/** Liga o "»" à barra `nav`; devolve a função que refaz a conta (chamada sozinha ao mudar o tamanho). */
export function barraComTransbordo(nav: HTMLElement): { mais: HTMLButtonElement; ajustar: () => void } {
  const mais = document.createElement("button");
  mais.type = "button";
  mais.className = "ic mais";
  mais.setAttribute("aria-label", tr("Mais botões"));
  mais.title = tr("Mais botões (os que não couberam na barra)");
  mais.append(icone("M6 7l5 5-5 5M13 7l5 5-5 5", 20));
  mais.hidden = true;
  nav.append(mais);

  let pedido = 0;
  let ajustando = false;
  const ajustar = () => {
    if (ajustando) return;
    ajustando = true;
    try {
      const lista = botoes(nav, mais);
      for (const b of lista) b.classList.remove(ESCONDIDO);
      for (const g of nav.querySelectorAll(".grupo")) g.classList.remove(ESCONDIDO);
      mais.hidden = true;
      if (nav.scrollWidth <= nav.clientWidth + 1) return;
      mais.hidden = false;
      // tira do fim para o começo até caber (o "»" ocupa o lugar dos que saem)
      for (let i = lista.length - 1; i >= 0 && nav.scrollWidth > nav.clientWidth + 1; i--) {
        lista[i].classList.add(ESCONDIDO);
        const g = lista[i].closest(".grupo");
        if (g && ![...g.querySelectorAll("button")].some((x) => visivelNoLayout(x as HTMLElement)
            && !(x as HTMLElement).classList.contains(ESCONDIDO))) g.classList.add(ESCONDIDO);
      }
    } finally {
      ajustando = false;
    }
  };
  const agendar = () => {
    cancelAnimationFrame(pedido);
    pedido = requestAnimationFrame(ajustar);
  };
  new ResizeObserver(agendar).observe(nav);
  window.addEventListener("resize", agendar);
  // botões que aparecem ou somem conforme o exame (Densidade só na mamografia, por exemplo)
  new MutationObserver(agendar).observe(nav, { subtree: true, attributes: true, attributeFilter: ["style", "hidden"] });

  mais.onclick = () => {
    const itens: ItemMenu[] = [];
    let grupo: Element | null = null;
    for (const b of botoes(nav, mais).filter((x) => x.classList.contains(ESCONDIDO))) {
      const g = b.closest(".grupo");
      if (grupo && g !== grupo) itens.push({ separador: true });
      grupo = g;
      itens.push({
        rotulo: rotuloDe(b), icone: b.querySelector("path")?.getAttribute("d") || undefined,
        marcado: b.classList.contains("ligado") || b.getAttribute("aria-pressed") === "true",
        desligado: b.disabled, acao: () => acionar(b),
      });
    }
    abrirMenu(itens, 0, 0, tr("Mais botões"), mais);
  };
  agendar();
  return { mais, ajustar };
}
