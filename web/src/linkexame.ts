// 0.100.109: "Link do exame" no Ipê Web — o mesmo do botão direito no Ipê de mesa: cria um link que abre só este
// exame, sem senha, com as permissões e a validade escolhidas; lista os links do exame e revoga.
import { cabecalhos } from "./api";
import { tr } from "./i18n";

interface Link {
  id: string; rotulo: string; perms: string[]; criado_por: string; criado_em: number; expira: number;
  usos: number; revogado: boolean; ativo: boolean;
}
interface Lista { links: Link[]; permissoes: Record<string, string>; validades: number[] }

async function pedirJson<T>(caminho: string, corpo?: unknown): Promise<T> {
  const r = await fetch(`${location.origin}${caminho}`, {
    method: corpo === undefined ? "GET" : "POST", cache: "no-store",
    headers: { ...cabecalhos(), ...(corpo === undefined ? {} : { "Content-Type": "application/json" }) },
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

const quando = (t: number) => (t ? new Date(t * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }) : "");
const NOMES_VALIDADE: Record<number, string> = { 24: "1 dia", 72: "3 dias", 168: "7 dias", 720: "30 dias" };

/** O painel (abre no lugar dos outros painéis do visualizador). */
export async function painelLinkExame(study: string): Promise<HTMLElement> {
  const raiz = el("div", { class: "painel-link-exame" });
  const aviso = el("p", { class: "dica" }, tr("Abre só este exame no Ipê Web, sem senha: sem a lista, sem o banco, sem laudo. Quem tiver o link vê o exame até ele vencer — mande só a quem deve ver."));
  const estado = el("div", { class: "estado", role: "status" });
  const rotulo = el("input", { type: "text", placeholder: tr("Para quem (ex.: Dr. Fulano, cirurgião)"), "aria-label": tr("Para quem") }) as HTMLInputElement;
  const perms = el("div", { class: "perms" });
  const validade = el("select", { "aria-label": tr("Vale por:") }) as HTMLSelectElement;
  const bCriar = el("button", { type: "button" }, tr("Criar e copiar")) as HTMLButtonElement;
  const saida = el("input", { type: "text", readonly: "", class: "link-gerado", "aria-label": tr("Link:") }) as HTMLInputElement;
  saida.hidden = true;
  const lista = el("div", { class: "lista-links" });
  raiz.append(aviso, el("label", {}, tr("Para quem:"), rotulo), el("div", { class: "rotulo" }, tr("O link também pode:")), perms,
    el("label", {}, tr("Vale por:"), validade), bCriar, saida, estado, el("h4", {}, tr("Links deste exame:")), lista);

  let dados: Lista;
  const carregar = async () => {
    dados = await pedirJson<Lista>(`/api/web/links?study=${encodeURIComponent(study)}`);
    lista.replaceChildren();
    if (!dados.links.length) lista.append(el("div", { class: "dica" }, tr("Nenhum link ainda.")));
    for (const x of dados.links) {
      const pode = x.perms.map((p) => tr(dados.permissoes[p] || p)).join(", ") || tr("só ver");
      const sit = x.revogado ? tr("revogado") : (x.ativo ? tr("ativo") : tr("vencido"));
      const linha = el("div", { class: `link-item ${x.ativo ? "ativo" : "inativo"}` },
        el("b", {}, x.rotulo || x.id), ` · ${pode} · ${tr("Vence")} ${quando(x.expira)} · ${tr("Usos")}: ${x.usos} · ${sit}`);
      if (x.ativo) {
        const b = el("button", { type: "button", class: "link" }, tr("Revogar")) as HTMLButtonElement;
        b.onclick = async () => {
          if (!window.confirm(tr("Revogar o link de “{}”? Quem estiver com ele aberto perde o acesso na hora.").replace("{}", x.rotulo || x.id))) return;
          try { await pedirJson("/api/web/links/revogar", { id: x.id }); await carregar(); } catch (e) { estado.textContent = (e as Error).message; }
        };
        linha.append(" ", b);
      }
      lista.append(linha);
    }
  };
  try {
    await carregar();
  } catch (e) {
    raiz.replaceChildren(el("div", { class: "estado" }, `${tr("Não consegui abrir os links do exame")}: ${(e as Error).message}`));
    return raiz;
  }
  const caixas = new Map<string, HTMLInputElement>();
  for (const [k, nome] of Object.entries(dados!.permissoes)) {
    const c = el("input", { type: "checkbox", value: k }) as HTMLInputElement;
    caixas.set(k, c);
    perms.append(el("label", { class: "perm" }, c, ` ${tr(nome)}`));
  }
  for (const h of dados!.validades) validade.append(el("option", { value: String(h) }, tr(NOMES_VALIDADE[h] || `${h} h`)));
  bCriar.onclick = async () => {
    bCriar.disabled = true;
    estado.textContent = "";
    try {
      const r = await pedirJson<{ caminho: string }>("/api/web/links", {
        study, rotulo: rotulo.value.trim(), horas: Number(validade.value),
        perms: [...caixas].filter(([, c]) => c.checked).map(([k]) => k),
      });
      saida.value = `${location.origin}${r.caminho}`;
      saida.hidden = false;
      saida.select();
      try { await navigator.clipboard.writeText(saida.value); estado.textContent = tr("Link criado e copiado."); }
      catch { estado.textContent = tr("Link criado — copie do campo acima."); }
      await carregar();
    } catch (e) {
      estado.textContent = `${tr("Não consegui criar o link: {}").replace("{}", (e as Error).message)}`;
    } finally {
      bCriar.disabled = false;
    }
  };
  return raiz;
}
