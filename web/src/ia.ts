// 0.100.10: pedir CAD/IA pelo navegador e acompanhar. A IA roda no servidor, pela mesma fila do automático da
// chegada (uma por vez); aqui aparecem as ferramentas que servem para o exame, com a série que cada uma usaria, e as
// tarefas do exame (as pedidas e as automáticas) com a etapa. 0.100.12: tudo numa aba do painel da direita. Só para quem tem a permissão de pedir CAD/IA.
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

/** 0.100.12: a aba IA do painel da direita. Todas as ferramentas de CAD/IA do Ipê, as que servem para o exame aberto
 *  primeiro (com a série sugerida ou a do quadro ativo) e as outras com o motivo; em cima, as tarefas do exame com o
 *  andamento. Fica montada (o painel redesenha a aba a cada mudança do quadro): só a série do quadro é trocada. */
export class AbaIA {
  raiz = el("div", { class: "aba-ia" });
  private lista = el("div", { class: "lista-ia" });
  private nota = el("div", { class: "nota" });
  private aviso = el("div", { class: "aviso" });
  private dados: { ferramentas: Ferramenta[]; instalado: boolean } | null = null;
  private quadroVisto = "";
  private carregando: Promise<void> | null = null;

  constructor(private study: string, private tarefas: TarefasIA,
    private serieAtual: () => { uid: string; rotulo: string } | null) {
    this.aviso.hidden = true;
    const bAtualizar = el("button", { type: "button", class: "link", title: tr("Ler de novo as ferramentas e as tarefas") }, tr("Atualizar"));
    bAtualizar.onclick = () => { void this.carregar(); void this.tarefas.atualizar(); };
    this.raiz.append(
      el("div", { class: "titulo-painel com-botao" }, el("span", {}, tr("CAD/IA neste exame")), bAtualizar),
      el("div", { class: "dica" }, tr("Escolha a ferramenta e a série e clique em Rodar. A IA roda no servidor, uma por vez; o andamento aparece logo abaixo.")),
      this.aviso, this.nota,
      // o andamento em cima (a lista de ferramentas é comprida)
      el("div", { class: "titulo-painel" }, tr("Tarefas deste exame")), this.tarefas.raiz,
      el("div", { class: "titulo-painel" }, tr("Ferramentas")), this.lista);
  }

  /** a aba apareceu ou o quadro mudou: lê as ferramentas na primeira vez; depois só troca a série do quadro */
  mostrar(): void {
    if (!this.dados) { void this.carregar(); return; }
    const q = this.serieAtual()?.uid || "";
    if (q !== this.quadroVisto) this.desenhar();
  }

  carregar(): Promise<void> {
    this.carregando ??= (async () => {
      try {
        this.dados = (await pedirJson(`/api/web/ia?study=${encodeURIComponent(this.study)}`)) as typeof this.dados;
        this.desenhar();
      } catch (e) {
        this.lista.replaceChildren(el("div", { class: "erro" }, `${tr("Não consegui ler as ferramentas")}: ${(e as Error).message}`));
      } finally {
        this.carregando = null;
      }
    })();
    return this.carregando;
  }

  private desenhar(): void {
    const d = this.dados;
    if (!d) return;
    const atual = this.serieAtual();
    this.quadroVisto = atual?.uid || "";
    this.aviso.hidden = d.instalado;
    this.aviso.textContent = d.instalado ? "" : tr("O pacote de segmentação (IA) não está instalado no servidor.");
    // a escolha de série de cada ferramenta sobrevive ao redesenho
    const escolhidas = new Map<string, string>();
    for (const s of this.lista.querySelectorAll<HTMLSelectElement>(".ferramenta-ia select")) {
      const t = (s.closest(".ferramenta-ia") as HTMLElement | null)?.dataset.tipo;
      if (t) escolhidas.set(t, s.value);
    }
    const usaveis = d.ferramentas.filter((f) => f.serie);
    const outras = d.ferramentas.filter((f) => !f.serie);
    const linhas: HTMLElement[] = [];
    if (usaveis.length) linhas.push(el("div", { class: "grupo-ia" }, tr("Servem para este exame")));
    for (const f of usaveis) linhas.push(this.linha(f, atual, escolhidas.get(f.tipo), d.instalado));
    if (outras.length) linhas.push(el("div", { class: "grupo-ia" }, tr("Outras ferramentas")));
    for (const f of outras) linhas.push(this.linha(f, atual, escolhidas.get(f.tipo), d.instalado));
    if (!linhas.length) linhas.push(el("div", { class: "dica" }, tr("Nenhuma ferramenta de CAD/IA no servidor.")));
    this.lista.replaceChildren(...linhas);
  }

  private linha(f: Ferramenta, atual: { uid: string; rotulo: string } | null, antes: string | undefined,
    instalado: boolean): HTMLElement {
    const sSerie = el("select", { "aria-label": `${tr("Série")}: ${tr(f.titulo)}` });
    if (f.serie) sSerie.append(el("option", { value: f.serie }, `${tr("sugerida")}: ${f.serie_rotulo}`));
    if (atual && atual.uid !== f.serie) sSerie.append(el("option", { value: atual.uid }, `${tr("do quadro")}: ${atual.rotulo}`));
    if (antes && [...sSerie.options].some((o) => o.value === antes)) sSerie.value = antes;
    const b = el("button", { type: "button", class: "primario" }, f.ja_feita ? tr("Refazer") : tr("Rodar"));
    b.disabled = !instalado || f.andando || !sSerie.options.length;
    b.onclick = async () => {
      b.disabled = true;
      this.nota.textContent = tr("Pondo na fila…");
      try {
        const r = (await pedirJson("/api/web/ia/pedir", { study: this.study, tipo: f.tipo, serie: sSerie.value || null })) as { tarefa: number };
        this.tarefas.pedidas.add(r.tarefa);
        this.nota.textContent = `${tr(f.titulo)}: ${tr("na fila")}.`;
        await Promise.all([this.tarefas.atualizar(), this.carregar()]);
      } catch (e) {
        this.nota.textContent = `${tr("Não foi possível pedir")}: ${(e as Error).message}`;
        b.disabled = false;
      }
    };
    const info = f.andando ? tr("na fila ou rodando") : f.ja_feita ? tr("já feita neste exame")
      : f.serie ? "" : (f.motivo || tr("sem série que sirva; escolha um quadro com a série"));
    return el("div", { class: `ferramenta-ia${f.serie ? "" : " sem-serie"}`, "data-tipo": f.tipo },
      el("div", { class: "ferramenta-titulo" }, tr(f.titulo)),
      ...(sSerie.options.length ? [sSerie] : []),
      ...(info ? [el("small", {}, info)] : []), b);
  }
}
