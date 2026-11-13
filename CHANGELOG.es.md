# Historial de versiones de Ipê

*El programa se llamó **DicomViewer** hasta la versión 0.99.10. [Volver al README](README.es.md).
El historial completo, con todas las versiones, está en portugués: [CHANGELOG.md](CHANGELOG.md).*

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
