> **No destinado a uso diagnóstico.** Este programa es un proyecto propio, sin registro sanitario y sin certificación como dispositivo médico. Los números que devuelve son medidas; la interpretación siempre es del médico.

<!--
Texto fuente de la guía del usuario (español). Para generar el PDF:  python tools/guia/gerar_guia.py --idioma es
La sintaxis aceptada está al comienzo de tools/guia/gerar_guia.py. {versao} se convierte en la versión del código.
Al cambiar una pantalla, cambie también esto (y las versiones en portugués e inglés) y genere de nuevo.
-->


# Primeros pasos

Ipê es un visor DICOM para Windows y Linux, hecho para la estación de informes: guarda los estudios en una base de datos local, recibe y busca estudios en la red DICOM, comprueba que los estudios de las modalidades llegaron al PACS, muestra las imágenes en varios monitores y termina en el informe, la película o la exportación.

Esta guía describe la versión {versao}. Donde el programa tiene una limitación, está escrita: es más útil saber lo que la herramienta no hace que descubrirlo delante del estudio.

## Panorama: lo que tiene Ipê

Un mapa del programa, por tema, con el capítulo donde se explica cada cosa.

| Tema | Qué hay | Dónde |
|---|---|---|
| Estudios | Base de datos local (PostgreSQL), ubicaciones (disco externo, banco de casos), importar carpeta/ZIP/RAR/7z/CD, comentarios, protección, papelera, comprobar y reconstruir la base de datos, limpiar la caché | Primeros pasos; La pantalla de la base de datos; Configuración |
| Visor | Ventana y presets, mediciones y calibración, mosaico, imágenes clave, sincronizar cuadros, MPR/oblicuo/curvo/3D, fusión, varios monitores, sellos de integridad | El visor; Varios monitores |
| Mamografía | Protocolos de visualización, alineación por el pezón, densidad (BI-RADS), calcificaciones vasculares y escalas, SR, búsqueda activa, tomosíntesis, implante de silicona | Mamografía; Mama |
| RM de mama y otras RM | Dinámica (curvas, mapas, sustracción, Tofts), alinear las fases por IA, separar series dinámicas, difusión (ADC), hígado (grasa, hierro, rigidez), próstata (PI-RADS), verificación de protocolos de RM | Mama; Medicina nuclear y oncología; Informe |
| IA | Órganos abdominales, niveles de la columna y vértebra de transición, ganglios cervicales, cefalometría, índices del cráneo, nódulos, enfisema, aorta, calcio coronario, composición corporal, médula, lesiones FDG/PSMA, glioma, FLAIR, T1 sintético, MedSAM2 — automáticas al llegar o a mano, en cola, con hallazgos revisables | Medicina nuclear y oncología; Mama; Configuración |
| Salida de las IA | SEG, tablas y serie con overlay en color, por IA o para todas, y envío a los destinos DICOM (para PACS que no muestran SEG) | Lo que cada IA guarda en el estudio |
| Lote | Lote a partir de una hoja de cálculo (busca en el PACS, ejecuta las IA, envía, imprime, anonimiza), exportar los resultados de las IA a Excel | Red DICOM, PACS y automatización; Listas de casos |
| Listas y enseñanza | Listas de casos e inteligentes, modo reunión, paquete de casos, perfiles de ocultación/anonimización | Listas de casos |
| Informe | Plantillas, hallazgos de IA, impresión por IA, esquemas guía, adjuntos (PDF e imágenes), firmar y enviar al PACS, lista de trabajo con plazo, productividad | Informe |
| Película e impresión | Compositor de película, impresión DICOM, impresiones recibidas, panel de películas | Película e impresión |
| Red | Nodos DICOM, buscar/descargar (C-FIND, C-MOVE, C-GET), enviar, reglas de automatización, gestión DICOM (¿los estudios de las modalidades están en el PACS?), servidor central, Ipê cliente, Ipê Web, HTTPS | Red DICOM, PACS y automatización; Gestión DICOM |
| Integración | Llamada externa (RIS, enlace ipe://, API HTTP), enlace del estudio sin contraseña, abrir por la dirección de Ipê Web | Llamada externa |
| Administración | Usuarios y permisos, perfiles, tres niveles de configuración, auditoría, exportar/importar configuraciones, actualización (GitHub y servidor) | Configuración, usuarios y exportación |

## Las dos pantallas

El programa tiene una pestaña fija, **Base de datos**, y una pestaña por estudio abierto. Todo empieza en la base de datos: es la lista de estudios, la búsqueda, las listas de casos y los botones que abren las otras ventanas (PACS, Gestión, impresiones, informe, configuración).

- **Abrir un estudio**: doble clic en la fila, o el botón **Abrir**.
- **Volver a la base de datos**: **Ctrl+B**, o la pestaña Base de datos.
- **Cerrar un estudio**: la ✕ de la pestaña. Con el estudio repartido entre monitores, cerrar uno cierra todos: medio estudio abierto en un monitor es peor que ninguno.
- **Cambiar de pestaña no le quita el teclado al cuadro**: al hacer clic en la pestaña de un estudio, el teclado va al cuadro. Las flechas avanzan por las etapas de la mamografía, no por las pestañas.
- **Un solo Ipê** (0.99.79): hacer clic otra vez en el acceso directo, o abrir un enlace ipe://, no abre otro programa. El que ya está abierto pasa al frente, incluso cuando estaba oculto en la bandeja (cerrar a la bandeja) o aún en el inicio de sesión. Si el programa se cayó, el siguiente clic abre normalmente.

## Importar estudios

Menú **Archivo**: **Importar carpeta…** (Ctrl+I), **Importar archivos…** e **Importar comprimido (ZIP, RAR, 7z)…**. También se pueden arrastrar archivos, carpetas o comprimidos sobre la ventana.

> **Comprimidos.** ZIP y TAR (.tar, .tar.gz, .tgz, .tar.bz2, .tar.xz) los abre el programa solo. RAR, 7z, ISO y CAB los abre con **7-Zip**, si está instalado (7-zip.org), o con el **tar que ya viene en Windows 10/11**; para RAR también sirve WinRAR instalado. Si no existe ninguno de los dos, el programa avisa. Comprimido en partes (.part1.rar, .part2.rar…, o .7z.001, .7z.002…): envíe todas las partes, o solo la primera, con las demás en la misma carpeta. Un comprimido dentro de otro también se abre. Un archivo con contraseña no se abre: el programa avisa, y entonces hay que descomprimir fuera e importar la carpeta.

> **¿Copiar o referenciar?** En Configuración ▸ Base de datos ▸ Importación, la casilla *Copiar los archivos al almacenamiento del programa* decide si el DICOM se copia a la carpeta del programa o solo se referencia donde está. Desmarcada, el programa nunca escribe en el archivo original, y nunca lo borra.

## Abrir el estudio más rápido (0.100.38)

Al abrir un estudio de la base de datos de este ordenador:

- Las imágenes en **JPEG-LS** (la compresión sin pérdida del archivo) y en HTJ2K se decodifican **en paralelo**, por los varios núcleos del procesador, sin bloquear la pantalla mientras se adelanta la serie. En la medición, la RM de 12 series se abrió en 0,4–0,6 s (antes, 1,1–1,3 s).
- En la **mamografía**, las cuatro proyecciones se decodifican a la vez, y la alineación por el pezón quedó unas quince veces más rápida: 0,7–0,8 s hasta la primera imagen (antes, 2,2 s), en un ordenador de dos núcleos; con más núcleos, menos.
- **Importar** (carpeta, CD, lo que llega por la red) graba en la base de datos por lotes: cerca de dos veces más rápido.

El registro sigue diciendo, en cada apertura, dónde se fue el tiempo (la línea *Apertura (…): primera imagen en … s*).

## Dónde están los datos

El menú **Ayuda ▸ Abrir carpeta de datos** muestra dónde están la base de datos (la carpeta `postgres`), las imágenes copiadas (Storage), la configuración (settings.json) y los registros (logs). Por la línea de comandos, `ipe-cli info` imprime las mismas rutas.

El programa no se ejecuta como administrador, y nunca lo necesita: todo lo que escribe queda en el perfil del usuario.

### Versión nueva desde GitHub

Al abrir (una vez al día), Ipê comprueba en GitHub si salió una versión nueva; **Ayuda ▸ Buscar versión nueva (GitHub)…** busca al instante, y **Ayuda ▸ Avisar cuando salga una versión nueva** activa y desactiva el aviso (lo mismo que la casilla **No volver a avisarme**, que está en el propio aviso). Si hay una versión nueva, la ventana muestra el número (y las novedades, en *Mostrar detalles*) y ofrece:

- **Descargar e instalar** (Windows, instalado con el instalador): descarga el instalador, comprueba el SHA-256 que publica GitHub, cierra el programa, instala sin preguntas y abre la versión nueva. La carpeta del programa, la de la base de datos, el idioma y el modo de uso quedan como estaban.
- **Descargar** (versión portátil de Windows y Linux): descarga el paquete y abre la carpeta; reemplazar la carpeta del programa se hace a mano (la base de datos y la configuración quedan fuera de ella).
- **Omitir esta versión**: el aviso automático no vuelve para ella (la búsqueda desde el menú sigue mostrándola). **Más tarde**: vuelve a preguntar al día siguiente. **Ver la página**: abre el release en el navegador.

Los archivos del release tienen nombres en inglés desde la 0.99.81: `Ipe-<versión>-windows-installer.exe` (hasta la 0.100.104, `Ipe-<versión>-installer.exe`), `Ipe-<versión>-windows-portable.zip` e `Ipe-<versión>-linux-portable.tar.gz`. Desde la 0.99.86 el release ya no trae la copia con el nombre antiguo (`-instalador.exe`): quien aún esté en una versión de la 0.99.70 a la 0.99.80 instala la nueva una vez a mano.

En el modo cliente, quien decide la versión es el servidor central (Ayuda ▸ Buscar actualización en el servidor central…), y el aviso de GitHub no aparece. La consulta envía a GitHub solo el nombre del programa y la versión.

**Límite de GitHub (0.100.54).** Sin cuenta, GitHub acepta pocas consultas por hora desde la misma dirección de internet (en una clínica, todos los ordenadores salen por la misma) y respondía "HTTP Error 403: rate limit exceeded". Ahora, cuando eso ocurre, Ipê descubre la versión nueva por la propia página del release (que no tiene ese límite) y descarga desde allí, comprobando el SHA-256 con el archivo `SHA256SUMS.txt` del release.

**La versión no cambió después de instalar (0.100.54).** Dos causas, y Ipê ahora avisa de las dos al abrir:

- *El acceso directo apunta a otra copia.* El instalador actualiza la carpeta donde se instaló Ipê (normalmente `%LOCALAPPDATA%\Programs\Ipe`); si el acceso directo que usted usa abre otra copia (la portátil, una carpeta antigua), esta sigue vieja. Ipê compara la versión abierta con la que registró el instalador y ofrece abrir la nueva. Después, cambie el acceso directo (o borre la copia antigua). El registro (`Logs\dicomviewer.log`) muestra, en cada apertura, la versión y la carpeta del programa.
- *Ipê estaba abierto durante la instalación* (por ejemplo, minimizado como icono cerca del reloj, en el ordenador que sirve los estudios): los archivos antiguos se quedaban en su lugar. Ahora el instalador espera a que Ipê se cierre (hasta 30 s, en la actualización automática) y, si sigue abierto, pide cerrarlo antes de continuar.

### Llevar la configuración a otro ordenador

**Configuración ▸ Sistema ▸ Exportar la configuración…** graba un archivo `.ipeconfig` con lo que usted elija: la configuración de este ordenador (ventana, ratón, impresión, exportación, red), sus preferencias, los protocolos de visualización y de mamografía, las plantillas de informe y de hoja, perfiles, SLA y búsqueda activa, los nodos DICOM, las identidades AE, la automatización y las traducciones propias. El archivo es el mismo en Windows y en Linux: se exporta en uno y se importa en el otro.

**Configuración ▸ Sistema ▸ Importar configuración…** abre el archivo, muestra lo que contiene e importa las partes marcadas. Lo que ya existe aquí con el mismo nombre (un nodo, una regla, un protocolo) se actualiza; el resto continúa. Antes de importar, la configuración actual se guarda en una copia, en `backups_config` dentro de la carpeta de configuración (para volver atrás, importe la copia). Después, cierre y abra el programa.

Lo que **no** va, porque es de cada ordenador: los estudios y la carpeta de la base de datos, las ubicaciones, los monitores, el inicio de sesión guardado, el título AE y el token de este ordenador, el rol de servidor o cliente y la posición de las ventanas. Una carpeta del otro sistema (`C:\...` llegando a Linux, `/home/...` llegando a Windows) no se graba. Las **contraseñas** de los nodos DICOM y de la IA del informe solo van si marca *Llevar las contraseñas*: en ese caso el archivo las lleva en texto claro, así que guárdelo con cuidado. La parte del servicio, los nodos y la automatización exigen el permiso de configurar el ordenador.

### Instalar y desinstalar en Windows

El instalador pregunta por dos carpetas: la **del programa** (sugiere `AppData\Local\Programs\Ipe` del usuario; puede ser otro disco, como `D:\Ipe`, pero no Archivos de programa, porque se instala sin administrador) y la **de la base de datos** (sugiere la actual; puede ser otro disco o un disco externo, pero fuera de la carpeta del programa). En una actualización, las dos vienen ya rellenadas con las anteriores. Si la base de datos actual ya tiene estudios y la carpeta elegida está vacía, el instalador no cambia y avisa: para llevar los estudios, use **Configuración ▸ Base de datos ▸ Cambiar la carpeta de la base de datos de este ordenador…**, que mueve los archivos: con **Mover los archivos**, la base de datos se mueve la próxima vez que el programa se abra, antes que cualquier otra cosa (con el programa abierto Windows no deja tocar la base de datos); si algo falla, lo que ya se había movido vuelve y nada cambia. **Solo apuntar** pasa a usar la base de datos que ya esté en la carpeta elegida. Por la línea de comandos: `ipe-cli set-data-dir CARPETA`.

Para desinstalar: **Configuración de Windows ▸ Aplicaciones ▸ Aplicaciones instaladas ▸ Ipê ▸ Desinstalar** (o el Panel de control ▸ Programas y características). Se va el programa, con los accesos directos y el enlace ipe://. La base de datos, los estudios, los informes y la configuración se quedan: son suyos. Para borrarlos también, elimine la carpeta de la base de datos y la carpeta `AppData\Local\DicomViewer` después de desinstalar.

### Instalar en Linux

**Con los paquetes del release (0.100.6)**: en GitHub, la página de releases ofrece dos maneras, las dos sin Python:

- **Paquete `.deb`** (Debian, Ubuntu, Mint…): `sudo apt install ./Ipe-<versión>-linux-amd64.deb`. Se instala en `/opt/ipe`, con el comando `ipe-viewer`, el icono y el acceso directo **Ipê** en el menú de aplicaciones; `apt` instala las bibliotecas de ventana que falten. Actualizar es instalar el `.deb` nuevo; quitar, `sudo apt remove ipe-viewer`.
- **Portátil** (`Ipe-<versión>-linux-portable.tar.gz`, cualquier distribución): extraiga y ejecute `Ipe/install.sh`. Se instala para su usuario, sin administrador (el programa en `~/.local/share/ipe/programa`, el comando `ipe-viewer` en `~/.local/bin`, el acceso directo en el menú). `install.sh --system` instala para todos los usuarios en `/opt/ipe` (pide la contraseña de `sudo`); `install.sh --uninstall` lo quita. También se puede ejecutar `Ipe/Ipe` sin instalar.

El comando se llama `ipe-viewer` porque `ipe` ya es el nombre de otro programa (un editor de dibujos) en las distribuciones. Instalar, actualizar o quitar el programa no toca los estudios, la base de datos ni la configuración (`~/.local/share/DicomViewer` y `~/.config/DicomViewer`).

Desde el código: en la carpeta de Ipê, `./instalar.sh` y luego `./executar.sh`. Necesita un Linux con **glibc 2.34 o más reciente** (Ubuntu 22.04, Debian 12, Fedora 35 o posterior), porque el Qt de Ipê no tiene paquete para sistemas más antiguos: el script avisa y se detiene. Busca por sí solo un **Python 3.10 o más reciente del sistema** (no el de Anaconda, que suele aparecer antes en la ruta y ser más viejo), rehace el entorno `.venv` si se creó con un Python antiguo e instala las bibliotecas de ventana que Ubuntu no trae (`libxcb-cursor0` y compañía, con `sudo`). La versión portátil de Linux prescinde de Python, pero también necesita esas bibliotecas.

### Comprobar y reconstruir la base de datos (0.100.117)

**Configuración ▸ Base de datos ▸ Comprobar y reconstruir la base de datos…** (administrador) hace lo que hace el *Rebuild Database* de OsiriX/Horos, sin perder lo que solo existe en Ipê: comentarios, listas, mediciones, imágenes clave, informes y resultados de IA se vinculan al estudio por el UID y nunca se borran.

- **Comprobar** (empiece por aquí; no cambia nada) muestra cuántas imágenes de la base de datos perdieron el archivo (en el Storage y referenciadas), cuántos archivos hay en el Storage sin estar en la base de datos, las series y estudios vacíos, los pacientes sin estudio, las series sin miniatura y las carpetas vacías. **Guardar el informe…** graba la lista con las rutas.
- **Reconstrucción parcial** arregla lo que encontró la comprobación: indexa los archivos sueltos del Storage, quita de la base de datos las imágenes del Storage cuyo archivo desapareció, limpia los vacíos, rehace las miniaturas y borra las carpetas vacías. Las imágenes **referenciadas** que no están en su lugar solo se quitan si marca la opción: un disco externo o un pendrive desconectado vuelve a funcionar cuando se conecta.
- **Reconstrucción completa** vuelve a leer la cabecera de todos los archivos y actualiza el índice (paciente, estudio, series, imágenes). Antes, graba una copia del índice en la carpeta de datos, en `Backups`. En una base de datos grande tarda: se puede **Detener** y luego **Continuar donde se detuvo**.

En el servidor, por la línea de comandos: `ipe-cli banco conferir`, `ipe-cli banco parcial` (con `--referenciados` para quitar también los referenciados), `ipe-cli banco completa`, `ipe-cli banco continuar` e `ipe-cli banco restaurar-indice <copia>` (devuelve el índice a como estaba antes de la reconstrucción completa). En Ipê cliente no hay reconstrucción: quien guarda la base de datos es el servidor.

### Aviso de IA no instaladas (0.100.121)

Al abrir, si el ordenador no tiene las IA instaladas (la **segmentación de órganos** (TotalSegmentator) o los **modelos extra** (MedSAM2, autoPET, BraTS, FLAMeS, médula)), Ipê avisa de lo que falta y ofrece **Instalar la segmentación** o **Instalar los modelos extra**, o **Más tarde**. El aviso vuelve cada vez que el programa se abre, hasta que todo esté instalado. Marque **No volver a avisarme** para que pare; para activarlo de nuevo, **Ayuda ▸ Avisar cuando falte instalar las IA**. Los modelos de investigación (próstata) y la alineación de la dinámica de la mama son opcionales y no entran en el aviso.

### Limpiar la caché de Ipê (0.100.120)

**Configuración ▸ Base de datos ▸ Limpiar la caché de Ipê…** borra lo que el programa guarda solo de paso y rehace por sí mismo. La ventana muestra el tamaño de cada elemento y limpia solo lo que esté marcado:

- **Memoria de imágenes del visor**: las imágenes ya leídas; vuelven al abrir el estudio.
- **Estudios descargados del servidor** (solo en el modo cliente; viene desmarcado): el servidor sigue con todo y el estudio se descarga de nuevo al abrirlo. Quedan en el ordenador los estudios **abiertos**, los **protegidos (candado)** y los que el servidor **no tiene completos** (el programa comprueba cada uno con el servidor antes de quitarlo).
- **Carpetas temporales olvidadas**: restos de las IA y de los informes de cuando el programa se cerró a medias, detenidos desde hace más de 6 horas.
- **Actualizaciones ya descargadas**: los instaladores de las versiones antiguas.

Nunca se tocan la base de datos, los estudios de este ordenador, la papelera, la configuración ni los modelos de IA. El límite de la caché del servidor (Configuración ▸ Modo de uso ▸ *Caché local*) sigue vigente: esta ventana sirve para liberar espacio al instante.

## Ayuda

**F1** (fuera de un estudio), el botón **Ayuda** de la pantalla de inicio o **Ayuda ▸ Guía del usuario (PDF)** abren esta guía en el lector de PDF del ordenador, **en el idioma del programa** (portugués, inglés o español; si no existe la del idioma elegido, abre la portuguesa). **Ayuda ▸ Acerca de Ipê…** muestra la versión. Dentro de un estudio, F1 es de la película (capítulo 12).

Las figuras de esta guía son pantallas del propio programa, rehechas con cada versión, con estudios reales **anonimizados** (pacientes EJEMPLO, fechas desplazadas, sin institución). Las pantallas son de la interfaz en portugués; en otro sistema (Windows o Linux) la fuente y el dibujo de las ventanas cambian un poco; los botones y menús son los mismos.

## Lo que el programa nunca hace con el original

- Exportar, empaquetar, anonimizar y corregir etiquetas (tags) generan archivos nuevos; el original queda intacto.
- La única función que reescribe un archivo de paciente es la compresión sin pérdida, y solo después de comprobar píxel a píxel que la imagen es idéntica.
- Borrar un estudio y borrar una serie eliminan archivos, y solo los que están dentro del Storage del programa. Un archivo solo referenciado no se toca.
- Lo que el programa graba *en* el estudio (captura de la lesión, película en el estudio, reconstrucciones guardadas) entra como **serie nueva**; las series originales no cambian.

# La pantalla de la base de datos

## Lista de estudios

La tabla central lista los estudios de la ubicación seleccionada. Encima: el campo **Buscar**, el botón **Columnas ▾** (elige qué columnas aparecen) y **Limpiar filtros**. El panel de la derecha muestra las series del estudio seleccionado.

![La pantalla de la base de datos con los estudios de ejemplo (anonimizados). A la izquierda, las ubicaciones y el banco de casos; a la derecha, las series y los comentarios del estudio elegido.](banco.png)

Clic derecho en un estudio (o en varios seleccionados), ordenado en grupos desde la 0.99.78:

- **Abrir**, **Abrir eligiendo series…** e **Informe…** arriba;
- **Organizar ▸** listas de casos, prioridad, subespecialidad, estado del estudio, comentario y la base de datos (personal o compartida);
- **Documentos ▸** adjuntar PDF o imagen, los documentos del estudio y el historial;
- **Enviar a ▸** un nodo ▸ *como este programa* o *como* una de las identidades registradas (capítulo 9), y **Exportar…**;
- **Película ▸**, solo cuando el estudio tiene imágenes clave o película guardada;
- **Herramientas ▸** **Anonimizar una copia de este estudio…** (exporta anonimizado o guarda una copia anonimizada en la base, capítulo 14), **Corregir etiquetas…** y, solo en mamografía, **Borrar implante**;
- al final, **Proteger** (o **Quitar protección**, si ya está protegido) y **Borrar de la base…**.

### Recoger los paneles de los lados

Los dos paneles a los lados de la lista — **Ubicaciones y listas**, a la izquierda, y **Series y comentarios**, a la derecha — se recogen en una **tira en el borde**, como los paneles de Weasis: botón **◂/▸** en el título del panel. Recogido, queda la tira con el nombre escrito de lado; un clic en ella (o en la flechita) trae el panel de vuelta, del tamaño que tenía. La lista de estudios queda con todo el ancho.

El botón **Listas** de la barra abre y recoge el panel izquierdo, y **Ver ▸ Mostrar Ubicaciones y listas / Mostrar Series y comentarios** hace lo mismo en el menú. Cada usuario tiene su estado, y el programa se abre como quedó la última vez.

## Panel de series

- Alterna entre icono y lista con el botón del encabezado; la elección queda guardada.
- Clic derecho en una serie: **Ocultar** (reversible — la serie desaparece de la lista y del visor, y el botón **Ocultas** la trae de vuelta) o **Borrar** (quita de la base y los archivos que están en el Storage). El programa rechaza borrar la última serie de un estudio y cualquier serie de un estudio con candado.
- **Enviar N serie(s) a ▸** un nodo ▸ como… — envía **solo las series seleccionadas** (Ctrl+clic o Shift+clic para elegir varias).
- Todavía en el clic derecho: marcar las series seleccionadas como dinámica (vale para TC y RM) y separar una serie que trae todas las fases juntas.
- Capturas y series que el propio programa guardó (la captura de la lesión, mapas y reconstrucciones guardados) aparecen con miniatura, como las demás.

## Ubicaciones

El panel **Ubicaciones**, a la izquierda, cambia entre bases diferentes (por ejemplo, la base local y un servidor central de la intranet). Se recoge, y recogido sigue diciendo en qué ubicación está. Una ubicación por vez.

## Banco de casos

Justo debajo de las ubicaciones está el árbol del **Banco de casos**: carpetas y listas. Tres tipos de lista, elegidos al crearla — Normal, Reunión e Inteligente (filtro). El capítulo 7 trata las dos últimas.

Botones: **+ Lista**, **+ Carpeta**, **▶ Modo reunión**. El clic derecho en el árbol abre los mismos elementos más renombrar, descripción, mover, exportar y eliminar.

## Comentarios y protección

- **Agregar comentario** escribe una nota en el estudio, que aparece en la lista.
- El **candado** protege el estudio: no entra en la limpieza automática y no se puede borrar mientras esté protegido.
- **Historial del estudio…** (clic derecho en el estudio ▸ Documentos) muestra quién hizo qué en **este** estudio — abrió, descargó, exportó, envió, imprimió, cambió de base, borró imagen, asumió el informe — y cuándo se crearon y firmaron los informes.

## Botones de la pantalla inicial

| Botón | Qué abre |
|---|---|
| Importar | importar carpeta, archivos o ZIP |
| PACS | búsqueda y descarga (Ctrl+Shift+F) — capítulo 9 |
| Gestión | comprobar si los estudios de las modalidades están en el PACS — capítulo 10 |
| Abrir / Enviar / Exportar | acciones sobre los estudios seleccionados |
| Imprimir | el compositor de película (Ctrl+P) — capítulo 12 |
| Impresiones | lo que las modalidades mandaron imprimir y lo que se montó aquí |
| Informe | el informe del estudio seleccionado — capítulo 11 |
| Listas / Reunión | el banco de casos y el modo reunión |
| Ocultar | oculta los datos del paciente en todo el programa |
| Borrar | borra los estudios seleccionados |
| Monitor | la configuración de monitores (no abre estudio) |
| Configuración / Usuarios / Ayuda | preferencias, perfiles y esta guía |

# El visor

Cada estudio se abre en una pestaña con la barra de herramientas arriba, la tira de miniaturas de las series a la izquierda y los cuadros en el centro. Al final de la barra está el bloque de las **aplicaciones del estudio** (MPR, 3D, Dinámica, Fusión, MN): cada una aparece solo cuando sirve al estudio abierto, según la modalidad, la región del cuerpo (de BodyPartExamined y de las descripciones) y el tipo de serie (angio, T1 3D, T2 3D, dinámica, volumen). En una mamografía no hay MPR, 3D, Fusión ni MN; en una RM de mama aparece la Dinámica. El botón **Aplicaciones** las enumera todas, incluso las que quedaron fuera, con el motivo, y se ejecutan igualmente. Clic derecho en una aplicación: **Automático**, **Siempre** o **Nunca**, en todos los estudios o solo en los estudios de esa región. El orden, los modos y el diccionario de regiones están en Configuración ▸ Visor ▸ *Barra de herramientas y aplicaciones* y Configuración ▸ Protocolos de estudio ▸ *Regiones del cuerpo* (con una casilla para probar descripciones).

![TC de abdomen en fase portal, con los órganos y los segmentos hepáticos de la segmentación de IA (TotalSegmentator) superpuestos.](visualizador_tc_orgaos.png)

## Ratón

La herramienta del botón izquierdo es la que esté encendida en la barra. Los otros botones, la rueda y los clics se configuran en Configuración ▸ Visor ▸ Ratón. De fábrica:

| Gesto | Qué hace |
|---|---|
| Izquierdo arrastrando | la herramienta elegida en la barra (de fábrica, ventana/nivel) |
| Derecho arrastrando | zoom |
| Derecho haciendo clic | menú del cuadro |
| Central arrastrando | mover la imagen (desplazar) |
| Central haciendo clic | ajustar a la ventana |
| Rueda | pasar los cortes |
| Shift mantenido | el izquierdo se vuelve cursor 3D (sin necesidad de hacer clic: mover el ratón ya encuentra el punto en los otros cuadros) |
| Ctrl mantenido | el izquierdo se vuelve desplazar (sube y baja los cortes) |

Shift y Ctrl toman prestado el botón izquierdo: la herramienta elegida en la barra no cambia, y al soltar todo vuelve a lo que era. Qué tecla hace qué se elige en Configuración ▸ Visor ▸ Atajos de teclado (Shift / Ctrl / Alt / Ninguna).

## Las herramientas

La herramienta del botón izquierdo se elige en la barra, en el menú del botón derecho del cuadro —en **Herramienta del botón izquierdo ▸ Navegar** (lo que mueve la imagen), **▸ Medir** (lo que mide) y **▸ Dibujar** (flecha, texto, lápiz, pincel)— o haciendo clic en la esquina que muestra la herramienta actual.

![La barra del visor. Las aplicaciones (MPR, 3D, composición, Genant…) aparecen al final de la barra solo cuando sirven al estudio abierto.](barra_ferramentas.png)

### El menú del botón derecho en el cuadro (0.99.78)

Ordenado para caber de un vistazo:

- **arriba, lo que depende del lugar donde se hizo clic**: la medición bajo el ratón (borrar, borrador, lesión, referencia, reflejar, clonar, perfil), *Nódulo pulmonar aquí* (TC de tórax), *Hallazgo BI-RADS aquí* y *Encontrar el implante* (mamografía), *Eje de simetría* (RM de mama, o cuando hay ROI en el corte), *Sustracción digital (DSA)* (solo angiografía, XA/RF), *Numeración de la columna*, *Cardíaco 4D*, guardar la reconstrucción del MPR y *Quitar la mesa de la TC*;
- **Marcar imagen clave ★** y **Copiar la imagen**;
- **Imagen ▸** ventana (solo los presets de la modalidad del cuadro), color (los más usados de la modalidad y *Más colores ▸* con los demás), invertir, filtro, girar/reflejar, mosaico de cortes, histograma, ajustar a la ventana y restaurar;
- **Cuadro ▸** fusionar este cuadro sobre otro, líneas de corte, grupo de sincronización, cine y la lista de las mediciones de la serie;
- **Anotaciones ▸**, **Herramienta del botón izquierdo ▸** e **Información DICOM (tags)…**;
- al final, separado, lo que borra: **Borrar medidas de este corte** y **Borrar esta imagen…**.

Las aplicaciones de IA (órganos, columna, nódulos…) están solo en los botones de la barra y en el botón **Aplicaciones**. Cada aplicación tiene su dibujo en la barra, y las que usan IA llevan un ✦ dorado en la esquina.

La columna *tecla* de abajo es una sugerencia: casi toda la lista de atajos viene vacía de fábrica, y cada tecla se elige en Configuración ▸ Visor ▸ Atajos de teclado (capítulo 14). De las herramientas, solo el zoom por cuadrante tiene tecla de fábrica (Q).

| Herramienta | Tecla | Para qué sirve |
|---|---|---|
| Ventana / nivel | W | brillo y contraste |
| Zoom | Z | acercar y alejar |
| Desplazar (pan) | P | mover la imagen en el cuadro |
| Recorrer | S | pasar los cortes |
| Regla | M | distancia en mm |
| Ángulo / Cobb | A / Shift+C | ángulo entre dos líneas |
| ROI elíptica / rectangular / poligonal | E / Shift+E / G | media, desviación, área |
| Intensidad | V | valor del píxel (HU, SUV, señal) y curva de la dinámica |
| Flecha / Texto / Lápiz | Shift+A / T / B | marcar y anotar |
| Cursor 3D | X | el mismo punto en los otros cuadros |
| Segmentar 3D | Shift+V | hace crecer la lesión y mide volumen, ejes, SUV, TLG |
| Seleccionar | — | no crea nada: elige, mueve y edita lo que ya está dibujado |
| Lupa | U | aumento local, mientras se mantiene el botón |
| Zoom por cuadrante | Q (de fábrica) | recorre los cuatro cuadrantes en tamaño real |

## Cuadros, series y diseño

- Diseño en la barra, o el menú **Ver ▸ Diseño de los cuadros** (de 1×1 a 4×4). El diseño inicial está en Configuración ▸ Sistema ▸ Al abrir el programa.
- `[` y `]` (sugerencia) cambian la serie del cuadro activo. Cambiar de secuencia mantiene la posición: el corte nuevo pasa por el punto que estaba a la vista.
- Arrastrar una miniatura de la tira a un cuadro pone esa serie allí.
- **Sello IA (0.100.14)**: la miniatura recibe un sello lila **IA** en la esquina superior cuando la serie es resultado de una IA (SEG, tablas, imágenes de verificación) o fue analizada por una (la serie de donde salió la SEG). Pase el ratón para ver qué herramientas. En el navegador, el mismo sello aparece en la tira de series.
- La esquina inferior derecha del cuadro dice el plano (se puede hacer clic), la fase de la dinámica, la ventana y el FOV.
- **Tamaño de letra de las anotaciones (0.100.40)**: en la flechita del botón **Anot.**, *Letra más grande*, *Letra más pequeña* (de 10 en 10 %, de 60 a 250 %) y *Letra de tamaño normal* cambian el texto de las esquinas (paciente, serie, ventana, FOV) en todas las ventanas; el menú muestra el tamaño en uso. Las tres acciones pueden recibir una tecla en Configuración ▸ Visor ▸ Atajos. Es el mismo ajuste de *Tamaño de letra de la información en las esquinas*, en la configuración, donde también está el tamaño de letra de las mediciones.
- **Zoom escrito**: doble clic en el "Zoom N %" de la esquina abre el menú: *Ajustar a la ventana*, *1 píxel de la imagen = 1 píxel de la pantalla (1:1)*, 50 a 400 % y **Escribir el zoom…** (acepta `150`, `150%`, `2x`, `1:1` y `2:1`). El número es el mismo de la esquina: 100 % es la imagen ajustada al cuadro.
- **Cortes no mostrados**: al recorrer rápido (rueda, arrastre, Shift), la imagen avanza varios cortes entre dos repintados de la pantalla y los del medio nunca aparecen. Cuando eso ocurre, junto a la barra de posición aparece durante un segundo y medio, en ámbar, "N corte(s) no mostrado(s)". Ir a un corte (clic en la barra, doble clic en el número de la imagen, sincronización) no avisa.

![RM de cráneo en el protocolo de visualización: cuatro series, con las líneas de referencia de un cuadro en los otros.](layout_rm_cranio.png)

## Sellos de integridad

Una franja en lo alto del cuadro avisa de lo que puede hacer la imagen inadecuada para leer. Hacer clic en ella explica cada sello.

| Sello | Color | Cuándo |
|---|---|---|
| COMPRESIÓN CON PÉRDIDA — inadecuada para el informe | rojo | mamografía comprimida con pérdida (por el atributo Lossy Image Compression o por la sintaxis del archivo), con el método y la tasa. El ACR y la FDA no la aceptan para la lectura final |
| Compresión con pérdida | ámbar | cualquier otra modalidad comprimida con pérdida |
| Modality LUT en tabla | rojo | el archivo convierte los píxeles por tabla; Ipê aplica solo slope/intercept, así que HU y densidades pueden no ser las reales |
| PACIENTES DISTINTOS EN EL DISEÑO | rojo | los cuadros de la pantalla tienen estudios de pacientes distintos (nombre o ID no coinciden) |
| Píxel no cuadrado | ámbar | espaciamientos distintos en la fila y en la columna |
| Imagen derivada | ámbar | ImageType DERIVED\SECONDARY (reconstrucción, captura, mapa) |
| Sincronía entre referenciales distintos | ámbar | el cuadro está en un grupo de sincronía (actual) con cuadros de otro Frame of Reference: otro estudio, o el paciente reposicionado. Se mueven por el desplazamiento de cuando se enlazaron, no por registro |

La reconstrucción (MPR, MIP) hereda el sello de compresión de la serie de origen.

**En la copia.** En Configuración ▸ Visor ▸ Anotaciones, *En la copia (Ctrl+C)* elige el nivel de anotación de la imagen copiada, separado del de la pantalla; por ejemplo, Parcial 1 (sin los datos del paciente) para clase, sin necesidad de anonimizar el archivo. El *sello mínimo* pone al pie de la copia la serie, la ventana, la escala, el procesamiento aplicado (MIP 10 mm, sustracción, DSA, filtro, fusión) y los sellos graves, incluso con las anotaciones ocultas. El elemento *Sellos de integridad* está en Configuración ▸ Visor ▸ Anotaciones; los sellos rojos aparecen en cualquier nivel, salvo en Ninguno.

## Ventana: del archivo, escrita y presets por modalidad

El menú de la ventana (flecha del botón Ventana, o doble clic en el "W … L …" de la esquina) ofrece:

- **Del archivo (Switch WL)**: todas las ventanas grabadas en el DICOM, con el nombre (la mamografía suele traer NORMAL, HARDER, SOFTER) y las VOI LUT. La acción *Switch WL* (sin tecla de fábrica; elija la suya en Atajos de teclado) recorre esas ventanas en ciclo; en la mamografía cambia a la vez las proyecciones a la vista. El nombre de la ventana aparece junto al W/L hasta que se arrastra la ventana.
- **Escribir la ventana…**: ancho y nivel, por ejemplo `400 40` o `1500/-600`.
- **Guardar la ventana actual como preset…**: graba la ventana a la vista en la lista de la modalidad del cuadro. RM, mamografía, PET y las demás pueden tener lista propia; sin ella vale la lista general (la de TC). Las teclas 1–9 aplican el preset de la modalidad del cuadro activo. Las listas también se editan en Configuración ▸ Visor ▸ Presets de ventana, eligiendo la lista arriba. Los protocolos de visualización siguen usando la lista general.

## Enviar a la película: F1 y F2

Con el foco en un cuadro del estudio:

| Tecla | Qué hace |
|---|---|
| F1 | manda la imagen del cuadro a la película, con la ventana, el zoom y el giro que tiene en la pantalla |
| F2 | manda la serie del cuadro, entera o un intervalo, elegido en una ventana |

Las dos vienen de fábrica y se pueden cambiar en Configuración ▸ Visor ▸ Atajos de teclado. Fuera del estudio (en la lista de la base de datos, por ejemplo), F1 vuelve a abrir esta guía. El botón **Película** de la barra hace lo mismo que F1, y su menú ofrece *todos los cuadros* e *imágenes clave del estudio*.

## Sincronizar cuadros

Botón **Sincronizar**. La flecha de al lado abre las opciones: Automática en el mismo estudio, Ventana/nivel, Zoom y desplazamiento, Líneas de referencia y Tira de series. Todas se guardan entre sesiones.

![El panel Previos (a la derecha) enumera los otros estudios del paciente; desde aquí vienen a la pestaña y se enlazan al estudio actual.](anteriores.png)

**Alinear automáticamente con el otro estudio** (menú de la sincronización) hace el **registro rígido** —rotación y traslación en 3D— entre dos estudios del mismo paciente: abra el otro estudio en un cuadro al lado (botón Previos) y deje activo el cuadro del estudio actual.

- La medida de similitud se elige sola: **correlación** para la misma modalidad y la misma secuencia; **información mutua** para modalidades o secuencias distintas (TC × RM, T1 × T2, PET × TC). La barra de estado dice la rotación, el desplazamiento y la calidad (buena, aceptable, débil).
- Los cuadros pasan a recorrerse juntos por el desplazamiento del centro. Cuando el otro estudio está **girado 1° o más**, el programa ofrece **grabarlo en el plano de este**: una serie nueva en el otro estudio ("… · registrada el <fecha>"), con la geometría y el Frame of Reference de este; así los dos avanzan juntos corte a corte, y el cursor 3D, las líneas de referencia y las ROI caen en el mismo lugar. Los archivos originales no cambian.
- El registro (la matriz entera) queda guardado para los dos estudios; ajustar a mano con **Alt+rueda** hace que vuelva a valer solo la traslación.
- Tarda de 5 a 15 s en CPU (se detiene solo a los 90 s con el mejor resultado; el botón Cancelar detiene antes). Rígido quiere decir la misma forma: sirve bien para cráneo, columna y huesos; la mama y el abdomen se deforman entre estudios, y el resultado en estos es aproximado.
- **Verificar el registro** (menú de la sincronización ▸ *Verificar el registro con el otro estudio*): el otro estudio va encima del cuadro activo, en gris y con su propia ventana, ya con la matriz del registro guardado: **Tablero** (casillas alternas de uno y de otro: el borde no puede tener escalón), **Cortina** (la divisoria sigue al ratón), **Diferencia** (lo que queda claro es lo que no se alineó) o **Mezcla 50 %**. La serie ya grabada en el plano de este estudio entra sin la matriz (ya está alineada). *Desactivar* la quita.
- **Verificado en el archivo**: en una RM de cráneo 3D real, con rotación y traslación conocidas aplicadas, el registro acertó con un error medio de 0,4 mm (máximo 0,5 mm) en 6 s; dos secuencias de la misma sesión (FLAIR y SWAN) dieron 0,5° y 1,6 mm.

## Mediciones

El botón **Mediciones** abre una ventana con todo lo que se midió en el estudio: serie, imagen, tipo, valor, lesión y texto. Hacer clic en una fila lleva a la imagen con la medición ya seleccionada. La lista sale de la base de datos, no de los cuadros abiertos: una medición hecha la semana pasada está ahí.

![Regla y elipse en la TC: la regla da la longitud; la elipse, la media ± desviación estándar, mínimo, máximo y área.](medidas.png)

- La herramienta **Seleccionar** edita lo que ya existe: un clic elige, arrastrar mueve, arrastrar el extremo redimensiona, Supr borra.
- **Editar lesión…** (o doble clic en una fila de segmentación) reabre la segmentación con el umbral y el pezón que usó (capítulo 6).
- Las mediciones salen a una hoja de cálculo (CSV/Excel) y a DICOM SR.
- **Borrador**: clic derecho en la medición ▸ *Borrador*. La medición queda **punteada**, en la pantalla y en la base de datos, pero **no sale**: no va al SR, al GSPS, al informe, a la hoja de cálculo, al visor exportado ni al seguimiento de lesiones. Desmarcar la convierte en una medición que vale. En Configuración ▸ Visor ▸ Texto y marcas sobre la imagen, *Las mediciones nuevas empiezan como borrador* hace que toda medición nazca así (las que se vuelven número; no calibración ni columna).
- **Perfil de intensidad**: clic derecho en una regla o polilínea ▸ *Perfil de intensidad…* muestra el gráfico del valor (HU en la TC) a lo largo de la línea, en mm, con mínimo, máximo y media: la transición de densidad, la pared de una lesión, el realce de un vaso. El gráfico acompaña a la línea cuando se mueve, y *Copiar valores* lleva la tabla a la hoja de cálculo.
- **Borrar esta imagen…** (clic derecho en el cuadro) quita solo esa imagen del estudio: la duplicada, la captura equivocada. Pide el permiso de borrar, se rechaza en un estudio con candado y en la última imagen de la serie, se lleva consigo las mediciones y la imagen clave y queda en el registro de acceso.

### Regla 3D, incertidumbre y ROI de referencia

- **Regla 3D** (menú Mediciones): haga clic en el punto A en un corte y en el punto B en otro corte, o en otro cuadro, como el axial y el sagital. La distancia sale en 3D, con las componentes derecha-izquierda, anteroposterior y craneocaudal; en dos puntos del mismo corte, la etiqueta dice "(2D)". El tercer clic empieza una regla nueva.
- **Cortes gruesos**: la regla dibujada en una reconstrucción de cortes gruesos (el sagital de un axial de 5 mm) avisa cuando su dirección tiene píxel de 5 mm: la medición craneocaudal hereda ese error, la anteroposterior no. En la imagen original, la regla menor que el grosor del corte también avisa.
- **Incertidumbre** (Configuración ▸ Visor ▸ Texto y marcas sobre la imagen): muestra ± el píxel en la dirección de la regla y ± perímetro × píxel ÷ 2 en el área de la ROI. Desactivada de fábrica; los avisos de arriba aparecen siempre.
- **Clonar la ROI**: clic derecho en una ROI ▸ *Clonar esta ROI en los otros cuadros*. Cada cuadro a la vista recibe una ROI nueva **en la misma posición en el paciente** (en mm, no en el mismo píxel: una serie con otra matriz u otro FOV recibe la ROI del tamaño correcto), en el corte más cercano a su centro, con la media, la desviación y el área de la imagen de allí: T2 → ADC, pre → post, actual → previo. En el mismo estudio vale el Frame of Reference; entre estudios distintos, enlace antes los cuadros en un grupo de sincronización (o registre): sin referencial común, la barra de estado dice que no copió y por qué. Tampoco copia a un plano no paralelo ni a una serie que no cubre ese punto.
- **Eje de simetría a mano** (0.99.61): cuando la línea media del cuerpo hallada sola no sirve (paciente rotado, mama muy asimétrica), clic derecho en el lugar del eje ▸ *Eje de simetría (ROI reflejada)* ▸ *Marcar el eje aquí*. Vale para la serie, en este ordenador, aparece como una línea azul punteada en el axial y en el coronal, y *Volver al eje automático* lo deshace.
- **ROI reflejada**: clic derecho en una ROI ▸ *Reflejar al otro lado (razón lesión / contralateral)*. La ROI nueva ("Contralateral") va al espejo en el plano sagital medio: en un axial o coronal, la línea media del cuerpo en esa imagen; en una serie sagital (RM de mama bilateral), el medio del rango de cortes, y el cuadro va al corte del otro lado. La ROI original pasa a mostrar *lesión / contralateral* (su media sobre la del otro lado), en cualquier mapa: ADC, realce, BPE. La barra de estado dice dónde quedó el eje. Plano oblicuo, serie que no cubre el otro lado e imagen en color no reflejan, y la barra dice por qué.
- **ROI de referencia**: clic derecho en una ROI ▸ *Usar como ROI de referencia*. Las otras ROI de la serie pasan a mostrar su media en % de la referencia (lesión/hígado, lesión/aorta, lesión/músculo). Solo una por serie; queda marcada "Referencia (100 %)" y acompaña si usted la mueve.

## Escala de las mediciones y calibración

Para medir en milímetros el programa necesita saber el tamaño del píxel. En la TC, la RM y la mamografía eso viene del archivo (PixelSpacing). En la ecografía no: la escala cambia en cada imagen, porque la profundidad y el zoom cambian durante el examen, y el aparato graba una región calibrada por rectángulo de la pantalla. El programa lee esa región y mide en milímetros sin que usted configure nada.

La esquina inferior izquierda del cuadro dice de dónde viene la escala, y se puede hacer clic en ella:

| Lo que aparece | Qué significa |
|---|---|
| Escala: región de la ecografía | vino de la tag del propio aparato, imagen por imagen |
| Escala: calibrada en esta imagen | usted calibró a mano aquí; vale solo en esta imagen |
| Escala: calibrada en la serie | usted calibró a mano y marcó que valga en toda la serie |
| Sin escala — mediciones en píxeles | el archivo no trae el tamaño del píxel y nadie calibró; la medición sale en px, diciendo que es px |

Para calibrar a mano: herramienta **Línea de calibración**, trace sobre una distancia que usted conozca (la regla de la imagen, por ejemplo) e indique la longitud real. La ventana pregunta también hasta dónde vale la calibración: solo esta imagen o toda la serie. En la ecografía el valor predeterminado es solo esta imagen; en las otras modalidades, la serie.

- El orden de confianza es: calibración de esta imagen, calibración de la serie, región de la ecografía, espaciamiento del archivo. Quien calibra a mano ya vio que la tag no servía.
- Una imagen de doble panel tiene una región a cada lado: la medición usa la región en que está. Una medición que cruza de un panel al otro vuelve a píxeles: la distancia entre dos imágenes distintas no es distancia.
- La ventana del Doppler espectral no calibra distancia: sus ejes son tiempo y velocidad, y el programa la rechaza a propósito.
- La captura secundaria de ecografía (una captura de la pantalla del aparato) suele venir sin ninguna región: entonces la calibración manual es el camino.

## Mosaico de cortes en el cuadro

Clic derecho en el cuadro ▸ **Imagen ▸ Mosaico de cortes** ▸ 2 × 2, 3 × 3 o 4 × 4 (o el atajo *Mosaico de cortes en el cuadro*, que recorre los tamaños): el cuadro muestra cortes **seguidos** de la misma serie, a partir del actual (el primero, arriba a la izquierda, tiene el número en amarillo). Sirve para echar un vistazo a una serie volumétrica sin recorrer corte a corte, con otro cuadro al lado recorriéndose normal.

- La rueda **pasa la página**: el conjunto avanza junto (4, 9 o 16 cortes); los cuadros sincronizados acompañan por el primero.
- Ventana/nivel, invertir y la tabla de colores valen para todas las imágenes del mosaico. Las imágenes clave aparecen con ★.
- El mosaico es **solo para ver**: las herramientas de medición no actúan en él. **Doble clic** en una imagen vuelve al cuadro normal **en esa** imagen.

## Imágenes clave

K (sugerencia) marca y desmarca la imagen del cuadro como imagen clave; Shift+K muestra solo las marcadas. Entran en el informe en PDF y en la película con un clic.

**Grabar en el estudio (KO + GSPS).** Botón **Clave** ▸ *Grabar imágenes clave y anotaciones en el estudio*: las imágenes clave se vuelven un objeto DICOM **KO** (Key Object Selection, "Of Interest") y las mediciones, flechas y textos se vuelven un **GSPS** (estado de presentación), con el número de cada medición escrito al lado, calculado con la misma escala de la pantalla (calibración a mano, región de la ecografía, tag). Los dos quedan en el estudio, van al PACS junto con él y se abren en otros visores (Weasis, OHIF, la estación del aparato). Una medición **borrador** queda fuera.

- **Un KO que llega en el estudio** (de otro sistema, o el nuestro de vuelta del PACS) marca las imágenes clave aquí, una vez: desmarcar después no las trae de vuelta.
- **GSPS de otros sistemas**: con más de uno en el mismo estudio, aparece solo el más reciente; los otros quedan en el botón CAD/IA, desactivados. Nuestro GSPS, al reabrir, queda desactivado: las mediciones ya están en la base de datos y se dibujarían dos veces.
- **Traer las mediciones para editar**: en el botón CAD/IA, un SR o GSPS de otro sistema tiene *Traer las mediciones para editar*: regla, polilínea, polígono, punto y texto se vuelven mediciones de Ipê (editables, en el panel de mediciones, en el informe). El objeto original queda desactivado.

## Reconstrucciones: MPR, oblicuo, curvo y 3D

- **MPR** monta el volumen y abre los tres planos. También se puede reconstruir solo el cuadro activo en axial, coronal o sagital.
- La línea de orientación en la esquina del cuadro admite clic: elige el plano, y **Oblicuo** vuelve oblicuo el cuadro sin cambiar la imagen; a partir de ahí la herramienta **Girar plano** lo inclina.
- Grosor (slab) en la barra del MPR, con media, MIP o MinIP.
- MPR curvo (haga clic en los puntos a lo largo de un vaso) y 3D (renderizado de volumen, con cortes, escultura y exportación de malla STL/GLB/3MF).
- **Estructuras en 3D** (0.99.82): con el 3D abierto, el botón **Estructuras** de la barra del 3D (o el clic derecho ▸ *Estructuras segmentadas*) muestra como superficies de color todo lo que está segmentado en el estudio y activado: órganos de la IA, segmentos y lesiones del hígado, nódulos, lesiones segmentadas a mano, niveles ganglionares, SEG y RTSTRUCT de otros sistemas. Las estructuras acompañan el giro, el corte, el plano y la escultura del volumen; lo que está detrás del hueso del VR aparece apagado. Desactivar un objeto en la lista de CAD/IA lo quita del 3D la próxima vez que se active.
- El plano reconstruido sale siempre en la convención de lectura (axial con anterior arriba y la izquierda del paciente a la derecha), incluso cuando la adquisición fue sagital.
- **Quitar la mesa de la TC**: clic derecho en el MPR o en el 3D de una TC ▸ *Quitar la mesa de la TC (MPR y 3D)*. El programa encuentra el cuerpo (lo que pasa por el medio del volumen) y borra lo que está fuera de él, corte a corte: la mesa sale, los pulmones y las vías aéreas se quedan. Vale para los volúmenes montados de ahí en adelante (cierre y abra el MPR/3D); la serie original no cambia.

![MPR en los tres planos, con el cursor 3D y las estructuras de la segmentación también en los planos reformateados.](mpr.png)

![3D en el propio cuadro: MIP del PET de cuerpo entero (el modo, el preset, la opacidad y las vistas están en la barra de arriba).](3d_mip_pet.png)

> **El volumen se monta en la memoria.** En Configuración ▸ Sistema ▸ Rendimiento hay un techo; por encima de él el programa pregunta antes de montar. El 3D se ejecuta en la CPU, y el detalle (lado del volumen) también se ajusta allí.

# Varios monitores

El programa trata el conjunto de pantallas como una estación, no como varios visores independientes: pasar de etapa, cambiar de protocolo o cambiar el diseño vale para todo el conjunto.

## Configurar

Configuración ▸ Monitores ▸ Función, layout y orden de los monitores…. Cada pantalla recibe un rol:

| Rol | Qué va allí |
|---|---|
| Base de datos | la ventana principal, con la lista de estudios |
| Visor | los estudios abiertos |
| Comparación | los estudios anteriores, ya vinculados al actual |
| No usar | el programa no pone nada en esa pantalla |

La columna **Orden** dice cuál pantalla es la 1, la 2, la 3 — y ese número es el que usa la mamografía cuando la etapa dice "con 2 pantallas, mostrar en el Monitor 2". El botón **Ordenar por la posición en la mesa (izquierda → derecha)** es un buen punto de partida; un número repetido se rechaza. **Identificar monitores** hace parpadear el número en cada pantalla.

Con dos o más monitores marcados como Visor, el estudio se abre repartido entre ellos. Con uno solo, se abre como pestaña, como siempre.

- **Mover estudio actual al monitor** (menú Ver) lleva el estudio abierto a otra pantalla.
- **Traer todos los estudios de vuelta** devuelve todo a la ventana principal.
- La tira de series puede quedar solo en el primer monitor — Configuración ▸ Monitores ▸ *Función, layout y orden de los monitores…* ▸ *Tira de series solo en el primer monitor*, con tres opciones: solo en mamografía, siempre que el estudio se abre repartido, o nunca.
- La cuadrícula de cada pantalla se recuerda por tipo de estudio (capítulo 5, *La memoria del diseño*).

> **En Linux** el rol de los monitores depende de que X11 informe la geometría de las pantallas; en algunos entornos Wayland la identificación puede fallar.

# Mamografía: protocolos de visualización

La mamografía no usa el protocolo de visualización genérico de los otros estudios. Tiene una pestaña propia, con **etapas**: cada etapa es una disposición de cuadros, y pasar de etapa cambia todos los monitores al mismo tiempo. Es la manera en que realmente funciona la lectura de cribado: CC, luego MLO, luego comparación con el previo.

## Dónde está el editor

- Configuración ▸ Protocolos de estudio ▸ **Mamografía**;
- o, con una mamografía abierta, la última línea del combo **etapa:** en la barra del estudio: *Editar protocolos…*.

## Crear un protocolo desde cero

A la izquierda está la lista **Protocolos**: se usa el primero activo que coincide. Botones **+ Nuevo**, **Duplicar**, **Quitar**, **Predeterminado**.

1. **+ Nuevo** y póngale un **Nombre:** (p. ej.: "Cribado 2 pantallas").
2. **La descripción del estudio contiene:** — vacío vale para cualquier mamografía; `RASTREAMENTO|DIAGNOSTICA` coincide con cualquiera de las dos palabras. Esto es lo que elige el protocolo cuando se abre el estudio.
3. Marque **Activo**. Las otras tres casillas son de presentación: *Pared torácica hacia el centro* (refleja la imagen cuando hace falta, para que las dos mamas se miren), *Pegar la imagen al borde de la pared torácica* y *Zoom por cuadrante en todos los cuadros juntos*. **Alinear en vertical:** (0.99.61): *por el pezón* (de fábrica: en la misma línea de la pantalla, el pezón de las dos mamas queda a la misma altura) o *por el medio de la mama* (como era antes). **Doble clic** en una proyección muestra solo esa (1×1) y la reencuadra para el cuadro grande, sin la alineación con la otra mama; otro doble clic vuelve a la etapa.
4. En el grupo **Etapas**, **+ Etapa**. Póngale un **Nombre de la etapa:**; aparece en el combo del estudio (p. ej.: "CC actual × previa").
5. Defina el **Diseño** (filas × columnas) de la etapa.
6. Rellene los cuadros: o por el campo **En texto:**, o por la cuadrícula de combos, uno por cuadro.
7. Repita para las otras etapas y use ↑ y ↓ para ponerlas en el orden en que usted lee.

## La sintaxis de las celdas

Cada cuadro recibe un código. El orden es: proyección (opcional) + lado (obligatorio) + marcadores opcionales.

| Parte | Valores | Observación |
|---|---|---|
| Proyección | CC, MLO, ML, LM, XCCL, XCCM, AT, FB, SIO, SPOT, MAG, ANY | sin proyección = cualquiera. FB, SIO y ANY funcionan pero no aparecen en la lista de la pantalla |
| Lado | D (derecha) o E (izquierda) | obligatorio |
| Tomosíntesis | tomo o dbt | toma la pila de la tomo en vez de la 2D |
| Contraste (CEM) | rec, recomb, sub o cem | la imagen recombinada |
| Previo | ant / ant2 | ant = el estudio previo; ant2 = el previo del previo |
| Otro estudio (0.99.61) | US, RM, RM:texto | el cuadro muestra la **última ecografía** o la **última RM** del paciente (hasta la fecha del estudio, las de mama primero); en la RM, la sustracción o el poscontraste, o la serie cuya descripción tiene el texto después de los dos puntos (`RM:T2`) |

En el campo **En texto:**, las columnas se separan con `x` y las filas con coma:

```
1 × 2   CCD x CCE
2 × 2   CCD, MLOD x CCE, MLOE
2 × 2   CCD, CCD ant x CCE, CCE ant     (actual arriba, previo abajo)
1 × 2   CCD tomo x CCE tomo             (tomosíntesis)
1 × 2   CCD rec x CCE rec               (contrastada, recombinada)
2 × 2   CCD, US x CCE, RM               (mamografía con la última ecografía y la última RM)
```

Un código que el programa no reconoce se rechaza en el acto, con el mensaje "Código(s) no reconocido(s): …". En la pantalla del estudio, un cuadro sin definición muestra *(cuadro vacío en el protocolo)*, y una imagen que no existe muestra "… no encontrada (sin estudio previo)", en vez de quedar negro sin explicación.

## Repartir la etapa entre monitores

Dentro de la etapa: *En esta etapa, con [1 a 4 pantallas] mostrar en [Monitor N]*. Usted define, para cada número de pantallas, lo que va en cada monitor. El botón **Repartir solo** deshace eso y devuelve la etapa al reparto automático.

Sin disposición definida, el reparto automático sigue este orden: si las filas se dividen por el número de pantallas, cada pantalla lleva un bloque de filas (dos filas en dos pantallas = CC en una, MLO en la otra); si no, lo intenta por las columnas; si no, distribuye los cuadros en orden. Con menos imágenes que pantallas, cada pantalla recibe una.

## Usar en el estudio

Con la mamografía abierta, la barra **Mamografía:** trae el combo del protocolo, el combo **etapa:**, y ◀ / ▶ para avanzar. Las teclas de fábrica son **→** (etapa siguiente), **←** (etapa anterior) y **Q** (zoom por cuadrante). También en la barra:

![Mamografía en el protocolo de 4 proyecciones (CC y MLO, derecha e izquierda), con cada mama pegada al borde exterior del cuadro.](mamografia.png)

![El mismo estudio con la tomosíntesis activada en el primer cuadro: el indicador de abajo a la izquierda muestra el corte y la profundidad.](mamografia_tomo.png)

- **Cuadrante ↻** (Q) y **1:1**: lectura en tamaño real. Desde la 0.100.78 el cuadrante tiene **cuatro áreas**: posterior y superior → anterior y superior → posterior e inferior → anterior e inferior → la mama entera (Shift+Q vuelve). El cuadrante vale para todos los cuadros juntos de fábrica; el botón **Cuadrante junto** lo desactiva durante el estudio (solo el cuadro activo);
- **Lupa**: mantenga el botón; la rueda cambia el aumento;
- **Grosor: fino ▾**: slab de la tomosíntesis: 1, 5, 10 o 20 cortes, en MIP o media;
- **BE ⇄ Recomb.**: alterna baja energía y recombinada en la contrastada;
- **Implante**: corrige la prótesis en todos los cuadros (Alt+I); véase abajo;
- **Densidad…**: mide la densidad mamaria de lo que está en los cuadros (capítulo 6);
- **2D ⇄ tomo** salta entre la 2D y la tomosíntesis en la misma lista;
- **Mama en el cuadro** reencuadra la mama (véase abajo);
- **Zoom y desplazamiento** (0.99.61, el mismo botón de sincronía de la barra principal): activado, el zoom y el desplazamiento en un cuadro muestran el mismo lugar en las otras mamas, reflejado. **Desde la 0.100.78, en la mamografía todas las sincronías vienen desactivadas** (zoom y desplazamiento, ventana y recorrido de los cortes) y se guardan aparte de las otras modalidades: activarla aquí no la activa en la TC, y viceversa. El zoom por cuadrante (Q) sigue valiendo para los cuadros juntos (es del protocolo, no de la sincronía; el botón **Cuadrante junto** lo desactiva durante el estudio);
- **Invertir solo la mama** (0.99.61): invierte el tejido y deja el fondo negro, en todos los cuadros y en las etapas siguientes;
- **Hallazgos…** (0.99.64): clic derecho en la imagen ▸ **Hallazgo BI-RADS aquí** ▸ *Hallazgo nuevo* pone la marca "A1" y guarda la distancia al pezón; en la otra proyección, *A1* marca el mismo hallazgo. La tabla muestra, para cada hallazgo, la mama, las vistas, la distancia al pezón (media de las dos) y la localización: cuadrante (o unión, región central, retroareolar), hora del reloj mirando a la paciente de frente y tercio (anterior, medio, posterior). En la CC, el lado lateral es el de arriba (o el que dice el PatientOrientation); en la MLO, el superior. Elija el tipo y **Enviar al informe BI-RADS**: los hallazgos entran en el panel BI-RADS del informe, para completar descripción, tamaño y categoría; enviar de nuevo sustituye los mismos hallazgos, no los duplica;
- **★ Corte** (0.99.61): marca el corte de la tomosíntesis (o la imagen 2D) del cuadro activo como imagen clave; la barra de estado dice qué corte y el grosor. En Atajos ▸ Mamografía hay *ir al siguiente / anterior corte marcado*, para volver a las estrellas en una tomo de decenas de cortes;
- **✕** sale del protocolo.

### Implante (0.95; solo "corregir" desde la 0.96)

El botón **Implante** (Alt+I) encuentra la prótesis de cada cuadro y la **corrige**: el silicona baja al nivel de gris del tejido que la rodea, pero el detalle fino continúa: el tejido que está delante o detrás de la prótesis aparece, y el borde no se vuelve un escalón (método de la patente US 8.160.346). **La ventana (WW/WL) no cambia**: queda la que estaba antes de activar el botón, incluso si usted la había ajustado a mano. El antiguo "borrar" (área lisa) se eliminó.

Cómo se encuentra la prótesis: es la región clara de **borde nítido y forma convexa**, que ocupa del 5 al 85 % de la mama. Antes de buscar, el programa lee lo que el aparato escribe en la imagen: con **BreastImplantPresent = NO**, o en una proyección con el **implante desplazado** (rótulo terminado en ID, como RCCID) o de **compresión localizada / magnificación** (RSCC, LMSCC…), no busca, y la barra de estado dice por qué. Si aun así hay prótesis, clic derecho dentro del silicona → **Encontrar el implante desde aquí**.

Verificado en el archivo: 28 imágenes 2D de 5 estudios, 2 con prótesis: las 7 imágenes con el implante a la vista se encontraron, y ninguna de las otras 21. Sin la información del aparato, la búsqueda solo por la imagen confunde el borde de la pala de compresión localizada con una prótesis; en un aparato que no escriba nada de esto, use el clic. La cápsula muy calcificada deja un anillo claro y oscuro en el borde.

### Qué imagen entra en el cuadro

Para una celda MLOD, el programa busca la imagen de lado y proyección iguales y prefiere, en este orden: la que es "para presentación", la que se llama exactamente esa proyección, y por último la más reciente.

- Quien decide la proyección, cuando existe, es el rótulo que grabó el aparato (GE, tag privada 0045,101B): RMLO es la MLO; RSMLO, RSCC, RMSCC y RCCS son variantes de ella (complementaria, magnificada), y todas traen el mismo ViewPosition y el mismo código de proyección: el estándar DICOM no distingue las dos, el rótulo del servicio sí.
- Sin ese rótulo (la tomosíntesis y V-Preview no lo traen), vale el nombre de la serie: CESM_PROC_RMLO nombra la MLO, CESM_PROC_RSMLO no. Un nombre que no habla de proyección (2D_PROC) no desempata nada.
- La complementaria no queda escondida: un segundo cuadro con la misma proyección la muestra, y el rótulo del cuadro pasa a traer el nombre de la serie ("MLO D · CESM_PROC_RSMLO").
- Si el estudio solo tiene la complementaria, entra: un cuadro rellenado con aviso en el rótulo es mejor que un cuadro vacío.
- La **2D sintetizada** de la tomosíntesis (V-Preview en GE) es una proyección, no un volumen: es una sola imagen, con el lado y la proyección en los grupos funcionales. Entra en la celda 2D; si el estudio también tiene la 2D adquirida de esa proyección, la adquirida es la que se abre, y la sintetizada queda detrás de ella en la misma lista del cuadro. Cuando es la sintetizada la que está en la pantalla, el rótulo dice "CC D · 2D sintetizada".

## Al abrir, encuadrar

La mitad del campo de una mamografía es aire. Encuadrar la imagen entera es encuadrar el aire; por eso cada etapa del protocolo tiene un campo **Al abrir, encuadrar:**

| Opción | Qué hace |
|---|---|
| Mama al cuadro | encuentra la mama, descarta el aire y escala para llenar el cuadro, con la pared torácica pegada al borde. Es lo predeterminado |
| Imagen entera | el ajuste a la ventana de siempre (el detector entero cabe en el cuadro) |
| Resolución completa | 1 píxel de la imagen = 1 píxel del monitor; la imagen queda mayor que el cuadro y se navega con desplazamiento |

- El zoom sale del tamaño del cuadro, que depende del monitor y del diseño de la etapa. No hay un número fijo.
- Las dos mamas de la etapa quedan en la misma escala: comparar lado a lado en escalas distintas no es comparar.
- La mama nunca queda menor que en el ajuste a la ventana.
- **Mama en el cuadro** en la barra reencuadra al instante, para usar después de cambiar el zoom a mano.
- Una imagen **arrastrada** a un cuadro (o abierta en él con doble clic en la lista de series) también entra encuadrada; en un cuadro del protocolo el conjunto se reencuadra junto.
- Si no se encuentra la mama, el cuadro se abre con la imagen entera y la barra de estado dice en cuántos cuadros ocurrió.

> **¿Ningún protocolo coincidió?** El estudio cae en una disposición común (ordenada por proyección y lado, en 2×2 o 1×2) y el registro dice qué descripción no coincidió. El protocolo tampoco se activa si ninguna imagen tiene lado reconocible.

## Protocolos de visualización de los otros estudios

**Protocolos de visualización** (Configuración ▸ Protocolos de estudio) se ocupa de TC, RM, US y afines, al estilo de la mamografía: cada protocolo tiene **etapas**, y **← →** pasan de una a otra.

**Al abrir el estudio**, el primer protocolo activo que coincida (modalidad y "la descripción del estudio contiene") se abre en la etapa 1. Aparece una barra encima de los cuadros: el nombre del protocolo, la lista de las etapas (elija cualquiera), ◀ ▶, **Guardar la pantalla como etapa…**, **Editar protocolos…** y **Salir del protocolo** (deja los cuadros como están). Vienen tres de fábrica para que usted los ajuste: **TC de tórax** (mediastino, pulmón y pulmón en MIP, cada uno con axial y coronal), **RM de mama** (sin contraste, dinámica, MIP de la sustracción) y **RM de cráneo** (T2/FLAIR/difusión y poscontraste con coronal).

**La pestaña** tiene tres partes:

- arriba, los protocolos, uno por línea: Activo, Nombre, Modalidad, La descripción del estudio contiene (`|` = o), cuántas etapas y **Previo en el monitor de comparación**. Nuevo, Duplicar, Quitar, ▲ ▼ (el orden decide cuál vale primero) y **Añadir los de fábrica**;
- abajo a la izquierda, las etapas del protocolo elegido (+ Etapa, Duplicar, Quitar, ▲ ▼);
- a la derecha, el dibujo de la etapa: nombre, diseño (filas × columnas) y un botón por cuadro. Haga clic en un cuadro y edite abajo:

| Campo | Qué hace |
|---|---|
| Serie | palabras de la descripción de la serie; con `\|`, alternativas **en orden de preferencia** (`T1 POS\|T1 GD\|T1` quiere la poscontraste antes que la simple). La misma serie puede estar en varios cuadros (axial en uno, coronal en el otro) |
| Del estudio previo | la serie viene del estudio previo de la misma modalidad |
| Plano | como se adquirió, axial, coronal o sagital (MPR) |
| Fase de la dinámica | serie entera, precontraste, poscontraste 1 a 9 o última fase. La serie se busca solo entre las que forman parte de una dinámica (▦); la 1.ª fase de la dinámica es la pre, así que "poscontraste 1" es la 2.ª fase del grupo |
| Reconstrucción | ninguna (como la serie), **MPR** (corte fino en el plano elegido), MIP, MinIP o media con el grosor en mm, **MIP 3D** o **VR**. Los dos últimos hacen lo mismo que el botón 3D: cada cuadro se vuelve un volumen propio, con la barra 3D entera (modo, preset, opacidad, color, Vistas, Cortar, Esculpir, Girar…) valiendo para el cuadro activo |
| Mitad (media mama) | paciente entero, solo la mitad derecha o solo la mitad izquierda. El volumen se corta en el centro del campo (derecha-izquierda). Con MIP 3D o VR, el 3D solo de esa mitad; con MIP/MinIP/media de grosor, el MIP **sagital** de la mitad entera |
| Vista | desde qué lado se mira: las mismas **Vistas** de la barra 3D: Anterior, Posterior, Derecha, Izquierda, Superior, Inferior. En el 3D es la cámara; en un corte, vale cuando el corte es de ese plano (lateral en un sagital, frontal en un coronal, desde arriba o desde abajo en un axial) |
| Ventana | un preset (Pulmón, Mediastino…) o ancho/nivel escrito a mano (`1500/-600`); "del archivo" lo deja como vino |
| Color | gris o una tabla de colores |
| Posición | automática (el mismo lugar al cambiar de serie), primer corte, medio de la pila o el mismo punto del cuadro activo de la etapa anterior |
| Sincronía | los cuadros con el mismo número recorren, amplían y cambian de ventana juntos |
| Con varias pantallas | en qué monitor queda el cuadro; "el programa reparte" divide la etapa como en la mamografía (por las filas, si no por las columnas) |

**Guardar la pantalla como etapa…** es la manera rápida: arregle el estudio en la pantalla (diseño, series, un coronal MIP de 10 mm, ventana de pulmón, cuadros sincronizados) y guarde. La ventana pregunta en qué protocolo (o uno nuevo, con la modalidad y la descripción de este estudio) y si la etapa entra como nueva o sustituye a la que está en la pantalla. Después, en el editor, cambie la serie guardada por alternativas (`|`) para servir a otros aparatos.

**Etapa con la evaluación dinámica (0.94).** En el editor, cada etapa tiene **Abrir la evaluación dinámica (mapas y curvas)**, con el diseño de los mapas (los mismos del botón Dinámica) y la serie de la dinámica (vacío = la dinámica del estudio, detectada sola). Al llegar a esa etapa, el programa hace lo que hace el botón Dinámica, sin la ventana: toma las fases, usa los **últimos parámetros** que usted usó en el botón (umbrales, pre, inicial, tardía, corrección de movimiento) y abre los mapas con el panel de curvas. Pasar a otra etapa cierra la dinámica; volver la abre de nuevo. La RM de mama de fábrica tiene la etapa **Evaluación dinámica** al final, y quien ya tenía la RM de mama guardada recibe esa etapa una vez. Para cambiar los parámetros, use **Parámetros…** en el panel de la dinámica: la próxima vez que se abra la etapa, usa los nuevos.

**La reconstrucción de la etapa es un volumen 3D (0.93).** Haga clic en un cuadro en que la etapa montó una reconstrucción (MPR, MIP, MinIP o media de grosor) y aparece la barra **3D — modo**, ya en su modo. La primera vez que usted la toque (cambiar el modo, preset, color, Vistas, Cortar, Esculpir, Girar…), el cuadro se vuelve un 3D: el mismo volumen (la misma fase, en la dinámica), cortado en el grosor que estaba en la pantalla y mirando desde el mismo lado. Los otros cuadros continúan como están. **Volver a la serie** lo deshace. El 3D se monta en una cuadrícula reducida (Configuración ▸ Sistema ▸ Rendimiento), así que puede salir menos nítido que el MIP de grosor. La barra del MPR también pasó a mostrar el grosor del cuadro (62 mm, 165 mm…) en vez de "fino".

**MIP de media mama (0.90; en 3D desde la 0.92).** La RM de mama de fábrica tiene la etapa **MIP de las fases (media mama)**: 2 × 2, cuatro **MIP 3D**, arriba la poscontraste 1 y abajo la poscontraste 3; a la izquierda la mama derecha vista desde la **Izquierda** (pezón hacia la izquierda), a la derecha la mama izquierda vista desde la **Derecha** (pezón hacia la derecha). Cada cuadro es un 3D propio: haga clic en él y use la barra 3D (girar, Vistas, cortar, cambiar MIP por VR) sin tocar los otros. La ventana de cada MIP sale de la propia proyección. Quien ya tenía la RM de mama guardada recibe esa etapa al final del protocolo una vez (las otras etapas no cambian). Para otra combinación (la 2.ª pos, la sustracción, la mama entera), cambie la fase, la mitad o el frente de cada cuadro en el editor. Las dos fases de la etapa quedan montadas en la memoria, así que los cuatro cuadros salen de dos volúmenes. El medio es el centro del campo de visión: en un estudio con el paciente descentrado, la mitad puede llevar un pedazo de la otra mama.

Cuando la serie de un cuadro no existe en el estudio, el cuadro dice **Serie no encontrada** con lo que buscó, y la barra de estado cuenta cuántas faltaron. La reconstrucción que el protocolo pide al abrir no hace preguntas: un volumen por encima del límite de memoria (Configuración ▸ Sistema ▸ Rendimiento) queda fuera, con aviso. Con el estudio en varias pantallas, la etapa es de la estación: pasar de etapa en una pasa en todas. Los protocolos hechos antes de la 0.88 siguen valiendo y se vuelven protocolos de una etapa al guardar la pestaña.

### Estado guardado del análisis

Al cerrar el estudio (por la X de la pestaña, al cambiar de estudio o al salir del programa), Ipê guarda **cómo estaba**, para cada usuario: el diseño, lo que había en cada cuadro (la serie, de qué estudio, el corte, la fase y la vista (ventana, zoom, desplazamiento, inversión, colores, giro, reflejos y filtro)), el cuadro activo, la herramienta del botón izquierdo, los previos traídos a la pestaña (que vuelven enlazados por la alineación guardada) y los paneles de Mediciones y Lesiones. Al reabrir, el estudio vuelve así, y la barra de estado dice de cuándo es el estado. La dinámica y el MPR no se rehacen solos (el cálculo puede tardar): **Ver ▸ Estado del análisis ▸ Reconectar la dinámica como estaba** abre la ventana de la dinámica con las mismas fases y parámetros, y el MPR se reconecta en su botón.

**Ver ▸ Estado del análisis** también tiene:
- **Reabrir como lo dejé**: rehace el estado en cualquier momento;
- **Volver a la disposición de fábrica**: olvida el estado de este estudio (y no lo guarda al cerrar esta vez);
- **Usar el montaje del estudio previo**: en un solo control, el diseño y las vistas del estudio previo del paciente, cada cuadro con la serie equivalente de este estudio (misma modalidad y descripción);
- **Abrir el previo al lado, como estaba**: el previo entra en la pestaña con sus cuadros como usted los dejó, al lado de los de este estudio.

**Retomar la sesión después de una caída (0.100.8).** Mientras Ipê está abierto, anota qué estudios están abiertos y guarda el estado del análisis de cada uno **cada 2 minutos**, y no solo al cerrar. Si el programa (o el ordenador) se cae, en la próxima apertura muestra los estudios que estaban abiertos y pregunta si los reabre: **Reabrir** abre cada uno como estaba la última vez que se guardó el estado (diseño, cortes, mediciones, paneles), con lo que estaba al frente de nuevo al frente. Cerrar bien el programa borra la anotación. En **Configuración ▸ Visor ▸ Estado del análisis al abrir…**, **Después de una caída, los estudios que estaban abiertos**: preguntar (de fábrica), reabrir sin preguntar o no reabrir.

**Configuración ▸ Visor ▸ Estado del análisis al abrir…**: reabrir como lo dejé (de fábrica), preguntar o abrir como de fábrica. El estado queda solo en Ipê (en la base de datos de este ordenador o, en el modo cliente, en el servidor central, para todas las estaciones); no viaja con el estudio. No vale cuando el estudio se abre con series elegidas, por un protocolo con etapas, repartido entre monitores, en el modo mamografía o en reunión: ahí manda el protocolo.

### La memoria del diseño

Fuera de la mamografía, el programa aprende la cuadrícula sin que nadie la configure: usted ajusta el diseño de una resonancia de hombro, y la próxima resonancia de hombro se abre así. La etiqueta es modalidad + las palabras de la descripción que importan; lado, contraste y números no cuentan.

- La memoria es por monitor y por cantidad de pantallas: la disposición de una pantalla no se impone cuando el mismo estudio se abre en dos.
- Un protocolo de visualización escrito por usted siempre manda sobre la memoria.
- Solo se guarda la cuadrícula, nunca qué serie estaba en qué cuadro.

# Mama: densidad, RM dinámica y lesiones

Este capítulo reúne lo que el programa hace de específico para la mama: la parte más desarrollada de él, y la que tiene más salvedades escritas.

## Densidad mamaria

El botón **Densidad** de la barra, en un estudio de mamografía (véase abajo), o **Densidad…** en la barra del protocolo de mamografía. La medición es del estudio entero, por la **red de la NYU** (una red neuronal en ONNX que da la categoría A–D a partir de las cuatro proyecciones). Desde la 0.100.46 la densidad salió del menú Archivo.

Hasta la 0.100.47 aparecían también el % de área por el umbral de Otsu y por la agrupación fuzzy. En las verificaciones, quedaron muy lejos de las categorías confirmadas, y desde la 0.100.48 solo se mide y se muestra la red (lo que ya se había guardado con ellos queda en la base de datos, fuera de las pantallas).

> **Lo que falta para que el número entre en el informe:** la lectura ciega: comparar la medición del programa con su categoría, sin que usted vea el número antes. Mientras eso no se haga, trate el valor como orientación, no como informe.

### El botón Densidad (0.100.44)

En los estudios de mamografía, el botón **Densidad** está en la barra (con su propio botón, fuera de la lista de IA). El clic abre **Medir y revisar**; la flechita muestra las opciones:

- **Medir en segundo plano (queda guardado en el estudio)**: mide las cuatro proyecciones 2D del estudio sin abrir ventana; la barra de estado avisa cuando termina, con el resultado.
- **Medir y revisar…**: abre la densidad del estudio. Si ya se midió, muestra lo que está guardado; si no, mide en el acto. Primero y más grande, la **red de la NYU**: la categoría y la probabilidad de cada una. La categoría marcada de salida es la de la red (o la que usted ya confirmó); cámbiela si discrepa y haga clic en **Confirmar** o **Confirmar y enviar al informe**, que pone la composición en el informe BI-RADS del estudio (en un informe firmado, o sin la parte BI-RADS, la frase va como texto). *Medir de nuevo* rehace el cálculo sin perder su confirmación.
- **Revisar varios estudios en cola…**: la cola de abajo.

La medición es del estudio entero, no solo de lo que está en la pantalla, y queda guardada en el estudio (en el servidor central, cuando usted usa uno), con quién confirmó y cuándo.

### Densidades medidas (0.100.46)

**Informes ▸ Densidad mamaria: mediciones y confirmaciones…**, o botón **Densidad** ▸ *Densidades medidas…*. Una fila por estudio medido: fecha, paciente, aparato, la **red de la NYU** (categoría y confianza), la categoría **confirmada**, quién confirmó y cuándo, y la situación (no confirmada, igual a la red, distinta de la red). Filtre por el período y por la situación. Arriba, cuántos estudios se midieron y confirmaron y el porcentaje de iguales a las confirmaciones, con el kappa. El doble clic abre el estudio; *Exportar CSV…* lleva la tabla, con las probabilidades de la red.

La red de la NYU va incluida en el paquete de Ipê desde la 0.100.46: no hace falta copiar nada a otros ordenadores.

### Revisar la densidad (cola de estudios)

Botón **Densidad** ▸ *Revisar varios estudios en cola…*, o **Revisar densidad…** en la barra de mamografía. Es la manera de saber, en sus estudios y en sus aparatos, si la sugerencia del programa sirve.

1. Elija el período y haga clic en **Montar la cola**: entran las mamografías de la base de datos en ese período (con *Solo los que aún no revisé*, las que usted aún no revisó), la más reciente primero.
2. Cada estudio se abre en una pestaña del visor, y la ventana muestra la sugerencia de la **red de la NYU** (categoría A–D, con la confianza). Abajo, el aparato y los avisos (proyección ausente, prótesis). El estudio que ya se midió (por el botón Densidad) no se mide de nuevo, y su respuesta vale también como la confirmación del estudio.
3. Responda con un clic o una tecla: **A**, **B**, **C**, **D** (o **1** a **4**), **N** para no evaluable. La respuesta se graba y se abre el siguiente estudio. **→** salta, **←** vuelve (el botón de la respuesta dada queda marcado). Con *Cerrar el estudio anterior al pasar*, la pestaña de cada estudio se cierra cuando usted sigue.
4. **Control**: en parte de los estudios (10 % de fábrica, ajustable) la sugerencia solo aparece después de su respuesta. Quien revisa con la respuesta a la vista tiende a coincidir con ella; los estudios de control miden cuánto.
5. Abajo, la **concordancia** de la red hasta ahora: kappa ponderado, acierto exacto y denso (C/D) × no denso (A/B), en total y en los estudios de control. **Exportar CSV…** lleva todo, estudio por estudio, con las probabilidades de la red.

La revisión queda en la base de datos (en el servidor central, cuando usted usa uno), una por estudio y por revisor: revisar el mismo estudio cambia la respuesta. Esas revisiones muestran cuánto acierta la red en sus aparatos.

### Calcificaciones vasculares (0.100.51)

En un estudio de mamografía, el botón **Vasos** (un vaso con tramos calcificados) busca calcificaciones vasculares de la mama (calcificación arterial) en **todas las imágenes 2D** del estudio: las cuatro de rutina, las repetidas, las otras proyecciones (perfil, XCCL…), la compresión localizada y la ampliación (la densidad, al contrario, usa solo las cuatro de rutina). La tomosíntesis queda fuera. La red es la **SCU-Net** (Emory, licencia MIT), que viene en el paquete de Ipê.

- **Medir y revisar** (el clic en el botón): abre la ventana con un cuadro por proyección y lo que marcó la red; desde la 0.100.91 con un **contorno blanco con borde negro**, separado ~1 mm, y **flechas numeradas** en las puntas de cada vaso (la numeración sigue la lista de vasos de las escalas, del más largo al más corto; las puntiformes quedan solo con contorno). Las marcas aparecen igual en el monitor en color, en el monitor B/N y en el PACS externo (antes eran rojas, y el rojo se vuelve un gris oscuro en B/N); el área en mm² de cada imagen y de cada mama (la mayor entre las imágenes de campo completo); y la **sugerencia** de grado. Cuando una proyección tiene más de una imagen, el cuadro muestra *(1/3)* y las flechas ◀ ▶ (o la rueda del ratón sobre la imagen) pasan por las otras. La compresión localizada y la ampliación aparecen marcadas *fuera de la cuenta* (el área en ellas sale mayor). Si el estudio aún no se midió, mide en el acto (algunos segundos).
- **Medir en segundo plano** (en el menú del botón): mide y guarda en el estudio sin abrir la ventana.
- **Su grado**: **ausente, leve, moderada o acentuada**. La sugerencia viene marcada de salida; cámbiela si discrepa y haga clic en **Confirmar** o **Confirmar y enviar al informe** (la frase, por ejemplo "Calcificaciones vasculares moderadas.", va como texto al informe). **Medir de nuevo** rehace sin perder el grado confirmado.

La sugerencia es **provisional**: cuenta solo los tramos alargados (con 3 mm o más en el lado mayor, la manera del vaso; los puntitos aislados quedan fuera) y usa cortes de área aún sin calibrar (5, 30 y 100 mm² en la mama con más). Lo que vale es su grado; las áreas quedan guardadas junto, para calibrar la sugerencia con sus confirmaciones y, después, llegar a una escala de puntos.

**Prótesis**: el borde de la prótesis engaña a la red. Ipê encuentra la prótesis en la imagen (incluso cuando el aparato no la declara) y saca de la cuenta lo que cae en ella y en una franja de 5 mm alrededor; aun así, en un estudio con prótesis no hay sugerencia de grado: verifique en las imágenes.

**Escalas.** Debajo de la sugerencia aparecen las escalas publicadas, estimadas por lo que la red marcó (pase el ratón para ver cómo se hace cada una):

- **Margolies** (0–12), por mama: vasos (1 punto por vaso, hasta 6) + extensión en el vaso más afectado (0–3) + densidad de la peor área (0–3: luz visible/una pared, dos paredes en riel, sin luz). Vale la peor mama: 0 negativa, 1–3 leve, 4–12 moderada a acentuada.
- **CSBI** (0–3): 1 algunas puntiformes; 2 gruesas o en riel en menos de 3 vasos; 3 tres o más vasos.
- **Loberant** (0–3): 1 pocas puntiformes o lineales cortas; 2 más abundantes; 3 continuas.
- **BAC-SS**, en la MLO: Nv (vasos) + Ov (1 si el calcio cubre la arteria de lado a lado por ≥ 1 mm) + L (longitud sumada en 4 clases: hasta 12, 33, 84 mm y más).

Son estimaciones: "vaso" son los tramos a hasta 2,5 mm unos de otros; "riel", dos tramos paralelos; "sin luz", un tramo con 1 mm o más de grosor; la extensión es la longitud del vaso sobre la profundidad de la mama. La densidad es la parte menos segura: verifique en las imágenes. Estudios medidos antes de la 0.100.55: **Medir de nuevo**.

En **Ipê Web**, el botón **Calcificaciones vasculares** (junto a Densidad mamaria) hace lo mismo, midiendo en el servidor: las vistas previas con las marcas (con ◀ ▶ y la rueda cuando la proyección tiene más de una imagen), la sugerencia, el grado y el informe. Confirmar pide el permiso de escribir informes. El panel se abre grande y se puede **redimensionar desde la esquina inferior derecha**; el navegador recuerda el tamaño.

### Automático: medir al llegar, confirmar al abrir, SR en el estudio (0.100.57)

Toda mamografía que llega (recibida por la red, descargada del PACS (Q/R), importada o enviada al servidor central) tiene la **densidad** y las **calcificaciones vasculares** medidas solas, en segundo plano, un estudio cada vez (siga y cancele en **Tareas de IA**). Nada se confirma solo: las mediciones quedan esperando.

- **Al abrir el estudio** (en Ipê o en Ipê Web), se abre la ventana de la **densidad** con la sugerencia marcada; confirmada (o cerrada) esta, se abre la de las **calcificaciones**. Solo aparece lo que aún no se confirmó, y una vez por estudio abierto.
- **Confirmadas las dos**, Ipê graba en el estudio tres series: el **SR** (*Densidad y calcificaciones (Ipê) SR*: la composición confirmada y las probabilidades de la red, el grado confirmado y la sugerencia, el área por mama y por imagen, las escalas, quién confirmó y las referencias a las imágenes), las **imágenes con las calcificaciones marcadas** (contorno y flechas numeradas) (*Calcificaciones vasculares (Ipê)*, una por imagen con calcificación) y un **resumen** en tabla (*Densidad y calcificaciones (Ipê)*, para PACS que no muestran SR). Confirmar de nuevo (otro grado) rehace las tres.
- **Las mamografías que ya estaban en la base de datos** se comprueban una vez, en segundo plano, después de abrir el programa (o el servidor) en esta versión: la tarea *Densidad y calcificaciones vasculares — mamografías de la base de datos* muestra cuántas faltan; las más nuevas primero. Lo que no termine continúa en la próxima apertura.
- Preferencias ▸ CAD/IA ▸ **Densidad y calcificaciones (mama)**: activar/desactivar la medición al llegar y la confirmación al abrir; **Comprobar la base de datos de nuevo en la próxima apertura**.
- **Aceptar la medición sin revisión** (0.100.78): la mamografía que llega se mide y el SR, las imágenes marcadas y el resumen se graban en el acto, como sugirió la red, marcados como **no revisados** (en el SR y en la tabla). Al abrir el estudio usted aún confirma o corrige: el SR se rehace, ya con lo que usted revisó. El barrido de las mamografías antiguas de la base de datos solo mide (no graba SR).
- **Después de grabar el SR, enviar a:** (0.100.78) los nodos DICOM marcados (el PACS) reciben el SR, las imágenes marcadas y el resumen, tanto sin revisión como después de confirmar (confirmar de nuevo reenvía). Lo mismo vale en Ipê Web, en Registros ▸ Automatizaciones de IA.
- En el ordenador conectado a un servidor central, quien mide es el servidor; la confirmación se hace en cualquiera.

### Dónde se ejecutan las IA en Ipê cliente (0.100.100)

En Ipê conectado a un servidor central, **Preferencias ▸ CAD/IA ▸ En Ipê cliente, ejecutar las IA**:

- **En el servidor central (predeterminado)**: la IA pedida en el visor va a la cola de IA del servidor (la misma de Ipê Web y de las automáticas). La ventana de progreso dice la etapa; al terminar, las series nuevas (máscaras, mosaicos, tablas) llegan al estudio abierto y aparecen los hallazgos. Necesita el permiso **Pedir CAD/IA a mano**.
- **En este ordenador**: se ejecuta con el paquete de IA de este ordenador y, al terminar, **las series generadas y los hallazgos suben solos al servidor**: quien abra el estudio en otro lugar ve el mismo resultado. Necesita el paquete de IA instalado aquí y el permiso **Ejecutar las IA en este ordenador** (de fábrica: administrador y médico; el administrador lo cambia en Usuarios ▸ Perfiles). Sin uno u otro, la IA va al servidor, avisando.
- En el **lote a partir de una hoja de cálculo**, la misma elección: con "En este ordenador", el servidor busca, descarga y hace el resto, pero pide las IA a este ordenador: deje abierta la ventana del lote mientras se ejecuta. Lo que no salga bien aquí, el servidor lo hace por sí mismo.
- La segmentación por caja (MedSAM2), que es interactiva, se ejecuta siempre en este ordenador.

### Enlace del estudio: abrir un estudio en Ipê Web sin contraseña (0.100.108)

Clic derecho en el estudio, en la base de datos ▸ **Crear enlace del estudio (Ipê Web)…**. El enlace abre **solo ese estudio**, directo en el visor de Ipê Web, **sin pedir contraseña**: quien lo recibe no ve la lista, la base de datos, los informes ni otros estudios.

- **Para quién**: un nombre, para que usted sepa después quién tiene el enlace.
- **El enlace también puede**: *Ejecutar y revisar IA*, *Enviar al PACS y a otros nodos*, *Adjuntar PDF e imágenes*. Sin marcar nada, solo ver (con mediciones).
- **Vale por**: 1, 3, 7 o 30 días.
- **Crear enlace** genera la dirección y ya la copia; la lista de abajo muestra los enlaces del estudio, cuántas veces se usaron y cuándo vencen. **Revocar el enlace seleccionado** corta el acceso en el acto, incluso a quien lo tiene abierto.

En **Ipê Web** (0.100.109), lo mismo está en el botón de **enviar** de la barra del visor (desde la 0.100.112, un menú: *Enviar a un destino DICOM…* y *Enlace del estudio (sin contraseña)…*): *Crear y copiar*, y la lista de los enlaces del estudio con *Revocar*. El enlace funciona por el Ipê Web del servidor central (en Ipê cliente, quien lo crea es el servidor). Crear un enlace pide el permiso de **exportar**. Cada creación, uso, intento denegado y revocación queda en el registro de acceso. Quien tenga el enlace ve el estudio hasta que venza: envíelo solo a quien deba verlo.

### Mamografía: densidad, calcificaciones y quitar el silicona a mano (0.100.106)

En la pestaña **IA** de Ipê Web (y en el clic derecho ▸ **IA** de la base de datos, en el Ipê de escritorio), la mamografía muestra tres herramientas: **Densidad mamaria (BI-RADS)**, **Calcificaciones vasculares de la mama** e **Implante de silicona: quitar la silicona**. Se ejecutan en el estudio entero, en la cola de IA del servidor, y no necesitan el paquete de segmentación. *Quitar la silicona* graba la copia " · sin implante" incluso con la corrección al llegar desactivada: es el camino para los estudios antiguos, que llegaron antes de ella. La densidad y las calcificaciones medidas así aparecen para verificar, como las de la llegada.

### Ipê Web: abrir un estudio por llamada externa (0.100.103)

Otro sistema (RIS, sistema de informes, un acceso directo) abre el estudio en Ipê Web por una dirección:

- `https://<servidor>:8053/web/#/abrir?acesso=12345` — por el número de acceso;
- `https://<servidor>:8053/web/#/abrir?id=98765&data=20261123&mod=MR` — por el ID del paciente, con fecha y modalidad (opcionales; la fecha también vale como 2026-11-23 o 23/11/2026);
- `https://<servidor>:8053/web/#/abrir?uid=<Study Instance UID>` — solo para lo que ya está en el servidor.

Ipê Web busca primero en el servidor. Si el estudio no está allí, busca en los nodos del PACS que el servidor comparte (Configuración ▸ Red ▸ nodo ▸ *Compartir con los clientes*), **descarga y abre** cuando llega, mostrando el progreso. Con más de un estudio, muestra la lista para elegir. El inicio de sesión sigue siendo obligatorio: sin sesión, Ipê Web pide la contraseña y vuelve a la dirección. Buscar en el PACS pide el permiso de búsqueda; descargar, el de descarga.

Cuando el estudio viene del PACS, se abre en cuanto llegan las primeras imágenes (0.100.105): las series van apareciendo en la tira y la serie en el cuadro crece sola, con un aviso de cuánto ha llegado ya.

**Mantener la sesión iniciada (0.100.104):** marque *Mantener la sesión iniciada en este ordenador (1 día)* en el inicio de sesión. El inicio de sesión pasa a valer en todas las pestañas de ese navegador y en los enlaces de apertura, por 1 día, incluso inactivo; *Salir* lo olvida en todas las pestañas. Sin marcar, vale solo en la pestaña (y caduca tras 12 h inactivo). No lo marque en un ordenador compartido.

### IA desde la base de datos, cola de IA y tabla del hígado (0.100.101)

- **Clic derecho en el estudio ▸ IA**: la lista de las IA que sirven para el estudio, como el botón IA del visor. Cada una trae las opciones: **ejecutar en la serie sugerida** (o **rehacer**, si ya se hizo, marcada con ✔), **ejecutar en otra serie** y abrir el estudio para ver el resultado. Las que la regla dejó fuera quedan en *Otras IA*, con el motivo, y se ejecutan igualmente. Con varios estudios seleccionados, cada IA entra en la cola en todos, en la serie que elige en cada uno. En Ipê cliente, vale la misma elección de dónde ejecutar (servidor o este ordenador).
- **Cola**: pedir una IA mientras otra se ejecuta en este ordenador ya no se rechaza: Ipê avisa, pone la nueva en la cola y empieza sola cuando la otra termina. La cola aparece en **Tareas de IA…**, donde también se puede quitar.
- **Resumen en imagen** (0.100.102): la IA de hígado graba en el estudio la serie **"Hígado en la RM: resumen (Ipê)"** (OT), como la de densidad mamaria: PDFF y grado, doble eco, R2* y LIC, rigidez y rango, el resultado de cada uno y quién revisó. Se rehace en cada revisión en Hallazgos de IA (en el Ipê de escritorio y en el Web), con los números corregidos, y va junto a los destinos configurados.
- **Informes ▸ Hígado en la RM (esteatosis, hierro, rigidez): mediciones y confirmaciones…** (también en el menú del botón Hígado del visor): una fila por estudio con PDFF y grado, doble eco, R2* y hierro estimado (LIC), rigidez y rango, la situación de la revisión, quién revisó y cuándo; filtros (no revisadas, con esteatosis, con sobrecarga de hierro, con rigidez por encima de lo normal), el doble clic abre el estudio y el CSV lleva la tabla. Los números son los que valen: los corregidos por el médico por encima de los de la IA.
- **Lote en Ipê cliente (0.100.107)**: con *Traer los estudios también a este ordenador* marcado, el estudio va del PACS al servidor y del servidor a la base de datos de este ordenador; marcando también *Borrar del servidor los estudios que el lote descargó del PACS, después de que lleguen completos a este ordenador*, queda solo aquí. El cliente solo libera el borrado cuando el estudio llegó completo (reintenta lo que faltó); lo que ya estaba en el servidor antes del lote nunca se borra. Deje abierta la ventana del lote hasta el final: cerrada, la copia se detiene y el servidor no borra nada. Desde la 0.100.111, cada estudio empieza a venir **en cuanto llega al servidor**, sin esperar las IA y los envíos de la línea; al final de la línea viene solo lo que falte (las series de las IA), y el diario muestra cada estudio que llegó aquí.
- **Lo que las IA graban y envían: SEG, tablas y serie con overlay en color (0.100.124)**: en Configuración ▸ CAD/IA, en el grupo *Lo que las IA graban y envían*, marque lo que debe ir a los destinos (**SEG**, **tablas e imágenes de verificación** y **serie con overlay en color**) y elija los **destinos** que valen para todas las IA. La serie en color es el estudio con las máscaras pintadas, una imagen por corte, en la posición del corte original: cualquier PACS la recorre, incluso los que no muestran SEG. Sale de la SEG grabada, así que vale para toda IA que grabe SEG. Viene desactivada de fábrica (ocupa espacio). La SEG y las tablas siempre quedan en el estudio de Ipê; las casillas deciden lo que se envía. **En cada IA** (en su configuración) el cuadro *Lo que esta IA graba y envía* sustituye la elección de todas las IA: SEG, tablas y overlay como Como en todas / Sí / No, y destinos sumados a los globales o solo los de la herramienta.
- **Exportar los resultados de las IA en lote a Excel (0.100.123)**: seleccione los estudios en la base de datos, clic derecho ▸ **Exportar resultados de las IA (Excel)…**. El .xlsx reúne lo que las IA **ya grabaron** en esos estudios (no se ejecuta nada): la pestaña *Estudios* (uno por fila, con qué IA tienen resultado) y una pestaña por IA, con los números de cada hallazgo (lo que el médico corrigió vale en lugar del número de la IA) y el estado de la revisión; la mamografía entra con la densidad y las calcificaciones vasculares. Se puede **anonimizar** (Caso 001, 002…, sin nombre, ID, accession ni descripción). Para ejecutar las IA y exportar a partir de una hoja de cálculo de pacientes, use el lote.
- **Lote a partir de una hoja de cálculo**: el estudio que **ya está en Ipê** pasa por las reglas de la llegada (IA automática, enrutamiento, impresión), como un estudio descargado; opción marcada de fábrica en el paso *Qué hacer* (el estudio descargado por el lote ya pasaba por ellas al terminar la descarga).
- **Columna "En este ordenador"** (en Ipê cliente): dice si el estudio del servidor también está en la base de datos de este ordenador: **completo** o **parcial** (solo parte de las imágenes).

### Investigación: las mamografías de una lista, en lote

Para medir la densidad y las calcificaciones vasculares de las mamografías de una lista (un estudio), use **Red ▸ Lote a partir de una hoja de cálculo…** con la plantilla lista **Densidad y calcificaciones de la mama**; véase "Lote a partir de una hoja de cálculo" en el capítulo *Buscar y descargar*.


## RM de mama dinámica

El programa reproduce el flujo de CADstream: detecta las fases, corrige el movimiento, calcula los mapas paramétricos, clasifica la cinética en seis colores y mide la lesión sobre el realce.

![RM de mama: T2 y las fases de la dinámica lado a lado, sincronizadas.](rm_mama.png)

![La ventana de la dinámica: las fases detectadas, el precontraste, las fases del SER y los parámetros del mapa cinético.](dinamica_fases.png){70}

### Abrir la dinámica

Botón **Dinámica** en la barra. La ventana de parámetros muestra las series que reconoció como fases y deja elegir:

| Campo | Qué es |
|---|---|
| Pre, inicial y tardía | cuáles fases son la precontraste, la de pico y la tardía |
| Realce mínimo (%) | por debajo de esto el vóxel no entra en el mapa cinético |
| Rápido (%) / Tardío (±%) | los umbrales de las seis clases: medio 50–100 %, rápido por encima; persistente / meseta / lavado por la variación de la tardía |
| Señal mínima del tejido (%) | máscara: precontraste de al menos N % de la señal de referencia |
| Corregir movimiento | registro por traslación 3D entre las fases |
| Incluir rotación | registro rígido (rotación + traslación) de cada fase sobre la pre, más lento (hasta unos 40 s por fase); solo remuestrea en 3D la fase que giró 0,75° o más: en las RM de mama del archivo la rotación entre las fases no pasó de 0,5°, y entonces queda la traslación |
| Disposición | qué mapas van a qué cuadros |

Los valores quedan guardados: el próximo estudio se abre con los últimos que usted usó.

### Alinear las fases (corrección de movimiento)

Cuando la paciente se mueve o respira entre las fases, la sustracción muestra un "fantasma" en los bordes. La IA **Dinámica de la mama: alinear las fases** corrige eso **en 3D**: alinea todas las fases entre sí (registro conjunto y deformable de elastix) y graba **en el propio estudio** las fases alineadas (*Dinámica alineada 1…N · Ipê*) y las sustracciones pos − pre (*Sustracción alineada…*). La serie original no se toca, y las imágenes nuevas dicen en la cabecera que se alinearon por IA.

- **Instalar (una vez)**: Configuración ▸ CAD/IA ▸ *Instalar el alineamiento de la dinámica de la mama (elastix, ~1,5 GB)…*. Necesita internet y espacio en disco; queda en un entorno propio.
- **Hacer a mano**: en la base de datos, menú **IA** del estudio (o el menú IA de Ipê Web) ▸ *Dinámica de la mama: alinear las fases*. La tarea aparece en la cola de IA; tarda algunos minutos y usa de 1 a 2 GB de memoria.
- **Hacer solo al llegar**: Preferencias ▸ CAD/IA ▸ *Dinámica de la mama: alinear las fases* ▸ *Alinear automáticamente cuando llegue la RM de mama dinámica* (viene desactivado). Se ejecuta en el servidor, un estudio cada vez.
- **Solo cuando vale la pena**: el programa mide cuánto del residuo |pos − pre| quitó el registro: el realce por el contraste se queda, solo sale el desalineamiento. Si quitó menos que el límite (12 % de fábrica), no se graba nada y el estudio queda como estaba. Pedida a mano, graba siempre.
- Otras opciones: grabar o no las sustracciones, la malla de la deformación (32 mm corrige la respiración y el movimiento del cuerpo; menor corrige más fino y tarda más) y los nodos adonde enviar el resultado.
- **Rehacer** reemplaza la dinámica alineada anterior. Para ver, abra las series *Dinámica alineada* y *Sustracción alineada* del estudio; la ventana Dinámica aún no las usa sola.
- **Cuidado**: verifique siempre con la original. Esta versión se probó en estudios sintéticos; la RM en archivo multiframe (Enhanced) aún no es compatible.

### Los mapas

| Mapa | Qué muestra |
|---|---|
| MSI | velocidad del realce inicial (señal/min) |
| PEI | realce de pico, en % sobre el precontraste |
| SER | razón de realce: < 0,9 persistente, 0,9–1,1 meseta, > 1,1 lavado |
| Cinética | las seis clases en color: el tono dice el comportamiento tardío (azul persistente, verde meseta, rojo lavado) y el brillo dice la intensidad |
| Sustracción | pos menos pre |
| MIP temporal | el mayor realce de cada vóxel en **cualquier** fase poscontraste (máximo de las sustracciones): la lesión aparece en su pico, aunque sea fuera de la fase inicial |
| Media temporal | el realce medio de las fases poscontraste |
| Llegada (BAT) | el tiempo (s) hasta que el realce del vóxel llega al 10 % de su pico, interpolado entre las fases |
| Lavado | la mayor pendiente de **descenso** después del pico (unidad del MSI); 0 cuando la curva no baja |
| iAUC90 | el área bajo la curva de realce en los primeros 90 s (unidad del PEI) |
| Tiempo medio (MRT) | el tiempo medio del realce, ∫t·realce / ∫realce (s) |

Los cuatro últimos (0.99.48) también salen por curva, en las columnas BAT, Lavado, iAUC90 y MRT de la tabla y en *Copiar valores*.

**Farmacocinética: Tofts, Ktrans** (0.100.67; botón *Ktrans (Tofts)…* del panel). Calcula, vóxel a vóxel, el modelo de Tofts: **Ktrans** (min⁻¹, el paso del contraste del plasma al intersticio), **ve** (la fracción del espacio extravascular extracelular), **kep** = Ktrans/ve (la vuelta al plasma) y, en el **Tofts extendido**, **vp** (la fracción de plasma). Los mapas entran en la lista *Cuadro activo* (el Ktrans va solo a un cuadro de mapa sin ROI), y cada ROI o punto recibe las columnas Ktrans, ve y kep en la tabla y en *Copiar valores*. La ventana pide:

- **Entrada arterial**: la *poblacional (Parker)*, que es la curva media del contraste en el plasma medida en pacientes, para la dosis estándar; o la **ROI en una arteria**: dibuje antes una ROI dentro de la aorta o de la mamaria interna en un cuadro de la dinámica, y aparece en la lista.
- **Inicio de la inyección**, contado desde la hora de la fase pre (de fábrica, media fase: el contraste entra cuando termina la pre y la imagen vale por el medio de la adquisición).
- **T1 del tejido antes del contraste**: supuesto (no hay mapa de T1 en el estudio de rutina): cerca de 1250 ms a 1,5 T y 1450 ms a 3 T para el tejido fibroglandular. **TR** y **ángulo** vienen del estudio; sin ellos, la concentración sale por una aproximación lineal. **Relaxividad** del contraste y **hematocrito**.

> **Lea el aviso de la ventana.** El modelo pide una imagen cada 5 a 15 segundos. La RM de mama de rutina hace una fase cada 60 a 90 s: el pico arterial no se ve, el T1 es supuesto y la entrada arterial es la poblacional. En ese caso el Ktrans es **indicativo**: sirve para comparar regiones del mismo estudio y estudios del mismo protocolo, no como valor absoluto ni para comparar con la literatura. En las pruebas con curvas simuladas (condición ideal, con el T1 y la hora de la inyección correctos), con una fase por minuto el error queda en torno al 5 a 15 % para Ktrans hasta 0,25 min⁻¹ y crece mucho por encima de eso; con una imagen cada 5 s, queda por debajo del 3 %. Lo que valió para los mapas queda escrito en lo alto del panel mientras estén activados. Donde el ajuste no cierra (sin realce, ruido, vaso), el mapa queda en cero. **Desactivar**, en la misma ventana, quita los mapas y las columnas.

**Mapas en color** (0.99.64, como ColorViz/AngioViz): *Tiempo en color* pinta cada vóxel que realza por la hora del pico (rojo temprano, amarillo y verde en el medio, azul tarde) con el brillo por el realce máximo (el percentil 99 del tejido que realza vale brillo completo, igual en todos los cortes); muestra el orden de llegada, que el mapa cinético de 6 colores no muestra. *Fases en color* pone el realce de la fase inicial en el rojo, el de la intermedia en el verde y el de la tardía en el azul: lo que lava queda rojizo, lo persistente azulado. Fuera del tejido que realza (el umbral de los mapas), negro. Son imágenes en color: se guardan como serie, pero no se reformatean ni entran en los cálculos por ROI.

**Fases fuera de la cuenta y línea de base** (botón *Parámetros…*). En *Fases fuera de la cuenta (movimiento)* escriba el número de la fase que se movió (por ejemplo `4`, o `4, 7`): sale de los mapas y de los cálculos de las curvas, y el resto se recalcula con los tiempos reales. No pueden salir la fase inicial, la tardía, todas las pre, ni dos fases seguidas (la curva perdería el tramo entero). En el gráfico la fase sigue dibujada, marcada "fuera"; en la lista de las vistas aparece "(fuera de la cuenta)", y el título del panel y la línea de resumen dicen cuáles salieron. *Línea de base: media de todas las fases hasta la precontraste elegida* usa la media de las fases pre como línea de base: con dos pre o más, menos ruido. Con una sola fase pre, el panel avisa.

**Paisaje.** Con la sustracción activada en el menú de la fase (esquina del cuadro), *Paisaje (anatomía en la sustracción)* devuelve 10, 20, 30 o 50 % de la anatomía a la sustracción, para encontrar el pezón, el clip o la piel sin cambiar de serie. Vale para todas las fases y aparece en la esquina ("sustracción + 20 % anatomía"). La sustracción digital (DSA) tiene la misma opción en su menú.

Cada mapa guarda el color que usted eligió por último, por separado. La leyenda de al lado siempre muestra la tabla en uso.

**Cambiar el plano**: la casilla **Plano:** en lo alto del panel, o la esquina del cuadro: Adquisición, Axial, Coronal, Sagital y **Oblicuo** (girable). Vale para los mapas, para la sustracción y para las fases. Girar el plano calcula todos los cortes de una vez (algunos segundos, con barra y botón de detener). **Volver al plano de la adquisición** vuelve al corte que estaba a la vista. El cuadro reconstruido no entra en las curvas (una ROI en un corte reconstruido atravesaría varios cortes originales), pero se puede **segmentar en él**.

### Curvas tiempo-intensidad

Con la herramienta **Intensidad** haga clic en un punto, o dibuje una ROI (elipse, rectángulo, polígono) en cualquier cuadro de la dinámica. La curva aparece en el panel, con la clasificación en la misma regla del mapa. **Peor píxel de las ROI** encuentra, dentro de la ROI, el píxel más sospechoso y lo marca con ✳.

### Medir la lesión

Herramienta **Segmentar 3D**: haga clic en la lesión y el programa hace crecer la región en tres dimensiones sobre el realce, no sobre la señal bruta: en la señal bruta la grasa es tan clara como la lesión.

- **Umbral**: la barra *incluye más ← → incluye menos* aprieta o suelta la región, y se rehace sola cuando usted deja de arrastrar: volumen, patrones y distancia junto. Los botones − y + hacen lo mismo en pasos.
- La lesión aparece dibujada en **todas las series y planos** del estudio: en las reconstrucciones, en las otras fases, en T2, en difusión. Se guarda en milímetros, en el espacio del paciente, y vuelve dibujada cuando usted reabre el estudio.

| Número | Qué es |
|---|---|
| Volumen | el volumen de la región crecida, en mL |
| Angiovolumen | el volumen de la parte que realza: excluye necrosis, fibrosis y quiste |
| Realce de pico | mayor aumento porcentual en la fase de pico, con la media al lado |
| Ejes perpendiculares | los tres mayores ejes perpendiculares entre sí; no es la caja en los ejes de la serie |
| Eje mayor | el que va al informe |
| Porcentaje de los seis patrones | la distribución que el mapa muestra en color, en número |
| Heterogeneidad cinética | entropía de Shannon de las seis clases, normalizada de 0 a 1 (la fórmula de CADstream no está publicada, y la pantalla lo dice) |

> **Una región fina y larga es vaso, no masa.** Cuando el alargamiento pasa de tres veces el diámetro de la esfera del mismo volumen, el programa avisa. No decide por usted: avisa, y el ajuste del umbral es el freno.

En la ventana de la lesión: **Guardar como medición**, **Guardar y vincular a una lesión…** (seguimiento), **Guardar como DICOM SEG**, **Superficie 3D (STL)…** y los dos botones siguientes.

### Distancia al pezón

El botón **Distancia al pezón** mide desde el **borde** y desde el **centro** de la lesión hasta el pezón. Hay dos maneras de encontrar el pezón:

- **Marcar el pezón** (recomendado): haga clic en el botón y después en el pezón, en la imagen. La distancia sale **en el acto**, a partir de su punto, y el punto vale para **las otras lesiones de la misma mama** en el estudio: en una adquisición de las dos mamas, cada mama tiene el suyo. Reabierto el estudio, el punto vuelve de las lesiones guardadas.
- **Automático**: sin marca, el programa busca el pezón por la superficie de la piel: el punto más anterior de la piel del lado de la lesión. Tarda unos 15 segundos en la primera lesión del estudio. Se equivoca en una mama cortada en el campo o con pezón retraído; por eso la pantalla dice si el punto es suyo o del programa.

La distancia entra en la medición guardada, en el rótulo de la medición, en el panel de mediciones, en el informe y en la captura. Las distancias a la piel y al pectoral salieron del programa.

### Captura de la lesión (2×2)

**Guardar captura (SC)…** graba en el estudio una imagen 2×2 de la lesión, como serie nueva "Captura: <nombre>":

- sagital y coronal arriba, axial y la curva de realce abajo; las imágenes son la **2.ª fase** de la dinámica (la primera poscontraste), con el borde de la lesión en su color, el **plano entero** (sin zoom), letras de orientación y regla de 10 mm;
- la curva es la señal media de la lesión entera por fase, con tipo de curva, SER y clase cinética;
- pie con volumen, angiovolumen, realces, ejes, patrón dominante, heterogeneidad, distancia al pezón, umbral usado y "medición semiautomática — verificar".

Si la lesión ya tiene captura, el programa pregunta: **Reemplazar la anterior**, **Crear nueva** o Cancelar.

### Editar una lesión

En el panel **Mediciones**, **Editar lesión…** (o doble clic en la fila) reabre la ventana con el nombre, el método, el umbral y el pezón que usted usó; **Guardar** actualiza la misma medición. Si la dinámica no está abierta, el programa ofrece abrirla con las fases en que se midió la lesión.

### Números del estudio entero

Botón **Números del estudio…** en el panel de la dinámica. Mide sobre la máscara de la mama y devuelve: volumen de la mama en la máscara, angiovolumen del estudio, realce de fondo del parénquima (media y mediana) y el porcentaje de cada uno de los seis patrones, con la fórmula escrita al lado.

> **Hasta dónde vale hoy ese número.** La máscara corta en la pared torácica, pero mantiene piel, vasos y músculo pectoral. Entonces el número sirve para comparar a la misma paciente y el mismo servicio a lo largo del tiempo, no para volverse categoría en el informe ni para comparar con un número publicado. El realce medido solo en el tejido fibroglandular está en el botón siguiente.

### Fibroglandular y realce de fondo

Botón **Fibroglandular y realce…** en el panel de la dinámica. El programa separa, en la mama, el **tejido fibroglandular** (FGT) de la grasa y mide cuánto **realza** en la primera fase poscontraste.

- **Dónde separa**: en el **T1 sin saturación** del estudio (el "A T1", "Axi T1" o "Ax T1 FSE"), que es donde grasa y glándula más se distinguen; sin él, en el **Dixon** (el par FAT:/WATER:, por la fracción de grasa); sin los dos, en la **precontraste de la dinámica**, con el aviso de que el número es menos confiable.
- **Cómo**: quita la piel (3 mm), corrige el degradado de la bobina usando la grasa como referencia y separa con un umbral automático (Otsu) en cada mama. Quita también el **músculo** (el oscuro pegado a la pared torácica, hasta 25 mm de ella) y la pared lateral del tórax (lo que queda detrás del punto más anterior del pulmón). Un **implante** (bloque oscuro, liso y grueso) sale de la cuenta, con aviso.
- **El resultado**: en cada mama, el porcentaje y el volumen del FGT; y, con la dinámica abierta, la **mediana del realce** del FGT y cuánto de él realza más del 20 %. La máscara se lleva a la cuadrícula de la dinámica por la posición en el paciente, así que la dinámica puede tener otra resolución.
- **Copiar frases** lleva dos frases listas para el informe; **Grabar la máscara (SEG)** graba la mama y el FGT como una serie de segmentación (*Mama y fibroglandular · Ipê*), para verificar encima de las imágenes.

> **El programa devuelve número, no categoría.** El porcentaje en volumen sale bien por debajo de la impresión visual (un estudio informado como "dispersas" midió 10 %), y el realce medido vóxel a vóxel aún no se ha calibrado frente a informes. La categoría de cantidad (a–d) y la de realce de fondo (mínimo a acentuado) quedan con el médico; el número sirve para seguir a la misma paciente y para ver asimetría entre las mamas.

### Dinámica lista al llegar

En **Automatización ▸ Dinámica lista** se puede mandar al programa, en cuanto llega un estudio que coincide con la regla, detectar las fases y decodificar los cuadros en segundo plano: el estudio se abre al instante. Nada se graba como serie y nada se envía.

## Difusión (ADC) en cualquier RM

Botón **Difusión** en la barra, en **toda RM** (desde la 0.100.37; antes, solo cuando alguna serie decía DWI, DIFUSAO, TRACE… en la descripción: los aparatos que llaman a la difusión de otra manera se quedaban sin el botón). Abre un panel que no es modal: se puede dibujar en el cuadro con él abierto.

- **Serie de difusión**: la del estudio, elegida sola por la descripción; las otras RM quedan en la lista, porque no todo aparato escribe "DWI".
- **Valores de b**: leídos del archivo: el estándar (0018,9087) y los lugares propios de cada fabricante (GE (0043,1039), Siemens, Philips). Una casilla por b: desmarque el b que no quiera en el ajuste. Cuando el archivo no dice el b, escríbalos en el orden en que se repiten en cada corte (p. ej.: *0, 1000*). En la serie de GE anonimizada, que pierde el privado, la imagen sin b en una serie en que las otras tienen b > 0 es el b0: el panel avisa que lo dedujo.
- **Avisos antes de calcular**: un solo b; sin b0; mayor b por debajo de 500; cortes sin todos los b; TE distinto entre los b; más de una imagen por b en el mismo corte.
- **Calcular y grabar el ADC**: regresión de ln(S) contra b en todos los b marcados (con dos b, es ln(S0/Sb)/b). Unidad **×10⁻⁶ mm²/s**, la misma del ADC de GE. Un píxel con señal del b0 por debajo del *umbral de ruido* (5 % del percentil 99, de fábrica) queda 0; con tres b o más, el píxel con ajuste peor que el *R² mínimo* (0,25) también. El mapa se graba como serie de RM del estudio ("ADC (Ipê) · b0-1000"), con la geometría de la DWI: sincroniza, mide con las ROI de siempre (el valor del píxel es el ADC), va a la película, a la exportación y al PACS, y se abre en el cuadro activo.
- **DWI sintética**: S(b) = S0·e^(−ADC·b) en un b elegido (50 a 5000), grabada como "DWI sintética b1500 (Ipê)". Es una imagen calculada: no la use para calcular ADC.
- **Medir la ROI seleccionada**: dibuje una ROI (elipse, rectángulo o polígono) en un cuadro con la difusión, el ADC de aquí o el del aparato; la tabla trae, para la misma ROI, el **ADC de aquí**, el **ADC del aparato** (cuando el estudio lo tiene) y la **señal en cada b**: media, DE, mediana, mínimo y máximo. **Enviar al informe** lleva la frase con la media, la DE y el mínimo.

**Verificado en el archivo** (16 series de cinco aparatos GE, b0 y b1000 o b750): en el cráneo el ADC de aquí es el del aparato (razón 1,0002, diferencia mediana 0). En la mama la diferencia es de ruido (mediana de 120 a 330 × 10⁻⁶ mm²/s): el aparato calcula la mama con medias y direcciones que no graba en la serie DWI, y el Pioneer pone a cero el 94 % de la imagen. Por eso la tabla muestra los dos.

## Series dinámicas: juntar y separar

Dos problemas opuestos, en el mismo lugar: Configuración ▸ Protocolos de estudio ▸ **Dinámicos**:

- **Juntar**: el aparato graba una serie por fase (RM de mama). Las series que coinciden se vuelven una dinámica, y eso queda grabado en la base de datos.
- **Separar**: el aparato graba todas las fases en la misma serie (la TC trifásica). La serie se reparte en fases solo en la pantalla, con una miniatura por fase en la tira, y "Deshacer el grupo" devuelve la serie entera. No se escribe nada, ningún archivo se toca.

La regla es modalidad + la descripción contiene, comparada sin acento y sin mayúsculas, y vale al abrir el estudio. Cuando usted marca una dinámica o separa una serie a mano, el programa anota la regla como **pendiente**: aparece en la tabla y no actúa hasta que usted confirme. Tres situaciones: **Confirmada** (vale siempre), **Pendiente** (no actúa) e **Ignorar** (vale solo en el estudio donde nació).

# Listas de casos, listas inteligentes y modo reunión

El **Banco de casos**, en el panel izquierdo de la pantalla de la base de datos, organiza estudios en carpetas y listas. Al crear una (**+ Lista**), el programa pregunta el tipo:

| Tipo | Para qué sirve |
|---|---|
| Normal | una colección de estudios que usted arma a mano |
| Reunión | igual a la normal, pero cada caso recibe nombre amigable, historia, respuesta, notas y etiquetas: es la lista de una sesión clínica o de enseñanza |
| Inteligente (filtro) | usted no pone estudios: escribe un filtro, y los estudios que coinciden aparecen solos, incluso los que lleguen después |

## Crear una lista inteligente

1. En el panel izquierdo, **+ Lista**.
2. Ponga el nombre y elija **Inteligente (filtro)**.
3. Rellene el filtro. Solo los campos rellenados entran en el cálculo.

| Campo | Qué hace |
|---|---|
| Búsqueda | coincide con nombre del paciente, ID, accession o descripción. `\|` separa alternativas |
| Modalidad | Todas, CT, MR, MG, US, CR, DX, PT, NM, XA, OT |
| Estudio de los últimos | N días (0 = cualquier fecha) |
| La descripción contiene | un pedazo de la descripción del estudio |
| La región contiene | parte del cuerpo (body part) |
| La institución / unidad contiene | basta con parte del nombre |
| Origen | Cualquiera, Importado, Recibido por la red, Descargado del PACS, Preúsqueda, Anonimizado |
| Solo estudios | con imágenes clave · con mediciones · con comentario · protegidos · aún no abiertos · que no están en ninguna lista |

Ejemplos del día a día:

```
RM de los últimos 3 días       Modalidad: MR · Estudio de los últimos: 3 días
RM de mama                     Modalidad: MR · La descripción contiene: mama
Lo que aún no leí              Solo estudios: aún no abiertos
Casos con medición, para revisar   Solo estudios: con mediciones
```

La lista inteligente queda en el mismo árbol que las otras, en verde, con el conteo al lado. El contenido se recalcula cada vez que usted la abre.

> **Lo que la lista inteligente no hace.** No acepta arrastrar un estudio hacia dentro (el filtro es quien manda), no aparece en los menús "Añadir a la lista", y sus casos no tienen nombre amigable, historia ni respuesta: en una reunión aparecen como "Caso 1", "Caso 2".

## Modo reunión

Sirve para recorrer los casos de una lista uno a uno con los datos del paciente ocultos en todo el programa: sesión clínica, clase, revisión por pares.

### Cómo entrar

- Botón **▶ Modo reunión** en el panel izquierdo (presenta la lista seleccionada);
- clic derecho en la lista → **▶ Iniciar reunión**;
- clic derecho en un estudio de la lista → **▶ Reunión a partir de este caso**;
- botón **Reunión** de la barra inicial.

### La barra de la reunión

| Botón | Atajo | Qué hace |
|---|---|---|
| ◀ Anterior / Siguiente ▶ | Alt+← / Alt+→ | avanzar por los casos |
| Casos ▾ | — | menú con todos, para saltar directo |
| Historia | Alt+H | muestra el texto de la historia clínica del caso |
| Revelar respuesta | Alt+R | muestra respuesta, notas y etiquetas |
| Pantalla completa | F11 | oculta el marco de la ventana |
| Terminar reunión | — | vuelve a lo normal |

### Qué cambia mientras la reunión está activada

- la tabla de la base de datos queda anonimizada, con el nombre amigable del caso en lugar del paciente;
- todas las pestañas del visor quedan con Anonimizar activado y bloqueado, y la película también;
- las ventanas del PACS, de la Gestión y del Panel de películas quedan no disponibles, con la explicación en la pantalla;
- solo un caso abierto a la vez: al pasar al siguiente, el anterior se cierra.

El botón **Ocultar** de la pantalla inicial hace lo mismo para ocultar los datos fuera de una reunión.

## Paquete de casos (se abre en el navegador)

A partir de la 0.100.56 una lista se vuelve un **paquete de casos**: una carpeta con el visor completo (el mismo de Ipê Web, con MPR, MIP, fusión, mamografía y mediciones) y los estudios anonimizados, para clase, congreso o para enviar a colegas. Quien lo recibe no instala nada.

### Preparar los casos

En **Organizar lista** (clic derecho en la lista), cada caso tiene dos partes:

| Parte | Campos |
|---|---|
| Presentación | Nombre del caso, Etiquetas, **Historia** (clínica, datos, la pregunta), **Series a abrir** (ninguna marcada = todas) |
| Resultado | **Respuesta** (diagnóstico), **Informe / resultado** (el botón **Usar el informe del estudio** copia el texto del informe: verifíquelo y quite nombres), **Biopsia / AP**, **Notas de enseñanza**, **Series del resultado** (solo aparecen al mostrar el resultado: la pieza, el PDF de la anatomía patológica, la imagen con la marca) |

Las **marcas** hechas en Ipê (flechas, mediciones, ROI) van en el paquete y solo aparecen en el resultado. Los PDF y las fotos adjuntos al estudio entran como documentos del caso (los de una serie del resultado, solo en el resultado).

### Exportar

Clic derecho en la lista → **Exportar paquete de casos (se abre en el navegador)…** → elija la carpeta. Ipê crea una carpeta con el nombre de la lista que contiene:

- `Abrir casos (Windows).exe`, `Abrir casos (Mac Apple)`, `Abrir casos (Mac Intel)`, `Abrir casos (Linux)`: dos clics abren el navegador con los casos (un servidorcito solo de este ordenador; la ventana negra queda abierta mientras se ven los casos);
- `LEIA-ME.txt` (en portugués, inglés y español);
- el sitio y la carpeta `casos` con los estudios.

Los estudios salen **anonimizados**: nombre "Caso N", sin nacimiento, institución, médicos ni accession, fechas desplazadas (manteniendo el intervalo entre estudios), UID nuevos sin vuelta, texto grabado tachado en las capturas y en la ecografía (las **pantallas guardadas del aparato** —el elastograma en color, gráficos— pierden la cabecera y el pie enteros, donde están nombre, edad y nacimiento, desde la 0.100.94). Los PDF y las fotos adjuntos van como están: verifíquelos. Las imágenes van comprimidas sin pérdida (HTJ2K).

### Abrir

- **Pendrive o archivo**: copie la carpeta y use el "Abrir casos" del sistema. En el Mac, si no deja abrir, clic derecho ▸ Abrir.
- **En un sitio web**: copie la carpeta entera a cualquier alojamiento de archivos estáticos (la dirección de la carpeta abre los casos). No necesita servidor de Ipê.

Se abre la lista de los casos (con búsqueda); cada caso se abre en el visor con la pestaña **Caso** a la derecha: la historia y el botón **Mostrar el resultado**, que trae el diagnóstico, el informe, la biopsia, las notas, las series y los documentos del resultado y las marcas en las imágenes (**Ocultar el resultado** vuelve). **Anterior / Siguiente** pasan de caso. Informe, IA, envío, PACS y película quedan ocultos: el paquete no tiene servidor. Las mediciones que se hagan quedan solo en esa pestaña del navegador.

### Perfiles de ocultación

La flecha del botón **Ocultar** (en el visor) elige **qué** queda oculto. La elección vale para todas las pestañas y para la lista de la base de datos (botón Ocultar de la pantalla inicial); la reunión usa siempre *Ocultar todo*, con el nombre del caso.

| Perfil | Nombre | ID | Nacimiento | Sexo y edad | Fecha del estudio | Institución, acceso, médico | Aparato |
|---|---|---|---|---|---|---|---|
| **Ocultar todo** (el de siempre) | "Paciente oculto" | — | — | — | — | — | aparece |
| **Pantalla** | seudónimo | seudónimo | — | aparecen | aparece | — | aparece |
| **Enseñanza** | seudónimo | — | — | aparecen | **desplazada** | — | aparece |
| **Publicación** | "Paciente" | — | — | aparecen | — | — | — |

- **Seudónimo**: `PACIENTE-` y seis caracteres, el mismo para el mismo paciente mientras el programa está abierto (el actual y el previo del mismo paciente tienen el mismo seudónimo); no se graba en ningún lugar.
- **Fecha desplazada**: todas las fechas del mismo paciente retroceden el mismo número de días (30 a 329, sorteado por paciente): la fecha real desaparece, el intervalo entre los estudios queda.
- La esquina del cuadro muestra el perfil en uso (un candado y **Enseñanza**, por ejemplo), y el título de la pestaña también.
- **Ocultar en la pantalla no cambia los archivos.** Para llevar el estudio, use Exportar: con la pantalla oculta la exportación sale anonimizada, y en el perfil Enseñanza la opción **Desplazar las fechas** ya viene marcada (el mismo desplazamiento de la pantalla).

# Llamada externa (RIS, enlace y API)

La llamada externa es lo que hace que el RIS, un script o un botón en una página abran el estudio correcto en Ipê. Son tres puertas de entrada (línea de comandos, enlace `ipe://` y API HTTP local) y las tres generan internamente la misma solicitud.

> **Lo que entra y lo que nunca entra.** Desde fuera solo se aceptan abrir, descargar y situación. Borrar y exportar no se exponen, en ninguna de las tres puertas.

## Las tres puertas

1. **Línea de comandos** — `ipe-cli.exe`:

```
ipe-cli open --accession 123456
ipe-cli open --study-uid 1.2.840.113619.2...
ipe-cli open --patient-id 00987
ipe-cli open C:\carpeta\estudio          (importa y abre)
ipe-cli retrieve --accession 123456      (descarga sin abrir)
```

2. **Enlace ipe://** — para el RIS web, un correo o un acceso directo:

```
ipe://open?accession=123456
ipe://open?accession=123456&node=PACS&janela=viewer
ipe://retrieve?studyuid=1.2.840...
```

Registre el enlace una vez en cada ordenador: **Red ▸ Registrar enlace ipe:// en este ordenador**, o `ipe-cli register-url`. El registro es en el perfil del usuario y graba la ruta del ejecutable: si el programa cambia de lugar, regístrelo de nuevo. En **macOS** no hace falta registrar: `ipe://` y `dicomviewer://` son de la propia aplicación, y el enlace abre Ipê (o va al que ya está abierto).

**Alias del enlace** (0.100.32). Si el RIS ya tiene el botón de otro visor, Ipê puede atender por su nombre: en **Red ▸ Llamada externa ▸ Alias del enlace**, escriba los nombres separados por coma (por ejemplo `osirix, horos`). Al guardar, Ipê se registra en el sistema para esos nombres. El alias acepta el formato de Ipê (`osirix://open?accession=123`) y el de OsiriX/Horos:

```
osirix://?methodName=displayStudy&StudyInstanceUID=1.2.840...
osirix://?methodName=displayStudy&PatientID=12345
osirix://?methodName=displayStudy&AccessionNumber=123456
```

Solo se aceptan abrir y buscar; `downloadURL` (descargar de una dirección cualquiera) se rechaza. Valen las mismas reglas de `ipe://`: con el token abre directo, sin el token vale la elección *Enlace ipe:// sin el token*. Si el programa de verdad (OsiriX) también está instalado, es el sistema el que decide quién atiende; Ipê pide ser el predeterminado al registrarse. En macOS cada alias se vuelve una aplicación mínima en `~/Applications/Ipe links`, que solo pasa el enlace a Ipê; quitar el alias de la lista borra esa aplicación.

3. **API HTTP local** — para scripts y para el RIS en la misma máquina:

```
GET http://127.0.0.1:8042/api/open?accession=123456&token=SU_TOKEN
GET http://127.0.0.1:8042/api/retrieve?studyuid=1.2.840...&token=SU_TOKEN
GET http://127.0.0.1:8042/api/status?token=SU_TOKEN
Respuesta: {"ok": true, "resultado": "aberto"}
El token también vale en la cabecera: Authorization: Bearer SU_TOKEN  (o X-Token)
```

## Todos los parámetros

Valen igualmente en el enlace y en la API. En la línea de comandos, el mismo parámetro aparece como opción con dos guiones.

| Parámetro | Línea de comandos | Qué hace |
|---|---|---|
| accession | --accession | número del pedido. Es el más usado por el RIS |
| studyuid o study_uid | --study-uid | StudyInstanceUID |
| patientid o patient_id | --patient-id | abre el estudio más reciente del paciente (uno solo) |
| node | --node | dónde buscar si el estudio no está en la base de datos: nombre exacto del nodo o AE title exacto. Sin esto, busca en todos los nodos marcados como "usar en la búsqueda" |
| janela (o window, modo) | --janela | viewer = solo el visor en esta llamada; completo = el programa entero. Sin el parámetro, vale la configuración de Red |
| token | — | solo en la API HTTP; obligatorio |
| requestType | — | IHE IID: PATIENT (los estudios del paciente) o STUDY (los estudios pedidos) |
| accessionNumber, studyUID, patientID | — | los nombres del IHE IID; varios valores separados por coma (o el parámetro repetido); patientID acepta `123^^^EMISOR` |
| mostRecentResults (o recentes) | — | cuántos estudios abrir, de los más recientes (hasta 4) |
| modalitiesInStudy (o modalidades) | — | solo estudios con estas modalidades: `CT,MR` |
| lowerDateTime / upperDateTime (o data_de / data_ate) | — | período: `2025-01-01` o `20250101` |
| containsInDescription (o descricao) | — | solo estudios cuya descripción contiene el texto (sin diferencia de acento y mayúscula) |
| c | — | enlace cifrado (abajo) |

Un valor que el programa no entiende se rechaza con motivo ("janela=minimizado: use viewer o completo"), en vez de ignorarse en silencio.

### IHE Invoke Image Display

El programa entiende el perfil **IHE IID** (el mismo de Weasis ViewerHub): `GET http://…:8042/IHEInvokeImageDisplay?requestType=PATIENT&patientID=123&mostRecentResults=2&modalitiesInStudy=CT&token=…` (o `/display`). Por el paciente sin filtro abre el estudio más reciente; con filtro, los que pasan (hasta 4). Los filtros valen también cuando el estudio se busca en el PACS. Los parámetros del IID que el programa no usa (viewerType, diagnosticQuality, keyImagesOnly) se aceptan y se ignoran.

### Enlace cifrado

El enlace común lleva el ID del paciente en texto abierto, y el enlace queda en el historial del navegador. El **enlace cifrado** es `ipe://open?c=…`: nada del paciente a la vista, solo quien tiene el **token de la API** consigue armarlo, abre directo (como el enlace con token) y **vale 24 horas**. Para armarlo: **Red ▸ Llamada externa ▸ Armar enlace cifrado…**, o `ipe-cli link-cifrado "accession=123&node=PACS"`. El RIS lo arma igual, con HMAC-SHA256 (biblioteca estándar de cualquier lenguaje):

```
clave = SHA256(token);  kc = HMAC(clave, "ipe-cifra");  ks = HMAC(clave, "ipe-selo")
texto = "accession=123&t=<segundos desde 1970>"
nonce = 16 bytes aleatorios;  flujo = HMAC(kc, nonce + i en 4 bytes) para i = 0, 1, 2…
cifrado = texto XOR flujo;  sello = HMAC(ks, nonce + cifrado)[:16]
c = base64url(nonce + cifrado + sello), sin "="
```

## Qué pasa con la solicitud

1. El programa busca en la base de datos local por accession, study UID o patient ID.
2. Lo encontró: abre hasta 4 estudios (1 cuando la búsqueda fue por patient ID). Con `retrieve`, responde `ja_no_banco` y no vuelve a descargar nada.
3. No lo encontró: busca en todos los nodos configurados (o solo en el nodo nombrado), responde `buscando` en el acto y manda descargar los 4 más recientes.
4. Nada encontrado: la barra de estado muestra el error de cada nodo y la respuesta es `nao_encontrado`.

> **El estudio llamado desde fuera se abre mientras se descarga.** Es lo contrario del predeterminado de la búsqueda manual, y a propósito: en la llamada externa no hay nadie para responder una pregunta. En Red ▸ Llamada externa, la casilla *La llamada externa abre el estudio mientras se descarga*.

## Modo "solo el visor"

Cuando la llamada abre solo el visor, el estudio aparece en una ventana maximizada y la base de datos no aparece, ni hay camino hacia ella por esa ventana:

- la barra de menú tiene solo Ver, Usuario y Ayuda;
- Exportar, Guardar mediciones como DICOM SR y Enviar a la película quedan ocultos;
- el estudio se abre en todos los monitores marcados como viewer, repartido por el mismo criterio del camino normal;
- cerrar la ventana de un monitor cierra el estudio en todos;
- al cerrar el estudio, el programa continúa en la bandeja: el nodo DICOM sigue recibiendo y la próxima llamada abre al instante.

**Otro paciente con uno ya abierto.** Si la llamada trae otro paciente mientras uno aún está abierto en algún monitor, Ipê pregunta: cerrar el anterior en todos los monitores, mantener los dos o no abrir. En Red ▸ Llamada externa, *Llamada con otro paciente abierto* decide sin preguntar. Abrir el siguiente con el anterior a la vista es como la imagen de uno acaba informada con el nombre del otro. La película hace lo mismo: poner imágenes de otro paciente en una película que ya tiene imágenes pide confirmación.

Se activa en **Red ▸ Llamada externa ▸ Abrir solo el visor (sin la base de datos)**, o por una llamada con `janela=viewer` / `janela=completo`: el parámetro manda sobre la configuración.

> **Esto no es control de usuario.** Quien tenga acceso a la máquina aún puede abrir el programa por el acceso directo. Para una estación en que el operador vea solo lo que el RIS envió, combine este modo con un usuario sin permiso de búsqueda y exportación (capítulo 14).

## Configurar la API HTTP

Red ▸ bloque *Llamada externa*:

| Campo | Observación |
|---|---|
| API HTTP local activada | de fábrica, activada |
| Puerto HTTP | 8042 de fábrica |
| Token | generado solo en la primera ejecución; botones Generar nuevo y Copiar. Sin token configurado, toda llamada recibe 401 |
| Aceptar llamadas de otros ordenadores | desactivada, la API escucha solo en 127.0.0.1. Activada, acepta solo las IP de la lista |
| IP permitidas | separadas por coma |

Solo se acepta GET. Todo valor pasa por un tamiz de caracteres y tamaño; todo lo que llega por enlace o HTTP va al registro con el origen.

## Instalado y portátil

El paquete trae dos ejecutables: `Ipe.exe` (el de ventana) e `ipe-cli.exe` (el de consola): en Windows, un programa de ventana no tiene salida estándar, así que los comandos que responden texto necesitan el segundo. En la versión portátil (ZIP), todo funciona igual, menos el enlace `ipe://`, que no viene registrado: ejecute `ipe-cli register-url` una vez.

### Idioma

Desde la 0.99.33 el predeterminado es el **inglés**. El instalador de Windows pregunta el idioma en la primera pantalla (inglés, portugués o español, con el inglés marcado) y graba la elección para el programa; los scripts `instalar.bat` e `instalar.sh` preguntan lo mismo. La versión portátil pregunta la primera vez que se abre. Después, **Configuración ▸ Sistema ▸ Idioma** lo cambia, y por la línea de comandos: `ipe-cli set-language pt-BR` (o `en`, `es`). Quien ya usaba el programa continúa en el idioma que había elegido.

La traducción cubre las pantallas, menús, mensajes y las IA. Quedan como están los nombres que vienen del estudio (descripción de la serie, institución, paciente) y las siglas. También quedan en portugués los nombres de las series DICOM que las IA crean ("Encéfalo", "Lesões hepáticas"… — el programa las reconoce por el nombre), las cabeceras de la hoja de cálculo del lote, las listas de palabras clave y las plantillas de informe. En la 0.100.118 todas las ventanas, menús y mensajes se verificaron en inglés. ¿Encontró un texto en portugués en la pantalla en inglés o español? **Configuración ▸ Sistema ▸ Idioma ▸ Editar traducciones** lo corrige en el acto, y vale la pena avisar para que entre en la próxima versión.

# Red DICOM, PACS y automatización

## Nodos y recepción

**Configuración ▸ Red ▸ Nodos DICOM…**. La pestaña *Este ordenador* define el AE title, el puerto y quién puede conectarse: así el aparato o el PACS envía estudios aquí. Las otras pestañas registran los nodos remotos.

![Configuración ▸ Red ▸ Nodos DICOM, pestaña Este ordenador: el nodo DICOM y la llamada externa.](config_rede.png){75}

### Dos tipos de nodo: DIMSE y DICOMweb

En el registro de un nodo, el primer campo es **Tipo de conexión**, y cambia los campos siguientes:

| | DICOM clásico (DIMSE) | DICOMweb (HTTP) |
|---|---|---|
| Cómo habla | C-FIND, C-GET / C-MOVE, C-STORE | QIDO-RS, WADO-RS, STOW-RS |
| Identificación | AE title de los dos lados | usuario y contraseña, OAuth2 / OIDC o token |
| ¿Necesita puerto abierto aquí? | solo con C-MOVE | no |
| ¿Atraviesa firewall y proxy? | difícil | sí, es HTTP |

La dirección del DICOMweb es la base, la que suele terminar en `/dicom-web` (por ejemplo `http://192.168.1.216:8042/dicom-web`). **Probar red** funciona en los dos.

> **Tres cosas sobre el DICOMweb.** No existe C-MOVE allí: la descarga vuelve por la misma conexión. La identidad de AE no vale en un nodo DICOMweb: quien identifica es el inicio de sesión. Y la contraseña, el token y el secreto del cliente quedan **cifrados** en este ordenador (en Windows por la protección del propio sistema; en los otros, por una clave local de la carpeta de configuración): la base copiada a otro ordenador no abre las contraseñas; allí, escríbalas de nuevo. Las contraseñas grabadas antes de la 0.99.55 se cifran la primera vez que el programa las lee. Use un usuario solo de lectura cuando el PACS lo permita.

**Autenticación** del nodo DICOMweb:

| Opción | Cuándo usar | Campos |
|---|---|---|
| Usuario y contraseña (Basic) | Orthanc, dcm4chee sin inicio de sesión central | usuario y contraseña |
| OAuth2 — credenciales del cliente | PACS en la nube, integración entre sistemas | token / emisor, ID y secreto del cliente, alcance |
| OAuth2 — usuario y contraseña (Keycloak) | dcm4chee-arc u Orthanc con Keycloak, cada médico con su inicio de sesión | token / emisor, ID (y secreto) del cliente, alcance, usuario y contraseña |
| Token fijo (Bearer) | el PACS entregó un token listo | el token, en el campo Contraseña / token |

En **Token / emisor** va el *token endpoint* (termina en `/token`) o solo la dirección del **emisor OIDC** (en Keycloak, `https://login.ejemplo/realms/pacs`): el programa lee `/.well-known/openid-configuration` y encuentra el endpoint solo. El token queda en memoria hasta cerca de vencer y se renueva sin pedir la contraseña de nuevo; si el PACS lo rechaza (401), el programa pide otro una vez. **Probar red** ya hace el inicio de sesión.

| Campo del nodo | Para qué sirve |
|---|---|
| Nombre / AE Title / Host / Puerto | identificación del nodo remoto |
| Usar en la búsqueda | entra en la búsqueda cuando no se nombra ningún nodo |
| Usar en previos | entra en la prebúsqueda de estudios previos |
| Usar en el envío | aparece en la lista de destinos de "Enviar a" |
| Recuperación | C-GET (las imágenes vuelven por la misma conexión) o C-MOVE (el PACS abre conexión de vuelta y necesita tener este ordenador registrado) |
| Abrir mientras descarga | por nodo; vacío = usa el estándar de las preferencias |

### Identidades: hablar "como" otro aparato

Algunas modalidades solo conversan con quien conocen, el OsiriX de la sala, por ejemplo. En **Configuración ▸ Red ▸ Nodos DICOM…**, pestaña **Identidades**, usted registra esos AE (nombre, AE title, destino del C-MOVE y en qué nodos pueden usarse). Después:

- en la búsqueda del PACS, el campo **Como:** elige con qué identidad buscar y descargar;
- en **Enviar a ▸ nodo ▸ como…**, la identidad elegida es la que envía.

### Cuando el DICOMweb se queja

| Mensaje | Qué verificar |
|---|---|
| HTTP 401 — usuario o contraseña rechazados | el usuario y la contraseña del nodo |
| HTTP 403 — acceso denegado | el usuario existe pero no tiene permiso para esa operación |
| HTTP 404 — dirección no encontrada | la base: falta o sobra /dicom-web, o el puerto está equivocado |
| no se aceptó el certificado | HTTPS con certificado propio: marque aceptar certificado no verificado |
| no pude hablar con el servidor | dirección, puerto o ruta |

## Buscar y descargar

Botón **PACS** (o Ctrl+Shift+F). Búsqueda por paciente, ID, accession, fecha y modalidad, en uno o en varios nodos a la vez. El resultado trae las series, y se puede descargar serie por serie; eso depende de que el PACS responda al C-FIND de series; cuando no responde, la descarga es del estudio entero.

Clic derecho en los resultados de la búsqueda:

| Elemento | Qué hace |
|---|---|
| Descargar a ▸ | el estudio (o las series marcadas) va **del nodo directo a otro destino**, sin pasar por este ordenador: un C-MOVE pedido al nodo de origen, con la identidad de *Como:*. **Otro AE…** acepta un destino no registrado. Quien decide si acepta el destino es el nodo de origen |
| Enviar a ▸ nodo ▸ como… | descarga el estudio aquí (si aún no está) y, al terminar, lo envía al nodo elegido con la identidad elegida. Un estudio ya completo aquí sale en el acto |
| Descargar directo al cliente | solo en el **Ipê cliente** (0.100.110), para los nodos del servidor central: el nodo envía al servidor, el servidor pasa el estudio a la base **de este ordenador** y borra su copia cuando el estudio llega entero aquí (hasta 3 intentos para lo que falte). Lo que ya estaba en el servidor antes de la descarga sigue allí. El servidor no ejecuta las reglas de llegada en el estudio de paso; las de este ordenador se ejecutan cuando llega. También es un botón junto a *Descargar y abrir* |

La descarga usa la identidad de **Como:** de la búsqueda; el envío usa la elegida en el menú: son dos, a propósito. Las tareas aparecen en la cola de transferencias, con avance, cancelar y el motivo de cada error ("X no conoce el destino Y: necesita estar registrado en X").

### Lote desde una planilla (0.100.97)

**Red ▸ Lote desde una planilla…** hace lo mismo con cada estudio de una lista: lo encuentra, lo descarga, ejecuta las IA, envía, imprime y exporta, y graba una planilla con los resultados. Sirve para estudios (validar las IA contra los informes, densidad × puntuación de calcio) y para trabajo en masa (ejecutar el enfisema en todas las TC de tórax de un mes, enviar los resultados al PACS).

La ventana tiene cinco pasos (a la izquierda) y, arriba, las **plantillas**: elija una y pulse **Usar**; **Guardar como plantilla…** guarda la configuración para repetirla (sin la planilla). Para solo traer los estudios de la lista a la base de datos, sin ejecutar ninguna IA, use la plantilla lista **Solo descargar** (0.100.115): ninguna IA, ni la automática de la llegada (*Estudio descargado: aplicar las reglas de la llegada* desmarcado), y los estudios quedan en la base al final.

1. **Planilla**: CSV/TSV, XLSX u ODS (el `.xls` antiguo, guárdelo como `.xlsx`). Ipê elige la hoja con cara de lista y adivina el tipo de cada columna por el título: **ID del paciente, n.º de accession, fecha del estudio, Study Instance UID, nacimiento, nombre, modalidad, descripción**; lo que no reconoce queda como *otra información (mantener)*. Verifique en la vista previa y cámbielo en el selector encima de cada columna. *Otro dato del paciente* marca una columna que debe salir de la planilla anonimizada (teléfono, dirección…).
2. **Encontrar el estudio**: en **Buscar por (en orden)**, marque y ordene los intentos: **Study UID**, **n.º de accession**, **ID + fecha + modalidad**, **ID + fecha**, **ID + modalidad (cualquier fecha)**, **solo ID (cualquier fecha)**. Ipê intenta el primero marcado; si no lo encuentra, el siguiente (de fábrica: UID, accession, ID + fecha + modalidad, ID + fecha). Una fila solo con el ID, sin fecha, solo se hace con "solo ID" o "ID + modalidad" marcado. La columna **Ipê: encontrado por** dice qué intento lo encontró. Ajuste la **tolerancia de la fecha** (± días), las **modalidades** (vacío = cualquiera), **la descripción contiene**, qué hacer si encuentra **más de un estudio** (el de más imágenes, el más cercano a la fecha o todos) y si verifica el **nacimiento** (distinto = otra persona con el mismo ID: no se usa).
3. **De dónde**: primero la base de datos de Ipê; si el estudio no está, los **nodos marcados, en el orden** de la lista (arrastre o Subir/Bajar): descarga del primero que lo tenga. El ID guardado con o sin ceros a la izquierda se encuentra igual.
4. **Qué hacer** (todo opcional):
   - **Ejecutar IA**: marque cuáles. La que no sirve para el estudio se salta, con el motivo; la que el estudio ya tiene no se ejecuta de nuevo (salvo con *Ejecutar de nuevo*). Las de mamografía (densidad, calcificaciones) se ejecutan aquí mismo; las otras pasan por la cola de IA (aparecen en *Tareas de IA*).
   - **Verificar el protocolo de RM**.
   - **Enviar** a nodos: los originales, los resultados de las IA o los dos.
   - **Imprimir** las **series de verificación** de las IA (la tabla de la densidad y de las calcificaciones, el mosaico de la rigidez hepática, el enfisema…) en un destino de impresión o en una impresora DICOM: una imagen por hoja.
   - **Exportar** a una carpeta: las series de verificación en **PNG** o **un PDF por estudio**, y, si quiere, **los DICOM generados** por las IA.
   - **Borrar de Ipê, al final, los estudios descargados solo para el lote**: lo que ya estaba en la base de datos nunca se borra.
5. **Ejecutar**: la **planilla de salida**; **Anonimizar la salida**; **Solo ejecutar entre** (p. ej., 20:00 y 06:00: fuera de eso el lote espera); **Cuántas filas ahora** (empiece con 5 o 10). **Simular** solo busca y cuenta (no descarga ni ejecuta nada): úselo antes de un lote grande para ver si las columnas están bien. **Iniciar** / **Detener**.

**La planilla de salida**:
- **Resultados**: las columnas originales y, al lado, las de Ipê (situación, Study UID, n.º de accession, fecha, descripción, de dónde vino, IA, protocolo, enviado, impreso, exportado). Con "todos los estudios", una fila de la lista se vuelve varias.
- **IA · …**: una hoja por IA, con los números de cada estudio (la densidad con la probabilidad de A a D; las calcificaciones con el área y las escalas; el hígado con PDFF, R2* y rigidez; …).
- **Resumen** y **LÉAME**.
- **Anonimizada**: sin ID, nombre, nacimiento, accession ni UID (*Caso 0001*…); la correspondencia queda en un archivo aparte (`…-chave.xlsx`), que no debe salir de la institución. En la exportación anonimizada, las imágenes que traen el nombre del paciente escrito quedan fuera.

**No encontrado**: la observación dice por qué: el error del nodo, los estudios que el nodo devolvió y el filtro quitó, o (buscando de nuevo solo por el ID) si el paciente tiene estudios en otras fechas/modalidades, con los más cercanos. Use la Simulación para acertar las columnas y la tolerancia antes de ejecutar de verdad.

**Se puede detener y continuar**: elija la misma planilla de salida y el lote sigue desde donde se detuvo (los *no encontrados* y los *con error* se intentan de nuevo, si la casilla está marcada). La ventana no muestra el nombre del paciente: solo el número de la fila y el resultado.

- **En el Ipê cliente** de un servidor central, el lote **se ejecuta en el servidor**: los nodos son los que el servidor comparte con los clientes, las IA y las impresoras son las suyas. La ventana es la misma; sigue el avance y, al final, descarga la planilla (y la clave, si está anonimizada) a la ruta elegida y los archivos exportados a la carpeta elegida. Puede cerrar la ventana: el lote continúa en el servidor; envíelo de nuevo con la **misma planilla de salida** (el nombre del lote es el de ella) para continuar o seguirlo. Marque **Traer también los estudios a este ordenador** para tener cada estudio hecho en la base local; si el lote borra lo que descargó, el servidor solo borra después de la copia.
- **En el Ipê con base de datos propia** (incluida la del propio servidor), el lote se ejecuta allí mismo.
- **Permisos**: buscar y descargar; enviar, imprimir y exportar cuando están marcados (exportar con identificación pide *exportar identificado*).

> Son **mediciones automáticas, sin confirmación**. Antes de analizar, **verifique una muestra**: abra algunos estudios por el Study UID y mire la serie de verificación.

## Enviar

**Enviar a** está en el clic derecho de la lista de estudios, de las series de la base de datos y de los resultados del PACS, siempre con el mismo submenú: un elemento por nodo marcado como *usar en el envío*, y en cada nodo *como este programa* o *como* una identidad permitida en ese nodo. En las series, solo van las seleccionadas. La cola y el registro de acceso dicen qué fue, adónde y cómo.

## Automatización

**Red ▸ Automatización…**:

| Pestaña | Qué hace |
|---|---|
| Búsquedas programadas | busca sola en el PACS a la hora elegida y avisa o descarga |
| Previos | al llegar o abrirse un estudio, busca los previos del paciente por sus reglas |
| Enrutamiento | un estudio que llega y coincide con el filtro se reenvía a otro nodo |
| Dinámica lista | detecta las fases y decodifica los cuadros en segundo plano. No se graba nada y no se envía nada |
| Limpieza | borra estudios antiguos por edad, por modalidad o por falta de uso; los estudios protegidos nunca entran, ni las copias anonimizadas |

La pestaña **Historial** muestra lo que cada regla hizo y cuándo.

## Servidor central (intranet)

**Configuración ▸ Red ▸ Servidor central…** pone una instalación en el papel de servidor, con inicio de sesión y base de datos compartida; las otras entran como cliente. La base es un **PostgreSQL** (a continuación), que aguanta muchas estaciones a la vez.

### La base de datos: PostgreSQL (desde la 0.100.36, la única)

La base de Ipê (pacientes, estudios, mediciones, informes, listas, usuarios, configuraciones del servicio) es un **PostgreSQL**. **No hace falta instalar nada**: el PostgreSQL 16 viene dentro de Ipê. Se enciende solo cuando Ipê (o `ipe server`) se abre, guarda los datos en la carpeta de datos (`postgres`, junto a Storage; cambiar la carpeta de la base la lleva consigo) y se apaga cuando se cierra el último programa de Ipê del ordenador. Solo acepta conexión de este ordenador (las otras estaciones llegan por el servidor central de Ipê, como siempre), y la contraseña la crea y la guarda el propio Ipê, junto con los datos. Cada ubicación (disco externo, otra carpeta) tiene su PostgreSQL dentro de su propia carpeta, y sigue yendo junto con ella, entre ordenadores del mismo sistema (Windows con Windows, Mac con Mac).

**Quien viene de una versión anterior:** en la primera apertura tras la actualización, Ipê pasa la base antigua (el archivo SQLite `dicomviewer.sqlite`) a PostgreSQL, con una ventana de avance; en una base grande, algunos minutos, una sola vez. Todo va junto, y el recuento de cada tabla se verifica al final. El archivo antiguo queda guardado como `dicomviewer.sqlite.migrado`, en la misma carpeta, como copia de seguridad (se puede borrar después de verificar que todo está allí). Lo mismo vale para las otras ubicaciones, la primera vez que se abre cada una.

La base principal también puede quedar en un **servidor PostgreSQL propio**, instalado aparte, en otro ordenador o en la nube. En **Configuración ▸ Base de datos ▸ Servidor de base de datos (PostgreSQL)…**:

1. Instale PostgreSQL (postgresql.org) y cree un usuario y una base vacía para Ipê; por ejemplo, en `psql`: `CREATE USER ipe PASSWORD '…'; CREATE DATABASE ipe OWNER ipe;`.
2. En el ordenador de la base principal (el servidor central), marque *Servidor PostgreSQL propio*, rellene servidor, puerto (5432), base, usuario y contraseña y haga clic en **Probar la conexión**.
3. Para llevar lo que ya existe: **Copiar la base de este ordenador allí…** copia todo de la base en uso, tabla a tabla, y verifica el recuento de cada una al final. La base de destino tiene que estar vacía. Cierre Ipê en las otras estaciones antes.
4. **OK** y abra Ipê de nuevo: la ventana pasa a mostrar *En uso ahora: PostgreSQL usuario@servidor:5432/ipe*.

Para volver al PostgreSQL que viene con Ipê, marque la primera opción (el botón Copiar trae de vuelta lo que entró en el servidor propio). Las **imágenes siguen en la carpeta de datos** (Storage): solo la información va a la base. La contraseña del servidor propio queda cifrada en este ordenador (`banco.json`, en la carpeta de configuraciones).

En el servidor sin ventana, lo mismo por la línea de comandos: `ipe banco status`, `ipe banco postgres --host 10.0.0.2 --banco ipe --usuario ipe --copiar` (pregunta la contraseña) y `ipe banco embutido --copiar` (de vuelta al de Ipê). La variable `IPE_DATABASE_URL` (`postgresql://usuario:contraseña@servidor:5432/ipe`) pasa por delante de lo que esté configurado, para servidores montados por guion.

![Configuración ▸ Red ▸ Servidor central: el modo de este ordenador (local, servidor o cliente).](config_servidor_central.png){65}

**Abrir mientras descarga.** En el cliente, el estudio que aún no está en el ordenador se abre en pocos segundos: primero llega una imagen de cada serie (la tira las muestra todas y el protocolo de visualización arma los cuadros), después el resto de cada serie va llegando y los cuadros crecen solos. La barra de estado muestra *Descargando del servidor central: N de M imagen(es) (P%)…*. Solo se descarga el estudio abierto (y el previo que el protocolo pide comparar). Reabrir un estudio que ya llegó es inmediato; la caché tiene el límite de **Configuración ▸ Red ▸ Servidor central**, y los estudios abiertos hace más tiempo salen primero.

**Imprimir en una impresora DICOM por el servidor (0.100.49).** En el servidor, abra la impresora en **Configuración ▸ Impresión ▸ Impresoras DICOM** y marque **Compartir con los clientes**. En el Ipê del cliente, la ventana **Imprimir** del compositor de películas muestra esa impresora como *Nombre (por el servidor)*, junto con las impresoras DICOM del propio ordenador; en Ipê Web, aparece en la Salida de la película. Quien envía las hojas a la impresora es el servidor, con **su IP y su AE** (el AE de origen de la impresora, si está rellenado), útil cuando la impresora solo acepta una IP registrada: registre solo el servidor en ella. El cliente no recibe la dirección ni el AE. La película va como receta, el servidor dibuja las hojas con el mismo código y cuenta la impresión en el registro de acceso. Una impresora DICOM no compartida solo sirve en el propio servidor (hasta la 0.100.48 Ipê Web mostraba todas).

**Buscar en el PACS por el servidor (0.100.37).** En el servidor, abra el nodo del PACS en **Configuración ▸ Red ▸ Nodos DICOM** y marque **Compartir con los clientes**. En el cliente, ese nodo aparece en la búsqueda del PACS como *Nombre (por el servidor)*, junto con los nodos del propio ordenador (y también en la búsqueda de previos). Buscar y descargar funcionan como siempre, pero quien habla con el PACS es el servidor, con su AE title y su contraseña (el cliente no recibe la dirección ni las credenciales) y el estudio descargado **entra en la base del servidor**, en la base de quien lo pidió (la suya o la compartida). La cola de descargas del cliente muestra el avance de la descarga en el servidor, y cancelar allí cancela en el servidor. Buscar pide el permiso de búsqueda; descargar, el de descarga; todo va al registro de acceso del servidor. Ipê Web tiene lo mismo (a continuación). Con un nodo del servidor elegido, el campo *Como* desaparece (el AE es el del servidor) y la ventana dice que la búsqueda y la descarga son por el servidor. *Visible para* en el registro del nodo es otra cosa: dice qué usuarios del propio servidor usan el nodo. Si el servidor no comparte ningún nodo, o no respondió, la lista del PACS en el cliente lo dice; la lista se pide de nuevo cada vez que se abre la ventana del PACS.

**Cuánto ya llegó de cada serie (0.100.0).** Mientras el estudio se descarga, la miniatura de cada serie en la tira muestra *34/120 im* con una barra debajo: azul y con ⬇ la que está llegando ahora, verde las que esperan su turno (pase el ratón: la posición en la cola). El cuadro muestra **⬇ 34/120** debajo del número de la imagen hasta que su serie termine. **Poner una serie en un cuadro** (clic o arrastrar) la pasa al frente de la cola. Dos series se descargan a la vez, y lo que llega entra en la base sin detener la red. Si alguna serie no se descarga entera, la barra de estado dice cuántas imágenes faltaron y por qué; y el servidor guarda en el registro de acceso (acciones *cliente_entrou* y *cliente_download*) la versión de cada cliente y lo que hizo cada descarga (0.100.1).

**Señal de la red (0.100.1).** En el cliente, la barra de estado muestra la red hasta el servidor: **barras** de 0 a 4 (como las del móvil), la **ida y vuelta** en milisegundos y el **caudal** en Mbit/s, por ejemplo *3 ms · 870 Mbit/s*. Vale lo peor de los dos: cuatro barras piden menos de 10 ms y 300 Mbit/s o más; tres, menos de 30 ms y 80 Mbit/s; dos, menos de 80 ms y 20 Mbit/s. El programa mide al abrir (con una prueba de 2 MB) y a cada estudio abierto (solo la ida y vuelta, para no disputar la red con la descarga; el caudal pasa a ser el de la propia descarga). Haga clic en las barras para medir de nuevo; *sin conexión*, en rojo, cuando el servidor no responde.

**Más rápido para abrir y para descargar (0.100.38).** Servidor y clientes en la 0.100.38 o más nueva:

- **La descarga del cliente** quedó unas tres veces más rápida en la medición (720 cortes de TC: de 2,9 s a 0,8 s, servidor y cliente en la misma máquina). El servidor envía junto con cada imagen sus datos que van a la base, y el cliente graba el archivo directo en su lugar y la base por lotes; antes, cada imagen se grababa dos veces en el disco, se releía y se grababa en la base una a una.
- **La primera imagen llega antes**: la imagen del medio de todas las series viene en un solo pedido (antes, dos pedidos por serie, uno tras otro), y el resto solo empieza a llegar después de que el estudio se abre.
- **La conexión con el servidor queda abierta** entre los pedidos (abrir un estudio hace unas veinte llamadas al servidor; cada una abría una conexión nueva y, en https, rehacía la negociación).
- **En el servidor**, el pedido de cada imagen de Ipê Web quedó unas cuatro veces más liviano (de 220 a 930 imágenes por segundo en la medición): los permisos y "quién ve este estudio" se verifican una vez cada pocos segundos, y no en cada imagen (un cambio hecho en el servidor vale en el acto); la imagen con la copia de envío lista sale sin abrir el archivo original; y las respuestas pequeñas ya no esperan la confirmación de la red (eran 40 ms más por respuesta en Linux, y hasta 200 ms con cliente Windows).
- **Los datos que el navegador pide al abrir** (los metadatos de cada serie) quedan guardados en disco, en la carpeta `CacheWeb`, y los de los estudios de hoy y de ayer quedan listos cada 2 minutos (los de los últimos 14 días, cada 30).
- Con un servidor de versión anterior, el cliente nuevo funciona como antes, sin las mejoras.

**Menos datos en la red (HTJ2K).** El cliente recibe las imágenes comprimidas **sin pérdida** en HTJ2K (2 a 4 veces menos datos en una TC; la misma imagen, verificada píxel a píxel). El archivo del servidor **no cambia**: lo que va es una copia de envío, que el servidor prepara en segundo plano para los estudios de los últimos 14 días (cada 30 minutos, cuando nadie está pidiendo imágenes) y guarda en la carpeta `CacheWeb`, junto al archivo (que se puede borrar a voluntad). Una imagen que aún no tiene la copia lista va como está, sin esperar. Desactívelo en **Configuración ▸ Red ▸ Servidor central ▸ Recibir las imágenes comprimidas sin pérdida**. Enviar una de esas imágenes a un nodo DICOM que no acepta HTJ2K va descomprimida.

### Visor web (0.99.91)

El servidor central trae un **visor en el navegador**: en cualquier ordenador de la red, abra **`http://IP-del-servidor:8043/web/`** (o `https://…`, con el certificado de Ipê) en Chrome o Edge y entre con el mismo usuario y contraseña de Ipê. No hace falta instalar nada. Si el navegador ofrece **traducir la página**, recházalo: desde la 0.100.64 la página ya pide no ser traducida (el traductor cambiaba los textos por otros sin sentido); el idioma de Ipê Web es el del propio programa. La dirección aparece en Configuración ▸ Red ▸ Servidor central, con el enlace.

En esta primera fase:

- **Lista de estudios** con búsqueda por nombre, ID o accession, por fechas y por modalidad; cada uno ve solo lo que puede ver en Ipê (los mismos permisos y la base personal). Doble clic abre el estudio.
- **Tira de series** con las miniaturas; hacer clic pone la serie en el cuadro activo (contorno amarillo), o **arrastre la miniatura hasta el cuadro** que quiera (0.99.95).
- **Imágenes disponibles** (0.99.95): en cuanto el estudio se abre, el navegador descarga las series en segundo plano: primero las que están en los cuadros, después las otras, en el orden de la tira. Cada miniatura muestra el porcentaje y una barrita hasta quedar lista, y lo alto de la pantalla muestra el total del estudio; con 100 %, desaparecen. Si la memoria del navegador se llena (estudios muy grandes), la precarga se detiene y el resto viene cuando se muestre.
- **Carga más rápida** (0.99.96):
  - **Menos bytes en la red**: el servidor envía cada imagen sin compresión (y la mamografía en JPEG-LS) como **HTJ2K sin pérdida**. Es una copia de envío, verificada píxel a píxel y guardada en una carpeta de caché (`CacheWeb`, junto al archivo, que se puede borrar a voluntad); el archivo del acervo no cambia. En una TC, va de 2 a 5 veces menos.
  - **Carga progresiva**: la imagen grande aparece primero en una versión menor y va ganando definición mientras llega. El volumen (MPR) viene intercalado: 1 de cada 4 cortes primero, y se completa enseguida.
  - **Caché del navegador**: reabrir un estudio solo verifica con el servidor si la imagen cambió (la contraseña sigue valiendo); casi nada pasa por la red.
  - La decodificación usa todos los núcleos del ordenador menos uno, y los metadatos de la serie van comprimidos.
  - **Todas las series empiezan enseguida** (0.99.99): el navegador pide la información de todas las series de una vez (no una tras otra), el servidor lee las cabeceras en paralelo y ya prepara el estudio entero en cuanto se abre; la serie siguiente ya no espera a la anterior. Las copias de envío hechas en segundo plano esperan mientras el navegador está pidiendo imágenes, para no disputar el procesador con ellas.
  - **Carga** (barra): muestra cuántas imágenes y cuántos MB vinieron por la red, en cuánto tiempo (MB/s), cuánto tardó el navegador en decodificar cada una, en qué formato vinieron y cuántas vinieron de la caché. Sirve para saber si lo que pesa es la red o el ordenador.
- **Cuadros** de 1×1 hasta 4×4 (icono de diseño: pase el ratón por la cuadrícula y haga clic) y protocolos listos (MPR, PET/TC). **Ventanas listas** (las suyas, por modalidad) en la pestaña **Imagen** y en el menú del botón derecho.
- **Formatos**: HTJ2K (la copia de envío), JPEG-LS, JPEG 2000 y JPEG se decodifican en el propio navegador; lo que está en otros formatos (color, JPEG 2000 guardado) va como está en la base. La mamografía usa la ventana del aparato (incluida la sigmoide).
- **Seguridad**: nada del paciente queda grabado en el navegador; recargar la página pide el inicio de sesión de nuevo y la sesión parada se cierra sola. Cada estudio abierto queda en el registro de acceso ("abrió en el navegador"). En la red interna, use HTTPS con el certificado de Ipê.

**La pantalla (0.99.97), al estilo de Weasis.**

- **Una barra de iconos** (pase el ratón para ver el nombre). Los iconos con flechita abren un menú: las ROIs (elíptica, rectangular, libre) y los ángulos (ángulo, Cobb) muestran la herramienta elegida; haga clic en la flechita para cambiar.
- **Cada botón del ratón con su función, como en Ipê**: haga clic en el icono de la función **con el botón del ratón que debe hacerla**: con el izquierdo, va al izquierdo; con el del medio, al del medio; con el derecho, al derecho. La marca amarilla debajo del icono muestra cuál: a la izquierda, en el medio o a la derecha (una función puede estar en dos botones). El pie resume los tres, y la elección queda guardada en el navegador. La rueda sigue pasando los cortes.
- **Botón derecho**: **hacer clic y mantener** (arrastrando) hace su función (de forma predeterminada, el zoom); **hacer clic y soltar** abre el **menú de la imagen**: Ventana (las listas, la del archivo, invertir), Zoom (ajustar, 1:1, 2×), Girar y reflejar, Plano (Original, A, C, S, MIP), Funciones de los botones, Serie, Cuadros y cine, Borrar las mediciones de la imagen y Restaurar. Encima de una medición, el menú empieza por ella: copiar el valor, editar el texto (flecha) y borrar.
- **Panel de la izquierda**: las series (con el porcentaje descargado) y los **estudios previos** del paciente (haga clic para abrir). **Panel de la derecha**, en pestañas: **Imagen** (ventanas listas, invertir, girar, reflejar, zoom), **Mediciones** (todas las del estudio con el valor y quién midió; haga clic para ir a la imagen; copiar y borrar), **DICOM** (las etiquetas de la imagen del cuadro activo, con filtro) y **PET** (SUV, color, opacidad, tope de la ventana y segmentaciones). Los dos paneles se recogen (la flecha arriba) y se abren de nuevo por la tira fina que queda en su lugar.
- **Pie**: imágenes disponibles, velocidad de la red y decodificación, **Carga** (el panel completo) y la función de cada botón.
- **Mediciones en dos clics (0.100.3)**: la regla y las otras mediciones también se dibujan en "clic, mover, clic". Una línea empezada y no terminada se deshace al hacer clic en otro cuadro, cambiar de herramienta o pulsar **Esc**: el ratón nunca queda atrapado.
- **Doble clic amplía (0.100.5)**: doble clic en un cuadro lo lleva a 1×1; otro doble clic vuelve a la disposición de antes, con cada cuadro como estaba (corte, zoom, ventana). Un doble clic sobre una medición sigue siendo de la medición.
- **Lista con filtros rápidos y vista previa (0.100.20)**: encima de la lista, tres filas de botones: **Período** (Hoy, Ayer, 7 días, 30 días, Todo, Otro período…), **Modalidad** y **Situación** (Sin informe, Borrador, Firmado, Con IA para revisar), filtran con un clic y quedan recordados. Junto al nombre, el sello **IA** (más fuerte cuando hay hallazgos esperando revisión) y el del informe (**R** borrador, **L** firmado). **Un clic** en un estudio muestra la **vista previa** a la derecha: las series (con el sello IA), la IA del estudio y los hallazgos por estado, el informe (estado, fecha y el comienzo del texto) y los estudios previos del paciente, con el botón **Abrir el estudio**; las flechas ↑↓ recorren la lista. **Dos clics** (o Enter) abren, como antes.
- **Ventanas enlazadas (0.100.20)**: en las ventanas de visualización, el icono de cadena **Enlazar las ventanas** (activado al inicio) hace que el desplazamiento, la ventana/nivel y el zoom de una ventana sigan en las otras: en el mismo estudio, por la posición en el paciente (cuadros en el mismo plano); en la ventana del **estudio previo**, avanzando los mismos milímetros: desactive, alinee los dos estudios y active de nuevo. **Desde la 0.100.21**, con las ventanas enlazadas, el corte que usted recorre en una ventana aparece en las otras como una **línea de referencia discontinua celeste** (en los cuadros de otro plano del mismo estudio, por ejemplo el axial de una ventana sobre el sagital o el localizador de la otra); y se puede **arrastrar una serie de la tira de una ventana y soltarla en un cuadro de otra ventana**, incluso de otro estudio (la ventana de comparación).
- **Apariencia del visor (0.100.19)**: el icono **Apariencia** (final de la barra) elige dónde quedan las **series** (a la izquierda, abajo o arriba; en las dos últimas, una franja que se desplaza de lado y deja todo el ancho para las imágenes) y los **botones** (arriba, o en una columna a la izquierda, que devuelve la altura de la barra a la imagen). **Modo lectura** (el icono al lado, o la tecla **F**) esconde barra, paneles y pie y deja solo las imágenes; **Esc** o **F** vuelve. El panel de la derecha (Imagen, Mediciones, DICOM, PET, Película, IA) viene **recogido**; la flechita en el borde lo abre. Todo queda guardado en el navegador.
- **Monitores y ventanas (0.100.19)**: el botón **Monitores**, en la lista, abre la configuración (guardada en el navegador, como la pestaña Monitores de Ipê): estudios **en esta ventana** o en **ventanas separadas**; para cada ventana, el **orden** (▲▼: la Ventana 1 empieza en las primeras series, la 2 en las siguientes), lo que **presenta** (el estudio, el **estudio previo** para comparación, o no usar), el **diseño** de los cuadros y el **monitor**. *Detectar los monitores* (Chrome y Edge, en HTTPS o en el propio ordenador) lista los monitores de izquierda a derecha, y cada ventana se abre en el monitor elegido; sin eso, arrastre cada ventana a su lugar una vez: la posición queda guardada.
- **Monitores de verdad (0.100.55)**: con el permiso del navegador (Chrome y Edge, con Ipê Web en **HTTPS** o abierto en el propio servidor), el panel **detecta solo todos los monitores** (cuantos haya, cada uno con la resolución y la orientación, horizontal o vertical) y muestra una fila por monitor: el de esta ventana se queda con la lista, y para cada uno de los otros usted elige **estudio**, **estudio previo** o **no usar** y el diseño; las ventanas se numeran de izquierda a derecha. Sin el permiso (por ejemplo, Ipê Web en HTTP por la red), el navegador no dice cuántos monitores hay: elija **cuántas ventanas de visualización** quiere (1 a 8) y arrastre cada una a su monitor una vez. El Ipê de escritorio ya detecta todos los monitores (Preferencias ▸ Monitores).
- **Enlazar en una sola ventana (0.100.55)**: el mismo icono de cadena (**Enlazar los cuadros y las ventanas**) aparece también cuando el estudio se abre en esta ventana: los cuadros de la pantalla se desplazan juntos (los del mismo plano, por la posición en el paciente; un estudio previo avanza los mismos milímetros), con la misma ventana/nivel (misma modalidad, no en la mamografía) y el mismo zoom. En una sola ventana empieza desactivado; con ventanas separadas, activado.
- **Varias ventanas, una por monitor (0.100.18)**: en la lista, la casilla **Abrir en esta ventana / 1, 2 o 3 ventanas de visualización** elige dónde se abren los estudios. Con ventanas de visualización, la lista sigue en su ventana (monitor 1) y cada estudio se abre en las otras ventanas (monitores 2, 3…), para cualquier estudio, como en Ipê. Las ventanas quedan abiertas entre un estudio y otro: **Cerrar** en una de ellas cierra el estudio en todas, y esperan el siguiente; **Salir**, en la lista, cierra todas. La 2.ª ventana empieza en las series siguientes a las de la 1.ª; en la mamografía, la 2.ª ventana es la segunda pantalla del protocolo. **La primera vez**: (1) el navegador solo deja abrir una ventana por clic: permita los *pop-ups* de la dirección del servidor (el icono que aparece en la barra de direcciones); (2) arrastre cada ventana a su monitor: la posición y el tamaño quedan guardados. En Chrome y Edge, en HTTPS, el navegador pregunta si puede *administrar ventanas en todas las pantallas*: si lo acepta, cada ventana nueva ya se abre en un monitor, ocupándolo entero.
- **Móvil y tableta (0.100.18)**: en el móvil la lista se vuelve tarjetas (un toque abre el estudio) y el visor muestra una imagen a la vez, con la barra de herramientas desplazándose de lado; **Series** y **Panel de herramientas** (los dos primeros iconos) abren los paneles como cajones encima de la imagen. Gestos: **un dedo** hace la función elegida en la barra (al inicio, recorrer los cortes), **dos dedos** en pinza amplían y desplazan, **tres dedos** mueven; mantener el dedo abre el menú. En la tableta horizontal el diseño es el del ordenador, con paneles más estrechos. La sesión ahora sobrevive a la recarga de la página (el móvil recarga solo) y termina al cerrar la pestaña.
- **Cerrar y salir (0.100.5; 0.100.15)**: con un estudio abierto, **Cerrar** (esquina de arriba) cierra el estudio y vuelve a la lista; en la lista, **Salir** sale de Ipê Web. Cerrar o recargar la pestaña con un estudio abierto pide confirmación.
- **La búsqueda vuelve (0.100.15)**: al cerrar el estudio (Cerrar o ← Volver), la lista vuelve con la misma búsqueda y los mismos filtros (nombre, fechas, modalidad), con el estudio que estaba abierto marcado. Vale para esa pestaña del navegador; **Salir** olvida la búsqueda.
- **Lista de estudios (0.100.2)**: haga clic en el título de una columna (Fecha, Paciente, ID, Descripción, Modalidad, Imágenes) para ordenar; haga clic de nuevo para invertir (▲ ascendente, ▼ descendente). La elección queda recordada en el navegador.
- **Overlay (0.100.2)**: el icono **Overlay** activa y desactiva, de una vez, todo lo que está encima de la imagen: los hallazgos de **CAD/IA** (SR), las anotaciones de otro sistema (**GSPS**), los contornos de radioterapia (**RTSTRUCT**), los textos de las esquinas, las mediciones y las líneas de referencia, como el botón CAD/IA de Ipê. La flechita al lado elige elemento por elemento: cada tipo de objeto (lo que usted esconde queda escondido en los próximos estudios), cada objeto, los textos de las esquinas, las mediciones y las líneas de referencia. Los objetos se leen en el servidor con el mismo lector de Ipê; las mediciones que el propio Ipê graba no aparecen dos veces. La SEG elegida en el icono de segmentación aparece también en los cuadros de cortes.
- **CAD/IA en el overlay (0.100.14)**: en la flechita del Overlay, **CAD/IA (hallazgos, segmentaciones, niveles)** activa y desactiva solo la IA (los hallazgos, la SEG en los cortes y los nombres de los niveles), sin tocar los textos y las mediciones; la elección queda recordada. Los **niveles de la columna** (C1…S1, vértebras y discos) y los **niveles ganglionares** aparecen como en Ipê: en cualquier serie y plano, incluido el MPR (en un sagital, todos; en un axial, el nivel de ese corte).
- **Líneas de referencia en los cortes (0.100.2)**: con dos o más cuadros de cortes, el plano del cuadro **activo** aparece como línea en los otros (un axial en el scout, un sagital en el axial…). Con la herramienta **Líneas de referencia** en un botón del ratón, hacer clic (o arrastrar) en un cuadro de cortes lleva los otros cuadros al corte de ese punto: el localizador de Ipê. **Desde la 0.100.58**, el punto en que se hizo clic aparece como una **cruz amarilla** en todos los cuadros cuyo corte pasa por él (como el Shift del Ipê de escritorio), en el lugar exacto de la imagen; desplazarse lejos la esconde, y **Esc** la quita. Ir a un hallazgo de la IA marca el punto del mismo modo.

**Volumen: MPR, oblicuo y MIP (0.99.92).**

- **Cambiar el plano con un clic**: arriba de cada cuadro, **A**, **C** y **S** reconstruyen la serie en ese plano (axial, coronal, sagital), **MIP** pone el MIP girando y **Original** vuelve a los cortes como se adquirieron.
- **MPR** (barra): el cuadro activo se vuelve cuatro (axial, coronal, sagital y el MIP girando) con las **líneas de referencia**. El botón izquierdo pasa a ser "Líneas de referencia": arrastrar el centro lleva los otros planos al punto; arrastrar la punta de una línea gira la línea, y los otros cuadros se vuelven planos **oblicuos**.
- **Oblicuo** (barra): dos clics en el cuadro activo marcan una recta; el otro cuadro de volumen se vuelve el plano que contiene esa recta, perpendicular al plano donde se dibujó (como el oblicuo de Ipê).
- **Grosor**: 3, 5, 10 o 20 mm, en **MIP**, **MinIP** o **Media**, en el cuadro de volumen activo; la esquina dice el plano y el grosor.
- **MIP girando**: **Girar MIP** activa el giro alrededor del eje del paciente; la rueda del ratón sobre el MIP lo gira poco a poco. **Hacer clic en un punto del MIP** lleva los otros cuadros al punto más claro de esa línea de visión. En la TC el MIP se abre con ventana ancha; en el PET, invertido.
- Una serie que no da volumen (imagen única, cortes con orientaciones o tamaños distintos, varios cuadros en un archivo) queda en cortes, con el aviso del motivo. Los volúmenes mayores de 1,5 GB no se arman en el navegador.

**Mediciones (0.99.93).** En la barra: regla, ángulo, Cobb, ROI elíptica, rectangular y libre, píxel, flecha y calibración (en cualquier botón del ratón).

- **El número es el de Ipê**: la misma escala (calibración de esta imagen, después la de la serie, la región de la ecografía y el espaciado del archivo), la misma regla de la ROI (el píxel cuenta si el centro está dentro) y el mismo texto: media ± DE, mínimo y máximo, área.
- **Quedan en la base del servidor**, en el formato de Ipê: lo que se mide en el navegador aparece en Ipê (y lo que se midió en Ipê aparece en el navegador), con quién midió. Mover un extremo actualiza la medición; para borrar, haga clic derecho en la medición (menú ▸ Borrar esta medición) o use la pestaña **Mediciones**. Solo vale para los cuadros de cortes ("Original"): en el MPR las mediciones quedan solo en la pantalla, como en Ipê.
- **Ecografía**: la distancia usa la región calibrada del propio aparato; una regla que atraviesa dos regiones (del 2D al Doppler, por ejemplo) queda en píxeles. **Calibración**: trace una distancia conocida y escriba los milímetros; en la ecografía vale solo para esa imagen; en las otras modalidades, para la serie.

**PET/TC (0.99.94).**

- **PET/TC** (barra): la lectura de PET como en Ipê: la **fusión** (la TC en partes blandas con el PET encima), el **PET** en gris invertido y el **MIP del PET**. Los dos axiales avanzan juntos (corte, zoom y posición); hacer clic en el MIP lleva los cortes al punto más claro. El programa elige el PET del cuadro activo (o el mayor del estudio) y la mayor TC.
- **SUV por el cálculo de Ipê**: el PET llega al navegador ya en SUV (por el peso, con la dosis y los horarios del archivo); sin peso o sin datos del radiofármaco, el aviso dice qué falta y los valores quedan en Bq/ml. La ROI y el valor del píxel en el PET traen el SUVmáx y el SUVmed como en Ipê.
- **Color de la fusión** (las tablas de Ipê: Hot Iron, PET, arcoíris…), **opacidad** y **tope de la ventana de SUV**. Lo que queda por debajo del 8 % de la ventana no se pinta, como en Ipê.
- **Ventana del PET en el ratón (0.100.2)**: con la ventana/nivel en un botón, arrastre en el PET, en el MIP o en la fusión: **arriba y abajo cambia el tope**, **hacia los lados el piso**; la ventana vale para todos los cuadros del mismo PET y aparece en la esquina (*SUV 1–9*). En la fusión, **Shift + arrastre** ajusta la TC de abajo.
- **Disposición del PET/TC (0.100.2)**: en la pestaña **PET**, elija la cuadrícula (1×1 a 2×3) y lo que muestra cada cuadro (**TC + PET**, **TC**, **PET** o el **MIP del PET (3D)**) y el plano (axial, coronal, sagital). La disposición queda recordada para el próximo PET/TC; **Disposición estándar** vuelve a la fusión, PET y MIP.
- **SUV máximo cerca del cursor**: elija el icono (con el botón del ratón que va a usar) y haga clic cerca de la lesión en un cuadro de volumen del PET (la fusión, A, C o S): el programa encuentra el vóxel más caliente en una esfera de 3 cm y lleva los cortes hasta él; el valor aparece en la esquina.
- **Segmentación (SEG)**: las segmentaciones grabadas en el estudio (la carga tumoral, los órganos y las lesiones de la IA de Ipê) aparecen como máscaras coloreadas en los cuadros de volumen, con los colores de Ipê. Desde la 0.100.112, la más reciente de la IA ya aparece al abrir el estudio (como en el Ipê de escritorio); las otras quedan en el botón de segmentación. Las **líneas de las mediciones** de la cefalometría del cavum y de los índices del cráneo también aparecen, en cualquier plano que contenga la línea.

**Mamografía con una y dos pantallas (0.99.98).**

- El estudio de mamografía **se abre en el protocolo de Ipê** (el suyo, de Configuración ▸ Mamografía, o el de fábrica): la barra **Mamografía** encima de las imágenes dice el protocolo y la etapa (**4 proyecciones**, CC, MLO, actual × previa…). Las flechas cambian de etapa; hacer clic en el nombre de la etapa abre la lista. El protocolo también se cambia allí.
- **Las mismas reglas de Ipê**: la imagen de cada cuadro (la de presentación, la más reciente), el **estudio previo** del paciente en los cuadros "prev" (con la fecha en la esquina), las mamas **espalda con espalda** (refleja cuando la pared torácica vino del otro lado), la **mama encuadrada** (el aire queda fuera), la pared pegada al borde, el mismo zoom en las dos y los **pezones a la misma altura**.
- **Doble clic** amplía el cuadro; otro doble clic vuelve. **Cada cuadro es una pila de la proyección, como en Ipê (0.100.2)**: la rueda del ratón pasa por todas las imágenes 2D de esa mama y proyección y, enseguida, por los cortes de la tomosíntesis. **Tomosíntesis del cuadro** (barra) salta de la 2D al medio de la tomo y de vuelta. **Al desplazarse de la 2D a la tomo (0.100.4)** la imagen nueva queda en la misma escala en milímetros y con la pared torácica en el mismo lugar, incluso con el zoom a mano: la tomo tiene otro tamaño y otro espaciado. **Desde la 0.100.17** el encuadre de la apertura de la etapa vale para todas las imágenes de la pila, como si estuvieran apiladas: ir y volver con la rueda devuelve exactamente el zoom y la posición de antes (el tamaño del píxel viene del servidor, que lee el ImagerPixelSpacing de la 2D y los grupos funcionales de la tomo). El zoom a mano pasa a ser el nuevo encuadre de todas.
- **Lupa (0.100.4)**: **Lupa en el botón izquierdo** (barra): mantenga el botón y pase sobre la imagen: el círculo muestra los píxeles de la propia imagen aumentados (no los de la pantalla), con la ventana del cuadro; la rueda, con la lupa abierta, cambia el aumento (1,5× a 8×, recordado). El mismo botón devuelve la función de antes. La lupa también está en **Zoom y lupa**, para cualquier botón del ratón y cualquier estudio.
- **Zoom por cuadrante (0.100.77; cuatro áreas desde la 0.100.78)**: el botón **Zoom por cuadrante** de la barra de mamografía (o la tecla **Q**; **Shift+Q** vuelve) amplía todos los cuadros de la etapa juntos, cada uno en su lado, como en el Ipê de escritorio: posterior y superior → anterior y superior → posterior e inferior → anterior e inferior → la mama entera. La pared torácica sigue pegada a su borde y las dos mamas quedan reflejadas; al recorrer la tomosíntesis, el cuadrante se mantiene. Cambiar de etapa vuelve a la mama entera; con dos pantallas, la segunda acompaña.
- **Sincronía en la mamografía (0.100.78)**: en el modo mamografía de Ipê Web, el desplazamiento, el zoom y lo que viene de otra ventana no avanzan juntos de fábrica. El zoom por cuadrante sigue en los cuadros juntos de fábrica (botón **Cuadrante junto** para desactivar). El botón de enlazar cuadros, en la mamografía, activa y desactiva solo su sincronía (guardada aparte); la ventana de cada imagen nunca pasa a las otras.
- **Dos pantallas**: abre una segunda ventana del navegador con la otra mitad de la etapa (las CC en una pantalla, las MLO en la otra, por ejemplo, como Ipê las reparte). La segunda ventana entra sin pedir la contraseña (recibe la sesión de la primera), y las dos cambian de etapa juntas. En Chrome y Edge con el permiso de "administración de ventanas", ya se abre en el otro monitor; sin el permiso, arrástrela hasta allí. Cerrar la segunda vuelve a una pantalla. Si el navegador bloquea la ventana, permita ventanas de la dirección del servidor.
- **Salir del modo mamografía** (barra) vuelve al visor común. La lectura en el navegador depende del monitor: para informar, use el monitor calibrado (DICOM GSDF).

**Dinámica de la mama (0.99.98).**

- **Dinámica de la mama** (barra, en los estudios de RM): el servidor encuentra las fases como Ipê (las series de la dinámica, o una serie con todas las fases) y el navegador arma cuatro cuadros (la **fase inicial**, el **mapa cinético**, el **SER** y la **sustracción**) que avanzan juntos por los cortes. Cada cuadro puede mostrar otro mapa: MSI, PEI, realce inicial, tiempo hasta el pico, MIP y media temporales.
- **Los mapas se calculan en el navegador, corte a corte, con las cuentas de Ipê** (los mismos umbrales, el mismo ruido y la misma máscara de tejido; verificados píxel a píxel en las pruebas). Las fases pre, inicial y tardía se cambian en la barra.
- **Sobre la fase**: un mapa calculado o un mapa que Ipê **ya grabó como serie** ("SER (dinámica)", "Cinética (dinámica)"…) va encima de la fase inicial, con la tabla de colores de Ipê y la opacidad de la barra; lo que no tiene valor queda transparente.
- **Curvas tiempo-intensidad**: dibuje una ROI (elipse, rectángulo o polígono) o marque un **punto** (valor del píxel, media 3×3) en cualquier cuadro; abajo aparece la curva y la tabla con la **clase** (medio/rápido × persistente/meseta/lavado), el realce inicial, el SER, el pico, el TTP, el BAT, el lavado, el iAUC90 y el MRT: los números de Ipê.
- **Curva bajo el cursor (0.100.2)**: como en Ipê, pasar el ratón sobre la imagen muestra la curva del punto (3×3 píxeles), discontinua, junto con las guardadas; la casilla **Curva bajo el cursor** en la barra la desactiva.
- **El rótulo de cada cuadro (0.100.2)**: en los cuadros de fase, **◂ ▸** cambian de fase; hacer clic en el texto (o el botón derecho) abre el menú del cuadro: qué mostrar (cualquier fase o mapa), **Sustracción (fase − precontraste)** de cualquier fase, **Paisaje** (10 a 50 % de la anatomía de vuelta en la sustracción, como en Ipê) y el **color** (las tablas de Ipê, o gris). La barra elige también el **color del mapa encima de la fase**.
- **Corrección de movimiento (0.100.8)**: el selector de la corrección de movimiento en la barra: **Sin corrección**, **Traslación** o **Rígida** (con rotación), como en Ipê. El servidor hace la cuenta de Ipê (la traslación 3D de cada fase sobre la pre y, en la rígida, la rotación de la fase que giró) y el navegador la aplica al armar cada corte: los mapas, las curvas, las sustracciones y el cuadro de la fase que se movió salen corregidos. La pista del selector dice cuánto se movió (el mayor desplazamiento y la mayor rotación). Viene activada como usted la dejó en Ipê; cambiar la pre rehace la cuenta.
- **Series de la dinámica (0.100.58)**: el botón **Series…** en la barra lista las series de RM del estudio, con las que entraron marcadas; marque la pre y las poscontraste (o una sola serie, con las fases repetidas) y **Usar estas series**: la dinámica se abre de nuevo con ellas (la corrección de movimiento también). **Detectar solo** vuelve a la detección. Cuando el servidor no encuentra las fases, la misma lista se abre para que usted elija.
- **Diseño y qué va en cada cuadro (0.100.58)**: **Diseño** en la barra (1 × 1 a 3 × 3); los cuadros que ya estaban se quedan, y los nuevos vienen con la fase tardía, la sustracción de la tardía, MSI, PEI y TTP. En el rótulo de cada cuadro, **Mostrar** elige cualquier fase, la **Sustracción (fase − pre)**, un mapa o, en **Series del estudio**, cualquier serie del estudio: una serie que es fase de la dinámica se vuelve la fase; las otras (T2, difusión…) avanzan junto con la dinámica por la posición en el paciente, incluso con otro grosor. La serie puesta en el cuadro por la lista de series (sin pasar por el rótulo) se trata del mismo modo (0.100.60). Una serie de **otro plano** (sagital, coronal) no avanza con el desplazamiento: el clic de las **Líneas de referencia** la lleva al punto, y queda allí mientras usted recorre la dinámica (0.100.59). En la **sustracción** los **◂ ▸** cambian de fase en el propio cuadro, como en el Ipê de escritorio: el cuarto cuadro de fábrica es la sustracción de la fase inicial.
- Quedan solo en Ipê, por ahora: fases fuera de la cuenta y la línea de base por la media de las fases pre.

**Buscar en el PACS y descargar (0.100.37).** En la lista de estudios, el botón **Buscar en el PACS…** aparece cuando el servidor comparte algún nodo con usted (vea *Buscar en el PACS por el servidor*, arriba). Elija el nodo, rellene nombre, ID, accession o un período (una búsqueda sin filtro no se acepta, para no cargar el PACS) y haga clic en **Buscar en el PACS**. Cada estudio del resultado tiene **Descargar** (el servidor descarga a su base, en la suya) o **Abrir**, cuando ya está en el servidor. Abajo, **Descargas por el servidor** muestra el avance de cada una, con **Cancelar** y, al final, **Abrir el estudio**.

En la 0.100.80: **Hoy** y **Ayer** ponen la fecha y ya buscan; **N.º del estudio** busca por el número del estudio en el PACS (el *Study ID*; si su PACS llama número del estudio al número de accession, use **Accession**): la tabla muestra las dos columnas; y hacer clic en el título de una columna ordena por ella (▲ ascendente; clic de nuevo, ▼ descendente).

**Gestión DICOM en el navegador (0.100.63).** Para **administradores**, la lista de estudios gana el botón **Gestión DICOM…**: la misma rutina de la ventana del Ipê de escritorio (vea *Gestión DICOM: ¿los estudios de las modalidades están en el PACS?*), atendida por el servidor:

- **Quien habla con las modalidades y con el PACS es el servidor**, con su AE Title o con la identidad elegida en *Hablar como*. Los equipos y el PACS necesitan aceptar al servidor; el botón **Probar** de cada fila hace un C-ECHO y dice si el nodo responde.
- Aparecen **todos los nodos DIMSE activos del servidor**: aquí no hace falta marcar *Compartir con los clientes* en el nodo.
- Marque las modalidades, elija el PACS, el período, qué ignorar y **Comprobar**. La tabla trae la situación de cada estudio (completo, incompleto, ausente, con otro UID, sin recuento, error); hacer clic en la fila abre las series. **Solo los con problema** filtra; **Marcar los con problema** selecciona.
- **Enviar lo que falta** y **Enviar el estudio entero** envían al PACS de la comprobación; los dos **…a ▾** envían a otro destino de envío del servidor (lo que falta se cuenta allí). La **Cola de envío** muestra cada estudio; después del envío el estudio se comprueba de nuevo. **Exportar CSV** guarda lo que está en la pantalla.
- **Todo se ejecuta en el servidor**: puede cerrar la página; la comprobación y el envío continúan, y al volver (usted u otro administrador) la pantalla muestra el mismo estado. Una operación a la vez. Las comprobaciones y los envíos van al registro de acceso, con el usuario.
- Las elecciones quedan guardadas en el servidor (las mismas de la ventana de Gestión del programa en el ordenador del servidor).
- **Pestaña Automático (0.100.65)**: las reglas con horario, las mismas de la ventana del Ipê de escritorio (están en la base de datos). **Nueva regla…** / **Editar…** abren el editor: nombre, activada, modalidades (con *Hablar como*), destino (*Enviar como*, destino del C-MOVE), enviar solo lo que falta o el estudio entero, cómo enviar, período, solo una modalidad, series a ignorar, imagen por imagen; **Cuándo**: cada N minutos entre dos horarios, o todos los días a una hora, en los días de la semana marcados; y *reintentar* en X minutos, hasta N veces, si hay error o un nodo está fuera de servicio. En la lista: activar/desactivar en la casilla, **Duplicar**, **Eliminar** y **Ejecutar ahora**. Abajo, el **último informe** de la regla elegida (completados ahora, con error, modalidades fuera de servicio, mismo accession con otro Study UID) y el **historial**. Las reglas se ejecutan en el servidor mientras esté encendido; no deje la misma regla activada en dos programas al mismo tiempo (los estudios irían por duplicado).

**Impresiones y Panel en el navegador (0.100.68).** Para **administradores y técnicos**, la lista de estudios gana el botón **Impresiones…**: la pestaña *Impresiones* del Ipê de escritorio, atendida por el servidor (quien dibuja la hoja, lee la cabecera y habla con la impresora es él, con su IP y su AE):

- **La lista**: lo que llegó por la impresora DICOM, lo que se armó en el compositor y la película que vino dentro del estudio, con las mismas columnas y la misma *Situación* (En la lista, Enviado, Error, Esperando paciente, Detenido: aparato sin registro…). La caja de búsqueda filtra por paciente, ID, origen o rótulo; la lista al lado muestra solo los recibidos, los armados, los enviados o los **detenidos**. Haga clic en una fila para elegir; las casillas de la izquierda (o Ctrl + clic) eligen varias. La lista se actualiza sola cada 20 segundos.
- **La hoja**, al lado: la vista previa de cada hoja (◀ ▶), **Ampliar**, los datos del trabajo y el **historial de envíos** (cuándo, adónde, quién, cómo —a mano, por la regla o reimpresión— y el resultado).
- **Identificar paciente…**: el nombre y el ID, los estudios del mismo aparato y horario para elegir y el botón **Leer la cabecera de la hoja (OCR)**, que lee lo alto y el pie de la primera hoja y busca al paciente en la base: es una sugerencia; verifique antes de confirmar. Al confirmar, la película **sigue por la regla**, como en el Ipê de escritorio. El OCR es el del servidor: si no está instalado allí, el botón dice por qué.
- **Enviar a…**: todos los **destinos registrados en el servidor** (Configuración de impresión ▸ Destinos) —aquí no vale el *Compartir con los clientes*—, con la **plantilla de hoja**. **Reimprimir…** envía de nuevo al último destino que funcionó, después de mostrar el plan.
- **Juntar como páginas** (dos o más recibidos), **Abrir el estudio**, **Borrar** (pregunta antes; los estudios guardados en la base no se borran) y **Detenidos…**: los trabajos que esperan, por aparato, con el motivo y el botón **Liberar** (envía cada uno por su regla).
- **Pestaña Panel**: el *Panel de películas e impresiones*: período, modalidad, quién creó y origen; las tarjetas (películas, % impresas, detenidas, estudio → película, película → impresión, estudio → impresión, hojas impresas), las películas por mes, las tablas por modalidad y por quién creó, la lista de las películas y **Exportar CSV**.

Las **configuraciones** (servidores de impresión, destinos, reglas, plantillas de hoja y registro de los orígenes) siguen en el Ipê de escritorio del servidor. Cada envío, identificación y eliminación hecha por el navegador queda en el registro de acceso, con el usuario. Armar una película nueva sigue siendo en la pestaña *Película* dentro del estudio.

**Registros en el navegador (0.100.71).** Para **administradores**, la lista de estudios gana el botón **Registros…**: lo que antes solo se hacía en el Ipê de escritorio del servidor:

- **Usuarios**: **Nuevo usuario…**, **Editar**, **Activar/Desactivar**, **Restablecer la contraseña** y **Eliminar**; en **Perfiles y permisos…**, la tabla de lo que cada perfil puede hacer. La contraseña dada por el administrador es **provisional**: al entrar en Ipê Web, la persona es llevada a elegir la suya antes que cualquier otra cosa. Siempre queda un administrador activo, y nadie se elimina a sí mismo. Quien es desactivado, eliminado o tiene la contraseña restablecida pierde en el acto las sesiones abiertas (navegador e Ipê cliente). **Cambiar mi contraseña…** cambia la propia contraseña.
- **Nodos DICOM**: los nodos del servidor, DIMSE o DICOMweb, con los mismos campos de la ventana *Red* (usos, C-GET o C-MOVE, compartir con los clientes, autenticación). **Probar red** vale para lo que está en la pantalla, antes de grabar. La contraseña, el token y el secreto del cliente **no vuelven al navegador**: el campo vacío deja lo que estaba. Abajo, las **identidades** (AE Title de origen).
- **Impresoras DICOM**: las mismas de *Película ▸ Impresoras DICOM*, con **Probar conexión** y **Duplicar**. Cambiar el nombre de una impresora acompaña a los destinos de impresión que la usan; eliminar una que está en un destino pide confirmación.
- **Automatizaciones de IA**: las herramientas de *Preferencias ▸ CAD/IA*: de cada una, si se ejecuta sola cuando llega el estudio, en qué estudios y series, y a qué nodos va el resultado. En la lista, cada herramienta dice **automático en la llegada** o **solo a mano**. Nada cambia hasta **Guardar**.
- **Registro de acceso**: quién hizo qué, con filtro de período, usuario, acción y texto.

Cada cambio queda en el registro de acceso con el nombre de quien lo hizo. Quedan en el Ipê de escritorio: la instalación de los modelos de IA, el nodo DICOM del propio servidor (AE, puerto, quién puede conectarse), las reglas de automatización de red y las configuraciones de impresión.

**Enviar a un destino DICOM (0.100.9).** El botón **Enviar a un destino DICOM** (el avión de papel, junto a Informe) solo aparece para quien tiene el permiso de enviar a nodos DICOM.

- **Qué**: el estudio entero, las series marcadas (la del cuadro activo ya viene marcada) o solo la imagen del cuadro activo.
- **Para**: los nodos DICOM activos del servidor (los del servicio, los suyos y los compartidos con usted) y, si el nodo la tiene, la identidad (el AE) con que el servidor habla con él.
- **Junto: las mediciones (GSPS) y las imágenes clave (KO)**: lo que se midió en el estudio se vuelve un GSPS y las imágenes clave un KO, grabados en el estudio y enviados en el mismo envío.
- El envío entra en la **cola de envíos del servidor**, la misma de Ipê. **Envíos**, en el pie, muestra los que usted pidió, con el avance (enviadas/total), el resultado y **Cancelar** mientras avanza. Cada envío queda en el registro de acceso, con su nombre.

**CAD/IA en el navegador (pestaña IA, 0.100.12).** La pestaña **IA** del panel de la derecha (junto a Película) solo aparece para quien tiene el permiso **Pedir CAD/IA a mano** (de fábrica: administrador y médico; el administrador lo ajusta en **Usuarios ▸ Perfiles y permisos**). El botón **CAD/IA en este estudio** de la barra e **IA**, en el pie, abren la misma pestaña.

- **Tareas de este estudio**, arriba: las pedidas y las automáticas, con el estado (en la cola, armando el volumen, ejecutando, grabando, lista), la etapa, el tiempo y una barra mientras avanza. **Cancelar** aparece en las que usted pidió (quien configura cancela cualquiera).
- **Herramientas**, abajo: todas las herramientas de IA de Ipê (órganos abdominales, columna, nódulos, composición corporal, enfisema, autoPET, calcio…). Primero las que **sirven para este estudio**, con la **serie sugerida** (la misma que elegiría el automático); después las **otras**, con el motivo de no servir. En cualquiera se puede elegir la **serie del cuadro activo**.
- Elija la herramienta y la serie y haga clic en **Ejecutar** (o **Rehacer**, si el estudio ya tiene el resultado). La IA se ejecuta **en el servidor**, en la misma cola del automático de la llegada, una por vez; el paquete de segmentación tiene que estar instalado en el ordenador del servidor. La ventana *Tareas de IA* de Ipê muestra las mismas tareas.
- Cuando la tarea termina, el resultado aparece **en la misma sesión**, sin cerrar y abrir el estudio (0.100.15): las series nuevas entran en la tira, la SEG entra en el icono de segmentación (y ya aparece pintada, si ninguna estaba elegida), los nombres de la columna y de los ganglios entran en el overlay y las series ganan el sello IA.
- **Hallazgos para revisar (0.100.16)**: las IA que señalan hallazgos para que el médico revise (enfisema, nódulos, Genant, calcio coronario, aorta, carga tumoral en el PET, composición corporal) aparecen en la pestaña IA, como en el panel *Hallazgos de IA* de Ipê. Cada hallazgo muestra los números, el estado (sugerido, confirmado, corregido, descartado) y quién revisó. **Ir a** lleva los cuadros al hallazgo; **Confirmar**, **Corregir…** (cambie los números y grabe: el hallazgo queda *corregido* y el informe lleva sus números), **Descartar** y **Volver a sugerido**. **Enviar al informe** abre el informe y pone el texto de los hallazgos confirmados y corregidos donde está el cursor: nada va al informe sin revisión. Revisar necesita el permiso de escribir informes (el residente también revisa; la pestaña IA aparece para él solo con los hallazgos); cada revisión queda en el registro de acceso. Es la misma lista de Ipê: lo que se revisa en uno aparece en el otro.

**Película e impresión en el navegador (0.100.11).** La pestaña **Película** del panel de la derecha solo aparece para quien tiene el permiso de imprimir.

- **Armar**: ajuste la imagen en el cuadro con las herramientas de siempre (ventana, zoom, desplazar, girar, invertir) y haga clic en **+ Cuadro activo**, **+ Todos los cuadros** o **+ Serie del cuadro** (la serie entera, una imagen cada N, con el ajuste del cuadro). Solo entran imágenes originales (no MPR, MIP ni mapas).
- **La vista previa es lo que sale**: el servidor dibuja la hoja con el mismo código del compositor de Ipê (cabecera con paciente y estudio, regla, textos, mediciones). ◂ ▸ cambian de hoja.
- **Editar**: haga clic en una celda de la vista previa. **Editar en el cuadro activo** pone la imagen en el cuadro con su ajuste; cambie lo que quiera y haga clic en **Actualizar la celda**. **◂ ▸** cambian el orden y **Quitar** la saca.
- **Hoja**: nombre, cuadrícula (1×1 a 6×5), papel (A4, A3, Carta, películas de 8×10 a 14×17 pulg), horizontal, textos, cabecera, anonimizar, regla y fondo negro. La película queda guardada en el navegador hasta que usted la limpie.
- **Imprimir**, en **Salida**:
  - **Descargar PDF**;
  - **Imprimir en este ordenador**: el navegador abre su ventana de impresión, con las impresoras del ordenador de quien está usando;
  - las **impresoras del ordenador del servidor**, por el nombre;
  - las **impresoras DICOM** que el servidor comparte (marcadas *Compartir con los clientes*, vea *Imprimir en una impresora DICOM por el servidor*, arriba), por el nombre;
  - los **destinos de impresión de Ipê** (PDF o imágenes en una carpeta, impresora del sistema, impresora DICOM).
- **Solo esta hoja** imprime la hoja de la vista previa. Cada impresión cuenta en el panel de películas (la película queda guardada, con quién imprimió y adónde) y en el registro de acceso.
- El zoom y el desplazamiento van como en Ipê, en relación con "caber en la celda". Como la celda de la película tiene otra proporción que el cuadro de la pantalla, el encuadre puede cambiar un poco; la vista previa muestra cómo saldrá.

**Pantallas menores (0.100.53).** La barra de arriba muestra los botones que caben, en orden; los que no caben (en una pantalla de 1366 × 768, por ejemplo: Densidad, Calcificaciones, Cine, Invertir, Overlay, Informe, Enviar, CAD/IA, Modo lectura, Apariencia) van al botón **»**, al final de la barra, que abre un menú con ellos: mismo nombre, mismo icono, misma acción; lo que es panel (el informe, la densidad) se abre debajo del ». Al agrandar la ventana, vuelven a la barra.

**Ventana en la mamografía y en la tomosíntesis (0.100.52).** En el navegador, cada mamografía se abre con la ventana del propio archivo, y la ventana de una imagen no pasa a las otras (ni por las ventanas enlazadas). La ventana que usted pone con el ratón en un corte de la tomosíntesis vale para los otros cortes de la misma serie; al desplazarse a la 2D (otra serie de la misma pila), vuelve a la ventana del archivo de ella, y al volver a la tomo su ventana sigue allí. La ventana *Del archivo* (en el menú de ventanas) deshace su ventana de la serie.

**Densidad mamaria en el navegador (0.100.50).** En un estudio con mamografía, el botón **Densidad mamaria** (la gota, junto a Dinámica) abre la misma densidad del botón Densidad de Ipê: la **red de la NYU** en las cuatro proyecciones 2D del estudio, con la categoría y la probabilidad de cada una. Si el estudio aún no se midió, el servidor mide en el acto (la medición queda guardada en el estudio, y el Ipê de escritorio ve la misma). La categoría marcada de entrada es la de la red (o la que ya se confirmó); cámbiela si discrepa y haga clic en **Confirmar** o **Confirmar y enviar al informe**, que abre el informe al lado y pone la composición en el BI-RADS de mamografía (con otro tipo de BI-RADS, la frase va como texto). **Medir de nuevo** rehace la cuenta sin perder la confirmación. Ver y medir piden solo el permiso de abrir estudios; confirmar pide el de escribir informes. Las confirmaciones entran en *Densidades medidas* y en la concordancia, como las de Ipê.

**Informe en el navegador (0.99.98).**

- **Informe** (barra) abre el informe al lado de las imágenes, en el mismo registro de informe de Ipê: lo que se escribe en uno aparece en el otro.
- Sin informe, empieza por la **plantilla sugerida** para el estudio, con los **campos automáticos** rellenados como en Ipê (paciente, edad, fecha, comparación, mediciones, lesiones…). **Aplicar plantilla** cambia el texto por el de otra plantilla.
- **Insertar hallazgos de IA** pone en el cursor los hallazgos de la IA **confirmados o corregidos** (el sugerido no entra), con la frase de cada herramienta.
- **Esquemas en el informe** (0.100.74): la misma casilla del Ipê de escritorio: incluye en el informe los esquemas guía del estudio (leyenda en el texto, figuras en el PDF y, al firmar, en el SR). Los esquemas se dibujan con el botón **Esquema** del visor.
- **Guardar borrador** (y también guarda solo unos segundos después de dejar de escribir). **Firmar y liberar** pide la confirmación en la propia ventana; firmado, el informe ya no cambia: **Rectificar** crea un borrador nuevo con el texto, y el anterior queda guardado.
- **Quién está informando**: abrir el informe bloquea el estudio para usted. Si otro médico lo abre, ve el aviso y elige **Solo leer** o **Asumir el informe** (queda en el registro de acceso); el servidor rechaza grabar o firmar por quien no tiene el bloqueo. Cerrar el informe (o salir del estudio) suelta el bloqueo. Quien no tiene permiso de escribir informes solo lee.
- **BI-RADS® (0.100.4)**: el mismo formulario de la ventana del informe de Ipê: el tipo (mamografía, ecografía o resonancia), la composición (o el tejido fibroglandular y el realce de fondo en la RM), los **hallazgos** (**+ Hallazgo**: lado, tipo, descriptores de la lista, tamaño, ubicación, distancia al pezón, cambio y categoría), la categoría de cada mama y la recomendación. El texto del informe cambia solo, con las mismas frases de Ipê; en una plantilla sin los campos del BI-RADS, **Llevar al texto del informe** pone los bloques donde está el cursor. La categoría final es la más preocupante.
- **PDF y DICOM (0.100.4)**: **Descargar PDF** genera el PDF de Ipê (un borrador sale marcado), con la **cabecera** y la **línea de la firma** (quedan guardadas). Al firmar, como en Ipê, el PDF (DICOM encapsulado) y el informe en **SR** entran en el estudio: las dos casillas eligen.
- **Búsqueda activa (0.100.4)**: al firmar, el BI-RADS 0 o 3 (las categorías de Configuración ▸ Búsqueda activa) crea el pedido de llamar a la paciente, con el plazo; la rectificación cambia el pedido. Los pedidos abiertos de la paciente aparecen en lo alto del informe.

Por ahora es solo en la red de la clínica; desde fuera, entre por la VPN.

### HTTPS en la red interna (certificado de Ipê)

Sin certificado, el servidor central usa HTTP y la contraseña de cada inicio de sesión pasa abierta por la red. Un certificado de autoridad pública no sirve para una dirección como 192.168.1.10, así que el propio Ipê hace el papel de **autoridad certificadora (AC) interna**:

1. **En el servidor:** Configuración ▸ Red ▸ Servidor central ▸ **Generar certificado para la red interna…**. La primera vez crea la AC del servicio (vale 10 años) y, con ella, el certificado del servidor, válido para el nombre del ordenador y todas sus IP (825 días). Los campos Certificado y Clave se rellenan solos. La ventana muestra la **huella digital** de la AC: anótela. Dé OK y cierre y abra el programa: el servidor pasa a responder en `https://`.
2. **En cada cliente:** cambie la dirección a `https://…` y haga clic en **Confiar en el certificado de este servidor…**. Ipê descarga la AC del servidor y muestra la huella digital: verifique que es la misma del servidor y confirme. De ahí en adelante el cliente solo acepta ese servidor (otro ordenador de la red no puede hacerse pasar por él).
3. **Navegadores y otros visores DICOMweb:** **Guardar la AC (.crt)…** en el servidor y, en el Windows de cada cliente, doble clic en el archivo ▸ Instalar certificado ▸ Equipo local (o Usuario actual) ▸ Entidades de certificación raíz de confianza.

Con el certificado, el servidor solo habla HTTPS: quien escribe `http://` en el navegador es llevado solo al `https://` de la misma dirección (0.100.62), y los clientes de Ipê deben tener la dirección en `https://`. Desde la 0.100.62 la negociación del HTTPS se hace en cada conexión, con plazo; antes, una conexión que se abría y quedaba callada (el navegador adelanta conexiones; un móvil que duerme) podía detener el servidor hasta que se cerrara, e Ipê Web solo volvía reiniciando el programa.

Generar de nuevo (por ejemplo, cuando el servidor cambie de IP) cambia solo el certificado del servidor; la AC sigue siendo la misma y los clientes no necesitan hacer nada. La clave de la AC queda solo en el servidor, en la carpeta `certificados` de las configuraciones; guarde una copia de ella junto con la copia de seguridad.

### Perfiles por grupo y ordenador

**Configuración ▸ Usuarios ▸ Perfiles por grupo y ordenador…** (quien gestiona usuarios) arma perfiles de preferencias que el servidor envía a las estaciones: cada perfil dice para qué **ordenadores** vale (nombres, con comodín: `SALA-MAMO*`, `TC-0?`), para qué **usuarios** y qué **perfiles de acceso** (vacío = todos), y qué preferencias lleva: ratón, texto sobre la imagen, atajos, columnas de la base, monitores, dinámica de la mama, CAD/IA, idioma… La manera más fácil es dejar un ordenador como debe quedar y usar **Capturar de este ordenador…**; también se puede escribir clave y valor a mano (el valor en JSON).

Al entrar, valen los perfiles que coinciden, en el orden de la lista (el de abajo gana). El perfil manda sobre lo que viene del ordenador, y cada persona aún puede ajustar el suyo, salvo en las claves marcadas **Forzar**, que nadie cambia. En el modo cliente los perfiles viven en el servidor; en un ordenador con varias personas, en su base (allí solo usuarios y perfiles de acceso hacen diferencia). El nombre de este ordenador aparece en la propia ventana.

### Actualizaciones por el servidor central

**Configuración ▸ Red ▸ Actualizaciones por el servidor central…** (quien gestiona usuarios, en el servidor o en un cliente) publica los paquetes de una versión (**uno por sistema**, con el nombre original de GitHub): el instalador de Windows (`Ipe-x.y.z-windows-installer.exe`), el `.dmg` de macOS (`arm64` para chip Apple, `x86_64` para Intel) y el de Linux, en uno de dos canales: **prueba**, que va primero a los ordenadores y las personas de los perfiles marcados *Actualizaciones: Prueba*, y **estable**, para todos. **Promover prueba → estable** libera para todos lo que ya se probó; **Retirar** saca el paquete del canal. Publicar el paquete de un sistema no toca el de los otros; la ventana muestra, en cada canal, lo que hay para cada sistema.

Cada ordenador solo recibe el paquete de su sistema. Si el servidor no tiene su paquete (por ejemplo, un Mac cuando solo se publicaron el de Windows y el de Linux), no se descarga nada, y **Ayuda ▸ Buscar actualización en el servidor central…** lo dice y ofrece buscar la versión en GitHub.

Al entrar en el modo cliente, el programa verifica su canal; si hay una versión más nueva, pregunta si la descarga e instala. Con el "sí", descarga, verifica el SHA-256 y, si es el instalador de Windows (o el `.dmg` en un Mac con Ipê en la carpeta Aplicaciones), cierra el programa e instala sin más preguntas. Otro tipo de paquete (zip, tgz) se descarga y la carpeta se abre, para instalar a mano. Con el "no", no vuelve a preguntar por la misma versión; **Ayuda ▸ Buscar actualización en el servidor central…** pregunta en el acto. Cada publicación, promoción y retirada queda en el registro de acceso.

## Compresión sin pérdida

**Archivo ▸ Informe del acervo (formato y compresión)…** muestra lo que el acervo tiene y cuánto ahorraría la compresión sin pérdida. La compresión cambia el archivo solo después de verificar píxel a píxel, leyendo de vuelta del disco, que la imagen es idéntica.

# Gestión DICOM: ¿los estudios de las modalidades están en el PACS?

La comprobación que se hace a mano (abrir cada modalidad, ver los estudios del día y comprobar en el PACS estudio por estudio y serie por serie) hecha con un botón. Botón **Gestión** en la pantalla de la base de datos.

## Preparar una vez

1. Registre cada modalidad como nodo DIMSE (Configuración ▸ Red ▸ Nodos DICOM).
2. Para la modalidad que solo acepta un AE conocido (el de OsiriX, por ejemplo), registre ese AE como identidad (capítulo 9).
3. Abra **Gestión**. En el cuadro **Modalidades**, marque las que quiere comprobar y, en cada una, la identidad con que se habla con ella.
4. En el cuadro **PACS**: el nodo del PACS, la identidad (*Como:*), el **Destino del C-MOVE** (normalmente el AE del propio PACS) y **Cómo enviar**:

| Cómo enviar | Qué hace |
|---|---|
| Directo; si la modalidad lo rechaza, por el ordenador | lo predeterminado: la modalidad envía directo al PACS; si no conoce el PACS, el estudio pasa por este ordenador |
| Solo directo | solo la modalidad envía al PACS |
| Solo por el ordenador | descarga aquí y reenvía al PACS como la identidad elegida |

Todo queda recordado: la rutina del día siguiente es un clic.

## Probar el nodo

**Probar el nodo seleccionado** responde, sin enviar nada: si el C-ECHO pasa con la identidad, si la modalidad busca por fecha, si informa el conteo de imágenes por estudio y por serie, si responde a nivel de imagen y si conoce el PACS como destino (un C-MOVE de prueba de un estudio inexistente: el rechazo 0xA801 dice con certeza que no lo conoce; "aceptó" no prueba que lo conozca, y la pantalla lo dice).

## Comprobar

En el cuadro **Qué comprobar**: el **Período** (Hoy, Ayer, Ayer y hoy, Últimos 7 días o fechas), **Ignorar series** (las que la modalidad guarda y no envía a propósito, como *Patient Protocol*) y *Comprobar imagen por imagen* (más lento; dice qué imágenes faltan). Después, **Comprobar**.

| Situación | Qué significa |
|---|---|
| ✖ ausente en el PACS | el estudio no llegó |
| ◐ incompleto | faltan series, o hay series con imágenes de menos (dice cuáles y cuántas) |
| ≠ otro UID | en el PACS hay un estudio con el mismo accession y otro UID: rehecho, fusionado o corregido. Enviar crearía un duplicado, y el programa avisa |
| ? sin conteo | el nodo no informa el número de imágenes ni responde a nivel de imagen |
| ✔ completo | está todo allí. Un PACS con imágenes de más no es un defecto |

Lo peor va primero. **Mostrar: Solo los que tienen problema** filtra; las series aparecen al abrir el estudio. Si los tres primeros estudios dan el mismo error, la comprobación se detiene y dice el motivo una vez: un error que se repite en todos es del nodo, no del estudio (por ejemplo, el PACS que acepta la conexión y rechaza toda búsqueda: suele ser falta de permiso del AE; elija en *Como:* la identidad que funciona).

## Enviar lo que falta

- **Enviar lo que falta al PACS** envía solo las series que faltan y, en las incompletas, solo las imágenes que faltan.
- **Enviar el estudio entero** envía todo.
- Después del envío el estudio se **comprueba de nuevo**: "enviado" no es "está en el PACS". La columna Envío dice lo que ocurrió, y todo va al registro de acceso.
- **Exportar CSV…** graba la comprobación para abrir en Excel.

> **Quien acepta el destino es quien envía.** En el C-MOVE, el programa solo elige el nombre del destino; la modalidad decide por su tabla. Si no tiene el PACS registrado, el envío directo no existe; por eso lo predeterminado cae a "por el ordenador". Los nodos DICOMweb no entran en la Gestión: comprobar y enviar directo son C-FIND y C-MOVE.

# Verificación de protocolos de RM

Cada RM que llega se compara con el **protocolo de referencia** del mismo estudio, y del mismo aparato cuando lo haya: las series que faltan, las que sobran y los parámetros de cada una (plano, 2D/3D, secuencia, TR, TE, TI, ángulo, ETL, NEX, grosor, espacio entre cortes, matriz, FOV, píxel, banda, campo, valores de b de la difusión, pre o poscontraste). Solo se lee la cabecera; nada de píxeles. Quedan fuera el localizador, la calibración y lo derivado (mapa ADC, sustracción, MIP, reformateo).

**Red ▸ Verificación de protocolos de RM…** tiene dos pestañas.

**Protocolos de referencia.** Tres maneras de registrar:

- **Crear todos por el archivo**: un protocolo para cada estudio × aparato con estudios suficientes en la base de datos (de fábrica: los últimos 6 meses, al menos 5 estudios, leyendo los 20 más recientes). Es el **protocolo dominante**: la serie que aparece en ≥ 80 % de los estudios es obligatoria, en ≥ 50 % es opcional; cada número es la mediana, el resto es el valor más común. Es la manera de registrar todas las RM del servicio de una vez.
- **Crear por el archivo…**: lo mismo para un estudio y aparato elegidos.
- **Usar este estudio como referencia** (en la verificación de un estudio): el estudio bueno se vuelve el estándar, solo de ese aparato o de cualquiera.

**Editar…** muestra las series esperadas (obligatoria o no, y los valores; valor vacío = no se verifica ese parámetro) y las **tolerancias**: relativa (TR, TE, TI ±10 %; FOV y píxel ±10 %; banda ±15 %), absoluta (ángulo ±2°, grosor ±0,3 mm, espacio entre cortes ±0,5 mm), igual (matriz, plano, 2D/3D, secuencia, campo, valores de b, contraste) o solo mostrar (número de imágenes). Cada protocolo puede tener las suyas.

**La verificación.** Con la casilla *Verificar solas las RM que llegan* activada (de fábrica), toda RM recibida, descargada o importada se verifica en segundo plano. El resultado va a la columna **Protocolo (RM)** de la base de datos (✓ conforme, △ con avisos, ⚠ divergente) y el ⚠ aparece también junto al nombre del paciente. Clic derecho en el estudio ▸ **Herramientas ▸ Verificar el protocolo de RM…** abre su verificación: cada serie esperada, la encontrada, la situación y lo que cambió ("TR: 1941 (esperado 1700 ±10 %)"). Con varios estudios seleccionados, verifica todos de una vez.

| Situación | Cuenta como |
|---|---|
| Serie obligatoria faltante | divergencia |
| Plano, 2D/3D, campo, secuencia, valores de b o contraste distintos | divergencia |
| Número fuera de la tolerancia | aviso |
| Serie opcional faltante, serie de más | aviso |

La serie se encuentra por el nombre (la descripción, sin acento y sin mayúsculas); si el nombre cambió, por plano + secuencia + 2D/3D + contraste. Serie repetida: vale la última (la rehecha), y la verificación dice "repetida 1×". La referencia se elige sola: la del mismo estudio y aparato, si no la del mismo estudio para cualquier aparato; en la verificación se puede elegir otra.

**Estudios verificados.** El período, *Solo los fuera del estándar*, **Verificar el período** (verifica de nuevo todas las RM, por ejemplo después de editar un protocolo) y **Exportar CSV** (una fila por diferencia: serie, parámetro, valor, esperado y tolerancia). El doble clic abre la verificación del estudio.

# Informe

Botón **Informe** en la pantalla inicial, o clic derecho en el estudio → **Informe…**.

1. Elija una **Plantilla:** y haga clic en **Aplicar plantilla**. Son 19 de fábrica: mamografía (cribado, diagnóstica, tomosíntesis, CEM), ecografía de mamas, RM de mamas, cráneo, abdomen, pelvis y **próstata multiparamétrica (PI-RADS)**, TC de cráneo, tórax, angio-TC pulmonar, abdomen y oncológica, PET-FDG, PET-PSMA, radiografía de tórax por la **Clasificación de la OIT** (neumoconiosis: calidad, opacidades pequeñas y grandes con la profusión en la escala de 12 puntos, pleura y símbolos) e informe libre. Rellenan solas campos como paciente, edad, fecha, comparación y mediciones.
2. Escriba el texto. El menú **Insertar ▾** trae al informe lo que el programa ya midió: mediciones del estudio, seguimiento de lesiones, segmentaciones (volumen, SUV, TMTV/TLG, distancia al pezón), curvas tiempo-intensidad, comparación con previos, composición mamaria y hallazgos de CAD/IA.
3. En el panel **BI-RADS**, a la derecha, arme los hallazgos (mama, tipo, descriptores, tamaño, localización, distancia al pezón, evolución, categoría) y la conducta; **Llevar al texto del informe** escribe todo en el cuerpo.
4. Finalice: **Guardar borrador**, **Guardar PDF…** o **Firmar y liberar**.

Al pie se pueden incluir las imágenes clave en el PDF, guardar el PDF en el estudio (como serie DICOM) y guardar DICOM SR. Un informe firmado no cambia: se crea una rectificación, que se vuelve un informe nuevo y guarda el anterior. Firmar exige el permiso *Firmar (liberar) informes*.

Las plantillas se editan en **Plantillas…** (nombre, modalidades, palabras clave, BI-RADS y el texto con campos automáticos entre llaves). Hay *Restaurar las de fábrica*.

## Esquemas guía

Para marcar **dónde** está cada hallazgo en un dibujo: útil sobre todo en la ecografía dermatológica, el tiroides, la mama y la RM de próstata. El esquema es **del estudio**, separado del informe: en el visor, el botón **Esquema** abre la ventana *Esquemas del estudio*, con los esquemas ya hechos y **Nuevo esquema…**, **Dibujar…**, **Borrar** y **Guardar en el estudio**. En Ipê Web el botón **Esquema** está en la barra del visor, junto a Informe, y hace lo mismo.

| Modelo | Para qué |
|---|---|
| Cara (frente, perfil derecho e izquierdo) y cuerpo (frente y espalda) | lesiones de piel |
| Tiroides y niveles cervicales | nódulos y ganglios |
| Mamas | reloj, cuadrantes y prolongación axilar |
| Próstata — mapa de sectores | los 41 sectores (base, tercio medio, ápice, vesículas y esfínter) |

En el editor, las herramientas están arriba: **Punto** (un clic), **Elipse** y **Flecha** (arrastrando), **Trazo libre**, **Texto**, **Mover**, **Borrar** y **Deshacer** (Ctrl+Z), con seis colores. Con **Numerar** activado, cada punto, elipse o flecha nuevos recibe el siguiente número y una línea en la lista de la derecha, donde se escribe la descripción del hallazgo.

- **Vincular a una imagen**: en cada marca, **Vincular a la imagen abierta** ata la marca a la imagen del cuadro activo del visor. Se vuelve imagen clave y la leyenda pasa a decir "(serie 3, imagen 12)".
- **Próstata**: con la herramienta **Sector**, elija la categoría (PI-RADS 1 a 5) y haga clic en el sector para pintarlo; otro clic lo limpia. La leyenda sale por categoría, de la más alta a la más baja.
- **Guardar en el estudio** graba en el acto, sin ningún informe: las figuras van a la serie "Esquemas del informe" y las marcas a un SR solo de los esquemas ("Esquemas del informe (SR)"), como la tabla de la segmentación y el resumen de la densidad. **Guardar de nuevo reemplaza lo que había** (no duplica).

**En el informe** el esquema solo se incluye, como las imágenes clave: la casilla **Esquemas en el informe** (en la ventana del informe de Ipê y en el panel del informe de Ipê Web) hace tres cosas:

- pone en el texto, donde está el cursor, la leyenda: una línea por marca numerada ("1. nódulo hipoecoico de 4 mm") y los sectores pintados. El campo `{esquemas}` hace lo mismo en las plantillas de informe;
- lleva las figuras, con la leyenda al lado, al **PDF**;
- al **firmar**, graba las figuras en el estudio y cita los esquemas en el **DICOM SR** del informe: la figura, cada marca con la posición y la imagen vinculada a ella (con esquema, el SR es un *Enhanced SR*). Lo que se había grabado antes por *Guardar en el estudio* se reemplaza.

Sin la casilla marcada, el informe no lleva ningún esquema. Un informe firmado no cambia la elección; para cambiarla, **Rectificar**.

**Plantillas** (0.100.74: **Configuración ▸ Esquemas ▸ Plantillas de esquema**; en Ipê Web, **Registros ▸ Plantillas de esquema**). Quien tiene el permiso de configurar registra y cambia las plantillas, que valen para todos los usuarios:

- **Nueva plantilla a partir de una imagen…**: un dibujo suyo (PNG o JPG) se vuelve una plantilla;
- **Nueva plantilla en blanco…**: una hoja vacía para dibujar la plantilla desde cero;
- **Editar la plantilla…**: abre la plantilla con las mismas herramientas de dibujo. Lo que se dibuja allí pasa a formar parte de la plantilla, en todos los estudios; también se cambia el nombre y el grupo. **Guardar como copia** crea una plantilla nueva a partir de ella (la copia de la próstata lleva los sectores);
- en una plantilla de Ipê, el dibujo original queda guardado: **Restaurar el original** deshace los cambios, y **Ocultar de la lista de plantillas** quita la plantilla de la elección sin borrar nada. Una plantilla propia se elimina en **Eliminar la plantilla**.

## PI-RADS (RM de próstata)

En la RM de próstata, el botón **PI-RADS** del visor (y de Ipê Web) abre el formulario del **PI-RADS® v2.1**. Es del estudio, como el esquema; el informe solo lee lo que hay en él.

- **Glándula y PSA**: el **PSA** y la fecha; los tres diámetros (AP, transverso y craneocaudal) —**Tomar de las reglas** usa las tres últimas reglas dibujadas en el estudio, en ese orden—, o el **Volumen automático (IA)**, que segmenta la próstata en el T2 axial (TotalSegmentator) y trae el volumen aquí. El volumen es el de la segmentación cuando la hay (la elección "Elipsoide" vale por encima de ella) y da la **densidad del PSA** (PSA ÷ volumen). Marque también **Biparamétrica (sin DCE)**, **Hemorragia posbiopsia** y la calidad.
- **Lesiones**: **Nueva lesión**, o un clic en el **mapa de sectores** a la derecha (sin lesión elegida, el clic crea una en ese sector; con lesión, pone o quita el sector de ella). Para cada lesión: zona, sectores, mayor diámetro, **T2**, **difusión**, **DCE**, **ADC** (**De la ROI del cuadro** toma la media de la ROI del cuadro activo: dibuje la ROI en el mapa ADC), extensión extraprostática, descripción y **Vincular a la imagen del cuadro** (se vuelve imagen clave). **Curva DCE…** abre la dinámica; las curvas medidas entran en el informe por el campo `{curva}`.
- **Categoría**: sale sola por la regla del PI-RADS v2.1: en la zona periférica manda la difusión (difusión 3 con DCE positivo pasa a 4); en la zona de transición manda el T2 (T2 2 con difusión ≥ 4 pasa a 3; T2 3 con difusión 5 pasa a 4); en la biparamétrica el DCE no cuenta. El programa avisa cuando el tamaño y la puntuación no combinan (5 pide ≥ 15 mm o extensión extraprostática). El estroma anterior y la zona central no tienen tabla propia en el PI-RADS: verifique. La **categoría manual** de cada lesión y la **general** valen por encima de la regla.
- **Salidas**: el mapa de sectores pintado entra en la lista de esquemas del estudio (esquema "PI-RADS — mapa de sectores"); **Guardar en el estudio (SR y mapa)** graba el SR del PI-RADS (serie "PI-RADS (SR)": volumen, PSA, densidad, cada lesión con las puntuaciones, el ADC, la categoría y la imagen) y la figura; **Enviar al informe** escribe el texto en el informe abierto. La plantilla de informe **RM de próstata multiparamétrica (PI-RADS)** usa los campos `{pirads_achados}` (volumen, PSA y lesiones) y `{pirads}` (la impresión); también existe `{prostata_volume}`.

**Modelos de investigación (opcionales, instalados aparte).** Dos IA de **investigación y enseñanza — no clínico, no comercial** que no vienen con Ipê: los pesos los descarga usted, de la fuente, solo después de leer y aceptar la licencia (**Configuración ▸ CAD/IA ▸ Modelos de investigación — próstata**, o la primera vez que intente usarlos):

- **Zonas de la próstata** (MONAI *prostate_mri_anatomy*, entrenado en Prostate158): actívelo en **Configuración ▸ CAD/IA ▸ Próstata: volumen (IA) ▸ Separar también las zonas**; el volumen automático pasa a traer la zona de transición y la periférica (serie "Zonas de la próstata (INVESTIGACIÓN - no diagnóstico)").
- **Lesiones sugeridas** (nnU-Net base del desafío **PI-CAI**, pesos CC BY-NC-SA 4.0): **Sugerencias del modelo de investigación…** en el formulario, o el botón **PI-CAI**. Usa el T2 axial, el mapa ADC y la difusión de mayor b del estudio; cada foco sugerido entra en el PI-RADS como lesión **por verificar**, con la probabilidad del modelo. Solo se ejecuta a mano.

Todo lo que viene de estos modelos sale marcado **"modelo de investigación — no usar para diagnóstico"**: la franja roja en el formulario, la descripción de la SEG, el SR y el texto del informe. La lesión sugerida sigue marcada como de investigación incluso después de **Verificada por el médico**.

## IA en el texto del informe

El botón **IA ▾**, en la ventana del informe, junto a **Insertar ▾**:

- **Revisar el informe (sin red)**: siempre disponible: señala un campo sin rellenar ("___", "{campo}"), una medición sin unidad ("midiendo 12") o demasiado grande (más de 400 mm o 60 cm), una palabra repetida, "derecha izquierda", un órgano que no combina con el sexo del paciente (útero en el masculino, próstata en el femenino), una categoría BI-RADS del texto distinta de la del formulario, BI-RADS 3 con conducta de rutina, BI-RADS 4 y 5 sin histopatológico, una conclusión que cita un lado que el cuerpo del informe no cita y una impresión vacía. La misma revisión se ejecuta **antes de firmar**: si encuentra algo, muestra la lista y pregunta si firma de todos modos (se desactiva en Configuración).
- **Refinar el texto (IA)…**, **Generar la impresión (IA)…** y **Señalar errores (IA)…**: con un modelo de lenguaje configurado. La respuesta se abre en una ventana editable; nada entra en el informe sin **Reemplazar el texto del informe por este** o **Insertar en el informe (en el cursor)**, y Ctrl+Z lo deshace.

**Configuración ▸ Informes ▸ IA en el texto del informe…** elige el proveedor: **Ollama** (el modelo se ejecuta en este ordenador o en un servidor de la red; el texto no sale del servicio), un servidor **compatible con OpenAI** (LM Studio, vLLM, llama.cpp) o la **API de Anthropic** (con la clave del servicio; el texto sale). Antes de salir del programa, el texto pierde el **nombre, el ID, el accession y la fecha de nacimiento** del paciente, que vuelven en la respuesta; para una dirección fuera de este ordenador, el programa pregunta una vez. **Probar** verifica la conexión. La clave de la API queda guardada **cifrada**. El modelo solo sugiere: quien firma es el médico.

## Documentos adjuntos al estudio (PDF e imágenes)

Pedido médico, consentimiento informado, informe previo de otro servicio, foto de la lesión: el PDF o la imagen entra **dentro del estudio**, convertido a DICOM, y va junto cuando el estudio se exporta o se envía al PACS. Tres caminos:

- **arrastrar sobre el visor**: va al estudio abierto (el del cuadro activo);
- **arrastrar en la base de datos con un estudio seleccionado**: el programa pregunta antes ("¿Adjuntar 2 archivos al estudio de …?"), para no caer en el paciente equivocado;
- **clic derecho en el estudio ▸ Documentos ▸ Adjuntar documento (PDF o imagen)…**, o, en el visor, el menú de series del cuadro ▸ **Adjuntar documento…**.

El **PDF** se vuelve un documento PDF encapsulado en DICOM (modalidad DOC), en la serie **Documentos adjuntos**, con el nombre del archivo como título. Cada **imagen** (JPG, PNG, TIFF —cada página se vuelve una—, BMP, GIF, WEBP) se vuelve una imagen DICOM (captura secundaria, modalidad OT) en la serie **Imágenes adjuntas**, y aparece en el visor como cualquier otra serie. Los datos del paciente y del estudio son los del propio estudio. Word, Excel y otros formatos quedan fuera, con aviso: guarde como PDF antes.

El adjunto sigue las **reglas de enrutamiento** del estudio (Configuración ▸ Red ▸ Automatización): si el estudio fuera a un nodo, el adjunto va también. Quién adjuntó queda en el registro de acceso.

Para leer los PDF del estudio (adjuntos, informes guardados en PDF o PDF que vinieron de otro sistema): clic derecho en el estudio ▸ **Documentos ▸ Documentos del estudio…**, doble clic en la serie de documentos en el panel de series, o el menú de series del cuadro ▸ **Documentos del estudio…**. El PDF se abre dentro del programa; hay también **Abrir en el programa del sistema** y **Guardar el PDF…**.

**En Ipê Web** (0.100.55): arrastre los archivos del ordenador sobre el estudio abierto (aparece "Suelte para adjuntar al estudio") o use **Adjuntar PDF o imagen…** debajo de las series. El navegador pregunta antes, envía al servidor, y el servidor hace lo mismo que Ipê de escritorio (convierte, guarda en el estudio y sigue las reglas de enrutamiento). Las imágenes entran en la lista de series al instante; los PDF quedan en **Documentos** (debajo de las series) y se abren en una pestaña nueva. Pide el permiso de importar; hasta 40 archivos u 80 MB de una vez.

## Informe en curso (servidor central)

En el modo cliente, quien abre el informe de un estudio pasa a ser **quien está informando**, hasta cerrar la ventana del informe. Otro médico que abra el informe del mismo estudio recibe un aviso ("La Dra. Ana está informando este estudio desde las 10:05") y elige **Solo leer** (la ventana se abre sin poder grabar) o **Asumir el informe** (queda en el registro de acceso, y el primero ya no graba). Quien solo abre las imágenes ve el aviso en la barra de estado. El servidor rechaza grabar o firmar el informe de quien no lo tiene. Si el ordenador de quien informaba se cuelga, el bloqueo cae solo en 10 minutos.

## Fin de la lectura: enviar al PACS al firmar

**Configuración ▸ Informes ▸ Fin de la lectura (enviar al PACS al firmar)…** activa el envío y elige el **destino** (uno de los nodos de red activos). Al **firmar** el informe, el programa graba las imágenes clave como un **KO** y las mediciones como un **GSPS** en el estudio, y envía al destino, por la cola de envíos (la misma del envío a mano):

- **el informe** de esta firma (el PDF y el SR, si usted los guarda en el estudio);
- **las imágenes clave (KO)** y **las mediciones y anotaciones (GSPS)**;
- **las series de Ipê** en el estudio (las SEG de los análisis, mapas, capturas).

Cada elemento se activa y desactiva. No van: el informe de antes, las series de otro aparato, las **ocultas** y las copias que quedan solo en este ordenador (la copia sin implante, las tablas de la segmentación). La barra de estado del informe dice "enviando al PACS: …" y el envío queda en el registro de acceso. Vale también para el informe firmado en el **navegador**: el servidor central graba y envía solo.

## Cerrar el estudio solo

**Configuración ▸ Visor ▸ Cerrar el estudio solo…**: cerrar el estudio (y la ventana del informe) al **firmar el informe**, y/o cerrar los estudios abiertos después de **N minutos sin tocar** el ratón y el teclado (el borrador del informe se guarda antes). Evita que se mire —o se informe— al paciente siguiente con el anterior aún en la pantalla.

## Búsqueda activa (BI-RADS 0 y 3)

Al **firmar** un informe con el formulario BI-RADS, la categoría final decide si la paciente entra en la **búsqueda activa**: de fábrica, **BI-RADS 0** con plazo de **30 días** y **BI-RADS 3** con **180 días**, contados desde la firma. La rectificación reemplaza el pedido abierto del estudio (o lo cierra, si la categoría nueva no pide retorno). En **Configuración ▸ Informes ▸ Búsqueda activa (plazos por BI-RADS)…** se pueden cambiar los días y activar también 4A, 4B, 4C y 5 ("esperando el histopatológico").

**Informes ▸ Búsqueda activa…** muestra los pedidos (abiertos, atrasados (en rojo), que regresaron o cerrados) con el plazo y la situación ("faltan 12 días", "atrasada 3 días"). Los botones **Contactada**, **Agendada**, **Regresó**, **Cerrar…** (con el motivo) y **Nota…** van al historial, con quién y cuándo; **Abrir el estudio** abre el estudio de origen (o el de retorno). La paciente **regresa sola** cuando llega a la base de datos un estudio de mama suyo con fecha igual o posterior (mamografía, o ecografía/RM con "mama" en la descripción); el botón **Comprobar retornos** rehace esa comprobación. **Exportar CSV…** lleva la lista a la hoja de cálculo de la recepción. En el servidor central, la lista es una sola para todas las estaciones.

## Lista de trabajo: prioridad, subespecialidad y plazo (SLA)

Cada estudio de la base de datos tiene una **prioridad** (rutina, urgente, emergencia), una **subespecialidad** (mama, neuro, cabeza y cuello, tórax, musculoesquelético, abdomen, medicina nuclear o general) y un **plazo del informe**: la llegada a la base de datos + las horas de la prioridad (de fábrica, rutina 48 h, urgente 4 h, emergencia 1 h; la rutina puede tener horas propias por subespecialidad, como "Mama=72"). Las columnas **Prioridad**, **Subespecialidad**, **Plazo del informe** y **SLA** muestran esto; el SLA dice "faltan 5 h", "vence en 40 min" (naranja, a menos de 2 h), "atrasado 3 h" (rojo) y, después de firmado, "en plazo" o "fuera de plazo (+5 h)". Urgente aparece en naranja y emergencia en rojo.

La prioridad sale de las palabras de la descripción del estudio (de fábrica "URGENTE", "PS", "PRONTO SOCORRO", "UTI" → urgente; "EMERGÊNCIA", "CÓDIGO AVC", "TRAUMA" → emergencia) y la subespecialidad de la primera regla que coincida (modalidades + palabras de la descripción). Todo se ajusta en **Configuración ▸ Informes ▸ Prioridad, subespecialidad y plazos (SLA)…**; en cada estudio, **clic derecho ▸ Organizar ▸ Prioridad** o **▸ Subespecialidad** cambia a mano ("De la regla" vuelve a lo automático).

El botón **Trabajo ▾**, en la base de datos, filtra y ordena por el plazo: **sin informe** (lo que vence primero arriba), **atrasados**, **vencen en menos de 2 h**, **urgencias y emergencias** y **mis subespecialidades** (elija las suyas una vez en *Elegir mis subespecialidades…*). En el servidor central las reglas valen para todas las estaciones.

**Estado del estudio** (0.99.63): la columna **Estado** (Columnas ▾) muestra *No leído* (nunca abierto y sin informe), *En lectura* (abierto, o con borrador), *Urgente* (sin informe firmado y con prioridad urgente o emergencia) y *Revisado* (informe firmado), en colores, y ordena en ese orden. El clic derecho ▸ **Organizar ▸ Estado del estudio** cambia a mano (el revisado sin informe (segunda lectura, reunión), el que volvió a lectura), y la columna marca el cambiado con ✎; *Automático* vuelve al cálculo. En **Trabajo ▾**: *No leídos*, *En lectura* y *Aún no revisados*. En el visor, la acción *Estudio: marcar como revisado* (elija una tecla en Atajos ▸ Estudios) marca el estudio del cuadro activo; de nuevo, vuelve a lo automático.

## Productividad

**Informes ▸ Productividad…** cuenta los informes **firmados** en el período (hoy, 7 o 30 días, este mes, mes pasado, este año o fechas elegidas) y agrupa por **médico**, **modalidad**, **subespecialidad**, **prioridad** o **día**: cuántos informes, cuántas rectificaciones, la **mediana** y el **p90** del tiempo desde la llegada del estudio a la base de datos hasta la firma (en horas) y cuántos salieron **en plazo** (por las reglas de plazo del elemento anterior). Las barras muestran en plazo en verde y fuera de plazo en naranja. Arriba, lo que está **pendiente ahora**: estudios sin informe firmado, atrasados y venciendo en menos de 2 h. **Exportar CSV…** lleva la tabla a la hoja de cálculo. Quien no gestiona usuarios ve solo sus propios informes. Un informe cuenta como un informe (sin pesos por modalidad).

## Filtros de mamografía

El botón **Mama ▾**, junto a **Columnas ▾** en la base de datos, aplica filtros listos y muestra las columnas que usan: **BI-RADS 0**, **3**, **4 y 5**, **6**; **mamas densas** (ACR c y d) o no densas; **mamografías sin informe firmado**; **cribado** o **diagnóstica** (por la descripción del estudio); **búsqueda activa abierta** o **que regresó**. Las columnas **BI-RADS** y **Densidad** vienen del informe BI-RADS firmado más reciente del estudio; **Búsqueda activa**, del pedido del estudio. Como toda columna, aceptan también el filtro escrito y el filtro por valores.

# Película e impresión

## El compositor de película

Botón **Imprimir** de la pantalla inicial, **Archivo ▸ Película / impresión** (Ctrl+P), o F1/F2 y el botón **Película** dentro del estudio. Con un estudio abierto, la película aparece como panel junto a los cuadros; el botón de expandir, en la esquina de la barra de la película (o doble clic en la película), alterna entre la película grande y los cuadros.

### Montar

- **Hoja**: cuadrícula (filas × columnas), papel, vertical u horizontal, y *en todas las hojas* para aplicar al conjunto. Las hojas están a la izquierda, con Nueva, Duplicar, Subir, Bajar, Eliminar y Compactar.
- **Rellenar**: F1 (la imagen del cuadro) y F2 (la serie del cuadro, entera o un intervalo) en el visor; arrastrar miniaturas de la tira a una celda; el menú del botón Película trae todos los cuadros y las imágenes clave.
- **Textos**: el nivel de texto en las celdas, cabecera, anonimizar, regla y fondo negro.

### En la celda

| Gesto | Qué hace |
|---|---|
| Izquierdo arrastrando | la función elegida en **Ratón (botón izquierdo)**: Ventana, Mover (la imagen dentro de su cuadro) o Zoom |
| Asa ⠿ arrastrada (esquina de la celda) | **intercambia la imagen** con la de la celda donde la suelte, con cualquier función del ratón; vale entre hojas |
| Derecho arrastrando / central arrastrando | zoom / mover |
| Rueda | pasa el corte de la serie |
| Botón derecho | menú: Ratón (botón izquierdo), copiar, cortar, pegar, girar, reflejar, invertir, ventana, color, filtro, restaurar, abrir en el visor, quitar, insertar o quitar hueco |
| Ctrl/Shift + clic | selecciona varias |
| Ctrl+C / Ctrl+X / Ctrl+V / Ctrl+A / Supr | copiar, cortar, pegar, seleccionar la hoja, borrar |
| Doble clic | expandir la película (o editar el texto, si es encima de un texto) |

La función del botón izquierdo también está en el botón **Ratón: …** de la segunda barra, y queda recordada.

### Anotaciones de la película

**➚ Flecha**, **T Texto** y **✎ Lápiz** anotan solo en la película, nunca en la imagen del estudio.

- Después de una anotación, el ratón **vuelve solo** a la función que tenía (ventana, mover o zoom).
- Al pasar el ratón por encima de una anotación el cursor cambia: arrastrar **mueve** la anotación; arrastrar la **punta o la cola de la flecha** cambia su tamaño; **doble clic en un texto** edita el texto (texto vacío borra la anotación).
- **Ctrl+Z** deshace la última anotación.
- El botón **Anotaciones** activa y desactiva todas las anotaciones de la película: en la pantalla, en la impresión, en el PDF y en el JPG/PNG. Elegir una herramienta de anotación las reactiva.

### Guardar, imprimir y exportar

| Botón | Qué hace |
|---|---|
| Guardar / Guardar como… | guarda la película en la base de datos (Abrir… y Archivo ▸ Películas guardadas… la reabren) |
| también en el estudio | casilla junto a Guardar: graba también la película **dentro del estudio**, en el formato de la estación AW de GE (véase abajo) |
| Imprimir… | impresora de Windows |
| PDF… | una página por hoja |
| JPG/PNG… | una imagen por hoja |
| DICOM Print… | impresora DICOM (exige el permiso de impresión) |

Una película impresa sin haber sido guardada se guarda en el momento de imprimir, con el nombre que tiene; si no, la impresión no aparecería en el panel de películas.

### Película en el estudio (formato AW)

Con **también en el estudio** marcada, Guardar graba en el estudio de la primera imagen de la película tres cosas, como las graba la AW:

- un **SR** "AW electronic film" con el plano de la película (páginas, huecos y posiciones);
- las **imágenes sueltas** de cada celda, con el texto y las anotaciones, en la modalidad del estudio;
- las **hojas listas** "AW electronic pages", como saldrían impresas.

La película recuerda lo que grabó. Si nada cambió desde la última grabación, Guardar no graba de nuevo; si cambió, pregunta: **Reemplazar la anterior**, **Guardar las dos** o **Ahora no**. Las series grabadas aparecen en la pestaña Impresiones como película de la estación, como las de la propia AW.

## Impresiones recibidas

Botón **Impresiones** (Ctrl+Shift+P): la lista de lo que las modalidades enviaron aquí y de lo que se montó aquí, con vista previa. Arriba están la búsqueda, el **Panel…** y la **Configuración…**; abajo, las acciones sobre el trabajo elegido: abrir, **Enviar a…**, **Reimprimir…**, **Historial…**, identificar al paciente, ver los **Detenidos…** y borrar.

### Historial de envíos y reimpresión

Cada envío queda guardado: cuándo, adónde, quién estaba en el programa, si fue **a mano**, **por la regla**, **reimpresión** o **en el compositor**, con qué plantilla de hoja, y si salió bien. Los tres últimos aparecen debajo de los detalles del trabajo; **Historial…** muestra todos. De aquí saca el Panel el "Impreso por" de las impresiones DICOM (el envío por la regla aparece como "regla (automático)"). El historial empieza en la 0.84: lo que se envió antes de eso no tiene historial.

**Reimprimir…**: elija uno o varios trabajos (Ctrl o Shift + clic) y cada uno vuelve al **último destino** al que salió, con la misma plantilla de hoja. Antes de enviar, la ventana dice cuántos van a cada destino; los que nunca se enviaron quedan fuera (para esos, use **Enviar a…**).

### Modalidad del trabajo

La impresión DICOM no dice la modalidad. El programa la descubre así: con el paciente identificado (OCR al llegar o **Identificar paciente**), es la modalidad del **estudio del paciente** hecho hasta la hora de llegada (el mismo día o el anterior); sin paciente, es la modalidad escrita en el **registro del origen** (Configuración ▸ Impresión ▸ Servidores, destinos, reglas y plantillas ▸ Orígenes ▸ Modalidad). La columna **Modalidad** de la lista muestra el resultado. Vale para las **reglas por modalidad** y para la **limpieza**.

### Columnas y filtros de la lista

La lista de impresiones funciona como la tabla de la base de datos:

- **filtrar**: la casilla bajo cada título filtra esa columna, con la misma escritura de la base de datos (`ana|maria`, `!Enviado`, `>=2` en las Hojas, `hoje` o `7d` en la Llegada); el botón derecho en el título abre **Filtrar valores de…**, para marcar los valores que quedan;
- **ordenar**: clic en el título; el segundo clic invierte y el tercero vuelve al orden de llegada (más recientes primero);
- **ordenar las columnas**: arrastre el título para cambiar el orden; el botón derecho ▸ **Columnas** oculta y muestra (el Paciente siempre aparece) y **Restaurar columnas predeterminadas** lo deshace. El orden, los anchos y las columnas ocultas quedan guardados.

Debajo de la lista aparece cuántos trabajos están a la vista y el botón **Limpiar filtros**.

### Vista previa

Haga clic en un trabajo para ver la hoja al lado, con ◀ ▶ para pasar las hojas. Vale para lo que llegó de la modalidad, para la película que vino en el estudio y para la película montada en el compositor (esta se dibuja en el acto, solo para mirar). El **doble clic** abre: la película del compositor se abre en el compositor para editar; las otras abren el estudio.

### Identificar al paciente de una impresión

La impresión DICOM no trae nombre ni ID del paciente. **Identificar paciente…** (con un trabajo recibido seleccionado) abre una ventana con tres caminos:

- **Estudios del mismo aparato y horario**: los estudios de la base de datos hechos en el aparato que envió la impresión, cerca de la hora en que llegó: haga clic para usar;
- **Leer la cabecera de la hoja (OCR)**: el programa lee el texto grabado en lo alto de la primera hoja (unos 2 segundos), muestra lo que leyó y busca en la base de datos los pacientes cuyo nombre —o ID— aparece allí, incluso con un espacio faltante, sin acento o con una letra cambiada. Los que coinciden entran en lo alto de la lista, con el porcentaje ("OCR 95% · …"); cuando el primero gana con holgura, ya viene elegido;
- escribir **Nombre** e **ID** a mano.

> **El OCR es una sugerencia.** Lee lo que la modalidad escribió en la hoja y a veces se equivoca: verifique el nombre antes del OK. Si el paciente no está en la base de datos, los campos se rellenan con lo que se leyó. El lector viene dentro del programa y funciona sin internet.

### OCR al llegar

Cuando una película llega por la impresora DICOM, el programa busca el paciente en la base de datos solo, sin colgar la pantalla. Lee, en este orden, y se detiene en el primero que identifique: el **texto que la modalidad envió aparte** (cuadros de anotación y rótulo de la sesión; hay aparatos que no graban el nombre en la imagen), la **parte superior** de la primera hoja, el **pie** y, por último, la **hoja entera** (unos 2 segundos por lectura):

| El OCR… | Qué ocurre |
|---|---|
| encontró al paciente con holgura clara | nombre e ID entran en el trabajo, el estudio de las hojas ya sale con el nombre, y la película **sigue por la regla** |
| no encontró (o quedó en duda entre dos) | la película **queda detenida**, con la Situación **Esperando paciente** |

La columna **Situación** dice por qué una película recibida no salió: **Esperando paciente** (el OCR no encontró), **Detenida: aparato sin registro** (el paciente puede incluso haberse encontrado, pero el aparato aún no tiene nombre en Orígenes; por defecto, una película de un aparato sin registro no sale sola), **Detenida: origen desactivado** o **En la lista (ninguna regla)**.

Para soltar una película que quedó esperando: selecciónela y use **Identificar paciente…**. Después del OK sigue por la regla sola, por el mismo camino del reenvío automático. Pasar el ratón sobre el nombre muestra de dónde vino (OCR, confirmado a mano, elegido entre los estudios).

> **El paciente tiene que estar en la base de datos.** El OCR compara lo que leyó con los pacientes que ya están aquí. Una película que llega antes de las imágenes del estudio queda esperando su confirmación.

Para desactivarlo: **Configuración ▸ Impresión ▸ Servidores, destinos, reglas y plantillas ▸ Reglas**, casilla "Identificar al paciente por el OCR cuando llegue la película". Desactivada, la regla actúa en cuanto llega la película, como antes de la 0.81.

### Imágenes enviadas a la impresora

Algunas modalidades (la ecografía, por ejemplo) envían **imágenes comunes** a la impresora en vez de una película lista. El puerto de cada servidor de impresión acepta esas imágenes:

- entran en la base de datos como cualquier estudio recibido;
- cuando la modalidad termina de enviar, el programa monta **una película por estudio con todas las imágenes**, en el orden en que llegaron (un clip con muchos cuadros entra con hasta 16, distribuidos). La cuadrícula y el papel vienen de la **regla de Automático** que coincida ("mi AE" es el AE de esa impresora); sin regla que coincida, de la cuadrícula predeterminada escrita al pie de la pestaña;
- si la regla de Automático tiene destino, la película va allí; si no, sigue las **reglas de impresión de ese servidor**, como una película impresa;
- con el **OCR al llegar** activado (Configuración ▸ Impresión ▸ … ▸ Reglas), el programa lee el texto que la modalidad grabó en las primeras imágenes (parte superior, pie y, por último, la imagen entera) y busca al paciente en la base de datos. El nombre que viene en la cabecera de las imágenes **no** vale como prueba: un aparato que envía un nombre genérico tendría ese mismo nombre en la base de datos. Al encontrar al paciente, el nombre y el ID van a la película (incluso en la cabecera de la hoja impresa) y sigue por la regla. Si no lo encuentra, la película queda con la Situación **Esperando paciente**: selecciónela y use **Identificar paciente…**, y después del OK sigue por la regla sola. Con el OCR desactivado, vale el nombre de las imágenes, como antes de la 0.89.

La película aparece en la lista de impresiones como "Montada aquí" y se puede abrir en el compositor.

**Configuración ▸ Impresión ▸ Servidores, destinos, reglas y plantillas de hoja** (o el botón de la pestaña) tiene las pestañas Servidores (cada uno es una impresora que las modalidades ven), Destinos, Orígenes, Reglas, Plantillas de hoja, Automático y Limpieza.

**Automático** (película montada sola, para la modalidad que envía **las imágenes** y no la película lista, como la ecografía): también es una tabla de reglas, una por línea, con Origen (AE), Recibido por, Modalidad, otras condiciones, cuadrícula, cuántas imágenes, adónde va después y la plantilla. El editor tiene las mismas tres listas de marcar —**Origen (AE title de quien envió)**, **Recibido por (mi AE llamado)** y **Modalidad**— y, en **Otras condiciones**, la descripción del estudio (`MAMA|AXILA`). Abajo, **Montar la película así**: cuadrícula, papel, cuántas imágenes (0 = todas), después de montar (dejar en la lista o enviar a un destino) y la plantilla de hoja. La primera regla activada que coincida monta la película, algunos segundos después de que el estudio deja de llegar; una película por estudio.

El "mi AE llamado" es el AE que la modalidad puso como destino. El nodo DICOM acepta cualquier AE llamado en el mismo puerto, así que se pueden registrar en el aparato dos destinos con AE distintos (por ejemplo `US_FILME` y `US_ARQUIVO`) y tener una regla solo para el primero. La lista muestra el AE del nodo, las identidades y los AE de las impresoras; "Otro AE mío…" añade un nombre nuevo. La configuración única de antes de la 0.86 se volvió la primera regla de la tabla.

**Reglas** (pestaña Reglas): una tabla, una regla por línea, con las columnas **Origen (AE)**, **Recibido por** (su AE), **Modalidad**, otras condiciones, destino, plantilla y si se detiene ahí. La casilla de la primera columna activa y desactiva la regla; ▲ ▼ cambian el orden (la primera que coincida manda); el doble clic edita.

En el editor de la regla, el **Cuándo** son tres listas lado a lado, de marcar:

- **Origen (AE title de quien envió)**: los AE que ya enviaron trabajo, con el nombre dado en Orígenes. Para un aparato que aún no envió nada, escriba el AE en "Otro AE title…" y haga clic en **+**;
- **Recibido por (mi AE)**: sus servidores de impresión (AE, puerto y nombre);
- **Modalidad**: MG, CT, MR, US… (las de los orígenes entran junto; "Otra…" añade). La modalidad es la del estudio del paciente identificado o, sin paciente, la del registro del origen; un trabajo de modalidad desconocida no coincide con una regla que exige modalidad.

En cada lista se pueden marcar varias; una lista sin nada marcado es "cualquiera". El trabajo tiene que coincidir con las tres. Para tratar distinto cada aparato, cada AE suyo o cada modalidad, haga una regla para cada caso (**Duplicar…** ayuda). **Otras condiciones** guarda el resto: aparato registrado (AE + dirección), AE con comodín (`MG*`), rótulo, tamaño de la película, número de hojas y horario. Abajo, el **Resumen** dice en una línea lo que hace la regla. Las reglas hechas antes de la 0.85 siguen valiendo como estaban; al abrir una en el editor, el servidor y la modalidad aparecen marcados en las listas.

**Limpieza** (pestaña propia): borra sola, al abrir el programa y cada hora, los trabajos recibidos que cumplen **todos** los criterios marcados: más viejos que N días (por la llegada), **solo los ya impresos** (predeterminado), de una **modalidad** (`MG`, `MG|US`) y de ciertos **orígenes** (ninguno marcado = todos). **¿Cuántos saldrían?** cuenta antes; **Limpiar ahora…** borra en el acto. Nace desactivada. No borra película del compositor, película que vino en el estudio ni el estudio creado en la base de datos con las hojas.

**Duplicar…**: en Servidores, Destinos, Reglas y Plantillas de hoja, elija un elemento y use **Duplicar…** para empezar de una copia. Abre el editor ya rellenado, con el nombre "(copia)", y usted cambia solo lo que sea distinto; la copia entra justo debajo de la original (en las reglas, el orden importa). El servidor copiado recibe un puerto libre, porque dos servidores no comparten puerto. La lista de impresoras DICOM (**Película ▸ Impresoras**) también tiene **Duplicar**.

> **Nada sale solo por defecto.** Un servidor de impresión nace desactivado, el destino automático nace vacío y, sin ninguna regla, el trabajo queda esperando en la lista. Quien manda que salga es usted, o una regla que usted escribió.

## Panel de películas e impresiones

**Archivo ▸ Panel de películas e impresiones…**, o **Panel…** en la pestaña Impresiones.

- **Qué entra**: las películas montadas en el compositor **y las impresiones que llegaron listas por la impresora DICOM**. La columna **Origen** dice cuál es cuál (Compositor o Impresión DICOM).
- **Filtros**: período, origen, modalidad, usuario (o aparato), "detenido hace más de N días" y solo los no impresos.
- **Tarjetas**: películas (cuántas del compositor y cuántas por impresión DICOM), **% impresas**, detenidas (guardadas y no impresas hace más de N días), y las medianas de **estudio → película**, **película → impresión** y **estudio → impresión** (con el percentil 90 en el detalle y el % impreso en hasta 24 h), hojas impresas y reimpresiones.
- **Gráficos**: películas por mes (impresas y no impresas) y % impreso por modalidad.
- **Tablas** por modalidad y por usuario o aparato, y la lista de películas (ordenable; doble clic abre la película en el compositor o, en la impresión DICOM, el estudio con las hojas). **Exportar CSV…** para Excel.

| Detalle | Cómo se cuenta |
|---|---|
| Modalidad | la de las series de las imágenes que están en la película: en un PET/CT, una película solo de TC cuenta como TC. Una película con dos modalidades cuenta en las dos |
| Impresión | impresora de Windows, DICOM Print y envío por la pestaña Impresiones cuentan; PDF y JPG/PNG no |
| Tiempos | estudio → película va de la fecha/hora del estudio hasta la película guardada; película → impresión, hasta la última impresión. El tiempo negativo (hora equivocada del aparato) queda fuera de la cuenta |
| Impresión DICOM | cuenta desde la llegada; "creado por" es el aparato (el nombre registrado en Orígenes, o el AE). Queda como impresa cuando se reenvía, por la regla o a mano. El estudio es el del paciente identificado (OCR o a mano), el más reciente hecho hasta la llegada (el mismo día o el anterior); sin paciente identificado, modalidad y tiempos quedan en blanco |
| Películas antiguas | usuario y destino solo se graban desde la versión 0.77; antes de eso aparecen como "(no registrado)" |

El panel desaparece en el modo Ocultar y en la reunión: la lista tiene nombres de pacientes.

# Medicina nuclear y oncología

## Medicina nuclear

En los estudios NM y PET aparece el botón **MN**, con: anterior y posterior lado a lado (con la misma ventana en los dos), invertir la escala, curvas y análisis por ROI, renograma y los cálculos de captación.

El SUV funciona en el PET (con los datos de dosis y decaimiento del archivo). En SPECT/TC, no: la conversión exige una calibración que no está en el DICOM. El programa lo dice en vez de devolver un número inventado.

> **Los valores normales de medicina nuclear no están en el código.** El programa devuelve un número; el rango de referencia es texto al lado, nunca un veredicto. Cuando una cuenta no sale, la respuesta es "no se pudo", no un número grande.

## Seguimiento de lesiones

El panel de lesiones da nombre a cada lesión, y las mediciones de estudios distintos se ligan a ella. El panel muestra la evolución y calcula la respuesta. **Diseño de las lesiones** pone un cuadro por lesión.

**Tiempo de duplicación**: en cada estudio en que la lesión creció desde el estudio anterior medido, la celda gana "· TD N d" (fuera del PERCIST). La cuenta es TD = t × ln 2 ÷ ln(V2/V1), suponiendo crecimiento exponencial, por el **volumen** cuando los dos estudios tienen volumen segmentado; si no, por el **mayor diámetro**, suponiendo una esfera (V ∝ d³). Sin crecimiento, sale "TD no se aplica": nunca un número enorme o negativo. La pista de la celda muestra las dos mediciones, el intervalo en días y la base de la cuenta; en una lesión pequeña, 1 mm de diferencia en el diámetro cambia mucho el resultado.

**Seguimiento entre fechas** (0.99.59):

- **Vínculo por la posición**: cada medición ligada a una lesión guarda dónde está en el paciente (en mm). Dibuje la medición en el estudio de seguimiento en el lugar de la lesión: llevada al estudio anterior por el registro (el rígido, o la alineación guardada al enlazar los cuadros), si cae a hasta **10 mm** de donde estaba la lesión, la medición **se liga sola** a ella, y la barra de estado dice a cuál y a qué distancia. Sin registro entre los dos estudios no se liga (no hay cómo saber dónde está el punto en el otro); con dos lesiones cerca, tampoco: ligue a mano. La casilla y la distancia quedan en el panel de lesiones.
- **Seguimiento…** (en el panel): las lesiones medidas antes y aún sin medición en este estudio, una por fila. **Repetir la medición** abre la serie equivalente en el lugar estimado, con el contorno anterior en amarillo y la misma herramienta; la próxima medición se liga a la lesión. **Demasiado pequeña (5 mm)** (diana; el RECIST 1.1 suma 5 mm), **Ausente (0)** y, en las no diana, **Presente / estable** y **Progresión inequívoca**. Las mediciones hechas antes de la 0.99.59 no tienen posición: el Repetir abre la serie, sin el lugar.
- **Nadir**: la fila *Nadir* muestra, en cada estudio, la menor suma hasta ahí, y el encabezado marca con ▼ el estudio que es el nadir del actual. El resumen del informe trae las cuatro fechas (base, nadir, anterior y actual) con la suma de cada una.

**Contorno de la lesión en el PET por el borde (0.100.8).** En la **Segmentar 3D** de un PET, el método **PET: borde por el gradiente (como el PET Edge)** contornea la lesión donde la señal **cae más rápido**, y no en un valor fijo. El umbral en % del SUVmáx (41 %) depende del pico: en una lesión pequeña el volumen parcial hunde el máximo, el umbral baja hasta el fondo borroso y el contorno se hincha. El borde por el gradiente no depende del pico.

- El programa parte del punto más caliente cerca del clic, lanza rayos en cerca de 260 direcciones y, en cada una, encuentra la caída más pronunciada antes de que la señal vuelva a subir (otra lesión, el corazón, la vejiga). El borde de cada dirección se verifica con las vecinas, y la lesión es lo que queda dentro de él.
- **Corrección del volumen parcial**: en una lesión borrosa por la resolución del aparato, la caída más pronunciada queda un poco hacia dentro del borde verdadero: poco en una lesión de 4 cm, bastante en una de 1,3 cm. El programa lleva cada rayo de vuelta al borde verdadero usando la **resolución del PET (FWHM)**. En una lesión grande, mide la resolución en la propia lesión (el ancho de la caída); en las pequeñas, usa el campo **Resolución del PET (FWHM)** de la ventana (6 mm de fábrica; PET/TC actual, 5–7 mm). El valor queda guardado.
- La nota de la ventana dice en qué porcentaje del máximo quedó el borde y qué resolución se usó. Por debajo de 1,5 × la resolución, avisa que la lesión está **cerca del límite** y que el volumen es menos fiable.
- En esferas de prueba (resolución de 7 mm, ruido de PET, fondo 4:1 a 8:1), el volumen quedó a ±15 % del real a partir de 1,3 cm, y el 41 % erró el doble o más en las pequeñas.

**PET en el seguimiento** (0.99.60, botón **PET…** del panel de lesiones):

- **SUL**: con la altura (PatientSize) y el sexo en el archivo, cada medición de PET guarda también el SUL: el SUV por la masa magra de Janmahasatian (LBM = 9270 × peso / (6680 + 216 × IMC) en los hombres, 9270 × peso / (8780 + 244 × IMC) en las mujeres). El PERCIST pasa a usar el SULpeak; sin altura o sexo, sigue en el SUVpeak y la celda dice cuál.
- **Referencia del hígado**: *Hígado: clic*: haga clic en el lóbulo derecho, en el PET; la esfera de 3 cm busca, hasta 2 cm del clic, el lugar más homogéneo (menor desviación estándar). *Hígado: automático*: usa la segmentación del hígado del estudio (Órganos/TotalSegmentator en la TC del PET/TC), pone la esfera entera dentro de él, en el lóbulo derecho. **Mediastino**: haga clic en la aorta descendente (esfera de 1 cm). Las referencias quedan por estudio.
- **PERCIST**: umbral de lesión medible = 1,5 × SULmedio del hígado + 2 × DE (sin hígado, 2 × pool + 2 × DE). El panel muestra la referencia y el umbral en cada estudio; avisa cuando la lesión más ávida de la base queda por debajo del umbral y cuando el hígado varía más de 20 % o 0,3 entre los estudios (no comparables).
- **Deauville / Lugano** (criterio nuevo en el panel): la puntuación de cada lesión en cada estudio se propone por los números (2 hasta el mediastino, 3 hasta el hígado, 4 por encima del hígado, 5 por encima de 2 × el SUVmáx del hígado (ajustable) o lesión nueva, 1 ausente) y se cambia con el botón derecho ▸ *Deauville en este estudio* (incluye la X). La respuesta metabólica sale por la mayor puntuación: 1–3 completa; 4–5 con captación menor que la de la base, parcial; igual, sin respuesta; mayor o lesión nueva, progresión.
- **Q.Check**: la cabecera del PET de este estudio (tiempo de captación (50–70 min), peso, altura y sexo, dosis, vida media, unidad, correcciones de decaimiento y atenuación, matriz, grosor, reconstrucción y aparato) y la comparación con el estudio de base (diferencia de captación hasta 15 min, mismo aparato y reconstrucción, peso, dosis, hígado). La glucemia no viene en el DICOM: escriba la de la ficha en el campo **Glucemia** de la ventana PET… (0.99.88). Queda guardada en el estudio; el Q.Check avisa por encima de 200 mg/dL (la EANM recomienda reprogramar o interpretar con cautela, el SUV queda subestimado) y dice que 150–200 es aceptable. Con la glucemia, las mediciones en el PET muestran también el **SUVgluc** = SUV × glucemia ÷ 100 mg/dL (acepta mmol/L: valores por debajo de 35 se vuelven mg/dL × 18).

La segmentación 3D mide volumen, SUV máximo y medio, TLG y, sumando las lesiones, TMTV. Los umbrales (porcentaje del SUVmáx, SUV mínimo, método) quedan guardados, y la barra del umbral vale también para el porcentaje del SUVmáx.

## Lectura PET y el SUV máximo cerca del cursor (0.99.88)

En el botón **Fusión** de los estudios de PET/TC:

- **Lectura PET: fusión, PET y MIP girando…** arma tres cuadros: la TC con el PET fusionado, el PET solo y el MIP del PET en 3D, invertido y girando. **Haga clic en un foco del MIP** para llevar los cortes de los otros cuadros hasta él. El PET corregido por atenuación se prefiere al NAC.
- **Ir al SUV máximo cerca del cursor (3 cm)** busca el vóxel más ávido en una esfera de 3 cm alrededor del cursor de referencia y lleva los cortes hasta él; la barra de estado dice el SUV. Útil para fijar el SUVmáx de una lesión sin cazar el píxel a mano.

## Sesión preparada del PET/TC (0.100.32)

Cuando la carga tumoral se ejecuta (sola en la llegada del estudio (Configuración ▸ CAD/IA ▸ Carga tumoral ▸ *Hacer automáticamente*) o por el botón **Carga**), el estudio queda listo para la lectura:

- **Referencias medidas.** El hígado (esfera de 3 cm en el lóbulo derecho) y el mediastino (esfera de 1 cm en la aorta descendente, encontrada por TotalSegmentator) quedan guardados donde la ventana **PET…** guarda las mediciones a mano: el umbral del PERCIST, el Deauville y la comparación del hígado con el estudio anterior ya se abren listos. Una referencia que usted midió a mano nunca se cambia.
- **Registro con el PET/TC anterior.** La TC se registra (rotación y traslación) con la TC del PET/TC anterior más reciente del paciente. Al abrir el anterior en un cuadro al lado (botón Previos), los dos ya se desplazan juntos. Un registro que ya existe entre los dos estudios no se cambia, y un registro de calidad floja no se guarda (el aviso aparece en el mensaje).
- **Se abre en la Lectura PET.** El estudio preparado, aún sin un estado de análisis guardado, se abre con la TC fusionada, el PET y el MIP girando. Si usted ya dejó el estudio de otro modo, vale el suyo.

Las dos opciones están en Configuración ▸ CAD/IA ▸ Carga tumoral: *Sesión preparada…* y *Abrir el estudio preparado en la Lectura PET*. El registro usa hasta 60 s.

## Carga tumoral en el PET: FDG, PSMA y DOTA (0.99.88)

Botón **Carga** (o Aplicaciones ▸ Carga tumoral) en un PET/TC. TotalSegmentator encuentra los órganos y los huesos en la TC del estudio (y, en el PSMA, las glándulas salivales); los órganos se llevan a la cuadrícula del PET. En el PET, todo lo que está por encima del umbral del trazador y no está en un órgano de captación fisiológica (dilatado 1 vóxel) se vuelve un **foco**:

- **Trazador**: leído de la cabecera (radiofármaco, descripción del estudio o de la serie). Sin él, las cuentas son de FDG y el aviso lo dice.
- **Umbral**: FDG: PERCIST (1,5 × hígado + 2 DE, por la esfera de 3 cm en el hígado segmentado; sin hígado, SUV 2,5), o un SUV fijo en las configuraciones; **PSMA**: SUV 3 (qPSMA); **DOTA**: la media del hígado (Krenning).
- **Captación fisiológica retirada**, por trazador: en FDG, encéfalo, corazón, riñones y vejiga; en PSMA, glándulas salivales, riñones, vejiga, hígado, bazo e intestino; en DOTA, hígado, bazo, suprarrenales, riñones, vejiga e intestino. La lista retirada sale en los avisos: en PSMA y DOTA una lesión hepática **no entra** en la cuenta.
- Cada foco (≥ 0,3 mL, ajustable) tiene volumen, SUVmáx, SUVmedio, SUVpeak, TLG y **región**: próstata, hueso (con el nombre del hueso: L3, 5.º arco costal derecho…), ganglio pélvico (por debajo de la cresta ilíaca), ganglio/partes blandas extrapélvico o víscera (pulmón, hígado…). Salen el **MTV** y la **TLG** totales.
- **En el PSMA**: el **miTNM** (PROMISE: miT por la próstata, miN1 pélvico, miM1a extrapélvico, M1b hueso —uni, oligo hasta 3 o diseminado—, M1c víscera) y la **puntuación miPSMA** de cada foco por las referencias del estudio: 0 por debajo del pool sanguíneo (aorta), 1 por debajo del hígado, 2 por debajo de la parótida, 3 por encima.
- Cada foco se vuelve un hallazgo en **Aplicaciones ▸ Hallazgos de IA**. **Descartar** un foco (inflamación, músculo, grasa parda, intestino…) lo saca del total: el texto del **informe** suma solo los confirmados y rehace el miTNM. La máscara queda en una SEG sobre el PET (serie 987), un segmento por región.

Son cuentas automáticas por umbral: verifique cada foco antes de usar el número.

## El botón IA (0.100.37)

Las IA quedan en un solo botón en la barra del visor: **IA**. Abre una lista, como la de las mediciones, con las IA que valen para el estudio abierto (por la misma regla de la barra inteligente: nódulos, enfisema, Genant, aorta y calcio en una TC de tórax; BraTS y lesiones en el FLAIR en una RM de cráneo…). Pase el ratón por una de ellas para ver qué hace (ejecutar en la serie del cuadro activo, ver el resultado) y haga clic. Al final de la lista: **Hallazgos de IA** (revisar, confirmar, descartar), **Tareas de IA** (avance y cancelar) y **Otras IA**, con las que la regla dejó fuera, que se ejecutan igual. El resultado se abre en el panel de cada IA, como antes.

Para volver a tener un botón para cada IA, marque **Mostrar cada IA con su botón en la barra**, al final de la misma lista. El botón **Aplicaciones** sigue listando todas.

## Qué graba cada IA en el estudio (0.100.124)

Toda IA que segmenta graba una **serie SEG** (las máscaras, que el botón **CAD/overlay** activa y desactiva). Algunas graban también **imágenes aparte**: tablas de números e imágenes de verificación. La mamografía graba la propia imagen del estudio con las marcas dibujadas.

| IA | Qué graba |
|---|---|
| Calcificaciones vasculares de la mama | Imagen de mamografía con las calcificaciones marcadas, informe estructurado (SR) y resumen |
| Densidad mamaria | SR e imagen de resumen |
| Órganos abdominales | SEG y una imagen-tabla de volúmenes (HU, en la TC) |
| Niveles de la columna | SEG, tablas de mediciones de los discos y de las vértebras (imágenes) y un segundo sagital de verificación con los niveles escritos |
| Hígado en la RM | SEG, imagen de resumen e imagen de la región de la rigidez |
| Índices del cráneo y cefalometría | SEG y una imagen de verificación |
| Ganglios, enfisema, aorta, médula, composición corporal, calcio coronario, nódulos, próstata, lesiones hepáticas, FLAIR, PET | Solo la SEG (los números quedan en los hallazgos de IA) |
| Dinámica de la mama alineada | Series de imagen (fases alineadas y sustracciones) |

Las imágenes-tabla y de verificación son imágenes comunes, sin relación con el CAD/overlay: aparecen como series propias, con el sello de IA, y tienen el nombre del paciente escrito en la imagen (por eso la anonimización y el modo reunión las tratan aparte).

### Para el PACS que no muestra SEG

En **Configuración ▸ CAD/IA**, el grupo **Qué graban y envían las IA (todas las IA)** tiene tres casillas y una lista de destinos:

- **Series SEG**: desmarcada, la SEG no va a los destinos (sigue en el estudio de Ipê, porque el CAD/overlay y las mediciones dependen de ella).
- **Tablas e imágenes de verificación**: van como imagen común.
- **Serie con overlay coloreado**: el estudio con las máscaras pintadas (núcleo translúcido y contorno), **una imagen por corte, en la posición del corte original**. Cualquier PACS la muestra y la recorre. Se genera a partir de la SEG grabada, por eso vale para **toda IA que grabe SEG**. Viene **desactivada** de fábrica, porque ocupa espacio (una imagen coloreada por corte); no se hace en estudios de más de 800 cortes ni en estudios multicuadro (Enhanced). Aparece como la serie `… · overlay coloreado · Ipê`.
- **Destinos**: los nodos DICOM que reciben lo que las IA graban. Valen para todas las IA, sumados a los de cada herramienta.

**En cada IA**, en sus configuraciones, el cuadro **Qué graba y envía esta IA** sobrepone la elección global: SEG, tablas y overlay como *Como en todas las IA / Sí / No*, y los destinos como *los de todas las IA y los de esta herramienta* o *solo los de esta herramienta* (sin ninguno marcado, esa IA no envía a ningún lugar).

La serie coloreada solo se hace para IA ejecutadas después de activar la opción; para estudios que ya tienen SEG, rehaga la IA.

## Tareas de IA: avance y cancelar

Las IA de Ipê (órganos abdominales, niveles de la columna, cefalometría, índices del cráneo, niveles ganglionares, implante en la mamografía) se ejecutan pedidas a mano o **solas cuando llega el estudio** (Configuración ▸ CAD/IA). Una por vez; las otras esperan en la cola.

- **Tareas de IA** muestra cada una: estudio, herramienta, si fue automática o a mano, situación (en la cola, armando el volumen, ejecutando, grabando, lista, error, cancelada), la etapa y el tiempo. Se abre por el botón **Aplicaciones** del visor, por **Ver ▸ Tareas de IA**, y por el aviso **⚙ IA: 1 ejecutando, 2 en la cola** que aparece en la barra de estado mientras hay alguna activa (un clic abre la ventana).
- **Cancelar la elegida** (o **Cancelar todas**): en la cola, no empieza; ejecutando, el proceso se derriba y **no se graba nada** en el estudio. La cancelación queda en el historial de la gestión automática. La ventana no es modal: se puede seguir trabajando con ella abierta.
- **Cerrar el estudio no interrumpe la IA pedida en él**: sigue ejecutándose y graba el resultado en el estudio, que aparece al abrir de nuevo. Si el trabajo no se detiene en 15 segundos después del Cancelar (por ejemplo, el proceso se colgó), la tarea se cierra a la fuerza y el estudio queda libre para las otras IA. Con una sola tarea activa, Cancelar la elegida funciona sin elegir la fila.
- **En la base de datos**, el estudio que tiene resultado de IA gana **✦** junto al nombre (la pista dice cuáles: "IA: órganos abdominales, columna"), y el que tiene IA en la cola o ejecutando, **⚙**. La columna **IA** (Columnas ▾) muestra las dos cosas por escrito.
- **Órganos abdominales** en el visor: botón **Órganos** (TC/RM de abdomen o pelvis; en los otros estudios, por el botón **Aplicaciones**) ▸ *Segmentar órganos abdominales de esta serie (IA)*. Graba las máscaras y la tabla de volúmenes en el estudio.

### Instalar la segmentación (TotalSegmentator)

Las IA de órganos, columna, cabeza y cuello, nódulos y cráneo se ejecutan en un entorno Python aparte, instalado una vez por **Configuración ▸ CAD/IA ▸ Instalar la segmentación de órganos (TotalSegmentator)…**. También se puede ejecutar el instalador fuera de Ipê: el archivo `instalar_segmentacao.bat` queda en la carpeta del programa, dentro de `_internal\ipe` (en la versión del código fuente, en la carpeta del proyecto). Necesita internet y unos 5 GB.

**La ventana de la instalación.** La instalación (la de la segmentación y la de los modelos extra) se ejecuta en una ventana del propio Ipê, que no bloquea el programa: arriba aparecen el paso actual y el tiempo transcurrido; en el medio, todo lo que el instalador escribe, con las líneas de error en rojo. Al final la ventana vuelve al frente con el veredicto (**Instalado sin errores**, **terminó con errores** o **NO quedó instalado**), verificado de verdad (¿se creó el entorno? ¿los modelos están en la carpeta?), no solo por lo que dijo el instalador. **Copiar todo** y **Guardar…** sirven para enviar la salida a quien da soporte; el texto también queda en `instalacao_ia.log`, en la carpeta de los registros (**Abrir la carpeta del registro**). Cerrar la ventana en el medio pregunta si es para interrumpir o solo esconder; escondida, vuelve por el mismo menú.

El instalador busca un Python de 3.10 a 3.13 que **abra de verdad** (un Python roto o el acceso directo de Microsoft Store no cuentan) y, si no hay, descarga un Python 3.12 solo para la segmentación. Al comienzo lista los Python del ordenador. Las variables PYTHONHOME y PYTHONPATH de Windows, que hacen que cualquier Python se rompa con *No module named 'encodings'*, se ignoran y aparecen como aviso. Un entorno antiguo que no abre se borra y se rehace; si la carpeta está atascada, la renombra. El **Visual C++ Redistributable** de Microsoft (x64) solo hace falta para la segmentación, por causa de PyTorch; Ipê y Python no lo necesitan. El instalador de Ipê verifica si existe y, si falta, ofrece abrir la descarga (https://aka.ms/vs/17/release/vc_redist.x64.exe), y Configuración ▸ CAD/IA ▸ Instalar la segmentación avisa lo mismo. Después de instalar PyTorch, el instalador de la segmentación verifica que abra; si no abre (en Windows, el error *WinError 126 … shm.dll*), casi siempre falta el **Microsoft Visual C++ Redistributable**, y el instalador lo descarga de Microsoft y lo instala (Windows puede pedir permiso de administrador y, a veces, reinicio). Si aun así falla, instale el Python 3.12 de python.org (marcando *Add python.exe to PATH*) y ejecute de nuevo. Si el fallo es de red (mensajes con *connection*, *timeout*, *SSL* o *proxy*), libere download.pytorch.org, pypi.org y files.pythonhosted.org.

## Hallazgos de IA y nódulos pulmonares

Las IA que **señalan** algo (la primera es la de nódulos pulmonares) no escriben en el informe: cada candidato se vuelve un **hallazgo sugerido**, revisado uno a uno en la ventana **Hallazgos de IA** (botón **Aplicaciones** ▸ *Hallazgos de IA…*, o el menú del botón **Nódulos**).

- Cada fila dice el rótulo (N1, N2…), el tipo, la ubicación, las mediciones, el **estado** (*sugerido* (ámbar), *confirmado* (verde), *corregido* (azul) o *descartado* (gris)) y quién revisó y cuándo. Abajo, de dónde vino: el modelo y la versión, la serie usada y los avisos (corte grueso, por ejemplo).
- **Ir a** (o doble clic) lleva el cuadro con la serie usada por la IA al corte del hallazgo, con el cursor 3D encima.
- **Confirmar**, **Descartar**, **Volver a sugerido**. **Corregir…** abre los números para que usted los cambie (diámetro, volumen, consistencia) y una observación; el hallazgo queda *corregido* y el informe lleva sus números.
- **Seguir como lesión** (solo en el confirmado o corregido): crea la lesión en el seguimiento ("N1 (IA)", con el lóbulo como ubicación) y una medición (un círculo del diámetro, con el volumen) en el corte del hallazgo. De ahí en adelante entra en el seguimiento y en el tiempo de duplicación, como cualquier lesión.
- **Enviar al informe** lleva solo los confirmados y los corregidos, una frase por hallazgo ("Nódulo sólido en el lóbulo inferior derecho, diámetro medio de 6,2 mm y volumen de 120 mm³ (N1)."). Sin informe abierto, el texto va al portapapeles.
- Ejecutar la IA de nuevo cambia solo los **sugeridos**. Lo que usted ya revisó se queda, con su rótulo, y no vuelve como sugerencia (el candidato a menos de 5 mm, o de medio diámetro, de un hallazgo revisado es el mismo hallazgo).

**Nódulos pulmonares** (botón **Nódulos**, en la TC de tórax; o Configuración ▸ CAD/IA ▸ Nódulos pulmonares, para ejecutar solo cuando llega el estudio). Usa la tarea abierta *lung_nodules* de TotalSegmentator (modelo de BLUEMIND AI, entrenado en 1353 TC, parte del LIDC-IDRI) y los lóbulos de la tarea *total*. En cada candidato:

| Número | Cómo sale |
|---|---|
| Diámetro mayor y ejes | los tres ejes perpendiculares de la máscara |
| Diámetro medio | media de los dos ejes mayores (el "diámetro medio" de Fleischner y Lung-RADS) |
| Volumen | vóxeles × volumen del vóxel |
| HU medio y parte sólida | media del HU; parte sólida = vóxeles a partir de −300 HU |
| Consistencia (por el HU) | propuesta: ≥ 80 % sólido, ≤ 20 % vidrio esmerilado, en el medio parcialmente sólido |
| Lóbulo | el lóbulo del centro (o el más cercano, hasta 10 mm) |

Los candidatos menores que el **diámetro mínimo** (3 mm de fábrica, de la esfera de igual volumen) no entran; quedan como máximo los 30 mayores. La serie preferida es la de pulmón de cortes finos; cortes de más de 2,5 mm generan aviso (Fleischner pide hasta 1,5 mm para nódulos pequeños). La consistencia por el HU es una propuesta: en un nódulo de pocos milímetros el volumen parcial baja el HU, y un nódulo sólido puede parecer vidrio esmerilado. La SEG "Nódulos pulmonares · TotalSegmentator" queda en el estudio, un segmento por candidato.

Para quien ya había instalado la segmentación: ejecute de nuevo *instalar_segmentacao* para descargar los modelos *lung_nodules* y *total* (o se descargan solos la primera vez, con internet).

**Nódulo por clic y crecimiento entre estudios** (0.99.62). En la TC, clic derecho en el nódulo ▸ *Nódulo pulmonar aquí (segmentar por clic)…*. No necesita la IA:

- La ventana segmenta a partir del punto: los vóxeles conectados por encima del umbral (−500 HU, la parte sólida; marque *Incluir el vidrio esmerilado* para −750 HU), en una caja de 25 mm de radio. *Separar de los vasos y de la pleura* hace una apertura de 1 vóxel, que corta el puente fino entre el nódulo y el vaso. La máscara aparece encima de la imagen, en cualquier plano; si toca el borde de la caja, la ventana avisa que se desbordó.
- Los números son los mismos de los candidatos de la IA: diámetro mayor y medio, volumen, HU medio, parte sólida, consistencia por el HU, ejes; y el lóbulo, cuando el estudio tiene la segmentación de los lóbulos.
- **Guardar como hallazgo** pone el nódulo en la lista de Hallazgos de IA, ya **confirmado** (modelo "Ipê: segmentación por clic"). Ejecutar la IA de nuevo no lo borra. **Guardar y seguir como lesión** ya lo pone en el seguimiento.
- **El mismo nódulo en el estudio anterior**: los nódulos confirmados o corregidos de los otros estudios del paciente, llevados a este por el registro, hasta 10 mm. Sin registro entre los dos estudios, vale el mismo lóbulo y hasta 25 mm, marcado "probable, sin registro (verifique)". La ventana y la lista de Hallazgos muestran el crecimiento: diámetro medio, volumen y el **tiempo de duplicación del volumen** (TD = Δt · ln 2 / ln(V2/V1)).
- Si el nódulo anterior ya estaba en el seguimiento, *Seguir como lesión* pone la medición nueva **en la misma lesión**. La tabla de las lesiones gana la columna del estudio nuevo, con el tiempo de duplicación. *Enviar al informe* añade "En relación con el estudio del dd/mm/aaaa (N1): …".

**Composición corporal en L3 y atenuación hepática** (botón **Composición**, en la TC de abdomen; o automático en Configuración ▸ CAD/IA ▸ Composición corporal). Los números aparecen como dos hallazgos en la misma ventana ("Composición corporal (L3)" y "Atenuación hepática") para verificar, corregir y enviar al informe como los otros.

- **Dónde mide**: el corte axial del medio craneocaudal de la vértebra L3 (encontrada por TotalSegmentator). La serie tiene que ser axial; si no lo es, la composición no sale (el hígado sale igual). *Ir a* lleva al corte de L3, y la SEG "Composición corporal · TotalSegmentator" muestra en él los cuatro compartimentos.
- **Cómo separa** (umbrales clásicos, Mitsiopoulos et al., 1998): músculo de −29 a 150 HU fuera de la cavidad abdominal, de los órganos y de la vértebra; grasa de −190 a −30 HU: visceral dentro de la cavidad (tarea abierta *trunk_cavities*), subcutánea en las regiones de grasa que tocan la piel, intermuscular el resto. La piel (3 mm de afuera) no cuenta como músculo.
- **Salen**: área muscular (SMA, cm²), densidad muscular (HU medio del músculo), grasa visceral, subcutánea e intermuscular (cm²) y VAT/SAT. Con la altura, el **índice muscular** (SMA/altura², cm²/m²), con la referencia de sarcopenia del sexo del paciente al lado (Prado et al., Lancet Oncol 2008: < 52,4 (hombres) y < 38,5 cm²/m² (mujeres)), como texto, no veredicto. Con el peso, el **IMC** y las referencias de Martin et al., J Clin Oncol 2013, que dependen de él: sarcopenia con índice < 43 cm²/m² en hombres con IMC < 25, < 53 con IMC ≥ 25 y < 41 en mujeres; miosteatosis con densidad muscular < 41 HU (IMC < 25) o < 33 HU (IMC ≥ 25).
- **Altura, peso y sexo** (0.99.80): al hacer clic para calcular, se abre una ventana con lo que vino del archivo (PatientSize, PatientWeight, PatientSex) para verificar o escribir; *Cancelar* no calcula. Lo escrito vale para ese estudio (el archivo no cambia) y se usa de nuevo si la IA se ejecuta otra vez. Después del cálculo, **Hallazgos de IA ▸ Altura y peso…** cambia los valores y rehace el índice, el IMC y las referencias sin ejecutar la IA. La casilla *Preguntar siempre antes de calcular* desactiva la ventana; para reactivarla, marque la casilla de nuevo en *Altura y peso…*.
- **Hígado y bazo**: media y mediana del HU (el borde, 2 vóxeles, queda fuera), hígado − bazo e hígado / bazo. En la TC sin contraste vienen las referencias como texto, las dos 100 % específicas para esteatosis de 30 % o más en la biopsia: hígado − bazo < −9 HU o hígado / bazo < 0,8 (Park et al., Radiology 2006) e hígado < 48 HU (Pickhardt et al., Eur Radiol 2012). Con contraste (por la etiqueta ContrastBolusAgent o por la descripción de la serie) la pantalla avisa que esos umbrales no valen.
- **Resultado de la esteatosis** (0.99.80), que aparece debajo de la lista en Hallazgos de IA y va al informe junto con los números:
  - *Compatible con esteatosis moderada a acentuada (≥ 30 %)*, cuando uno de los criterios anteriores se cumple;
  - *Esteatosis leve posible*, cuando el hígado está menos denso que el bazo (hígado / bazo < 1,0) sin cumplir ninguno;
  - *Sin signos tomográficos de esteatosis moderada o acentuada*, si no; la TC no excluye la leve;
  - *No clasificado* en la serie con contraste.
  
  Si usted corrige el HU del hígado o del bazo, el resultado acompaña; en *Corregir…* se puede escribir otro resultado.
- Ejecute de nuevo *instalar_segmentacao* para descargar el modelo *trunk_cavities*.

**Grasa y hierro hepáticos en la RM** (botón **Hígado**, en la RM de abdomen; o automático en Configuración ▸ CAD/IA ▸ Grasa y hierro hepáticos). El hígado, el bazo y los segmentos de Couinaud vienen de TotalSegmentator (*total_mr* y *liver_segments_mr*), ejecutado en una serie anatómica axial del abdomen (de fábrica, el "WATER" del LAVA/Dixon; la de la pelvis queda fuera); la máscara se lleva punto a punto, por la posición en el paciente, a la cuadrícula de cada mapa, que suele ser más gruesa (en el IDEAL IQ del acervo, cortes de 16 mm cada 8 mm). El borde del hígado (1 vóxel en el plano) queda fuera. Salen hasta tres hallazgos, en la ventana Hallazgos de IA:

| Hallazgo | De dónde | Números |
|---|---|---|
| Grasa hepática (PDFF) | el mapa de fracción de grasa del aparato (IDEAL IQ, mDIXON Quant, LiverLab), reconocido por la ImageType FAT_FRACTION o por la descripción | mediana, media, p25 y p75 (%), y la mediana de cada segmento |
| Hierro hepático (R2*) | el mapa de R2* (o de T2*, convertido: R2* = 1000 / T2*) | R2* mediano (s⁻¹), T2* (ms), R2* del bazo; a 1,5 T, el hierro estimado |
| Grasa hepática (doble eco) | el doble eco en fase / fuera de fase (los dos ecos en la misma serie, o el par InPhase/OutPhase) | fracción de **señal** de grasa = (EF − FF) / (2 · EF), y la razón EF/FF |

- **Hierro estimado**: LIC = 0,0254 · R2* + 0,202 mg Fe/g de peso seco (Wood et al., Blood 2005), calibración de 1,5 T. **A 3 T** (0.99.50) el R2* del hígado se divide por 2,05 para el equivalente a 1,5 T (Alam et al., JCMR 2016: el R2* hepático a 3 T fue 105 % mayor) y entonces entra en la fórmula de Wood; el hallazgo muestra también ese R2* equivalente. A 3 T el T2* muy corto se mide peor: en sobrecarga grave, prefiera 1,5 T. En otro campo (o sin el campo en el archivo) no estima.

- **Hierro por las dos fórmulas** (0.100.126): además de Wood, Ipê calcula el LIC por **Hankins et al. (Blood 2009)**, LIC = 0,02802 · R2* − 0,45485 mg Fe/g, sobre el R2* del equipo (nunca por debajo de cero). El **campo de la RM se lee del DICOM** y aparece junto al hierro. El LIC principal y la clasificación usan, por defecto, **Wood a 1,5 T y Hankins a 3 T**; en Configuración ▸ CAD/IA ▸ *Fórmula del hierro (LIC)* se puede fijar Wood o Hankins. Las dos quedan en el panel, en el resumen en imagen y en el Excel.
- **Rango del LIC** (texto de referencia, no veredicto): 3,2–7 leve, 7–15 moderada, > 15 mg Fe/g grave.
- **Referencia de la grasa**, como texto: PDFF ≥ 6,4 % grado ≥ 1, ≥ 17,4 % grado ≥ 2, ≥ 22,1 % grado 3: umbrales de alta especificidad en la enfermedad hepática grasa (Tang et al., Radiology 2015).
- La fracción de señal del doble eco **no es PDFF**: no corrige T1 ni T2*. En fase con señal menor que fuera de fase sugiere hierro, y entonces la grasa sale subestimada.
- **Rehacer la medición (0.100.89; en todas las IA desde la 0.100.90)**: con hallazgos en el estudio, el botón de la IA solo abre la revisión. Para medir de nuevo, use la flechita del botón ▸ **Rehacer en el estudio (serie preferida de las Configuraciones)…**: está en **todas** las IA: órganos abdominales, niveles de la columna (en el menú del Genant), cefalometría, índices del cráneo, niveles ganglionares (el botón ganó menú), nódulos, composición, hígado en la RM, enfisema, Genant, lesiones hepáticas, autoPET, BraTS, FLAMeS, médula, aorta, calcio, carga en el PET, próstata y PI-CAI; en la densidad mamaria y en las calcificaciones vasculares es **Rehacer la medición en el estudio (en segundo plano)**. El mismo elemento aparece en la lista del botón IA. La serie es la que la regla de la IA elige en el estudio (Configuración ▸ CAD/IA); si no está en la pantalla, entra en el cuadro activo. Los sugeridos se cambian por los nuevos; si ya hay hallazgos confirmados o corregidos, Ipê pregunta si descarta los antiguos. El elemento "… en esta serie" sigue ejecutándose en la serie del cuadro activo.
- **Clasificación sugerida (0.100.88)**: como en las calcificaciones vasculares de la mama, la ventana Hallazgos de IA tiene la columna **Clasificación** y, al elegir el hallazgo, la tabla de las escalas (pase el ratón para ver de dónde viene cada una). **Grasa**: PDFF < 5 % sin esteatosis; 5–6,4 % esteatosis discreta; y el grado histológico estimado por los umbrales de Tang (6,4 % grado 1 leve; 17,4 % grado 2 moderada; 22,1 % grado 3 acentuada). **Hierro**: por el LIC, < 1,8 sin sobrecarga; 1,8–3,2 por encima de lo normal; 3,2–7 leve; 7–15 moderada; > 15 grave; al lado, el R2\* del hígado y el del bazo. Es una sugerencia: en **Corregir…** se puede cambiar la clasificación, y la frase del informe usa la que valga (la del PDFF va al final de la frase: "… — esteatosis leve (grado 1)"). También en Ipê Web.
- **Qué serie es mapa (0.100.87)**: las imágenes de agua y de grasa del IDEAL IQ ("WATER: IDEAL IQ (R2\*)", "FAT: …") **no** son mapa: el "(R2\*)" es el nombre de la secuencia. Hasta la 0.100.85 se tomaban por el mapa de R2\* y, por venir después de él, el hierro salía de la señal del agua o de la grasa: **rehaga el hierro de los estudios GE con IDEAL IQ medidos antes**. Ahora manda la ImageType; con más de un mapa del mismo tipo, queda el que la ImageType confirma y, entre esos, el de más cortes (el R2\* del IDEAL IQ cubre el hígado; el del STARMAP, 3 cortes).
- **Intercambio agua-grasa (0.100.87)**: el Dixon a veces intercambia agua y grasa en una región (en la cúpula, cerca del pulmón, y con mucho hierro): la fracción se vuelve 100 menos la verdadera (en un estudio, 10 % en el hígado y 92–98 % en la cúpula). Cuando parte del hígado pasa de 60 % y el resto está bien por debajo de 35 %, esos vóxeles salen de la cuenta, con aviso. Con R2\* ≥ 400 s⁻¹ (1,5 T) viene también el aviso de que el PDFF queda menos fiable.
- **Validación (0.100.87)**: en tres RM GE 1,5 T, con el hígado encontrado en series distintas (agua del IDEAL IQ, grasa del IDEAL IQ, el propio mapa de grasa, el agua del LAVA, el doble eco 3D), el PDFF varió como máximo 3 puntos y el R2\* como máximo 26 s⁻¹ (5 %). El R2\* del IDEAL IQ coincidió con un ajuste independiente de los 16 ecos del STARMAP: 53 × 61–65, 183 × 175–185 y 558 × 570 s⁻¹.
- Un mapa de grasa en 0–1000 (algunos fabricantes) se lee como décimas de porcentaje, con aviso. A mano sigue valiendo: una ROI en el propio mapa muestra la media en % (o en s⁻¹ en el de R2*).
- **Rigidez hepática en la elastografía (0.100.94)**: si el estudio tiene elastografía por RM (MR-Touch y afines: el elastograma en Pa, ImageType ELASTOGRAM), la misma cuenta mide la **rigidez** con una ROI automática, sin red neuronal en la medición, como la ROI a mano, corte a corte: el hígado de TotalSegmentator llevado a la cuadrícula del elastograma, **a ≥ 5 mm del borde** (cápsula, fisuras y el desalineamiento entre las apneas), **dentro del área de confianza del aparato** (en GE, el elastograma "STGRYM" tiene el área mala rayada en ajedrez; Ipê compara con el "STGRY" entero), **sin los vasos grandes** (magnitud de la propia adquisición por debajo de la mitad de la del hígado) y sin islas pequeñas; un corte con menos de 1,5 cm² de ROI queda fuera. El número del hallazgo es la **media ponderada por el área** (la del informe), con la mediana, p25–p75, el área medida, los cortes, cuánto del hígado quedó dentro de la confianza y la **heterogeneidad** (CV entre cortes e IQR/mediana). Con dos adquisiciones (p. ej.: *Standard* y *Short T2\**), mide las dos: la de más área va como principal y la otra como número adicional. Rango de referencia, como texto (2D, 60 Hz; Venkatesh, Yin & Ehman, JMRI 2013): < 2,5 kPa normal; 2,5–2,9 normal o inflamación; 2,9–3,5 fibrosis estadio 1–2; 3,5–4,0 estadio 2–3; 4,0–5,0 estadio 3–4; > 5,0 estadio 4 o cirrosis. Queda grabada la serie **"Rigidez hepática: ROI automática"**: el elastograma en color (0–8 kPa), la baja confianza en gris, el hígado en amarillo y la ROI con contorno blanco de borde negro, con el valor de cada corte, para verificar antes de enviar el número al informe.

**Las configuraciones de cada IA en el menú (0.100.90).** Configuración ▸ CAD/IA lista todas las IA, una por elemento; cada una abre su página en la pestaña CAD/IA (automático en la llegada, serie preferida, destinos, opciones).

**Ejecutar en la serie del cuadro (0.100.85).** Cada IA tiene, en el menú del botón IA (o en su botón), el elemento "… en esta serie": se ejecuta en la serie del cuadro activo, aunque no sea la preferida en las Configuraciones. Si da error, el mensaje dice cuál es la serie recomendada para esa IA. El clic en el botón sigue usando la serie preferida (FLAIR, T2 axial, la TC del PET/TC…). En Ipê Web, la pestaña IA deja elegir entre la serie sugerida y la del cuadro.

### Enfisema por lóbulo (0.99.77)

En la TC de tórax, el botón **Enfisema** (o Aplicaciones ▸ Enfisema) separa los cinco lóbulos por la IA y mide, en cada lóbulo, en cada pulmón y en el total, el **%LAA−950** (fracción del volumen por debajo de −950 HU), el **Perc15** (el HU del percentil 15) y el volumen, y dice la distribución (predominio superior, inferior u homogéneo). El resultado va a los Hallazgos de IA, como un hallazgo "Enfisema (%LAA−950)", y las áreas por debajo de −950 HU quedan en una SEG que aparece solo en la serie calculada.

El número depende de la técnica, y la revisión avisa: corte fino (≤ 1,5 mm), filtro suave (B30, STANDARD; un filtro de pulmón o hueso aumenta el ruido y el %LAA), sin contraste y en inspiración plena; la mediana del aire de la tráquea verifica la calibración (cerca de −1000 HU). Use de preferencia la serie fina de filtro suave, si la hay. La referencia (umbral de −950 HU validado por Gevenois et al., 1996; un %LAA por encima de ~5–6 % suele tratarse como enfisema relevante) va como texto al lado, no como veredicto.

**Ruido (0.100.81).** El ruido de un filtro duro pone puntitos por debajo de −950 HU en todo el pulmón e infla el %LAA. Por eso, en una serie ruidosa (filtro duro, o desviación estándar del aire de la tráquea por encima de 30 HU), Ipê aplica un filtro gaussiano leve (σ 0,8 mm) antes del umbral; el hallazgo dice cuándo lo hizo. Se desactiva en **Configuración ▸ CAD/IA ▸ Enfisema**. Desde la 0.100.85 la serie preferida es la de **parénquima/pulmón**: en un estudio con las dos, la de parénquima (con la reducción de ruido) dio el resultado del informe y la de mediastino erró.

### Fractura vertebral — Genant (0.99.77)

En la TC o la RM con la columna torácica o lumbar, el botón **Genant** (o Aplicaciones ▸ Genant) nombra las vértebras (la misma regla de la Columna, con la IA en resolución plena), mide la altura anterior, media y posterior de cada cuerpo y calcula la pérdida de altura: **cuña** (anterior contra posterior), **bicóncava** (media contra posterior) o **aplastamiento** (posterior contra la media de las dos vecinas). De T4 a L5, 20–25 % es grado 1 (leve), 25–40 % grado 2 (moderada) y más de 40 % grado 3 (acentuada), por la clasificación semicuantitativa de Genant (1993).

Cada vértebra con grado 1 o más se vuelve un hallazgo "Fractura vertebral (Genant)" para confirmar, corregir o descartar: deformidad no es sinónimo de fractura (variante, Scheuermann, nódulo de Schmorl, degeneración), así que verifique en el sagital. Un hallazgo de resumen dice cuántas vértebras se midieron; confirmado sin alteradas, entra en el informe como "cuerpos vertebrales sin reducción de altura de 20 % o más". Una vértebra ya revisada no vuelve como sugerencia cuando la IA se ejecuta de nuevo.

### Lesiones hepáticas y carga por segmento (0.99.82)

En la TC o la RM de abdomen, el botón **Lesiones** (o Aplicaciones ▸ Lesiones hepáticas) ejecuta dos tareas abiertas de TotalSegmentator (los ocho segmentos de Couinaud y las lesiones focales del hígado) y mide:

- para cada lesión (hasta 20, las mayores): volumen, mayor diámetro axial, HU medio (TC) y el segmento donde está la mayor parte de ella; cada una se vuelve un hallazgo "Lesión hepática" para confirmar, corregir, descartar o ligar a una lesión del seguimiento;
- en el resumen: número de lesiones, volumen total, **carga** (% del volumen del hígado ocupada por lesión), volumen del hígado y la carga de cada segmento.

El modelo no dice qué es la lesión (quiste, hemangioma, metástasis): es recuento y volumen. Funciona mejor en fase con contraste (portal o hepatobiliar) y corte fino; la revisión avisa cuando no es el caso. Las máscaras (lesiones y segmentos) quedan en una SEG que aparece solo en la serie calculada y en el 3D, en *Estructuras*.

### Calcio coronario — Agatston (0.99.89)

En la TC **sin contraste** (puntuación de calcio o TC de tórax), el botón **Calcio** (o Aplicaciones ▸ Calcio coronario) mide la puntuación de Agatston:

- **Órganos**: TotalSegmentator encuentra el corazón, la aorta y los huesos del tórax (esternón, cartílagos costales, costillas, vértebras). El calcio se busca alrededor del corazón, con 8 mm de margen, que es por donde corren las coronarias; el hueso queda fuera.
- **Agatston**, corte a corte: píxel ≥ 130 HU, lesión de al menos 1 mm² en un corte, peso por el HU máximo (130–199 = 1, 200–299 = 2, 300–399 = 3, ≥ 400 = 4), puntuación = área × peso × grosor ÷ 3 mm. Sale también el **volumen** (mm³). Los cortes finos (hasta 2 mm) se **suman en lonchas de ~3 mm** (media de los HU), como la reconstrucción en que se definió la puntuación: el corte fino aumenta la puntuación. Umbral, menor lesión y la suma de los cortes quedan en Configuración ▸ CAD/IA ▸ Calcio coronario.
- **Vaso sugerido** de cada lesión, por la posición: cerca de la raíz de la aorta y a la izquierda de ella, **TCI**; alrededor del corazón, anterior y a la izquierda **DA**, a la izquierda y atrás **CX**, a la derecha y posteroinferior **CD**. La tarea de las coronarias de TotalSegmentator exige licencia, así que el vaso es una sugerencia: verifique en la SEG (un color por vaso) y corrija.
- **Fuera de la puntuación coronaria**, aparte: el calcio pegado a la **aorta** (incluye la raíz y la válvula aórtica) y el que está a más de 5 mm **dentro del corazón** (válvula, anillo mitral).
- **Resultado**: el Agatston y el volumen totales y por vaso, el **CAC-DRS** (A0 = 0, A1 = 1–99, A2 = 100–299, A3 ≥ 300, con N = número de vasos con calcio) y la categoría de la SCCT/STR para TC de tórax (ninguno, leve, moderado, grave).
- **Hallazgos de IA**: un resumen y un hallazgo por vaso. Para cambiar una lesión de vaso, corrija el Agatston de los dos vasos; descartar un vaso lo saca del total. El texto del informe rehace el total, el CAC-DRS y la categoría con los vasos confirmados o corregidos.

Avisos: con contraste la puntuación **no se mide** (la sangre pasa de 130 HU); TC sin sincronización con el ECG (el movimiento subestima la puntuación); kV distinto de 120; corte fino sin sumar o corte grueso. El percentil por edad y sexo (MESA) no se calcula.

### Aorta: diámetro por segmento (0.99.90)

En la TC de tórax o de abdomen, con o sin contraste, el botón **Aorta** (o Aplicaciones ▸ Aorta) mide el diámetro de la aorta **perpendicular al eje**, de forma automática:

- **Línea central**: TotalSegmentator encuentra la aorta y los puntos de referencia (tronco braquiocefálico, subclavia izquierda, T12, riñones). El programa traza la línea por el medio de la aorta, desde la raíz (cuando la serie abarca el corazón) hasta la bifurcación o el final de la serie, y la ajusta al centro de cada corte perpendicular.
- **Planos perpendiculares** cada 2 mm: en cada uno, el **diámetro máximo**, el **perpendicular** a él y el diámetro por el área.
- **Segmentos** y el mayor diámetro de cada uno: **raíz** (los primeros 15 mm), **ascendente** (hasta el tronco braquiocefálico), **arco** (hasta 10 mm después de la subclavia izquierda), **descendente torácica** (hasta el borde de abajo de T12), **abdominal suprarrenal** (hasta el medio de los riñones) e **infrarrenal**. Sin las ramas del arco, el arco es el tramo de 30 mm de cada lado del punto más alto; en una serie solo del abdomen salen solo los segmentos abdominales.
- **Hallazgos de IA**: un resumen y un hallazgo por segmento; hacer clic lleva al punto del mayor diámetro. La SEG pinta cada segmento de un color. El texto del informe lleva los segmentos confirmados o corregidos ("Aorta ascendente: diámetro máximo 46 × 45 mm, perpendicular al eje, pared externa").

La medición es **de pared externa a externa** (la máscara toma la pared y el trombo). La ACC/AHA (2022) pide la raíz y la ascendente de borde interno a interno, en TC sincronizada con el ECG; sin ECG, la raíz no vale. Las referencias aparecen como texto en el hallazgo, nunca como veredicto: ascendente, arco y descendente ≥ 40 mm suelen informarse como dilatación, y ≥ 55 mm es el umbral de cirugía (ACC/AHA 2022); en la infrarrenal, aneurisma es ≥ 30 mm, con el intervalo de control del ACR (2013) para el tamaño medido.

### Modelos extra: MedSAM2, autoPET, BraTS, FLAMeS y médula

(Los modelos de **investigación** de la próstata quedan aparte, con licencia propia: vea *PI-RADS (RM de próstata)*.)

Cinco IA que no vienen con la segmentación y se instalan una vez, con internet, en **Configuración ▸ CAD/IA ▸ Instalar los modelos extra (MedSAM2, autoPET, BraTS, FLAMeS, médula)…** (la ventana dice lo que ya está listo y lo que falta). Se ejecutan en el mismo entorno de TotalSegmentator, en CPU. Antes de nada, la ventana verifica si el **PyTorch y el torchvision** del entorno combinan y, si no, reinstala los dos juntos: es el arreglo del error *operator torchvision::nms does not exist*, que tumba todo TotalSegmentator (enfisema, órganos, todo) cuando algún `pip install` cambia uno de los dos.

- **Segmentar por la caja (MedSAM2).** Herramienta del botón izquierdo (*Herramienta del botón izquierdo ▸ Medir*): dibuje una caja alrededor de la lesión en un corte de la serie original. MedSAM2 hace el contorno en ese corte y lo propaga hacia arriba y hacia abajo (hasta 60 cortes de cada lado); queda solo la parte contigua al corte de la caja. La ventana que entra en el modelo es la de la pantalla: ajuste la ventana para que la lesión se vea bien antes de dibujar. El resultado se abre en la ventana de la **Segmentación 3D** (método *IA: contorno por la caja*), con volumen, ejes, SUV en el PET, ligar a una lesión del seguimiento y grabar la SEG. Sirve para TC, RM y PET.
- **autoPET (lesiones en el PET-FDG).** Botón **autoPET** (o Aplicaciones ▸ autoPET) en el PET de un PET/TC: el nnU-Net del desafío autoPET II encuentra las lesiones ávidas (deja fuera la captación fisiológica de cerebro, corazón, riñones y vejiga) usando el PET en SUV y la TC del mismo estudio remuestreada en la cuadrícula del PET. Salen el **MTV** (volumen metabólico total), la **TLG** y el SUVmáx, y cada lesión (hasta 20) con volumen, SUVmáx, SUVmedio, SUVpeak y TLG, como hallazgo para verificar: descarte la captación fisiológica que se escape. Necesita el factor de SUV (peso, dosis y horarios en el archivo).
- **BraTS (glioma en la RM).** Botón **BraTS** en la RM de cráneo con T1 poscontraste, T1, T2 y FLAIR: el programa encuentra las cuatro por la descripción, registra la T1, la T2 y la FLAIR en la T1 poscontraste (registro rígido), quita el cráneo (encéfalo de TotalSegmentator) y el SegResNet de MONAI separa la parte **captante**, la **necrosis** y el **edema**, con los volúmenes y el mayor diámetro axial de la parte captante. Un hallazgo para verificar; la revisión avisa cuando el registro quedó con semejanza baja. Es el modelo de ejemplo de MONAI, entrenado en el BraTS 2018: verifique cada parte.
- **FLAMeS (lesiones de sustancia blanca en el FLAIR).** Botón **Lesiones SB** en la RM de cráneo: el programa encuentra el FLAIR del estudio (el de más cortes; el "T1 FLAIR" no sirve), quita el cráneo con SynthSeg y FLAMeS marca las lesiones hiperintensas. Sale un hallazgo con el **número de lesiones**, el **volumen total**, el recuento por región (**periventriculares** (tocan un ventrículo lateral), **yuxtacorticales/corticales** (tocan la corteza), **infratentoriales** (tronco y cerebelo) y **profundas**) y la mayor lesión. Si un estudio anterior del mismo paciente ya pasó por la herramienta, el hallazgo y la frase del informe traen la comparación de número y volumen (no es emparejamiento lesión a lesión). Las lesiones quedan en la serie **Lesiones en el FLAIR · FLAMeS**, coloreadas por región. Modelo de investigación hecho para esclerosis múltiple y para FLAIR 3D: marca cualquier hiperseñal de la sustancia blanca, sin distinguir la causa, y pierde lesiones pequeñas en FLAIR 2D grueso (el programa avisa). La descarga es de 2,4 GB; en CPU el análisis tarda varios minutos.
- **Médula y canal (TotalSpineSeg).** Botón **Médula** en la RM de la columna (de preferencia el sagital T2; sirve cualquier contraste y orientación): TotalSpineSeg segmenta la médula, el canal, los discos y las vértebras, ya con el nombre de cada nivel. Ipê traza la línea central de la médula y mide en cada disco, en el **plano perpendicular a la médula**: el **área**, el diámetro **anteroposterior** y el **transverso**, la **razón de compresión** (AP ÷ transverso), el AP del **canal**, la ocupación del canal por la médula y los índices **MSCC** y **MCC** (Fehlings 1999: 1 − diámetro en el disco ÷ media de los diámetros en los medios de los cuerpos de arriba y de abajo). Cada disco es un hallazgo para verificar; el resumen dice el nivel de mayor MSCC. La médula y el canal quedan en la serie **Médula y canal · TotalSpineSeg**. En un sagital 2D de 3–4 mm, el área y el transverso son aproximados (el programa avisa); el AP, el MSCC y el MCC valen. Verifique siempre el nombre de los niveles. TotalSpineSeg se instala en un **entorno solo suyo** (cerca de 1 GB) y descarga el modelo (2 GB) en el primer uso; necesita unos **8 GB de memoria libres** y tarda varios minutos en CPU.

## CAD, IA y anotaciones de otros sistemas

El botón **CAD/IA** reúne lo que otro programa escribió sobre el estudio: SEG (segmentaciones), GSPS (anotaciones gráficas del aparato o de la estación), SR (hallazgos de CAD/IA) y RTSTRUCT (contornos de radioterapia). El número en el botón dice cuántos objetos tiene el estudio; el menú los lista uno por uno, con *Ir a la imagen* de cada hallazgo.

**En cualquier plano.** Las segmentaciones (SEG, incluidas las de TotalSegmentator: órganos, cefalometría), contornos (RTSTRUCT), niveles de la columna, lesiones segmentadas y líneas de medición automática aparecen también cuando el cuadro se reformatea (MPR sagital, coronal, oblicuo) o en otra serie del mismo estudio en otro plano: la máscara guardada corte a corte se apila en un volumen en milímetros y se corta por el plano del cuadro. **Excepción (0.99.65):** los órganos abdominales y los niveles ganglionares aparecen solo en la serie en que se calcularon (y en sus reconstrucciones): en otra serie el paciente ya se movió, y la misma posición en milímetros no cae en el mismo lugar. Lo que es solo 2D (mamografía, CAD de mamografía, anotaciones gráficas pegadas a una imagen) sigue solo en la imagen de origen.

**Cuánto tarda la apertura, y dónde.** Cada estudio abierto deja una línea en el registro (`Logs\dicomviewer.log`, en la carpeta de datos), por ejemplo *Apertura (MG MAMOGRAFÍA DIGITAL): primera imagen en 0,84 s — base 0,02 · barra 0,21 · tira 0,05 · protocolo 0,30 · ventana 0,03 · estado 0,04 · imagen 0,19*, y una segunda cuando las superposiciones de IA terminan de entrar. Es lo que se puede enviar cuando la apertura parezca lenta. **Desde la 0.100.60**, Ipê Web también deja las suyas en el registro del servidor: *Apertura web (MR, 14 series): primera imagen en 1,92 s — series 0,21 · estudio 0,05 · pantalla 0,10 · protocolo 0,20 · imagen 1,36 | Firefox 160 1628x1064 | 0.100.60* y, con todas las imágenes en el navegador, *…: todo disponible en 12,40 s — 1830 imágenes · 85,2 MB a 9,1 MB/s · decodificación 6,2 ms* (solo modalidad, recuentos y tiempos). En el **modo cliente** (0.100.61), las líneas del Ipê de escritorio también van al registro del servidor, como *Apertura cliente (…) | usuario@ordenador | versión*: la etapa *servidor* es la espera por las primeras imágenes. La tomosíntesis (0.100.60) tiene la cabecera y el lugar de los cortes leídos una vez por archivo y se decodifica sin detener la pantalla. Las imágenes en JPEG-LS (la compresión sin pérdida de Ipê, que guarda toda la mamografía) se leen con el decodificador CharLS, cerca de dos veces más rápido que el anterior en una mamografía, y los decodificadores y módulos de la apertura se cargan unos segundos después de que el programa abre, para que el primer estudio no pague por ellos.

**Las SEG grandes se abren en segundo plano.** Una SEG de órganos de TotalSegmentator tiene miles de cuadros. El estudio se abre primero, con la imagen en la pantalla, y la SEG se lee aparte; la barra de estado muestra *Leyendo las segmentaciones de IA del estudio…* y los colores entran en uno o dos segundos. Reabrir el mismo estudio en la misma sesión de Ipê es inmediato: la SEG ya leída queda guardada en la memoria (hasta ~800 MB de máscaras) mientras el archivo no cambie.

**Leer antes, ver el CAD después.** En Configuración ▸ CAD/IA, *Leer antes, ver el CAD después* hace que las marcas de CAD (el CAD de mamografía y otros CAD SR) empiecen **ocultas** en cada estudio. Lea el estudio y use **CAD/IA ▸ Revelar el CAD** (o la tecla del atajo *Revelar el CAD*): las marcas aparecen y la barra de estado dice cuánto tiempo de lectura hubo antes. Las otras superposiciones (SEG, las IA de Ipê) no cambian.

Hacer clic en el botón muestra u oculta todos. La elección queda guardada por tipo: si usted desactivó las segmentaciones de una IA, nacen ocultas en los próximos estudios, y las anotaciones que el técnico dejó en el aparato siguen apareciendo. Cuando algo nace oculto, la barra de estado avisa cuántos están escondidos.

## Estructuras: editar máscaras (SEG / RTSTRUCT)

En la flechita ▾ del botón **3D** ▸ *Estructuras: editar máscaras* (o en la del botón **CAD/IA**), o simplemente empiece a pintar con la herramienta **Pincel** (*Herramienta del botón izquierdo ▸ Dibujar ▸ Pincel*): el panel se abre solo, con una estructura nueva. Abre una ventana, al lado del visor, para **corregir y organizar** las máscaras del estudio (la lesión que la segmentación 3D o la captura de la dinámica tomó con un vaso pegado, el órgano que la IA contorneó mal) y grabarlas en el estudio.

![El panel Estructuras: la lista, el pincel, los límites de la edición y las correcciones (crecer, encoger, agujeros, interpolar).](estruturas_painel.png){60}

- **Serie de referencia**: la del cuadro activo cuando la ventana se abre. Las estructuras se guardan en su cuadrícula, pero aparecen en **todas las series y planos** del estudio, y el pincel pinta en cualquier cuadro del estudio, en el plano que está en la pantalla (incluido el MPR).
- **Lista**: para cada estructura, *Ver* (mostrar/ocultar; doble clic cambia el color), nombre (editable), tipo (lesión, órgano, otro), volumen en mL, *Bloqueada* y de dónde vino. Abajo, los números de la elegida: volumen, vóxeles, cortes, los tres ejes, media ± desviación, mínimo, máximo, **mediana, percentiles 10 y 90, asimetría, curtosis, entropía y uniformidad** (las definiciones de pyradiomics/IBSI), **mayor diámetro (Feret), esfericidad, alargamiento y aplanamiento**, y cuántas islas separadas tiene. **Copiar los números** pone una fila por estructura, separada por tabulación, en el portapapeles: se pega directo en la planilla. La esfericidad se calcula por la malla de la superficie; en una estructura pequeña (radio de menos de unos 10 vóxeles) es aproximada.
- **Nueva** crea una estructura vacía; **Importar del estudio** trae una lesión guardada, un segmento de SEG (incluidos los de la IA: órganos, cefalometría, implante), un contorno de RTSTRUCT, o todos. Mientras la copia se edita, el original sale de la pantalla; vuelve al cerrar.
- **Pincel / Goma** (botón izquierdo; el derecho sigue con zoom/pan): el círculo alrededor del ratón es el tamaño del pincel (*Radio*, en mm). De forma predeterminada es un disco en el plano de la pantalla (solo el corte que se ve); **Esfera 3D** pinta también los cortes vecinos. **Solo en el rango del clic ±** pinta solo los vóxeles de intensidad parecida a la del punto donde empieza el trazo (el rango es en % del rango de intensidades de la serie): el pincel no sale de la lesión hacia la grasa. El pincel nunca pinta encima de una estructura **bloqueada**: bloquee el órgano y pinte la lesión pegada a él.
- **Límites de la edición** (valen para el pincel, crecer, rellenar agujeros e interpolar: lo que *entra* en la estructura; borrar no está limitado): **Área** en todas partes, *solo dentro de* una estructura (pinte la lesión sin salir del órgano) o *solo fuera de las otras* visibles; **Solo intensidades entre** mín y máx (nada entra fuera del rango, en ninguna herramienta); **Sobrescribir las otras**: lo que la estructura gana sale de las otras no bloqueadas (cada una guarda su deshacer); sin eso, las estructuras pueden superponerse.
- **Corregir la estructura elegida**: **Crecer / Encoger** (margen en mm, en una bola con el espaciado real; *solo en los cortes* no pasa al corte de arriba y de abajo); **Solo la mayor isla** y **Quitar islas menores que** N mL; **Rellenar agujeros** (corte a corte); **Interpolar cortes**: dibuje cada 3 o 4 cortes y los cortes vacíos entre dos dibujados salen por la forma intermedia; **Recortar fuera de** (quita los vóxeles con intensidad fuera del rango); **Unir con / Restar / Cruzar con** otra estructura crea una nueva (por ejemplo, *lesión menos necrosis*). **Deshacer** y **Rehacer** (Ctrl+Z / Ctrl+Y), por estructura.
- **Pestaña “Más herramientas”** (0.100.67). Los botones **Deshacer / Rehacer** quedan debajo de las pestañas y valen para las dos. Las herramientas de ratón de aquí usan el botón izquierdo, como el pincel (activar una desactiva el pincel). Son las ocho herramientas siguientes.
- **Tijera**: dibuje una forma sobre la imagen (*forma libre*, *rectángulo* o *elipse*) y la estructura elegida se corta por ella (**Borrar dentro**, **Borrar fuera** o **Rellenar dentro**), **solo en este corte** o en **todos los cortes** (la forma atraviesa el volumen en la dirección en que usted mira; en un MPR coronal, corta de adelante hacia atrás). Es la manera rápida de quitar un vaso o una costilla que vino junto.
- **Contorno por nivel**: haga clic sobre la lesión y arrastre. Entra la región del corte, ligada al punto, limitada por la línea de igual intensidad que pasa por él (el lado más claro o el más oscuro, el que sea menor; sirve para lesión clara y para lesión oscura). Cerca del borde toma toda la lesión; más hacia dentro, solo el centro. El contorno acompaña al ratón; suelte cuando esté bien. *Borrar en vez de sumar* saca la región de la estructura. En una imagen con mucho ruido el contorno queda picado: prefiera el pincel con *Solo en el rango del clic*.
- **Por el mayor diámetro**: trace el mayor diámetro de la lesión, de borde a borde. Ipê compara la intensidad a lo largo de la línea con la de una cáscara alrededor, encuentra el umbral en el medio y devuelve el **contorno en 3D** en una estructura nueva, con el **mayor diámetro**, el **eje corto** (los dos en el corte en que la lesión es mayor, como en el RECIST) y el **volumen**. ¿Quedó pequeño o grande? Cambie el **Ajuste** (− más ajustado, + más suelto): el contorno se rehace en el acto, sin volver a dibujar. Cuando el contraste con el entorno es poco, aparece un aviso para verificar. Es un contorno por umbral, no una IA: una lesión pegada a una estructura de la misma intensidad se desborda; corrija con la tijera.
- **Hueco (cáscara)**: cambia la estructura por su cáscara, con el grosor elegido, *hacia dentro del borde*, *hacia fuera* (el anillo alrededor de la lesión, para medir el realce perilesional) o *mitad hacia cada lado*.
- **Suavizar**: **mediana** (quita puntas y cierra agujeros pequeños), **apertura** (quita puntas y puentes finos) o **cierre** (cierra agujeros y entrantes), con el radio en mm.
- **Umbral automático (Otsu)**: encuentra solo el corte que mejor separa lo claro de lo oscuro (en la serie o, con el límite *Solo dentro de*, solo dentro de esa estructura) y lo pone en el rango de al lado (*por encima* o *por debajo* del umbral). **Rellenar por el rango** hace que la estructura elegida sea todo lo que está en el rango (respeta el *Área* de los límites: use *Solo dentro de* para no tomar el estudio entero).
- **Dividir islas en estructuras**: cada pedazo suelto se vuelve una estructura (la elegida se queda con el mayor): una lesión por fila, cada una con su volumen. Los pedazos menores que el valor al lado se borran.
- **Crecer desde las semillas**: pinte unos trazos dentro de la lesión en una estructura y, en otra (llámela *Fondo*), unos trazos en lo que está alrededor, en dos o tres cortes. Cada vóxel de la región alrededor de las semillas (hasta el *Margen*) queda con la semilla a la que se liga por el camino de menor cambio de intensidad. Usa todas las estructuras visibles como semillas; las bloqueadas sirven de semilla y no cambian. Si se desbordó, pinte un trazo más de *Fondo* donde se desbordó y ejecute de nuevo. Para deshacer, use *Deshacer* en cada estructura. Después borre el *Fondo*.
- **Grabar SEG**: todas las estructuras en una serie *Estructuras (Ipe)* del estudio, como DICOM SEG (máscara vóxel a vóxel, con el tipo de cada una: lesión u órgano). Va al PACS junto con el estudio y se abre en 3D Slicer y en otros visores, y vuelve a aparecer aquí, por el botón CAD/IA.
- **Grabar RTSTRUCT**: los contornos de radioterapia, corte a corte, que el sistema de planificación lee directo. El contorno sigue el borde de los píxeles (rellenado por los centros, como hacen los planificadores, da la misma máscara); un agujero se vuelve un segundo contorno dentro del primero. Una lesión sale como GTV, un órgano como ORGAN.
- **Actualizar la lesión guardada**: para la estructura que vino de una lesión segmentada, la medición pasa a tener la máscara, el volumen y los ejes corregidos, y es ese volumen el que usa el seguimiento de lesiones.
- **Enviar al informe**: una fila por estructura, con el volumen y los ejes.

Al cerrar con estructuras alteradas y no grabadas, la ventana pregunta si las graba como SEG.

> **Un dibujo grabado en el píxel no es overlay.** Cuando la IA graba el resultado como una serie de imágenes nuevas, no hay cómo desactivarlo: el camino es **Ocultar** la serie con el botón derecho en la lista de series.

## Fusión

Botón **Fusión**: superpone una serie a otra en el cuadro activo (PET sobre la TC, por ejemplo), con opacidad, tabla de colores y límites mínimo y máximo, y la opción de ocultar lo que está por debajo del mínimo.

![PET/TC fusionado: el PET (en SUV, color hierro caliente) sobre la TC, con opacidad, color y ventana del PET en la barra de arriba.](pet_fusao.png)

**Fusionar arrastrando** (0.99.64): arrastre una serie de la tira hasta la **esquina inferior izquierda** del cuadro ("Fusionar encima"): entra como fusión, en colores y con transparencia, en vez de cambiar la serie. Para fusionar lo que otro cuadro muestra (un mapa de la dinámica (SER, realce, cinético…), una fase, el ADC), clic derecho en él ▸ **Cuadro ▸ Fusionar este cuadro sobre…** ▸ el cuadro de destino (ADC sobre la T2, cinético sobre la DWI). La fusión usa las coordenadas del paciente: las series de referenciales distintos reciben el aviso para verificar la alineación.

# Mediciones guiadas

Botón **Índices** (aparece en RM y TC de cráneo; en otros estudios, por el botón **Aplicaciones**). Abre una ventana, encima del visor, con un **guion**: la lista de mediciones, una a la vez, cada una con la herramienta correcta y el plano en que debe hacerse. Al hacer clic en **Medir este paso**, la herramienta del paso va al botón izquierdo; la próxima medición de ese tipo, en cualquier cuadro, se vuelve el valor del paso, y el guion avanza solo. La medición sigue siendo una medición común, visible en el cuadro y en el panel de mediciones.

Guiones de fábrica:

| Guion | Mediciones | Cálculo |
|---|---|---|
| MRPI y MRPI 2.0 | áreas del puente y del mesencéfalo (sagital medio), pedúnculo cerebeloso medio (sagital) y superior (coronal oblicuo), y, para el 2.0, el 3.er ventrículo (tres mediciones) y los cuernos frontales (axial AC-PC) | MRPI = (puente ÷ mesencéfalo) × (PCM ÷ PCS); MRPI 2.0 = MRPI × (3.er ventrículo ÷ cuernos frontales) |
| Índice de Evans | cuernos frontales y diámetro interno del cráneo, en el mismo axial | cuernos ÷ cráneo |
| Ángulo calloso | ángulo en el coronal perpendicular al AC-PC, en la comisura posterior | — |
| Bulbos olfatorios | contorno del bulbo derecho y del izquierdo en cada corte coronal T2 (planimetría) y, opcional, la profundidad del surco olfatorio en el plano tangente a la parte posterior de los globos | volumen = suma de las áreas × distancia entre los cortes (Cavalieri), en mm³; contorno de nuevo en el mismo corte reemplaza el anterior |

El plano y el grosor del corte se verifican y se vuelven **observación** junto al número, no rechazo: una medición en un plano distinto del pedido, o en un corte de más de 3 mm, aparece con ⚠. En estudios con serie 3D, use el MPR para llegar al plano correcto. Los valores de referencia aparecen como texto junto al número, con la fuente: el programa no clasifica. **Copiar el texto** y **Enviar al informe** llevan el resultado en formato de lista, con las referencias entre paréntesis.

## Índices automáticos del cráneo (SynthSeg)

En el botón **Índices** (RM y TC de cráneo): **Índices automáticos (IA, SynthSeg) de esta serie…**. La serie del cuadro activo (de preferencia la 3D T1; sirve cualquier secuencia, incluso poscontraste y 2D, y la TC) va a SynthSeg, que separa ventrículos, hipocampos, amígdalas y el resto del encéfalo. Los cálculos los hace Ipê:

| Medición | Cómo sale |
|---|---|
| Índice de Evans | mayor ancho de los cuernos frontales (ventrículos laterales delante del 3.er ventrículo, los dos lados en el mismo corte) ÷ mayor diámetro intracraneal en el mismo axial |
| 3.er ventrículo | ancho transversal al 25 %, 50 % y 75 % de su longitud; vale la media |
| Ángulo calloso | en el coronal del extremo posterior del 3.er ventrículo (comisura posterior): rectas por las paredes superomediales de los ventrículos laterales |
| Volúmenes | hipocampos (con la asimetría), amígdalas, ventrículos y volumen intracraneal estimado |

La ventana de verificación es la misma de la cefalometría: valor, referencia, de quién es el número, **Ver en el cuadro**, **Medir a mano** y el texto para el informe. Cambiar los cuernos o el diámetro rehace el Evans. Las mediciones se hacen en la segmentación de 1 mm que SynthSeg produce de cualquier serie (incluso de una 2D de 5 mm), en los **ejes del aparato**, no reorientados al AC-PC: con la cabeza inclinada, verifique en el plano correcto. Al abrir los guiones **MRPI y MRPI 2.0**, **Índice de Evans** y **Ángulo calloso**, los pasos que mide la IA ya vienen rellenados ("medido automáticamente (SynthSeg)"); **Rehacer** mide a mano. Puente, mesencéfalo y pedúnculos siguen a mano: SynthSeg no separa el puente del mesencéfalo.

En el estudio quedan la SEG **Encéfalo · SynthSeg** y la imagen **Índices del cráneo: verificación · SynthSeg** (axial de los cuernos, coronal de la comisura posterior y la lista). Automático al llegar: **Configuración ▸ CAD/IA ▸ Índices del cráneo (SynthSeg)…**. Necesita ejecutar una vez más instalar_segmentacao, que añade DIPY y los pesos de SynthSeg.

## T1 sintético de 1 mm (SynthSR)

Para los estudios de cráneo **sin T1 3D** (los protocolos de Parkinson suelen tener solo 2D de 4–5 mm), en que el MPR sale en escalones. En el botón **Índices**: **Crear T1 sintético de 1 mm de esta serie (IA, SynthSR)…**. La serie del cuadro activo (cualquier contraste, orientación y grosor; de preferencia un T1 o un FLAIR) va a SynthSR, que devuelve un volumen isotrópico de 1 mm con contraste de T1. En algunos minutos el estudio gana la serie **T1 sintético 1 mm · SynthSR**, y el programa pregunta si la muestra en el cuadro activo.

La serie nueva está en la misma posición del paciente que la original: se abre en el **MPR**, sincroniza con las otras series, y acepta las mediciones guiadas (**MRPI y MRPI 2.0**, Evans, ángulo calloso) y los **índices automáticos**. Queda solo en este ordenador (no se envía al PACS) y lleva el sello de IA en la miniatura.

**Es una imagen sintética.** La red solo conoce la anatomía normal: las lesiones pueden no aparecer o cambiar de aspecto, y el contraste es calculado, no adquirido. Úsela para **medir la anatomía** (distancias, áreas, volúmenes); **nunca para buscar ni caracterizar lesiones**, y verifique las mediciones frente a las imágenes originales. Con menos de 20 cortes en la serie de origen, o a partir de TC, el resultado es peor, y el programa avisa.

Por el navegador, la herramienta aparece en la pestaña **IA** como **T1 sintético de 1 mm (IA, SynthSR)**. Automático al llegar: **Configuración ▸ CAD/IA ▸ T1 sintético (SynthSR)…**; en ese modo solo se ejecuta en estudios de cráneo que no tienen ninguna serie fina (hasta 1,5 mm). El modelo (53 MB) se descarga una vez, por instalar_segmentacao o en el primer uso.

## Niveles ganglionares cervicales

Botón **Ganglios** (TC de cuello; en otros estudios, por el botón **Aplicaciones**): **Mapa de los niveles ganglionares (IA)**. La serie de TC del cuadro activo va a TotalSegmentator, que encuentra los puntos de referencia; Ipê arma el mapa de los niveles I a VII, derecho e izquierdo, por las reglas de imagen de la estadificación:

| Nivel | Regla usada |
|---|---|
| IA / IB | por encima del borde inferior del hioides y delante del borde posterior de la submandibular; IA entre los vientres anteriores de los digástricos |
| IIA / IIB | del hioides a la base del cráneo, delante del borde posterior del esternocleidomastoideo y lateral a la carótida; IIB detrás del borde posterior de la yugular |
| III | del hioides al borde inferior del cricoides |
| IV | del cricoides a la clavícula |
| VA / VB | detrás del borde posterior del esternocleidomastoideo; VB por debajo del cricoides |
| VI | entre las carótidas, del hioides al tope del manubrio |
| VII | por debajo del tope del manubrio, entre las carótidas |
| retrofaríngeo | por encima del hioides, medial a la carótida |

El rótulo de cada nivel ("IIA D") aparece en cualquier plano, en el medio del pedazo que el corte atraviesa: en el axial, en el coronal reformateado, en el sagital. Con el mapa hecho, una lesión segmentada con la herramienta **Segmentar** recibe el nivel sola (nombre "Ganglio IIA I" y la regla que decidió). Los puntos de referencia quedan en la SEG **Niveles ganglionares · TotalSegmentator** (hioides, cricoides, carótidas, yugulares, esternocleidomastoideos, submandibulares), para verificar. Un punto de referencia que no apareció se vuelve aviso, y su límite no se usa. Automático al llegar: **Configuración ▸ CAD/IA ▸ Niveles ganglionares…**.

## Cefalometría del cavum

Botón **Cefalometría** (aparece en TC de cara, cavum o cuello; en otros estudios, por el botón **Aplicaciones**). Dos caminos:

> **Estado del resultado** (vale también para los índices del cráneo): la ventana dice si el resultado está *automático — aún no verificado*, *editado (\*)* o *aceptado por fulano en tal fecha*. Cada valor cambiado lleva "editado \*" en la columna De quién. **Aceptar el resultado** graba quién y cuándo, con lo que se editó; al reabrir el estudio, la ventana vuelve como usted la dejó.

- **Automática (IA)**: la serie de TC del cuadro activo (de preferencia axial fina) va a TotalSegmentator, que separa paladar blando y duro, naso, oro e hipofaringe, hioides, mandíbula, lengua y las vértebras cervicales. Los cálculos los hace Ipê sobre esas estructuras. Tarda algunos minutos en CPU, y se puede seguir trabajando. Usa la misma instalación de la segmentación abdominal; la primera vez, descarga los modelos de cabeza y cuello (o ejecute de nuevo instalar_segmentacao).
- **A mano (guion)**: la misma ventana, vacía; elija la fila, haga clic en **Medir a mano** y haga la medición en un cuadro (regla; contorno para el área).

| Medición | Cómo sale |
|---|---|
| Área de sección transversal mínima | luz de la vía aérea (por debajo de −400 HU) dentro de la faringe; área en el plano **perpendicular al eje** de la vía aérea, donde es menor, con el lugar (tercio del paladar blando o retrolingual) y el rango (> 100 mm² normal; 50–100 moderadamente reducida; < 50 acentuadamente reducida). Un gráfico muestra el área a lo largo del eje |
| 1. Longitud del paladar blando | sagital medio, de la espina nasal posterior a la punta de la úvula |
| 2. Grosor del paladar blando | el mayor, perpendicular a la longitud |
| 3. Espacio aéreo posterior | menor distancia anteroposterior de la luz en el sagital medio: retropalatal (a la altura del paladar blando) y retrolingual (por debajo de la úvula) |
| 4. Hioides al plano mandibular | línea gonion–mentón (Go–Me) trazada en la mandíbula proyectada en el sagital; distancia perpendicular hasta el borde superior del hioides |
| 5 y 6. Lengua | mayor ancho laterolateral y longitud anteroposterior en el sagital medio |
| 7. Nivel del hioides en la columna | línea horizontal por el cuerpo del hioides contra los cuerpos de C1–C7 (p. ej.: platillo inferior de C3) |

La ventana muestra cada número con la referencia y **de quién es** (automático o editado). Para corregir, escriba en la celda o use **Medir a mano**; **Volver a lo automático** lo deshace. **Referencias…** cambia los valores entre paréntesis (quedan guardados). El texto sale en el formato del informe: el área mínima con el lugar y el rango, y la lista numerada con las referencias.

**Verificar en el cuadro:** las líneas de cada medición quedan en el estudio como superposición en 3D y aparecen en cualquier plano que las contenga: en el sagital medio reformateado (paladar, espacio aéreo, Go–Me y hioides, lengua AP, nivel del hioides), en el axial de la altura (ancho de la lengua), en el oblicuo perpendicular al eje (área mínima). En la ventana, **Ver en el cuadro** (o doble clic en la fila) reformatea el cuadro activo en el plano correcto y va al corte de la medición. Una medición cambiada a mano pierde la línea automática. Las líneas se activan y desactivan en el botón CAD/IA, como las otras superposiciones.

**Automática al llegar:** en **Configuración ▸ CAD/IA ▸ Cefalometría del cavum…** (o en la página CAD/IA de las Preferencias) marque *Hacer automáticamente cuando llegue el estudio*. Vale para TC que llega por la red o se importa, cuando la descripción del estudio contiene uno de los pedazos elegidos (de fábrica: CAVUM, RINOFARINGE, NASOFARINGE, ADENOIDE, APNEIA, RONCO, CEFALOMETRIA, VIA AÉREA). La serie se elige por la lista de preferencia (de fábrica, la axial de partes blandas), con grosor hasta 1,5 mm y al menos 40 cortes. Un estudio a la vez, en segundo plano; lo que se ejecutó aparece en Tareas automáticas. Un estudio que ya tiene la cefalometría no se rehace. Al abrir el estudio, el botón **Cefalometría** abre directamente los números guardados para verificar, sin ejecutar de nuevo. Para rehacer, use Cefalometría ▸ Cefalometría automática (IA) de esta serie.

En el estudio quedan dos series, solo en este ordenador: **Cefalometría · TotalSegmentator** (las estructuras, que se pueden activar y desactivar como las otras segmentaciones) y **Cefalometría: verificación · TotalSegmentator**, una imagen con el sagital medio, las líneas de cada medición, la lista de los números y el perfil del área. Mire esa imagen antes de usar los números: si una línea cayó fuera de lugar, ese número no vale. Las distancias se miden en la posición en que el paciente está en la mesa; una cabeza muy flexionada o extendida cambia la "horizontal" del nivel del hioides.

# Configuración, usuarios y exportación

Todas las ventanas de configuración **se reducen y se maximizan** (botones de maximizar y minimizar en la barra de la ventana); lo que no cabe se desplaza.

## Niveles de la columna y vértebra de transición

**Identificar vértebras y discos de esta serie** (en la flecha del botón **Genant** de la barra, o del botón **Aplicaciones**, o en el clic derecho de la serie en la base de datos, en una TC o RM de columna) da nombre a cada vértebra y disco. Los nombres aparecen en cualquier serie y plano del estudio.

![RM lumbar con los niveles de la columna marcados por la segmentación, incluida la vértebra de transición (S1 lumbarizada).](rm_coluna_niveis.png)

**De dónde viene la numeración**: la ventana final y la lista del objeto dicen cuál se usó:

| Ancla | Cuándo |
|---|---|
| contando desde C2 | la serie abarca C2 y no falta ninguna vértebra hasta el sacro |
| por la última costilla (T12) | TC sin C2: la vértebra de la costilla más baja es T12 (supone 12 pares) |
| C2 en otra serie del estudio | la serie no abarca C2, pero otra del estudio (columna total, mismo Frame of Reference) abarca desde C2 hasta ella |
| por los nombres de la IA | ninguna de las anteriores: verifique |

Con C2 y costillas juntas, la costilla verifica la cuenta: la última costilla en L1 pasa a ser "L1 con costilla", y en T11, "T12 sin costilla" (transición toracolumbar). Si la serie abarca de C7 a la última costilla, el número de pares aparece cuando no es 12.

**Transición lumbosacra**: los nombres siguen lumbarizada / sacralizada:

| En la pantalla | Quiere decir |
|---|---|
| **S1 lumbarizada**, sacro como **Sacro (S2)** | seis vértebras de tipo lumbar; el disco de abajo es S1-S2 |
| **L5 sacralizada** | L5 aún separada del sacro, con transición (marcada por usted) |
| **Sacro (L5 sacralizada)** | solo cuatro lumbares libres: L5 está fusionada al sacro; el último disco es L4-L5 |
| **¿L5 transición?** | cinco lumbares, pero con indicio: disco L5-S1 rudimentario (menos de la mitad de los de arriba) o Castellvi sugerido |

**Castellvi** se sugiere por la forma de la última vértebra libre: apófisis transversa con 19 mm o más de altura (I) o apoyada en el ala sacra (II; si es fusión ósea, cambie a III). Necesita que la serie abarque ±45 mm de la línea media: el sagital de RM casi nunca lo abarca, y entonces la ventana dice "no evaluable".

**Clic derecho ▸ Numeración de la columna**:
- **Ajustar la numeración y la vértebra de transición…**: la ventana se abre con la vértebra que estaba bajo el clic. *Esta vértebra es la…* renumera todo a partir de ella; *Transición lumbosacra* (ninguna, L5 sacralizada, L5 fusionada al sacro, S1 lumbarizada) renumera para quedar coherente; *Castellvi* viene con la sugerencia y el motivo. La **frase para el informe** se rehace con cada elección (Copiar / Enviar al informe). **Aplicar** graba en el estudio y registra quién verificó.
- **Un nivel hacia abajo / hacia arriba**: todos los nombres avanzan un nivel. Si alguno saliera de la columna (antes de C1 o después de S2), el programa lo rechaza y lo dice.

**Estudios siguientes del paciente**: la numeración que usted aplicó queda guardada. Si el próximo estudio del mismo paciente sale distinto (por ejemplo, L5 aquí y S1 lumbarizada en el anterior), aparece el aviso con la fecha del estudio anterior.

## El menú Configuración

Todo lo que se configura vive en el menú **Configuración** (y en el botón Configuración de la pantalla inicial), con un submenú por tema: **Visor** (barra y aplicaciones, botones extra, ratón, atajos, presets de ventana, anotaciones, texto sobre la imagen, sincronización), **Protocolos de estudio** (protocolos de visualización, mamografía, dinámica de la mama, dinámicos, regiones del cuerpo), **CAD/IA**, **Monitores** (función, diseño, orden y calibración GSDF), **Red** (nodos DICOM, automatización, servidor central, enlace ipe://), **Impresión** (impresoras DICOM y configuración de impresión), **Base de datos** (importación, carpeta de la base), **Usuarios** y **Sistema** (al abrir el programa, rendimiento, módulos, idioma). Cada elemento abre su propia ventana, solo con ese tema. Los menús Ver, Red, Impresión y Usuario quedan solo con acciones.

![Configuración ▸ Visor ▸ Barra y aplicaciones: en qué estudios aparece cada aplicación en la barra.](config_barra.png){75}

**Hacer clic en el nombre del grupo** (Visor, Protocolos de estudio, CAD/IA, Informes…) abre una ventana solo de ese grupo, con sus etapas en una lista a la izquierda: las páginas de preferencias aparecen allí mismo y se guardan juntas con el OK; las que tienen ventana propia (Barra de herramientas, Nodos DICOM…) muestran un botón **Abrir…**. Hacer clic en un elemento del submenú sigue abriendo solo ese elemento.

La ventana completa, con todas las pestañas, sigue en **Configuración ▸ Todas las preferencias** (Ctrl+,):

| Pestaña | Qué tiene |
|---|---|
| Ratón | qué hacen cada botón, clic y la rueda |
| Atajos de teclado | las más de 80 acciones, con búsqueda y un encabezado que ordena por grupo, por acción o por tecla; de fábrica solo Q, ←, →, F1 y F2. Y qué teclas (Shift / Ctrl / Alt) prestan el botón izquierdo |
| Presets de ventana | ventanas con nombre por modalidad |
| Monitores | función, orden, identificación y la tira de series |
| Rendimiento | caché de imágenes, tope del volumen del MPR, detalle del 3D y tamaño de la lupa |
| Protocolos de visualización | los protocolos con etapas de los estudios que no son mamografía (diseño, series, planos, MIP, ventana, color) |
| Dinámicos | las reglas de juntar y separar series |
| Mamografía | los protocolos con etapas (capítulo 5) |
| General | al abrir el programa, texto y marcas sobre la imagen, botones en la barra del visor, importación e idioma |
| Módulos | activar y desactivar Medicina nuclear, Mamografía, 3D, RM/TC avanzada e Impresión recibida |

**Módulos**: desactive lo que no usa y los botones y servicios de ese módulo desaparecen. **Ningún estudio se borra**: el estudio sigue en la base de datos y se abre como imagen común; volver a activar devuelve todo. Medicina nuclear se lleva los botones de MN y de la fusión PET/TC; Mamografía, los protocolos al abrir (el estudio se abre sin hanging) y la densidad; 3D, el botón 3D (el MPR se queda); RM/TC avanzada, el botón de la dinámica; Impresión recibida, los servidores de impresión (los puertos dejan de recibir), la lista y la configuración de impresión, la película automática de la ecografía y la limpieza; el compositor y el panel de películas siguen. Solo quien tiene el permiso de configurar cambia los módulos.

En Configuración ▸ Visor ▸ *Botones extra en la barra*: cuatro botones (Invertir, Girar y reflejar, Cine, Ocultar datos del paciente) salen de la barra de forma predeterminada y viven en el menú **Más**; desmarcar y marcar allí los mueve entre los dos lugares. La función nunca desaparece: solo cambia de lugar.

## Modo de uso

La primera vez que el programa se abre, pregunta cómo se va a usar. Se puede cambiar después en **Configuración ▸ Usuarios ▸ Modo de uso**.

| Modo | Cómo queda |
|---|---|
| **Solo yo uso este ordenador** | se abre directo, sin pedir usuario y contraseña. Con usuarios ya registrados, entra como el elegido ("Entrar como") o, si hay solo uno, como él |
| **Varias personas usan este ordenador** | cada uno entra con su usuario. La primera vez usted crea ahí mismo al administrador |
| **Este ordenador es el servidor del grupo** | guarda los estudios, los usuarios y las configuraciones y atiende a los otros ordenadores (puerto elegido allí; certificado en Red ▸ Servidor central) |
| **Conectar a un servidor del grupo** | usa la base de datos y los usuarios del servidor; **Probar** verifica la dirección. Entrar o salir de este modo pide reabrir el programa |

**Entrar con la cuenta del sistema.** En los modos de varias personas y de servidor, la casilla *Entrar con la cuenta del sistema sin escribir contraseña* deja que quien abrió el programa con la cuenta de Windows/Linux vinculada a un usuario entre directamente como él. La cuenta de cada uno queda en el registro del usuario (**Cuenta del sistema**, con el botón *Usar la de este ordenador*); una cuenta vacía siempre pide la contraseña, y un usuario desactivado no entra. Cada entrada así queda en el registro de acceso.

### Visible para: del servicio, personal o compartido

Con varias personas (o servidor), el registro de **nodos DICOM**, **identidades**, **servidores de impresión**, **reglas de impresión** y **reglas de la película automática** tiene el campo **Visible para**:

| Elección | Quién lo ve |
|---|---|
| **Todos (del servicio)** | todo el mundo. Solo quien tiene el permiso de configurar crea o cambia |
| **Solo yo** | solo usted |
| **Yo y usuarios elegidos…** | usted y quien usted marque |

- Un elemento nuevo del administrador nace **del servicio**; el de los demás nace **personal**.
- En las elecciones del día a día (con qué nodo buscar, adónde enviar) cada uno ve el del servicio, el suyo y el que le compartieron.
- El **administrador** ve y edita, en la pantalla de configuración, también lo que es personal de los demás (columna *Visible para*: "de fulano"), pero eso no entra en sus elecciones.
- Quien **no** tiene el permiso de configurar abre **Configuración ▸ Red ▸ Nodos DICOM** como **Mis nodos DICOM**: solo nodos e identidades, y solo los suyos se editan.
- Lo que trabaja por el ordenador (el nodo DICOM que recibe, la automatización, las reglas de impresión) usa todos los elementos, sean de quien sean.
- En el modo **Solo yo** el campo no aparece.

### Base de datos personal y compartida

Con varias personas (o servidor), el panel **Ubicaciones** gana el grupo **Base de datos**: *Todo lo que veo*, *Mi base*, *Compartida* y *Compartidas conmigo*. El administrador ve también **Base de fulano (n)** para cada uno que tiene estudios personales.

- El estudio existe **una sola vez** en la base de datos del ordenador: "personal" es una marca. Mover entre las bases no copia imágenes. Informes, mediciones y anotaciones acompañan al estudio.
- **Clic derecho en el estudio ▸ Organizar ▸ Base de datos**: *Mover a mi base (personal)*, *Mover a la compartida*, *Compartir con…* (elegir usuarios) y, para el administrador, *Pasar a la base de…*. Sacar un estudio de la compartida lo esconde de los demás, por eso solo quien configura el ordenador lo hace; para juntar casos, use las listas.
- **Adónde van los estudios nuevos**: lo que llega por la red al AE de una **identidad personal** (el "AE del Dr. Fulano", con *Visible para: Solo yo*) va a la base del dueño; lo que llega al AE del servicio, a la compartida. Lo que **usted** importa o descarga del PACS sigue su elección en **Ubicaciones ▸ clic derecho en una base ▸ Los estudios que importo o descargo van a** (de fábrica, la compartida).
- **El administrador** abre la base personal de cualquiera; abrir esa base y cada estudio de ella queda en el **registro de acceso**. Cuando alguien sale del servicio: clic derecho en *Base de fulano ▸ Pasar la base de fulano a* otro usuario o a la compartida.
- **Atención**: en el mismo ordenador, "personal" esconde el estudio **dentro del programa**, pero los archivos siguen en la carpeta de la base de datos: quien abra la carpeta por el sistema ve las imágenes. Sigilo de verdad solo en el modo servidor.
- La columna **Base de datos** de la lista (Columnas ▾) muestra de qué base es cada estudio.

### Base personal en el servidor o en este ordenador

En el **modo cliente** el panel **Ubicaciones** muestra el **Servidor central** (donde se abre la ventana) y la **Base de este ordenador**. Un clic cambia: la base de este ordenador se abre **sin el servidor** (sin internet, intranet ni VPN) y sirve como base de casos.

- **Clic derecho en el estudio ▸ Base de datos**, mirando el servidor: *Copiar a este ordenador* (queda en los dos) y *Mover a este ordenador* (sale del servidor; solo el dueño o el administrador; un estudio con candado queda copiado). Mirando este ordenador: *Enviar al servidor central…*, a su base personal o a la compartida.
- **Informes, mediciones, anotaciones, imágenes clave, comentarios, etiquetas y el diagnóstico van juntos**, sin borrar lo que ya existe del otro lado. Quedan fuera las lesiones en seguimiento (son del paciente) y las películas. **Las listas de casos van juntas** (desde la 0.99.36): el estudio entra, del otro lado, en la misma lista y en la misma carpeta (creadas si no existen, con el mismo *Visible para* cuando quien lo lleva puede), con nombre amigable, historia, respuesta y notas; traerlo de nuevo no duplica nada. Las listas inteligentes no viajan: el filtro se ejecuta solo del otro lado.
- **Los estudios que importo o descargo van a** gana, en el modo cliente, *mi base en este ordenador*: lo que usted importa va directo aquí y **no sube** al servidor. *Mi base en el servidor* sube ya marcada como suya. Desde la 0.99.36 vale también para lo que **usted descarga del PACS**: el estudio nuevo queda en la base de este ordenador y no sube; si está abierto en una pestaña, cambia de lugar cuando la pestaña se cierra.
- **Llevar una base entera al servidor** (el ordenador que pasó a ser cliente): clic derecho en la ubicación (este ordenador, un disco externo…) **▸ Enviar esta base al servidor central…**. El administrador puede enviar *tal como están*: cada estudio en la base del dueño. Nada se borra de aquí.
- **El servidor verifica todo**: un estudio de la base personal de otro no aparece en la búsqueda (ni por DICOMweb) y no se entrega a quien lo pide; sacarlo de la compartida pide el permiso de configurar; ponerlo en la base de otro, solo el administrador.
- **Cambiar el modo de uso** no borra ni copia estudios: el programa avisa lo que cambia (por ejemplo, de "varias personas" a "solo yo", los estudios personales pasan a aparecer para quien use el ordenador, y vuelven a ser personales si vuelve).

### Configuraciones personales, compartidas y del servicio

Con varias personas, también las **listas de configuración** tienen tres niveles: **del servicio** (todos), **compartidas con usuarios elegidos** y **personales**: protocolos de visualización, protocolos de mamografía, diseños de la dinámica de la mama, plantillas de hoja de impresión, plantillas de informe y las **listas de casos** (incluidas las inteligentes).

- En las ventanas de siempre nada cambia: cada uno ve las del servicio, las suyas y las compartidas con él. Un elemento **nuevo** nace del servicio cuando lo crea el administrador y personal para los demás.
- **Cambiar un elemento del servicio** sin el permiso de configurar crea una **copia personal** con el mismo nombre, que ocupa el lugar del del servicio **solo para usted**; los demás siguen con el original. Con el permiso, cambia el del servicio. Borrar el del servicio también pide el permiso.
- **Configuración ▸ Usuarios ▸ Configuraciones personales y compartidas…** muestra, en una pestaña por tema, quién ve cada elemento, con los botones *Todos (del servicio)*, *Solo yo*, *Yo y usuarios elegidos…*, *Copiar para mí* y, para el administrador, *Pasar a*. El administrador ve los de todos.
- **Listas de casos**: clic derecho en la lista ▸ **Visible para**. En una carpeta, vale para todo lo que está dentro. La lista personal aparece en cursiva.
- La pestaña **Preferencias** trata de lo que ya era de cada uno (atajos, ratón, presets de ventana, columnas): *Volver al estándar de este ordenador* o, para quien configura, *Hacer de las mías el estándar de este ordenador*.
- Quien ya tenía protocolos propios en las preferencias: en la primera entrada se convierten en elementos personales suyos.
- En el modo cliente todo esto vive en el servidor, que verifica las reglas; en "solo yo" nada cambia.
- **Reglas de automatización** (0.99.36): las búsquedas programadas, previos, enrutamiento, dinámica lista y gestión automática también tienen **Visible para** en el editor de cada regla, y la columna en la lista. Cada uno ve las del servicio, las suyas y las compartidas con él; el administrador ve todas. **Todas se ejecutan**: la automatización trabaja por el ordenador, sea de quien sea la regla. Lo que una búsqueda programada descarga va a la base **compartida**; en una búsqueda personal, la casilla *Los estudios nuevos descargados por esta búsqueda van a la base personal del dueño* los manda a la base de quien es la regla. El **previo** descargado por causa de un estudio (prebúsqueda o por la tira de previos) va a la **misma base** del estudio actual. En la ventana *Configuraciones personales y compartidas*, la pestaña **Reglas de automatización** cambia quién la ve y hace *Copiar para mí* (la copia nace en pausa, para no ejecutarse dos veces). La automatización es de cada ordenador: en el modo cliente las reglas quedan en el ordenador, no en el servidor.
- **Referencias** de la cefalometría y de los índices del cráneo (el texto entre paréntesis en el informe): en el botón **Referencias…**, *Vale para*: **Solo para mí** (las suyas, encima de las del ordenador) o **Todos de este ordenador** (pide el permiso de configurar). La pestaña *Preferencias* de la ventana de configuraciones personales también las devuelve al estándar.
- **Llamada externa** (RIS, enlace `ipe://`, API): abre solo lo que quien está conectado podría abrir por la lista. Un estudio de la base personal de otro usuario no se abre ni se busca de nuevo en el PACS (la barra de estado dice por qué); el administrador lo abre, y queda en el registro de acceso.
- Lo que no tiene tres niveles, a propósito: las opciones de exportación ya son de cada usuario (con el estándar del ordenador por debajo); las listas inteligentes son listas de casos y ya tienen *Visible para*.

## Usuarios y permisos

Botón **Usuarios**. Cuatro perfiles de fábrica (Administrador, Médico, Residente y Técnico) y la tabla de permisos de cada perfil la edita el administrador.

| Permiso | Qué permite |
|---|---|
| Abrir y ver estudios | lo básico |
| Importar archivos | importación |
| Buscar en el PACS / Descargar del PACS | consulta y descarga (y la Gestión DICOM) |
| Enviar a nodos DICOM | enviar estudios hacia fuera |
| Exportar | CD, memoria USB, imágenes |
| Exportar con datos del paciente | sin eso, toda exportación sale anonimizada |
| Borrar estudios | eliminación |
| Listas de casos y modo reunión | la base de casos |
| Películas e impresión | compositor, impresora DICOM y el panel de películas |
| Escribir informes / Firmar informes | borrador y liberación, separados |
| Configurar red, automatización y preferencias | las ventanas de configuración |
| Gestionar usuarios y ver el registro de acceso | administración |

**Olvidé el usuario o la contraseña (0.100.113).** En la ventana de inicio de sesión, haga clic en *Olvidé el usuario o la contraseña…*:

- En el Ipê de **uso único** ("Solo yo uso este ordenador"), aparece la lista de usuarios: elija el suyo y grabe una contraseña nueva. Quien abrió Ipê ya está en la cuenta de Windows dueña de la base de datos, así que la contraseña no protege nada más allá de eso. El cambio queda en el registro de acceso.
- Con **varias personas** o en el **servidor**, un administrador la restablece en **Usuarios**. Si nadie recuerda la contraseña de administrador, abra una ventana de comandos en la carpeta de Ipê y ejecute `ipe-cli redefinir-senha` (lista los usuarios) y `ipe-cli redefinir-senha <usuario>` (pide la contraseña nueva dos veces).
- En el **cliente**, la contraseña es del servidor central: su administrador la restablece.

Para empezar de cero en un ordenador sin estudios, cierre Ipê y borre la carpeta `%LOCALAPPDATA%\DicomViewer` (configuraciones, base de datos y estudios). En la próxima apertura Ipê pregunta de nuevo el modo de uso.

## Exportar

**Archivo ▸ Exportar…** (o el botón **Exportar**) exporta el estudio abierto o los seleccionados en la base de datos:

![Exportar: DICOM (con DICOMDIR y visor en el navegador) o imágenes, con la anonimización de las copias.](exportar.png){65}

- **DICOM**: carpeta, CD o memoria USB, con DICOMDIR y, si quiere, un visor que se abre en el navegador (completo, con mediciones, valores, ROIs y MPR; o ligero). Puede salir comprimido en .zip.
- **Imágenes**: JPG o PNG, con formato, calidad, ventana (la del archivo o la del cuadro actual), intervalo y tamaño máximo.

**Elegir las series**: marque la casilla debajo de *Qué exportar* y aparece la lista de cada estudio con sus series; desmarque las que no deben salir (por ejemplo el topograma, las series de dosis o las segmentaciones). Vale para DICOM, imágenes y la copia anonimizada; un estudio sin ninguna serie marcada queda fuera.

**Los hallazgos de IA van juntos (0.100.86)**: en la exportación DICOM (carpeta, .zip o copia anonimizada en la base) los hallazgos de IA de los estudios (el %LAA del enfisema, la composición en L3, los nódulos, con el estado de cada uno: sugerido, confirmado, corregido, descartado) salen en un archivo `IPE_ACHADOS.json` en la raíz. Al importar esa carpeta en otro Ipê, vuelven a la base de datos, ligados al estudio y a la serie (por los UIDs nuevos, cuando la exportación genera UIDs nuevos). Anonimizado, no salen el nombre de quien revisó ni la nota libre. Solo van los hallazgos de las series que salieron.

La anonimización es una opción de la ventana, y obligatoria para quien no tiene el permiso de exportar con datos del paciente.

**Pacientes distintos en un solo paquete**: exportar identificado, en un CD/memoria USB con visor o en un .zip, estudios de pacientes distintos pregunta antes, mostrando dónde nombre e ID no coinciden: es el paquete que se entrega a un paciente con el estudio de otro dentro. Carpeta suelta, imágenes JPG/PNG y copias anonimizadas no preguntan (juntar casos para clase o investigación es uso normal).

**Las series derivadas dicen de dónde vinieron**: toda serie que Ipê graba a partir de otra (reconstrucción, MIP, mapa de la dinámica, captura) lleva en *Derivation Description* la versión del programa y los parámetros (plano, grosor y modo, paso, píxel, orientación y serie de origen; en el mapa, las fases y los umbrales) y en *Source Image Sequence* las imágenes de origen (hasta 300 por imagen, espaciadas por igual cuando hay más; la descripción dice cuántas de cuántas).

### Anonimizar

Clic derecho en un estudio, o en varios, y **Herramientas ▸ Anonimizar una copia de este estudio…**. La ventana se abre ya marcada para anonimizar, y hay tres destinos: DICOM, Imágenes, o **Copia anonimizada en mi base** (se vuelve otro estudio en la lista, y nada sale de la máquina).

| Elección | Qué ocurre |
|---|---|
| Nombre e ID | texto libre; `{n}` se vuelve el número (ANON001, ANON002…). En la copia en la base la numeración continúa desde donde se detuvo, para que dos copias no se vuelvan el mismo paciente |
| Mantener sexo / edad | el nacimiento siempre sale; edad y sexo son opcionales |
| Mantener fechas del estudio | sin eso, las fechas salen en blanco |
| Mantener descripciones | descripción del estudio y de la serie (en algunos servicios contienen nombre) |
| Mantener institución | nombre y departamento |
| Quitar etiquetas privadas | todo lo que el fabricante añadió fuera del estándar |
| Generar UIDs nuevos | obligatorio (y bloqueado) en la copia en la base: con los mismos UIDs caería dentro del original |
| Texto grabado en la imagen | franja negra: automático (ecografía e imágenes marcadas), franja superior, o no tocar los píxeles |

> **Anonimizar es copiar.** Los archivos del original no se tocan. La copia en la base aparece con origen *Anonimizado* y la limpieza automática no la borra: solo existe aquí. Vale la pena verificar las imágenes: en ecografía el nombre a veces queda dentro del área de la imagen.

## Las tablas

En toda tabla del programa la división entre columnas se arrastra, y hacer clic en el encabezado ordena donde eso tiene sentido.

## Limitaciones conocidas

- El JPG/PNG exportado no borra el texto grabado en la imagen ni aplica el giro.
- El registro entre estudios es rígido (rotación y traslación), no deformable.
- El 3D se ejecuta en la CPU.
- La base de datos de una ubicación en una carpeta de red (recurso compartido de Windows, NAS) no se recomienda: PostgreSQL quiere los datos en un disco de este ordenador. Para dividir la base, use el servidor central.
- En la mamografía, los previos salen solo de la base local.
- El streaming no es bajo demanda: el resto del estudio entra en el orden en que el PACS lo envía.
- La Gestión DICOM es por el botón (no está programada) y no verifica nodos DICOMweb.
- El realce de fondo de la RM de mama aún no separa tejido fibroglandular de grasa.
- La captura de la lesión usa la 2.ª fase como imagen anatómica (no la sustracción ni el mapa coloreado).
- El instalador es solo de Windows y aún no está firmado digitalmente; no hay actualización automática.
- La densidad está validada en 17 mamas de un solo servicio.

# Recetas

Caminos completos, de principio a fin.

## Dejar la mamografía lista en dos monitores

1. Configuración ▸ Monitores ▸ Función, diseño y orden: marque dos pantallas como **Viewer** y ponga el **Orden** 1 y 2. Verifique con **Identificar monitores**.
2. Configuración ▸ Protocolos de estudio ▸ Mamografía ▸ **+ Nuevo**. Nombre "Cribado", La descripción del estudio contiene: vacío, **Activo** marcado.
3. **+ Etapa** "CC": diseño 1 × 2, *En texto:* `CCD x CCE`.
4. **+ Etapa** "MLO": diseño 1 × 2, `MLOD x MLOE`.
5. **+ Etapa** "Actual × previa": diseño 2 × 2, `CCD, CCD ant x CCE, CCE ant`.
6. Abra una mamografía y avance con **→** y **←**; **Q** recorre los cuadrantes.

## Comprobar al final del día si los estudios llegaron al PACS

1. Una vez: registre las modalidades como nodos y, si hace falta, la identidad con el AE que aceptan (capítulo 10).
2. **Gestión** ▸ marque las modalidades ▸ elija el PACS ▸ **Probar el nodo seleccionado** la primera vez.
3. Período **Hoy** ▸ **Comprobar**. Mostrar: **Solo los que tienen problema**.
4. Seleccione los incompletos y ausentes ▸ **Enviar lo que falta al PACS**. El programa comprueba de nuevo después de enviar.
5. **Exportar CSV…** si quiere guardar el registro del día.

## Enviar solo algunas series como otro aparato

1. En la base de datos, seleccione el estudio y, en el panel de series, las series (Ctrl+clic).
2. Clic derecho ▸ **Enviar N serie(s) a** ▸ el nodo ▸ *como* la identidad (OsiriX, por ejemplo).
3. Siga en la cola de transferencias. Para un estudio que aún está solo en el PACS, el mismo menú existe en los resultados de la búsqueda: descarga y envía solo.

## Hacer que el RIS abra el estudio solo en el visor

1. En la estación, ejecute una vez `ipe-cli register-url` (o Red ▸ Registrar enlace ipe://).
2. En Red, verifique el puerto y copie el token si va a usar la API.
3. Registre el PACS como nodo, marque *usar en la búsqueda* y elija C-GET.
4. En el RIS, arme el enlace: `ipe://open?accession={ACC}&janela=viewer`.
5. Pruebe con un accession que no esté en la base de datos: el estudio debe abrirse mientras se descarga.

## Conectar con un Orthanc por DICOMweb

1. Pida la base del DICOMweb (algo como `http://servidor:8042/dicom-web`) y un usuario solo de lectura.
2. Configuración ▸ Red ▸ Nodos DICOM ▸ **+ Nuevo**. En **Tipo de conexión**, elija DICOMweb (HTTP).
3. Rellene Nombre, Dirección DICOMweb, Usuario y Contraseña. HTTPS con certificado propio: marque *Aceptar certificado no verificado*.
4. Marque en *Usar en* lo que tenga sentido y pulse **Probar red**.
5. Abra el PACS y busque. La descarga vuelve por la misma conexión: no hace falta registrar nada del lado del servidor.

## Medir una lesión en la RM de mama y guardar la captura

1. Abra el estudio y el botón **Dinámica**; verifique la pre, la de pico y la tardía.
2. Mire el mapa **Cinética**; dibuje una ROI en la lesión para ver la curva.
3. **Segmentar 3D** y haga clic en la lesión. Ajuste la barra del **Umbral** hasta que la región cubra la lesión.
4. **Marcar el pezón** y haga clic en el pezón: la distancia sale en el acto, y vale para las otras lesiones de la misma mama.
5. Póngale un nombre y **Guardar como medición**; después **Guardar captura (SC)…**.
6. En el informe, **Insertar ▾** trae las mediciones y las curvas al texto.

## Montar, imprimir y guardar una película

1. En el estudio, **F1** en cada imagen que quiere en la película, o **F2** para una serie (entera o intervalo).
2. Elija la cuadrícula de la hoja. Para intercambiar dos imágenes, arrastre por el asa ⠿.
3. Ajuste cada imagen con el botón izquierdo (Ratón: Ventana, Mover o Zoom, en el botón derecho de la celda).
4. Anote con flecha o texto; el ratón vuelve solo a la función anterior.
5. Marque **también en el estudio** y **Guardar**; después **DICOM Print…** o **Imprimir…**.
6. El **Panel de películas e impresiones** muestra lo que se imprimió y en cuánto tiempo.

## Montar una sesión de casos

1. **+ Lista**, nombre de la sesión, tipo **Reunión**.
2. Arrastre estudios de la base de datos a la lista (o clic derecho → añadir a la lista).
3. Doble clic en la lista abre el organizador: dé a cada caso un nombre amigable, la historia, la respuesta, notas y etiquetas.
4. **▶ Modo reunión**. Presente con Alt+→; Alt+H muestra la historia y Alt+R revela la respuesta.

## Separar la TC trifásica que viene en una sola serie

1. Abra el estudio, clic derecho en la serie → **separar**.
2. Las fases aparecen como miniaturas propias en la tira. No se escribió nada en la base de datos.
3. En Configuración ▸ Protocolos de estudio ▸ Dinámicos, la regla nació como pendiente: confírmela para que valga en todos los estudios iguales, o déjela en Ignorar.

# Apéndice: los atajos

La lista de atajos viene casi vacía. Solo cinco teclas son de fábrica; todas las demás acciones nacen sin tecla, para que usted elija las suyas en Configuración ▸ Visor ▸ Atajos de teclado. Nada deja de funcionar sin tecla: toda acción está en un menú o en la barra. Un atajo repetido se rechaza con aviso.

## De fábrica

| Tecla | Qué hace |
|---|---|
| Q | Mamografía: zoom por cuadrante de la mama; cada Q va al siguiente, en ciclo |
| → | Mamografía: etapa siguiente del protocolo |
| ← | Mamografía: etapa anterior |
| F1 | en el estudio: la imagen del cuadro va a la película |
| F2 | en el estudio: la serie del cuadro va a la película (entera o intervalo) |

## Fijos (no configurables)

### Programa

| Tecla | Qué hace |
|---|---|
| Ctrl+I | Importar carpeta |
| Ctrl+P | Película / impresión |
| Ctrl+Shift+P | Impresiones |
| Ctrl+Shift+F | Consulta PACS |
| Ctrl+B | Volver a la base de datos |
| Ctrl+, | Todas las preferencias (ventana completa) |
| F1 | Guía del usuario (fuera del estudio; en el estudio es de la película) |
| Ctrl+Q | Salir |

### Modo reunión

| Tecla | Qué hace |
|---|---|
| Alt+→ / Alt+← | caso siguiente / anterior |
| Alt+H | Historia |
| Alt+R | Revelar respuesta |
| F11 | Pantalla completa |

### En el cuadro, siempre

| Tecla | Qué hace |
|---|---|
| ↑ ↓ | recorrer los cortes |
| PgUp PgDn | recorrer 10 cortes |
| Home / End | primera / última imagen |
| 1–9 | presets de ventana |
| 0 | la ventana del archivo |
| Supr | borra la medición seleccionada |
| Esc | cancela lo que se está dibujando |
| Alt + rueda o Alt + ↑↓ | ajuste fino de un cuadro enlazado |

### En la película

| Tecla | Qué hace |
|---|---|
| Ctrl+C / Ctrl+X / Ctrl+V | copiar, cortar, pegar celdas |
| Ctrl+A | seleccionar todas de la hoja |
| Ctrl+Z | deshacer la última anotación |
| Supr | borrar las celdas seleccionadas |
| ↑ ↓ ← → | pasar el corte de la celda |

## Sugerencias, por grupo

Era lo predeterminado hasta la versión 0.64: está aquí para quien quiera repetir el mismo mapa, o parte de él. Los nombres de las acciones son los que aparecen en la ventana de preferencias.

### Herramientas y mediciones

| Tecla sugerida | Qué hace |
|---|---|
| W / Z / P / S | Ventana / Zoom / Desplazar (pan) / Recorrer cortes |
| M | Regla |
| X | Cursor 3D |
| A / Shift+C | Ángulo / Cobb |
| E / Shift+E / G | ROI elíptica / rectangular / poligonal |
| Shift+G | Polilínea |
| Shift+A / T / B | Flecha / Texto / Lápiz |
| V | Intensidad (valor del píxel) |
| Shift+V | Segmentar 3D |
| , y . | imagen anterior / siguiente con medición |

### Imagen

| Tecla sugerida | Qué hace |
|---|---|
| I | Invertir tonos |
| F | Ajustar a la ventana |
| R | Restaurar visualización |
| C | Cine |
| H | Histograma de la imagen (o de la ROI) |
| Alt+R / Alt+Shift+R | Girar 90° a la derecha / a la izquierda |
| Alt+H / Alt+V | Reflejar izquierda ↔ derecha / arriba ↕ abajo |
| U | Lupa |
| Shift+Q | Zoom por cuadrante: anterior |
| Shift+H | Ocultar datos del paciente |
| Shift+I | Mostrar/ocultar CAD/IA |

### Series, MPR y dinámica

| Tecla sugerida | Qué hace |
|---|---|
| [ y ] | serie anterior / siguiente en el cuadro |
| K / Shift+K | marcar imagen clave / mostrar las marcadas |
| Shift+P | Añadir estudio previo |
| Shift+M | MPR activar/desactivar |
| O | MPR oblicuo (dibuje una línea) |
| Alt+1 / Alt+2 / Alt+3 | reconstruir el cuadro activo: axial / coronal / sagital |
| Shift+D | Evaluación dinámica |

### Sincronización

| Tecla sugerida | Qué hace |
|---|---|
| Shift+S | Sincronización automática (mismo estudio) |
| L / Shift+L / Ctrl+L | enlazar cuadros / alternar modo / cambiar grupo |
| Shift+W / Shift+Z | sincronizar ventana / zoom y desplazamiento |
| Shift+R | Líneas de referencia |
| Shift+Y | Tira de series |

### Mamografía, informe y película

| Tecla sugerida | Qué hace |
|---|---|
| Shift+T | Saltar entre 2D y tomosíntesis |
| Shift+B | Contrastada: baja energía ⇄ recombinada |
| Shift+J | Tomosíntesis: siguiente grosor (slab) |
| Alt+I | Implante (corregir la prótesis) |
| Alt+Q | Encuadrar la mama en el cuadro |
| Ctrl+R | Informe del estudio |
| Ctrl+Alt+F | Enviar todos los cuadros a la película |
| Ctrl+Shift+L | Seguimiento de lesiones |

## Respuestas de la llamada externa

| Respuesta | Significa |
|---|---|
| aberto | el estudio estaba en la base de datos y se abrió |
| buscando | no estaba; se disparó la búsqueda en los nodos |
| ja_no_banco | pedido de retrieve para un estudio que ya está aquí |
| nao_encontrado | ni en la base de datos ni en los nodos (o no hay nodo configurado) |
| importando | la llamada trajo rutas de archivo |
| erro | falló; el motivo está en el registro |
| recusado | enlace ipe:// sin el token, rechazado (o usted respondió "no" a la pregunta) |

## Seguridad en la red

- **Enlace `ipe://`**: cualquier página abierta en el navegador puede armar un enlace así. Con el token de la API en el enlace (`…&token=<token>`), abre directo; sin el token vale **Red ▸ Llamada externa ▸ Enlace ipe:// sin el token**: *Preguntar antes de abrir* (predeterminado), *Aceptar* o *Rechazar*. Ponga el token en el enlace del RIS para que no pregunte.
- **Nodo DICOM**: el AE Title es solo un nombre que el aparato dice tener: cualquier ordenador de la red puede imitarlo. En **Aceptar conexiones de**, *Solo nodos registrados, comprobando la IP del nodo* solo acepta la conexión que viene de la dirección registrada en el nodo con ese AE.
- **Impresora DICOM**: una impresora nueva acepta *cualquier AE de la red local* (10.x, 172.16–31.x, 192.168.x y VPN 100.64.x): de fuera de la red interna no viene modalidad. Las impresoras que usted ya tenía continúan como estaban; cámbielas en Configuración ▸ Impresión ▸ Servidores.
- **Servidor central**: sin certificado usa HTTP, y usuario y contraseña pasan por la red sin cifrar: úselo solo en una red interna de confianza, o indique un certificado (.pem). Cinco contraseñas erróneas en 10 minutos bloquean ese ordenador por 10 minutos.

> **Una última palabra.** Toda función nueva de este programa tiene modo manual de reserva, avisa cuando no lo logró y muestra el estado en la pantalla. Cuando un número no sale, la respuesta es "no se pudo", nunca un número grande. El programa devuelve un número; la interpretación es del médico.

# Sobre Ipê

## Por qué Ipê

En Brasilia, en medio de la sequía, cuando la ciudad se vuelve parda y el aire se seca, los ipês florecen. Amarillos, morados, blancos, y de repente el paisaje cambia. Me gusta la idea de un programa con ese nombre: algo que nace en medio del trabajo árido del día a día y vuelve más ligera la rutina.

Y hay una coincidencia que solo noté después: *ipê* está en mi nombre. Fil**ipe**.

## Cómo nació

Soy radiólogo, dedicado a la imagen de la mama, y entusiasta de la tecnología. Como muchos radiólogos, migré a macOS por causa de OsiriX y Horos, que durante años fueron la mejor estación de trabajo al alcance de quien informa. Pero siempre quise un programa completo y robusto que funcionara también en Windows y Linux, los sistemas de la mayor parte de los servicios donde trabajamos.

Durante mucho tiempo, ese deseo se quedó en ideas: yo sabía lo que quería en la pantalla, pero no tenía cómo convertirlo en programa por mi cuenta. La inteligencia artificial cambió eso. Hoy describo una necesidad de la práctica ("en la RM de mama, quiero el mapa cinético"; "en un cuadro vacío, déjame elegir la serie") y **Claude**, de Anthropic, trabaja como un programador sénior: escribe el código, lo prueba y explica lo que hizo. Las decisiones clínicas, lo que entra y cómo debe funcionar siguen siendo mías, así como la verificación en estudios reales.

## Sobre hombros de gigantes

Ipê solo existe porque mucha gente compartió su trabajo en código abierto: las bibliotecas de interfaz (Qt/PySide6), de DICOM (pydicom, pynetdicom, GDCM, pylibjpeg), de cálculo (NumPy) y de inteligencia artificial, como **TotalSegmentator**, además de muchas otras enumeradas en *Créditos y licencias*. Por eso Ipê también es abierto (GPL-3.0): para que otros puedan usar, estudiar, mejorar y devolver.

## Lo que no es

Ipê es una herramienta de investigación y enseñanza. **No es un producto sanitario registrado** y no se destina a uso diagnóstico.

— Filipe Ramos Barra

## Créditos y licencias

La lista completa de lo que Ipê usa (bibliotecas, modelos de IA y herramientas), con la licencia y el enlace de cada una, está en **Ayuda ▸ Acerca de Ipê ▸ Créditos y licencias** y en el archivo CREDITOS.md del repositorio. Los autores de TotalSegmentator y de nnU-Net piden que los trabajos que usan esas herramientas citen sus artículos; las citas están en la misma lista.

