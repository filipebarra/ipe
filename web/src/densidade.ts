// 0.100.50: a densidade mamária no navegador — o botão Densidade do Ipê de mesa. A rede da NYU mede no servidor as
// quatro incidências 2D do exame (fica guardado no exame); o médico confirma a categoria, ou troca, e pode mandar a
// composição ao laudo BI-RADS. A mesma medida e a mesma confirmação do Ipê.
import { cabecalhos } from "./api";
import { tr } from "./i18n";

export interface MedidaDensidade {
  nyu: string | null;
  nyu_probs: number[];
  nyu_aviso: string;
  avisos: string[];
  aparelho: string;
  quando: string;
  categoria?: string;
  estado?: string;
  revisor?: string;
  confirmado_em?: string;
  frase: string;
}

export interface RespostaDensidade {
  medida: MedidaDensidade | null;
  pode_confirmar: boolean;
  frases?: Record<string, string>;
}

const CATS = ["a", "b", "c", "d"] as const;
const NOMES: Record<string, string> = {
  a: "quase inteiramente adiposa", b: "áreas esparsas de densidade fibroglandular",
  c: "heterogeneamente densa", d: "extremamente densa",
};

async function pedirJson(caminho: string, corpo?: unknown): Promise<RespostaDensidade> {
  const r = await fetch(`${location.origin}${caminho}`, {
    method: corpo === undefined ? "GET" : "POST", cache: "no-store",
    headers: { ...cabecalhos(), ...(corpo === undefined ? {} : { "Content-Type": "application/json" }) },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.text()) || msg; } catch { /* sem corpo */ }
    try { msg = (JSON.parse(msg) as { error?: string }).error || msg; } catch { /* texto */ }
    throw new Error(msg);
  }
  return (await r.json()) as RespostaDensidade;
}

export const verDensidade = (study: string) => pedirJson(`/api/web/densidade?study=${encodeURIComponent(study)}`);
export const medirDensidade = (study: string, deNovo = false) => pedirJson("/api/web/densidade/medir", { study, de_novo: deNovo });
export const confirmarDensidade = (study: string, categoria: string) =>
  pedirJson("/api/web/densidade/confirmar", { study, categoria });

/** O painel da densidade. `aoLaudo(categoria, frase)` põe a composição no laudo e diz se conseguiu. */
export class PainelDensidade {
  readonly raiz = document.createElement("div");
  private resp: RespostaDensidade | null = null;
  private escolhida = "";
  private ocupado = false;

  /** 0.100.57: depois de confirmar (o Ipê Web abre as calcificações em seguida, quando também esperam) */
  aoConfirmar: (() => void) | null = null;

  constructor(private study: string, private aoLaudo: (categoria: string, frase: string) => Promise<boolean>) {
    this.raiz.className = "painel-densidade";
    (window as unknown as Record<string, unknown>).__ipeDensidade = this; // testes
  }

  async abrir(): Promise<void> {
    this.desenhar(tr("Procurando a medida guardada…"));
    try {
      this.resp = await verDensidade(this.study);
      if (!this.resp.medida) await this.medir(false);
      else this.desenhar();
    } catch (e) {
      this.desenhar(`${tr("Não deu para falar com o servidor:")} ${(e as Error).message}`);
    }
  }

  private async medir(deNovo: boolean): Promise<void> {
    this.ocupado = true;
    this.desenhar(tr("Medindo no servidor (a rede da NYU nas quatro incidências)…"));
    try {
      this.resp = await medirDensidade(this.study, deNovo);
      this.escolhida = "";
      this.desenhar();
    } catch (e) {
      this.desenhar(`${tr("A medida falhou:")} ${(e as Error).message}`);
    } finally {
      this.ocupado = false;
      this.desenhar();
    }
  }

  private async confirmar(laudo: boolean): Promise<void> {
    const cat = this.escolhida || this.resp?.medida?.categoria || this.resp?.medida?.nyu || "";
    if (!cat) return;
    this.ocupado = true;
    try {
      this.resp = await confirmarDensidade(this.study, cat);
      let msg = `${tr("Confirmado:")} ${cat.toUpperCase()}.`;
      if (laudo) {
        const frase = this.resp.frases?.[cat] || this.resp.medida?.frase || "";
        msg += (await this.aoLaudo(cat, frase)) ? ` ${tr("A composição foi para o laudo.")}`
          : ` ${tr("O laudo não está aberto para escrever: a frase não foi.")}`;
      }
      this.ocupado = false;
      this.desenhar(msg);
      this.aoConfirmar?.();
    } catch (e) {
      this.ocupado = false;
      this.desenhar(`${tr("Não confirmou:")} ${(e as Error).message}`);
    }
  }

  private desenhar(aviso = ""): void {
    const r = this.raiz;
    r.replaceChildren();
    const h = document.createElement("strong");
    h.textContent = tr("Densidade mamária (rede da NYU)");
    r.append(h);
    const m = this.resp?.medida;
    if (m) {
      const linha = document.createElement("div");
      linha.className = "rede";
      if (m.nyu) {
        const p = Math.max(...(m.nyu_probs.length ? m.nyu_probs : [0]));
        linha.textContent = `${m.nyu.toUpperCase()} — ${tr(NOMES[m.nyu] || "")} (${Math.round(100 * p)}%)`;
      } else {
        linha.textContent = `${tr("A rede não mediu:")} ${m.nyu_aviso || tr("sem as incidências")}`;
      }
      r.append(linha);
      if (m.nyu_probs.length === 4) {
        const probs = document.createElement("div");
        probs.className = "probs";
        CATS.forEach((c, i) => {
          const b = document.createElement("span");
          const v = Math.round(100 * m.nyu_probs[i]);
          b.textContent = `${c.toUpperCase()} ${v}%`;
          b.style.setProperty("--p", `${v}%`);
          if (c === m.nyu) b.className = "maior";
          probs.append(b);
        });
        r.append(probs);
      }
      const atual = this.escolhida || m.categoria || m.nyu || "";
      const grupo = document.createElement("div");
      grupo.className = "categorias";
      grupo.setAttribute("role", "radiogroup");
      grupo.setAttribute("aria-label", tr("Categoria"));
      for (const c of CATS) {
        const lb = document.createElement("label");
        const rb = document.createElement("input");
        rb.type = "radio";
        rb.name = "densidade";
        rb.value = c;
        rb.checked = c === atual;
        rb.disabled = !this.resp?.pode_confirmar || this.ocupado;
        rb.onchange = () => { this.escolhida = c; };
        lb.append(rb, ` ${c.toUpperCase()}`);
        lb.title = tr(NOMES[c]);
        grupo.append(lb);
      }
      r.append(grupo);
      const info = document.createElement("div");
      info.className = "info";
      const partes = [];
      if (m.categoria) partes.push(`${tr("Confirmada:")} ${m.categoria.toUpperCase()}${m.revisor ? ` ${tr("por")} ${m.revisor}` : ""}${m.confirmado_em ? ` ${tr("em")} ${m.confirmado_em}` : ""}`);
      else partes.push(tr("Ainda não confirmada."));
      if (m.aparelho) partes.push(m.aparelho);
      if (m.quando) partes.push(`${tr("medida em")} ${m.quando}`);
      info.textContent = partes.join(" · ");
      r.append(info);
      for (const a of m.avisos || []) {
        const d = document.createElement("div");
        d.className = "aviso";
        d.textContent = tr(a);
        r.append(d);
      }
      const botoes = document.createElement("div");
      botoes.className = "botoes";
      const bt = (rot: string, fn: () => void, desligado = false) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = tr(rot);
        b.disabled = desligado || this.ocupado;
        b.onclick = fn;
        botoes.append(b);
        return b;
      };
      const semPerm = !this.resp?.pode_confirmar || !m.nyu;
      bt("Confirmar", () => void this.confirmar(false), semPerm);
      bt("Confirmar e mandar ao laudo", () => void this.confirmar(true), semPerm);
      bt("Medir de novo", () => void this.medir(true));
      r.append(botoes);
      if (!this.resp?.pode_confirmar) {
        const d = document.createElement("div");
        d.className = "aviso";
        d.textContent = tr("Confirmar pede a permissão de escrever laudos.");
        r.append(d);
      }
    }
    if (aviso) {
      const d = document.createElement("div");
      d.className = "estado";
      d.setAttribute("role", "status");
      d.textContent = aviso;
      r.append(d);
    }
  }
}
