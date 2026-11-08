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
  "Linhas de referência": ["Reference lines", "Líneas de referencia"],
  "MPR": ["MPR", "MPR"],
  "Axial, coronal, sagital e o MIP girando da série do quadro ativo, com as linhas de referência": ["Axial, coronal, sagittal and the rotating MIP of the active viewport's series, with reference lines", "Axial, coronal, sagital y el MIP girando de la serie del cuadro activo, con las líneas de referencia"],
  "Espessura (quadros A, C, S)": ["Thickness (A, C, S viewports)", "Espesor (cuadros A, C, S)"],
  "Corte fino": ["Thin slice", "Corte fino"],
  "Projeção da espessura": ["Thick-slab projection", "Proyección del espesor"],
  "Média": ["Average", "Media"],
  "Dois cliques no quadro ativo definem a reta; o oblíquo vai para o outro quadro de volume": ["Two clicks in the active viewport define the line; the oblique goes to the other volume viewport", "Dos clics en el cuadro activo definen la recta; el oblicuo va al otro cuadro de volumen"],
  "Oblíquo": ["Oblique", "Oblicuo"],
  "Gira o MIP (a roda do mouse também gira)": ["Rotates the MIP (the mouse wheel also rotates it)", "Gira el MIP (la rueda del mouse también lo gira)"],
  "Girar MIP": ["Rotate MIP", "Girar MIP"],
  "Parar o giro": ["Stop rotating", "Parar el giro"],
  "a série tem poucos cortes para o volume": ["the series has too few slices for a volume", "la serie tiene pocos cortes para el volumen"],
  "série de vários quadros num arquivo (sem volume por enquanto)": ["multi-frame series in one file (no volume for now)", "serie de varios cuadros en un archivo (sin volumen por ahora)"],
  "a série não tem a posição dos cortes": ["the series has no slice positions", "la serie no tiene la posición de los cortes"],
  "os cortes não têm a mesma orientação": ["the slices do not share the same orientation", "los cortes no tienen la misma orientación"],
  "os cortes não têm o mesmo tamanho": ["the slices do not have the same size", "los cortes no tienen el mismo tamaño"],
  "Sagital": ["Sagittal", "Sagital"],
  "Coronal": ["Coronal", "Coronal"],
  "Axial": ["Axial", "Axial"],
  "Original": ["Original", "Original"],
  "MIP girando (clique leva os cortes ao ponto mais claro)": ["Rotating MIP (a click takes the slices to the brightest point)", "MIP girando (un clic lleva los cortes al punto más claro)"],
  "Os cortes como foram adquiridos": ["The slices as acquired", "Los cortes como fueron adquiridos"],
  "Sem volume:": ["No volume:", "Sin volumen:"],
  "Série grande demais para o volume no navegador (mais de 1,5 GB).": ["Series too large for a volume in the browser (over 1.5 GB).", "Serie demasiado grande para el volumen en el navegador (más de 1,5 GB)."],
  "A espessura vale nos quadros de volume (A, C, S).": ["Thickness applies to volume viewports (A, C, S).", "El espesor vale en los cuadros de volumen (A, C, S)."],
  "O oblíquo por dois pontos parte de um quadro de volume (A, C, S).": ["The two-point oblique starts from a volume viewport (A, C, S).", "El oblicuo por dos puntos parte de un cuadro de volumen (A, C, S)."],
  "Oblíquo: clique em dois pontos da reta no quadro ativo.": ["Oblique: click two points of the line in the active viewport.", "Oblicuo: haga clic en dos puntos de la recta en el cuadro activo."],
  "MIP": ["MIP", "MIP"],
  "Régua": ["Ruler", "Regla"],
  "Ângulo": ["Angle", "Ángulo"],
  "Ângulo de Cobb": ["Cobb angle", "Ángulo de Cobb"],
  "ROI elíptica": ["Elliptical ROI", "ROI elíptica"],
  "ROI retangular": ["Rectangular ROI", "ROI rectangular"],
  "ROI livre": ["Freehand ROI", "ROI libre"],
  "Valor do pixel": ["Pixel value", "Valor del píxel"],
  "Seta": ["Arrow", "Flecha"],
  "Calibração": ["Calibration", "Calibración"],
  "Calibração:": ["Calibration:", "Calibración:"],
  "(só esta imagem)": ["(this image only)", "(solo esta imagen)"],
  "Mín": ["Min", "Mín"],
  "Máx": ["Max", "Máx"],
  "Área": ["Area", "Área"],
  "Texto da seta:": ["Arrow text:", "Texto de la flecha:"],
  "Comprimento real desta linha (mm):": ["Real length of this line (mm):", "Longitud real de esta línea (mm):"],
  "Apagar medida": ["Delete measurement", "Borrar medida"],
  "Apaga a medida selecionada (clique nela antes)": ["Deletes the selected measurement (click it first)", "Borra la medida seleccionada (haga clic en ella antes)"],
  "Clique numa medida para selecioná-la antes de apagar.": ["Click a measurement to select it before deleting.", "Haga clic en una medida para seleccionarla antes de borrar."],
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
