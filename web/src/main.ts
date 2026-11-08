// Ipê Web (0.99.91, fase W0): login, lista de exames, tira de séries e quadros 2D.
// Rotas pelo endereço depois do # (#/lista, #/exame/<StudyInstanceUID>): o servidor só serve o index.

import "./estilo.css";
import * as API from "./api";
import { setLang, tr } from "./i18n";
import { apagarSelecionadas } from "./medidas";
import { COR_PADRAO, SUV_PADRAO, registrarCores } from "./pet";
import { Disponiveis } from "./disponiveis";
import { Grade, TIPO_ARRASTO, aplicarBotoes, carregarSerie, iniciar, type Ferramenta, type Projecao } from "./visor";

const app = document.getElementById("app")!;
let config: API.Config | null = null;
let grade: Grade | null = null;
let disp: Disponiveis | null = null;

function pararDisponiveis(): void {
  disp?.parar();
  disp = null;
}
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
  pararDisponiveis();
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
      registrarCores(config);
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
  pararDisponiveis();
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
const NOMES_FERRAMENTAS: Record<Ferramenta, string> = {
  janela: "Janela", mover: "Mover", zoom: "Zoom", rolar: "Rolar", linhas: "Linhas de referência",
  regua: "Régua", angulo: "Ângulo", cobb: "Ângulo de Cobb", elipse: "ROI elíptica", retangulo: "ROI retangular",
  poligono: "ROI livre", pixel: "Valor do pixel", seta: "Seta", calibracao: "Calibração",
  suvmax: "SUV máximo perto do cursor",
};

const LAYOUTS: [number, number][] = [[1, 1], [1, 2], [2, 1], [1, 3], [2, 2], [2, 3]];

function janelasProntas(modalidade: string): [string, number, number][] {
  const porMod = config?.["viewer.wl_presets_mod"]?.[modalidade.toUpperCase()];
  const d = (porMod && Object.keys(porMod).length ? porMod : config?.["viewer.wl_presets"]) || {};
  return Object.keys(d).sort().map((k) => d[k]).filter((x) => Array.isArray(x) && x.length >= 3);
}

async function telaExame(study: string): Promise<void> {
  pararDisponiveis();
  grade?.desmontar();
  const todas = await API.qido(`/studies/${study}/series`);
  const segs = todas.filter((s) => API.texto(s, "00080060") === "SEG");
  const series = todas
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
    ...(Object.entries(NOMES_FERRAMENTAS) as [Ferramenta, string][]).map(([f, n]) =>
      el("option", { value: f }, tr(n)))) as HTMLSelectElement;
  const presets = el("select", { title: tr("Janelas prontas") }) as HTMLSelectElement;
  const fps = el("select", { title: tr("quadros/s") },
    ...[5, 10, 15, 20, 30].map((n) => el("option", { value: n, selected: n === 10 }, `${n} ${tr("quadros/s")}`))) as HTMLSelectElement;
  let tocando = false;
  const cine = el("button", {}, tr("Cine"));
  const inverter = el("button", {}, tr("Inverter"));
  const restaurar = el("button", {}, tr("Restaurar"));
  // W1: volume
  const mpr = el("button", { title: tr("Axial, coronal, sagital e o MIP girando da série do quadro ativo, com as linhas de referência") }, tr("MPR"));
  const espessura = el("select", { title: tr("Espessura (quadros A, C, S)") },
    ...[0, 3, 5, 10, 20].map((n) => el("option", { value: n }, n ? `${n} mm` : tr("Corte fino")))) as HTMLSelectElement;
  const projecao = el("select", { title: tr("Projeção da espessura") },
    el("option", { value: "mip" }, "MIP"), el("option", { value: "minip" }, "MinIP"),
    el("option", { value: "media" }, tr("Média"))) as HTMLSelectElement;
  const obliquo = el("button", { title: tr("Dois cliques no quadro ativo definem a reta; o oblíquo vai para o outro quadro de volume") }, tr("Oblíquo"));
  let girando = false;
  const girar = el("button", { title: tr("Gira o MIP (a roda do mouse também gira)") }, tr("Girar MIP"));
  // W3: PET/CT
  const petct = el("button", { title: tr("Fusão, PET e o MIP do PET, com os axiais andando juntos") }, tr("PET/CT"));
  const cores = el("select", { title: tr("Cor da fusão") },
    ...(config?.tabelas_cores ? Object.entries(config.tabelas_cores) : []).map(([k, t]) =>
      el("option", { value: k, selected: k === COR_PADRAO }, tr(t.nome)))) as HTMLSelectElement;
  const opacidade = el("select", { title: tr("Opacidade da fusão") },
    ...[20, 35, 50, 65, 80, 100].map((n) => el("option", { value: n / 100, selected: n === 50 }, `${n}%`))) as HTMLSelectElement;
  const topoSuv = el("select", { title: tr("Topo da janela de SUV") },
    ...[3, 5, 6, 8, 10, 15, 20].map((n) => el("option", { value: n, selected: n === SUV_PADRAO }, `SUV ${n}`))) as HTMLSelectElement;
  const seg = el("select", { title: tr("Segmentação (SEG)") }, el("option", { value: "" }, tr("Sem segmentação")),
    ...segs.map((x) => el("option", { value: API.texto(x, "0020000E") },
      `${API.texto(x, "00200011")} · ${API.texto(x, "0008103E") || "SEG"}`))) as HTMLSelectElement;
  if (!segs.length) seg.disabled = true;
  const apagarMedida = el("button", { title: tr("Apaga a medida selecionada (clique nela antes)") }, tr("Apagar medida"));
  const barra = el("nav", { class: "barra" }, voltar, layout,
    el("label", {}, tr("Botão esquerdo:"), ferr), apagarMedida, presets, inverter, cine, fps, restaurar,
    el("span", { class: "sep" }), mpr, espessura, projecao, obliquo, girar,
    el("span", { class: "sep" }), petct, cores, opacidade, topoSuv, seg);

  // tira
  const tira = el("aside", { class: "tira" }, el("div", { class: "dica" }, tr("Clique numa série para mostrar no quadro ativo, ou arraste-a até um quadro.")));
  const telas = el("section", { class: "grade" });
  const aviso = el("div", { class: "estado" });
  // imagens disponíveis no navegador: o total do exame no cabeçalho, o de cada série na tira
  const geral = el("span", { class: "disponiveis", title: tr("Imagens já baixadas e prontas no navegador") });
  barra.append(geral);
  app.replaceChildren(cabecalho(barra), el("main", { class: "telaexame" }, tira, el("div", { class: "area" }, telas, aviso)), tarja());

  grade = new Grade(telas);
  grade.paciente = paciente;
  grade.aviso = (m: string) => { aviso.textContent = m; };
  (window as unknown as Record<string, unknown>).__ipeGrade = grade; // para os testes de ponta a ponta
  const g = grade;
  const d = new Disponiveis();
  disp = d;
  const barras = new Map<string, { item: HTMLElement; barra: HTMLElement; texto: HTMLElement }>();
  d.aoMudar = () => {
    for (const [uid, b] of barras) {
      const pc = d.porcentagem(uid);
      const fim = pc === null || pc >= 100;
      b.item.classList.toggle("baixando", !fim);
      b.barra.style.width = `${pc ?? 0}%`;
      b.texto.textContent = fim ? "" : `${pc}%`;
    }
    const g0 = d.geral();
    geral.textContent = g0.porcentagem >= 100 ? ""
      : `${tr("Imagens disponíveis:")} ${g0.porcentagem}%${d.cheio ? ` (${tr("memória do navegador cheia; o resto vem ao mostrar")})` : ""}`;
  };
  (window as unknown as Record<string, unknown>).__ipeDisp = d; // testes
  const carregadas = new Map<string, Promise<Awaited<ReturnType<typeof carregarSerie>>>>();
  const pegar = (uid: string) => {
    if (!carregadas.has(uid)) {
      carregadas.set(uid, carregarSerie(study, uid).then((s) => {
        if (s && disp === d) d.conhecer(uid, s.imageIds);
        return s;
      }));
    }
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
    const barra = el("i");
    const texto = el("b");
    const item = el("button", { class: "serie", title: API.texto(s, "0008103E"), draggable: "true",
      "data-serie": uid }, img,
      el("span", {}, `${API.texto(s, "00200011")} ${API.texto(s, "00080060")} · ${API.texto(s, "00201209")}`),
      el("small", {}, API.texto(s, "0008103E")), el("div", { class: "disp" }, barra), texto);
    item.onclick = () => void mostrarNoAtivo(uid);
    item.ondragstart = (e) => {
      e.dataTransfer?.setData(TIPO_ARRASTO, uid);
      if (e.dataTransfer) e.dataTransfer.effectAllowed = "copy";
    };
    barras.set(uid, { item, barra, texto });
    d.estimar(uid, Number(API.texto(s, "00201209") || 0));
    tira.append(item);
  }
  g.aoSoltar = (uid, i) => void mostrarNoAtivo(uid, i);
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
  mpr.onclick = () => {
    if (g.abrirMPR()) {
      layout.value = "2x2";
      ferr.value = "linhas";
      aplicarBotoes("linhas");
      aviso.textContent = "";
    }
  };
  petct.onclick = async () => {
    // o PET: o do quadro ativo, ou o maior PET do exame; a TC: a maior do exame
    const maior = (mod: string) => series.filter((x) => API.texto(x, "00080060") === mod)
      .sort((a, b) => Number(API.texto(b, "00201209") || 0) - Number(API.texto(a, "00201209") || 0))[0];
    const ativa = g.quadros[g.ativo]?.serie;
    const ptUid = ativa?.modalidade === "PT" ? ativa.series : (maior("PT") ? API.texto(maior("PT"), "0020000E") : "");
    const ctUid = maior("CT") ? API.texto(maior("CT"), "0020000E") : "";
    if (!ptUid || !ctUid) {
      aviso.textContent = tr("O PET/CT pede uma série de PET e uma de TC no exame.");
      return;
    }
    aviso.textContent = tr("Carregando…");
    const [tc, pet] = await Promise.all([pegar(ctUid), pegar(ptUid)]);
    aviso.textContent = "";
    if (!tc || !pet) return;
    if (!pet.suv) aviso.textContent = `${tr("Sem SUV:")} ${pet.suvMotivo || "?"}.`;
    if (g.abrirPETCT(tc, pet)) {
      layout.value = "1x3";
      g.fusao({ cor: cores.value, opacidade: Number(opacidade.value), suvMax: Number(topoSuv.value) });
    }
  };
  cores.onchange = () => g.fusao({ cor: cores.value });
  opacidade.onchange = () => g.fusao({ opacidade: Number(opacidade.value) });
  topoSuv.onchange = () => g.fusao({ suvMax: Number(topoSuv.value) });
  seg.onchange = async () => {
    aviso.textContent = seg.value ? tr("Carregando…") : "";
    const r = await g.mostrarSegDaSerie(study, seg.value || null, pegar);
    if (r) aviso.textContent = `${r.descricao}: ${r.segmentos.map((x) => x.nome).join(", ")}`;
    else if (seg.value) seg.value = "";
  };
  const aplicarEspessura = () => g.espessura(Number(espessura.value), projecao.value as Projecao);
  espessura.onchange = aplicarEspessura;
  projecao.onchange = aplicarEspessura;
  obliquo.onclick = () => g.obliquoPorDoisPontos();
  girar.onclick = () => {
    girando = !girando;
    g.girar(girando);
    girar.textContent = girando ? tr("Parar o giro") : tr("Girar MIP");
  };
  apagarMedida.onclick = () => {
    if (!apagarSelecionadas()) aviso.textContent = tr("Clique numa medida para selecioná-la antes de apagar.");
  };
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
  // pré-carga: primeiro as séries que estão nos quadros, depois as outras, na ordem da tira
  void (async () => {
    await new Promise((r) => setTimeout(r, 300));
    const nosQuadros = new Set(g.quadros.map((q) => q.serie?.series).filter(Boolean) as string[]);
    const ordem = series.map((x) => API.texto(x, "0020000E"));
    ordem.sort((a, b) => Number(nosQuadros.has(b)) - Number(nosQuadros.has(a)));
    for (const uid of ordem) {
      if (disp !== d) return;
      const s = await pegar(uid);
      if (s && disp === d) d.preCarregar(s.imageIds);
    }
  })();
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
