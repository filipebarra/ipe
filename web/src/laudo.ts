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

/** 0.100.4: as listas do formulário BI-RADS (as do Ipê). */
interface CatalogoBirads {
  tipos: Record<string, string>; categorias: Record<string, string>; achados: Record<string, string[]>;
  descritores: Record<string, string[]>; lados: Record<string, string>; composicao: Record<string, Record<string, string>>;
  bpe: Record<string, string>; locais: string[]; mudancas: string[]; recomendacao: Record<string, string>;
}

export interface Achado {
  side: string; type: string; desc: string; size: string; location: string; distance: string; change: string; category: string;
}

export interface CamposBirads {
  kind?: string; findings?: Achado[]; cat_right?: string; cat_left?: string; recommendation?: string;
  composition?: string; fgt?: string; bpe?: string; bpe_sym?: string;
}

interface TextosBirads { blocos: Record<string, string>; final: string; achados: string[] }

interface Busca { id: number; categoria: string; motivo: string; prazo: string; estado: string; situacao: string; atrasado: boolean }

const CHAVES_BIRADS = ["achados_birads", "composicao", "birads", "bpe_texto", "conduta"];

interface DadosLaudo {
  laudos: Laudo[];
  modelos: { id: string; name: string; modalities: string[]; keywords: string[]; text: string; birads?: string }[];
  birads: CatalogoBirads;
  opcoes: { cabecalho: string; assinatura: string; pdf: boolean; sr: boolean };
  buscas: Busca[];
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
  // 0.100.4: o formulário BI-RADS, o PDF/SR e a busca ativa
  private birads = el("details", { class: "birads-laudo" });
  private campos: CamposBirads = {};
  private auto: Record<string, string> = {};       // os blocos do BI-RADS que estão no texto (para trocar)
  private textosB: TextosBirads = { blocos: {}, final: "", achados: [] };
  private pedidoB = 0;
  private editando: number | null = null;          // o achado aberto no formulário (-1 = novo)
  private saidas = el("details", { class: "saidas-laudo" });
  private cabecalho = el("textarea", { class: "cabecalho-laudo", rows: "2", "aria-label": tr("Cabeçalho do PDF") });
  private assinatura = el("input", { "aria-label": tr("Linha da assinatura") });
  private cPdf = el("input", { type: "checkbox", "aria-label": tr("Guardar o PDF no exame (DICOM)") });
  private cSr = el("input", { type: "checkbox", "aria-label": tr("Guardar o SR no exame (DICOM)") });
  private bPdf = el("button", { type: "button" }, tr("Baixar PDF"));
  private buscas = el("div", { class: "buscas-laudo", role: "note" });

  constructor(private study: string, private aoFechar: () => void) {
    const bFechar = el("button", { type: "button", class: "fechar", "aria-label": tr("Fechar o laudo"), title: tr("Fechar o laudo") }, "×");
    bFechar.onclick = () => void this.fechar();
    this.raiz = el("aside", { class: "laudo", "aria-label": tr("Laudo") },
      el("div", { class: "titulo-painel com-botao" }, el("span", {}, tr("Laudo")), this.estado, bFechar),
      this.trava,
      el("label", {}, tr("Versão"), this.versoes),
      el("div", { class: "linha-laudo" }, el("label", {}, tr("Modelo"), this.modelo), this.bAplicar),
      el("label", {}, tr("Título"), this.titulo),
      this.buscas,
      this.birads,
      this.texto,
      el("div", { class: "botoes-laudo" }, this.bIa, this.bSalvar, this.bAssinar, this.bRetificar),
      this.saidas,
      this.confirmar, this.msg);
    this.saidas.append(el("summary", {}, tr("PDF e DICOM")),
      el("label", {}, tr("Cabeçalho do PDF"), this.cabecalho),
      el("label", {}, tr("Linha da assinatura"), this.assinatura),
      el("label", { class: "marcar" }, this.cPdf, tr("Guardar o PDF no exame (DICOM)")),
      el("label", { class: "marcar" }, this.cSr, tr("Guardar o SR no exame (DICOM)")),
      el("div", { class: "botoes-laudo" }, this.bPdf));
    this.assinatura.placeholder = tr("ex.: CRM-DF 00000 — Radiologia");
    this.cabecalho.placeholder = tr("Nome da clínica, endereço…");
    this.bPdf.onclick = () => void this.baixarPdf();
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
    this.cabecalho.value = d.opcoes?.cabecalho || "";
    this.assinatura.value = d.opcoes?.assinatura || "";
    this.cPdf.checked = d.opcoes?.pdf ?? true;
    this.cSr.checked = d.opcoes?.sr ?? true;
    this.mostrarBuscas();
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
      this.campos = {};
      this.aplicarModelo(false);
      this.sujo = false;
    } else {
      this.atual = { ...cur };
      this.versoes.value = String(cur.id);
      if (cur.template) this.modelo.value = cur.template;
      this.titulo.value = cur.title || "";
      this.texto.value = cur.text || "";
      this.sujo = false;
      this.campos = JSON.parse(JSON.stringify(cur.fields || {})) as CamposBirads;
      this.auto = {};
      void this.textosDoFormulario().then((tb) => {
        // os blocos do formulário que estão no texto salvo passam a ser trocados quando o formulário mudar
        for (const k of CHAVES_BIRADS) if (tb.blocos[k] && this.texto.value.includes(tb.blocos[k])) this.auto[k] = tb.blocos[k];
      });
    }
    this.editando = null;
    this.montarBirads();
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
    for (const e of this.birads.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLButtonElement>("input, select, button")) {
      e.disabled = !pode;
    }
    this.cabecalho.readOnly = !pode;
    this.assinatura.readOnly = !pode;
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
    if (m.birads && !this.campos.kind) {
      this.campos = { kind: m.birads, findings: [] };
      this.montarBirads();
    }
    const blocos = this.textosB.blocos;
    const aplicar = (tb: TextosBirads) => {
      const ctx = { ...d.contexto };
      for (const k of CHAVES_BIRADS) if (tb.blocos[k]) ctx[k] = tb.blocos[k];
      this.texto.value = preencher(m.text, ctx);
      this.auto = {};
      for (const k of CHAVES_BIRADS) if (tb.blocos[k] && m.text.includes(`{${k}}`)) this.auto[k] = tb.blocos[k];
    };
    if (this.campos.kind && !Object.keys(blocos).length) {
      void this.textosDoFormulario().then((tb) => { aplicar(tb); if (marcar) this.mudou(); });
      this.texto.value = preencher(m.text, d.contexto);
    } else {
      aplicar(this.textosB);
    }
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
        title: this.titulo.value, text: this.texto.value, author: this.dados!.eu.nome, fields: this.camposNormalizados() }]);
      a.id = id;
      a.title = this.titulo.value;
      a.text = this.texto.value;
      a.fields = this.camposNormalizados() as Record<string, unknown>;
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
      // 0.100.4: como no Ipê — o PDF e o SR no exame e a busca ativa (BI-RADS 0, 3…)
      let extras: string[] = [];
      try {
        const r = await fetch(`${location.origin}/api/web/laudo_assinado`, { method: "POST", headers: { ...API.cabecalhos(),
          "Content-Type": "application/json" }, body: JSON.stringify({ id: rep.id, ...this.opcoes() }) });
        if (r.ok) extras = ((await r.json()) as { mensagens: string[] }).mensagens || [];
        else extras = [`${tr("não foi possível gravar no exame")}: ${r.status}`];
      } catch (e) {
        extras = [`${tr("não foi possível gravar no exame")}: ${(e as Error).message}`];
      }
      this.dados!.laudos = await API.rpc<Laudo[]>("reports", [this.study]);
      this.carregar(rep.id);
      await this.recarregarBuscas();
      this.msg.textContent = [tr("Laudo assinado."), ...extras.map((x) => tr(x))].join(" · ");
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
    this.campos = JSON.parse(JSON.stringify(old.fields || {})) as CamposBirads;
    this.montarBirads();
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
      podeEscrever: this.podeEscrever(), texto: this.texto.value, amends: this.atual?.amends ?? null,
      campos: this.campos, final: this.textosB.final, auto: this.auto };
  }

  // ------------------------------------------------------------------ 0.100.4: BI-RADS, PDF/SR e busca ativa
  /** Os campos no formato da janela do Ipê (BiradsPanel.fields): todos os campos, vazios como "". */
  private camposNormalizados(): CamposBirads {
    const c = this.campos;
    if (!c.kind) return {};
    const d: CamposBirads = { kind: c.kind, findings: c.findings || [], cat_right: c.cat_right || "", cat_left: c.cat_left || "",
      recommendation: c.recommendation || "" };
    if (c.kind === "mri") Object.assign(d, { fgt: c.fgt || "", bpe: c.bpe || "", bpe_sym: c.bpe_sym || "" });
    else d.composition = c.composition || "";
    return d;
  }

  private opcoes(): Record<string, unknown> {
    return { cabecalho: this.cabecalho.value, assinatura: this.assinatura.value, pdf: this.cPdf.checked, sr: this.cSr.checked };
  }

  private async textosDoFormulario(): Promise<TextosBirads> {
    const n = ++this.pedidoB;
    try {
      const r = await fetch(`${location.origin}/api/web/birads_texto`, { method: "POST", headers: { ...API.cabecalhos(),
        "Content-Type": "application/json" }, body: JSON.stringify({ fields: this.camposNormalizados() }) });
      const tb = (await r.json()) as TextosBirads;
      if (n === this.pedidoB) this.textosB = tb;
      return tb;
    } catch {
      return this.textosB;
    }
  }

  /** O formulário mudou: refaz os textos e troca no laudo os blocos do BI-RADS (como o Ipê). */
  private async birdsMudou(forcar = false): Promise<void> {
    const tb = await this.textosDoFormulario();
    this.montarBirads();
    if (!this.podeEscrever()) return;
    const novo = tb.blocos;
    if (!Object.keys(novo).length) return;
    let texto = this.texto.value;
    const m = this.dados?.modelos.find((x) => x.id === this.atual?.template);
    const usados = CHAVES_BIRADS.filter((k) => !m || m.text.includes(`{${k}}`));
    const chaves = usados.length ? usados : ["achados_birads", "composicao", "birads"];
    const faltam: string[] = [];
    for (const k of chaves) {
      const velho = this.auto[k], val = novo[k] || "";
      if (velho && texto.includes(velho)) {
        if (velho !== val) texto = texto.replace(velho, val);
        this.auto[k] = val;
      } else if (val) {
        faltam.push(k);
      }
    }
    if (texto !== this.texto.value) {
      const cur = this.texto.selectionStart;
      this.texto.value = texto;
      this.texto.selectionStart = this.texto.selectionEnd = Math.min(cur, texto.length);
    }
    if (faltam.length && forcar) {
      const blocos = ["composicao", "achados_birads", "birads"].filter((k) => faltam.includes(k)).map((k) => novo[k]);
      const t = this.texto;
      const i = t.selectionStart ?? t.value.length;
      const antes = t.value.slice(0, i);
      const bloco = `${antes && !antes.endsWith("\n") ? "\n" : ""}${blocos.join("\n").trimEnd()}\n`;
      t.value = antes + bloco + t.value.slice(t.selectionEnd ?? i);
      for (const k of faltam) this.auto[k] = novo[k];
      this.msg.textContent = tr("BI-RADS inserido onde está o cursor.");
    } else if (faltam.length) {
      this.msg.textContent = tr("Parte do texto do BI-RADS foi editada à mão: clique em “Levar ao texto do laudo” para inserir o BI-RADS onde está o cursor.");
    } else {
      this.msg.textContent = tr("Texto atualizado com o BI-RADS.");
    }
    this.mudou();
  }

  private mudarCampo(k: keyof CamposBirads, v: string): void {
    (this.campos as Record<string, unknown>)[k] = v;
    void this.birdsMudou();
  }

  /** Monta o formulário BI-RADS (como o painel da janela do laudo do Ipê). */
  private montarBirads(): void {
    const cat = this.dados?.birads;
    if (!cat) return;
    const c = this.campos;
    const k = c.kind || "";
    const aberto = this.birads.open;
    const opc = (pares: [string, string][], val: string, aria: string, fn: (v: string) => void) => {
      const s = el("select", { "aria-label": tr(aria) }, ...pares.map(([v, n]) => new Option(n, v, false, v === val)));
      s.onchange = () => fn(s.value);
      return s;
    };
    const cats: [string, string][] = [["", ""], ...Object.entries(cat.categorias).map(([v, n]) => [v, `${v} — ${tr(n)}`] as [string, string])];
    const tipo = opc(Object.entries(cat.tipos).map(([v, n]) => [v, tr(n)]), k, "Tipo do BI-RADS", (v) => {
      this.campos = v ? { ...this.campos, kind: v, findings: this.campos.findings || [] } : {};
      void this.birdsMudou();
    });
    const filhos: Node[] = [el("summary", {}, "BI-RADS®", el("span", { class: "final-birads" },
      this.textosB.final ? ` · ${tr("categoria final")} ${this.textosB.final}` : "")), el("label", {}, tr("Tipo"), tipo)];
    if (k) {
      const comp = cat.composicao[k] || {};
      const chave = k === "mri" ? "fgt" : "composition";
      filhos.push(el("label", {}, k === "mri" ? tr("Tecido fibroglandular") : k === "us" ? tr("Ecotextura de fundo") : tr("Composição"),
        opc([["", ""], ...Object.entries(comp).map(([v, n]) => [v, `${v}) ${tr(n)}`] as [string, string])], (c as Record<string, string>)[chave] || "",
          k === "mri" ? "Tecido fibroglandular" : "Composição", (v) => this.mudarCampo(chave, v))));
      if (k === "mri") {
        filhos.push(el("div", { class: "linha-laudo" },
          el("label", {}, tr("Realce de fundo"), opc([["", ""], ...Object.entries(cat.bpe).map(([v, n]) => [v, tr(n)] as [string, string])],
            c.bpe || "", "Realce de fundo", (v) => this.mudarCampo("bpe", v))),
          el("label", {}, tr("Simetria"), opc([["", ""], ["simetrico", tr("simétrico")], ["assimetrico", tr("assimétrico")]],
            c.bpe_sym || "", "Simetria do realce", (v) => this.mudarCampo("bpe_sym", v)))));
      }
      // os achados
      const lista = el("ol", { class: "achados-birads" });
      (c.findings || []).forEach((f, i) => {
        const bE = el("button", { type: "button", "aria-label": `${tr("Editar o achado")} ${i + 1}` }, tr("Editar"));
        const bR = el("button", { type: "button", "aria-label": `${tr("Remover o achado")} ${i + 1}` }, "×");
        bE.onclick = () => { this.editando = i; this.montarBirads(); };
        bR.onclick = () => { c.findings!.splice(i, 1); this.editando = null; void this.birdsMudou(); };
        lista.append(el("li", {}, el("span", {}, this.textosB.achados[i] || `${f.type}`), bE, bR));
      });
      const bNovo = el("button", { type: "button" }, `+ ${tr("Achado")}`);
      bNovo.onclick = () => { this.editando = -1; this.montarBirads(); };
      filhos.push(el("div", { class: "rotulo-campo" }, tr("Achados")), lista);
      if (this.editando !== null) filhos.push(this.formularioDoAchado(cat, k, cats));
      else filhos.push(bNovo);
      filhos.push(el("div", { class: "linha-laudo" },
        el("label", {}, tr("Mama direita"), opc(cats, c.cat_right || "", "Categoria da mama direita", (v) => this.mudarCampo("cat_right", v))),
        el("label", {}, tr("Mama esquerda"), opc(cats, c.cat_left || "", "Categoria da mama esquerda", (v) => this.mudarCampo("cat_left", v)))));
      const rec = el("input", { "aria-label": tr("Recomendação") });
      rec.value = c.recommendation || "";
      rec.placeholder = this.textosB.blocos.conduta || tr("automática pela categoria");
      rec.onchange = () => this.mudarCampo("recommendation", rec.value.trim());
      filhos.push(el("label", {}, tr("Recomendação (vazia = a da categoria)"), rec));
      if (this.textosB.final) {
        filhos.push(el("div", { class: "final-texto" }, `${tr("Categoria final")}: BI-RADS® ${this.textosB.final} — ${tr(cat.categorias[this.textosB.final] || "")}`));
      }
      const bLevar = el("button", { type: "button" }, tr("Levar ao texto do laudo"));
      bLevar.onclick = () => void this.birdsMudou(true);
      filhos.push(el("div", { class: "botoes-laudo" }, bLevar));
    }
    this.birads.replaceChildren(...filhos);
    this.birads.open = aberto || !!k;
    if (!this.podeEscrever()) {
      for (const e of this.birads.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLButtonElement>("input, select, button")) e.disabled = true;
    }
  }

  private formularioDoAchado(cat: CatalogoBirads, k: string, cats: [string, string][]): HTMLElement {
    const i = this.editando!;
    const f: Achado = i >= 0 ? { ...this.campos.findings![i] } : { side: "D", type: (cat.achados[k] || cat.achados.mg)[0], desc: "",
      size: "", location: "", distance: "", change: "", category: "" };
    const s = (pares: [string, string][], val: string, aria: string) =>
      el("select", { "aria-label": tr(aria) }, ...pares.map(([v, n]) => new Option(n, v, false, v === val)));
    const lado = s(Object.entries(cat.lados).map(([v, n]) => [v, tr(n)]), f.side, "Lado do achado");
    const tipos = cat.achados[k] || cat.achados.mg;
    const tipo = s(tipos.map((x) => [x, tr(x)]), f.type, "Tipo do achado");
    const desc = el("input", { "aria-label": tr("Descritores") });
    desc.value = f.desc;
    const descs = el("select", { "aria-label": tr("Acrescentar descritor") });
    const encherDescs = () => {
      descs.replaceChildren(new Option(tr("+ descritor"), ""), ...(cat.descritores[tipo.value] || []).map((x) => new Option(tr(x), x)));
    };
    encherDescs();
    tipo.onchange = encherDescs;
    descs.onchange = () => {
      if (descs.value) desc.value = desc.value.trim() ? `${desc.value.trim()}, ${descs.value}` : descs.value;
      descs.value = "";
    };
    const tam = el("input", { "aria-label": tr("Tamanho") });
    tam.value = f.size;
    tam.placeholder = "12 mm";
    const local = s([["", ""], ...cat.locais.map((x) => [x, tr(x)] as [string, string])], f.location, "Local do achado");
    const dist = el("input", { "aria-label": tr("Distância do mamilo") });
    dist.value = f.distance;
    dist.placeholder = "3 cm";
    const mud = s(cat.mudancas.map((x) => [x, tr(x)]), f.change, "Mudança");
    const categ = s(cats, f.category, "Categoria do achado");
    const ok = el("button", { type: "button", class: "primario" }, tr("OK"));
    const cancelar = el("button", { type: "button" }, tr("Cancelar"));
    ok.onclick = () => {
      const novo: Achado = { side: lado.value, type: tipo.value, desc: desc.value.trim(), size: tam.value.trim(),
        location: local.value, distance: dist.value.trim(), change: mud.value, category: categ.value };
      const fs = this.campos.findings || (this.campos.findings = []);
      if (i >= 0) fs[i] = novo;
      else fs.push(novo);
      this.editando = null;
      void this.birdsMudou();
    };
    cancelar.onclick = () => { this.editando = null; this.montarBirads(); };
    return el("div", { class: "form-achado" },
      el("div", { class: "linha-laudo" }, el("label", {}, tr("Lado"), lado), el("label", {}, tr("Tipo"), tipo)),
      el("label", {}, tr("Descritores"), desc), descs,
      el("div", { class: "linha-laudo" }, el("label", {}, tr("Tamanho"), tam), el("label", {}, tr("Distância do mamilo"), dist)),
      el("div", { class: "linha-laudo" }, el("label", {}, tr("Local"), local), el("label", {}, tr("Mudança"), mud)),
      el("label", {}, tr("Categoria do achado"), categ),
      el("div", { class: "botoes-laudo" }, ok, cancelar));
  }

  /** O PDF do laudo (igual ao do Ipê), baixado pelo navegador. */
  async baixarPdf(): Promise<void> {
    if (this.sujo && this.podeEscrever()) await this.salvar(true);
    const a = this.atual;
    if (!a?.id) {
      this.msg.textContent = tr("Salve o rascunho antes de gerar o PDF.");
      return;
    }
    this.msg.textContent = tr("Gerando o PDF…");
    try {
      const r = await fetch(`${location.origin}/api/web/laudo_pdf`, { method: "POST", headers: { ...API.cabecalhos(),
        "Content-Type": "application/json" }, body: JSON.stringify({ id: a.id, ...this.opcoes() }) });
      if (!r.ok) throw new Error(((await r.json().catch(() => ({}))) as { error?: string }).error || String(r.status));
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const link = el("a", { href: url, download: `laudo_${(a.title || "laudo").replace(/[^\w\-]+/g, "_")}.pdf` });
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      this.ultimoPdf = blob.size;
      this.msg.textContent = tr("PDF gerado.");
    } catch (e) {
      this.msg.textContent = `${tr("Não deu para gerar o PDF:")} ${(e as Error).message}`;
    }
  }

  ultimoPdf = 0;

  private mostrarBuscas(): void {
    const bs = this.dados?.buscas || [];
    this.buscas.replaceChildren();
    this.buscas.hidden = !bs.length;
    if (!bs.length) return;
    this.buscas.append(el("strong", {}, tr("Busca ativa da paciente")),
      ...bs.map((b) => el("div", { class: b.atrasado ? "busca atrasada" : "busca" },
        `${tr(b.motivo)} · ${tr("até")} ${b.prazo} (${tr(b.situacao)}) · ${tr(b.estado)}`)));
  }

  private async recarregarBuscas(): Promise<void> {
    try {
      const r = await fetch(`${location.origin}/api/web/laudo?study=${encodeURIComponent(this.study)}`,
        { headers: API.cabecalhos(), cache: "no-store" });
      if (r.ok && this.dados) {
        this.dados.buscas = ((await r.json()) as DadosLaudo).buscas || [];
        this.mostrarBuscas();
      }
    } catch { /* fica a lista de antes */ }
  }
}

(window as unknown as Record<string, unknown>).__ipeLaudoPreencher = preencher; // testes
