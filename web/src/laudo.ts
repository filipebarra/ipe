// Laudo no navegador (0.99.98, W6): os modelos do Ipê com os campos automáticos, os achados de IA revisados, a
// trava de "quem está laudando" (0.99.31), o rascunho gravado no mesmo registro de laudo do Ipê, a assinatura
// (liberação) e a retificação. Gravar, assinar e a trava passam pelo /api/rpc do servidor central — as mesmas
// regras do programa do consultório ligado ao servidor: permissão do perfil, banco pessoal e a trava.
import * as API from "./api";
import { tr } from "./i18n";

export interface Laudo {
  id: number | null; study_uid: string; template: string; title: string; status: string; text: string;
  fields: Record<string, unknown>; author?: string; signed_by?: string; created_at?: string; updated_at?: string;
  signed_at?: string; amends?: number | null;
}

interface DadosLaudo {
  laudos: Laudo[];
  modelos: { id: string; name: string; modalities: string[]; keywords: string[]; text: string }[];
  sugerido: string;
  contexto: Record<string, string>;
  campos: Record<string, string>;
  ia: string;
  trava: { usuario: string; nome: string; desde: string } | null;
  pode: { escrever: boolean; assinar: boolean };
  eu: { usuario: string; nome: string };
}

const CAMPO = /\{([a-z_]+)\}/g;

/** Troca {campo} pelo valor; a linha que só tinha campos vazios some (reporting/fill.py: fill). */
export function preencher(texto: string, ctx: Record<string, string>): string {
  const saida: string[] = [];
  for (const linha of (texto || "").split(/\r?\n/)) {
    const tinha = /\{([a-z_]+)\}/.test(linha);
    const nova = linha.replace(CAMPO, (m, k: string) => (k in ctx ? String(ctx[k]) : m));
    if (tinha && !nova.trim()) continue;
    saida.push(nova);
  }
  return `${saida.join("\n").replace(/\n{3,}/g, "\n\n").trim()}\n`;
}

const ESTADO: Record<string, string> = { draft: "rascunho", final: "assinado", amended: "retificado" };

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, string> = {}, ...filhos: (Node | string)[]): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) e.setAttribute(k, v);
  e.append(...filhos);
  return e;
}

export class PainelLaudo {
  raiz: HTMLElement;
  private dados: DadosLaudo | null = null;
  private atual: Laudo | null = null;
  private soLeitura = "";
  private sujo = false;
  private relogio = 0;
  private autoSalvar = 0;
  private aberto = false;
  private texto = el("textarea", { class: "texto-laudo", "aria-label": tr("Texto do laudo"), spellcheck: "true" });
  private titulo = el("input", { class: "titulo-laudo", "aria-label": tr("Título do laudo") });
  private versoes = el("select", { "aria-label": tr("Versões do laudo") });
  private modelo = el("select", { "aria-label": tr("Modelo") });
  private msg = el("div", { class: "msg-laudo", role: "status" });
  private trava = el("div", { class: "trava-laudo", role: "alert", hidden: "" });
  private estado = el("span", { class: "estado-laudo" });
  private bAplicar = el("button", { type: "button" }, tr("Aplicar modelo"));
  private bIa = el("button", { type: "button" }, tr("Inserir achados de IA"));
  private bSalvar = el("button", { type: "button" }, tr("Salvar rascunho"));
  private bAssinar = el("button", { type: "button", class: "primario" }, tr("Assinar e liberar"));
  private bRetificar = el("button", { type: "button" }, tr("Retificar"));
  private confirmar = el("div", { class: "confirmar-laudo", hidden: "" });

  constructor(private study: string, private aoFechar: () => void) {
    const bFechar = el("button", { type: "button", class: "fechar", "aria-label": tr("Fechar o laudo"), title: tr("Fechar o laudo") }, "×");
    bFechar.onclick = () => void this.fechar();
    this.raiz = el("aside", { class: "laudo", "aria-label": tr("Laudo") },
      el("div", { class: "titulo-painel com-botao" }, el("span", {}, tr("Laudo")), this.estado, bFechar),
      this.trava,
      el("label", {}, tr("Versão"), this.versoes),
      el("div", { class: "linha-laudo" }, el("label", {}, tr("Modelo"), this.modelo), this.bAplicar),
      el("label", {}, tr("Título"), this.titulo),
      this.texto,
      el("div", { class: "botoes-laudo" }, this.bIa, this.bSalvar, this.bAssinar, this.bRetificar),
      this.confirmar, this.msg);
    this.texto.oninput = () => this.mudou();
    this.titulo.oninput = () => this.mudou();
    this.versoes.onchange = () => void this.escolherVersao(Number(this.versoes.value));
    this.bAplicar.onclick = () => this.aplicarModelo();
    this.bIa.onclick = () => this.inserirIa();
    this.bSalvar.onclick = () => void this.salvar();
    this.bAssinar.onclick = () => this.pedirAssinatura();
    this.bRetificar.onclick = () => this.retificar();
    (window as unknown as Record<string, unknown>).__ipeLaudo = this; // testes
  }

  /** Lê os laudos e os modelos e começa a leitura (a trava). */
  async abrir(): Promise<void> {
    this.aberto = true;
    const r = await fetch(`${location.origin}/api/web/laudo?study=${encodeURIComponent(this.study)}`,
      { headers: API.cabecalhos(), cache: "no-store" });
    if (!r.ok) {
      this.msg.textContent = tr("Não foi possível abrir o laudo.");
      return;
    }
    this.dados = (await r.json()) as DadosLaudo;
    const d = this.dados;
    this.modelo.replaceChildren(...d.modelos.map((m) => new Option(m.name, m.id, false, m.id === d.sugerido)));
    this.bIa.disabled = !d.ia;
    this.bIa.title = d.ia ? d.ia : tr("Nenhum achado de IA confirmado ou corrigido neste exame.");
    this.soLeitura = "";
    if (!d.pode.escrever) {
      this.soLeitura = tr("Seu perfil não permite escrever laudos.");
    } else {
      await this.comecarLeitura(false);
    }
    this.carregar(null);
  }

  private async comecarLeitura(forcar: boolean): Promise<void> {
    this.trava.replaceChildren();
    this.trava.hidden = true;
    let r: { ok: boolean; de?: string; desde?: string } = { ok: true };
    try {
      r = await API.rpc("leitura_comecar", [this.study, forcar]);
    } catch { /* sem trava: segue */ }
    if (!r.ok) {
      this.soLeitura = `${r.de ?? "?"} ${tr("está laudando este exame desde")} ${r.desde ?? "?"}`;
      const bLer = el("button", { type: "button" }, tr("Só ler"));
      const bAssumir = el("button", { type: "button" }, tr("Assumir o laudo"));
      bLer.onclick = () => { this.trava.querySelectorAll("button").forEach((b) => b.remove()); };
      bAssumir.onclick = async () => {
        this.soLeitura = "";
        await this.comecarLeitura(true);
        this.atualizarEstado();
      };
      this.trava.append(el("span", {}, this.soLeitura), bLer, bAssumir);
      this.trava.hidden = false;
      return;
    }
    // avisa o servidor a cada 2 minutos que continua (sem aviso por 10, a trava cai sozinha)
    clearInterval(this.relogio);
    this.relogio = window.setInterval(() => { void API.rpc("leitura_manter", [[this.study]]).catch(() => undefined); }, 120_000);
  }

  private carregar(id: number | null): void {
    const d = this.dados!;
    const ls = d.laudos;
    this.versoes.replaceChildren(...ls.map((l) => new Option(`#${l.id} ${tr(ESTADO[l.status] || l.status)} ${l.updated_at || ""}`, String(l.id))));
    let cur = id !== null ? ls.find((l) => l.id === id) ?? null : null;
    if (!cur && ls.length) {
      const rascunhos = ls.filter((l) => l.status === "draft");
      cur = rascunhos.length ? rascunhos[rascunhos.length - 1] : ls[ls.length - 1];
    }
    if (!cur) {
      const m = d.modelos.find((x) => x.id === d.sugerido);
      this.atual = { id: null, study_uid: this.study, status: "draft", text: "", fields: {}, template: m?.id || "",
        title: m?.name || tr("Laudo") };
      this.titulo.value = this.atual.title;
      this.aplicarModelo(false);
      this.sujo = false;
    } else {
      this.atual = { ...cur };
      this.versoes.value = String(cur.id);
      if (cur.template) this.modelo.value = cur.template;
      this.titulo.value = cur.title || "";
      this.texto.value = cur.text || "";
      this.sujo = false;
    }
    this.atualizarEstado();
  }

  private async escolherVersao(id: number): Promise<void> {
    if (this.sujo && this.podeEscrever()) await this.salvar();
    this.carregar(id);
  }

  private podeEscrever(): boolean {
    return !!this.atual && this.atual.status === "draft" && !this.soLeitura && !!this.dados?.pode.escrever;
  }

  private atualizarEstado(): void {
    const a = this.atual;
    const pode = this.podeEscrever();
    const assinado = !!a && a.status !== "draft";
    this.texto.readOnly = !pode;
    this.titulo.readOnly = !pode;
    this.modelo.disabled = !pode;
    this.bAplicar.disabled = !pode;
    this.bIa.disabled = !pode || !this.dados?.ia;
    this.bSalvar.disabled = !pode;
    this.bAssinar.disabled = !pode || !this.dados?.pode.assinar;
    this.bAssinar.title = this.dados?.pode.assinar ? "" : tr("Seu perfil não permite assinar laudos.");
    this.bRetificar.hidden = !assinado;
    this.bRetificar.disabled = !this.dados?.pode.escrever || !!this.soLeitura;
    this.estado.textContent = !a ? "" : assinado
      ? `${tr(ESTADO[a.status] || a.status)} · ${a.signed_by || ""} · ${a.signed_at || ""}`
      : a.amends ? tr("retificação (rascunho)") : a.id ? tr("rascunho") : tr("novo");
    this.estado.dataset.estado = a?.status || "";
    if (this.soLeitura && !this.trava.childElementCount) {
      this.trava.replaceChildren(el("span", {}, this.soLeitura));
      this.trava.hidden = false;
    }
  }

  private mudou(): void {
    if (!this.podeEscrever()) return;
    this.sujo = true;
    clearTimeout(this.autoSalvar);
    this.autoSalvar = window.setTimeout(() => { if (this.sujo) void this.salvar(true); }, 4000);
  }

  aplicarModelo(marcar = true): void {
    const d = this.dados;
    const m = d?.modelos.find((x) => x.id === this.modelo.value);
    if (!d || !m || !this.atual) return;
    this.atual.template = m.id;
    if (!this.atual.id && !this.sujo) this.titulo.value = m.name;
    this.texto.value = preencher(m.text, d.contexto);
    if (marcar) this.mudou();
  }

  /** Os achados de IA revisados entram no cursor (ou no fim). */
  inserirIa(): void {
    const ia = this.dados?.ia;
    if (!ia || !this.podeEscrever()) return;
    const t = this.texto;
    const i = t.selectionStart ?? t.value.length;
    const antes = t.value.slice(0, i);
    const bloco = `${antes && !antes.endsWith("\n") ? "\n" : ""}${ia}\n`;
    t.value = antes + bloco + t.value.slice(t.selectionEnd ?? i);
    t.selectionStart = t.selectionEnd = i + bloco.length;
    this.mudou();
  }

  /** Grava o rascunho (o mesmo registro de laudo do Ipê). */
  async salvar(automatico = false): Promise<boolean> {
    const a = this.atual;
    if (!a || !this.podeEscrever()) return false;
    clearTimeout(this.autoSalvar);
    try {
      const id = await API.rpc<number>("save_report", [{ id: a.id, study_uid: this.study, template: a.template,
        title: this.titulo.value, text: this.texto.value, author: this.dados!.eu.nome, fields: a.fields || {} }]);
      a.id = id;
      a.title = this.titulo.value;
      a.text = this.texto.value;
      this.sujo = false;
      await this.recarregarLista(id);
      this.msg.textContent = automatico ? tr("Rascunho salvo automaticamente.") : tr("Rascunho salvo.");
      return true;
    } catch (e) {
      this.msg.textContent = `${tr("Não deu para salvar:")} ${(e as Error).message}`;
      return false;
    }
  }

  private async recarregarLista(id: number): Promise<void> {
    const ls = await API.rpc<Laudo[]>("reports", [this.study]).catch(() => null);
    if (!ls || !this.dados) return;
    this.dados.laudos = ls;
    const amends = this.atual?.amends;
    this.versoes.replaceChildren(...ls.map((l) => new Option(`#${l.id} ${tr(ESTADO[l.status] || l.status)} ${l.updated_at || ""}`, String(l.id))));
    this.versoes.value = String(id);
    const novo = ls.find((l) => l.id === id);
    if (novo && this.atual) this.atual = { ...novo, amends };
    this.atualizarEstado();
  }

  /** Assinar pede uma confirmação na própria janela (sem caixa do navegador). */
  pedirAssinatura(): void {
    if (!this.texto.value.trim()) {
      this.msg.textContent = tr("O laudo está vazio.");
      return;
    }
    const sim = el("button", { type: "button", class: "primario" }, tr("Assinar"));
    const nao = el("button", { type: "button" }, tr("Cancelar"));
    sim.onclick = () => void this.assinar();
    nao.onclick = () => { this.confirmar.hidden = true; };
    this.confirmar.replaceChildren(el("span", {}, tr("Assinar e liberar o laudo? Depois de assinado, ele só pode ser mudado por retificação.")), sim, nao);
    this.confirmar.hidden = false;
  }

  async assinar(): Promise<boolean> {
    this.confirmar.hidden = true;
    const a = this.atual;
    if (!a || !(await this.salvar())) return false;
    try {
      const rep = await API.rpc<Laudo | null>("sign_report", [a.id, "", a.amends ? "amended" : "final"]);
      if (!rep) throw new Error("?");
      await API.rpc("audit", ["laudo_assinado", rep.title || ""], { study_uid: this.study }).catch(() => undefined);
      this.dados!.laudos = await API.rpc<Laudo[]>("reports", [this.study]);
      this.carregar(rep.id);
      this.msg.textContent = tr("Laudo assinado.");
      return true;
    } catch (e) {
      this.msg.textContent = `${tr("Não deu para assinar:")} ${(e as Error).message}`;
      return false;
    }
  }

  /** Um rascunho novo com o texto do assinado; o assinado continua guardado. */
  retificar(): void {
    const old = this.atual;
    if (!old || old.status === "draft") return;
    this.atual = { id: null, study_uid: this.study, status: "draft", template: old.template, title: `${old.title || tr("Laudo")} (${tr("retificação")})`,
      text: old.text, fields: old.fields || {}, amends: old.id };
    this.titulo.value = this.atual.title;
    this.texto.value = old.text;
    this.sujo = true;
    this.atualizarEstado();
    this.msg.textContent = tr("Retificação: edite e assine; o laudo anterior continua guardado.");
  }

  /** Fecha: grava o rascunho que mudou e solta a trava. */
  async fechar(): Promise<void> {
    if (!this.aberto) return;
    this.aberto = false;
    clearInterval(this.relogio);
    if (this.sujo && this.podeEscrever() && this.texto.value.trim()) await this.salvar(true);
    if (this.dados?.pode.escrever && !this.soLeitura) await API.rpc("leitura_terminar", [this.study]).catch(() => undefined);
    this.raiz.remove();
    this.aoFechar();
  }

  /** Para os testes. */
  estadoAtual(): Record<string, unknown> {
    return { id: this.atual?.id ?? null, status: this.atual?.status, soLeitura: this.soLeitura, sujo: this.sujo,
      podeEscrever: this.podeEscrever(), texto: this.texto.value, amends: this.atual?.amends ?? null };
  }
}

(window as unknown as Record<string, unknown>).__ipeLaudoPreencher = preencher; // testes
