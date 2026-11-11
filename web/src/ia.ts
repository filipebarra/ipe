// 0.100.10: pedir CAD/IA pelo navegador e acompanhar. A IA roda no servidor, pela mesma fila do automático da
// chegada (uma por vez); aqui aparecem as ferramentas que servem para o exame, com a série que cada uma usaria, e as
// tarefas do exame (as pedidas e as automáticas) com a etapa. Só para quem tem a permissão de pedir CAD/IA.
import { cabecalhos } from "./api";
import { tr } from "./i18n";

export interface Ferramenta {
  tipo: string;
  titulo: string;
  serie: string | null;
  serie_rotulo: string;
  motivo: string;
  ja_feita: boolean;
  andando: boolean;
}

export interface TarefaIA {
  id: number;
  ferramenta: string;
  estado: string;
  rotulo: string;
  etapa: string;
  mensagem: string;
  origem: string;
  segundos: number;
  ativa: boolean;
  pode_cancelar: boolean;
}

async function pedirJson(caminho: string, corpo?: unknown): Promise<unknown> {
  const r = await fetch(`${location.origin}${caminho}`, {
    method: corpo === undefined ? "GET" : "POST", cache: "no-store",
    headers: { ...cabecalhos(), ...(corpo === undefined ? {} : { "Content-Type": "application/json" }) },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.text()) || msg; } catch { /* sem corpo */ }
    throw new Error(msg);
  }
  return r.json();
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, string> = {}, ...filhos: (Node | string)[]): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) e.setAttribute(k, v);
  e.append(...filhos);
  return e;
}

function tempo(s: number): string {
  if (s < 60) return `${s} s`;
  return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
}

/** As tarefas de IA do exame; atualiza sozinha enquanto houver tarefa andando e avisa quando uma termina. */
export class TarefasIA {
  raiz = el("div", { class: "tarefas-ia" });
  private relogio = 0;
  private vistas = new Map<number, string>();
  /** as tarefas pedidas daqui: avisa do "Pronto" mesmo se ela terminar antes da primeira consulta */
  pedidas = new Set<number>();
  aoMudar: (ativas: number, total: number) => void = () => {};
  /** uma tarefa terminou bem: o exame tem séries novas */
  aoTerminar: (t: TarefaIA) => void = () => {};

  constructor(private study: string) {}

  parar(): void { clearTimeout(this.relogio); }

  async atualizar(): Promise<TarefaIA[]> {
    let lista: TarefaIA[] = [];
    try {
      lista = ((await pedirJson(`/api/web/ia/tarefas?study=${encodeURIComponent(this.study)}`)) as { tarefas: TarefaIA[] }).tarefas;
    } catch { /* sem rede agora */ }
    for (const t of lista) {
      const antes = this.vistas.get(t.id);
      const nova = antes === undefined ? this.pedidas.has(t.id) : antes !== t.estado;
      if (nova && t.estado === "pronto") this.aoTerminar(t);
      this.vistas.set(t.id, t.estado);
    }
    this.desenhar(lista);
    const ativas = lista.filter((t) => t.ativa).length;
    this.aoMudar(ativas, lista.length);
    clearTimeout(this.relogio);
    if (ativas) this.relogio = window.setTimeout(() => void this.atualizar(), 1500);
    return lista;
  }

  private desenhar(lista: TarefaIA[]): void {
    if (!lista.length) {
      this.raiz.replaceChildren(el("div", { class: "dica" }, tr("Nenhuma tarefa de IA neste exame.")));
      return;
    }
    this.raiz.replaceChildren(...lista.map((t) => {
      const linha = el("div", { class: `tarefa ${t.estado.replace(/\s/g, "-")}`, "data-id": String(t.id) },
        el("div", { class: "tarefa-titulo" }, t.ferramenta),
        el("div", { class: "tarefa-estado" }, [tr(t.rotulo), t.etapa, t.segundos ? tempo(t.segundos) : ""].filter(Boolean).join(" · ")),
        ...(t.mensagem ? [el("div", { class: "tarefa-msg" }, t.mensagem)] : []),
        el("div", { class: "tarefa-origem" }, t.origem.startsWith("manual") ? `${tr("pedida por")} ${t.origem.replace(/^manual · ?/, "") || "—"}` : tr("automática")));
      if (t.ativa) linha.append(el("progress", {}));
      if (t.pode_cancelar) {
        const b = el("button", { type: "button", class: "link" }, tr("Cancelar"));
        b.onclick = () => { void pedirJson("/api/web/ia/cancelar", { id: t.id }).then(() => this.atualizar()); };
        linha.append(b);
      }
      return linha;
    }));
  }
}

/** O painel de pedir: as ferramentas para o exame, a série de cada uma (a sugerida ou a do quadro ativo). */
export async function painelIA(study: string, serieAtual: { uid: string; rotulo: string } | null, tarefas: TarefasIA,
  fechar: () => void): Promise<HTMLElement> {
  const raiz = el("div", { class: "painel-ia" });
  let d: { ferramentas: Ferramenta[]; instalado: boolean };
  try {
    d = (await pedirJson(`/api/web/ia?study=${encodeURIComponent(study)}`)) as typeof d;
  } catch (e) {
    raiz.append(el("div", { class: "erro" }, `${tr("Não consegui ler as ferramentas")}: ${(e as Error).message}`));
    return raiz;
  }
  raiz.append(el("div", { class: "titulo-painel" }, tr("CAD/IA neste exame")));
  if (!d.instalado) raiz.append(el("div", { class: "aviso" }, tr("O pacote de segmentação (IA) não está instalado no servidor.")));
  const nota = el("div", { class: "nota" });
  const lista = el("div", { class: "lista-ia" });
  const usaveis = d.ferramentas.filter((f) => f.serie);
  const outras = d.ferramentas.filter((f) => !f.serie);
  for (const f of [...usaveis, ...outras]) {
    const sSerie = el("select", { "aria-label": `${tr("Série")}: ${f.titulo}` });
    if (f.serie) sSerie.append(el("option", { value: f.serie }, `${tr("sugerida")}: ${f.serie_rotulo}`));
    if (serieAtual && serieAtual.uid !== f.serie) sSerie.append(el("option", { value: serieAtual.uid }, `${tr("do quadro")}: ${serieAtual.rotulo}`));
    const b = el("button", { type: "button", class: "primario" }, f.ja_feita ? tr("Refazer") : tr("Rodar"));
    b.disabled = !d.instalado || f.andando || !sSerie.options.length;
    b.onclick = async () => {
      b.disabled = true;
      nota.textContent = tr("Pondo na fila…");
      try {
        const r = (await pedirJson("/api/web/ia/pedir", { study, tipo: f.tipo, serie: sSerie.value || null })) as { tarefa: number };
        tarefas.pedidas.add(r.tarefa);
        nota.textContent = "";
        fechar();
        await tarefas.atualizar();
      } catch (e) {
        nota.textContent = `${tr("Não foi possível pedir")}: ${(e as Error).message}`;
        b.disabled = false;
      }
    };
    const info = f.andando ? tr("na fila ou rodando") : f.ja_feita ? tr("já feita neste exame") : f.serie ? "" : f.motivo;
    lista.append(el("div", { class: `ferramenta-ia${f.serie ? "" : " sem-serie"}`, "data-tipo": f.tipo },
      el("div", { class: "ferramenta-titulo" }, tr(f.titulo)),
      ...(sSerie.options.length ? [sSerie] : []),
      ...(info ? [el("small", {}, info)] : []), b));
  }
  raiz.append(lista, nota);
  return raiz;
}
