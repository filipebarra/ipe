// Ipê Web (0.99.91, fase W0): login, lista de exames, tira de séries e quadros 2D.
// Rotas pelo endereço depois do # (#/lista, #/exame/<StudyInstanceUID>): o servidor só serve o index.

import "./estilo.css";
import * as API from "./api";
import { setLang, tr } from "./i18n";
import { Grade, aplicarBotoes, carregarSerie, iniciar, type Ferramenta } from "./visor";

const app = document.getElementById("app")!;
let config: API.Config | null = null;
let grade: Grade | null = null;
const NAO_MOSTRA = new Set(["SR", "KO", "PR", "DOC", "RTSTRUCT", "RTPLAN", "SEG", "REG", "OT_PDF"]);

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, unknown> = {},
  ...filhos: (Node | string)[]): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") e.className = String(v);
    else if (k.startsWith("on") && typeof v === "function") (e as unknown as Record<string, unknown>)[k] = v;
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, String(v));
  }
  e.append(...filhos);
  return e;
}

function tarja(): HTMLElement {
  return el("div", { class: "tarja" }, tr("Não destinado a uso diagnóstico"));
}

// ------------------------------------------------------------------ login
function telaLogin(msg = ""): void {
  grade?.desmontar();
  grade = null;
  const u = el("input", { id: "usuario", autocomplete: "username", required: true }) as HTMLInputElement;
  const s = el("input", { id: "senha", type: "password", autocomplete: "current-password", required: true }) as HTMLInputElement;
  const erro = el("div", { class: "erro", role: "alert" }, msg);
  const form = el("form", { class: "login" },
    el("h1", {}, tr("Ipê Web")),
    el("label", { for: "usuario" }, tr("Usuário")), u,
    el("label", { for: "senha" }, tr("Senha")), s,
    el("button", { type: "submit" }, tr("Entrar")), erro, tarja());
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    erro.textContent = "";
    try {
      await API.entrar(u.value, s.value);
      config = await API.configuracao();
      setLang(config.lang);
      await iniciar();
      rota();
    } catch (e) {
      const m = String((e as Error).message);
      erro.textContent = m === "401" ? tr("Usuário ou senha incorretos.")
        : m === "429" ? tr("Muitas tentativas: espere alguns minutos.") : tr("Não foi possível falar com o servidor.");
    }
  };
  app.replaceChildren(form);
  u.focus();
}

API.quandoEncerrar(() => telaLogin(tr("Sessão encerrada: entre de novo.")));

function cabecalho(...extra: Node[]): HTMLElement {
  const quem = config?.usuario.full_name || config?.usuario.username || "";
  const b = el("button", { class: "sair", onclick: async () => { await API.sair(); config = null; telaLogin(); } },
    tr("Sair"));
  return el("header", {}, el("strong", {}, tr("Ipê Web")), ...extra, el("span", { class: "quem" }, quem), b);
}

// ------------------------------------------------------------------ lista
const MODALIDADES = ["", "CT", "MR", "MG", "US", "PT", "NM", "CR", "DX", "XA", "RF"];

function dataBr(d: string): string {
  return d && d.length === 8 ? `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : d;
}

async function telaLista(): Promise<void> {
  grade?.desmontar();
  grade = null;
  const busca = el("input", { placeholder: tr("Nome, ID ou acesso"), id: "busca" }) as HTMLInputElement;
  const de = el("input", { type: "date", title: tr("De") }) as HTMLInputElement;
  const ate = el("input", { type: "date", title: tr("Até") }) as HTMLInputElement;
  const mod = el("select", { title: tr("Modalidade") },
    ...MODALIDADES.map((m) => el("option", { value: m }, m || tr("Todas")))) as HTMLSelectElement;
  const corpo = el("tbody");
  const estado = el("div", { class: "estado" });
  const form = el("form", { class: "filtros" }, busca, de, ate, mod, el("button", { type: "submit" }, tr("Buscar")));
  const tabela = el("table", { class: "lista" },
    el("thead", {}, el("tr", {}, ...["Data", "Paciente", "ID", "Descrição", "Modalidade", "Imagens"].map(
      (c) => el("th", {}, tr(c))))), corpo);
  app.replaceChildren(cabecalho(), el("main", { class: "telalista" }, form, estado, tabela), tarja());
  const procurar = async () => {
    estado.textContent = tr("Carregando…");
    corpo.replaceChildren();
    const q = new URLSearchParams();
    const t = busca.value.trim();
    if (t) q.set("PatientName", `*${t}*`);
    const d1 = de.value.replace(/-/g, ""), d2 = ate.value.replace(/-/g, "");
    if (d1 || d2) q.set("StudyDate", `${d1}-${d2}`);
    if (mod.value) q.set("ModalitiesInStudy", mod.value);
    q.set("limit", "300");
    const rows = await API.qido(`/studies?${q}`);
    estado.textContent = rows.length ? "" : tr("Nenhum exame encontrado.");
    for (const r of rows) {
      const uid = API.texto(r, "0020000D");
      const tr_ = el("tr", { tabindex: 0 },
        el("td", {}, dataBr(API.texto(r, "00080020"))), el("td", {}, API.texto(r, "00100010")),
        el("td", {}, API.texto(r, "00100020")), el("td", {}, API.texto(r, "00081030")),
        el("td", {}, ((r["00080061"]?.Value as string[]) || []).join(", ")),
        el("td", { class: "num" }, API.texto(r, "00201208")));
      tr_.ondblclick = () => { location.hash = `#/exame/${uid}`; };
      tr_.onkeydown = (e) => { if ((e as KeyboardEvent).key === "Enter") location.hash = `#/exame/${uid}`; };
      corpo.append(tr_);
    }
  };
  form.onsubmit = (e) => { e.preventDefault(); void procurar(); };
  busca.focus();
  await procurar();
}

// ------------------------------------------------------------------ exame
const LAYOUTS: [number, number][] = [[1, 1], [1, 2], [2, 1], [2, 2], [2, 3]];

function janelasProntas(modalidade: string): [string, number, number][] {
  const porMod = config?.["viewer.wl_presets_mod"]?.[modalidade.toUpperCase()];
  const d = (porMod && Object.keys(porMod).length ? porMod : config?.["viewer.wl_presets"]) || {};
  return Object.keys(d).sort().map((k) => d[k]).filter((x) => Array.isArray(x) && x.length >= 3);
}

async function telaExame(study: string): Promise<void> {
  grade?.desmontar();
  const series = (await API.qido(`/studies/${study}/series`))
    .filter((s) => !NAO_MOSTRA.has(API.texto(s, "00080060")))
    .sort((a, b) => Number(API.texto(a, "00200011") || 0) - Number(API.texto(b, "00200011") || 0));
  const estudo = (await API.qido(`/studies?StudyInstanceUID=${study}`))[0];
  if (!estudo) {
    app.replaceChildren(cabecalho(), el("div", { class: "estado" }, tr("Sem permissão para ver este exame.")));
    return;
  }
  void API.avisarAbertura(study);
  const paciente = `${API.texto(estudo, "00100010")}  ${API.texto(estudo, "00100020")}\n${dataBr(API.texto(estudo, "00080020"))}  ${API.texto(estudo, "00081030")}`;

  // barra
  const voltar = el("button", { onclick: () => { location.hash = "#/lista"; } }, `← ${tr("Voltar à lista")}`);
  const layout = el("select", { title: tr("Layout") },
    ...LAYOUTS.map(([l, c]) => el("option", { value: `${l}x${c}` }, `${l}×${c}`))) as HTMLSelectElement;
  const ferr = el("select", { title: tr("Botão esquerdo:") },
    ...(["janela", "mover", "zoom", "rolar"] as Ferramenta[]).map((f) =>
      el("option", { value: f }, tr({ janela: "Janela", mover: "Mover", zoom: "Zoom", rolar: "Rolar" }[f])))) as HTMLSelectElement;
  const presets = el("select", { title: tr("Janelas prontas") }) as HTMLSelectElement;
  const fps = el("select", { title: tr("quadros/s") },
    ...[5, 10, 15, 20, 30].map((n) => el("option", { value: n, selected: n === 10 }, `${n} ${tr("quadros/s")}`))) as HTMLSelectElement;
  let tocando = false;
  const cine = el("button", {}, tr("Cine"));
  const inverter = el("button", {}, tr("Inverter"));
  const restaurar = el("button", {}, tr("Restaurar"));
  const barra = el("nav", { class: "barra" }, voltar, layout,
    el("label", {}, tr("Botão esquerdo:"), ferr), presets, inverter, cine, fps, restaurar);

  // tira
  const tira = el("aside", { class: "tira" }, el("div", { class: "dica" }, tr("Clique numa série para mostrar no quadro ativo.")));
  const telas = el("section", { class: "grade" });
  const aviso = el("div", { class: "estado" });
  app.replaceChildren(cabecalho(barra), el("main", { class: "telaexame" }, tira, el("div", { class: "area" }, telas, aviso)), tarja());

  grade = new Grade(telas);
  grade.paciente = paciente;
  (window as unknown as Record<string, unknown>).__ipeGrade = grade; // para os testes de ponta a ponta
  const g = grade;
  const carregadas = new Map<string, Promise<Awaited<ReturnType<typeof carregarSerie>>>>();
  const pegar = (uid: string) => {
    if (!carregadas.has(uid)) carregadas.set(uid, carregarSerie(study, uid));
    return carregadas.get(uid)!;
  };
  const encherPresets = () => {
    const s = g.quadros[g.ativo]?.serie;
    const lista = janelasProntas(s?.modalidade || "");
    presets.replaceChildren(el("option", { value: "" }, tr("Janelas prontas")),
      el("option", { value: "arquivo" }, `0 · ${tr("Do arquivo")}`),
      ...lista.map(([n, w, l], i) => el("option", { value: String(i) }, `${n} (${w}/${l})`)));
    presets.onchange = () => {
      if (presets.value === "arquivo") g.janelaDoArquivo();
      else if (presets.value !== "") {
        const [, w, l] = lista[Number(presets.value)];
        g.janela(Number(w), Number(l));
      }
      presets.value = "";
    };
  };
  g.aoMudar = encherPresets;
  const mostrarNoAtivo = async (uid: string, i = g.ativo) => {
    aviso.textContent = tr("Carregando…");
    const s = await pegar(uid);
    if (!s) {
      aviso.textContent = tr("Esta série não tem imagens que o navegador mostre.");
      return;
    }
    aviso.textContent = "";
    await g.mostrar(i, s);
    encherPresets();
  };
  for (const s of series) {
    const uid = API.texto(s, "0020000E");
    const img = el("img", { alt: "" }) as HTMLImageElement;
    void API.miniatura(study, uid).then((u) => { if (u) img.src = u; });
    const item = el("button", { class: "serie", title: API.texto(s, "0008103E") }, img,
      el("span", {}, `${API.texto(s, "00200011")} ${API.texto(s, "00080060")} · ${API.texto(s, "00201209")}`),
      el("small", {}, API.texto(s, "0008103E")));
    item.onclick = () => void mostrarNoAtivo(uid);
    tira.append(item);
  }
  const montar = (l: number, c: number) => {
    g.montar(l, c);
    // quadros vazios ganham as primeiras séries, na ordem
    const livres = g.quadros.map((q, i) => (q.serie ? -1 : i)).filter((i) => i >= 0);
    const usadas = new Set(g.quadros.map((q) => q.serie?.series).filter(Boolean));
    const resto = series.map((s) => API.texto(s, "0020000E")).filter((u) => !usadas.has(u));
    livres.forEach((i, k) => { if (resto[k]) void mostrarNoAtivo(resto[k], i); });
  };
  layout.onchange = () => {
    const [l, c] = layout.value.split("x").map(Number);
    montar(l, c);
  };
  ferr.onchange = () => aplicarBotoes(ferr.value as Ferramenta);
  inverter.onclick = () => g.inverter();
  restaurar.onclick = () => g.restaurar();
  cine.onclick = () => {
    tocando = !tocando;
    g.cine(tocando ? Number(fps.value) : null);
    cine.textContent = tocando ? tr("Parar") : tr("Cine");
  };
  fps.onchange = () => { if (tocando) g.cine(Number(fps.value)); };
  const inicial: [number, number] = series.length >= 2 ? [1, 2] : [1, 1];
  layout.value = `${inicial[0]}x${inicial[1]}`;
  montar(...inicial);
  encherPresets();
}

// ------------------------------------------------------------------ rotas
function rota(): void {
  if (!API.tokenAtual()) {
    telaLogin();
    return;
  }
  const h = location.hash || "#/lista";
  const m = h.match(/^#\/exame\/([0-9.]+)$/);
  if (m) void telaExame(m[1]);
  else void telaLista();
}

window.addEventListener("hashchange", rota);
window.addEventListener("resize", () => grade?.redimensionar());
rota();
