// 0.100.79: o PI-RADS no navegador — o mesmo formulário do Ipê de mesa (botão PI-RADS): volume (elipsoide ou a
// segmentação automática) e densidade do PSA; as lesões com a zona, os setores (toque no mapa), o tamanho, as
// pontuações, o DCE, o ADC, a extensão extraprostática e a imagem aberta ligada. As contas (categoria de cada lesão,
// a geral, o texto do laudo) são sempre do servidor: a cada mudança, o servidor devolve o estado calculado e, quem
// pode escrever laudos, já fica gravado. O que veio de um modelo de pesquisa aparece com a faixa vermelha.
import { pedir } from "./api";
import { desenhar, modelos, type Esquema, type Modelo } from "./esquemas";
import { tr } from "./i18n";
import { botao, el } from "./impressoes";

export interface ImagemPirads { series_uid: string; sop_uid: string; frame: number; rotulo?: string }
export interface Lesao {
  n: number; zona: string; setores: string[]; tamanho_mm: number | null; t2: number | null; dwi: number | null;
  dce: string; adc: number | null; epe: string; descricao: string; categoria_manual: string; origem: string;
  pesquisa: boolean; conferida: boolean; probabilidade: number | null; imagem?: ImagemPirads;
  categoria?: string; avisos?: string[];
}
export interface Estado {
  psa: number | null; psa_data: string; diametros: number[]; volume_usar: string;
  volume_auto: { ml: number; fonte: string; pesquisa: boolean; diametros: number[] } | null;
  biparametrico: boolean; qualidade: string; hemorragia: boolean; outros: string; geral_manual: string;
  lesoes: Lesao[]; volume_ml?: number | null; volume_fonte?: string; psad?: number | null; geral?: string;
  pesquisa?: boolean; a_conferir?: number;
}
interface Setor { id: string; nome: string; zona: string; nivel: string; lado: string }
interface Resposta {
  estado: Estado; texto: string; achados: string; impressao: string; pode: boolean; esquema: Esquema;
  setores?: Setor[]; zonas?: Record<string, string>; categorias?: Record<string, string>; cores?: Record<string, string>;
  dce?: Record<string, string>; epe?: Record<string, string>; marca_pesquisa?: string;
}
type ImagemAberta = () => { series_uid: string; sop_uid: string; frame: number } | null;

async function json<T>(c: string, corpo?: unknown): Promise<T> {
  const r = await pedir(`${location.origin}/api/web/pirads/${c}`, {
    method: corpo === undefined ? "GET" : "POST",
    headers: corpo === undefined ? {} : { "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo), cache: "no-store",
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = ((await r.json()) as { error?: string }).error || msg; } catch { /* sem corpo */ }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

const fmt = (v: number | null | undefined, casas = 1): string =>
  v === null || v === undefined ? "—" : v.toFixed(casas).replace(".", ",");

function dentro(p: number[][], x: number, y: number): boolean {
  let d = false;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    if ((p[i][1] > y) !== (p[j][1] > y) && x < ((p[j][0] - p[i][0]) * (y - p[i][1])) / (p[j][1] - p[i][1]) + p[i][0]) d = !d;
  }
  return d;
}

function numero(v: string): number | null {
  const x = Number(String(v).replace(",", "."));
  return v.trim() === "" || !Number.isFinite(x) ? null : x;
}

export class PainelPirads {
  readonly raiz = el("div", { class: "pirads" });
  private r: Resposta | null = null;
  private atual = -1;
  private modelo: Modelo | null = null;
  private espera = 0;
  private pedido = 0;                                  // a resposta de um pedido mais antigo que o último não vale
  private refazer = false;                             // algum pedido em curso pediu para refazer a tela
  private msg = el("span", { class: "esq-msg", "aria-live": "polite" });
  /** o que muda com as contas do servidor (o resto da tela fica: não perde o que está sendo digitado) */
  private refs: { faixa?: HTMLElement; vol?: HTMLElement; tbody?: HTMLElement; cat?: HTMLElement; avisos?: HTMLElement;
    setores?: HTMLElement; cv?: HTMLCanvasElement; geral?: HTMLElement } = {};

  constructor(private study: string, private imagemAberta: ImagemAberta,
              private aoLaudo: (texto: string) => Promise<boolean>) {
    (window as unknown as Record<string, unknown>).__ipePirads = this; // testes
  }

  get estado(): Estado | null { return this.r?.estado ?? null; }

  async abrir(): Promise<void> {
    this.raiz.replaceChildren(el("p", { class: "dica" }, tr("Abrindo o PI-RADS…")));
    try {
      const [r, ms] = await Promise.all([json<Resposta>(`estado?study=${encodeURIComponent(this.study)}`), modelos()]);
      this.r = r;
      this.modelo = ms.modelos.find((m) => m.id === "prostata") || null;
      this.atual = r.estado.lesoes.length ? 0 : -1;
      this.montar();
    } catch (e) {
      this.raiz.replaceChildren(el("p", {}, `${tr("Não deu para falar com o servidor:")} ${(e as Error).message}`));
    }
  }

  /** Manda o estado ao servidor (grava, se pode; senão só calcula). Com `reconstruir` (lesão nova, excluída, setor,
   * imagem), a tela é refeita com o estado do servidor; sem, só as contas entram no estado da tela e são pintadas
   * (os campos ficam como estão, com o que está sendo digitado). */
  private mudou(imediato = false, reconstruir = false): void {
    clearTimeout(this.espera);
    this.refazer = this.refazer || reconstruir;
    const ir = async () => {
      if (!this.r) return;
      const base = this.r;
      const meu = ++this.pedido;
      try {
        const r = await json<Resposta>(base.pode ? "gravar" : "calcular", { study: this.study, estado: base.estado });
        if (meu !== this.pedido) return;                 // chegou fora de ordem: a resposta do mais novo vem depois
        reconstruir = this.refazer;
        this.refazer = false;
        if (reconstruir) {
          this.r = { ...base, ...r };
        } else {
          const loc = base.estado, srv = r.estado;
          loc.volume_ml = srv.volume_ml; loc.volume_fonte = srv.volume_fonte; loc.psad = srv.psad; loc.geral = srv.geral;
          loc.pesquisa = srv.pesquisa; loc.a_conferir = srv.a_conferir;
          srv.lesoes.forEach((l, i) => {
            const x = loc.lesoes[i];
            if (!x) return;
            x.categoria = l.categoria; x.avisos = l.avisos;
            if (!x.zona) x.zona = l.zona;
            if (l.imagem) x.imagem = l.imagem;
          });
          this.r = { ...base, ...r, estado: loc };
        }
        this.msg.textContent = base.pode ? tr("Salvo.") : "";
      } catch (e) {
        this.msg.textContent = (e as Error).message;
      }
      if (reconstruir) this.montar();
      else this.pintar();
    };
    if (imediato) void ir();
    else this.espera = window.setTimeout(() => void ir(), 500);
  }

  private campo(rotulo: string, ...filhos: Node[]): HTMLElement {
    return el("label", { class: "pir-campo" }, el("span", {}, tr(rotulo)), ...filhos);
  }

  private entrada(valor: string, aoMudar: (v: string) => void, props: Record<string, string> = {}): HTMLInputElement {
    const i = el("input", { type: "text", inputmode: "decimal", value: valor, ...props });
    if (!this.r?.pode) i.disabled = true;
    i.onchange = () => { aoMudar(i.value); this.mudou(true); };
    return i;
  }

  private escolha(op: [string, string][], valor: string, aoMudar: (v: string) => void): HTMLSelectElement {
    const s = el("select", {});
    for (const [v, t] of op) {
      const o = el("option", { value: v }, tr(t));
      if (v === valor) o.selected = true;
      s.append(o);
    }
    if (!this.r?.pode) s.disabled = true;
    s.onchange = () => { aoMudar(s.value); this.mudou(true); };
    return s;
  }

  private caixa(texto: string, valor: boolean, aoMudar: (v: boolean) => void): HTMLElement {
    const c = el("input", { type: "checkbox" });
    c.checked = valor;
    if (!this.r?.pode) c.disabled = true;
    c.onchange = () => { aoMudar(c.checked); this.mudou(true); };
    return el("label", { class: "pir-caixa" }, c, tr(texto));
  }

  private montar(): void {
    const r = this.r;
    if (!r) return;
    const e = r.estado;
    const lesao = e.lesoes[this.atual] || null;
    const faixa = el("div", { class: "pir-pesquisa", role: "alert" });

    // ---- glândula e PSA
    const d = e.diametros.length === 3 ? e.diametros : [0, 0, 0];
    const diam = (i: number) => this.entrada(d[i] ? String(d[i]).replace(".", ",") : "", (v) => {
      const n = e.diametros.length === 3 ? [...e.diametros] : [0, 0, 0];
      n[i] = numero(v) || 0;
      e.diametros = n;                                 // o elipsoide só vale com os três (o servidor confere)
    }, { size: "5", placeholder: "mm" });
    const usar = this.escolha([["elipsoide", "Elipsoide (0,52 × AP × T × CC)"],
      ...(e.volume_auto ? [["auto", `${tr("Segmentação automática")}: ${fmt(e.volume_auto.ml)} mL (${e.volume_auto.fonte})`] as [string, string]] : [])],
    e.volume_usar || (e.volume_auto ? "auto" : "elipsoide"), (v) => { e.volume_usar = v; });
    const vol = el("div", { class: "pir-volume" });
    const gl = el("fieldset", { class: "pir-grupo" }, el("legend", {}, tr("Glândula e PSA")),
      this.campo("PSA (ng/mL)", this.entrada(e.psa !== null ? String(e.psa).replace(".", ",") : "", (v) => { e.psa = numero(v); }, { size: "6" })),
      this.campo("Data do PSA", (() => {
        const i = el("input", { type: "date", value: e.psa_data || "" });
        if (!r.pode) i.disabled = true;
        i.onchange = () => { e.psa_data = i.value; this.mudou(true); };
        return i;
      })()),
      this.campo("AP", diam(0)), this.campo("Transverso", diam(1)), this.campo("Craniocaudal", diam(2)),
      this.campo("Volume por", usar), vol,
      el("div", { class: "pir-linha" },
        this.caixa("Biparamétrica (sem DCE)", e.biparametrico, (v) => { e.biparametrico = v; }),
        this.caixa("Hemorragia pós-biópsia", e.hemorragia, (v) => { e.hemorragia = v; })),
      this.campo("Qualidade", this.entrada(e.qualidade, (v) => { e.qualidade = v; }, { inputmode: "text", size: "30" })));

    // ---- lesões
    const tbody = el("tbody", {});
    const tabela = el("table", { class: "pir-tabela" },
      el("thead", {}, el("tr", {}, ...["Nº", "Localização", "Tamanho", "T2", "DWI", "DCE", "PI-RADS"].map((t) => el("th", {}, tr(t))))),
      tbody);
    const bNova = botao("Nova lesão", () => {
      e.lesoes.push({ n: e.lesoes.length + 1, zona: "", setores: [], tamanho_mm: null, t2: null, dwi: null, dce: "", adc: null,
        epe: "", descricao: "", categoria_manual: "", origem: "medico", pesquisa: false, conferida: true, probabilidade: null });
      this.atual = e.lesoes.length - 1;
      this.mudou(true, true);
    });
    const bExcluir = botao("Excluir lesão", () => {
      if (!lesao) return;
      e.lesoes.splice(this.atual, 1);
      this.atual = Math.min(this.atual, e.lesoes.length - 1);
      this.mudou(true, true);
    });
    bNova.hidden = bExcluir.hidden = !r.pode;
    bExcluir.disabled = !lesao;

    // ---- a lesão escolhida
    const editor = el("fieldset", { class: "pir-grupo" }, el("legend", {}, lesao ? `${tr("Lesão")} ${lesao.n}` : tr("Lesão (escolha ou crie uma)")));
    if (lesao) {
      const pontos: [string, string][] = [["", "—"], ["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]];
      const zonas: [string, string][] = [["", "—"], ...Object.entries(r.zonas || {})];
      const cats: [string, string][] = [["", "pela regra"], ...Object.keys(r.categorias || {}).map((k) => [k, `PI-RADS ${k}`] as [string, string])];
      const bImg = botao("Ligar à imagem aberta", () => {
        const im = this.imagemAberta();
        if (!im) { this.msg.textContent = tr("Abra uma imagem deste exame no quadro ativo."); return; }
        lesao.imagem = { ...im };
        this.mudou(true, true);
      });
      bImg.hidden = !r.pode;
      editor.append(
        this.campo("Zona", this.escolha(zonas, lesao.zona, (v) => { lesao.zona = v; })),
        el("div", { class: "pir-setores" }),
        this.campo("Maior diâmetro (mm)", this.entrada(lesao.tamanho_mm ? String(lesao.tamanho_mm).replace(".", ",") : "",
          (v) => { lesao.tamanho_mm = numero(v); }, { size: "5" })),
        el("div", { class: "pir-linha" },
          this.campo("T2", this.escolha(pontos, lesao.t2 ? String(lesao.t2) : "", (v) => { lesao.t2 = v ? Number(v) : null; })),
          this.campo("Difusão", this.escolha(pontos, lesao.dwi ? String(lesao.dwi) : "", (v) => { lesao.dwi = v ? Number(v) : null; })),
          this.campo("DCE", this.escolha([["", "não avaliado"], ["-", "negativo"], ["+", "positivo"]], lesao.dce, (v) => { lesao.dce = v; }))),
        this.campo("ADC (× 10⁻⁶ mm²/s)", this.entrada(lesao.adc ? String(lesao.adc) : "", (v) => { lesao.adc = numero(v); }, { size: "6" })),
        this.campo("Extensão extraprostática", this.escolha([["", "—"], ...Object.entries(r.epe || {}).filter(([k]) => k)], lesao.epe,
          (v) => { lesao.epe = v; })),
        this.campo("Descrição", this.entrada(lesao.descricao, (v) => { lesao.descricao = v; }, { inputmode: "text", size: "34" })),
        this.campo("Categoria", this.escolha(cats, lesao.categoria_manual, (v) => { lesao.categoria_manual = v; })),
        el("div", { class: "pir-cat-calc" }),
        el("div", { class: "pir-avisos" }),
        el("div", { class: "pir-linha" }, bImg, el("span", { class: "dica" }, lesao.imagem?.rotulo || "")));
      if (lesao.pesquisa) {
        editor.append(this.caixa("Conferida pelo médico (sugestão do modelo de pesquisa)", lesao.conferida, (v) => { lesao.conferida = v; }));
      }
    }

    // ---- o mapa de setores
    const cv = el("canvas", { class: "pir-mapa", width: "300", height: "405", title: tr("Toque num setor para pôr ou tirar da lesão escolhida") });
    if (this.modelo) {
      const mod = this.modelo;
      cv.onclick = (ev) => {
        if (!r.pode) return;
        const q = cv.getBoundingClientRect();
        const x = ((ev.clientX - q.left) / q.width) * mod.w, y = ((ev.clientY - q.top) / q.height) * mod.h;
        const s = mod.setores.find((s) => (r.setores || []).some((z) => z.id === s.id) && dentro(s.p, x, y));
        if (!s) return;
        const zona = (r.setores || []).find((z) => z.id === s.id)?.zona || "";
        const l = e.lesoes[this.atual];
        if (!l) {                                       // sem lesão escolhida: o toque cria uma no setor
          e.lesoes.push({ n: e.lesoes.length + 1, zona, setores: [s.id], tamanho_mm: null, t2: null, dwi: null, dce: "",
            adc: null, epe: "", descricao: "", categoria_manual: "", origem: "medico", pesquisa: false, conferida: true,
            probabilidade: null });
          this.atual = e.lesoes.length - 1;
          this.mudou(true, true);
          return;
        }
        l.setores = l.setores.includes(s.id) ? l.setores.filter((x) => x !== s.id) : [...l.setores, s.id];
        if (!l.zona) l.zona = zona;
        this.mudou(true, true);
      };
    }

    // ---- geral e botões
    const geral = el("div", { class: "pir-geral" });
    const geralManual = this.escolha([["", "Geral pela maior categoria"],
      ...Object.keys(r.categorias || {}).map((k) => [k, `Geral: PI-RADS ${k}`] as [string, string])], e.geral_manual,
    (v) => { e.geral_manual = v; });
    const outros = el("textarea", { rows: "2", placeholder: tr("Outros achados (vesículas seminais, feixes neurovasculares, linfonodos, ossos…)") });
    outros.value = e.outros;
    if (!r.pode) outros.disabled = true;
    outros.onchange = () => { e.outros = outros.value; this.mudou(true); };
    const bExame = botao("Gravar no exame (SR e mapa)", () => {
      bExame.disabled = true;
      this.msg.textContent = tr("Gravando no exame…");
      json<{ esquemas: number }>("no_exame", { study: this.study })
        .then((x) => { this.msg.textContent = tr(x.esquemas ? "Gravado no exame: o SR do PI-RADS e o mapa de setores." : "Gravado no exame: o SR do PI-RADS."); },
          (x: Error) => { this.msg.textContent = x.message; })
        .finally(() => { bExame.disabled = false; });
    });
    const bLaudo = botao("Mandar ao laudo", () => {
      void this.aoLaudo(this.r?.texto || "").then((ok) => { this.msg.textContent = tr(ok ? "Texto do PI-RADS mandado ao laudo." : "O laudo não pode ser escrito agora."); });
    }, "primario");
    bExame.hidden = bLaudo.hidden = !r.pode;
    this.raiz.replaceChildren(faixa, gl,
      el("div", { class: "pir-corpo" },
        el("div", { class: "pir-esq" }, tabela, el("div", { class: "imp-barra" }, bNova, bExcluir), editor), cv),
      outros, el("div", { class: "imp-barra" }, geral, geralManual, bExame, bLaudo), this.msg);
    const q = (c: string) => (this.raiz.querySelector(c) as HTMLElement | null) || undefined;
    this.refs = { faixa, vol, tbody, cv, geral, cat: q(".pir-cat-calc"), avisos: q(".pir-avisos"), setores: q(".pir-setores") };
    this.pintar();
  }

  /** O que vem das contas: a faixa de pesquisa, o volume e a densidade, a tabela, a categoria, o mapa e a geral. */
  private pintar(): void {
    const r = this.r;
    if (!r) return;
    const e = r.estado, f = this.refs, lesao = e.lesoes[this.atual] || null;
    if (f.faixa) {
      f.faixa.textContent = `${tr("Atenção: há dados de um")} ${tr(r.marca_pesquisa || "modelo de pesquisa — não usar para diagnóstico")}.` +
        (e.a_conferir ? ` ${e.a_conferir} ${tr("lesão(ões) sugerida(s) ainda a conferir.")}` : "");
      f.faixa.hidden = !e.pesquisa;
    }
    if (f.vol) {
      f.vol.textContent = (e.volume_ml ? `${tr("Volume")}: ${fmt(e.volume_ml)} mL (${tr(e.volume_fonte || "")})` : `${tr("Volume")}: —`) +
        (e.psad !== null && e.psad !== undefined ? `  ·  ${tr("Densidade do PSA")}: ${fmt(e.psad, 2)} ng/mL/cm³` : "");
    }
    f.tbody?.replaceChildren(...e.lesoes.map((l, i) => {
      const tdCat = el("td", { class: "pir-cat" }, l.categoria || "?");
      if (l.categoria && r.cores) { tdCat.style.background = r.cores[l.categoria]; tdCat.style.color = "#fff"; }
      const linha = el("tr", { class: i === this.atual ? "escolhida" : "", "data-lesao": String(l.n) },
        el("td", {}, String(l.n)), el("td", {}, (l.pesquisa && !l.conferida ? "⚠ " : "") + this.onde(l)),
        el("td", {}, l.tamanho_mm ? `${fmt(l.tamanho_mm, 0)} mm` : "—"), el("td", {}, String(l.t2 ?? "—")),
        el("td", {}, String(l.dwi ?? "—")), el("td", {}, l.dce === "+" ? "+" : l.dce === "-" ? "−" : "—"), tdCat);
      linha.onclick = () => { this.atual = i; this.montar(); };
      return linha;
    }));
    if (lesao) {
      if (f.cat) f.cat.textContent = lesao.categoria ? `PI-RADS ${lesao.categoria}` : "PI-RADS —";
      if (f.avisos) f.avisos.textContent = (lesao.avisos || []).join("; ");
      if (f.setores) f.setores.textContent = `${tr("Setores")}: ${lesao.setores.length ? this.onde(lesao) : tr("toque no mapa")}`;
    }
    if (f.geral) f.geral.textContent = `PI-RADS ${tr("geral")}: ${e.geral || "—"}`;
    if (f.cv && this.modelo) {
      const mod = this.modelo;
      desenhar(f.cv, mod, r.esquema);
      const c = lesao ? f.cv.getContext("2d") : null;
      if (c && lesao) {                                  // os setores da lesão escolhida em azul
        const k = f.cv.width / mod.w;
        c.strokeStyle = "#1565c0";
        c.lineWidth = 2.5;
        for (const s of mod.setores) {
          if (!lesao.setores.includes(s.id)) continue;
          c.beginPath();
          s.p.forEach(([x, y], i) => (i ? c.lineTo(x * k, y * k) : c.moveTo(x * k, y * k)));
          c.closePath();
          c.stroke();
        }
      }
    }
  }

  private onde(l: Lesao): string {
    const nomes = new Map((this.r?.setores || []).map((s) => [s.id, s.nome]));
    if (l.setores.length) return l.setores.map((s) => tr(nomes.get(s) || s)).join("; ");
    return l.zona ? tr(this.r?.zonas?.[l.zona] || l.zona) : tr("sem localização");
  }
}

/** A janela do botão PI-RADS do visualizador. */
export function abrirPirads(study: string, imagemAberta: ImagemAberta, aoLaudo: (texto: string) => Promise<boolean>): Promise<void> {
  return new Promise((resolver) => {
    const painel = new PainelPirads(study, imagemAberta, aoLaudo);
    const d = el("dialog", { class: "imp-janela larga pirads-janela", "aria-label": tr("PI-RADS — RM de próstata") });
    d.append(el("h3", {}, tr("PI-RADS — RM de próstata")), el("div", { class: "imp-janela-corpo" }, painel.raiz),
      el("div", { class: "imp-janela-botoes" }, botao("Fechar", () => d.close())));
    d.addEventListener("close", () => { d.remove(); resolver(); });
    document.body.append(d);
    d.showModal();
    void painel.abrir();
  });
}
