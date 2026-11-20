// 0.100.37: buscar exames no PACS e baixar — pelo servidor. Só os nós que o servidor compartilha com os clientes
// (Configurações ▸ Rede ▸ nó ▸ "Compartilhar com os clientes"); quem fala com o PACS é o servidor, e o exame baixado
// entra no banco dele. Buscar pede a permissão de busca; baixar, a de download.
import { pedir } from "./api";
import { tr } from "./i18n";

export interface NoPacs { id: number; nome: string; busca: boolean; anteriores: boolean; dicomweb: boolean }
export interface EstudoPacs {
  study_uid: string; patient_name: string; patient_id: string; study_date: string; description: string;
  modalities: string; accession: string; num_images: number; num_series: number; no_servidor: boolean;
  study_id?: string;
}
export interface Download {
  id: number; rotulo: string; no: string; estado: "waiting" | "running" | "done" | "error" | "cancelled";
  feitas: number; total: number; mensagem: string; study_uid: string;
}

async function pedirJson<T>(caminho: string, corpo?: unknown): Promise<T> {
  const r = await pedir(`${location.origin}${caminho}`, {
    method: corpo === undefined ? "GET" : "POST",
    headers: corpo === undefined ? {} : { "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.text()) || msg; } catch { /* sem corpo */ }
    try { msg = (JSON.parse(msg) as { error?: string }).error || msg; } catch { /* texto */ }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, string> = {}, ...filhos: (Node | string)[]): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) e.setAttribute(k, v);
  e.append(...filhos);
  return e;
}

function dataBr(d: string): string {
  return d && d.length === 8 ? `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : d;
}

/** Os nós que o servidor compartilha com esta pessoa (vazio: sem nós ou sem permissão — o botão nem aparece). */
export async function nosDoServidor(): Promise<{ nos: NoPacs[]; baixar: boolean }> {
  try {
    return await pedirJson<{ nos: NoPacs[]; baixar: boolean }>("/api/web/pacs/nos");
  } catch {
    return { nos: [], baixar: false };
  }
}

const ESTADOS: Record<Download["estado"], string> = {
  waiting: "Na fila", running: "Baixando", done: "No servidor", error: "Erro", cancelled: "Cancelado",
};

/** A tela de busca no PACS: filtros, resultado e os downloads desta pessoa, com o andamento. */
export async function telaPacs(abrirExame: (uid: string) => void): Promise<HTMLElement> {
  const raiz = el("div", { class: "tela-pacs" });
  const { nos, baixar: podeBaixar } = await nosDoServidor();
  if (!nos.length) {
    raiz.append(el("div", { class: "dica" }, tr("O servidor não compartilha nenhum nó de busca com você.")));
    return raiz;
  }
  const sNo = el("select", { "aria-label": tr("Onde buscar") }, ...nos.map((n) => el("option", { value: String(n.id) }, n.nome)));
  const nome = el("input", { placeholder: tr("Nome"), "aria-label": tr("Nome") });
  const pid = el("input", { placeholder: tr("ID do paciente"), "aria-label": tr("ID do paciente") });
  const acesso = el("input", { placeholder: tr("Acesso"), "aria-label": tr("Acesso") });
  // 0.100.80: o "nº do exame" — em muitos PACS é o Study ID (0020,0010), à parte do número de acesso
  const numExame = el("input", { placeholder: tr("Nº do exame"), "aria-label": tr("Nº do exame"),
    title: tr("Número do exame no PACS (Study ID). Se o seu PACS chama de número do exame o número de acesso, use o campo Acesso.") });
  const de = el("input", { type: "date", title: tr("De") });
  const ate = el("input", { type: "date", title: tr("Até") });
  const mod = el("select", { title: tr("Modalidade") },
    ...["", "CT", "MR", "MG", "US", "PT", "NM", "CR", "DX", "XA", "RF"].map((m) => el("option", { value: m }, m || tr("Todas"))));
  const bBuscar = el("button", { type: "submit", class: "primario" }, tr("Buscar no PACS"));
  // 0.100.80: atalhos de período — põem a data e já buscam
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const atalho = (rotulo: string, dias: number) => {
    const b = el("button", { type: "button", class: "atalho-data", "data-dias": String(dias) }, tr(rotulo));
    b.onclick = () => {
      const d = new Date();
      d.setDate(d.getDate() - dias);
      de.value = ate.value = iso(d);
      form.requestSubmit();
    };
    return b;
  };
  const form = el("form", { class: "filtros filtros-pacs" }, sNo, nome, pid, acesso, numExame, de, ate,
    atalho("Hoje", 0), atalho("Ontem", 1), mod, bBuscar);
  const estado = el("div", { class: "estado" });
  const corpo = el("tbody");
  // 0.100.80: clicar no título da coluna ordena (de novo: inverte); começa pela data, mais recente primeiro
  type Chave = keyof EstudoPacs;
  const COLUNAS: [string, Chave | ""][] = [["Data", "study_date"], ["Paciente", "patient_name"], ["ID", "patient_id"],
    ["Acesso", "accession"], ["Nº do exame", "study_id"], ["Descrição", "description"], ["Modalidade", "modalities"],
    ["Imagens", "num_images"], ["", ""]];
  let ordem: { chave: Chave; desc: boolean } = { chave: "study_date", desc: true };
  let ultimos: EstudoPacs[] = [];
  const cabecas = COLUNAS.map(([t, k]) => {
    const th = el("th", k ? { "data-col": k, class: "ordenavel", role: "button", tabindex: "0",
      title: tr("Ordenar por esta coluna (clique de novo para inverter)") } : {}, t ? tr(t) : "");
    if (k) {
      const ir = () => {
        ordem = { chave: k, desc: ordem.chave === k ? !ordem.desc : k === "study_date" || k === "num_images" };
        desenhar();
      };
      th.onclick = ir;
      th.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); ir(); } };
    }
    return th;
  });
  const tabela = el("table", { class: "lista lista-pacs" }, el("thead", {}, el("tr", {}, ...cabecas)), corpo);
  const listaDl = el("div", { class: "envios downloads-pacs" });
  const titDl = el("div", { class: "titulo-painel" }, tr("Downloads pelo servidor"));
  raiz.append(form, estado, tabela, titDl, listaDl);

  let relogio = 0;
  let downloads: Download[] = [];
  const desenharDl = () => {
    titDl.hidden = !downloads.length;
    listaDl.replaceChildren(...downloads.map((d) => {
      const pct = d.total ? Math.round((100 * d.feitas) / d.total) : (d.estado === "done" ? 100 : 0);
      const linha = el("div", { class: `envio ${d.estado}`, "data-id": String(d.id) },
        el("div", { class: "envio-titulo" }, `${d.rotulo.replace(/ — pelo (navegador|cliente)$/, "")} ← ${d.no}`),
        el("div", { class: "envio-estado" }, `${tr(ESTADOS[d.estado] || d.estado)}${d.total ? ` · ${d.feitas}/${d.total}` : ""}` +
          `${d.mensagem && d.estado === "error" ? ` · ${d.mensagem}` : ""}`),
        el("progress", { max: "100", value: String(pct) }));
      if (d.estado === "waiting" || d.estado === "running") {
        const b = el("button", { type: "button", class: "link" }, tr("Cancelar"));
        b.onclick = () => { void pedirJson("/api/web/pacs/cancelar", { id: d.id }).then(() => atualizarDl()); };
        linha.append(b);
      } else if (d.estado === "done" && d.study_uid) {
        const b = el("button", { type: "button", class: "link" }, tr("Abrir o exame"));
        b.onclick = () => abrirExame(d.study_uid);
        linha.append(b);
      }
      return linha;
    }));
  };
  const atualizarDl = async () => {
    try {
      downloads = (await pedirJson<{ downloads: Download[] }>("/api/web/pacs/downloads")).downloads;
    } catch { /* sem rede agora */ }
    desenharDl();
    // o que terminou de baixar passa a constar como "no servidor" na tabela
    for (const d of downloads.filter((x) => x.estado === "done")) {
      const b = corpo.querySelector<HTMLButtonElement>(`tr[data-uid="${d.study_uid}"] button.baixar`);
      if (b) trocarPorAbrir(b, d.study_uid);
    }
    clearTimeout(relogio);
    if (raiz.isConnected && downloads.some((d) => d.estado === "waiting" || d.estado === "running")) {
      relogio = window.setTimeout(() => void atualizarDl(), 1500);
    }
  };
  const trocarPorAbrir = (b: HTMLButtonElement, uid: string) => {
    const a = el("button", { type: "button", class: "link" }, tr("Abrir"));
    a.onclick = () => abrirExame(uid);
    b.replaceWith(a);
  };

  form.onsubmit = async (e) => {
    e.preventDefault();
    const filtros = {
      name: nome.value.trim(), patient_id: pid.value.trim(), accession: acesso.value.trim(),
      study_id: numExame.value.trim(), modality: mod.value,
      date_from: de.value.replace(/-/g, ""), date_to: ate.value.replace(/-/g, ""),
    };
    if (!filtros.name && !filtros.patient_id && !filtros.accession && !filtros.study_id && !filtros.date_from) {
      estado.textContent = tr("Diga um nome, ID, acesso, nº do exame ou um período (busca sem filtro pesa no PACS).");
      return;
    }
    if (filtros.date_from && !filtros.date_to) filtros.date_to = filtros.date_from;
    estado.textContent = tr("Buscando no PACS…");
    corpo.replaceChildren();
    bBuscar.disabled = true;
    let r: { estudos: EstudoPacs[] };
    try {
      r = await pedirJson<{ estudos: EstudoPacs[] }>("/api/web/pacs/buscar", { no: Number(sNo.value), filtros });
    } catch (err) {
      estado.textContent = `${tr("A busca não deu certo")}: ${(err as Error).message}`;
      return;
    } finally {
      bBuscar.disabled = false;
    }
    estado.textContent = r.estudos.length ? `${r.estudos.length} ${tr(r.estudos.length === 1 ? "exame" : "exames")}` : tr("Nenhum exame encontrado.");
    ultimos = r.estudos;
    desenhar();
  };
  function valorDe(s: EstudoPacs, k: Chave): string | number {
    if (k === "num_images") return Number(s.num_images ?? -1);
    if (k === "study_date") return `${s.study_date || ""}${(s as unknown as { study_time?: string }).study_time || ""}`;
    return String(s[k] ?? "");
  }
  function desenhar(): void {
    for (const th of cabecas) {
      const k = th.getAttribute("data-col");
      th.classList.toggle("asc", k === ordem.chave && !ordem.desc);
      th.classList.toggle("desc", k === ordem.chave && ordem.desc);
      if (k) th.setAttribute("aria-sort", k === ordem.chave ? (ordem.desc ? "descending" : "ascending") : "none");
    }
    const ordenados = [...ultimos].sort((a, b) => {
      const x = valorDe(a, ordem.chave), y = valorDe(b, ordem.chave);
      const c = typeof x === "number" && typeof y === "number" ? x - y
        : String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: "base" });
      return ordem.desc ? -c : c;
    });
    corpo.replaceChildren();
    for (const s of ordenados) {
      const acao = el("td", { class: "acao" });
      if (s.no_servidor) {
        const b = el("button", { type: "button", class: "link" }, tr("Abrir"));
        b.onclick = () => abrirExame(s.study_uid);
        acao.append(b);
      } else if (podeBaixar) {
        const b = el("button", { type: "button", class: "baixar" }, tr("Baixar"));
        b.onclick = async () => {
          b.disabled = true;
          b.textContent = tr("Pedindo…");
          try {
            await pedirJson("/api/web/pacs/baixar", { no: Number(sNo.value), study: s.study_uid,
              rotulo: `${s.patient_name} — ${dataBr(s.study_date)} ${s.modalities} ${s.description}`.trim() });
            b.textContent = tr("Baixando…");
            void atualizarDl();
          } catch (err) {
            b.disabled = false;
            b.textContent = tr("Baixar");
            estado.textContent = `${tr("O download não foi aceito")}: ${(err as Error).message}`;
          }
        };
        acao.append(b);
      }
      corpo.append(el("tr", { "data-uid": s.study_uid },
        el("td", {}, dataBr(s.study_date)), el("td", {}, s.patient_name), el("td", {}, s.patient_id),
        el("td", {}, s.accession || ""), el("td", {}, s.study_id || ""),
        el("td", {}, s.description), el("td", {}, s.modalities), el("td", { class: "num" }, String(s.num_images ?? "")), acao));
    }
    // o que já terminou de baixar continua como "Abrir" depois de reordenar
    for (const d of downloads.filter((x) => x.estado === "done")) {
      const b = corpo.querySelector<HTMLButtonElement>(`tr[data-uid="${d.study_uid}"] button.baixar`);
      if (b) trocarPorAbrir(b, d.study_uid);
    }
  }
  void atualizarDl();
  nome.focus();
  return raiz;
}
