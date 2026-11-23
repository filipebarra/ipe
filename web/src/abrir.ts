// 0.100.103: abrir um exame por chamada externa — #/abrir?acesso=12345 ou #/abrir?id=98765&data=20261123&mod=MR.
// Procura no servidor; se não estiver, no PACS (pelos nós que o servidor compartilha), baixa e abre quando chegar.
// O login continua obrigatório: sem sessão, o Ipê Web pede a senha e depois volta para este endereço.
import { pedir } from "./api";
import { tr } from "./i18n";
import type { Download } from "./pacs";

export interface EstudoAchado {
  study_uid: string; patient_name: string; patient_id: string; study_date: string; description: string;
  modalities: string; accession: string; num_images: number; no_servidor?: boolean; no?: number; no_nome?: string;
}
export interface RespostaAbrir {
  criterios: Record<string, string>; servidor: EstudoAchado[]; pacs: EstudoAchado[]; erros: string[]; baixar: boolean;
}

/** Os parâmetros depois de "#/abrir?" (vazio se o endereço não for de abertura). */
export function parametros(hash: string): Record<string, string> | null {
  const m = /^#\/abrir(?:\?(.*))?$/.exec(hash);
  if (!m) return null;
  const out: Record<string, string> = {};
  new URLSearchParams(m[1] || "").forEach((v, k) => { out[k] = v; });
  return out;
}

async function json<T>(caminho: string, corpo?: unknown): Promise<T> {
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

/** O servidor já mostra alguma série deste exame (a primeira imagem chegou e entrou no banco)? */
async function jaTemSerie(uid: string): Promise<boolean> {
  try {
    const r = await pedir(`${location.origin}/dicomweb/studies/${uid}/series`);
    return r.ok && ((await r.json()) as unknown[]).length > 0;
  } catch { return false; }
}

function oQueProcura(p: Record<string, string>): string {
  const partes: string[] = [];
  if (p.acesso) partes.push(`${tr("acesso")} ${p.acesso}`);
  if (p.id) partes.push(`ID ${p.id}`);
  if (p.data) partes.push(dataBr(p.data.replace(/-/g, "")));
  if (p.mod) partes.push(p.mod.toUpperCase());
  if (p.uid) partes.push(p.uid);
  return partes.join(" · ");
}

/** A tela de abertura: procura, baixa se for preciso e chama `abrirExame` quando o exame está no servidor. */
export function telaAbrir(p: Record<string, string>, abrirExame: (uid: string) => void): HTMLElement {
  const raiz = el("div", { class: "tela-abrir" });
  const titulo = el("h2", {}, `${tr("Abrir exame")}: ${oQueProcura(p)}`);
  const estado = el("div", { class: "estado", role: "status" }, tr("Procurando no servidor…"));
  const barra = el("progress", { max: "100" }) as HTMLProgressElement;
  barra.hidden = true;
  const lista = el("div", { class: "abrir-lista" });
  raiz.append(titulo, estado, barra, lista);

  const baixarEAbrir = async (e: EstudoAchado) => {
    lista.replaceChildren();
    estado.textContent = `${tr("Pedindo ao PACS")} (${e.no_nome || ""})…`;
    try {
      await json("/api/web/pacs/baixar", { no: e.no, study: e.study_uid,
        rotulo: `${e.patient_name} — ${dataBr(e.study_date)} ${e.modalities} ${e.description}`.trim() });
    } catch (err) {
      estado.textContent = `${tr("O download não foi aceito")}: ${(err as Error).message}`;
      return;
    }
    barra.hidden = false;
    const acompanhar = async () => {
      if (!raiz.isConnected) return;
      let d: Download | undefined;
      try {
        d = (await json<{ downloads: Download[] }>("/api/web/pacs/downloads")).downloads
          .filter((x) => x.study_uid === e.study_uid).sort((a, b) => b.id - a.id)[0];
      } catch { /* sem rede agora: tenta de novo */ }
      if (d?.estado === "done") { abrirExame(e.study_uid); return; }
      // 0.100.105: abre assim que as primeiras imagens chegam; o visor acompanha o resto
      if (d && d.feitas > 0 && (d.estado === "running" || d.estado === "waiting") && await jaTemSerie(e.study_uid)) {
        abrirExame(e.study_uid);
        return;
      }
      if (d?.estado === "error" || d?.estado === "cancelled") {
        barra.hidden = true;
        estado.textContent = `${tr("O download não terminou")}: ${d.mensagem || d.estado}`;
        return;
      }
      const pct = d?.total ? Math.round((100 * d.feitas) / d.total) : 0;
      barra.value = pct;
      estado.textContent = `${tr("Baixando do PACS")}${d?.total ? ` · ${d.feitas}/${d.total}` : ""}…`;
      window.setTimeout(() => void acompanhar(), 1500);
    };
    void acompanhar();
  };

  const tabela = (itens: EstudoAchado[], doPacs: boolean, podeBaixar: boolean) => {
    const corpo = el("tbody");
    for (const e of itens) {
      const acao = el("td", { class: "acao" });
      const b = el("button", { type: "button" }, tr(!doPacs || e.no_servidor ? "Abrir" : "Baixar e abrir"));
      if (doPacs && !e.no_servidor && !podeBaixar) b.setAttribute("disabled", "");
      b.onclick = () => { if (!doPacs || e.no_servidor) abrirExame(e.study_uid); else void baixarEAbrir(e); };
      acao.append(b);
      corpo.append(el("tr", {}, el("td", {}, dataBr(e.study_date)), el("td", {}, e.patient_name),
        el("td", {}, e.patient_id), el("td", {}, e.accession || ""), el("td", {}, e.modalities),
        el("td", {}, e.description), el("td", {}, doPacs ? e.no_nome || "" : tr("servidor")), acao));
    }
    const cab = el("tr", {}, ...["Data", "Paciente", "ID", "Acesso", "Modalidade", "Descrição", "Onde", ""]
      .map((t) => el("th", {}, t ? tr(t) : "")));
    lista.replaceChildren(el("table", { class: "lista lista-pacs" }, el("thead", {}, cab), corpo));
  };

  void (async () => {
    let r: RespostaAbrir;
    try {
      r = await json<RespostaAbrir>("/api/web/abrir", p);
    } catch (err) {
      estado.textContent = `${tr("Não deu para procurar")}: ${(err as Error).message}`;
      return;
    }
    if (!raiz.isConnected) return;
    if (r.servidor.length === 1) { abrirExame(r.servidor[0].study_uid); return; }
    if (r.servidor.length > 1) {
      estado.textContent = `${r.servidor.length} ${tr("exames no servidor: escolha qual abrir.")}`;
      tabela(r.servidor, false, r.baixar);
      return;
    }
    const prontos = r.pacs.filter((e) => e.no_servidor);
    if (r.pacs.length === 1 && prontos.length === 1) { abrirExame(prontos[0].study_uid); return; }
    if (r.pacs.length === 1 && r.baixar) { void baixarEAbrir(r.pacs[0]); return; }
    if (r.pacs.length) {
      estado.textContent = r.baixar
        ? `${r.pacs.length} ${tr("exames no PACS: escolha qual baixar e abrir.")}`
        : tr("O exame está no PACS, mas o seu perfil não permite baixar.");
      tabela(r.pacs, true, r.baixar);
      return;
    }
    estado.textContent = tr("Nenhum exame encontrado no servidor nem no PACS.")
      + (r.erros.length ? ` ${tr("Avisos")}: ${r.erros.join("; ")}` : "");
  })();
  return raiz;
}
