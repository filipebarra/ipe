// 0.100.37: buscar exames no PACS e baixar — pelo servidor. Só os nós que o servidor compartilha com os clientes
// (Configurações ▸ Rede ▸ nó ▸ "Compartilhar com os clientes"); quem fala com o PACS é o servidor, e o exame baixado
// entra no banco dele. Buscar pede a permissão de busca; baixar, a de download.
import { pedir } from "./api";
import { tr } from "./i18n";

export interface NoPacs { id: number; nome: string; busca: boolean; anteriores: boolean; dicomweb: boolean }
export interface EstudoPacs {
  study_uid: string; patient_name: string; patient_id: string; study_date: string; description: string;
  modalities: string; accession: string; num_images: number; num_series: number; no_servidor: boolean;
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
  const de = el("input", { type: "date", title: tr("De") });
  const ate = el("input", { type: "date", title: tr("Até") });
  const mod = el("select", { title: tr("Modalidade") },
    ...["", "CT", "MR", "MG", "US", "PT", "NM", "CR", "DX", "XA", "RF"].map((m) => el("option", { value: m }, m || tr("Todas"))));
  const bBuscar = el("button", { type: "submit", class: "primario" }, tr("Buscar no PACS"));
  const form = el("form", { class: "filtros filtros-pacs" }, sNo, nome, pid, acesso, de, ate, mod, bBuscar);
  const estado = el("div", { class: "estado" });
  const corpo = el("tbody");
  const tabela = el("table", { class: "lista lista-pacs" },
    el("thead", {}, el("tr", {}, ...["Data", "Paciente", "ID", "Descrição", "Modalidade", "Imagens", ""].map((t) => el("th", {}, t ? tr(t) : "")))),
    corpo);
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
      name: nome.value.trim(), patient_id: pid.value.trim(), accession: acesso.value.trim(), modality: mod.value,
      date_from: de.value.replace(/-/g, ""), date_to: ate.value.replace(/-/g, ""),
    };
    if (!filtros.name && !filtros.patient_id && !filtros.accession && !filtros.date_from) {
      estado.textContent = tr("Diga um nome, ID, acesso ou um período (busca sem filtro pesa no PACS).");
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
    const ordenados = [...r.estudos].sort((a, b) => (b.study_date || "").localeCompare(a.study_date || ""));
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
        el("td", {}, s.description), el("td", {}, s.modalities), el("td", { class: "num" }, String(s.num_images ?? "")), acao));
    }
  };
  void atualizarDl();
  nome.focus();
  return raiz;
}
