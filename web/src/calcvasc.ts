// 0.100.51: calcificações vasculares da mama no navegador — o botão do Ipê de mesa. A rede (SCU-Net) mede no
// servidor as quatro incidências; aqui as prévias com o que ela marcou, a área por mama, a sugestão provisória e o
// grau do médico (ausente, leve, moderada, acentuada), que pode ir ao laudo.
import { cabecalhos } from "./api";
import { tr } from "./i18n";

interface Medida {
  sugestao: string | null;
  area_mm2: number | null;
  por_mama: Record<string, number>;
  aviso: string;
  avisos: string[];
  aparelho: string;
  quando: string;
  grau?: string;
  revisor?: string;
  confirmado_em?: string;
  vistas: Record<string, { area_mm2: number; protese: boolean }>;
}
interface Resposta { medida: Medida | null; pode_confirmar: boolean; frases?: Record<string, string> }

const GRAUS = ["ausente", "leve", "moderada", "acentuada"] as const;
const NOMES: Record<string, string> = { ausente: "Ausente", leve: "Leve", moderada: "Moderada", acentuada: "Acentuada" };
const VISTAS: [string, string][] = [["R-CC", "CC direita"], ["L-CC", "CC esquerda"], ["R-MLO", "MLO direita"], ["L-MLO", "MLO esquerda"]];

async function pedir(caminho: string, corpo?: unknown): Promise<Resposta> {
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
  return (await r.json()) as Resposta;
}

export class PainelCalcVascular {
  readonly raiz = document.createElement("div");
  private resp: Resposta | null = null;
  private escolhido = "";
  private ocupado = false;
  private urls: string[] = [];

  constructor(private study: string, private aoLaudo: (frase: string) => Promise<boolean>) {
    this.raiz.className = "painel-calcvasc";
    (window as unknown as Record<string, unknown>).__ipeCalcVasc = this; // testes
  }

  async abrir(): Promise<void> {
    this.desenhar(tr("Procurando a medida guardada…"));
    try {
      this.resp = await pedir(`/api/web/calcvasc?study=${encodeURIComponent(this.study)}`);
      if (!this.resp.medida) await this.medir(false);
      else this.desenhar();
    } catch (e) {
      this.desenhar(`${tr("Não deu para falar com o servidor:")} ${(e as Error).message}`);
    }
  }

  private async medir(deNovo: boolean): Promise<void> {
    this.ocupado = true;
    this.desenhar(tr("Procurando calcificações vasculares no servidor (as quatro incidências)…"));
    try {
      this.resp = await pedir("/api/web/calcvasc/medir", { study: this.study, de_novo: deNovo });
      this.escolhido = "";
      this.ocupado = false;
      this.desenhar();
    } catch (e) {
      this.ocupado = false;
      this.desenhar(`${tr("A medida falhou:")} ${(e as Error).message}`);
    }
  }

  private async confirmar(laudo: boolean): Promise<void> {
    const g = this.escolhido || this.resp?.medida?.grau || this.resp?.medida?.sugestao || "";
    if (!g) { this.desenhar(tr("Marque um grau.")); return; }
    this.ocupado = true;
    try {
      this.resp = await pedir("/api/web/calcvasc/confirmar", { study: this.study, grau: g });
      let msg = `${tr("Confirmado:")} ${tr(NOMES[g])}.`;
      if (laudo) {
        msg += (await this.aoLaudo(this.resp.frases?.[g] || "")) ? ` ${tr("A frase foi para o laudo.")}`
          : ` ${tr("O laudo não está aberto para escrever: a frase não foi.")}`;
      }
      this.ocupado = false;
      this.desenhar(msg);
    } catch (e) {
      this.ocupado = false;
      this.desenhar(`${tr("Não confirmou:")} ${(e as Error).message}`);
    }
  }

  private async previa(img: HTMLImageElement, vista: string): Promise<void> {
    try {
      const r = await fetch(`${location.origin}/api/web/calcvasc/previa?study=${encodeURIComponent(this.study)}&vista=${vista}`,
        { headers: cabecalhos(), cache: "no-store" });
      if (!r.ok) return;
      const u = URL.createObjectURL(await r.blob());
      this.urls.push(u);
      img.src = u;
    } catch { /* sem prévia */ }
  }

  private desenhar(aviso = ""): void {
    for (const u of this.urls) URL.revokeObjectURL(u);
    this.urls = [];
    const r = this.raiz;
    r.replaceChildren();
    const h = document.createElement("strong");
    h.textContent = tr("Calcificações vasculares (rede SCU-Net)");
    r.append(h);
    const m = this.resp?.medida;
    if (m) {
      const grade = document.createElement("div");
      grade.className = "previas";
      for (const [k, rot] of VISTAS) {
        const fig = document.createElement("figure");
        const img = document.createElement("img");
        img.alt = tr(rot);
        const cap = document.createElement("figcaption");
        const v = m.vistas?.[k];
        cap.textContent = v ? `${tr(rot)} — ${Math.round(v.area_mm2)} mm²` : `${tr(rot)} — ${tr("sem esta incidência")}`;
        fig.append(img, cap);
        grade.append(fig);
        if (v) void this.previa(img, k);
      }
      r.append(grade);
      const linha = document.createElement("div");
      linha.className = "rede";
      if (m.aviso) linha.textContent = `${tr("A rede não rodou:")} ${tr(m.aviso)}`;
      else {
        const sug = m.sugestao ? tr(NOMES[m.sugestao]) : tr("nenhuma");
        linha.textContent = `${tr("Sugestão")}: ${sug} (${tr("provisória, pela área dos trechos alongados")})`;
      }
      r.append(linha);
      const atual = this.escolhido || m.grau || m.sugestao || "";
      const grupo = document.createElement("div");
      grupo.className = "categorias";
      grupo.setAttribute("role", "radiogroup");
      grupo.setAttribute("aria-label", tr("Grau"));
      for (const g of GRAUS) {
        const lb = document.createElement("label");
        const rb = document.createElement("input");
        rb.type = "radio";
        rb.name = "calcvasc";
        rb.value = g;
        rb.checked = g === atual;
        rb.disabled = !this.resp?.pode_confirmar || this.ocupado;
        rb.onchange = () => { this.escolhido = g; };
        lb.append(rb, ` ${tr(NOMES[g])}`);
        grupo.append(lb);
      }
      r.append(grupo);
      const info = document.createElement("div");
      info.className = "info";
      const partes = [m.grau ? `${tr("Confirmado:")} ${tr(NOMES[m.grau])}${m.revisor ? ` ${tr("por")} ${m.revisor}` : ""}`
        : tr("Ainda não confirmado.")];
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
      };
      const sem = !this.resp?.pode_confirmar || !!m.aviso;
      bt("Confirmar", () => void this.confirmar(false), sem);
      bt("Confirmar e mandar ao laudo", () => void this.confirmar(true), sem);
      bt("Medir de novo", () => void this.medir(true));
      r.append(botoes);
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
