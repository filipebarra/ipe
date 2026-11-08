// Textos do site. A chave é o português (como no Ipê); en e es ao lado. O idioma vem do servidor depois do
// login (o mesmo do Ipê) e, antes, do navegador.

type Trad = Record<string, [string, string]>;

const T: Trad = {
  "Entrar": ["Sign in", "Entrar"],
  "Usuário": ["User", "Usuario"],
  "Senha": ["Password", "Contraseña"],
  "Usuário ou senha incorretos.": ["Incorrect user or password.", "Usuario o contraseña incorrectos."],
  "Muitas tentativas: espere alguns minutos.": ["Too many attempts: wait a few minutes.", "Demasiados intentos: espere unos minutos."],
  "Não foi possível falar com o servidor.": ["Could not reach the server.", "No se pudo hablar con el servidor."],
  "Sair": ["Sign out", "Salir"],
  "Exames": ["Exams", "Estudios"],
  "Buscar": ["Search", "Buscar"],
  "Nome, ID ou acesso": ["Name, ID or accession", "Nombre, ID o acceso"],
  "De": ["From", "Desde"],
  "Até": ["To", "Hasta"],
  "Modalidade": ["Modality", "Modalidad"],
  "Todas": ["All", "Todas"],
  "Data": ["Date", "Fecha"],
  "Paciente": ["Patient", "Paciente"],
  "ID": ["ID", "ID"],
  "Descrição": ["Description", "Descripción"],
  "Imagens": ["Images", "Imágenes"],
  "Nenhum exame encontrado.": ["No exams found.", "Ningún estudio encontrado."],
  "Carregando…": ["Loading…", "Cargando…"],
  "Voltar à lista": ["Back to the list", "Volver a la lista"],
  "Layout": ["Layout", "Diseño"],
  "Janela": ["Window", "Ventana"],
  "Mover": ["Pan", "Mover"],
  "Zoom": ["Zoom", "Zoom"],
  "Rolar": ["Scroll", "Desplazar"],
  "Inverter": ["Invert", "Invertir"],
  "Cine": ["Cine", "Cine"],
  "Parar": ["Stop", "Parar"],
  "Restaurar": ["Reset", "Restablecer"],
  "Janelas prontas": ["Window presets", "Ventanas predefinidas"],
  "Do arquivo": ["From the file", "Del archivo"],
  "Botão esquerdo:": ["Left button:", "Botón izquierdo:"],
  "Não destinado a uso diagnóstico": ["Not for diagnostic use", "No destinado a uso diagnóstico"],
  "Clique numa série para mostrar no quadro ativo.": ["Click a series to show it in the active viewport.", "Haga clic en una serie para mostrarla en el cuadro activo."],
  "Esta série não tem imagens que o navegador mostre.": ["This series has no images the browser can show.", "Esta serie no tiene imágenes que el navegador muestre."],
  "Sessão encerrada: entre de novo.": ["Session ended: sign in again.", "Sesión cerrada: entre de nuevo."],
  "Sem permissão para ver este exame.": ["No permission to view this exam.", "Sin permiso para ver este estudio."],
  "Este navegador não tem WebGL 2: o visualizador não funciona nele. Use o Chrome ou o Edge atuais.": [
    "This browser has no WebGL 2: the viewer does not work in it. Use a current Chrome or Edge.",
    "Este navegador no tiene WebGL 2: el visualizador no funciona en él. Use Chrome o Edge actuales."],
  "quadros/s": ["frames/s", "cuadros/s"],
  "Im": ["Im", "Im"],
  "Se": ["Se", "Se"],
  "Exame": ["Exam", "Estudio"],
  "Ipê Web": ["Ipê Web", "Ipê Web"],
};

let lang: "pt" | "en" | "es" = (() => {
  const n = (navigator.language || "en").toLowerCase();
  return n.startsWith("pt") ? "pt" : n.startsWith("es") ? "es" : "en";
})();

export function setLang(l: string): void {
  lang = l === "pt" ? "pt" : l === "es" ? "es" : "en";
  document.documentElement.lang = lang === "pt" ? "pt-BR" : lang;
}

export function getLang(): string {
  return lang;
}

export function tr(s: string): string {
  if (lang === "pt") return s;
  const t = T[s];
  if (!t) return s;
  return lang === "en" ? t[0] : t[1];
}

export const TEXTOS = T;
