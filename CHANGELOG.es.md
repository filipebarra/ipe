# Historial de versiones de Ipê

*El programa se llamó **DicomViewer** hasta la versión 0.99.10. [Volver al README](README.es.md).
El historial completo, con todas las versiones, está en portugués: [CHANGELOG.md](CHANGELOG.md).*

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
