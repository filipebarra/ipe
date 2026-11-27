# Historial de versiones de Ipê

*El programa se llamó **DicomViewer** hasta la versión 0.99.10. [Volver al README](README.es.md).
El historial completo, con todas las versiones, está en portugués: [CHANGELOG.md](CHANGELOG.md).*

## 0.100.131 — La búsqueda por lote con el disco externo activo lista los nodos del servidor
Reporte (27/11/2026): con una base local activa, la página «3. De dónde» de la búsqueda por lote quedaba vacía y no se podía elegir de qué PACS descargar.
- **La lista de nodos del lote ahora incluye los que comparte el servidor** («… (por el servidor)») cuando la ubicación activa es el disco externo o la base de este equipo. Marque, ordene y ejecute como antes: la búsqueda y la descarga pasan por el servidor y el estudio entra en la ubicación activa.
- Prueba nueva: la lista del lote trae los nodos del servidor con la base local activa.

## 0.100.130 — Los nodos del servidor aparecen con el disco externo activo
Reporte (27/11/2026): solo se podía descargar del servidor con el «Servidor central» activo; con el disco externo activo los nodos DICOM no aparecían.
- **Los nodos que comparte el servidor ahora aparecen en la búsqueda, el PACS y la búsqueda por lote también con una base local activa** (disco externo o de este equipo). El estudio descargado por ellos entra en la ubicación activa y el servidor borra su copia cuando todo llegó.
- La pantalla de configuración de nodos sigue mostrando solo los de este equipo.
- Prueba nueva: con la base local activa la lista trae los nodos del servidor (y los quita sin conexión).

## 0.100.129 — Densidad ósea oportunista en TC de abdomen (L1 y L1–L4)
Pedido (27/11/2026): estimar la densidad ósea en TC convencional, sin doble energía, para comparar con la DMO de columna y fémur.
- **Nuevo hallazgo "Densidad ósea (TC)"**, junto a la composición corporal (misma serie de TC de abdomen sin contraste, mismo TotalSegmentator): el HU del **hueso trabecular de L1** y la media de **L1 a L4** (ponderada por el volumen), con mediana, desviación estándar y volumen de la ROI de cada nivel.
- **ROI dentro del cuerpo vertebral**: margen de 5 mm (quita la cortical, los pedículos y el plexo venoso posterior) y solo el tercio central de la vértebra (lejos de los platillos y los discos). La ROI queda en la serie "Composición corporal · TotalSegmentator".
- **Resultado provisional de L1** con los cortes de Pickhardt et al. (Ann Intern Med 2013): ≤ 110 HU osteoporosis probable, ≤ 135 baja densidad, 135–160 zona gris, > 160 sin signos. Los tres cortes y el margen se editan en Configuración ▸ CAD/IA ▸ Composición corporal.
- **L1–L4 sin corte de la literatura**: Ipê muestra el HU y solo compara si escribe un corte del servicio (0 = solo el número). Para hallar el suyo, ejecute el lote en estudios con DMO y compare en Excel (Búsqueda por lote ▸ resultados de las IA: las columnas nuevas salen solas).
- Con contraste o kVp distinto de 120, mide pero **no clasifica**; hueso muy denso (mediana > 300 HU) avisa. Texto de referencia, nunca diagnóstico.
- Pruebas nuevas: ROI solo en trabecular, clasificación, cortes editables, contraste, sin L1, serie no axial y la frase del informe.

## 0.100.128 — Descarga del PACS directo al cliente con el disco externo activo
Reporte (26/11/2026): en un cliente con la base en el disco externo, "descargar directo al cliente" desde el PACS y "descargar a mi PC" en la búsqueda por lote dejaban el estudio solo en el servidor (log: `'Repository' object has no attribute 'client'`).
- **El estudio va a la base activa** (disco externo o de este equipo) cuando el nodo es del servidor central: el cliente lee del servidor, guarda en la base activa y solo entonces avisa al servidor, que borra su copia (mismas reglas de seguridad de antes).
- El programa ahora **conserva la conexión con el servidor central** aunque haya otra ubicación activa; sin conexión, el error dice el motivo («no hay conexión con el servidor»).
- Consejo: no cambie de ubicación mientras hay descargas en curso.
- Pruebas nuevas: PACS por el servidor con el disco activo (llega completo, el servidor borra) y sin conexión con el servidor.

## 0.100.127 — Borrar varios estudios ya no congela la pantalla
Informe (26/11/2026): con la base en un HD externo, borrar varios estudios dejaba el programa casi congelado.
- **Borrar corre en un hilo aparte**, con barra de avance ("Borrando los estudios… 12 de 40") y **Cancelar** (lo ya borrado queda borrado). La pantalla sigue respondiendo; la lista se actualiza al final y los errores (estudio con candado, sin permiso) aparecen juntos.
- **Menos idas al disco**: cada archivo se comprueba por la ruta (sin `resolve()` ni `exists()` por archivo) y se borra directo; en un HD externo cada ida al disco cuesta tiempo.
- **Los pacientes sin estudio se quitan una sola vez, al final**, y no tras cada estudio (antes, cada estudio recorría la tabla de pacientes y escribía en el HD).
- Pruebas nuevas: borrar en segundo plano actualiza la lista; nunca borra un archivo fuera del Storage; la limpieza de pacientes al final del lote.

## 0.100.126 — Hierro hepático: fórmulas de Wood y de Hankins, elegidas por el campo de la RM
- **Nuevo**: el hierro (LIC) de la RM de hígado se calcula con **las dos calibraciones**, y las dos aparecen en el panel de hallazgos, en el resumen en imagen (OT), en la tabla de hígados medidos y en el CSV/Excel: **Wood 2005** (`0,0254 · R2* + 0,202`, a 1,5 T; a 3 T el R2* se divide antes por 2,05, como ya era) y **Hankins 2009** (`0,02802 · R2* − 0,45485`, sobre el R2* del equipo, nunca por debajo de cero).
- **El campo se lee del DICOM** (`MagneticFieldStrength`) y se muestra junto al hierro. El LIC principal y la clasificación sugerida usan, por defecto, **Wood a 1,5 T y Hankins a 3 T**; un campo que no es 1,5 ni 3 T sigue sin estimación.
- Configuración ▸ CAD/IA ▸ *Grasa, hierro y rigidez hepáticos (RM)* ▸ **Fórmula del hierro (LIC)**: 0 = según el campo (por defecto), 1 = siempre Wood, 2 = siempre Hankins. La elección solo cambia cuál de las dos es la principal; las dos se siguen calculando.
- CSV/Excel de hígados medidos: columnas nuevas `lic_formula`, `lic_wood_mgFe_g`, `lic_hankins_mgFe_g` y `campo_T`.
- **Atención**: los estudios a 3 T que antes salían por Wood con la conversión de Alam pasan a salir por Hankins sobre el R2* bruto. En 70 estudios comparados con los informes del servicio, esto redujo el sesgo a 3 T de −0,56 a −0,07 mg Fe/g. La conversión de campo es una convención; los informes del servicio se comportan como Hankins sin conversión.
- Pruebas nuevas: fórmula por campo y por elección, los dos valores en el resultado y el piso en cero.

## 0.100.125 — La guía (F1) en portugués, inglés y español, con todo lo que el programa hace hoy
- **Nuevo**: la guía del usuario existe ahora en **tres idiomas** — `Ipe-guia-do-usuario.pdf` (portugués), `Ipe-user-guide.pdf` (inglés) e `Ipe-guia-del-usuario.pdf` (español) —, cada una con su texto fuente (`tools/guia/guia.md`, `guia.en.md`, `guia.es.md`), sus palabras fijas (portada, pie, avisos) y las mismas figuras. Las tres van dentro del programa y en `docs/`.
- **F1 y Ayuda ▸ Guía del usuario abren la guía en el idioma del programa**; si el idioma elegido no tiene guía, se abre la de portugués. El enlace del pie del sitio también apunta al PDF del idioma de la página.
- **Guía revisada**: entró lo que faltaba — el panel de visión general del comienzo de la guía, la sección **Qué graba cada IA en el estudio** (SEG, tablas e imágenes de verificación, serie con overlay coloreado, destinos globales y por IA), el lote desde una planilla y la exportación de los resultados de las IA a Excel, el enlace del estudio en Ipê Web, el PACS directo al cliente, "olvidé la contraseña", el aviso de que las IA graban en la ubicación en uso, entre otras.
- Prueba nueva: los tres textos de la guía tienen los mismos capítulos, secciones, tablas y figuras, y F1 elige el PDF por el idioma.

## 0.100.124 — Qué guardan y envían las IA: SEG, tablas y serie con overlay en color
- **Nuevo** (su PACS no muestra SEG): en Configuración ▸ CAD/IA, el grupo **Qué guardan y envían las IA (todas las IA)** tiene tres casillas — **series SEG**, **tablas e imágenes de verificación** y **serie con overlay en color** — y una lista de **destinos que valen para todas las IA** (se suman a los de cada herramienta). Las casillas deciden qué va a los destinos; la SEG y las tablas siempre quedan en el estudio de Ipê (el CAD/overlay y las medidas dependen de ellas).
- **Serie con overlay en color**: el estudio con las máscaras pintadas (relleno translúcido y contorno), **una imagen por corte, en la posición del corte original**, que cualquier PACS recorre. Sale de la SEG guardada, así que vale para **toda IA que guarde SEG** (abdomen, columna, ganglios, enfisema, aorta, nódulos, próstata…). Queda en el estudio (serie `… · overlay colorido · Ipê`) y se envía junto. Viene **desactivada** por defecto (ocupa espacio: una imagen en color por corte); SEG y tablas vienen activadas.
- **Por IA**: en cada herramienta (abdomen, columna, ganglios, hígado, mama, dinámica…) el cuadro **Qué guarda y envía esta IA** permite elegir SEG, tablas y overlay en color como *Como en todas las IA / Sí / No* y si los destinos son *los de todas las IA y los de esta herramienta* o *solo los de esta herramienta*. La elección de la IA reemplaza la global.

## 0.100.123 — Exportar en lote los resultados de las IA a Excel
- **Nuevo**: clic derecho en los estudios ▸ **Exportar resultados de las IA (Excel)…**. Reúne en un .xlsx lo que las IA **ya guardaron** en los estudios elegidos (no se ejecuta nada): una hoja *Estudios* (uno por fila, con qué IA tienen resultado) y una hoja por IA, con los números de cada hallazgo (los corregidos por el médico reemplazan a los de la IA) y el estado de la revisión; mamografía añade densidad y calcificaciones vasculares. Puede anonimizar (Caso 001, 002…, sin nombre, ID, accession ni descripción). Para ejecutar las IA y exportar desde una hoja de pacientes, siga usando el lote.

## 0.100.122 — Las IA guardan en el local en uso (disco externo); instalador de PI-CAI en Windows
- **Corregido (importante con disco externo como base)**: las series generadas por las IA (alineación de la
  dinámica, elastografía, implantes, segmentaciones, niveles de la columna, cefalometría, ganglios…) se guardaban en
  la carpeta de archivos **del equipo**, incluso con la base en el disco externo, y la base del disco guardaba la
  ruta de esa carpeta. En otro equipo (o sin esa carpeta) aparecían la miniatura y los hallazgos, pero la imagen daba
  *No se pudo leer esta imagen* y no se exportaba. Ahora las IA guardan en la carpeta de archivos del **local en
  uso**, junto con la base, y acompañan el cambio de local. La retención/papelera y la ventana **Comprobar y
  reconstruir la base** también usan el local en uso.
  - Las series **ya guardadas** antes de la corrección siguen apuntando al equipo donde se hicieron (abren allí);
    para abrirlas en otro equipo, vuelva a ejecutar la IA en el estudio.
- **Corregido**: en Preferencias ▸ CAD/IA, la etiqueta "automático / solo a mano" de Cefalometría, Índices del cráneo
  y Niveles ganglionares aparecía cambiada tras la llegada de la alineación de la dinámica (0.100.119).
- **Instalador de modelos extra (Windows)**: usa una carpeta temporal corta (`C:\ipe_tmp`) solo durante la
  instalación, para que PI-CAI no falle con *No such file or directory* por el límite de 260 caracteres.

## 0.100.121 — Avisos al abrir: IA no instaladas y "No volver a notificarme"
- **Nuevo aviso al abrir Ipê**: si este equipo **no tiene las IA instaladas** (la segmentación de órganos o los modelos
  extra: MedSAM2, autoPET, BraTS, FLAMeS, médula), una ventana dice qué falta y ofrece **Instalar la segmentación** /
  **Instalar los modelos extras** o **Después**. Aparece cada vez que se abre el programa, hasta que las IA estén
  instaladas.
- Ese aviso y los de **versión nueva** (de GitHub y del servidor central) ahora tienen la casilla **No volver a
  notificarme**. Marcada, el aviso no vuelve. Para activarlo de nuevo: **Ayuda ▸ Avisar cuando salga una versión
  nueva** y **Ayuda ▸ Avisar cuando falte instalar las IA**.
- Los modelos de investigación (próstata) y la alineación de la dinámica de mama no entran en el aviso: son opcionales.

## 0.100.120 — Limpiar la caché de Ipê
- Nuevo: **Configuración ▸ Base de datos ▸ Limpiar la caché de Ipê…**. La ventana muestra cuánto ocupa cada cosa y
  limpia solo lo que usted marque:
  - **Memoria de imágenes del visor** (las imágenes ya leídas; vuelven al abrir el estudio);
  - **Estudios descargados del servidor** (solo en modo cliente; viene sin marcar): el servidor conserva todo y el
    estudio se descarga de nuevo al abrirlo. Se quedan los estudios **abiertos**, los **protegidos (candado)** y los
    que el servidor **no tiene completos** — antes de quitar cada uno, el programa lo confirma con el servidor;
  - **Carpetas temporales olvidadas** (restos de las IA y de los informes de cuando el programa se cerró a medias,
    sin tocar hace más de 6 horas);
  - **Actualizaciones ya descargadas** (instaladores de versiones antiguas).
- Nunca se tocan: la base, los estudios de este equipo, la papelera, la configuración y los modelos de IA.
- Corregido: al vaciar la memoria de imágenes, la cuenta de memoria usada no volvía a cero.

## 0.100.119 — Dinámica de mama: alinear las fases (corrección de movimiento)
- Nueva IA **Dinámica de mama: alinear las fases**: alinea entre sí las fases de la RM de mama dinámica **en 3D**
  (registro conjunto y deformable de elastix, el método del antiguo proyecto *dce-align*, ahora con todos los cortes
  juntos y no uno a uno) y **guarda en el propio estudio** las fases alineadas ("Dinámica alineada 1…N · Ipê") y las
  **sustracciones** post − pre. El original no se toca y las imágenes nuevas dicen en el encabezado que son
  alineadas por IA, no adquisición.
- **Solo guarda cuando vale la pena**: el registro mide cuánto del residuo |post − pre| logró quitar (el realce por
  contraste se queda; solo sale el desalineamiento). Por debajo del límite (12 % por defecto) el estudio se deja
  como está. Pedida a mano, guarda siempre.
- Se ejecuta **en el servidor cuando llega el estudio** (se activa en Preferencias ▸ CAD/IA ▸ *Dinámica de mama:
  alinear las fases*; viene desactivada) y **a mano** desde el menú IA de la base y de Ipê Web. De una en una;
  rehacer reemplaza la anterior.
- Preferencias: límite de movimiento, guardar o no las sustracciones, malla de la deformación (32 mm) y nodos de
  destino.
- **Instalación aparte**: Configuración ▸ CAD/IA ▸ *Instalar la alineación de la dinámica de mama (elastix,
  ~1,5 GB)…*. elastix vive en un entorno propio; el resto no cambia.
- Límites de esta versión: probada en estudios sintéticos (el movimiento fue simulado), **aún no en estudios
  reales** — compare siempre con el original; la RM en archivos multiframe (Enhanced) aún no está soportada; usa de
  1 a 2 GB de memoria durante el registro; las series alineadas quedan aparte (la ventana Dinámica aún no las usa
  sola).

## 0.100.118 — Revisión del inglés (y del español) en todas las pantallas
- Revisión de **todas las ventanas, menús, mensajes y avisos de las IA** con el programa en inglés: unos 270 textos
  que todavía salían en portugués fueron traducidos (mensajes de finalización y de error de las IA, frases de
  PI-RADS, lote desde planilla, errores del servidor, impresión, SLA, protocolos de visualización, licencias de los
  modelos de investigación).
- **Frases a medias**: un texto de varias líneas o armado por partes salía con el comienzo traducido y el resto en
  portugués. El traductor ahora solo acepta la frase entera.
- Base de datos: el panel de ubicaciones, las columnas Origen, Base, IA, Prioridad, Estado, Subespecialidad y Plazo,
  "Paciente oculto", "Sin comentarios", el título de la ventana y el nombre del usuario siguen el idioma de la
  pantalla.
- Visor: ayudas de los botones de herramienta, nombres de las etapas de los protocolos, presets de ventana, reglas
  de la barra de herramientas, rótulos del 3D y de la fusión.
- Ipê Web: clasificación sugerida de PI-RADS/BI-RADS, SUV y otros rótulos.
- Quedan en portugués a propósito: los **nombres de las series DICOM creadas por las IA** (el programa las reconoce
  por el nombre), los encabezados de la planilla del lote, las listas de palabras clave y los modelos de informe.
- Corregido: **Perfiles ▸ Capturar de este equipo…** daba error al hacer clic.

## 0.100.117 — Conferir y reconstruir la base
- **Configuración ▸ Base de datos ▸ Conferir y reconstruir la base…** (administrador), como el *Rebuild Database*
  de OsiriX/Horos — sin perder lo que solo existe en Ipê (comentarios, listas, medidas, imágenes clave, informes,
  IA):
  - **Conferir** (no cambia nada): imágenes cuyo archivo desapareció (del Storage y referenciadas), archivos del
    Storage fuera de la base, series y estudios vacíos, pacientes sin estudio, series sin miniatura, carpetas
    vacías; el informe se puede guardar.
  - **Reconstrucción parcial**: indexa lo que está fuera, quita de la base lo que desapareció del Storage (los
    referenciados solo si se marca — un disco externo desconectado vuelve), limpia los vacíos, rehace miniaturas.
  - **Reconstrucción completa**: relee la cabecera de todos los archivos y actualiza el índice; antes guarda una
    copia del índice (Backups/indice-….json.gz); se puede parar y continuar después.
- Línea de comandos (servidor): `ipe-cli banco conferir | parcial [--referenciados] | completa | continuar |
  restaurar-indice <copia>`.
- La ventana del **lote desde planilla** es una ventana normal: se minimiza en Ubuntu.

## 0.100.116 — Pacientes sin estudios en la base
- Una serie nueva de un estudio existente (resultado de IA, SR, captura) con el nombre del paciente escrito distinto
  o sin la fecha de nacimiento creaba un **paciente sin estudios** — el pie llegaba a mostrar "168 pacientes, 14
  estudios". Ahora el paciente solo se crea con un estudio nuevo.
- Al abrir Ipê (y en cada estudio borrado), los pacientes que quedaron sin ningún estudio salen de la base. No se
  pierde nada: el paciente solo existe por sus estudios.
- Recordatorio: borrar un estudio nunca borra los archivos solo **referenciados** (importados sin copiar al Storage).

## 0.100.115 — Ipê Web: la tira de series acompaña el estudio
- Lo que se graba en el estudio aparece en la tira de series **sin cerrar y abrir el estudio**: el esquema grabado en
  el estudio entra en el acto (y grabar de nuevo cambia la miniatura); lo demás (anexos, IA, informe, lo que llegue
  del PACS o del Ipê de escritorio) entra en hasta 20 s, o en el acto al volver a la pestaña. Lo que se borró del
  estudio sale de la tira.
- Lote desde planilla: **solo descargar**. Modelo listo *Só baixar* y la opción *Estudio descargado: aplicar las
  reglas de llegada* (desmarcada, el estudio descargado solo entra en la base — ninguna IA corre en él, ni la
  automática de la llegada).

## 0.100.114 — Listas de casos con las columnas de la base
- Con una lista de casos abierta, la tabla queda como la de la base: las mismas columnas, en el mismo orden y ancho.
  Delante solo el **Nº**, estrecho; **Caso (lista)** solo aparece cuando la lista tiene nombre de caso. Antes las
  dos, anchas, empujaban Series, Imágenes y las demás fuera de la pantalla.
- *La historia de Ipê* ganó la línea del tiempo: la primera línea de código se escribió el 18/09/2026.

## 0.100.113 — Olvidé el usuario o la contraseña
- Ventana de inicio: **Olvidé el usuario o la contraseña…**. En el Ipê de **uso único** ("Solo yo uso esta
  computadora"), muestra la lista de usuarios y guarda una contraseña nueva (reactiva al usuario si estaba
  desactivado); queda en la auditoría, con la cuenta de Windows. Con varias personas o en el servidor, explica el
  camino (un administrador en Usuarios); en el cliente, la contraseña es del servidor central.
- Línea de comandos: `ipe-cli redefinir-senha` lista los usuarios de esta computadora e `ipe-cli redefinir-senha
  <usuario>` guarda una contraseña nueva — para cuando nadie recuerda la contraseña de administrador (cualquier modo,
  menos cliente).

## 0.100.112 — Ipê Web: las marcas de las IAs como en el Ipê de escritorio
- Las **líneas de las medidas** de la cefalometría del cavum y de los índices del cráneo (área mínima, paladar,
  espacio aéreo, hioides, lengua; Evans y los demás) aparecen en Ipê Web, en cualquier plano que contenga la línea —
  como en el Ipê de escritorio. Antes solo aparecía la imagen de conferencia.
- La **segmentación de la IA** (SEG) aparece al abrir el estudio en Ipê Web (la más reciente), como en el Ipê de
  escritorio; antes solo aparecía cuando la IA corría en la misma sesión. No aparece si el CAD/IA o las SEG están
  ocultos; las demás están en el botón de segmentación.
- El **Enlace del estudio** de Ipê Web pasó al botón de enviar (un menú con *Enviar a un destino DICOM…* y *Enlace
  del estudio (sin contraseña)…*): el botón extra empujaba otros al » ya en pantallas de 1920 px.

## 0.100.111 — Lote en el cliente: el estudio viene en cuanto llega al servidor
- Lote desde planilla en el Ipê cliente, con **Traer los estudios también a esta computadora**: cada estudio empieza
  a venir a la base de esta computadora **en cuanto llega del PACS al servidor**, sin esperar las IAs, envíos e
  impresión de la línea (antes solo venía al final de cada línea). Al final de la línea viene de nuevo solo lo que
  falte (las series de las IAs).
- El borrado del servidor solo vale después de esa copia final, y el servidor confiere el número de imágenes del
  cliente: si falta alguna, pide la copia de nuevo en vez de borrar.
- El diario del lote muestra cada estudio que llegó a esta computadora (o que no llegó entero). Cerrar la ventana
  con el lote trayendo estudios pide confirmación: los estudios solo vienen con la ventana abierta.

## 0.100.110 — PACS: descargar directo al cliente
- Ipê cliente, ventana **PACS**: botón y clic derecho **Descargar directo al cliente**. El nodo envía al servidor
  central, el servidor pasa el estudio a la base de esta computadora y **borra su copia cuando el estudio llega entero
  aquí** (hasta 3 intentos para lo que falte). Lo que ya estaba en el servidor antes sigue allí. El servidor no ejecuta
  las reglas de llegada en el estudio de paso; las de esta computadora se ejecutan cuando llega. Queda en el registro
  de acceso (`transito_apagado`).

## 0.100.109 — Enlace del estudio también desde Ipê Web
- Botón **Enlace del estudio (sin contraseña)** en la barra del visor de Ipê Web (quien puede exportar): para quién,
  qué más puede (IA, enviar, adjuntar), validez; **Crear y copiar**; los enlaces del estudio con **Revocar**. No
  aparece en una sesión abierta por enlace (un enlace no crea otro).

## 0.100.108 — Enlace del estudio (Ipê Web), sin contraseña
- Clic derecho en el estudio ▸ **Crear enlace del estudio (Ipê Web)…**: un enlace que abre **solo ese estudio** en
  Ipê Web, directo en el visor, **sin contraseña** — sin lista, sin base, sin informe. Al crearlo: para quién, qué más
  puede (**ejecutar y revisar IA**, **enviar al PACS**, **adjuntar PDF e imágenes**) y la validez (1, 3, 7 o 30 días).
  La ventana lista los enlaces del estudio (usos, validez) y los **revoca** — quien lo tenga abierto pierde el acceso
  al instante.
- Seguridad: token aleatorio por enlace (el servidor guarda solo el hash), después del "#" y quitado de la barra de
  direcciones; el servidor solo deja pasar las rutas permitidas y los UID de ese estudio; los intentos erróneos por IP
  están limitados; creación, uso, rechazo y revocación quedan en la auditoría. Crear un enlace requiere el permiso de
  exportar.

## 0.100.107 — Lote en el Ipê cliente: traer a esta computadora y borrar del servidor
- En el paso **Qué hacer** del lote (Ipê cliente), con **Traer los estudios también a esta computadora** marcado, la
  opción de borrar dice lo que hace: **borrar del servidor los estudios que el lote descargó del PACS, después de que
  lleguen completos a esta computadora**. El cliente solo avisa al servidor cuando el estudio llegó completo (reintenta
  lo que faltó, hasta 3 veces); lo que ya estaba en el servidor antes del lote nunca se borra.

## 0.100.106 — Mamografía en Ipê Web: densidad, calcificaciones y quitar la silicona a mano
- En la pestaña **IA** del Ipê Web (y clic derecho ▸ IA en la base), la mamografía muestra **Densidad mamaria
  (BI-RADS)**, **Calcificaciones vasculares de la mama** e **Implante de silicona: quitar la silicona**. Se ejecutan en
  todo el estudio, en la cola del servidor, sin el paquete de segmentación. "Quitar la silicona" funciona aunque la
  corrección a la llegada esté apagada: sirve para los estudios antiguos.

## 0.100.105 — Ipê Web: el estudio abre mientras llega; instalador con "windows" en el nombre
- **Enlace de apertura**: el estudio que viene del PACS abre en cuanto llegan las primeras imágenes; la tira recibe
  las series nuevas y la serie que creció se recarga en el cuadro, en la misma imagen, con un aviso de cuánto llegó.
- El instalador de Windows pasa a llamarse **`Ipe-<versión>-windows-installer.exe`** (como los paquetes de Linux y
  macOS). La actualización automática reconoce el nombre nuevo y el antiguo.

## 0.100.104 — Ipê Web: mantener la sesión por 1 día
- **"Mantener la sesión en esta computadora (1 día)"** en el login del Ipê Web: el inicio de sesión vale en todas las
  pestañas del navegador y en los enlaces de apertura (`#/abrir?…`), aunque esté inactivo, por 1 día. "Salir" lo
  olvida en todas las pestañas. Sin marcar, queda como antes (solo en la pestaña, 12 h inactivo). El servidor lo
  registra en la auditoría; el administrador puede desactivarlo (`web.manter_conectado`).

## 0.100.103 — Ipê Web: abrir por llamada externa
- **Dirección de apertura**: `…/web/#/abrir?acesso=12345` o `…/web/#/abrir?id=98765&data=20261123&mod=MR` (también
  `uid=`). Ipê Web busca en el servidor; si no lo encuentra, en los nodos del PACS que el servidor comparte, **lo
  descarga y lo abre** cuando llega, con el progreso en pantalla. Más de un estudio: una lista para elegir. El login
  sigue siendo obligatorio (sin sesión pide la contraseña y vuelve a la dirección). Fecha en AAAAMMDD, AAAA-MM-DD o
  DD/MM/AAAA.

## 0.100.102 — Resumen de la RM del hígado como imagen
- La IA de hígado (grasa, hierro, rigidez) graba en el estudio el **resumen como imagen (OT)**, como el de la
  densidad mamaria: serie "Fígado na RM: resumo (Ipê)" con PDFF y grado, doble eco, R2*, hierro estimado (LIC),
  rigidez y rango, el resultado de cada uno y quién lo revisó. Se rehace en cada revisión en Hallazgos de IA
  (escritorio y Web): muestra los números corregidos y pasa de "sin revisión" a "revisado". También va a los destinos
  configurados.

## 0.100.101 — IA desde la base, cola de IA, tabla del hígado
- **Clic derecho en el estudio ▸ IA**: las IA del estudio, como en el botón IA del visor, cada una con sus opciones
  (serie sugerida, rehacer, otra serie); las que la regla dejó fuera en *Otras IA*. Varios estudios: la IA entra en
  la cola en todos.
- **Cola de IA**: pedir una IA con otra ejecutándose en esta computadora ya no se bloquea — entra en la cola y
  empieza sola (aparece en Tareas de IA, donde se puede quitar).
- **Informes ▸ Hígado en la RM (esteatosis, hierro, rigidez): medidas y confirmaciones…**: la tabla de todos los
  estudios con la IA de hígado, como la de la densidad mamaria, con filtros y CSV.
- **Columna "En esta computadora"** en el Ipê cliente: el estudio del servidor también está aquí, completo o parcial.
- **Lote desde planilla**: el estudio que ya está en el Ipê pasa por las reglas de llegada (IA automática, ruteo,
  impresión), como un estudio descargado (opción marcada de fábrica en el paso "Qué hacer").
- Notas de la versión: macOS dejó de ser "experimental".

## 0.100.100 — Ipê cliente: IA en el servidor o en esta computadora
- **Preferencias ▸ CAD/IA ▸ En el Ipê cliente, ejecutar las IA**: **en el servidor central** (predeterminado) — la
  IA pedida en el visor va a la cola del servidor y el resultado llega al estudio abierto — o **en esta
  computadora**, y entonces las series generadas y los hallazgos **suben solos al servidor** (antes, las series
  quedaban solo en el caché de esta computadora).
- Nuevo permiso de perfil **Ejecutar las IA en esta computadora** (de fábrica: administrador y médico). Sin él, o sin
  el paquete de IA instalado aquí, la IA va al servidor, con un aviso.
- **Lote en el cliente**: con "en esta computadora", el servidor busca y descarga, pide las IA a esta computadora,
  recoge el resultado y sigue con el envío, la impresión y la exportación.

## 0.100.99 — lote: qué buscar y en qué orden
- **Lote desde hoja de cálculo ▸ Encontrar el estudio**: usted elige **por qué buscar y en qué orden** — Study UID,
  n.º de acceso, ID + fecha + modalidad, ID + fecha, ID + modalidad (cualquier fecha), solo ID (cualquier fecha).
  Ipê intenta la primera marcada; si no encuentra, la siguiente. Con "solo ID" o "ID + modalidad", las filas sin
  fecha también se procesan.
- Nueva columna **Ipê: encontrado por** (qué intento lo encontró); en "no encontrado", la observación dice por
  cuáles buscó.
- El modelo de mama busca solo por UID, acceso e ID + fecha + MG.

## 0.100.98 — lote: por qué no lo encontró
- **Lote desde hoja de cálculo**: cuando no encuentra un estudio, la observación ahora dice **por qué**: el error
  del nodo (si la búsqueda falló); los estudios que el nodo devolvió y el filtro quitó (ID, fecha, modalidad); o,
  buscando de nuevo solo por el ID, si el paciente tiene estudios en **otras fechas o modalidades** (con los más
  cercanos) o ninguno en el nodo.
- PACS que no filtra por modalidad en la búsqueda: el lote busca de nuevo sin ella y filtra en Ipê.

## 0.100.97 — lote desde hoja de cálculo
- **Red ▸ Lote desde hoja de cálculo…** (en lugar del lote de mama): para cada fila de una hoja (CSV, XLSX u ODS),
  Ipê encuentra el estudio — por Study UID, n.º de acceso o ID + fecha, con tolerancia de días, modalidad y
  "descripción contiene" —, primero en su base y luego en los nodos marcados, en orden, y hace lo que usted elija:
  ejecutar IA, verificar el protocolo de RM, enviar a nodos (originales, resultados o ambos), **imprimir las series
  de revisión** de las IA, **exportar** (PNG, un PDF por estudio, DICOM) y borrar lo que vino de fuera.
- El tipo de cada columna se adivina por el título y se corrige en la vista previa. Una fila solo con el ID, sin
  fecha, no se procesa.
- Salida: la hoja original con las columnas de Ipê, **una pestaña por IA** con los números, Resumen y LÉAME.
  **Anonimizar** cambia los datos del paciente por "Caso 0001…" y guarda la clave en un archivo aparte.
- **Simular** (solo busca y cuenta), **modelos** guardados (el de mama viene incluido), **franja horaria**
  (ej.: solo de 20 h a 6 h), detener y continuar. El registro no muestra nombres de pacientes.
- **En el Ipê cliente, el lote se ejecuta en el servidor central** (sus nodos compartidos, IA e impresoras): la
  ventana lo acompaña y, al final, descarga la hoja y los archivos exportados. **Traer los estudios también a esta
  computadora** copia cada estudio hecho a la base local (el servidor borra lo que descargó solo después de la copia).

## 0.100.96 — menú de las IA traducido; RM de hígado en el sitio
- **Ipê en inglés o español**: en el menú de las IA, el motivo por el que una IA no vale para el estudio ("el
  estudio no tiene CT", "no encontré en el estudio: Cráneo y encéfalo") aparecía en portugués, a veces mezclado.
  Ahora sale en el idioma elegido.
- **Sitio**: página nueva "RM de hígado: grasa, hierro y rigidez", con un video corto (mapas y máscara del hígado,
  hallazgos de IA y la serie de revisión de la rigidez) en un estudio anonimizado.

## 0.100.95 — correcciones: rigidez hepática y columnas de la base
- **La rigidez hepática no salía**: el cálculo usaba una biblioteca (SciPy) que el programa no instala — en la
  computadora del usuario la elastografía fallaba en silencio y el botón **Hígado** mostraba solo grasa y hierro.
  Ahora usa solo lo que Ipê ya tiene.
- **Columnas de la base**: la columna activada por el usuario (ej.: **Agregado el**) aparecía marcada en el menú,
  pero no en la tabla al abrir el programa — había que desactivarla y activarla otra vez. Ahora aparece al entrar.

## 0.100.94 — rigidez hepática en la elastografía por RM; capturas de pantalla anonimizadas
- **Rigidez hepática automática (elastografía por RM)**: el botón **Hígado** (grasa y hierro) ahora también mide la
  rigidez cuando el estudio tiene elastografía (MR-Touch y similares) — sin red neuronal en la medida, como la ROI a
  mano: el hígado del TotalSegmentator a ≥ 5 mm del borde, dentro del área de confianza del equipo (el damero del
  elastograma enmascarado), sin los vasos grandes (por la magnitud de la propia adquisición). Media ponderada por el
  área (la del informe), mediana, p25–p75, área, cortes, fracción del hígado dentro de la confianza y
  heterogeneidad; con dos adquisiciones, las dos. Rango de referencia (2D, 60 Hz) como texto y clasificación
  sugerida. Serie nueva **"Rigidez hepática: ROI automática"** con el elastograma en color, la ROI y el valor de cada
  corte, para verificar.
- **Anonimización: capturas de pantalla del equipo** (elastograma en color, gráficos — ImageType "SCREEN SAVE",
  Secondary Capture): el equipo graba nombre, edad, nacimiento y fecha en el encabezado de la pantalla y aun así
  dice que no hay texto grabado. En la exportación anonimizada y en el paquete de casos, estas pantallas ahora
  pierden el encabezado y el pie enteros. **Los estudios exportados antes con capturas de pantalla deben exportarse
  de nuevo.**

## 0.100.93 — verificación de protocolos de RM; calcificaciones vasculares con implante
- **Verificación de protocolos de RM** (Red ▸ Verificación de protocolos de RM…): cada RM que llega se compara con el
  protocolo de referencia del estudio y del equipo — series que faltan o sobran, plano, 2D/3D, secuencia, TR, TE, TI,
  ángulo, ETL, NEX, espesor, espacio entre cortes, matriz, FOV, ancho de banda, campo, valores de b y contraste, con
  tolerancias por protocolo. **Crear todas desde el acervo** registra de una vez el protocolo dominante de cada
  estudio × equipo de la base; un estudio bueno también puede ser la referencia. Resultado en la nueva columna
  **Protocolo (RM)** de la base (y ⚠ junto al nombre), en la verificación del estudio (clic derecho ▸ Herramientas) y
  en la pestaña *Estudios verificados*, con CSV.
- **Calcificaciones vasculares en mamas con implante**: el borde de la prótesis todavía contaba como "calcificación" en
  algunas proyecciones (y en las escalas). Ahora la máscara del implante de la mamografía (la misma de "borrar el
  implante") también queda fuera, y la copia con el implante corregido no se mide (se mide la original). Use "Medir de
  nuevo" en los estudios con prótesis ya medidos.
- Traducciones: "mama derecha/izquierda" y "ninguna" en la ventana de calcificaciones; el aviso "Para que el PACS envíe
  aquí…" en Red ▸ Esta computadora.

## 0.100.92 — C-GET con series comprimidas, filtro "Todas" en inglés y traducciones
- **C-GET**: cuando quien pide solo acepta sintaxis sin compresión, Ipê descomprime las series JPEG-LS/JPEG 2000
  al momento en lugar de dejarlas atrás (antes el estudio llegaba sin esas series).
- **Buscar en el PACS, base y listas de casos**: con el programa en inglés o español, la modalidad "Todas" iba
  como "ALL" y no encontraba nada.
- Traducciones que faltaban en la gestión DICOM (cola de envío, estados, reglas con horario y días), la impresión
  (panel de películas, orígenes sin registro, envíos, "cualquiera") y el compositor de películas (ayuda y copias).

## 0.100.91 — calcificaciones vasculares marcadas para el monitor B/N y el PACS
- **Marcas de las calcificaciones vasculares**: en lugar del rojo (gris oscuro en el monitor B/N), un **contorno
  blanco con borde negro** ~1 mm alrededor de lo que halló la red y **flechas numeradas** en las puntas de cada vaso.
  En la ventana, Ipê Web y las imágenes marcadas que van al PACS (Secondary Capture) — confirme de nuevo un estudio
  antiguo para rehacer sus imágenes.

## 0.100.90 — rehacer en todas las IA; las IA en el menú Configuración ▸ CAD/IA
- **Rehacer en el estudio en todas las IA**: órganos, columna, cefalometría, índices del cráneo, niveles
  ganglionares y las del contrato común; densidad y calcificaciones vasculares de la mama ("Rehacer la medida en el
  estudio"). Usa la serie que elige la regla de la IA; también en la lista del botón IA.
- **Configuración ▸ CAD/IA** lista todas las IA (eran seis); cada ítem abre la página de la IA.

## 0.100.89 — rehacer la IA en el estudio
- **Rehacer en el estudio**: el menú de cada IA (Hígado, Composición, Nódulos y las demás) tiene "Rehacer en el
  estudio (serie preferida de la Configuración)…" — antes, con hallazgos en el estudio, solo se podía rehacer en la
  serie abierta. Pregunta si descarta los hallazgos ya revisados.

## 0.100.88 — clasificación sugerida de la grasa y el hierro hepáticos
- **Clasificación sugerida** en la ventana Hallazgos de IA (columna nueva y tabla de las escalas, como en las
  calcificaciones vasculares de la mama): esteatosis por el PDFF (umbral de 5% y grado estimado de Tang 2015) y
  sobrecarga de hierro por el LIC (< 1,8 normal; 3,2–7 leve; 7–15 moderada; > 15 grave). Corregible; la frase del
  informe usa la que valga. También en Ipê Web.

## 0.100.87 — hierro hepático en la RM con el mapa correcto; intercambio agua-grasa
- **Hierro hepático en la RM (importante)**: en RM GE con IDEAL IQ, la serie "WATER: IDEAL IQ (R2\*)" (y "FAT: …")
  se tomaba como el mapa de R2\* — "(R2\*)" es el nombre de la secuencia — y, al venir después del mapa, lo
  reemplazaba: el hierro salía de la señal del agua o de la grasa. Rehaga el hierro de los estudios medidos antes.
  Ahora manda la ImageType.
- **Intercambio agua-grasa**: los vóxeles del hígado por encima de 60% con el resto muy por debajo quedan fuera del
  PDFF, con aviso; con R2\* alto, aviso de que el PDFF es menos confiable.

## 0.100.86 — hallazgos de IA en la exportación; frases armadas traducidas
- **Hallazgos de IA en la exportación**: la exportación DICOM (carpeta, .zip, copia anonimizada en la base) lleva
  los hallazgos de IA de los estudios en un `IPE_ACHADOS.json`; al importarlo en otro Ipê vuelven con el estado de
  cada uno. Anonimizado, sin el revisor ni la nota.
- **Inglés y español**: frases armadas por partes (como el final de Nódulos pulmonares) salían mitad en portugués;
  ahora cada parte se traduce.

## 0.100.85 — IA en la serie del cuadro; enfisema en la serie de parénquima; menos falta de memoria
- **"… en esta serie"**: el ítem del menú de cada IA corre en la serie del cuadro activo, aunque no sea la preferida en
  Configuración (antes, algunas IA cambiaban a la preferida). Si hay error, el mensaje dice cuál es la serie
  recomendada — también en Ipê Web, cuando se elige la serie del cuadro.
- **Enfisema**: la serie preferida pasa a ser la de parénquima/pulmón (`PARENQUIMA|PULMAO|…`), y el botón ya no cambia
  la serie de filtro duro por la de filtro suave. En un estudio con las dos, la de parénquima (con la reducción de
  ruido de la 0.100.81) dio el resultado del informe; la de mediastino falló.
- **Memoria**: en el modo rápido, una serie muy fina (ej.: TC de tórax de 0,6 mm) entra en el TotalSegmentator ya
  reducida a 1,5 mm, y las máscaras vuelven a la grilla original. Y los procesos auxiliares del TotalSegmentator ya no
  quedan trabados (unos 2 GB cada uno) cuando la IA cae — antes, la IA siguiente también se quedaba sin memoria.

## 0.100.84 — Exportar: elegir las series
- En la ventana **Exportar** (y en **Anonimizar una copia**), la casilla **Elegir las series** muestra cada estudio
  con sus series para marcar solo las que deben salir, con **Todas** y **Ninguna**. Vale para DICOM, imágenes y la
  copia anonimizada en la base; un estudio sin ninguna serie marcada queda fuera.

## 0.100.83 — El Ipê de escritorio ya no se congela con el servidor integrado
- Cuando el Ipê de escritorio es también el servidor, la preparación en segundo plano de los estudios recientes para
  Ipê Web leía los encabezados con 8 hilos y le quitaba el turno a la ventana, que quedaba "no responde". Ahora esta
  preparación lee un archivo a la vez, con pausa; los pedidos del navegador siguen rápidos, en paralelo.
- Un elemento DICOM con valor inválido (común en etiquetas privadas) dejaba fuera toda la imagen de los metadatos de
  Ipê Web y llenaba el registro; ahora solo queda fuera ese elemento.
- **Enfisema**: el filtro de ruido de la 0.100.81 dependía de scipy, que no viene en el Ipê instalado ("No module
  named 'scipy'" al grabar); ahora se hace solo con numpy, con el mismo resultado.
- Linux: el aviso del sistema mostraba "IpÃª" en lugar de "Ipê".

## 0.100.82 — Arreglo del "operator torchvision::nms does not exist"
- El **torchvision** entraba indirectamente (nnU-Net → timm) desde PyPI, hecho para otro PyTorch, y un `pip install`
  de los modelos extra podía cambiar el PyTorch de CPU; con el par descasado, el TotalSegmentator (enfisema y todo lo
  demás) y la instalación de la médula paraban con *operator torchvision::nms does not exist*.
- Ahora el PyTorch y el torchvision se instalan **juntos, del mismo índice**, y quedan fijados en las instalaciones
  siguientes. **Instalar los modelos extra** revisa el par antes de todo y, si no combinan, reinstala los dos (arregla
  un entorno que ya se rompió). La tarea que falla por esto dice qué hacer.

## 0.100.81 — Enfisema: menos puntos falsos en la serie ruidosa
- **Enfisema (%LAA−950)**: en una serie ruidosa (filtro duro, o aire de la tráquea con desvío estándar mayor de
  30 HU) Ipê aplica un filtro gaussiano leve (σ 0,8 mm) antes del umbral, y el ruido deja de aparecer como
  "enfisema" disperso por el pulmón. El hallazgo dice cuándo se hizo; se apaga en Configuración ▸ CAD/IA ▸ Enfisema.
- El botón **Enfisema** mide en la serie de filtro suave del estudio cuando la del cuadro tiene filtro duro.

## 0.100.80 — Ipê Web: búsqueda en el PACS con Hoy/Ayer, n.º del estudio y columnas ordenables
- En la búsqueda del PACS de Ipê Web: botones **Hoy** y **Ayer** (ponen la fecha y buscan), el campo **N.º del
  estudio** (Study ID; el número de acceso sigue en el campo Acceso) y las columnas **Acceso** y **N.º del estudio**.
- **Ordenar**: hacer clic en el título de una columna ordena por ella; de nuevo, invierte (▲/▼).

## 0.100.79 — RM de próstata: PI-RADS v2.1, volumen automático y modelos de investigación aparte
- **PI-RADS** (botón en el visor y en Ipê Web, en la RM de próstata): PSA y fecha, volumen por el elipsoide (los tres
  diámetros, o **Tomar de las reglas**) o por la segmentación automática, y la **densidad del PSA**; cada lesión con la
  zona, los **sectores** (clic en el mapa), el tamaño, T2, difusión, DCE, **ADC de la ROI del cuadro**, extensión
  extraprostática y la imagen vinculada. La **categoría** sale por la regla del PI-RADS v2.1 (zona periférica por la
  difusión, con el DCE; zona de transición por el T2, con la difusión), con avisos cuando tamaño y puntuación no
  coinciden, y se puede cambiar a mano.
- **Salidas**: el mapa de sectores pintado (esquema del estudio), el **SR del PI-RADS** ("Grabar en el estudio"), el
  texto del informe y la nueva plantilla **RM de próstata multiparamétrica (PI-RADS)**, con los campos
  `{pirads_achados}`, `{pirads}` y `{prostata_volume}`.
- **Volumen automático de la próstata** (TotalSegmentator, en el T2 axial): volumen y extensiones en los tres ejes,
  SEG y hallazgo; el volumen entra en el PI-RADS y da la densidad del PSA.
- **Modelos de investigación, opcionales y fuera del Ipê**: zonas de la próstata (MONAI/Prostate158) y lesiones
  sugeridas (PI-CAI, pesos CC BY-NC-SA 4.0). Nada viene en el instalador: el programa muestra la licencia, la persona
  acepta "uso en investigación y enseñanza, no clínico, no comercial" y solo entonces descarga (los pesos del PI-CAI
  se verifican por SHA-256). Las sugerencias entran como lesiones a revisar, y todo sale marcado **"modelo de
  investigación — no usar para diagnóstico"** (pantalla, SEG, SR e informe). Configuración ▸ CAD/IA ▸ Modelos de
  investigación.

## 0.100.78 — Mamografía: cuatro áreas de cuadrante, sincronías apagadas, SR sin revisión y envío al PACS
- **Zoom por cuadrante con cuatro áreas** (Ipê de escritorio e Ipê Web): posterior y superior → anterior y superior
  → posterior e inferior → anterior e inferior → mama entera (tecla Q; Mayús+Q vuelve). El cuadrante anda junto en
  todos los cuadros de fábrica; el botón **Cuadrante junto** de la barra de la mamografía lo apaga durante el examen.
- **En la mamografía, todas las sincronías vienen apagadas** (zoom y desplazamiento, ventana y cortes), en Ipê de
  escritorio e Ipê Web, y se guardan aparte de las otras modalidades. Quien había encendido el desplazamiento junto
  de la mamografía vuelve a apagado una vez.
- **Densidad y calcificaciones vasculares sin revisión** (opcional): la mamografía que llega se mide y el SR, las
  imágenes marcadas y el resumen se guardan enseguida, marcados como no revisados. Al abrir el examen todavía se
  puede confirmar o corregir: el SR se rehace.
- **Envío al PACS**: los nodos elegidos reciben el SR, las imágenes marcadas y el resumen una vez guardados (sin
  revisión o después de confirmar). Configuración ▸ CAD/IA ▸ Densidad y calcificaciones, y Registros ▸
  Automatizaciones de IA en Ipê Web.

## 0.100.77 — Ipê Web: zoom por cuadrante en la mamografía
- **Zoom por cuadrante en la mamografía de Ipê Web**, como en Ipê de escritorio: botón **Zoom por cuadrante** en la
  barra de la mamografía o tecla **Q** (**Mayús+Q** vuelve). Posterior y superior → posterior e inferior → mama
  entera, en todos los cuadros de la etapa juntos, cada uno de su lado: la pared torácica sigue en su borde y las
  mamas quedan espejadas. La tomosíntesis desplazada mantiene el cuadrante; la segunda pantalla acompaña; cambiar de
  etapa vuelve a la mama entera.

## 0.100.76 — Sitio web de Ipê con videos por tarea; más pantallas traducidas
- **Sitio web de Ipê** (GitHub Pages: <https://filipebarra.github.io/ipe/>), en inglés, portugués y español,
  organizado por tarea del día — leer un estudio, mamografía, RM de mama, PET/TC, IA, informes y esquemas, docencia
  con casos, servidor e Ipê Web. Cada tarea tiene un video corto grabado en el propio Ipê (estudios de ejemplo
  anonimizados), los pasos y dónde está cada cosa. El tutorial "Cómo armar un curso con casos" está en los tres
  idiomas. El sitio se genera desde `site/conteudo.py` y se publica solo con cada cambio.
- **Traducciones**: en inglés y español, ahora aparecen traducidos los rótulos de los formularios (por ejemplo, la
  ventana Organizar la lista), los botones con texto propio de las ventanas (Guardar, Eliminar el esquema…), los
  encabezados de las columnas de la Base de datos y el "etapa:" de la mamografía.

## 0.100.75 — Ipê Web: las marcas en mamografía, rayos X y ecografía vuelven a aparecer
- **Las marcas guardadas reaparecen** en Ipê Web en imágenes sin marco de referencia (mamografía, rayos X,
  ecografía): flechas, textos y medidas hechos en Ipê de escritorio o en Ipê Web se guardaban, pero no volvían a la
  pantalla al reabrir el examen.
- **Mamografía**: en la disposición de mamografía (que junta imágenes de varias series en un mismo cuadro), las
  marcas ahora se piden por las series reales de las imágenes.
- **Paquete de casos**: con eso, las marcas de los casos de mamografía aparecen al pedir "Mostrar el resultado".

## 0.100.74 — Esquemas guía separados del informe: botón Esquema en el visor y modelos en Configuración
- **Botón Esquema en el visor** (Ipê de escritorio e Ipê Web): abre los *Esquemas del examen* — nuevo, dibujar,
  eliminar y **Guardar en el examen** (guardar de nuevo reemplaza lo que había). El esquema es del examen y no
  depende de informe.
- **En el informe, solo incluir**: la casilla **Esquemas en el informe** (como las imágenes clave) pone la leyenda
  en el texto, las figuras en el PDF y, al firmar, los esquemas en el DICOM SR. Sin ella, el informe no lleva
  esquema. La franja de dibujar salió de la ventana del informe.
- **Modelos en la configuración**: **Configuración ▸ Esquemas ▸ Modelos de esquema** en el Ipê de escritorio y
  **Registros ▸ Modelos de esquema** en el Ipê Web (nuevo de una imagen, en blanco, editar, copiar, ocultar,
  restaurar, eliminar). La ventana de elegir el modelo quedó solo para elegir.
- Quien ya tenía esquemas de las versiones 0.100.72 y 0.100.73: siguen en el examen, pero entran en el informe solo
  con la casilla marcada.

## 0.100.73 — Esquemas guía: guardar en el examen sin informe y registrar o cambiar los modelos (escritorio y Web)
- **Guardar en el examen**: en la franja de los esquemas (Ipê de escritorio e Ipê Web), guarda al instante las
  figuras (serie "Esquemas do laudo") y un SR solo de los esquemas, sin firmar ni guardar el informe — como la tabla
  de la segmentación y el resumen de la densidad. Guardar de nuevo reemplaza lo que había; al firmar, el SR del
  informe pasa a llevar los esquemas.
- **Modelos también por el Ipê Web**: quien puede configurar envía una imagen (**Nuevo modelo de una imagen…**) o
  parte de una hoja vacía (**Nuevo modelo en blanco…**), en el navegador o en el Ipê de escritorio.
- **Cambiar los modelos existentes**: **Editar el modelo…** abre el modelo con las herramientas de dibujo — lo que se
  dibuja pasa a formar parte de él en todos los exámenes — y cambia el nombre y el grupo. **Guardar como copia** crea
  un modelo nuevo; en los modelos de Ipê hay **Ocultar de la lista** y **Restaurar el original** (el dibujo original
  nunca se pierde); los propios se eliminan.

## 0.100.72 — Esquemas guía en el informe (cara, cuerpo, tiroides, mamas, próstata), en Ipê y en Ipê Web
- **Esquemas guía**: en la ventana del informe (y en el informe del Ipê Web), **Nuevo esquema…** abre un dibujo de
  base para marcar los hallazgos: cara (frente y perfiles), cuerpo (frente y espalda), tiroides con los niveles
  cervicales, mamas y el mapa de sectores de la próstata. Son dibujos propios de Ipê; quien puede configurar registra
  los suyos a partir de una imagen.
- **Herramientas**: punto numerado, elipse, flecha, trazo libre, texto, mover, borrar y deshacer, en seis colores. En
  el Ipê Web funcionan con ratón, dedo o lápiz.
- **Próstata**: el clic pinta el sector con la categoría (PI-RADS 1 a 5); son los 41 sectores del PI-RADS v2.1.
- **Vinculado al informe y a las imágenes**: cada marca numerada tiene su descripción; **Insertar la leyenda en el
  informe** (y el campo `{esquemas}` de los modelos) lleva la lista al texto. **Vincular a la imagen abierta** une la
  marca a la imagen del visor, que pasa a ser imagen clave.
- **Adónde va**: la figura entra en el PDF del informe; al firmar, va al examen como imagen DICOM (serie "Esquemas
  do laudo") y se cita en el DICOM SR, con la posición de cada marca y la imagen vinculada. Con esquema, el SR pasa a
  ser un Enhanced SR (el Basic Text SR no acepta coordenadas); sin esquema, nada cambia.

## 0.100.71 — Ipê Web: Registros (usuarios, nodos DICOM, impresoras DICOM, automatizaciones de IA)
- Para **administradores**, la lista de exámenes del Ipê Web gana el botón **Registros…**, con cinco pestañas:
  - **Usuarios**: crear, editar, activar/desactivar, restablecer la contraseña y eliminar; **Perfiles y permisos…**
    con la tabla de lo que cada perfil puede hacer. Valen las reglas del Ipê de escritorio (contraseña de 6 o más
    caracteres; siempre queda un administrador activo; nadie se elimina a sí mismo). Quien es desactivado, eliminado
    o tiene la contraseña restablecida pierde al instante las sesiones abiertas.
  - **Nodos DICOM** (DIMSE y DICOMweb) con **Probar red**, y las **identidades** (AE de origen). Contraseña, token y
    secreto no vuelven al navegador: el campo vacío deja lo que estaba.
  - **Impresoras DICOM**, con **Probar conexión**; cambiar el nombre acompaña los destinos de impresión.
  - **Automatizaciones de IA**: las herramientas de Preferencias ▸ CAD/IA — qué corre solo a la llegada, en qué
    exámenes y series, y adónde va el resultado.
  - **Registro de acceso**, con filtros.
- **Contraseña provisional en el Ipê Web**: quien entra con la contraseña dada por el administrador debe cambiarla
  antes de cualquier otra cosa (antes, solo el Ipê de escritorio lo pedía). **Cambiar mi contraseña…** está en
  Registros ▸ Usuarios.
- Todo lo que cambia va al registro de acceso con el nombre de quien lo cambió.

## 0.100.70 — Ipê Web: arrastrar la miniatura de la serie ya no es "adjuntar"
- En Ipê Web, arrastrar la miniatura de una serie al visor mostraba "Suelte para adjuntar al estudio" y podía adjuntar
  la propia miniatura. El navegador pone la imagen de la miniatura en el arrastre, y el Ipê la tomaba por un archivo
  del ordenador. Ahora solo lo que viene de fuera de la página es adjunto; la serie va al cuadro.

## 0.100.69 — Investigación: densidad y calcificaciones de las mamografías de una lista, en lote
- **Red ▸ Densidad y calcificaciones en lote (hoja de cálculo)…**: a partir de una hoja (.xlsx o .csv) con el ID del
  paciente y la fecha de la mamografía, el Ipê encuentra cada examen (en su base o en el PACS), lo descarga, mide la
  densidad (red de la NYU) y las calcificaciones vasculares (SCU-Net) y guarda una hoja con las columnas originales y
  las del Ipê al lado: categoría y probabilidades de la densidad; grado, área (mama peor, por mama y por incidencia) y
  las escalas estimadas (CSBI, Margolies, Loberant, BAC-SS); prótesis; avisos; Study UID y accession.
- Comprueba la fecha de nacimiento (opcional), borra del Ipê lo que descargó solo para el lote (lo que ya estaba nunca
  se borra), puede parar y continuar, reintenta los que fallaron, y tiene "cuántas filas ahora" para probar con pocas.
- Son las medidas automáticas, sin confirmación: revise una muestra antes de analizar.

## 0.100.68 — Impresiones y panel de películas en Ipê Web
- **Botón "Impresiones…" en la lista de exámenes de Ipê Web**, para **administradores y técnicos**: la pestaña
  Impresiones del Ipê de escritorio, atendida por el servidor.
  - La lista de lo que llegó por la impresora DICOM, de lo montado en el compositor y de la película que vino en el
    examen, con búsqueda, filtro (recibidos, montados, enviados, detenidos) y actualización automática.
  - La **hoja** al lado (◀ ▶, Ampliar), los datos del trabajo y el **historial de envíos**.
  - **Identificar paciente…** con **OCR** del encabezado (leído en el servidor); al confirmar, la película sigue por
    la regla.
  - **Enviar a…** cualquier **destino registrado en el servidor** (sin necesidad de compartir), con modelo de hoja;
    **Reimprimir…**, **Unir como páginas**, **Borrar** y **Detenidos…** con **Liberar**.
  - Pestaña **Panel**: las tarjetas, las películas por mes, por modalidad y por quién las creó, la lista y
    **Exportar CSV**.
  - La configuración de impresión sigue en el Ipê de escritorio. Todo lo hecho desde el navegador va al registro de acceso.
- **Servidor más firme**: cada pedido del navegador que necesitaba el hilo principal (película, impresión, IA) dejaba
  un objeto de Qt; con muchos, el servidor podía caerse o trabarse al grabar una hoja en PDF. Corregido (hallado en las
  pruebas de esta versión).

## 0.100.67 — Estructuras: tijera, contorno con un clic, semillas; farmacocinética (Tofts, Ktrans)
- **Panel Estructuras, pestaña nueva "Más herramientas"** (Deshacer/Rehacer valen para las dos pestañas):
  - **Tijera**: dibuje una forma (libre, rectángulo o elipse) y la estructura se corta con ella — borrar dentro, borrar
    fuera o rellenar —, solo en el corte o en todos los cortes, en cualquier plano.
  - **Contorno por nivel**: haga clic y arrastre sobre la lesión; entra la región limitada por la línea de la misma
    intensidad del punto (lesión clara u oscura), siguiendo el ratón.
  - **Por el diámetro mayor**: trace el diámetro mayor y reciba el contorno 3D en una estructura nueva, con diámetro
    mayor, eje corto y volumen; el **Ajuste** rehace el contorno al instante, y aparece un aviso si hay poco contraste.
  - **Hueco (cáscara)** hacia dentro, hacia fuera o mitad a cada lado; **Suavizar** (mediana, apertura, cierre).
  - **Umbral automático (Otsu)** y **Rellenar por el rango**; **Dividir islas en estructuras** (una lesión por línea).
  - **Crecer desde las semillas**: trazos en la lesión y trazos en el fondo; cada vóxel queda con la semilla a la que
    se une por el camino de menor cambio de intensidad.
- **Dinámica: botón Ktrans (Tofts)…** — mapas de **Ktrans**, **ve**, **kep** (y **vp** en el Tofts extendido) y los
  mismos números por ROI en la tabla y en *Copiar valores*. Entrada arterial poblacional (Parker) o de una ROI en una
  arteria; TR y ángulo leídos del examen; T1 del tejido supuesto (editable). La ventana y el panel **avisan** cuando
  la resolución temporal es de rutina (una fase por minuto): el Ktrans es entonces indicativo, no absoluto.
- Las cuentas nuevas se verificaron con datos sintéticos (formas y curvas simuladas); en un examen real, revise el
  contorno y lea el aviso del Tofts.

## 0.100.66 — Gestión en el Web en el idioma de la página; días de la semana en las reglas
- **Gestión DICOM en el Ipê Web**: el progreso, los resúmenes, los detalles de cada estudio, la cola y los informes de
  las reglas ahora salen en el idioma de la página (inglés o español) — antes venían del servidor solo en portugués.
- **Horario de las reglas** (Ipê de escritorio y Web): los días aparecen como "Lun a Vie" o "Lun, Mié, Vie" — antes
  eran iniciales, y cambiadas.
- Traducciones: un texto con varios huecos genéricos ya no pasa por delante de uno más específico.

## 0.100.65 — Gestión DICOM en el Ipê Web: la pestaña Automático
- **Pestaña Automático** en la Gestión DICOM del navegador (administradores): crear, editar, duplicar, activar o
  desactivar, eliminar y **ejecutar ahora** las reglas con horario — las mismas del Ipê de escritorio (quedan en la
  base de datos). El editor tiene todo lo que tiene la ventana: modalidades e identidades, destino, qué enviar,
  período, horario (cada N minutos o todos los días a una hora, por día de la semana) y nuevo intento en caso de error.
- **Último informe** de cada regla (completados ahora, con error, fuera de línea, otro Study UID) e **historial**.
- Las reglas se ejecutan en el servidor; los cambios van al registro de acceso, con el usuario.

## 0.100.64 — Ipê Web: el traductor del navegador ya no toca la página
- El navegador ofrecía (o hacía solo) la traducción de la página y cambiaba los textos del Ipê Web por otros sin
  sentido. La página ahora le dice al navegador que no traduzca; los idiomas del Ipê Web siguen siendo los del
  propio programa.

## 0.100.63 — Gestión DICOM en el Ipê Web (administradores)
- **Gestión DICOM… en la lista de estudios del Ipê Web**, solo para administradores: comprobar si los estudios de las
  modalidades están en el PACS (por estudio y por serie) y enviar lo que falta o el estudio entero, al PACS o a otro
  destino — la misma rutina de la ventana del Ipê de escritorio.
- **Corre en el servidor**: quien habla con las modalidades y el PACS es el servidor (con su AE o la identidad
  elegida); la comprobación y el envío continúan con la página cerrada. Aparecen todos los nodos DIMSE del servidor,
  sin necesidad de compartirlos con los clientes. **Probar** (C-ECHO) en cada nodo.
- Cola de envío, nueva comprobación después del envío, filtro "solo los que tienen problema", CSV y registro de
  acceso con el usuario.

## 0.100.62 — servidor HTTPS: el Ipê Web ya no desaparece; http:// lleva a https://
- **Servidor con certificado (HTTPS)**: una conexión que se abría y no decía nada (el navegador adelantando
  conexiones, un celular dormido) detenía el servidor entero hasta cerrarse — el Ipê Web y los clientes dejaban de ser
  atendidos y solo volvían al reiniciar. La negociación del HTTPS ahora se hace en cada conexión, con plazo de 20 s.
- **http:// en el servidor HTTPS**: en lugar de fallar, el navegador es llevado al https:// de la misma dirección.

## 0.100.61 — tiempo de apertura del Ipê de escritorio en modo cliente en el registro del servidor
- En modo cliente, cada línea "Abertura (…)" del Ipê de escritorio (primera imagen, por etapa — con la espera del
  servidor — y lo que llega después) también va al registro del servidor, como "Abertura cliente (…) |
  usuario@computadora | versión". Se pueden comparar versiones y computadoras sin ir a la máquina del cliente.

## 0.100.60 — la tomosíntesis abre rápido; calcificaciones automáticas; serie puesta por fuera en la dinámica (Web)
- **Abrir mamografía con tomosíntesis**: cada corte releía el encabezado entero del archivo y decodificaba reteniendo
  el programa; ahora el encabezado y el lugar de los cortes se leen una vez y la decodificación corre en paralelo (en
  la prueba: de ~8 s a ~1,5 s hasta la primera imagen; desplazar los cortes también es más ligero).
- **Calcificaciones vasculares automáticas**: la medida a la llegada y en la revisión del banco fallaba en todas las
  imágenes (error interno); corregido, y las mamografías del banco se revisan de nuevo en el próximo inicio.
- **Ipê Web, dinámica**: la serie puesta en un cuadro desde la lista de series (y no desde el rótulo del cuadro) pasa
  a acompañar por la posición en el paciente — antes seguía el número del corte y se perdía al desplazar.
- Sin aviso de "miniatura falló" para series sin imagen (SR).
- **Ipê Web: tiempo de apertura en el registro del servidor** — la línea "Abertura web (…)" (primera imagen, por
  etapa, y todo disponible, con red y decodificación), como la "Abertura (…)" del Ipê de escritorio; solo modalidad,
  recuentos y tiempos.
- **Modo cliente**: volver a grabar el SR de densidad y calcificaciones ya no duplica las series en el servidor.

## 0.100.59 — Ipê Web: serie de otro plano en la dinámica
- Una serie de otro plano (sagital, coronal) en un cuadro de la dinámica ya no vuelve al medio al desplazar la
  dinámica después del clic de las **Líneas de referencia**: no acompaña el desplazamiento (ni mueve la dinámica); va
  al punto solo con el clic.

## 0.100.58 — Ipê Web: dinámica con series, diseño y cuadros a elección; el punto de la correlación
- **Dinámica de mama**: **Series…** elige las series que entran en el cálculo (o **Detectar solo**); cuando el
  servidor no encuentra las fases, la lista se abre para marcarlas.
- **Diseño** de la dinámica (1 × 1 a 3 × 3) y, en cada cuadro, **cualquier fase, sustracción, mapa o serie del
  estudio** (la serie que no es de la dinámica acompaña por la posición en el paciente).
- **Sustracción con ◂ ▸** en el propio cuadro, como en el Ipê de escritorio (el cuarto cuadro de fábrica ya es la
  sustracción).
- **Correlación**: hacer clic con las **Líneas de referencia** marca el punto con una cruz en todos los cuadros que
  pasan por él (como el Shift del Ipê de escritorio); **Esc** la quita.

## 0.100.57 — Densidad y calcificaciones automáticas, confirmación al abrir y SR
- Toda **mamografía que llega** (red, PACS, importación, envío al servidor) tiene la **densidad** y las
  **calcificaciones vasculares** medidas solas, en segundo plano (Tareas de IA). Nada se confirma solo.
- **Al abrir la mamografía** (Ipê e Ipê Web), se abre la ventana de la densidad para confirmar; luego, la de las
  calcificaciones.
- **Confirmadas las dos**, el estudio recibe un **SR** con todo, las **imágenes con las calcificaciones marcadas** y
  un **resumen** en tabla.
- **Las mamografías que ya estaban en la base** se revisan una vez, en segundo plano, al abrir esta versión.
- Preferencias ▸ CAD/IA ▸ **Densidad y calcificaciones (mama)**.

## 0.100.56 — Paquete de casos (la lista se abre en el navegador)
- **Exportar paquete de casos** (clic derecho en la lista): una carpeta con el visor completo de Ipê Web y los
  estudios anonimizados, para docencia, congresos o colegas. Se abre con **Abrir casos** en Windows, Mac o Linux (sin
  instalar nada) o copiada a cualquier sitio de archivos estáticos.
- Cada caso tiene la **presentación** (historia clínica, series, documentos) y el **resultado** — con **Mostrar el
  resultado**: diagnóstico, informe/resultado, biopsia/anatomía patológica, notas docentes, las series y documentos
  del resultado y las **marcas** (flechas, medidas, ROIs) en las imágenes.
- **Organizar lista**: campos nuevos **Informe / resultado** (con **Usar el informe del estudio**), **Biopsia / AP**
  y **Series del resultado**.

## 0.100.55 — Calcificaciones vasculares: cuatro escalas; adjuntos y panel más grande en Ipê Web
- **Ipê Web: adjuntar PDF e imágenes al estudio** — arrastre los archivos sobre el estudio abierto (como en Ipê de
  escritorio) o use **Adjuntar PDF o imagen…** debajo de las series. Se convierten en DICOM dentro del estudio en el
  servidor, siguen las reglas de envío del estudio y aparecen enseguida. Los PDF del estudio se listan en
  **Documentos** y se abren en una pestaña nueva.
- **Ipê Web: monitores reales** — el panel Monitores ya no muestra siempre 3 ventanas: con el permiso del navegador
  (Chrome/Edge, en HTTPS o en el propio servidor) detecta **todos** los monitores, con la resolución y orientación de
  cada uno, y usted elige qué va en cada uno. Sin el permiso, elija cuántas ventanas (1 a 8).
- **Ipê Web: Vincular** ahora funciona también en una sola ventana — los cuadros se desplazan juntos (mismo plano),
  con la misma ventana (misma modalidad, no en MG) y el mismo zoom.
- La ventana de **Calcificaciones vasculares** (escritorio e Ipê Web) muestra también las escalas publicadas,
  estimadas por lo que marcó la red: **Margolies** (0–12: vasos + extensión + densidad, por mama), **CSBI** (0–3),
  **Loberant** (0–3) y **BAC-SS** (Nv + Ov + L, en la MLO). Pase el ratón para ver cómo se calcula cada una. Son
  estimaciones — revise las imágenes. Estudios medidos antes de esta versión: **Medir de nuevo** para obtener las escalas.
- El panel de **Calcificaciones vasculares** en Ipê Web abría estrecho y cortaba las vistas previas, el grado
  "Acentuada" y los botones. Ahora abre grande (cabe en la pantalla), las vistas previas crecen con él y se puede
  **redimensionar arrastrando la esquina inferior derecha**; el navegador recuerda el tamaño. El panel de Densidad
  mamaria también se puede redimensionar.
- Los avisos del panel (prótesis, compresión localizada/ampliación, incidencias faltantes) aparecen traducidos.

## 0.100.54 — Actualización: límite de GitHub y "la versión no cambia"
- **"HTTP Error 403: rate limit exceeded"** al buscar versión nueva: la API de GitHub limita las consultas por
  dirección de internet (en una clínica, todos salen por la misma). Ahora Ipê encuentra la versión en la página del
  release, que no tiene ese límite, y verifica la descarga con el nuevo `SHA256SUMS.txt` del release.
- **"Instalo otra versión y la versión no cambia"**: al abrir, Ipê avisa cuando la copia abierta es más vieja que la
  que el instalador registró en otra carpeta (acceso directo a otra copia) y ofrece abrir la nueva; o cuando el
  instalador corrió en esta carpeta sin poder reemplazar los archivos. El instalador ahora espera que Ipê se cierre
  (también el de la bandeja) antes de reemplazar los archivos. El registro muestra la carpeta del programa al abrir.

## 0.100.53 — Ipê Web en pantallas más pequeñas
- La barra superior del visor muestra lo que cabe y pone el resto en el botón **»**, al final de la barra (menú con
  los botones que no cupieron). Antes, en pantallas de menos de ~1900 píxeles de ancho, los botones de la derecha
  (Informe, Enviar, CAD/IA, Modo lectura…) quedaban escondidos, accesibles solo desplazando la barra de lado.

## 0.100.52 — Calcificaciones vasculares en todas las imágenes; ventana de la mamografía en el navegador
- **Calcificaciones vasculares** en **todas las imágenes 2D** del examen (repetición, otras incidencias, compresión
  localizada, magnificación); en la ventana de confirmación (y en Ipê Web) cada incidencia recorre sus imágenes
  (◀ ▶ o la rueda). La compresión y la magnificación aparecen, pero no entran en el área de la mama.
- **Ipê Web**: la mamografía mantiene la ventana del archivo (la ventana de una imagen ya no pasa a las otras, ni por
  las ventanas vinculadas); la ventana puesta en un corte de la tomosíntesis vale para los otros cortes de la serie.

## 0.100.51 — Calcificaciones vasculares de la mama
- Botón **Vasos** en la mamografía (y **Calcificaciones vasculares** en Ipê Web): la red **SCU-Net** (Emory, licencia
  MIT, en el paquete) marca las calcificaciones vasculares en las cuatro incidencias; la ventana muestra las
  incidencias con las marcas, el área por mama y una sugerencia provisional de grado; el médico gradúa (**ausente,
  leve, moderada o acentuada**), confirma y puede enviar la frase al informe. Todo queda guardado en el examen, para
  validar y calibrar.
- Solo cuentan los tramos alargados (≥ 3 mm); la prótesis se detecta en la imagen y su borde queda fuera (en
  examen con prótesis, sin sugerencia de grado).

## 0.100.50 — Densidad mamaria en Ipê Web
- Botón **Densidad mamaria** en el visor web (exámenes con mamografía): la red de NYU medida en el servidor en las
  cuatro incidencias, la categoría con las probabilidades, **Confirmar** y **Confirmar y enviar al informe** (la
  composición en el BI-RADS del informe del navegador) y **Medir de nuevo**. La medida y la confirmación son las
  mismas del Ipê de escritorio (entran en Densidades medidas y en la concordancia). Confirmar requiere el permiso de
  escribir informes.

## 0.100.49 — Imprimir por el servidor
- **Impresora DICOM compartida por el servidor**, como los nodos DICOM: en el servidor, la impresora tiene la
  casilla *Compartir con los clientes*. En el Ipê del cliente aparece en la ventana Imprimir del compositor como
  *Nombre (por el servidor)*; en Ipê Web, en la Salida de la película. Las hojas salen del servidor, con su IP y su
  AE; el cliente no recibe la dirección ni el AE.
- Ipê Web muestra solo las impresoras DICOM compartidas, sin la dirección (antes mostraba todas las del servidor,
  con AE e IP).

## 0.100.48 — Densidad mamaria: solo la red de NYU
- Después de las revisiones, la densidad queda **solo con la red de NYU**: el % de área por Otsu y por fuzzy, muy
  distintos de las categorías confirmadas, ya no se miden ni se muestran (ventana del examen, cola de revisión,
  Densidades medidas, CSV y concordancia). Medir es más rápido. Lo ya guardado con ellos queda en la base.
- Salieron también la tabla por imagen con la máscara (*Por imagen, con la máscara…*) y el botón *Ver el % de área
  con la máscara…* de la cola.

## 0.100.47 — Actualización por el servidor: un paquete por sistema
- **El Mac descargaba el paquete de Linux** al buscar versión nueva en un servidor central con Linux: el servidor
  guardaba un solo paquete por canal y lo entregaba a cualquier equipo. Ahora cada canal guarda un paquete por
  sistema (Windows, Linux, macOS chip Apple, macOS Intel, por el nombre del paquete) y cada equipo solo recibe el
  suyo; publicar uno no borra los otros. Sin paquete para el sistema, no se descarga nada y el aviso ofrece GitHub.
- Con un servidor todavía antiguo, el cliente revisa el nombre del paquete y no descarga el de otro sistema.
- En el Mac, el `.dmg` que viene del servidor se instala como el de GitHub (cambia la aplicación y la abre de nuevo).
- La ventana *Actualizaciones por el servidor central* muestra lo publicado para cada sistema.

## 0.100.46 — Densidades medidas; la red de la NYU va en el paquete
- **Densidades medidas** (Informes ▸ Densidad mamaria: medidas y confirmaciones…, y en el botón Densidad): una fila
  por examen medido, con la red de la NYU, el % de área por Otsu y por fuzzy, la categoría confirmada, quién la
  confirmó y cuándo. Filtros por período y situación (no confirmada, igual a la red, distinta de la red), la
  concordancia de cada método con las confirmaciones, doble clic para abrir el examen y CSV.
- **La red de la NYU va en el paquete** (Windows, Linux y macOS): antes, el paquete no llevaba el archivo del modelo,
  y la red no corría sin copiarlo a mano. Licencia BSD-2, con la atribución en `modelos/LEIAME.md`.
- La densidad y la cola de revisión **salieron del menú Archivo**: quedan en el botón Densidad.

## 0.100.45 — Los nodos del servidor en la ventana PACS del cliente
- **El nodo compartido por el servidor no aparecía en el cliente** cuando la primera consulta al servidor fallaba
  (la lista quedaba vacía hasta cambiar de ubicación). Ahora la lista se pide de nuevo cada vez que se abre la
  ventana PACS, la falla no se guarda, y la lista dice el motivo cuando está vacía (el servidor no comparte ningún
  nodo, o no respondió).
- **El nodo 1 del servidor se confundía con "Todos los nodos de búsqueda"** en la ventana PACS del cliente.
  Corregido.
- Con un nodo del servidor elegido, el campo **Como** desaparece: quien busca y descarga es el servidor, con su AE,
  y el examen va a la base del servidor (la ventana lo dice).
- En el registro del nodo, la ayuda de *Visible para* explica que es para los usuarios del propio programa; para
  los clientes, vale *Compartir con los clientes*.
- **Densidad**: cuando el examen no se puede guardar (servidor central en una versión anterior), la medida aparece
  igual, con el aviso para actualizar el servidor.

## 0.100.44 — El botón Densidad
- **Botón Densidad** en los exámenes de mamografía (fuera de la lista de IA): *Medir en segundo plano* (mide las
  cuatro proyecciones y las guarda en el examen, sin abrir ventana) y *Medir y revisar* (muestra lo que ya se midió o
  mide en el momento). La **red de la NYU** va primero, con la probabilidad de cada categoría; el **% de área por Otsu
  y por fuzzy** queda abajo, por ahora. La categoría de la red viene marcada; usted confirma o la cambia, y
  *Confirmar y enviar al informe* pone la composición en el informe BI-RADS. Todo queda guardado en el examen, con
  quién confirmó y cuándo.
- La cola de revisión usa la medida ya guardada del examen y muestra también el fuzzy; la respuesta en la cola vale
  como la confirmación del examen. El CSV ganó las columnas del fuzzy.

## 0.100.43 — Revisión de la densidad mamaria
- **Revisar la densidad (cola de exámenes)**: en *Archivo*, en la barra de mamografía y en el botón IA ▸ Densidad.
  Arme la cola por período, y cada mamografía se abre en el visor con las dos sugerencias del programa (red de la
  NYU y % de área). Usted confirma o corrige con una tecla (A–D o 1–4; N = no evaluable) y se abre el examen
  siguiente. En parte de los exámenes (10 %, ajustable) la sugerencia solo aparece después de la respuesta, como
  control. Abajo, la concordancia de cada método con usted (kappa ponderado, acuerdo exacto, denso × no denso), y el
  CSV con todo. La revisión queda en la base, una por examen y por revisor.
- **Densidad en la lista del botón IA** en los exámenes de mamografía: medir en las imágenes de la pantalla y la
  cola de revisión.

## 0.100.42 — Organización del código, tercera parte (sin cambios de uso)
- **El cuadro de imagen y la ventana principal también se dividieron**, con los mismos nombres de función.
  `viewport.py` (3900 líneas) quedó con 1200; el resto pasó al dibujo del cuadro, el mouse y el teclado, los menús y la
  mamografía. `main_window.py` (4200) quedó con 2900; el resto pasó a la pestaña Impresiones, las bases y el servidor,
  la película automática de la ecografía y los documentos adjuntos. Nada cambia en pantalla; la prueba que verifica
  que ninguna función quede oculta por otra ahora revisa también estas dos partes.

## 0.100.41 — Organización del código, segunda parte (sin cambios de uso)
- **El visor se dividió en cuatro archivos más**, con los mismos nombres de función: MPR y planos (`mpr_aba.py`),
  fusión y lectura PET (`fusao_aba.py`), mamografía y protocolos por etapas (`mamografia_aba.py`) y las herramientas
  de IA y Estructuras (`ia_aba.py`). `viewer_tab.py` bajó de 6600 líneas (en la 0.100.38) a 3000. Nada cambia en
  pantalla; la prueba que verifica que ninguna función quede oculta por otra con el mismo nombre ahora revisa todas
  las partes.

## 0.100.40 — Letra de las anotaciones en la barra; el pincel abre Estructuras
- **Letra de las anotaciones más grande o más pequeña sin ir a la configuración**: en la flecha del botón **Anot.**,
  *Letra más grande*, *Letra más pequeña* (de 10 en 10 %, de 60 a 250 %) y *Letra de tamaño normal*, para el texto
  de las esquinas (paciente, serie, ventana, FOV), en todas las ventanas. El menú muestra el tamaño en uso, y las tres
  acciones pueden tener tecla en los atajos.
- **El pincel abre el panel Estructuras solo**: antes, pintar sin el panel abierto mandaba buscar un menú
  "3D ▸ Estructuras" que no existía con ese nombre. Ahora el panel se abre en la serie del cuadro y el trazo ya pinta
  en una estructura nueva. En un cuadro sin serie de cortes (mamografía, rayos X), la barra de estado dice por qué no
  pinta.

## 0.100.39 — Organización del código (sin cambios de uso)
- **La barra de herramientas del visor tiene su propio archivo** (`ui/viewer/barra.py`). `viewer_tab.py` tenía 6600
  líneas; la barra, los botones por modalidad, el botón IA, los botones del mouse y el nivel de anotación (unas 1400
  líneas) pasaron allí, con los mismos nombres. Nada cambia en pantalla; una prueba nueva verifica que ningún método
  de la barra quede oculto por otro con el mismo nombre.

## 0.100.38 — Abrir y descargar más rápido (Ipê, modo cliente e Ipê Web)
- **Descarga en modo cliente ~3× más rápida** (720 cortes de TC: de 2,9 s a 0,8 s en la medición): el servidor envía
  junto los datos de cada imagen, y el cliente guarda el archivo directo en su lugar y la base en lotes, sin releer ni
  escribir dos veces. La **primera imagen** llega antes: la muestra de todas las series viene en una sola petición.
- **La conexión con el servidor queda abierta** entre las peticiones (antes, una conexión nueva en cada llamada).
- **Servidor ~4× más ligero por imagen en Ipê Web** (de 220 a 930 imágenes/s en la medición): permisos y "quién ve
  este estudio" guardados por segundos (un cambio hecho en el servidor vale al instante); la imagen con la copia de
  envío lista sale sin abrir el original; los metadatos de las series quedan en disco y listos para los estudios
  recientes.
- **Respuestas pequeñas del servidor sin espera**: en una conexión abierta (el navegador), cada respuesta pequeña
  esperaba la confirmación de la red — 40 ms en Linux, hasta 200 ms con cliente Windows.
- **Abrir desde la base local**: JPEG-LS y HTJ2K decodificados en paralelo, sin bloquear la pantalla (RM: de
  1,1–1,3 s a 0,4–0,6 s); **mamografía** con las incidencias decodificadas juntas y la alineación por el pezón ~15×
  más rápida (de 2,2 s a 0,7–0,8 s en dos núcleos).
- **Importación ~2× más rápida** (escritura en la base en lotes).

## 0.100.37 — PACS por el servidor (cliente e Ipê Web), botón IA y difusión en toda RM
- **Buscar y descargar del PACS por el servidor central.** En el servidor, cada nodo de búsqueda puede marcarse
  *Compartir con los clientes*. El Ipê cliente pasa a ver ese nodo en la búsqueda del PACS (y en la de anteriores)
  como *Nombre (por el servidor)*: quien habla con el PACS es el servidor, con su AE title y su contraseña, y el
  estudio descargado entra **en la base del servidor**, en la base de quien lo pidió. El progreso aparece en la cola
  del cliente; cancelar allí cancela en el servidor.
- **Ipê Web: Buscar en el PACS…** en la lista de estudios, con los mismos nodos compartidos: búsqueda, **Descargar**
  (a la base del servidor), el progreso de las descargas y **Abrir el estudio** al terminar. Buscar requiere el
  permiso de búsqueda; descargar, el de descarga; todo en el registro de acceso.
- **Botón IA en el visor:** las IA salen de la barra y quedan en una sola lista, como la de las medidas, con las que
  valen para el estudio; al final, los hallazgos para revisar, las tareas de IA y las otras IA. Se puede volver a un
  botón por IA al final de la misma lista.
- **Difusión en toda RM:** el botón Difusión aparece en cualquier RM, aunque la descripción de la serie no diga DWI
  (y reconoce también RESOLVE, ZOOMit, IVIM, SS-EPI y EP2D).

## 0.100.36 — PostgreSQL es la única base de datos
- **La base de datos de Ipê pasa a ser siempre el PostgreSQL incluido en Ipê** (nada que instalar). SQLite sale: en la
  primera apertura después de actualizar, la base antigua pasa a PostgreSQL con una ventana de progreso (solo una
  vez; en una base grande, algunos minutos), con el recuento de cada tabla verificado. El archivo antiguo queda
  guardado como `dicomviewer.sqlite.migrado` en la misma carpeta. Vale para la base principal, para las otras
  ubicaciones (disco externo, otra carpeta: cada una con PostgreSQL dentro de su propia carpeta) y para la caché del
  modo cliente.
- El servidor PostgreSQL propio sigue como opción para la base principal. La ventana *Servidor de base de datos* y la
  línea de comandos pierden la opción SQLite; el botón Copiar (y `--copiar`) copia la base en uso a la elegida.
- La contraseña del PostgreSQL de Ipê pasa a guardarse con los datos (cada carpeta con la suya).
- Corregido: con un espacio en la ruta de la carpeta de datos (en macOS la carpeta predeterminada lo tiene,
  "Application Support") el PostgreSQL de Ipê no arrancaba.
- Valores vacíos que SQLite aceptaba en campos obligatorios (de bases de versiones antiguas) entran con un valor
  predeterminado en la migración.

## 0.100.35 — PostgreSQL que viene con Ipê
- **Ya no hace falta instalar PostgreSQL aparte**: Ipê trae PostgreSQL 16 dentro del paquete (Windows, macOS y
  Linux). En Configuración ▸ Base de datos ▸ Servidor de base de datos, la opción *PostgreSQL que viene con Ipê*: se
  inicia solo cuando Ipê o el servidor central se abre, guarda los datos en la carpeta de datos y se detiene cuando
  se cierra el último programa de Ipê. Solo acepta conexiones de este equipo, con una contraseña creada y guardada por
  Ipê. El botón Copiar lleva la base actual a él. Línea de comandos: `ipe banco embutido --copiar`.
- El paquete es unos 35 MB más grande.

## 0.100.34 — Base principal en PostgreSQL
- La base principal puede estar en un servidor **PostgreSQL** (gratuito; Windows, macOS, Linux o nube), para el
  servidor central con muchas estaciones o un servidor en la nube. **Configuración ▸ Base de datos ▸ Servidor de base
  de datos**: servidor, puerto, base, usuario y contraseña (cifrada), probar la conexión y **copiar la base actual** de
  SQLite allí, con el recuento de cada tabla verificado. SQLite sigue siendo el predeterminado; las imágenes siguen en
  la carpeta de datos.
- Línea de comandos: `ipe banco status | postgres … [--copiar] | sqlite`; la variable `IPE_DATABASE_URL` para
  servidores montados por guion.
- Toda la batería de pruebas ahora también corre contra un PostgreSQL real.

## 0.100.33 — Segmentar por la caja (MedSAM2) no montaba el modelo
- **Segmentar por la caja (MedSAM2)** se detenía con "Cannot find primary config 'configs/sam2.1_hiera_t512.yaml'":
  el paquete de MedSAM2 se instala sin el archivo de configuración del modelo. Ipê trae ahora ese archivo y lo
  coloca cuando falta — **no hace falta reinstalar** los modelos extra. La instalación también comprueba la
  configuración del modelo, y no solo que el paquete exista.

## 0.100.32 — macOS: teclas del Mac, enlaces del sistema con alias, actualización que instala y paquete en el release; PET/CT con sesión preparada
- **Teclas del Mac:** los atajos ya valían con ⌘ (Qt los cambia solo); ahora los textos también — ayudas, menús y
  avisos muestran ⌘ y ⌥ en lugar de Ctrl y Alt.
- **Enlaces:** en macOS, `ipe://` y `dicomviewer://` abren Ipê (o van al que ya está abierto).
- **Alias del enlace** (todos los sistemas): en Red ▸ Llamada externa, otros nombres de enlace que abren Ipê, como
  `osirix` u `horos`. El enlace con el formato de OsiriX (`osirix://?methodName=displayStudy&StudyInstanceUID=…`)
  se entiende; `downloadURL` se rechaza.
- **Actualización en macOS:** Buscar actualizaciones descarga el `.dmg` de la arquitectura correcta (antes ofrecía
  el paquete de Linux), reemplaza la aplicación y la abre de nuevo. Donde no se puede reemplazar sola, el `.dmg`
  se abre para hacerlo a mano.
- Los paquetes de macOS (chip Apple e Intel) salen ahora junto con el release.
- **PET/CT — sesión preparada:** junto con la carga tumoral (al llegar el estudio o con el botón Carga) quedan
  guardadas las referencias de hígado y mediastino (PERCIST/Deauville) y el registro con el PET/CT anterior; el
  estudio preparado se abre en la Lectura PET. Lo hecho a mano no se cambia. Opciones en Configuración ▸ CAD/IA.
- Registro entre estudios: un volumen demasiado pequeño para la primera resolución ya no rompe el registro.

## 0.100.31 — macOS: buscar actualizaciones (y todo HTTPS) vuelve a funcionar
- En el paquete de macOS, **Buscar actualizaciones** fallaba con "certificate verify failed": el programa no
  encontraba los certificados de las autoridades. Lo mismo pasaba al descargar modelos de IA, con DICOMweb por
  HTTPS y con el informe por IA. Donde el sistema no entrega los certificados, Ipê usa la lista de Mozilla
  (certifi). Windows no cambia.

## 0.100.30 — macOS: hacer clic en el icono de la barra de menús ya no cierra el programa
- En macOS 27, hacer clic en el icono de Ipê en la barra de menús (junto al reloj) cerraba el programa — un defecto
  de Qt con ese sistema. En el Mac, Ipê ya no pone ese icono: el Dock cumple el mismo papel. Windows y Linux no cambian.

## 0.100.29 — El programa ya no se cierra solo con un archivo comprimido fuera de lo común
- Al abrir un estudio, Ipê podía **cerrarse solo** (visto en macOS): el decodificador GDCM termina todo el proceso
  cuando la cabecera DICOM no coincide con la imagen comprimida (filas, columnas, color). GDCM salió del programa;
  JPEG, JPEG 2000 y JPEG-LS quedan con pylibjpeg, CharLS y Pillow, que devuelven un error tratable — la imagen
  defectuosa aparece como error y el resto del estudio se abre. Vale para Windows, Linux y macOS.
- En el programa instalado, el último mensaje de una biblioteca antes de una caída también va a `queda.log`.

## 0.100.28 — macOS: el teclado llega al programa
- En el paquete de prueba de macOS no se podía escribir (por ejemplo, la dirección del servidor): la app estaba
  marcada como "solo de fondo", sin icono en el Dock. Corregido; Ipê ahora aparece en el Dock y recibe el teclado.

## 0.100.27 — La instalación de las IA en una ventana, con el avance y los errores
- **Instalar la segmentación** e **Instalar los modelos extra** se ejecutan en una ventana de Ipê: paso actual,
  tiempo, la salida completa con los errores en rojo y, al final, el veredicto verificado (instalado, con errores o
  no instalado). Copiar todo, Guardar y el registro en `instalacao_ia.log`. No bloquea el programa.
- Cuando el programa se cierra solo por un error de una biblioteca, queda el rastro en `queda.log`, en la carpeta
  de registros.

## 0.100.26 — Médula y canal: área y compresión por nivel (TotalSpineSeg)
- Botón **Médula** en la RM de columna: segmenta la médula, el canal, los discos y las vértebras y mide en cada
  disco, en el plano perpendicular a la médula, el área, el AP, el transverso, la razón de compresión, el canal, el
  MSCC y el MCC. Cada nivel es un hallazgo para revisar, con frase para el informe. También en la pestaña IA del
  navegador.
- Es un modelo extra (TotalSpineSeg), instalado en un entorno propio para no tocar TotalSegmentator: Configuración
  ▸ CAD/IA ▸ Instalar los modelos extra. Pide unos 8 GB de memoria libres.

## 0.100.25 — Lesiones de sustancia blanca en FLAIR (FLAMeS)
- Botón **Lesiones SB** en la RM de cráneo: marca las lesiones hiperintensas en FLAIR y da el número, el volumen
  total y el recuento por región (periventricular, yuxtacortical, infratentorial, profunda), con la comparación con
  el estudio anterior. Hallazgo para revisar, frase para el informe y las lesiones coloreadas por región. También en
  la pestaña IA del navegador.
- Es un modelo extra (FLAMeS, 2,4 GB): instalar en Configuración ▸ CAD/IA ▸ Instalar los modelos extra.
- BraTS y autoPET: la máscara ahora aparece en el estudio justo después de ejecutar, sin reabrirlo.

## 0.100.24 — macOS: paquete de prueba
- Primer paquete de Ipê para **macOS** (Ipe.app en un .dmg, para chip Apple y para Intel), generado aparte y aún
  fuera del release. Sin firma de Apple: la primera vez, abrir con clic derecho ▸ Abrir.
- En el Mac, el instalador de la segmentación se abre en Terminal y usa la carpeta Application Support.

## 0.100.23 — T1 sintético de 1 mm (SynthSR)
- **Índices ▸ Crear T1 sintético de 1 mm de esta serie (IA, SynthSR)…**: de una serie 2D del cráneo (cualquier
  contraste y espesor) sale una serie T1 isotrópica de 1 mm, en la misma posición del paciente, para el MPR, las
  medidas guiadas (MRPI) y los índices automáticos en los estudios sin T1 3D. También en la pestaña IA del navegador
  y en Configuración ▸ CAD/IA.
- Es una **imagen sintética**: sirve para medir la anatomía, no para buscar lesiones (el programa avisa y lo graba
  en el encabezado). Queda solo en este equipo.
- Sin TensorFlow: la red de SynthSR se reescribió en PyTorch y lee los pesos originales (53 MB, descargados una vez).

## 0.100.22 — Linux: instalar la segmentación en un sistema antiguo
- El instalador de la segmentación busca un **Python 3.10 o más nuevo** (Ubuntu 20.04 trae el 3.8, y pip no hallaba
  TotalSegmentator); si no hay, descarga un Python propio sin tocar el del sistema. El entorno hecho con un Python
  antiguo se rehace.
- En el paquete de Linux, la **terminal del instalador no abría** (gnome-terminal: "undefined symbol"): los
  programas externos ya no heredan las bibliotecas de Ipê.

## 0.100.21 — Navegador: línea de referencia y arrastre entre ventanas
- Con las ventanas vinculadas, el corte de una ventana aparece en las demás como **línea de referencia**
  (discontinua), en los cuadros de otro plano del mismo estudio.
- **Arrastrar una serie** de la tira de una ventana y soltarla en un cuadro de otra ventana, incluso de otro estudio.

## 0.100.20 — Navegador: lista con filtros rápidos y vista previa; ventanas vinculadas
- **Lista**: filtros de un clic (período, modalidad, situación del informe y de la IA), sellos de IA y de informe en
  cada estudio, y la **vista previa** del estudio seleccionado a la derecha (series, IA, informe, anteriores).
- **Ventanas vinculadas**: el desplazamiento, la ventana/nivel y el zoom de una ventana de visualización siguen en
  las demás (en el estudio anterior, por los mismos milímetros).

## 0.100.19 — Navegador: apariencia del usuario, modo lectura y configuración de monitores
- **Apariencia**: series a la izquierda, abajo o arriba; botones arriba o en una columna a la izquierda; **modo
  lectura** (solo imágenes, tecla F). El panel derecho viene plegado. Guardado en el navegador.
- **Monitores**: configuración guardada en el navegador, como en el Ipê — el orden de las ventanas, qué presenta cada
  una (el estudio o el estudio anterior), y el diseño y el monitor de cada una.

## 0.100.18 — Navegador: varias ventanas (una por monitor), móvil y tableta
- **Ventanas de visualización**: la lista en una ventana y los estudios en 1, 2 o 3 ventanas separadas, una por
  monitor, para cualquier estudio. Las ventanas quedan abiertas esperando el siguiente estudio y recuerdan su posición;
  en mamografía, la 2ª ventana es la segunda pantalla del protocolo.
- **Móvil y tableta**: lista en tarjetas, una imagen a la vez, paneles en cajones, barra desplazable; un dedo hace la
  función de la barra (desplazar cortes), dos dedos amplían y mueven.
- **Inicio de sesión en el móvil**: después de entrar volvía al inicio de sesión. La sesión ahora vive en la pestaña
  (sobrevive a las recargas que el móvil hace solo), el teclado ya no pone mayúscula en el usuario, y un fallo del motor
  de imágenes ya no impide entrar. Los errores del navegador van al registro del servidor.

## 0.100.17 — Mamografía en el navegador: el mismo zoom en toda la pila
- Al desplazarse a otra imagen de la incidencia (otra 2D, la tomo), el zoom no acompañaba, y al volver ya no era el
  de la apertura. El navegador no leía el tamaño del píxel de la mamografía (ImagerPixelSpacing; grupos funcionales en
  la tomo) y volvía a medir el encuadre en cada cambio, sumando error. Ahora el servidor informa el tamaño del píxel y
  el encuadre de apertura de la etapa (o su zoom manual) se aplica a cada imagen, como si estuvieran apiladas.
- Publicación en GitHub: acciones actualizadas (Node 24) y la versión solo se arma cuando llega el código nuevo.

## 0.100.16 — Navegador: revisar los hallazgos de IA
- **Hallazgos para revisar** en la pestaña IA del navegador (enfisema, nódulos, Genant, calcio, aorta, carga tumoral
  PET, composición corporal): Ir a, Confirmar, Corregir los números, Descartar, Volver a sugerido y **Enviar al
  informe** (solo los confirmados y corregidos). La misma lista del Ipê; requiere el permiso de escribir informes.
- "Ir a" y las líneas de referencia del navegador encuentran el corte correcto aunque la serie siga llegando.

## 0.100.15 — Navegador: Cerrar, la búsqueda vuelve, IA en la misma sesión
- Con el estudio abierto, el botón de la esquina superior es **Cerrar**; en la lista sigue siendo **Salir**.
- **La búsqueda vuelve**: cerrar el estudio vuelve a la lista con la búsqueda y los filtros que había, con el estudio
  abierto marcado.
- **IA en la misma sesión**: al terminar una tarea de IA, las series nuevas entran en la tira y la SEG en el menú (y
  se muestra si no había ninguna elegida), sin cerrar y abrir el estudio.

## 0.100.14 — IA visible en el navegador; sello IA en las miniaturas
- **Navegador:** los **niveles de la columna** y los **niveles ganglionares** pedidos desde la pestaña IA no
  aparecían (el overlay decía "Sin CAD/IA en este estudio"). Ahora los nombres aparecen en cualquier serie y plano,
  MPR incluido, como en el Ipê, en cuanto termina la tarea.
- **Overlay del navegador:** el ítem **CAD/IA (hallazgos, segmentaciones, niveles)** enciende y apaga solo la IA, y se
  recuerda de un estudio al otro.
- **Sello IA** en las miniaturas de las series (Ipê y navegador): en las series que son resultado de IA o que fueron
  analizadas por una, con las herramientas en la ayuda.

## 0.100.13 — Instalar la segmentación: Python descargado e idioma
- **El instalador de la segmentación fallaba** con "os error 448 (punto de montaje no confiable)" en algunos Windows:
  uv crea un acceso directo de carpeta al Python 3.12 que descarga, y Windows lo bloquea. Ahora el entorno se crea
  directamente desde el Python real (el acceso directo se borra); un Python ya descargado se reutiliza.
- El instalador habla el **idioma del Ipê** (inglés, español o portugués), y la pregunta "Instalar la segmentación"
  y otros mensajes armados por partes ahora salen traducidos.
- El paquete de Windows no llevaba algunas herramientas de IA (enfisema, Genant, aorta…), importadas por nombre: la
  pestaña IA del navegador quedaba vacía con error. Ahora van todas, y una herramienta con problemas no rompe la lista.

## 0.100.12 — Visor web: pestaña IA
- El CAD/IA del navegador pasó a ser la pestaña **IA** del panel derecho, como la de la película: todas las
  herramientas de IA del Ipê (primero las que sirven para el estudio, las demás con el motivo), la serie de cada una
  (la sugerida o la del cuadro activo) y **Ejecutar**; arriba, las tareas del estudio con el progreso y **Cancelar**.
  El botón de la barra e **IA** en el pie abren la pestaña.

## 0.100.11 — Visor web: armar el filme e imprimir
- Pestaña **Filme** en el navegador: los cuadros ajustados (ventana, zoom, desplazamiento, giro) van al filme (el
  cuadro, todos o la serie cada N); la vista previa la dibuja el servidor con el código del compositor de Ipê;
  editar, reordenar y quitar celdas; cuadrícula, papel, horizontal, textos, encabezado, anonimizar.
- **Imprimir**: descargar el PDF, imprimir en la computadora de quien usa el navegador, en las impresoras del
  servidor, en las impresoras DICOM y en los destinos de impresión de Ipê. Cuenta en el panel de filmes. Solo con
  permiso de imprimir.
- El servidor sin pantalla (`ipe server`) pasó a usar Qt de widgets (offscreen) para dibujar las hojas.

## 0.100.10 — Visor web: CAD/IA desde el navegador
- **CAD/IA en este examen** en el navegador: las herramientas de IA de Ipê que sirven para el examen, con la serie
  sugerida (o la del cuadro), ejecutándose en la cola de IA del servidor. **IA** en el pie muestra las tareas del
  examen (pedidas y automáticas) con la etapa y el tiempo, y cancela las suyas; al terminar, **Recargar el examen**
  trae las series nuevas.
- Permiso nuevo **Pedir CAD/IA a mano** (de fábrica: administrador y médico).

## 0.100.9 — Visor web: enviar a un destino DICOM
- **Enviar a un destino DICOM** desde el navegador: el examen, las series marcadas o la imagen del cuadro activo, a
  los nodos del servidor, por la cola de envíos del servidor (la misma de Ipê). Opcionalmente junto con las medidas
  (GSPS) y las imágenes clave (KO). **Envíos** en el pie muestra el avance y cancela. Solo para quien tiene permiso
  de enviar.

## 0.100.8 — PET por el borde (gradiente); retomar la sesión; movimiento en la dinámica web
- **PET: borde por el gradiente (como el PET Edge)** en Segmentar 3D: el contorno queda donde la señal cae más rápido,
  con la corrección del volumen parcial por la resolución del PET (medida en la propia lesión cuando es grande; el
  campo *Resolución del PET (FWHM)* en las pequeñas). En las esferas de prueba, ±15% del volumen real a partir de
  1,3 cm, contra el doble o más de error del 41% en las pequeñas. Avisa cuando la lesión está cerca del límite de
  resolución.
- **Retomar la sesión**: Ipê anota los exámenes abiertos y guarda el estado del análisis cada 2 minutos; después de
  una caída, ofrece reabrir lo que estaba abierto, como estaba (Configuración ▸ Visor ▸ Estado del análisis al abrir:
  preguntar, reabrir sin preguntar o no reabrir).
- **Visor web — corrección de movimiento en la dinámica de mama**: traslación o rígida, con el cálculo de Ipê hecho en
  el servidor; mapas, curvas, sustracciones y la fase que se movió salen corregidos.

## 0.100.7 — RM de mama: fibroglandular y realce de fondo; el fin de la lectura envía al PACS
- **Fibroglandular y realce…** (panel de la dinámica de mama): separa el tejido fibroglandular de la grasa en el T1
  sin saturación (o en el Dixon, o en la precontraste) y da, en cada mama, el porcentaje y el volumen; con la
  dinámica abierta, la mediana del realce del FGT en la primera fase y cuánto de él realza más del 20%. Quita piel,
  músculo y pared lateral del tórax, corrige el degradado de la bobina y deja un implante fuera del cálculo. **Copiar
  frases** para el informe y **Guardar la máscara (SEG)** para revisarla. Devuelve números, no categoría: la
  categoría queda con el médico.
- **Fin de la lectura** (Configuración ▸ Informes): al firmar el informe, el KO de las imágenes clave, el GSPS de las
  medidas, el informe de esta firma (PDF y SR) y las series de Ipê van solos al PACS elegido, por la cola de envíos —
  también cuando el informe se firma en el navegador. Ocultas, copias locales y series de otro equipo no van.

## 0.100.6 — Linux: paquete .deb e install.sh en el portátil
- **Paquete `.deb`** en el release (`Ipe-<versión>-linux-amd64.deb`, paquete `ipe-viewer`): `sudo apt install ./…deb`
  instala en `/opt/ipe`, con el comando `ipe-viewer`, el ícono y el acceso **Ipê** en el menú; `apt` trae las
  bibliotecas de ventana que falten. `sudo apt remove ipe-viewer` lo quita.
- **`install.sh` en el portátil**: instala para su usuario, sin administrador (programa, comando `ipe-viewer`, acceso
  e ícono en el menú); `--system` instala para todos en `/opt/ipe`; `--uninstall` lo quita. Ejecutar el de la versión
  nueva actualiza.
- Instalar, actualizar o quitar no toca los estudios, la base ni la configuración. El nombre es `ipe-viewer` porque
  `ipe` ya es otro programa en las distribuciones.

## 0.100.5 — visor web: doble clic amplía; "Salir" vuelve a la lista
- **Doble clic** en un cuadro lo amplía a 1×1; otro doble clic vuelve a la disposición anterior, cada cuadro como
  estaba (corte, zoom, ventana). Sobre una medida, el doble clic sigue siendo de la medida.
- **Salir**: con un estudio abierto, cierra el estudio y vuelve a la lista de estudios; en la lista, sale de Ipê Web.
- Cerrar o recargar la pestaña con un estudio abierto pide confirmación.

## 0.100.4 — visor web: lupa y pila alineada en mamografía; informe con BI-RADS, PDF/SR y búsqueda activa
- **Mamografía**: al pasar de la 2D a la tomosíntesis de la misma incidencia, la imagen nueva queda en la misma
  escala en mm y con la pared torácica en el mismo lugar (la tomo tiene otro tamaño y espaciado; antes la mama
  cambiaba de tamaño y se movía). Vale también con el zoom hecho a mano.
- **Lupa**: mantener el botón muestra los píxeles de la propia imagen aumentados alrededor del cursor, con la
  ventana del cuadro; la rueda cambia el aumento (1,5× a 8×). Botón en la barra de mamografía y herramienta en
  "Zoom y lupa".
- **Informe en el navegador**: el formulario **BI-RADS®** de Ipê (composición, hallazgos, categoría por mama,
  recomendación), con las mismas frases en el texto; **Descargar PDF** (el PDF de Ipê, con encabezado y firma); al
  firmar, el **PDF** y el **SR** guardados en el estudio y la **búsqueda activa** (BI-RADS 0 y 3), con los pedidos
  abiertos de la paciente arriba del informe.
- El servidor sin ventana (`ipe server`) inicia el Qt de interfaz sin pantalla, para generar el PDF.

## 0.100.3 — visor web: los botones del mouse vuelven a obedecer
- **Corregido**: después de cambiar la función de un botón (por ejemplo, la ventana en el derecho, que antes era
  zoom), el mouse seguía haciendo la función anterior — Cornerstone3D sumaba el botón nuevo a los anteriores y, al
  quitar una función, solo soltaba el botón izquierdo. Ahora cada cambio deja en cada botón exactamente la función
  elegida.
- **Corregido**: una medida empezada con un solo clic (la regla también dibuja en "clic, mover, clic") dejaba todas
  las herramientas paradas hasta terminar la línea. Ahora hacer clic en otro cuadro, cambiar de herramienta o pulsar
  Esc deshace la línea a medias, y no se guarda.

## 0.100.2 — visor web: overlay, líneas de referencia, PET ajustable, dinámica y mamografía como en Ipê
- **Overlay**: el ícono nuevo enciende y apaga de una vez el CAD/IA (SR), las anotaciones de otro sistema (GSPS),
  los contornos RTSTRUCT, los textos de las esquinas, las medidas y las líneas de referencia; la flecha elige ítem
  por ítem, y el tipo oculto sigue oculto en los próximos estudios. La SEG elegida aparece también en los cuadros
  de cortes.
- **Líneas de referencia en los cortes**: el plano del cuadro activo aparece como línea en los otros (el axial en el
  scout…); con la herramienta Líneas de referencia, hacer clic en un cuadro lleva los otros al corte del punto.
- **PET**: la ventana de SUV al arrastrar el mouse (tope y piso, en todos los cuadros del mismo PET; Shift en la
  fusión ajusta la TC) y la **disposición** elegida en la pestaña PET — la cuadrícula y lo que muestra cada cuadro
  (TC + PET, TC, PET, MIP del PET) con el plano —, recordada para el próximo PET/CT.
- **Dinámica de mama**: la **curva bajo el cursor** (3×3, como en Ipê) y la curva del punto (valor del píxel); en la
  etiqueta de cada cuadro, ◂ ▸ cambian de fase y el menú elige la fase, la **sustracción** de cualquier fase, el
  **paisaje** (anatomía de vuelta) y el **color**; la barra elige el color del mapa sobre la fase.
- **Mamografía**: cada cuadro es la pila de la incidencia, como en Ipê — la rueda pasa por las imágenes 2D de la
  misma mama e incidencia y por los cortes de la tomosíntesis.
- **Lista de estudios**: hacer clic en el título de la columna ordena (▲/▼), y la elección queda recordada.

## 0.100.1 — cliente del servidor central: la descarga ya no se detiene al abrir el examen
- **La descarga se detenía justo después de abrir el examen**: cuando las primeras imágenes tardaban más de 0,4 s
  (una red real), cerrar el aviso "Descargando las primeras imágenes…" se leía como "Cancelar" — solo terminaban
  las series que ya estaban llegando, y las demás quedaban con una imagen. Ahora solo el botón Cancelar detiene la descarga.
- **Señal de la red** en la barra de estado del cliente: barras (como las del móvil), ida y vuelta en ms y caudal en
  Mbit/s hasta el servidor. Se mide al abrir el programa y en cada examen abierto (ahí solo la ida y vuelta; el
  caudal pasa a ser el de la propia descarga); haga clic para medir de nuevo.
- Una serie que falla ya no es silenciosa: la barra de estado dice cuántas imágenes faltaron y por qué.
- El cliente envía al registro de acceso del servidor su versión al entrar y, al final de cada descarga, cuántas
  imágenes llegaron, en cuánto tiempo, lo que faltó (por serie) y los errores — se puede verificar desde el servidor.
- Los comentarios del examen vuelven a aparecer en el cliente (el servidor respondía con error).

## 0.100.0 — cliente del servidor central: cuánto llegó de cada serie, y menos datos en la red
- La tira muestra, en cada serie, cuántas imágenes ya llegaron (*34/120 im*) con una barra, y ⬇ en la que está
  llegando; el cuadro muestra **⬇ 34/120** hasta que su serie termina; la barra de estado gana el porcentaje.
- Poner una serie en un cuadro la pasa al frente de la descarga.
- Dos series se descargan a la vez, y la entrada en la base corre en un hilo aparte (la red ya no se detiene
  mientras el lote entra en la base).
- **HTJ2K sin pérdida en la red**: el servidor envía al cliente una copia de envío (verificada píxel a píxel; el
  acervo no cambia), de 2 a 4× menos datos. Las copias de los exámenes de los últimos 14 días quedan listas en
  segundo plano; la imagen sin copia lista va como está. El cliente decodifica con OpenJPH (imagecodecs, ~1 ms por
  corte de TC). Configuración ▸ Red ▸ Servidor central lo activa y desactiva.
- Enviar a un nodo DICOM que no acepta la sintaxis del archivo (HTJ2K, JPEG-LS) ahora va descomprimido.
- Visualizador web: cambiar el layout o la etapa mientras una imagen cargaba a veces rompía la página; y el paquete
  del sitio ya no depende del orden de los módulos (un error de carga que aparecía al cambiar el código).
- Medido en un examen de 720 imágenes con las copias listas: en una red de ~100 Mbit/s, 4,9 s con HTJ2K contra
  16,8 s sin; en 1 Gbit/s, 2,6 s contra 2,9 s.

## 0.99.99 — visualizador web: las series siguientes empiezan enseguida
- El navegador pide los metadatos de todas las series juntos (tres a la vez), en lugar de uno tras otro; los
  cuadros entran en la cola en el orden de la tira apenas llega cada serie.
- El servidor lee los encabezados en paralelo, guarda la respuesta (reabrir es inmediato; cambia si cambia el
  archivo) y lee el examen entero apenas se pide la primera serie.
- Las copias de envío (HTJ2K) de la serie las hace un solo trabajador, en cola, y esperan mientras se piden
  cuadros — antes, cada serie abierta competía por el procesador con las imágenes que el navegador esperaba.
- En un examen de prueba con 6 series de 120 cortes, la última serie empezaba a bajar a los 12,7 s; ahora, a los 3,3 s.

## 0.99.98 — visualizador web: mamografía con una y dos pantallas, dinámica de mama e informe
- **Mamografía** en el protocolo del Ipê: etapas (4 incidencias, CC, MLO, actual × anterior…), la imagen de cada
  cuadro y el examen anterior por las mismas reglas, mamas espalda con espalda (volteadas cuando hace falta), la
  mama encuadrada sin el aire, pared torácica contra el borde, mismo zoom y pezones a la misma altura; doble clic
  amplía; tomosíntesis por cuadro.
- **Dos pantallas**: una segunda ventana (en el otro monitor cuando el navegador lo permite) con la otra mitad de la
  etapa, sin pedir la contraseña; las dos cambian de etapa juntas.
- **Dinámica de mama**: fases encontradas como en el Ipê; mapa cinético, SER, MSI, PEI, realce inicial,
  sustracción, TTP y MIP/media temporales **calculados en el navegador** con las fórmulas del Ipê; un mapa
  (calculado o ya guardado por el Ipê) sobre la fase; **curvas tiempo-intensidad** de las ROI con la clase, el SER y
  los descriptores.
- **Informe en el navegador**, en el mismo registro del Ipê: plantilla sugerida con los campos automáticos,
  hallazgos de IA revisados en el cursor, borrador (con guardado automático), firmar y liberar, rectificar, y el
  bloqueo de quién está informando (solo leer o asumir; el servidor rechaza guardar por quien no tiene el bloqueo).

## 0.99.97 — visualizador web: interfaz nueva (estilo Weasis)
- **Barra de íconos** y **cada botón del ratón con su función, como en el Ipê**: hacer clic en el ícono con el
  botón izquierdo, el central o el derecho da la función a ese botón; la marca debajo del ícono (izquierda, centro,
  derecha) muestra cuál. La elección queda guardada.
- **Menú del botón derecho** en la imagen (clic y soltar; clic y mantener hace la función del botón): ventana,
  zoom, girar y voltear, plano, funciones de los botones, serie, cuadros y cine, borrar medidas, restaurar; sobre
  una medida, copiar el valor y borrarla.
- **Paneles plegables**: series y estudios anteriores a la izquierda; pestañas **Imagen**, **Medidas**, **DICOM**
  (tags con filtro) y **PET** a la derecha. Layout de 1×1 a 4×4 en una cuadrícula, y pie con carga y funciones de
  los botones.

## 0.99.96 — visualizador web: carga más rápida
- Las imágenes van al navegador en **HTJ2K sin pérdida** (copia de envío verificada píxel a píxel, en caché; el acervo
  no cambia): de 2 a 5 veces menos bytes en una TC, decodificación rápida y **carga progresiva**.
- **Volumen intercalado** (el MPR aparece pronto y se completa), **caché del navegador** con revalidación (reabrir
  casi no usa la red), decodificación en todos los núcleos menos uno y metadatos comprimidos.
- **Carga** (barra): MB por la red, MB/s, tiempo de decodificación por imagen, formato y lo que vino de la caché.

## 0.99.95 — visualizador web: arrastrar series e imágenes disponibles
- **Arrastrar la serie** de la tira hasta cualquier cuadro del visualizador web (el clic sigue poniéndola en el cuadro
  activo).
- **Imágenes disponibles**: al abrir el examen, el navegador descarga las series en segundo plano (las de los cuadros
  primero); cada miniatura muestra el porcentaje listo y la parte superior, el total del examen. Con la memoria llena,
  la precarga se detiene.

## 0.99.94 — visualizador web: PET/TC (fase 4)
- **PET/TC** en el visualizador web: fusión (TC + PET), PET en grises invertidos y el MIP del PET, con los axiales
  moviéndose juntos y un clic en el MIP llevando los cortes al punto más brillante.
- El PET llega **en SUV con el cálculo del Ipê** (peso, dosis y horarios); la ROI y el valor del píxel en el PET
  muestran SUVmáx y SUVmed como en el Ipê.
- **Color de la fusión** con las tablas del Ipê, **opacidad** y **tope de la ventana de SUV**; por debajo del 8% del
  tope no se pinta.
- **SUV máximo cerca del cursor** (esfera de 3 cm) lleva los cortes al vóxel más caliente.
- Las **segmentaciones (SEG)** del examen — carga tumoral, órganos, lesiones de la IA — como máscaras con los colores
  del Ipê.

## 0.99.93 — visualizador web: medidas en la base y calibración del ultrasonido (fase 3)
- **Medidas en el visualizador web**: regla, ángulo, Cobb, ROI elíptica, rectangular y libre, píxel, flecha y
  calibración. El número es el del Ipê (misma escala, misma regla de la ROI, mismo texto).
- Las medidas quedan **en la base del servidor**, en el formato del Ipê, con quién midió: lo que se mide en el
  navegador aparece en el Ipê y viceversa. Mover una punta la actualiza; clic en la medida y en **Borrar medida** la
  borra.
- **Ultrasonido**: la distancia usa la región calibrada del equipo (cruzar dos regiones queda en píxeles); la
  **calibración** manual vale para esa imagen (en las otras modalidades, para la serie).
- Corrección: al cambiar la grilla de cuadros, la imagen podía aparecer diminuta en una esquina.

## 0.99.92 — visualizador web: MPR, oblicuo y MIP (fase 2)
- Cada cuadro del visualizador web ganó **A, C, S, MIP y Original** arriba: cambia el plano con un clic,
  reconstruyendo la serie en el navegador.
- **MPR** (barra): axial, coronal, sagital y el MIP girando, con las líneas de referencia — arrastrar el centro lleva
  los planos al punto; girar una línea hace los oblicuos.
- **Oblicuo por dos puntos**, **espesor** (3 a 20 mm en MIP, MinIP o media) y **MIP girando** (botón o rueda del
  mouse); un clic en el MIP lleva los cortes al punto más claro.
- La serie que no forma volumen sigue en cortes, con el motivo; los volúmenes de más de 1,5 GB no se montan.

## 0.99.91 — visualizador web en el servidor central (fase 1)
- El servidor central trae un **visualizador en el navegador** en `http(s)://servidor:8043/web/` (Chrome o Edge),
  con el mismo login del Ipê: lista de estudios con búsqueda y filtros, tira de series con miniaturas, cuadros de
  1×1 a 2×3, ventana, mover, zoom, desplazamiento, cine, invertir y las ventanas predefinidas del Ipê. Hecho con
  Cornerstone3D.
- Las imágenes van como están en el banco: JPEG-LS, JPEG 2000 y JPEG se decodifican en el navegador; la mamografía
  usa la ventana del equipo (incluso la sigmoide de GE).
- Nada del paciente queda grabado en el navegador; cada apertura entra en el registro de acceso. La dirección
  aparece en Configuración ▸ Red ▸ Servidor central.
- En el servidor: metadatos y cuadros del DICOMweb (WADO-RS), miniatura de la serie y encabezados de seguridad.

## 0.99.90 — diámetro de la aorta por segmento
- **Aorta** (botón **Aorta**, o Aplicaciones ▸ Aorta) en la TC de tórax o de abdomen, con o sin contraste:
  TotalSegmentator halla la aorta y los reparos; el programa traza la línea central y mide, en planos perpendiculares
  cada 2 mm, el diámetro máximo y el perpendicular. Sale el mayor de cada segmento — raíz, ascendente, arco,
  descendente torácica, abdominal suprarrenal e infrarrenal —, de pared externa a externa, con la referencia como
  texto (ACC/AHA 2022; aneurisma infrarrenal ≥ 30 mm y el control del ACR 2013). Un hallazgo por segmento y la SEG
  con un color por tramo.

## 0.99.89 — puntaje de calcio coronario (Agatston)
- **Calcio coronario** (botón **Calcio**, o Aplicaciones ▸ Calcio coronario) en la TC sin contraste: TotalSegmentator
  halla el corazón, la aorta y los huesos; alrededor del corazón, el calcio ≥ 130 HU se puntúa por Agatston corte a
  corte (cortes finos sumados en láminas de 3 mm), con el volumen y el vaso sugerido de cada lesión (TCI, DA, CX, CD).
  Sale el total, el **CAC-DRS** y la categoría de la SCCT/STR; la aorta y lo que está dentro del corazón (válvula,
  anillo mitral) salen aparte. Un hallazgo por vaso: corregirlo o descartarlo cambia el total del informe. Con
  contraste el puntaje no se mide.
- Corrección: la SEG de la carga tumoral en el PET (0.99.88) no aparecía sola en la pestaña después del cálculo y no
  se trataba como serie de la propia computadora.

## 0.99.88 — PET: carga tumoral (FDG, PSMA, DOTA), lectura PET y SUV por la glucemia
- **Carga tumoral en el PET** (botón **Carga**, o Aplicaciones ▸ Carga tumoral): TotalSegmentator halla los órganos
  en la TC del PET/TC; en el PET, los focos sobre el umbral del trazador (FDG: PERCIST; PSMA: SUV 3; DOTA: hígado)
  fuera de la captación fisiológica pasan a ser hallazgos, con volumen, SUVmáx/medio/peak, TLG y región (próstata,
  hueso, ganglio pélvico o extrapélvico, víscera). Sale el MTV y la TLG totales; en el PSMA, el **miTNM** (PROMISE) y
  el puntaje **miPSMA** de cada foco. Descartar un foco en Hallazgos lo quita del total del informe. La máscara queda
  en una SEG sobre el PET.
- **Lectura PET** (botón Fusión): fusión, PET y MIP girando en tres cuadros; un clic en un foco del MIP lleva los
  cortes hasta él. **Ir al SUV máximo cerca del cursor (3 cm)**.
- **Glucemia** en la ventana PET…: queda guardada en el estudio, entra en el Q.Check (aviso sobre 200 mg/dL) y las
  medidas en el PET muestran también el SUVglu (SUV × glucemia ÷ 100).

## 0.99.87 — guía del usuario con pantallas del programa
- La guía en PDF ganó 19 figuras: banco de datos, visor con la segmentación de IA, barra de herramientas, layout,
  medidas, MPR, 3D (MIP del PET), mamografía y tomosíntesis, RM de mama y la ventana de la dinámica, anteriores,
  fusión PET/CT, niveles de la columna, Estructuras, exportar y las configuraciones (barra, red, servidor central).
- Las pantallas usan estudios reales anonimizados (pacientes EXEMPLO, fechas desplazadas, UIDs nuevos, sin
  institución ni tags privadas) y se rehacen en cada versión con el script `tools/guia/capturas.py`, que abre el
  programa sin ventana y fotografía cada pantalla. El generador de la guía acepta `![leyenda](archivo.png)`.

## 0.99.86 — apertura más rápida (JPEG-LS) y cronómetro de la apertura en el registro
- Las imágenes en JPEG-LS (la compresión sin pérdida de Ipê; toda la mamografía guardada) pasan a decodificarse
  con pyjpegls (CharLS) en vez de gdcm: en una mamografía 2850×2394 de su banco, 122 ms en vez de 280 ms, y los
  cuadros decodifican en paralelo.
- Los decodificadores y módulos que el primer estudio cargaba en el momento se cargan unos segundos después de
  abrir el programa.
- Cada apertura deja en el registro el tiempo hasta la primera imagen, por etapa (banco, barra, tira, protocolo,
  ventana, estado, imagen), y cuándo terminan de entrar las superposiciones de IA.
- Release: sale solo el `-installer.exe` (terminó la copia `-instalador.exe` de la transición).

## 0.99.85 — el cliente del servidor central abre el estudio mientras descarga; instalación en Linux
- En modo cliente, un estudio que aún no estaba en la computadora solo abría después de descargar todas las
  imágenes. Ahora llega primero una imagen de cada serie (el estudio abre con la tira completa y el protocolo arma
  los cuadros) y el resto de cada serie llega en segundo plano, en lotes; los cuadros crecen solos. La barra de
  estado muestra "N de M imágenes", y el registro anota el estudio y el total a descargar.
- `instalar.sh`: se detiene con un mensaje claro en Linux antiguo (glibc < 2.34), elige un Python 3.10+ del
  sistema en vez del de Anaconda (y rehace un `.venv` antiguo) e instala las bibliotecas de la ventana que faltan
  (`libxcb-cursor0`…).

## 0.99.84 — apertura más rápida de los estudios con SEG de IA
- La SEG de órganos del TotalSegmentator (miles de cuadros) se leía en la pantalla principal en cada apertura y
  trababa el estudio por segundos. Ahora los cuadros salen directo de los bytes del archivo (2–5× más rápido), las
  SEG grandes se leen en segundo plano (la imagen aparece antes) y lo ya leído queda en memoria: reabrir el estudio
  es inmediato.
- El dibujo solo pasa por las máscaras cerca del corte actual, en vez de todas en cada pintura.
- Medido en un estudio de 300 cortes con SEG de 60 estructuras: apertura de 6,2 s a 1,4 s; reapertura de 2,2 s a
  0,2 s.

## 0.99.83 — MedSAM2, autoPET y BraTS (modelos extra)
- **Segmentar por la caja (MedSAM2)**: herramienta del botón izquierdo; la caja en un corte se vuelve máscara 3D,
  propagada hacia arriba y hacia abajo, y abre en la ventana de Segmentación 3D (volumen, ejes, SUV, lesión, SEG).
- **autoPET**: lesiones en el PET-FDG por el nnU-Net de autoPET II, con la TC del PET/CT remuestreada en el PET;
  MTV, TLG, SUVmáx y cada lesión como hallazgo.
- **BraTS**: glioma en la RM (T1 poscontraste, T1, T2, FLAIR registradas y sin cráneo), SegResNet de MONAI;
  volúmenes de la parte captante, necrosis y edema.
- **Configuración ▸ CAD/IA ▸ Instalar los modelos extra…**: instala los tres en el entorno de la segmentación y
  muestra lo que ya está listo.

## 0.99.82 — estructuras en el 3D y lesiones hepáticas por segmento
- **3D ▸ Estructuras**: las segmentaciones del examen (órganos de la IA, lesiones, nódulos, SEG/RTSTRUCT) aparecen
  como superficies de color, junto con el hueso del VR o sobre el MIP, y acompañan giro, cortes y escultura.
- **Lesiones hepáticas** (TC y RM): tareas abiertas `liver_lesions` y `liver_segments` de TotalSegmentator; volumen,
  diámetro axial mayor y segmento de cada lesión, y la carga tumoral (% del hígado) total y por segmento de Couinaud.
  Cada lesión es un hallazgo revisable.

## 0.99.81 — nombres de los paquetes en inglés
- Los archivos del release pasan a llamarse `Ipe-<versión>-installer.exe`, `-windows-portable.zip` y
  `-linux-portable.tar.gz`. La actualización por GitHub encuentra los nombres nuevos y los antiguos.
- Transición: el release trae también `Ipe-<versión>-instalador.exe` (el mismo instalador), para que las versiones
  0.99.70 a 0.99.80 se actualicen con un clic.
- Este release reúne la 0.99.79 (un solo Ipê por usuario) y la 0.99.80 (altura y peso en la composición corporal y
  el resultado de la esteatosis).

## 0.99.80 — peso y altura en la composición corporal, y el resultado de la esteatosis
- Al hacer clic para calcular la composición corporal, una ventana muestra altura, peso y sexo del archivo para
  revisar o ingresar (vale para el examen; el archivo no cambia). En Hallazgos de IA, **Altura y peso…** los cambia
  después y recalcula el índice muscular, el IMC y las referencias sin ejecutar la IA.
- Con el peso: IMC y las referencias de Martin et al. (J Clin Oncol 2013) de sarcopenia y mioesteatosis.
- La atenuación hepática tiene ahora un **resultado** en texto (Park 2006, Pickhardt 2012): compatible con
  esteatosis moderada a grave, posible esteatosis leve (hígado/bazo < 1,0), sin signos, o no clasificado con
  contraste. Va al informe y acompaña la corrección de los números.

## 0.99.79 — un solo Ipê
- Hacer clic de nuevo en el acceso directo (o en un enlace ipe://) ya no abre otra copia: la que ya está abierta
  pasa al frente, también desde la bandeja o el inicio de sesión. El bloqueo es por usuario y se suelta solo si el
  programa se cae.

## 0.99.78 — menús del botón derecho más limpios e íconos de las aplicaciones de IA
- **Cuadro**: arriba, solo lo que depende del lugar del clic (medida, nódulo, hallazgo BI-RADS, eje de simetría,
  DSA); después imagen clave y copiar; **Imagen ▸** (ventana, color, invertir, filtro, girar, mosaico,
  histograma), **Cuadro ▸** (fusionar, líneas de corte, sincronización, cine), **Anotaciones ▸**, **Herramienta
  del botón izquierdo ▸** (Navegar, Medir, Dibujar) y las etiquetas; lo que borra queda al final. El color muestra
  los más usados de la modalidad y *Más colores ▸*. La segmentación salió del botón derecho (queda en los botones;
  *Identificar vértebras y discos* pasó a la flecha del botón Genant). DSA solo en angiografía; eje de simetría en
  la RM de mama o con ROI en el corte.
- **Banco**: Abrir e Informe arriba; **Organizar ▸** (listas, prioridad, subespecialidad, estado, comentario,
  banco), **Documentos ▸**, Enviar/Exportar, **Herramientas ▸** (anonimizar, corregir etiquetas, borrar implante
  solo en mamografía); Proteger y Quitar protección son un solo ítem.
- **Íconos**: cada aplicación de la barra tiene su dibujo (nódulos, enfisema, composición, hígado, órganos,
  Genant, ganglios, cefalometría, índices, difusión), con un ✦ dorado en las que usan IA.

## 0.99.77 — enfisema por lóbulo y fractura vertebral (Genant)
- **Enfisema** (TC de tórax): %LAA−950, Perc15 y volumen por lóbulo, por pulmón y en total, con la distribución
  (superior, inferior u homogénea); avisos de corte grueso, filtro duro, contraste y calibración del aire
  (tráquea). Las áreas por debajo de −950 HU en una SEG solo de la serie calculada.
- **Genant** (TC o RM de columna): altura anterior, media y posterior de cada cuerpo vertebral y la pérdida de
  altura (cuña, bicóncava, aplastamiento), con el grado de Genant de T4 a L5.
- Los dos resultados entran en Hallazgos de IA para revisar; solo lo confirmado va al informe.

## 0.99.76 — mamografía: el doble clic encuadra bien
- En el 1×1 del doble clic en una incidencia, la mama quedaba alta y con parte oculta: el zoom y la alineación
  por el pezón venían de los cuadros ocultos. Ahora el cuadro ampliado se encuadra solo, para su tamaño.

## 0.99.75 — cambiar la carpeta de la base sin el "WinError 32"
- **Mover los archivos** (Configuración ▸ Base de datos ▸ Cambiar la carpeta de la base) fallaba en Windows con
  *WinError 32* (la base abierta por los servicios de fondo) y dejaba el programa en la carpeta nueva con solo
  parte de la base. Ahora el cambio se hace en la próxima apertura, antes de abrir la base; si algo falla, lo que
  ya se había movido vuelve y el programa sigue en la carpeta anterior.

## 0.99.74 — HTTPS en la red interna, con certificado del propio Ipê
- **Servidor central ▸ Generar certificado para la red interna…**: Ipê crea una AC interna del servicio y el
  certificado del servidor (nombre e IP del equipo), y el servidor pasa a usar HTTPS.
- **Cliente ▸ Confiar en el certificado de este servidor…**: descarga la AC del servidor, muestra la huella digital
  para comprobar y pasa a exigir HTTPS comprobado con ella. **Guardar la AC (.crt)** para instalar en Windows
  (navegador y otros visores DICOMweb).
- Nueva dependencia: cryptography.

## 0.99.73 — Configuración: la ventana del grupo
- Hacer clic en el nombre de un grupo del menú Configuración (Visualizador, Protocolos de examen, CAD/IA,
  Informes…) abre una ventana con todos los pasos de ese grupo en una lista a la izquierda. El ítem del submenú
  sigue abriendo solo ese ítem, y *Todas las preferencias* sigue abriendo todo.

## 0.99.72 — el instalador avisa del Visual C++
- El instalador de Ipê comprueba si existe el Microsoft Visual C++ Redistributable (x64) y, si falta, ofrece abrir
  la descarga de Microsoft. Solo la segmentación (PyTorch) lo necesita; Ipê y Python no. *Instalar la
  segmentación* avisa lo mismo antes de abrir.

## 0.99.71 — instalador de la segmentación: Visual C++ de PyTorch
- `instalar_segmentacao.bat` comprueba que PyTorch abra. Si no abre (*WinError 126 … shm.dll*, común en Windows
  Server y en Windows recién instalado), descarga e instala el Microsoft Visual C++ Redistributable y comprueba
  de nuevo, con un mensaje claro si aún hace falta reiniciar.

## 0.99.70 — versión nueva desde GitHub, con un clic
- Al abrir (una vez al día) y en **Ayuda ▸ Buscar versión nueva (GitHub)…**, Ipê busca el último release. En
  Windows instalado, **Descargar e instalar** descarga el instalador, comprueba el SHA-256, cierra, instala sin
  preguntas y abre la versión nueva. En la versión portátil y en Linux, descarga el paquete y abre la carpeta.
  *Saltar esta versión*, y **Ayuda ▸ Avisar cuando salga una versión nueva** para desactivarlo.
- La actualización sin preguntas (desde GitHub o desde el servidor central) ya no vuelve el modo de uso a "solo
  yo" ni el idioma al inglés, y el instalador abre el programa al final.

## 0.99.69 — instalador de la segmentación: encuentra el Python correcto
- `instalar_segmentacao.bat` comprueba que cada Python **abra de verdad** y responda (antes, un Python roto o un
  comando inexistente podían pasar), lista los Python del equipo e ignora PYTHONHOME y PYTHONPATH de Windows, que
  rompían cualquier Python con *No module named 'encodings'*.
- Un entorno antiguo que no abre se borra y se rehace (o se renombra, si la carpeta está bloqueada). Si el Python
  del equipo no sirve, se descarga un 3.12 solo para la segmentación. Mensaje de red más claro.

## 0.99.68 — exportar e importar la configuración
- **Configuración ▸ Sistema ▸ Exportar la configuración…** e **Importar configuración…**: un archivo `.ipeconfig`
  que va de Windows a Linux y al revés. Lleva la configuración del equipo y la personal, protocolos, plantillas de
  informe y de hoja, perfiles, SLA, búsqueda activa, nodos DICOM, identidades AE, automatización y traducciones.
- No lleva lo que es de cada equipo (base, monitores, inicio de sesión, título AE, token, servidor/cliente,
  ventanas) ni las carpetas del otro sistema. Contraseñas solo si se marca. El mismo nombre se actualiza, no se
  duplica; antes de importar queda una copia de la configuración actual.

## 0.99.67 — el instalador pregunta la carpeta del programa y la de la base
- El instalador de Windows pregunta siempre la **carpeta del programa** y la **carpeta de la base de datos** (en
  una actualización, ya rellenadas con las anteriores). No acepta Archivos de programa (instala sin administrador)
  ni la base dentro de la carpeta del programa. Una base con estudios no se cambia por una carpeta vacía: el
  instalador avisa y el programa la mueve, en Configuración ▸ Base de datos.
- Línea de comandos: `ipe-cli set-data-dir CARPETA`.
- La guía explica cómo desinstalar (Aplicaciones instaladas de Windows) y qué queda en el equipo.

## 0.99.66 — importar RAR, 7z y otros comprimidos
- **Archivo ▸ Importar comprimido (ZIP, RAR, 7z)…** y el arrastre ahora también abren RAR, 7z, TAR (gz/bz2/xz),
  ISO y CAB. RAR, 7z e ISO usan 7-Zip, si está instalado, o el tar que ya trae Windows 10/11; WinRAR también
  sirve para RAR.
- Los ZIP en Deflate64 (los que Windows hace con archivos grandes) ahora abren con 7-Zip o con el tar de Windows.
- Comprimido en partes (.part1.rar, .7z.001): basta enviar todas las partes, o solo la primera. Un comprimido
  dentro de otro también abre. Un archivo con contraseña avisa, en vez de trabarse.

## 0.99.65 — órganos abdominales y niveles ganglionares solo en la serie calculada
- La segmentación de los órganos abdominales y el mapa de los niveles ganglionares aparecen solo en la serie en
  que se calcularon (y en sus reconstrucciones), ya no en todas las series del examen, donde caían fuera de lugar.

## 0.99.64 — mama: fusión por arrastre, mapas en color, hallazgos por marcadores
- **Fusionar por arrastre**: soltar la serie en la esquina "Fusionar encima" del cuadro; y clic derecho ▸
  Fusionar este cuadro sobre… para cualquier mapa de la dinámica, fase o ADC sobre otro cuadro.
- **Mapas en color** en la dinámica: *Tiempo en color* (color = tiempo hasta el pico, brillo = realce) y *Fases en
  color* (RGB = inicial, intermedia, tardía).
- **Hallazgos BI-RADS por marcadores** en la mamografía: marcar en la CC y la MLO, tabla con distancia al pezón,
  cuadrante, hora y tercio, y enviar al informe BI-RADS.

## 0.99.63 — estado del examen
- Columna **Estado** en la base: no leído, en lectura, urgente, revisado — automática, por el acceso, el informe y
  la prioridad; se cambia a mano con clic derecho (✎), filtros en **Trabajo ▾** y la acción "marcar como revisado"
  en el visor.

## 0.99.62 — nódulo pulmonar completo
- **Nódulo por clic** en la TC (clic derecho ▸ Nódulo pulmonar aquí): segmentación por umbral, separada de los
  vasos y la pleura, con vidrio esmerilado opcional; los mismos números de la IA; guardar como hallazgo confirmado
  o seguirlo ya como lesión.
- **El mismo nódulo en el examen anterior** (por el registro, o probable por lóbulo y distancia): crecimiento del
  diámetro medio y del volumen y tiempo de duplicación, en la ventana, en la lista de Hallazgos y en el informe. La
  medida nueva entra en la lesión que ya se seguía.

## 0.99.61 — ronda de mama P2
- **Alineación por el pezón** en la mamografía: en la misma fila de la pantalla, las dos mamas con el pezón a
  la misma altura (opción del protocolo; "por el centro de la mama" como antes). **Zoom y pan** reflejados
  ahora también en la barra.
- **Invertir solo la mama**: tejido invertido, fondo negro, en todos los cuadros.
- **★ Corte**: el corte de la tomosíntesis como imagen clave, con el número del corte; atajos para ir al
  siguiente y al anterior marcados.
- Cuadros **US** y **RM** en el protocolo de la mamografía: la última ecografía y la última RM del paciente
  (`RM:T2` elige la serie).
- **Eje de simetría a mano** para la ROI reflejada (clic derecho ▸ Eje de simetría).

## 0.99.60 — PET en el seguimiento (ítem 7, parte 2)
- **SUL** (masa magra de Janmahasatian) guardado en cada medida de PET; el PERCIST usa el SULpeak.
- Botón **PET…** en el panel de lesiones: referencia del **hígado** (esfera de 3 cm, por clic o automática
  por la segmentación del hígado) y del **mediastino**, **umbral del PERCIST** (1,5 × hígado + 2 DE), aviso
  de hígado no comparable entre exámenes.
- Criterio **Deauville / Lugano**: puntuación propuesta por lesión y por examen (se cambia con clic derecho)
  y la respuesta metabólica.
- **Q.Check** del encabezado del PET, en el examen y contra el de base (captación, peso, dosis, unidad,
  correcciones, reconstrucción, equipo).

## 0.99.59 — seguimiento entre fechas (ítem 7, parte 1)
- **Vínculo por posición**: la medida hecha en el examen de seguimiento en el lugar de una lesión (hasta
  10 mm, llevada al anterior por el registro) se vincula sola a ella. Sin registro, o con dos lesiones cerca,
  no se vincula.
- **Seguimiento…** en el panel de lesiones: las lesiones aún sin medida en este examen, una a una —
  **repetir** la medida en el lugar estimado (contorno anterior en sombra), **demasiado pequeña** (5 mm),
  **ausente**, estable o progresión.
- **Nadir** en el panel (fila y marca ▼) y las cuatro fechas (base, nadir, anterior, actual) en el resumen.

## 0.99.58 — estado guardado del análisis
- El examen **se reabre como lo dejó**: diseño, series, corte, ventana, zoom, desplazamiento, giro, colores,
  cuadro activo, anteriores (vinculados de nuevo), paneles y los parámetros de la dinámica (se vuelve a encender
  con un clic). Por usuario, solo en Ipê (en el servidor central para todas las estaciones).
- **Ver ▸ Estado del análisis**: reabrir, volver al de fábrica, usar el montaje del examen anterior o abrirlo al
  lado como estaba. Configuraciones ▸ Visor ▸ Estado del análisis al abrir.

## 0.99.57 — PDF e imágenes adjuntos al examen
- Arrastrar un **PDF** o una **imagen** sobre el examen abierto, o en la base de datos con un examen
  seleccionado (con confirmación), o clic derecho ▸ **Adjuntar documento…**: se vuelve DICOM dentro del examen
  (PDF encapsulado o imagen de captura secundaria) y sigue las reglas de enrutamiento del examen. Otros
  formatos: guárdelos como PDF.
- **Documentos del examen…**: los PDF del examen se abren dentro del programa.

## 0.99.56 — perfiles por grupo y computadora y actualización por el servidor (ola B2 y B1)
- **Perfiles por grupo y computadora** (Configuraciones ▸ Usuarios): preferencias enviadas por el servidor
  por computadora (con comodín), usuario o perfil de acceso; captura de la computadora configurada; claves
  forzadas.
- **Actualizaciones por el servidor central** (Configuraciones ▸ Red): publicar el instalador en los canales
  prueba y estable, promover y retirar; el cliente avisa al entrar, descarga, revisa el SHA-256 e instala con
  un clic.

## 0.99.55 — OAuth2/OIDC en los nodos DICOMweb y contraseñas cifradas (ola B3)
- Nodo DICOMweb con **OAuth2**: credenciales del cliente, usuario y contraseña (Keycloak) o token fijo; la
  dirección del token puede ser la del emisor OIDC (descubrimiento automático); token renovado solo y un nuevo
  intento en el 401.
- **Contraseñas cifradas**: la contraseña, el token y el secreto del cliente quedan cifrados en la base (DPAPI
  en Windows; clave local en los otros); las antiguas en texto claro se cifran en la primera lectura.

## 0.99.54 — IA en el texto del informe (ola B5)
- Botón **IA ▾** en el informe: **revisión local** (sin red; campo vacío, medida sin unidad, lateralidad,
  sexo × órgano, BI-RADS del texto × formulario, conducta × categoría, impresión vacía), también **antes de
  firmar**; y, con un modelo configurado (Ollama, servidor compatible con OpenAI o la API de Anthropic),
  **refinar el texto**, **generar la impresión** y **señalar errores** — siempre como sugerencia para aceptar.
- El texto va sin nombre, ID, accession ni nacimiento del paciente; la clave de la API queda cifrada.

## 0.99.53 — panel de productividad (ola B6)
- **Informes ▸ Productividad…**: informes firmados por médico, modalidad, subespecialidad, prioridad o día,
  con rectificaciones, mediana y p90 de la llegada a la firma y la parte en plazo; pendientes ahora; CSV.
  Quien no administra usuarios ve solo sus propios informes.

## 0.99.52 — lista de trabajo con prioridad, subespecialidad y plazo (ola B4)
- Columnas **Prioridad**, **Subespecialidad**, **Plazo del informe** y **SLA** (faltan / vence en / atrasado;
  en plazo o fuera de plazo después de firmado), por reglas del servicio y cambiables con clic derecho.
- **Trabajo ▾**: sin informe por plazo, atrasados, venciendo en 2 h, urgencias y mis subespecialidades.
- Reglas en **Configuraciones ▸ Informes ▸ Prioridad, subespecialidad y plazos (SLA)…**.

## 0.99.51 — búsqueda activa y filtros de mamografía (ola B8 y B7)
- **Búsqueda activa**: el informe BI-RADS 0 o 3 firmado genera el pedido de llamar de vuelta a la paciente
  (30 y 180 días, configurables; 4 y 5 opcionales). **Informes ▸ Búsqueda activa…**: plazos, atrasos,
  contactada / agendada / cerrada con historial, exportar CSV; la paciente sale sola cuando llega un examen
  de mama nuevo suyo.
- **Mama ▾** en la base de datos: filtros listos por BI-RADS, densidad, sin informe, tamizaje o diagnóstica
  y búsqueda activa; columnas nuevas **BI-RADS**, **Densidad** y **Búsqueda activa**.

## 0.99.50 — hierro hepático a 3 T y rango del LIC
- **Hígado en la RM**: a 3 T, el R2* hepático se divide por 2,05 para el equivalente a 1,5 T (Alam et al.,
  JCMR 2016) y luego entra en la calibración de Wood — el hallazgo muestra el R2* equivalente y el LIC. Antes,
  a 3 T no estimaba.
- **Rango del LIC** junto al número: 3,2–7 leve, 7–15 moderada, > 15 mg Fe/g grave (texto de referencia).

## 0.99.49 — grasa y hierro hepáticos en la RM
- **Hígado** (RM de abdomen): el hígado, el bazo y los segmentos vienen del TotalSegmentator y las medidas de
  los mapas del equipo — **PDFF** (mediana, p25–p75 y por segmento) y **R2\*** (con T2\*, el bazo y, a 1,5 T,
  el hierro estimado por la calibración de Wood 2005); con la doble eco en fase / fuera de fase, la fracción de
  señal de grasa. Referencia de PDFF de Tang 2015 como texto.
- Los números son hallazgos revisables (Aplicaciones ▸ Hallazgos de IA); automático en Configuración ▸ CAD/IA.

## 0.99.48 — fases fuera de la cuenta, descriptores de la curva, ROI reflejada
- **Dinámica ▸ Parámetros**: **fases fuera de la cuenta** (la que se movió sale de los mapas y curvas; no la
  inicial, la tardía ni dos seguidas) y **línea de base por la media de las fases pre**; aviso con una sola
  fase pre.
- **Mapas y columnas nuevos**: llegada del contraste (BAT), lavado (mayor descenso después del pico), iAUC90
  y tiempo medio del realce (MRT).
- **ROI reflejada** (botón derecho en la ROI): la ROI del otro lado, reflejada en el plano medio — en el mismo
  corte (axial/coronal) o en el corte del otro lado (sagital) —, con la razón lesión / contralateral.

## 0.99.47 — composición corporal en L3 y atenuación hepática
- **Composición** (TC de abdomen): en el corte axial del medio de L3, área muscular, densidad muscular, grasa
  visceral, subcutánea e intermuscular; con la altura en el archivo, el índice muscular (referencia de Prado
  2008 como texto). Hígado y bazo: HU medio, hígado − bazo e hígado / bazo, con aviso cuando hay contraste.
- Los números son hallazgos revisables (Aplicaciones ▸ Hallazgos de IA); automático en Configuración ▸ CAD/IA.
- El instalador de la segmentación pasa a descargar *trunk_cavities*.

## 0.99.46 — hallazgos de IA revisables; nódulos pulmonares
- **Hallazgos de IA** (Aplicaciones ▸ Hallazgos de IA): cada candidato que una IA señala queda *sugerido*, con
  posición, números, modelo, serie y avisos; usted **confirma, corrige o descarta** uno a uno, con quién y
  cuándo. Solo lo confirmado o corregido va al informe; lo confirmado puede volverse **lesión en seguimiento**.
  Correr de nuevo no rehace lo ya revisado.
- **Nódulos pulmonares** en la TC (botón Nódulos, o automático en Configuración ▸ CAD/IA): TotalSegmentator
  *lung_nodules* — lóbulo, diámetro mayor y medio, volumen, HU medio, parte sólida y consistencia propuesta.
- El instalador de la segmentación pasa a descargar *lung_nodules* y *total*.

## 0.99.45 — zoom escrito, ROI clonada, tiempo de duplicación, series derivadas que dicen de dónde vienen
- **Zoom escrito**: doble clic en el "Zoom N%" de la esquina ▸ ajustar, 1:1, 50 a 400% o *Escribir el
  zoom…* (`150`, `2x`, `1:1`).
- **Clonar la ROI** (botón derecho en la ROI): los otros cuadros reciben la ROI en la misma posición en el
  paciente, con la estadística de su imagen; entre exámenes diferentes, solo con los cuadros vinculados o
  registrados.
- **Tiempo de duplicación** en el seguimiento de lesiones, por el volumen o por el diámetro (suponiendo
  esfera); sin crecimiento, "no aplica".
- **Sello ámbar** cuando el cuadro está vinculado en la sincronía a cuadros de otro Frame of Reference.
- **Cortes no mostrados**: al desplazarse rápido, aparece por un instante cuántos cortes no llegaron a la
  pantalla.
- **Exportar pacientes diferentes en un solo paquete** (CD con visor o .zip, identificado) pregunta antes.
- **Series derivadas** (reconstrucciones, mapas, capturas) graban los parámetros en *Derivation Description*
  y las imágenes de origen en *Source Image Sequence*.

## 0.99.44 — límites de la edición, estadística ampliada, verificar el registro
- **Estructuras ▸ Límites de la edición**: área (en todas partes, solo dentro de una estructura, solo fuera
  de las otras), rango de intensidad válido para todas las herramientas y **sobrescribir** (lo que una gana
  sale de las otras).
- **Estadística ampliada** de la estructura: mediana, percentiles 10/90, asimetría, curtosis, entropía,
  uniformidad, diámetro mayor (Feret), esfericidad, alargamiento y aplanamiento; **Copiar los números** (una
  línea por estructura, para la planilla).
- **Verificar el registro** con el otro estudio: tablero, cortina que sigue el ratón, diferencia y mezcla,
  con la matriz del registro rígido.

## 0.99.43 — mosaico en el cuadro; CAD oculto hasta revelar
- **Mosaico de cortes** (botón derecho ▸ Mosaico, o atajo): 2 × 2, 3 × 3 o 4 × 4 cortes seguidos de la misma
  serie dentro de un cuadro; la rueda pasa la página; doble clic vuelve al cuadro normal en la imagen.
- **Leer antes, ver el CAD después** (Configuración ▸ CAD/IA): las marcas de CAD empiezan ocultas en cada
  estudio; **CAD/IA ▸ Revelar el CAD** (o el atajo) las muestra y dice cuánto tiempo de lectura hubo antes.

## 0.99.42 — perfiles de ocultación
- **Ocultar datos del paciente** gana perfiles (flecha del botón): **Ocultar todo** (el de antes),
  **Pantalla** (seudónimo, fechas reales), **Enseñanza** (seudónimo, fechas desplazadas el mismo número de
  días para todo el paciente — el intervalo entre estudios se mantiene) y **Publicación** (sin fechas ni
  equipo). Valen para el cuadro, el título de la pestaña y la lista de la base; la esquina del cuadro
  muestra el perfil en uso.
- Exportar anonimizado gana **Desplazar las fechas**, marcado solo en el perfil Enseñanza.

## 0.99.41 — imágenes clave y anotaciones en DICOM; medida borrador
- **Guardar imágenes clave y anotaciones en el estudio** (botón Clave): las imágenes clave salen como
  **KO** y las medidas, flechas y textos como **GSPS**, con el número de cada medida al lado; van al PACS
  con el estudio y se abren en otros visores.
- El **KO que llega** marca las imágenes clave aquí; con varios **GSPS de otros sistemas**, aparece solo
  el más reciente; **Traer las medidas para editar** (botón CAD/IA) convierte las medidas de un SR o GSPS
  externo en medidas de Ipê.
- **Medida borrador** (botón derecho ▸ Borrador, o preferencia para toda medida nueva): discontinua, no va
  al SR, al GSPS, al informe, a la planilla ni al seguimiento.
- Corregido: el **SR** de las medidas usaba solo el tamaño del píxel de la etiqueta — la medida calibrada a
  mano o en la ecografía salía en píxeles. Ahora usa la misma escala de la pantalla (verificado en el
  archivo: 10, 20 y 50 mm).

## 0.99.40 — estructuras: editar máscaras y guardar SEG / RTSTRUCT
- Nueva ventana **Estructuras** (botón 3D, o CAD/IA): lista de las máscaras del estudio con nombre,
  color, tipo (lesión, órgano, otro), volumen, *bloqueada* y origen; importa lesiones guardadas,
  segmentos de SEG (incluidos los de las IA) y contornos de RTSTRUCT.
- **Pincel y borrador** en cualquier cuadro y plano del estudio (disco en el plano o esfera 3D, radio en
  mm, opción de pintar solo en el rango de intensidad del clic, nunca encima de las estructuras bloqueadas).
- **Crecer / encoger** en mm, **solo la isla mayor**, **quitar islas pequeñas**, **rellenar huecos**,
  **interpolar los cortes** entre dos dibujados, **recortar por rango**, **unir / restar / intersecar**;
  deshacer y rehacer.
- **Guardar SEG** (con el tipo de cada segmento) y **guardar RTSTRUCT** (contornos por el borde de los
  píxeles, huecos como contorno interno); **actualizar la lesión guardada** con la máscara y el volumen
  corregidos; enviar los volúmenes al informe.
- Medido en el archivo: las SEG de las IA (órganos abdominales, cefalometría, implante) se importan, se
  corrigen y se guardan como RTSTRUCT en menos de 1 s por estructura.

## 0.99.39 — corrección de movimiento rígida en el estudio dinámico
- En la ventana de la **Dinámica** (y en el editor de la dinámica en Configuración), **Incluir rotación**:
  además de la traslación, el registro rígido de cada fase sobre la precontraste; la fase que giró 0,75° o
  más se remuestrea en 3D antes de los mapas, las curvas y la captura de la lesión. El título del panel
  muestra el mayor desplazamiento y la mayor rotación corregidos.
- Medido antes en el archivo: en 6 RM de mama (11 fases) la rotación entre fases quedó entre 0 y 0,5° y
  la traslación por debajo de 1,3 mm; por eso la opción viene desactivada y, por debajo del umbral, la
  fase queda solo con la traslación (sin el suavizado del remuestreo).

## 0.99.38 — registro rígido entre estudios
- **Alinear automáticamente con el otro estudio** pasa a hacer el registro **rígido** (rotación y
  traslación en 3D), con correlación (misma secuencia) o información mutua (otra modalidad o secuencia),
  en varias resoluciones; la calidad aparece en la barra de estado.
- Con el otro estudio girado 1° o más, el programa ofrece **guardarlo en el plano de este** (serie nueva,
  con la geometría y el Frame of Reference de este): los dos avanzan juntos corte a corte.
- La matriz del registro queda guardada; validación por pares de puntos (error medio y máximo en mm).
- Verificado en el acervo: RM de cráneo 3D real con transformación conocida, error medio 0,4 mm en 6 s.

## 0.99.37 — difusión en cualquier RM
- Botón **Difusión** (y en Aplicaciones): **mapa ADC** a partir de los valores de b de la serie (regresión
  en todos los b marcados), guardado como serie de RM del estudio en ×10⁻⁶ mm²/s, con umbral de ruido y
  R² mínimo; **DWI sintética** en un b elegido, marcada como sintética; **ADC en una ROI**, con el ADC del
  equipo y la señal de cada b lado a lado, y la frase para el informe.
- El b sale del archivo (estándar, GE, Siemens, Philips); en la GE anonimizada se deduce el b0; sin b en
  el archivo, se escribe. Avisos antes de calcular: un solo b, sin b0, b bajo, cortes incompletos, TE distinto.
- Verificado en el acervo: en el cráneo el ADC es el del equipo (razón 1,0002).

## 0.99.36 — fin del plan del modo de uso
- **Reglas de automatización con dueño**: búsquedas programadas, anteriores, enrutamiento, dinámica lista
  y gestión automática ganan *Visible para* (Todos / Solo yo / con elegidos) y la columna en la lista;
  pestaña propia en Configuración personal y compartida, con *Copiar para mí*. Todas siguen corriendo.
- **Adónde van los estudios bajados por la automatización**: a la base compartida (antes iban a la de
  quien estuviera conectado); la búsqueda personal puede enviarlos a la base del dueño. El **anterior**
  va a la misma base del estudio actual.
- **Referencias** de la cefalometría y de los índices craneales: solo mías o de todos en esta computadora.
- **Llamada externa** (RIS, enlace, API) ya no abre la base personal de otro usuario (el administrador
  sí, con registro).
- **Las listas de casos viajan** con los estudios entre esta computadora y el servidor central (carpeta,
  lista, nombre amigable, historia, respuesta y notas, sin duplicar).
- **Modo cliente**: el estudio nuevo bajado del PACS respeta "mi base en esta computadora".
- Corrección: guardar la configuración de una regla sin el dueño ya no borra el dueño.

## 0.99.35 — traducción revisada
- **Textos que quedaban en portugués** en el programa en inglés o español: unos 650 textos nuevos
  traducidos, entre ellos las pantallas y mensajes de las IAs (CAD/IA, segmentación, columna,
  cefalometría, ganglios, índices craneales, implante, Tareas de IA), la gestión automática y el
  mensaje de cierre del programa.
- La barra de estado, los avisos de la bandeja y las sugerencias dibujadas a mano ahora se traducen.
- Las frases armadas al momento (con números, nombres y etapas en medio) y los textos de varias líneas
  se traducen por partes; antes, nombres como "Segmentación abdominal" salían a medias.
- Verificado abriendo el programa en inglés y en español y recorriendo menús, botones, ventanas de
  Configuración y las IAs.

## 0.99.34 — correcciones: base de datos en inglés y cancelar las IAs
- **Base de datos vacía en inglés**: el filtro de modalidad "Todas" se traducía y la búsqueda buscaba la
  modalidad "All". Corregido en todas las listas desplegables: la pantalla muestra la traducción y el
  programa lee el original. Los permisos de los menús y abrir la página correcta de Configuración
  también solo funcionaban en portugués; corregido.
- **Tareas de IA que no se cancelaban**: la segmentación pedida en el visor se borraba al cerrar el
  estudio, pero la tarea quedaba "ejecutando" para siempre, el estudio "ocupado" (ninguna otra IA corría)
  y Cancelar no hacía nada. Ahora sigue con el estudio cerrado y graba el resultado; Cancelar siempre
  cierra la tarea (a la fuerza, si el trabajo no se detiene en 15 s) y libera el estudio.

## 0.99.33 — inglés por defecto
- El programa y el README pasan a tener el **inglés** por defecto; el portugués y el español siguen.
- El **instalador** de Windows pregunta el idioma en la primera pantalla (inglés marcado) y lo guarda
  para el programa; `instalar.bat` e `instalar.sh` también preguntan. La versión portátil pregunta al
  abrir, con el inglés marcado. Quien ya lo usaba sigue en el idioma elegido.
- Nuevo comando `ipe set-language en|pt-BR|es`.
- README: `README.md` en inglés (ahora completo), `README.pt-BR.md` en portugués, `README.es.md`.
- Las notas de los releases en GitHub salen en inglés.

## 0.99.32 — seguir las IAs
- **Tareas de IA**: avance (en cola, armando, ejecutando, grabando, listo, error) y **cancelar**, también de
  las que corren solas al llegar el estudio. Desde el botón Aplicaciones, el menú Ver y el aviso "⚙ IA: …"
  en la barra de estado. Cancelar no graba nada en el estudio.
- **Banco**: ✦ en el estudio con resultado de IA (la ayuda dice cuáles) y ⚙ cuando hay IA en cola o en
  ejecución; columna **IA**.
- **Órganos abdominales** en el visor (botón propio en TC/RM de abdomen y en el botón Aplicaciones).
- **Ventanas de configuración** se achican y maximizan (antes el mínimo era casi el tamaño de la pantalla).

## 0.99.31 — ola A (ideas de Weasis ViewerHub y de Eden)
- **Informe en curso** en el servidor central: quien abre el informe lo tiene; el siguiente elige solo
  leer o asumir (registrado), y el servidor rechaza grabar el informe de quien no lo tiene.
- **Apertura IHE IID** (`/IHEInvokeImageDisplay`, `requestType`) y filtros en el enlace y la API:
  estudios más recientes, modalidades, período, descripción; varios IDs y UIDs.
- **Enlace ipe:// cifrado** (`c=`): sin datos del paciente a la vista, hecho con el token, vale 24 h.
- **Perfil de intensidad** a lo largo de una regla o polilínea, con gráfico.
- **Quitar la mesa de la TC** en MPR y 3D.
- **Historial del estudio** en el clic derecho; **borrar una sola imagen**, con registro.
- **Cerrar el estudio solo** al firmar el informe o tras un tiempo inactivo.
- **Modelo de informe OIT** (neumoconiosis).

## 0.99.30 — configuraciones en tres niveles
- **Protocolos de visualización y de mamografía, layouts de la dinámica, modelos de hoja, modelos de
  informe y listas de casos** pasan a ser del servicio, compartidos con elegidos o personales.
- Cambiar un ítem del servicio sin permiso de configurar crea una copia personal que solo usted ve.
- **Configuración ▸ Usuarios ▸ Configuraciones personales y compartidas…** muestra y cambia quién ve
  cada ítem; las listas de casos tienen **Visible para** en el clic derecho.
- Atajos, ratón y presets: volver al estándar del equipo o hacer de los suyos el estándar.
- En modo cliente el servidor guarda y controla todo (las listas personales de otro no se entregan).

## 0.99.29 — recoger los paneles del banco (como en Weasis)
- **Ubicaciones y listas** (izquierda) y **Series y comentarios** (derecha) se recogen en una tira en el
  borde con el botón ◂/▸ del título; un clic en la tira los trae de vuelta, del tamaño de antes. La
  lista de estudios queda con todo el ancho.
- El botón **Listas** y el menú **Ver** abren y recogen los paneles; el estado queda guardado.

## 0.99.28 — banco personal en el servidor o en este equipo
- **Modo cliente**: el panel Ubicaciones muestra el **Servidor central** y el **Banco de este equipo**; el
  local abre sin red y sirve de banco de casos.
- **Clic derecho ▸ Banco**: copiar o mover del servidor a este equipo, y enviar de aquí al servidor (a mi
  banco o al compartido). Informes, medidas, anotaciones e imágenes clave van juntos.
- **Los estudios que importo van a "mi banco en este equipo"** (no se suben) o a mi banco en el servidor
  (se suben ya marcados).
- **Enviar un banco entero al servidor** (migración del equipo que pasó a cliente); el administrador
  envía cada estudio al banco de su dueño.
- **El servidor controla el banco**: el estudio personal de otro no aparece en búsquedas, DICOMweb ni pedidos.
- Cambiar el modo de uso avisa qué pasa con los estudios.

## 0.99.27 — base personal y compartida
- Ubicaciones ▸ Base: todo lo que veo, mi base, compartida y compartidas conmigo; el administrador ve
  también la base de cada usuario. Columna "Base" en la lista.
- Botón derecho en el examen ▸ Base: mover a mi base, a la compartida, compartir con…, y (administrador)
  pasar a la base de otro. El examen sigue siendo uno solo: solo cambia la marca.
- El examen que llega al AE de una identidad personal va a la base del dueño; lo que usted importa o
  descarga sigue su elección.
- Registro de acceso cuando el administrador abre la base o un examen personal de otro; pasar la base
  entera de quien dejó el servicio a otro usuario o a la compartida.

## 0.99.26 — "Visible para" en la configuración
- Nodos DICOM, identidades, servidores de impresión, reglas de impresión y de película automática ganan el
  campo "Visible para": todos (del servicio), solo yo, o yo y usuarios elegidos.
- En las elecciones del día a día cada uno ve lo del servicio, lo suyo y lo compartido con él; el
  administrador ve y edita lo de todos en la pantalla de configuración.
- Quien no configura la computadora abre "Mis nodos DICOM".

## 0.99.25 — modo de uso en el primer uso
- En la primera apertura el programa pregunta cómo se va a usar: solo yo (abre sin login), varias personas
  en esta computadora (crea el administrador ahí), esta computadora es el servidor del grupo, o conectar a
  un servidor. Vale para el instalador, el portátil, `executar.bat` y Linux.
- Configuración ▸ Usuarios ▸ Modo de uso lo cambia después.
- Entrar con la cuenta de Windows/Linux, sin contraseña, para usuarios vinculados a esa cuenta.

## 0.99.24 — revisión de seguridad
- Los enlaces `ipe://` sin el token ya no abren solos: el programa pregunta antes (o acepta / rechaza, en
  Red ▸ Llamada externa). Con `&token=` en el enlace abre directo. Comparación del token en tiempo constante.
- Nodo DICOM: nueva opción "Solo nodos registrados, comprobando la IP del nodo".
- Impresora DICOM: las nuevas aceptan solo la red local (las existentes no cambian).
- Servidor central: 5 contraseñas erróneas en 10 min bloquean la dirección por 10 min; aviso cuando corre
  sin certificado (HTTP).

## 0.99.23.1
- Corrección: ajustar la numeración de la columna (p. ej. L5 sacralizada) cambiaba solo la pestaña del clic; las otras pantallas del examen y una copia repetida del mismo SEG seguían con el nombre antiguo. Ahora todas se rehacen.

## 0.99.23 — vértebra de transición y numeración de la columna
- Corrección: subir un nivel en la lumbar daba dos S1; ahora la última libre pasa a S1, el sacro a S2 y
  el disco a S1-S2; renumerar fuera de la columna se rechaza con aviso.
- Numeración por la secuencia física, contada desde C2 (en la serie u otra serie del examen) o por la
  última costilla (T12, TC); los nombres de la IA solo sin ancla.
- Vértebra de transición con los nombres lumbarizada / sacralizada (S1 lumbarizada, L5 sacralizada, L5
  fusionada al sacro), transición toracolumbar, conteo de pares de costillas, disco rudimentario y
  Castellvi sugerido.
- Botón derecho ▸ Numeración de la columna ▸ Ajustar…: "esta vértebra es…", transición, Castellvi y la
  frase del informe; se guarda con el examen y avisa en el siguiente examen del paciente si difiere.

## 0.99.22 — ronda barata del plan AW: sellos, mezcla de pacientes, ventanas, medidas y salida
- Sellos de integridad arriba del cuadro: mamografía comprimida con pérdida en rojo ("no apta para el
  informe"), compresión con pérdida en otras modalidades, Modality LUT en tabla, píxel no cuadrado,
  imagen derivada.
- Mezcla de pacientes: sello rojo cuando los cuadros muestran pacientes distintos; la llamada externa
  que trae otro paciente pregunta (cerrar el anterior en todos los monitores / mantener los dos / no
  abrir) o sigue la configuración; la película pide confirmación antes de mezclar pacientes.
- Switch WL por las ventanas guardadas en el archivo; ventana escrita; "guardar la ventana actual como
  preset" con listas de presets por modalidad.
- Paisaje en la sustracción dinámica y en la DSA; mapas MIP temporal y media temporal.
- ROI de referencia (las otras muestran % de ella); regla 3D; avisos de cortes gruesos e incertidumbre ±.
- Estado del resultado de IA (automático / editado * / aceptado por quién y cuándo), guardado con el examen.
- Copia (Ctrl+C) con nivel de anotación propio y sello mínimo (serie, ventana, escala, procesamiento).
- Corrección: una respuesta del PACS (anteriores, guardar sin el implante) que llegaba tras cerrar la pestaña daba error; ahora se descarta.

## 0.99.21 — niveles ganglionares: base del cráneo por las yugulares
- La base del cráneo (límite superior de los niveles II y V) sale del borde superior de las yugulares
  internas o de las carótidas internas; el cráneo de TotalSegmentator incluye la mandíbula.

## 0.99.20 — niveles ganglionares cervicales
- Mapa de los niveles ganglionares (I–VII, derecho/izquierdo) en la TC de cuello con los reparos de
  TotalSegmentator y las reglas de imagen del estadiaje, rotulado en cualquier plano; la lesión
  segmentada con la herramienta Segmentar recibe su nivel.

## 0.99.19 — bulbos olfatorios
- Nueva medida guiada: volumen de los bulbos olfatorios por planimetría (Cavalieri) en coronal T2 y
  profundidad del surco olfatorio.

## 0.99.18 — índices del cráneo medidos en la malla de 1 mm de SynthSeg
- Las medidas usan la segmentación de 1 mm de SynthSeg (las series 2D gruesas daban un 3.er ventrículo
  de un píxel); ya no se eligen series SWAN, de fase, angio ni perfusión.

## 0.99.17 — índices del cráneo automáticos (SynthSeg)
- Índice de Evans, ancho del 3.er ventrículo, ángulo calloso y volúmenes de hipocampos y ventrículos
  con SynthSeg (versión PyTorch de DIPY) en RM de cualquier secuencia o TC, con la misma ventana de
  revisión; las medidas guiadas MRPI 2.0, Evans y ángulo calloso se abren ya completadas. Ejecute de
  nuevo instalar_segmentacao una vez.

## 0.99.16 — cefalometría automática al llegar
- **Configuración ▸ CAD/IA ▸ Cefalometría del cavum**: se hace sola cuando llega la TC, filtrada por
  la descripción del estudio, con la serie preferida, espesor máximo, mínimo de cortes y destinos.
  Los números quedan guardados en la imagen de revisión: el botón Cefalometría los reabre sin
  volver a calcular. Las líneas de las medidas aparecen en cualquier plano que las
  contenga (sagital reformateado, axial, oblicuo); “Ver en el cuadro” lleva a cada una.
- Toda segmentación e IA (SEG, RTSTRUCT) aparece también en los planos reformateados.

## 0.99.15 — cefalometría del cavum automática
- Botón **Cefalometría** (TC de cara, cavum y cuello): TotalSegmentator (tareas abiertas) separa
  paladar, faringe, hioides, mandíbula, lengua y vértebras cervicales, e Ipê mide el área de sección
  transversal mínima perpendicular al eje de la vía aérea, longitud y espesor del paladar blando,
  espacio aéreo posterior, hioides al plano mandibular, tamaño de la lengua y nivel del hioides.
- Ventana de revisión con el origen de cada número (automático o editado), medida a mano,
  referencias editables y texto para el informe; una imagen de revisión con las líneas queda en el
  estudio.

## 0.99.11 — DicomViewer pasa a llamarse Ipê
- Nombre e icono nuevos (la flor del ipê amarillo); código publicado en GitHub bajo GPL-3.0.
- La carpeta de datos, el AE de fábrica `DICOMVIEWER`, los enlaces `dicomviewer://` y
  `python -m dicomviewer` siguen funcionando; el enlace nuevo es `ipe://`.
- Estudios anteriores elegidos encima de la tira de miniaturas; un clic en un cuadro vacío muestra
  la lista de series.

## Novedades de la 0.15.1

La línea de texto azul a la izquierda de cada cuadro fue sustituida por un **icono pequeño de ratón**. Al
pasar el cursor por encima, un globo muestra qué hace cada botón en ese momento (izquierdo, derecho, medio,
rueda, Ctrl+rueda, Shift+rueda); el botón izquierdo del icono se enciende en ámbar cuando hay una
herramienta activa distinta de ventana/nivel, y al hacer clic se abre la lista de herramientas del botón
izquierdo. El texto dibujado sobre la imagen (Im 31/60, Esp 3.0 mm, W/L, FOV), la película y los gráficos
también se traducen ahora, y el catálogo creció a 2708 entradas.

## Novedades de la 0.16 — varias ubicaciones de estudios

Como el panel *Sources* de OsiriX/Horos, la columna izquierda de la pestaña Base de datos ahora tiene
**Ubicaciones**. Un clic cambia de ubicación y la lista pasa a ser la de esa carpeta. Cada ubicación lleva
la base entera dentro de su carpeta (`dicomviewer.sqlite`, `Storage/`, un archivo de marca), así que un
disco externo se abre en otro ordenador con todo: estudios, listas de casos, comentarios, mediciones e
informes. Añadir una ubicación **no copia nada** — los archivos que ya están en la carpeta solo se indexan.
Con el botón derecho sobre un estudio, *Copiar a la ubicación*; los archivos de origen nunca se tocan. Las
ubicaciones no disponibles (disco desconectado, red caída) se muestran en gris y vuelven cuando vuelve el
disco. Los nodos PACS aparecen en el mismo panel.

## Novedades de la 0.26 — comparar las imágenes del estudio: DMSA, paratiroides, tiroides y tránsito

Cuatro estudios no caben en la ventana de curvas, porque su cálculo compara **imágenes separadas**:
DMSA (anterior × posterior), paratiroides (precoz × tardía), tiroides (tiroides × jeringa) y
tránsito colónico (24 h × 48 h × 72 h). Ahora hay una ventana para eso — **MN ▸ Comparar las
imágenes del estudio…**

- **Cada imagen es una fila**, con su **papel** y la **hora leída del encabezado**. Las capturas de
  pantalla de la estación quedan fuera: son la hoja del informe, no una imagen de medida.
- **Las regiones se dibujan en cada imagen**. **Copiar** y **Copiar reflejado** ahorran el
  retrabajo; el reflejado es el correcto para ANT/POST, porque mantiene ambas con la misma área.
- **Corrección de decaimiento entre las imágenes**, activada por defecto.

**Los cálculos**: función relativa del DMSA por media geométrica √(ANT × POST); paratiroides en
doble fase (corregida del decaimiento); captación tiroidea contra el patrón de la jeringa; centro
geométrico del tránsito colónico; y un modo libre con solo las cuentas.

## Novedades de la 0.25 — una receta por estudio: gástrico, DISIDA, salivales y razón

La ventana de curvas ganó una caja **Estudio**. Elegir el estudio cambia tres cosas a la vez: los
nombres listos de las regiones, el cálculo y lo que la ventana pregunta.

- **Renograma** (como en la 0.24).
- **Vaciamiento gástrico** — % de retención a 30 min, 1 h, 2 h y 4 h, y el T½. Un punto que la
  curva no alcanza aparece como **—**, nunca extrapolado.
- **Vesícula (DISIDA)** — fracción de eyección a partir del máximo antes del estímulo y el mínimo
  después. La ventana pregunta cuándo se dio la sincalida y la marca en el gráfico.
- **Glándulas salivales** — captación relativa por glándula (suma 100%) y fracción de excreción.
- **Razón lesión / lado normal** — media por píxel de cada región y la razón entre ellas.
- **Libre** — solo los números generales de la curva.

**Los valores de referencia de las guías aparecen bajo la tabla**, como texto junto a lo medido. El
programa no clasifica: nunca escribe "retardado" ni "obstruido".

**Imagen condensada**: cada cuadro se convierte en una columna y el tiempo pasa a ser el eje
horizontal.

## Novedades de la 0.24.1 — mano alzada, contorno automático y doble clic en las incidencias

- **Mano alzada** en la caja "Forma": arrastre sobre la imagen y el trazo se convierte en la región.
- **Contorno automático**: dibuje una región aproximada alrededor del objetivo, selecciónela y haga
  clic en **Contorno automático**. Sigue un umbral en **% del máximo de esa región** (40% por
  defecto) y toma **solo lo conectado al píxel más caliente**. No se sale de la caja dibujada, y
  cambiar el umbral recalcula dentro de la misma caja.
- **Reflejar D/I funciona con el contorno automático**: la máscara va reflejada con la misma área,
  que es lo que exige la función relativa.
- **Doble clic en una serie de medicina nuclear** abre **todas sus incidencias lado a lado**, se
  llamen como se llamen, con la misma ventana y el zoom enlazado.

## Novedades de la 0.24 — medicina nuclear fase 2: regiones, curvas y el renograma

La maquinaria que comparten siete estudios. Renograma, glándulas salivales, dacriocistografía,
cistografía isotópica, reflujo gastroesofágico, vaciamiento gástrico y trifásico óseo son lo mismo:
contar los píxeles de una región en cada cuadro, restar el fondo, ponerlos en el eje de tiempo
correcto y aplicar una fórmula. Solo cambia la fórmula.

- **Ventana propia de análisis** (**MN ▸ Curvas actividad-tiempo por región…**): la imagen con las
  regiones a la izquierda, el gráfico y la tabla a la derecha. Abre con **todos los cuadros sumados**
  — un cuadro de 2 s por sí solo tiene demasiado ruido para dibujar un riñón encima.
- **Reflejar D/I**: dibuje un riñón y el otro sale reflejado en el eje vertical, con el mismo método
  de fondo — así ambas regiones tienen el mismo tamaño, que es lo que exige la función relativa.
- **Tres formas de restar el fondo**: una ROI de fondo propia, un **anillo alrededor de la región**
  (con un píxel de holgura) o una fracción fija. El método queda escrito junto al resultado.
- **Cuentas por segundo**, activado por defecto: sin dividir por la duración aparece un escalón de
  15× que no existe en el paciente.
- **Cada punto va en el medio de su cuadro**, no al principio.
- **Renograma completo**: función relativa por el método de la integral (1 a 2,5 min), tiempo al
  pico, T½ tras el pico y relación 20 min/pico. **Un T½ no alcanzado aparece como "no alcanzado"**,
  nunca como un número grande.
- **Corrección de decaimiento** opcional; sin vida media en el archivo el programa lo dice en vez de
  corregir mal.
- **Exportar CSV** y **Enviar al informe** — solo números, sin interpretación, y nada sale solo.

El programa **no trae valores de referencia** y nunca escribe "obstruido".

**También en esta versión:** la hoja de informe de la estación se marca como **imagen clave
automáticamente** al importar. **Los estudios de medicina nuclear que ya estaban en la base también
se marcan**, en una pasada en segundo plano al abrir el programa.

## Novedades de la 0.23.1 — la medicina nuclear comprobada con estudios reales

Tres cosas que el estándar DICOM manda grabar y los equipos no graban. Descubiertas al abrir 146
series reales de medicina nuclear, y todas se convirtieron en un ajuste:

- **La vista (ANT, POST, LAT) casi nunca está en el encabezado.** Solo las series de cuerpo entero
  traen la `ViewCodeSequence`; en las demás el programa solo veía "Detector 1" y "Detector 2".
  Ahora lee las siglas de la **descripción de la serie** — "ANT POST PERF", "LD LE PERF" — y solo
  las acepta cuando su número coincide con el número de detectores. La vista obtenida así aparece
  como **"ANT (de la descripción)"**, en otro color y con aviso en la barra: confundir anterior con
  posterior invierte derecha e izquierda en el informe.
- **Una misma serie puede mezclar un archivo de dos detectores con otro de uno solo**, lo que la
  partía en vistas paralelas que no coincidían. Los ejes se deciden ahora para la serie entera.
- **`SeriesType` viene vacío**, así que el tipo sale de los propios vectores, y las proyecciones de
  SPECT cuentan como tomografía aunque no haya eje de corte.

**Sobre el SUV en SPECT/CT: no es posible, y ahora está confirmado.** Ninguna de las 146 series
trae la escala cuantitativa (`Units` ni Real World Value Mapping) — todo son cuentas brutas. En el
PET, que sí trae `Units = BQML`, el SUV sigue funcionando.

## Novedades de la 0.23 — medicina nuclear: el estudio deja de ser un montón de cuadros

Primera etapa del módulo de medicina nuclear. Un archivo de MN guarda varias imágenes en el mismo cubo,
y lo que dice qué es cada cuadro son los **vectores del grupo 0054** del DICOM: detector, ventana de
energía, fase, corte, proyección, tiempo. Sin leer esos vectores — que es lo que la mayoría de los
visores genéricos no hace — un renograma o un cuerpo entero ANT/POST aparece como un montón de cuadros
sin sentido.

- **La serie se abre en las partes que la componen.** En la tira de la izquierda, justo debajo de la
  serie de MN, una línea por vista: `↳ ANT`, `↳ POST`, `↳ Fase 1 · 20 × 2 s`, `↳ ANT · Tc-99m`… Cada una
  puede arrastrarse sola a un marco. Funciona tanto si el equipo graba todo en un archivo como si graba
  un archivo por vista.
- **Botón MN en la barra: "Anterior y posterior lado a lado"**. Abre ANT y POST en dos marcos **con la
  misma ventana** — calculada sobre las dos imágenes juntas, para que ninguna sature — y con **ventana y
  zoom enlazados**. Comparar ANT con POST con ventanas distintas es un error de lectura, así que el
  programa no deja que ocurra por descuido.
- **Escala de grises invertida por defecto** en medicina nuclear (captación oscura), que es la convención
  del área. Se puede desactivar en el menú del botón MN.
- **Media geométrica √(ANT × POST)**, calculada al momento, como una tercera vista. La posterior se
  refleja antes de combinar — sin eso la cuenta suma el hígado con el bazo.
- **Tiempo real en los estudios dinámicos**: la duración de cada cuadro sale de la secuencia de fases
  (0054,0032), no de un valor único.
- **Corrección de decaimiento y cuentas por segundo**, con la vida media leída del encabezado y, si
  falta, de una tabla (Tc-99m, I-123, I-131, Ga-67, In-111, Tl-201, Lu-177).
- **Fantomas de medicina nuclear** en los datos de prueba: una gammagrafía ósea de cuerpo entero con ANT
  y POST en un archivo y un renograma con flujo de 2 s y dinámico de 30 s.

Todavía no: curvas actividad-tiempo con ROI, cuantificación por estudio, fusión SPECT/CT y cardíaco.

## Novedades de la 0.22 — marcas en la lista, descarga por serie, búsqueda del PACS y 3D con cortes

- **Marcas en la lista de estudios**, al lado del nombre del paciente (como el ✎ del comentario):
  **⌛ informe en borrador**, **✔ informe firmado**, **✔↻ informe rectificado** y **▦ película
  guardada**, con explicación al pasar el ratón.
- **Estudio que todavía está descargando**: las series que aún no llegaron aparecen en la tira de la
  izquierda, **más claras**, como "en cola", "descargando ahora" o "no se descarga" — como hace Weasis.
  Clic derecho en una de ellas: **No descargar esta serie** (o cancelar el estudio entero). Para eso, la
  descarga pasó a ser **serie por serie**.
- **Búsqueda del PACS**: el botón **Buscar** se convierte en **Parar** mientras la búsqueda corre — el
  C-FIND se aborta y queda en pantalla lo que ya había llegado. La **modalidad** acepta más de una
  (escriba `CT, MR`). Además de los períodos ya listos, ahora hay **Fecha exacta…** e **Intervalo…** con
  calendario. Y el estado **"en el ordenador"** (sí / parcial) ahora también aparece **en cada serie**.
- **3D**: nuevo modo **Superficie** junto a VR, MIP, MinIP y media — primer encuentro con el umbral, con
  el cruce interpolado y la normal calculada en ese punto, así el contorno sale liso. Y el botón
  **Cortar…**: desde el **cursor 3D** (o el centro del volumen) deja solo lo que está detrás, delante, a
  la derecha, a la izquierda, arriba o abajo — la cara del corte se dibuja lisa. Vale también para VR y
  MIP, y el volumen sigue girando normalmente.

## Novedades de la 0.21 — seis funciones de una vez

- **Corregir etiquetas DICOM**: nombre cambiado, lado equivocado, incidencia equivocada, fecha mal
  escrita en el aparato. Clic derecho en la imagen (Información DICOM → **Corregir**) o en la lista de
  estudios. El programa guarda una **copia corregida** con UIDs nuevos y referencia a la imagen de
  origen — **el estudio original nunca se altera**.
- **Filtros de nitidez y suavizado**: tres niveles de nitidez (máscara de desenfoque) y dos de
  suavizado, aplicados **a los valores de la imagen**, antes de la ventana. El filtro acompaña a la
  imagen en la película, el PDF, las imágenes exportadas y el **visor HTML** (botón Filtro, tecla S).
- **Calibración GSDF del monitor** (DICOM PS3.14): indique el negro, el blanco y la gamma de su
  monitor y el programa construye la tabla que hace los pasos de gris **perceptualmente iguales**.
  Muestra la desviación antes y después (en un monitor común baja de ~65% a ~5%) y trae cuatro
  patrones de prueba, también a pantalla completa. La calibración es **por monitor**.
- **Superficie 3D y STL**: de la segmentación que ya hizo o de un rango de densidad (hueso, hueso
  cortical, piel, metal). La malla sale por *surface nets* — cerrada y lisa — con opciones de solo la
  pieza mayor, reducir y suavizar, y graba **STL binario** para impresión 3D o planificación.
- **DSA (sustracción digital)**: máscara en un cuadro elegido o en el promedio de los tres primeros,
  sustracción **logarítmica** o lineal, inversión y **desplazamiento de la máscara** con flechas para
  quitar el fantasma del movimiento.
- **Cardíaco 4D**: las series con los mismos cortes repetidos en varias fases se reconocen solas (por
  la posición, sin depender de etiquetas). El desplazamiento recorre **los cortes sin salir de la
  fase**; el cine de fases reproduce el ciclo **en un corte fijo**; se pueden **comparar dos fases lado
  a lado**; y la MPR/3D monta el volumen **de la fase en la que está**.

## Novedades de la 0.20.1 — tabla de servidores de impresión

La lista de servidores pasó a ser una **tabla como la de los nodos DICOM**, con una **casilla para
encender y apagar** en la primera columna y las columnas que importan: nombre, AE Title, puerto, a quién
acepta, qué hace al recibir, plantilla de hoja, si guarda en la base y la situación (*Recibiendo*,
*Apagado* o el error del puerto). También hay **Probar (C-ECHO)**, que llama al propio servidor para
comprobar que el puerto está abierto y responde. Marcar o desmarcar se aplica al hacer clic en OK.

## Novedades de la 0.20 — la impresión con vida propia: varios servidores, reglas, logo y US automático

- **Botón Impresiones en la pantalla inicial** y una ventana solo para esto (**Configuración de
  impresión**), con pestañas de servidores, destinos, reglas, plantillas de hoja y montaje automático.
- **Varios servidores de impresión a la vez**: un AE y un puerto por aparato o por sector, cada uno con
  su destino fijo, su plantilla de hoja y su opción de guardar las hojas en la base. La lista muestra en
  qué servidor llegó cada trabajo.
- **Reglas de reenvío**: *cuándo* — servidor, AE de origen (acepta `MG*`), texto de la etiqueta, tamaño
  de la película, número de hojas y franja horaria (incluso la que cruza la medianoche); *entonces* —
  destino y plantilla. Se revisan en orden, y una regla puede **dejar continuar**, para que el mismo
  trabajo se guarde en PDF *y* salga en película. Sin ninguna regla, nada sale solo.
- **Plantillas de hoja con logo**: logo, nombre de la clínica, segunda línea, qué mostrar (paciente,
  fecha, aparato), pie, fondo de película o de papel, márgenes — con **vista previa en vivo** en el
  editor. Se puede respetar la hoja tal como llegó o **rehacerla con nuestra rejilla** (guardamos cada
  caja de imagen por separado, así que 2×2, 3×3… son posibles). Vale para el PDF, la impresora del
  equipo y la impresora DICOM.
- **Identificar al paciente es más fácil**: el programa lista **estudios de la base del mismo aparato y
  horario** y un clic completa nombre e ID; con Tesseract instalado, un botón de **OCR** intenta leer el
  encabezado quemado en la hoja.
- **Película automática del ultrasonido**: el US envía las imágenes por C-STORE, no por impresión —
  ahora, algunos segundos después de que el estudio deja de llegar, el programa monta la película en el
  layout que eligió y la deja lista en la lista de impresiones, o la reenvía de inmediato.

## Novedades de la 0.19 — el programa como impresora DICOM

Ipê ahora **recibe las películas de las modalidades** (TC, RM, MG, US) como si fuera una
impresora de película, las guarda en una **lista de impresiones** y permite reenviar cada trabajo a
donde quiera.

- **Actívela** en Red → Red DICOM → **Impresora DICOM** e indique en la modalidad el AE, la IP y el
  puerto que aparecen allí (predeterminado **11113**: las impresoras de película suelen usar el 104,
  pero el programa nunca se ejecuta como administrador y en Linux los puertos por debajo de 1024 lo
  exigen; casi toda modalidad acepta otro puerto).
- **Lo que llega** es la hoja terminada: la rejilla (`STANDARD\2,2`, `ROW`, `COL`), el tamaño de la
  película, la orientación, la polaridad, el tamaño real pedido en mm y los píxeles de cada caja de
  imagen, guardados **tal como llegaron**. Se responde al estado de la impresora (N-GET), que muchas
  modalidades consultan antes de enviar la primera imagen.
- **El nombre y el ID del paciente no llegan**: la impresión DICOM no los envía (quedan quemados en los
  píxeles). Cuando la modalidad escribe algo en la **etiqueta de la sesión** o en el Owner ID el
  programa lo aprovecha; si no, usted lo escribe con **“Identificar paciente”**.
- **Lista de impresiones (Ctrl+Shift+P)**: las películas recibidas y las **montadas aquí en el
  compositor** están en la misma lista, con vista previa hoja por hoja, los parámetros de la película y
  la situación de cada trabajo.
- **Cada hoja también se guarda como estudio** en la base (Secondary Capture), para abrirla en el visor
  como cualquier otro.
- **Enviar a…**: un trabajo o varios a la vez — **PDF en una carpeta**, la **impresora del equipo**, una
  **impresora DICOM** (reenviado *tal como llegó*: misma rejilla, mismo tamaño, caja por caja) o
  **imágenes PNG/JPEG en una carpeta**. Nada sale solo, salvo que elija un destino fijo en “Al recibir”.

## Novedades de la 0.18.2 — editar protocolos desde la lista de etapas

En la barra de mamografía, **"Editar protocolos…" ya no es un botón aparte: ahora es la última línea de la
lista de etapas** (tras un separador). Elegirla abre el editor y **no cambia la etapa en la que está**.

## Novedades de la 0.18.1

El implante apagado ya no tiene el borde dentado: la prótesis se busca en una imagen reducida (rápido),
pero el borde ahora se **rehace a resolución completa** — en una franja estrecha alrededor del contorno
grueso cada píxel se decide por su propio valor, con el umbral a medio camino entre la silicona y el tejido
vecino, seguido de un filtro de mayoría. El contorno coincide con el real con precisión de un píxel. El
área apagada además queda siempre en el gris medio de la ventana que está en pantalla.

## Novedades de la 0.18

**Apagar implante, rehecho**: antes buscaba la prótesis por la densidad, lo que falla en estudios reales
porque una mama densa también es clara. Ahora busca por la **falta de textura** — la silicona es un área
grande, clara y *lisa*. Si aun así no la encuentra, haga clic derecho dentro de la silicona → *Apagar el
implante desde aquí*.

**El visor HTML de la exportación ahora hace mamografía**: el botón *Mamografía* coloca CC y MLO de ambas
mamas lado a lado, con la pared torácica hacia el centro y la ventana del tejido; *Cuadrante* (Q) amplía el
cuadrante posterior y superior y después el posterior e inferior, en todos los cuadros a la vez y anclado a
la esquina; *Ventana de la mama* rehace la ventana solo con el tejido. El lado, la incidencia, la caja de la
mama, el lado de la pared torácica y la ventana del tejido se calculan al exportar y viajan con el archivo.
El visor exportado sale en el idioma en uso.

## Novedades de la 0.17.2

**Apagar implante** (barra de mamografía, Alt+I): la prótesis se muestra como un área lisa, sin textura —
solo queda la línea de la cápsula — y la ventana se calcula solo con el tejido mamario, tal como la
presentan los equipos de mamografía. Se aplica a todos los cuadros a la vez y nunca modifica el archivo. El
zoom por cuadrante pasó a dos pasos en lugar de cuatro: posterior y superior → posterior e inferior →
imagen completa.

## Novedades de la 0.17

**La carpeta de la base de este ordenador** ya se puede cambiar desde el propio programa (botón derecho en
*Base de este ordenador*, en el panel Ubicaciones, o *Configuración → Cambiar la carpeta de la base de este
ordenador…*); pregunta si **mover** la base y los archivos o **solo apuntar** a la carpeta nueva, y recuerda
la elección.

**Mamografía:** el zoom y el desplazamiento ahora se **sincronizan entre los cuadros** por posición
anatómica — en la otra mama sale reflejado, y se mantiene entre 2D, tomosíntesis y recombinada. El zoom por
cuadrante sigue la mama y no la pantalla, en cuatro pasos: **posterior y superior → posterior e inferior →
anterior y superior → anterior e inferior → imagen completa**, y el cuadrante queda **anclado a la
esquina**, de modo que la pared torácica se mantiene en el lado de la pantalla en que ya estaba y las dos
mamas siguen reflejadas. Pasar de la 2D a los cortes de la tomo ya no
salta, y *BE ⇄ Recomb.* mantiene el cuadrante. El nombre de la etapa quedó a la izquierda y las dos flechas
juntas a la derecha.
