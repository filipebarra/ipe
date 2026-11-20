// 0.100.71: Cadastros no Ipê Web — usuários e perfis, nós DICOM e identidades, impressoras DICOM, automações de IA
// e o registro de acesso. É o que o administrador mantinha só no Ipê de mesa do servidor. Só administradores; a
// troca da própria senha (a senha provisória pede no primeiro acesso) vale para qualquer pessoa.
// Senhas e segredos nunca vêm do servidor: o campo vazio deixa o que estava.
import { pedir } from "./api";
import { getLang, tr } from "./i18n";
import { gradeDeModelos } from "./esquemas";
import { botao, confirmar, el, janela } from "./impressoes";

interface Usuario {
  id: number; username: string; full_name: string; role: string; papel: string; active: boolean; must_change: boolean;
  criado: string; ultimo: string;
}
interface Nome { k: string; nome: string }
interface Usuarios { eu: string; usuarios: Usuario[]; papeis: Nome[]; permissoes: Nome[]; perfis: Record<string, string[]> }
interface No {
  id: number; name: string; kind: string; ae_title: string; host: string; port: number; base_url: string; username: string;
  tem_senha: boolean; verify_tls: boolean; auth: string; token_url: string; client_id: string; tem_segredo: boolean;
  scope: string; retrieve: string; move_destination: string; use_in_search: boolean; use_in_priors: boolean;
  use_in_send: boolean; stream_open: boolean | null; compartilhar_clientes: boolean; priority: number; active: boolean;
  note: string; endereco: string;
}
interface Identidade { id: number; name: string; ae_title: string; move_destination: string; note: string; allowed_nodes: number[] }
interface Nos { nos: No[]; identidades: Identidade[]; auths: Nome[]; ae_local: string; rede: boolean }
interface Impressora {
  name: string; ae_title: string; host: string; port: number; calling_ae: string; film_size: string; medium: string;
  destination: string; magnification: string; copies: number; dpi: number; color: boolean; compartilhar_clientes: boolean;
  usada_em: string[];
}
interface Impressoras { impressoras: Impressora[]; tamanhos: string[]; midias: string[]; destinos: string[]; ampliacoes: string[]; ae_local: string }
type ValorIa = boolean | string | number | (string | number)[];
interface CampoIa {
  k: string; tipo: "bool" | "texto" | "numero" | "inteiro" | "nos" | "lista" | "escolha"; rotulo: string; valor: ValorIa;
  dica: string; vazio?: string; min?: number; max?: number; passo?: number; sufixo?: string;
  opcoes?: { k: string | number | boolean; nome: string }[];
}
interface Ferramenta { id: string; nome: string; titulo: string; explicacao?: string; auto: string; ligada: boolean; campos: CampoIa[] }
interface Ia { ler_antes: boolean; ferramentas: Ferramenta[]; nos: { id: number; nome: string }[]; nota: string }
interface LinhaRegistro { quando: string; usuario: string; acao: string; detalhe: string; study_uid: string; maquina: string }
interface Registro { linhas: LinhaRegistro[]; cheio: boolean; usuarios: string[]; acoes: string[]; periodos: Nome[] }
interface Resposta { ok: boolean; mensagem: string; ms?: number; usada_em?: string[] }

function caminho(c: string): string {
  const idioma = getLang();
  if (idioma !== "pt") c += `${c.includes("?") ? "&" : "?"}lang=${idioma}`;
  return `${location.origin}/api/web/cadastros/${c}`;
}

async function pedirJson<T>(c: string, corpo?: unknown): Promise<T> {
  const r = await pedir(caminho(c), {
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

// ---------------------------------------------------------------------- formulário
type Opcao = [string | number | boolean | null, string];
interface Campo {
  k: string; rotulo: string; tipo?: "texto" | "senha" | "numero" | "bool" | "escolha"; opcoes?: Opcao[]; dica?: string;
  vazio?: string; min?: number; max?: number; fixo?: boolean; traduzido?: boolean;
}
interface Formulario {
  el: HTMLElement; ler: () => Record<string, unknown>; linha: (k: string) => HTMLElement;
  entrada: (k: string) => HTMLInputElement | HTMLSelectElement; erro: (t: string) => void;
}

/** Os campos de uma janela de cadastro: uma linha por campo, com o rótulo ligado à entrada. */
function formulario(campos: Campo[], valores: Record<string, unknown>): Formulario {
  const linhas = new Map<string, HTMLElement>();
  const entradas = new Map<string, HTMLInputElement | HTMLSelectElement>();
  const caixa = el("div", { class: "cad-form" });
  for (const c of campos) {
    const id = `cad-${c.k}`;
    const rot = c.traduzido ? c.rotulo : tr(c.rotulo);
    const v = valores[c.k];
    let linha: HTMLElement;
    if (c.tipo === "bool") {
      const e = el("input", { type: "checkbox", id });
      e.checked = !!v;
      entradas.set(c.k, e);
      linha = el("label", { class: "cad-caixa", for: id }, e, el("span", {}, rot));
    } else if (c.tipo === "escolha") {
      const e = el("select", { id });
      (c.opcoes || []).forEach(([, nome], i) => e.append(el("option", { value: String(i) }, nome)));
      e.value = String(Math.max(0, (c.opcoes || []).findIndex(([k]) => k === v)));
      entradas.set(c.k, e);
      linha = el("div", { class: "imp-campo" }, el("label", { for: id }, rot), e);
    } else {
      const e = el("input", { id, type: c.tipo === "senha" ? "password" : c.tipo === "numero" ? "number" : "text" });
      if (c.tipo === "senha") e.autocomplete = "new-password";
      else e.autocomplete = "off";
      if (c.min !== undefined) e.min = String(c.min);
      if (c.max !== undefined) e.max = String(c.max);
      if (c.vazio) e.placeholder = tr(c.vazio);
      if (c.fixo) e.readOnly = true;
      e.value = v === undefined || v === null ? "" : String(v);
      entradas.set(c.k, e);
      linha = el("div", { class: "imp-campo" }, el("label", { for: id }, rot), e);
    }
    if (c.dica) linha.title = tr(c.dica);
    linhas.set(c.k, linha);
    caixa.append(linha);
  }
  const erro = el("p", { class: "cad-erro", role: "alert" });
  caixa.append(erro);
  return {
    el: caixa,
    linha: (k) => linhas.get(k)!,
    entrada: (k) => entradas.get(k)!,
    erro: (t) => { erro.textContent = t; },
    ler: () => {
      const out: Record<string, unknown> = {};
      for (const c of campos) {
        const e = entradas.get(c.k)!;
        if (c.tipo === "bool") out[c.k] = (e as HTMLInputElement).checked;
        else if (c.tipo === "escolha") out[c.k] = (c.opcoes || [])[Number(e.value)]?.[0] ?? null;
        else if (c.tipo === "numero") out[c.k] = Number(e.value || 0);
        else out[c.k] = e.value;
      }
      return out;
    },
  };
}

/** Uma janela de cadastro: os campos, o que mais houver, Cancelar e Salvar. `gravar` devolve o erro ou "". */
function janelaDeCadastro(titulo: string, f: Formulario, extra: Node[], gravar: (d: Record<string, unknown>) => Promise<void>,
  larga = false, salvar = "Salvar"): HTMLDialogElement {
  const bSalvar = botao(salvar, () => {
    f.erro("");
    bSalvar.disabled = true;
    gravar(f.ler()).then(() => d.close(), (e: Error) => f.erro(e.message)).finally(() => { bSalvar.disabled = false; });
  }, "primario");
  const d = janela(titulo, [f.el, ...extra], [botao("Cancelar", () => d.close()), bSalvar], larga);
  return d;
}

function tabela(classe: string, colunas: string[]): { el: HTMLTableElement; corpo: HTMLTableSectionElement } {
  const corpo = el("tbody");
  const t = el("table", { class: `cad-tabela ${classe}` },
    el("thead", {}, el("tr", {}, ...colunas.map((c) => el("th", { scope: "col" }, tr(c))))), corpo);
  return { el: t, corpo };
}

function vazia(corpo: HTMLElement, n: number, texto: string): void {
  corpo.replaceChildren(el("tr", { class: "vazio" }, el("td", { colspan: String(n) }, tr(texto))));
}

function acoes(...bs: HTMLButtonElement[]): HTMLTableCellElement {
  return el("td", { class: "cad-acoes" }, ...bs);
}

// ---------------------------------------------------------------------- trocar a própria senha
/** A janela de trocar a senha; com `obrigatoria`, é a senha provisória pedindo a troca (não dá para cancelar). */
export function trocarSenha(obrigatoria = false): Promise<boolean> {
  return new Promise((resolver) => {
    let feito = false;
    const f = formulario([{ k: "atual", rotulo: obrigatoria ? "Senha provisória" : "Senha atual", tipo: "senha" },
      { k: "nova", rotulo: "Senha nova", tipo: "senha" }, { k: "de_novo", rotulo: "Senha nova, de novo", tipo: "senha" }], {});
    const bOk = botao("Trocar a senha", () => {
      const v = f.ler();
      f.erro("");
      if (v.nova !== v.de_novo) { f.erro(tr("As duas senhas novas não são iguais.")); return; }
      bOk.disabled = true;
      pedirJson<Resposta>("minha_senha", { atual: v.atual, nova: v.nova })
        .then(() => { feito = true; d.close(); }, (e: Error) => f.erro(e.message)).finally(() => { bOk.disabled = false; });
    }, "primario");
    const texto = obrigatoria ? [el("p", { class: "dica" }, tr("A sua senha é provisória: escolha uma nova para continuar."))] : [];
    const d = janela(tr("Trocar a senha"), [...texto, f.el], obrigatoria ? [bOk] : [botao("Cancelar", () => d.close()), bOk]);
    d.classList.add("cad-senha");
    if (obrigatoria) d.addEventListener("cancel", (e) => e.preventDefault());
    d.addEventListener("close", () => resolver(feito));
  });
}

// ---------------------------------------------------------------------- a tela
export async function telaCadastros(): Promise<HTMLElement> {
  const raiz = el("div", { class: "cadastros" });
  const nota = el("div", { class: "imp-nota", "aria-live": "polite" });
  const dizer = (t: string, erro = false) => { nota.textContent = t; nota.classList.toggle("erro", erro); };
  const tentar = async (fn: () => Promise<unknown>) => {
    try { await fn(); } catch (e) { dizer((e as Error).message, true); }
  };

  // ================================================================== usuários
  let us: Usuarios = await pedirJson<Usuarios>("usuarios");
  const tUs = tabela("cad-usuarios", ["Usuário", "Nome", "Perfil", "Situação", "Último acesso", ""]);
  const carregarUsuarios = async () => { us = await pedirJson<Usuarios>("usuarios"); desenharUsuarios(); };
  const desenharUsuarios = () => {
    if (!us.usuarios.length) { vazia(tUs.corpo, 6, "Nenhum usuário."); return; }
    tUs.corpo.replaceChildren(...us.usuarios.map((u) => {
      const sit = !u.active ? tr("Desativado") : u.must_change ? tr("Ativo — troca a senha no próximo acesso") : tr("Ativo");
      const tr_ = el("tr", { "data-u": u.username, class: u.active ? "" : "cad-inativo" },
        el("td", {}, u.username), el("td", {}, u.full_name), el("td", {}, u.papel), el("td", { class: "sit" }, sit),
        el("td", {}, u.ultimo || tr("nunca")),
        acoes(botao("Editar", () => editarUsuario(u)), botao("Redefinir a senha", () => redefinir(u)),
          botao(u.active ? "Desativar" : "Ativar", () => void tentar(async () => {
            const r = await pedirJson<Resposta>("usuario", { id: u.id, full_name: u.full_name, role: u.role, active: !u.active });
            dizer(r.mensagem);
            await carregarUsuarios();
          })),
          botao("Excluir", () => void excluirUsuario(u))));
      return tr_;
    }));
  };
  const editarUsuario = (u: Usuario | null) => {
    const papeis: Opcao[] = us.papeis.map((p) => [p.k, p.nome]);
    const campos: Campo[] = [{ k: "username", rotulo: "Usuário", fixo: !!u }, { k: "full_name", rotulo: "Nome completo" },
      { k: "role", rotulo: "Perfil", tipo: "escolha", opcoes: papeis }];
    if (!u) {
      campos.push({ k: "password", rotulo: "Senha provisória", tipo: "senha", dica: "Pelo menos 6 caracteres." },
        { k: "must_change", rotulo: "Trocar a senha no primeiro acesso", tipo: "bool" });
    }
    campos.push({ k: "active", rotulo: "Ativo (pode entrar no Ipê)", tipo: "bool" });
    const f = formulario(campos, u ? { ...u } : { role: "medico", active: true, must_change: true });
    janelaDeCadastro(tr(u ? "Editar o usuário" : "Novo usuário"), f, [], async (d) => {
      const r = await pedirJson<Resposta>("usuario", u ? { ...d, id: u.id } : d);
      dizer(r.mensagem);
      await carregarUsuarios();
    });
  };
  const redefinir = (u: Usuario) => {
    const f = formulario([{ k: "senha", rotulo: "Senha provisória", tipo: "senha", dica: "Pelo menos 6 caracteres." }], {});
    const aviso = el("p", { class: "dica" }, `${u.username}: ${tr("no próximo acesso a pessoa escolhe a senha dela. As sessões abertas dela são encerradas.")}`);
    janelaDeCadastro(tr("Redefinir a senha"), f, [aviso], async (d) => {
      const r = await pedirJson<Resposta>("usuario_senha", { id: u.id, senha: d.senha });
      dizer(r.mensagem);
      await carregarUsuarios();
    }, false, "Redefinir");
  };
  const excluirUsuario = async (u: Usuario) => {
    if (!(await confirmar(tr("Excluir o usuário"), `${tr("Excluir o usuário")} ${u.username}?`,
      tr("Para só impedir o acesso e manter o histórico, prefira desativar."), "Excluir"))) return;
    await tentar(async () => {
      const r = await pedirJson<Resposta>("usuario_excluir", { id: u.id });
      dizer(r.mensagem);
      await carregarUsuarios();
    });
  };
  const perfis = () => {
    const papeis = us.papeis;
    const caixas = new Map<string, HTMLInputElement>();
    const corpo = el("tbody", {}, ...us.permissoes.map((p) => el("tr", {}, el("th", { scope: "row" }, p.nome),
      ...papeis.map((r) => {
        const c = el("input", { type: "checkbox", "aria-label": `${r.nome}: ${p.nome}` });
        c.checked = (us.perfis[r.k] || []).includes(p.k);
        c.disabled = r.k === "admin";
        caixas.set(`${r.k}|${p.k}`, c);
        return el("td", {}, c);
      }))));
    const t = el("table", { class: "cad-tabela cad-perfis" },
      el("thead", {}, el("tr", {}, el("th", {}, tr("Permissão")), ...papeis.map((r) => el("th", { scope: "col" }, r.nome)))), corpo);
    const erro = el("p", { class: "cad-erro", role: "alert" });
    const gravar = (corpo_: unknown) => {
      pedirJson<Resposta>("perfis", corpo_).then(async (r) => { dizer(r.mensagem); d.close(); await carregarUsuarios(); },
        (e: Error) => { erro.textContent = e.message; });
    };
    const d = janela(tr("Perfis e permissões"),
      [el("p", { class: "dica" }, tr("O que cada perfil pode fazer. O administrador sempre pode tudo. Vale na hora, também para quem já está com o Ipê aberto.")), t, erro],
      [botao("Voltar ao padrão", () => gravar({ padrao: true })), botao("Cancelar", () => d.close()),
        botao("Salvar", () => {
          const tab: Record<string, string[]> = {};
          for (const r of papeis) tab[r.k] = us.permissoes.filter((p) => caixas.get(`${r.k}|${p.k}`)!.checked).map((p) => p.k);
          gravar({ perfis: tab });
        }, "primario")], true);
  };
  const abaUsuarios = el("div", { class: "imp-aba" },
    el("div", { class: "imp-barra" }, botao("Novo usuário…", () => editarUsuario(null), "primario"),
      botao("Perfis e permissões…", perfis), botao("Trocar a minha senha…", () => void trocarSenha().then((ok) => { if (ok) dizer(tr("Senha trocada.")); }))),
    el("div", { class: "imp-rolagem" }, tUs.el));
  desenharUsuarios();

  // ================================================================== nós DICOM e identidades
  let ns: Nos | null = null;
  const tNos = tabela("cad-nos", ["Nome", "Tipo", "Endereço", "Usado em", "Situação", ""]);
  const tIds = tabela("cad-identidades", ["Nome", "AE Title de origem", "Destino do C-MOVE", "Nós", ""]);
  const carregarNos = async () => { ns = await pedirJson<Nos>("nos"); desenharNos(); };
  const desenharNos = () => {
    if (!ns) return;
    const dados = ns;
    if (!dados.nos.length) vazia(tNos.corpo, 6, "Nenhum nó DICOM cadastrado.");
    else {
      tNos.corpo.replaceChildren(...dados.nos.map((n) => {
        const usos = [n.use_in_search && tr("busca"), n.use_in_priors && tr("anteriores"), n.use_in_send && tr("envio"),
          n.compartilhar_clientes && tr("compartilhado com os clientes")].filter(Boolean).join(", ");
        const sit = el("td", { class: "sit" }, n.active ? tr("Ativo") : tr("Desativado"));
        return el("tr", { "data-no": n.name, class: n.active ? "" : "cad-inativo" }, el("td", {}, n.name),
          el("td", {}, n.kind === "dicomweb" ? "DICOMweb" : "DIMSE"), el("td", {}, n.endereco), el("td", {}, usos), sit,
          acoes(botao("Editar", () => editarNo(n)),
            botao("Testar", () => { sit.textContent = tr("Testando…"); void testarNo({ ...n }).then((r) => { sit.textContent = r.mensagem; sit.classList.toggle("erro", !r.ok); }); }),
            botao("Excluir", () => void excluir("no_excluir", { id: n.id }, tr("Excluir o nó DICOM"), n.name, carregarNos))));
      }));
    }
    if (!dados.identidades.length) vazia(tIds.corpo, 5, "Nenhuma identidade: o servidor fala com os nós com o AE dele.");
    else {
      tIds.corpo.replaceChildren(...dados.identidades.map((i) => el("tr", { "data-id": i.name }, el("td", {}, i.name),
        el("td", {}, i.ae_title), el("td", {}, i.move_destination),
        el("td", {}, i.allowed_nodes.length ? dados.nos.filter((n) => i.allowed_nodes.includes(n.id)).map((n) => n.name).join(", ") : tr("todos")),
        acoes(botao("Editar", () => editarIdentidade(i)),
          botao("Excluir", () => void excluir("identidade_excluir", { id: i.id }, tr("Excluir a identidade"), i.name, carregarNos))))));
    }
  };
  const testarNo = async (d: Record<string, unknown>): Promise<Resposta> => {
    try { return await pedirJson<Resposta>("no_testar", d); } catch (e) { return { ok: false, mensagem: (e as Error).message }; }
  };
  const excluir = async (rota: string, corpo: Record<string, unknown>, titulo: string, nome: string, depois: () => Promise<void>) => {
    if (!(await confirmar(titulo, `${titulo}: ${nome}?`, "", "Excluir"))) return;
    await tentar(async () => {
      let r = await pedirJson<Resposta>(rota, corpo);
      if (!r.ok && r.usada_em?.length) {
        if (!(await confirmar(titulo, r.mensagem, tr("Esses destinos deixam de imprimir até você escolher outra impressora neles."), "Excluir assim mesmo"))) return;
        r = await pedirJson<Resposta>(rota, { ...corpo, confirmar: true });
      }
      dizer(r.mensagem, !r.ok);
      await depois();
    });
  };
  const editarNo = (n: No | null) => {
    if (!ns) return;
    const web = ["base_url", "auth", "username", "password", "token_url", "client_id", "client_secret", "scope", "verify_tls"];
    const dimse = ["ae_title", "host", "port", "retrieve", "move_destination"];
    const campos: Campo[] = [
      { k: "kind", rotulo: "Tipo de conexão", tipo: "escolha", opcoes: [["dimse", tr("DICOM clássico (DIMSE) — C-FIND, C-GET/C-MOVE, C-STORE")], ["dicomweb", tr("DICOMweb (HTTP) — QIDO-RS, WADO-RS, STOW-RS")]] },
      { k: "name", rotulo: "Nome", vazio: "Ex.: PACS da clínica" },
      { k: "ae_title", rotulo: "AE Title" }, { k: "host", rotulo: "IP ou nome" },
      { k: "port", rotulo: "Porta", tipo: "numero", min: 1, max: 65535 },
      { k: "retrieve", rotulo: "Para baixar", tipo: "escolha", opcoes: [["get", tr("C-GET (mais simples; imagens voltam pela mesma conexão)")], ["move", tr("C-MOVE (o PACS precisa ter este computador cadastrado)")]] },
      { k: "move_destination", rotulo: "Destino do C-MOVE", vazio: "vazio = este programa" },
      { k: "base_url", rotulo: "Endereço DICOMweb", vazio: "Ex.: http://192.168.1.216:8042/dicom-web" },
      { k: "auth", rotulo: "Autenticação", tipo: "escolha", opcoes: ns.auths.map((a) => [a.k, a.nome]) },
      { k: "username", rotulo: "Usuário", vazio: "vazio = sem autenticação" },
      { k: "password", rotulo: "Senha ou token", tipo: "senha", vazio: n?.tem_senha ? "guardada — vazio = não muda" : "" },
      { k: "token_url", rotulo: "Endereço do token", vazio: "emissor OIDC ou …/token" }, { k: "client_id", rotulo: "ID do cliente" },
      { k: "client_secret", rotulo: "Segredo do cliente", tipo: "senha", vazio: n?.tem_segredo ? "guardado — vazio = não muda" : "" },
      { k: "scope", rotulo: "Escopo", vazio: "opcional, ex.: openid dicomweb" },
      { k: "verify_tls", rotulo: "Conferir o certificado do servidor (HTTPS)", tipo: "bool", dica: "Desmarque só em rede interna, com certificado próprio, e sabendo o que faz." },
      { k: "use_in_search", rotulo: "Busca (“Todos os nós de busca”, chamada externa e buscas agendadas)", tipo: "bool" },
      { k: "use_in_priors", rotulo: "Busca de anteriores (painel Anteriores e pré-busca automática)", tipo: "bool" },
      { k: "use_in_send", rotulo: "Envio (aparece em “Enviar para”)", tipo: "bool" },
      { k: "compartilhar_clientes", rotulo: "Compartilhar com os clientes (o Ipê cliente e o Ipê Web buscam e baixam por este nó)", tipo: "bool",
        dica: "Quem fala com o PACS é o servidor, com o AE title e a senha dele: os clientes não recebem o endereço nem as credenciais." },
      { k: "stream_open", rotulo: "Abrir enquanto baixa", tipo: "escolha", opcoes: [[null, tr("Usar o padrão das preferências")], [true, tr("Sempre abrir enquanto baixa (streaming)")], [false, tr("Nunca: esperar o download terminar")]] },
      { k: "priority", rotulo: "Prioridade (0 = primeiro)", tipo: "numero", min: 0, max: 99 },
      { k: "note", rotulo: "Observação" },
      { k: "active", rotulo: "Ativo (pode conectar e enviar para este servidor)", tipo: "bool" },
    ];
    const f = formulario(campos, n ? { ...n } : { kind: "dimse", port: 104, retrieve: "get", auth: "basic", verify_tls: true,
      use_in_search: true, use_in_priors: true, use_in_send: true, active: true, priority: 0, stream_open: null });
    const mostrar = () => {
      const eWeb = f.ler().kind === "dicomweb";
      const auth = String(f.ler().auth);
      for (const k of web) f.linha(k).hidden = !eWeb;
      for (const k of dimse) f.linha(k).hidden = eWeb;
      if (eWeb) {
        for (const k of ["token_url", "client_id", "client_secret", "scope"]) f.linha(k).hidden = !auth.startsWith("oauth2");
        f.linha("username").hidden = auth === "token" || auth === "oauth2_cliente";
      }
    };
    f.entrada("kind").onchange = mostrar;
    f.entrada("auth").onchange = mostrar;
    mostrar();
    const estado = el("span", { class: "cad-teste", "aria-live": "polite" });
    const corpoDoNo = () => ({ ...f.ler(), ...(n ? { id: n.id } : {}) });
    const bTestar = botao("Testar rede", () => {
      estado.textContent = tr("Testando…");
      estado.classList.remove("erro", "ok");
      void testarNo(corpoDoNo()).then((r) => { estado.textContent = r.mensagem; estado.classList.add(r.ok ? "ok" : "erro"); });
    });
    const avisoSegredo = el("p", { class: "dica" }, tr("A senha, o token e o segredo ficam cifrados no servidor e não voltam para o navegador."));
    janelaDeCadastro(tr(n ? "Editar o nó DICOM" : "Novo nó DICOM"), f, [avisoSegredo, el("div", { class: "imp-barra" }, bTestar, estado)], async () => {
      const r = await pedirJson<Resposta>("no", corpoDoNo());
      dizer(r.mensagem);
      await carregarNos();
    }, true);
  };
  const editarIdentidade = (i: Identidade | null) => {
    if (!ns) return;
    const dados = ns;
    const f = formulario([{ k: "name", rotulo: "Nome", vazio: "Ex.: Workstation mama 2" }, { k: "ae_title", rotulo: "AE Title de origem" },
      { k: "move_destination", rotulo: "Destino do C-MOVE", vazio: "vazio = este programa; ou o AE da estação real" },
      { k: "note", rotulo: "Observação" }], i ? { ...i } : {});
    const marcados = new Set(i?.allowed_nodes || []);
    const lista = el("fieldset", { class: "cad-lista" }, el("legend", {}, tr("Nós em que pode ser usada (nenhum marcado = todos):")),
      ...dados.nos.filter((n) => n.kind !== "dicomweb").map((n) => {
        const c = el("input", { type: "checkbox" });
        c.checked = marcados.has(n.id);
        c.onchange = () => { if (c.checked) marcados.add(n.id); else marcados.delete(n.id); };
        return el("label", {}, c, ` ${n.name} (${n.ae_title})`);
      }));
    const aviso = el("p", { class: "imp-aviso" }, tr("Use o AE de outra estação só com o conhecimento da TI: muitos PACS conferem o AE junto com o IP. Toda operação com identidade fica registrada na auditoria."));
    janelaDeCadastro(tr(i ? "Editar a identidade" : "Nova identidade"), f, [lista, aviso], async (d) => {
      const r = await pedirJson<Resposta>("identidade", { ...d, allowed_nodes: [...marcados], ...(i ? { id: i.id } : {}) });
      dizer(r.mensagem);
      await carregarNos();
    });
  };
  const semRede = el("div", { class: "imp-faixa", hidden: "" }, tr("Este servidor está sem a rede DICOM ligada: dá para cadastrar, mas não para testar."));
  const abaNos = el("div", { class: "imp-aba", hidden: "" },
    el("div", { class: "imp-barra" }, botao("Novo nó DICOM…", () => editarNo(null), "primario"), botao("Nova identidade…", () => editarIdentidade(null))),
    semRede, el("div", { class: "imp-rolagem" }, tNos.el),
    el("h3", { class: "cad-titulo" }, tr("Identidades (AE Title de origem)")), el("div", { class: "imp-rolagem baixa" }, tIds.el));

  // ================================================================== impressoras DICOM
  let ps: Impressoras | null = null;
  const tImp = tabela("cad-impressoras", ["Nome", "AE", "Endereço", "Filme", "Compartilhada", "Situação", ""]);
  const carregarImpressoras = async () => { ps = await pedirJson<Impressoras>("impressoras"); desenharImpressoras(); };
  const testarImpressora = async (d: Record<string, unknown>): Promise<Resposta> => {
    try { return await pedirJson<Resposta>("impressora_testar", d); } catch (e) { return { ok: false, mensagem: (e as Error).message }; }
  };
  const desenharImpressoras = () => {
    if (!ps) return;
    if (!ps.impressoras.length) { vazia(tImp.corpo, 7, "Nenhuma impressora DICOM cadastrada."); return; }
    tImp.corpo.replaceChildren(...ps.impressoras.map((p) => {
      const sit = el("td", { class: "sit" }, p.usada_em.length ? `${tr("destinos")}: ${p.usada_em.join(", ")}` : "");
      return el("tr", { "data-imp": p.name }, el("td", {}, p.name), el("td", {}, p.ae_title), el("td", {}, `${p.host}:${p.port}`),
        el("td", {}, `${p.film_size || tr("o tamanho de cada folha")} · ${p.medium}`), el("td", {}, tr(p.compartilhar_clientes ? "Sim" : "Não")), sit,
        acoes(botao("Editar", () => editarImpressora(p)),
          botao("Testar", () => { sit.textContent = tr("Testando…"); void testarImpressora({ ...p }).then((r) => { sit.textContent = r.mensagem; sit.classList.toggle("erro", !r.ok); }); }),
          botao("Duplicar", () => editarImpressora({ ...p, name: `${p.name} (${tr("cópia")})` }, true)),
          botao("Excluir", () => void excluir("impressora_excluir", { name: p.name }, tr("Excluir a impressora DICOM"), p.name, carregarImpressoras))));
    }));
  };
  const editarImpressora = (p: Impressora | null, copia = false) => {
    if (!ps) return;
    const lista = (v: string[]): Opcao[] => v.map((x) => [x, x]);
    const f = formulario([{ k: "name", rotulo: "Nome" }, { k: "ae_title", rotulo: "AE da impressora" }, { k: "host", rotulo: "IP / host" },
      { k: "port", rotulo: "Porta", tipo: "numero", min: 1, max: 65535 },
      { k: "calling_ae", rotulo: "AE de origem" },
      { k: "film_size", rotulo: "Tamanho do filme", tipo: "escolha", opcoes: ps.tamanhos.map((x) => [x, x || tr("o tamanho de cada folha")]) },
      { k: "medium", rotulo: "Mídia", tipo: "escolha", opcoes: lista(ps.midias) },
      { k: "destination", rotulo: "Destino", tipo: "escolha", opcoes: lista(ps.destinos) },
      { k: "magnification", rotulo: "Ampliação", tipo: "escolha", opcoes: lista(ps.ampliacoes) },
      { k: "dpi", rotulo: "Resolução enviada (dpi)", tipo: "numero", min: 72, max: 600 },
      { k: "copies", rotulo: "Cópias", tipo: "numero", min: 1, max: 20 },
      { k: "color", rotulo: "Colorida (Basic Color Print)", tipo: "bool" },
      { k: "compartilhar_clientes", rotulo: "Compartilhar com os clientes", tipo: "bool",
        dica: "Os clientes (Ipê e Ipê Web) imprimem nesta impressora pelo servidor, que manda com o IP e o AE dele. Os clientes não veem o endereço." }],
    p ? { ...p } : { port: 104, film_size: "", medium: "BLUE FILM", destination: "MAGAZINE", magnification: "CUBIC", dpi: 150, copies: 1 });
    if (ps.ae_local) (f.entrada("calling_ae") as HTMLInputElement).placeholder = `(${tr("padrão")}: ${ps.ae_local})`;
    const estado = el("span", { class: "cad-teste", "aria-live": "polite" });
    const bTestar = botao("Testar conexão", () => {
      estado.textContent = tr("Testando…");
      estado.classList.remove("erro", "ok");
      void testarImpressora(f.ler()).then((r) => { estado.textContent = r.mensagem; estado.classList.add(r.ok ? "ok" : "erro"); });
    });
    janelaDeCadastro(tr(p && !copia ? "Editar a impressora DICOM" : "Nova impressora DICOM"), f, [el("div", { class: "imp-barra" }, bTestar, estado)], async (d) => {
      const r = await pedirJson<Resposta>("impressora", { ...d, original: p && !copia ? p.name : "" });
      dizer(r.mensagem);
      await carregarImpressoras();
    });
  };
  const abaImpressoras = el("div", { class: "imp-aba", hidden: "" },
    el("div", { class: "imp-barra" }, botao("Nova impressora DICOM…", () => editarImpressora(null), "primario")),
    el("p", { class: "dica" }, tr("As impressoras DICOM do servidor. Os destinos de impressão, as regras e os modelos de folha continuam no Ipê de mesa (Preferências ▸ Impressão).")),
    el("div", { class: "imp-rolagem" }, tImp.el));

  // ================================================================== automações de IA
  let ia: Ia | null = null;
  let ferramenta = "";
  const valores = new Map<string, ValorIa>();
  const listaIa = el("div", { class: "cad-ia-lista", role: "listbox", "aria-label": tr("Ferramentas") });
  const painelIa = el("div", { class: "cad-ia-painel" });
  const cLer = el("input", { type: "checkbox", id: "cad-ler-antes" });
  const notaIa = el("p", { class: "dica" });
  const bSalvarIa = botao("Salvar", () => void salvarIa(), "primario");
  const mudouIa = () => { bSalvarIa.disabled = false; desenharListaIa(); };
  const valorDe = (c: CampoIa): ValorIa => (valores.has(c.k) ? valores.get(c.k)! : c.valor);
  const desenharListaIa = () => {
    if (!ia) return;
    listaIa.replaceChildren(...ia.ferramentas.map((f) => {
      const auto = !!valorDe(f.campos.find((c) => c.k === f.auto)!);
      const b = el("button", { type: "button", role: "option", "aria-selected": String(f.id === ferramenta), "data-f": f.id, class: auto ? "auto" : "" },
        el("strong", {}, f.nome), el("small", {}, tr(auto ? "automático na chegada" : "só à mão")));
      b.onclick = () => { ferramenta = f.id; desenharListaIa(); desenharPainelIa(); };
      return b;
    }));
  };
  const caixas = (c: CampoIa, opcoes: { k: string | number; nome: string }[], vazio: string): HTMLElement => {
    const marcados = new Set(valorDe(c) as (string | number)[]);
    const fs = el("fieldset", { class: "cad-lista" }, el("legend", {}, c.rotulo));
    if (!opcoes.length) fs.append(el("span", { class: "dica" }, tr(vazio)));
    for (const o of opcoes) {
      const e = el("input", { type: "checkbox" });
      e.checked = marcados.has(o.k);
      e.onchange = () => {
        if (e.checked) marcados.add(o.k); else marcados.delete(o.k);
        valores.set(c.k, opcoes.filter((x) => marcados.has(x.k)).map((x) => x.k));
        mudouIa();
      };
      fs.append(el("label", {}, e, ` ${o.nome}`));
    }
    return fs;
  };
  const desenharPainelIa = () => {
    const f = ia?.ferramentas.find((x) => x.id === ferramenta);
    if (!ia || !f) return;
    const filhos: Node[] = [el("h3", { class: "cad-titulo" }, f.titulo)];
    if (f.explicacao) filhos.push(el("p", { class: "dica" }, f.explicacao));
    for (const c of f.campos) {
      const id = `ia-${c.k}`;
      let linha: HTMLElement;
      if (c.tipo === "bool") {
        const e = el("input", { type: "checkbox", id });
        e.checked = !!valorDe(c);
        e.onchange = () => { valores.set(c.k, e.checked); mudouIa(); };
        linha = el("label", { class: "cad-caixa", for: id }, e, el("span", {}, c.rotulo));
      } else if (c.tipo === "nos") {
        linha = caixas(c, ia.nos.map((n) => ({ k: n.id, nome: n.nome })), "(nenhum nó DICOM ativo cadastrado)");
      } else if (c.tipo === "lista") {
        linha = caixas(c, (c.opcoes || []) as { k: string | number; nome: string }[], "");
        if ((c.opcoes || []).length > 6) linha.classList.add("colunas");
      } else if (c.tipo === "escolha") {
        const e = el("select", { id });
        (c.opcoes || []).forEach((o, i) => e.append(el("option", { value: String(i) }, o.nome)));
        e.value = String(Math.max(0, (c.opcoes || []).findIndex((o) => o.k === valorDe(c))));
        e.onchange = () => { valores.set(c.k, (c.opcoes || [])[Number(e.value)].k as ValorIa); mudouIa(); };
        linha = el("div", { class: "imp-campo" }, el("label", { for: id }, c.rotulo), e);
      } else {
        const numero = c.tipo !== "texto";
        const e = el("input", { id, type: numero ? "number" : "text", autocomplete: "off" });
        if (numero) {
          e.min = String(c.min ?? 0);
          e.max = String(c.max ?? 9999);
          e.step = String(c.tipo === "inteiro" ? 1 : c.passo ?? 0.1);
        }
        if (c.vazio) e.placeholder = c.vazio;
        e.value = String(valorDe(c));
        e.oninput = () => { valores.set(c.k, numero ? Number(e.value || 0) : e.value); mudouIa(); };
        linha = el("div", { class: "imp-campo" }, el("label", { for: id }, c.rotulo), e, ...(c.sufixo ? [el("span", { class: "cad-sufixo" }, c.sufixo)] : []));
      }
      if (c.dica) linha.title = c.dica;
      filhos.push(linha);
    }
    painelIa.replaceChildren(...filhos);
  };
  const carregarIa = async () => {
    ia = await pedirJson<Ia>("ia");
    valores.clear();
    if (!ia.ferramentas.some((f) => f.id === ferramenta)) ferramenta = ia.ferramentas[0]?.id || "";
    cLer.checked = ia.ler_antes;
    notaIa.textContent = ia.nota;
    bSalvarIa.disabled = true;
    desenharListaIa();
    desenharPainelIa();
  };
  cLer.onchange = () => { bSalvarIa.disabled = false; };
  const salvarIa = async () => {
    await tentar(async () => {
      const r = await pedirJson<Resposta>("ia", { valores: { ...Object.fromEntries(valores), "cad.ler_antes": cLer.checked } });
      dizer(r.mensagem);
      await carregarIa();
    });
  };
  const abaIa = el("div", { class: "imp-aba", hidden: "" }, notaIa,
    el("label", { class: "cad-caixa", for: "cad-ler-antes" }, cLer,
      el("span", {}, tr("Ler antes, ver o CAD depois: as marcas de CAD (mamografia e outros CAD SR) começam ocultas em cada exame"))),
    el("div", { class: "cad-ia" }, listaIa, painelIa),
    el("div", { class: "imp-barra" }, bSalvarIa, botao("Desfazer o que não foi salvo", () => void tentar(carregarIa))));

  // ================================================================== registro de acesso
  const tReg = tabela("cad-registro", ["Quando", "Usuário", "Ação", "Detalhe", "Computador"]);
  const rPeriodo = el("select", { "aria-label": tr("Período") });
  const rUsuario = el("select", { "aria-label": tr("Usuário") });
  const rAcao = el("select", { "aria-label": tr("Ação") });
  const rTexto = el("input", { type: "search", placeholder: tr("Texto no detalhe"), "aria-label": tr("Texto no detalhe") });
  const rConta = el("span", { class: "imp-contagem" });
  let registroMontado = false;
  const carregarRegistro = async () => {
    const q = new URLSearchParams({ dias: rPeriodo.value || "7", usuario: rUsuario.value, acao: rAcao.value, texto: rTexto.value.trim() });
    const r = await pedirJson<Registro>(`registro?${q.toString()}`);
    const encher = (s: HTMLSelectElement, todos: string, itens: string[]) => {
      const antes = s.value;
      s.replaceChildren(el("option", { value: "" }, tr(todos)), ...itens.map((x) => el("option", { value: x }, x)));
      s.value = itens.includes(antes) ? antes : "";
    };
    if (!registroMontado) {
      registroMontado = true;
      rPeriodo.replaceChildren(...r.periodos.map((p) => el("option", { value: p.k }, p.nome)));
      rPeriodo.value = "7";
    }
    encher(rUsuario, "Todos os usuários", r.usuarios);
    if (!rAcao.value) encher(rAcao, "Todas as ações", r.acoes);
    rConta.textContent = `${r.linhas.length} ${tr("linhas")}${r.cheio ? ` — ${tr("só as 1000 mais recentes: aperte o filtro")}` : ""}`;
    if (!r.linhas.length) { vazia(tReg.corpo, 5, "Nada no registro com esse filtro."); return; }
    tReg.corpo.replaceChildren(...r.linhas.map((l) => el("tr", {}, el("td", {}, l.quando), el("td", {}, l.usuario),
      el("td", {}, l.acao), el("td", { class: "cad-detalhe", title: l.detalhe }, l.detalhe), el("td", {}, l.maquina))));
  };
  for (const s of [rPeriodo, rUsuario, rAcao]) s.onchange = () => void tentar(carregarRegistro);
  rTexto.onkeydown = (e) => { if (e.key === "Enter") void tentar(carregarRegistro); };
  const abaRegistro = el("div", { class: "imp-aba", hidden: "" },
    el("div", { class: "imp-barra" }, rPeriodo, rUsuario, rAcao, rTexto, botao("Atualizar", () => void tentar(carregarRegistro)), rConta),
    el("div", { class: "imp-rolagem" }, tReg.el));

  // ================================================================== modelos de esquema (0.100.74)
  const abaModelos = el("div", { class: "imp-aba", hidden: "" },
    el("p", { class: "dica" }, tr("Os modelos de esquema desta instalação, para todos os usuários. O que se desenha num modelo aparece em todos os exames; nos modelos do Ipê o desenho original fica guardado.")));
  let modelosMontados = false;
  const carregarModelos = async () => {
    if (modelosMontados) return;
    modelosMontados = true;
    abaModelos.append(el("div", { class: "imp-rolagem" }, gradeDeModelos({ gerir: true })));
  };

  // ================================================================== abas
  const abas: [string, string, HTMLElement, (() => Promise<void>) | null][] = [
    ["usuarios", "Usuários", abaUsuarios, null], ["nos", "Nós DICOM", abaNos, carregarNos],
    ["impressoras", "Impressoras DICOM", abaImpressoras, carregarImpressoras], ["ia", "Automações de IA", abaIa, carregarIa],
    ["modelos", "Modelos de esquema", abaModelos, carregarModelos],
    ["registro", "Registro de acesso", abaRegistro, carregarRegistro]];
  const botoes = new Map<string, HTMLButtonElement>();
  let aba = "usuarios";
  const trocar = (k: string) => {
    aba = k;
    dizer("");
    for (const [id, , painel, carregar] of abas) {
      painel.hidden = id !== k;
      const b = botoes.get(id)!;
      b.setAttribute("aria-selected", String(id === k));
      b.classList.toggle("sel", id === k);
      if (id === k && carregar) void tentar(async () => { await carregar(); if (id === "nos") semRede.hidden = !!ns?.rede; });
    }
  };
  const barra = el("div", { class: "abas gestao-abas", role: "tablist" }, ...abas.map(([id, nome]) => {
    const b = el("button", { type: "button", role: "tab", "data-aba": id, "aria-selected": String(id === aba) }, tr(nome));
    if (id === aba) b.classList.add("sel");
    b.onclick = () => trocar(id);
    botoes.set(id, b);
    return b;
  }));
  raiz.append(barra, nota, ...abas.map(([, , p]) => p));
  (window as unknown as { __ipeCadastros: unknown }).__ipeCadastros = {
    estado: () => ({ aba, usuarios: us.usuarios, nos: ns?.nos || [], identidades: ns?.identidades || [], impressoras: ps?.impressoras || [],
      ferramenta, ferramentas: (ia?.ferramentas || []).map((f) => ({ id: f.id, ligada: f.ligada })), nota: nota.textContent }),
  };
  return raiz;
}
