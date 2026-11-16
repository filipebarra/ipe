// 0.100.55: anexar PDF e imagens ao exame pelo navegador — arrastar os arquivos para o exame (como no Ipê de mesa)
// ou pelo botão "Anexar PDF ou imagem…". O servidor converte em DICOM dentro do exame (PDF → série "Documentos
// anexados"; imagem → "Imagens anexadas"), guarda e manda pelas regras de envio do exame. Os documentos (PDF) do
// exame ficam listados embaixo das séries e abrem numa aba nova.
import { cabecalhos } from "./api";
import { tr } from "./i18n";

const PDF = [".pdf"];
const IMAGENS = [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"];
export const ACEITOS = [...PDF, ...IMAGENS];

export function aceito(nome: string): boolean {
  const n = nome.toLowerCase();
  return ACEITOS.some((s) => n.endsWith(s));
}

interface Resultado { n: number; series: string[]; avisos: string[]; enviados: number }
interface Documento { sop: string; serie: string; titulo: string }

async function chamar<T>(caminho: string, corpo?: unknown): Promise<T> {
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

function base64(f: File): Promise<string> {
  return new Promise((ok, falha) => {
    const leitor = new FileReader();
    leitor.onload = () => ok(String(leitor.result || "").replace(/^data:[^,]*,/, ""));
    leitor.onerror = () => falha(leitor.error || new Error(f.name));
    leitor.readAsDataURL(f);
  });
}

/** Manda os arquivos aceitos; devolve o texto para a barra de estado (ou "" se o médico desistiu). */
export async function anexar(study: string, arquivos: File[], paciente: string, perguntar = true): Promise<{ texto: string; ok: boolean }> {
  const bons = arquivos.filter((f) => aceito(f.name));
  const fora = arquivos.filter((f) => !aceito(f.name)).map((f) => `${f.name}: ${tr("formato não aceito — salve como PDF")}`);
  if (!bons.length) return { texto: fora.join(" · ") || tr("Nenhum arquivo."), ok: false };
  if (perguntar && !window.confirm(`${tr("Anexar ao exame")} ${paciente}: ${bons.length} ${tr("arquivo(s)")}?\n\n${bons.map((f) => f.name).join("\n")}`))
    return { texto: "", ok: false };
  const corpo = { study, arquivos: await Promise.all(bons.map(async (f) => ({ nome: f.name, dados: await base64(f) }))) };
  const r = await chamar<Resultado>("/api/web/anexos", corpo);
  const avisos = [...fora, ...r.avisos.map((a) => tr(a))];
  let texto = `${r.n} ${tr("anexo(s) gravado(s) no exame")}`;
  if (r.enviados) texto += `; ${tr("enviado(s) a")} ${r.enviados} ${tr("destino(s)")}`;
  texto += ".";
  if (avisos.length) texto += ` ${tr("Não entraram:")} ${avisos.join(" · ")}`;
  return { texto, ok: r.n > 0 };
}

export async function documentos(study: string): Promise<Documento[]> {
  return (await chamar<{ documentos: Documento[] }>(`/api/web/documentos?study=${encodeURIComponent(study)}`)).documentos;
}

/** Abre o PDF numa aba nova (a aba abre antes de baixar, para o bloqueador de janelas não barrar). */
export async function abrirDocumento(study: string, d: Documento): Promise<void> {
  const aba = window.open("", "_blank");
  try {
    const r = await fetch(`${location.origin}/api/web/documento?study=${encodeURIComponent(study)}&sop=${encodeURIComponent(d.sop)}`,
      { headers: cabecalhos(), cache: "no-store" });
    if (!r.ok) throw new Error(`${r.status}`);
    const url = URL.createObjectURL(await r.blob());
    if (aba) aba.location.href = url;
    else {
      const a = document.createElement("a");
      a.href = url;
      a.download = d.titulo.toLowerCase().endsWith(".pdf") ? d.titulo : `${d.titulo}.pdf`;
      a.click();
    }
    setTimeout(() => URL.revokeObjectURL(url), 120_000);
  } catch (e) {
    aba?.close();
    throw e;
  }
}

/** A lista "Documentos" (embaixo das séries) e o botão de anexar. */
export class PainelDocumentos {
  readonly raiz = document.createElement("div");
  private lista = document.createElement("div");
  private entrada = document.createElement("input");

  constructor(private study: string, private podeAnexar: boolean, private aoAnexar: (arquivos: File[]) => void,
              private aviso: (texto: string) => void) {
    this.raiz.className = "documentos";
    this.lista.className = "lista-docs";
    const titulo = document.createElement("div");
    titulo.className = "titulo-painel";
    titulo.textContent = tr("Documentos");
    this.raiz.append(titulo, this.lista);
    if (podeAnexar) {
      this.entrada.type = "file";
      this.entrada.multiple = true;
      this.entrada.accept = ACEITOS.join(",");
      this.entrada.hidden = true;
      this.entrada.onchange = () => {
        const fs = [...(this.entrada.files || [])];
        this.entrada.value = "";
        if (fs.length) this.aoAnexar(fs);
      };
      const b = document.createElement("button");
      b.type = "button";
      b.className = "anexar";
      b.textContent = tr("Anexar PDF ou imagem…");
      b.title = tr("Ou arraste os arquivos para o exame");
      b.onclick = () => this.entrada.click();
      this.raiz.append(b, this.entrada);
    }
    void this.carregar();
  }

  async carregar(): Promise<void> {
    let docs: Documento[] = [];
    try { docs = await documentos(this.study); } catch { /* sem documentos */ }
    this.lista.replaceChildren();
    for (const d of docs) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "doc";
      b.textContent = `📄 ${d.titulo}`;
      b.title = tr("Abrir o PDF numa aba nova");
      b.onclick = () => void abrirDocumento(this.study, d).catch((e) => this.aviso(`${tr("Não abriu:")} ${(e as Error).message}`));
      this.lista.append(b);
    }
    if (!docs.length) {
      const v = document.createElement("div");
      v.className = "dica";
      v.textContent = this.podeAnexar ? tr("Nenhum. Arraste PDF ou imagens para o exame para anexar.") : tr("Nenhum.");
      this.lista.append(v);
    }
  }
}
