# Ipê

**Visor DICOM para investigación y docencia**, en Python (PySide6), para Windows, Linux y macOS
(experimental). Nació
como estación de lectura de imagen mamaria y creció para cubrir TC, RM, PET/TC, medicina nuclear,
ecografía y radiografía, con red DICOM, placas, impresión e informe.

> **No destinado a uso diagnóstico.** Ipê no es un dispositivo médico registrado. No use sus
> imágenes, medidas o resultados para informar estudios, decidir conductas ni tratar pacientes.

*Otros idiomas: [English](README.md) · [Português](README.pt-BR.md) · Historial de versiones:
[CHANGELOG.es.md](CHANGELOG.es.md)*

El programa abre en **inglés** por defecto. El instalador pregunta el idioma (inglés, portugués o
español), y se puede cambiar después en Configuración ▸ Sistema ▸ Idioma.

## ¿Por qué Ipê?

En Brasilia, en plena estación seca, florecen los ipês y el paisaje cambia. Y hay una coincidencia:
*ipê* está en Fil**ipe**. Ipê fue creado por un radiólogo de mama que, como muchos colegas, se pasó a
macOS por OsiriX y Horos, y siempre quiso un programa completo para Windows y Linux. Está escrito con
la ayuda de Claude (Anthropic), que trabaja como programador sénior a partir de los pedidos del autor,
y existe gracias a bibliotecas abiertas de DICOM, cálculo e IA.
[Lea la historia completa](HISTORIA.es.md) · [Créditos y licencias](CREDITOS.md)

---

## Funciones

- **Base de estudios:** base local SQLite con miniaturas y búsqueda; importación de carpetas, CD/DVD,
  ZIP, RAR, 7z o arrastrando; varias ubicaciones; listas de casos; copias anonimizadas; corrección
  de tags que graba una copia; compresión sin pérdida con verificación píxel a píxel; PDFs e imágenes
  adjuntos; estado del estudio y del análisis; lista de trabajo con prioridad y plazo; panel de
  productividad.
- **Visor:** varios layouts, varios monitores como una sola estación, protocolos de visualización,
  ventana/nivel, zoom, cine, filtros, escalas de color editables, sincronización automática o
  manual, cursor 3D y líneas de referencia, anotaciones en cuatro niveles, Ctrl+C copia el cuadro
  en alta resolución, estudios anteriores en la tira de miniaturas.
- **Reconstrucciones y 3D:** MPR ortogonal, oblicuo y curvo, slab, volume rendering, superficie,
  recorte, fusión PET/TC, exportación de malla 3D (STL, OBJ, PLY, GLB, 3MF), 4D cardíaco, DSA,
  registro rígido entre estudios, corrección de movimiento, estructuras 3D grabadas como SEG o
  RTSTRUCT.
- **Medidas:** regla, ángulo, Cobb, ROIs, ecografía calibrada, panel de medidas, DICOM SR,
  segmentación 3D con volumen y tres ejes perpendiculares; índices de cráneo (SynthSeg), niveles
  ganglionares cervicales, cefalometría del cavum; composición corporal en L3, grasa y hierro
  hepáticos en RM, esteatosis, difusión; enfisema por lóbulo, fracturas vertebrales (Genant), calcio
  coronario (Agatston) y diámetros de la aorta por segmento.
- **Mama:** mamografía y tomosíntesis por etapas entre monitores, encuadre de la mama, implante,
  densidad mamaria (tres métodos), RM dinámica con MSI/PEI/SER y mapa cinético de 6 colores,
  medida de la lesión y distancias a la piel, al pezón y al pectoral; fusión arrastrando, mapas de
  color y hallazgos por marcadores; búsqueda activa de pacientes.
- **Medicina nuclear:** NM multi-frame, ANT/POST y media geométrica, ROIs y curvas, renograma,
  vaciamiento gástrico, DISIDA, salivales, DMSA, paratiroides, captación tiroidea y tránsito; PET
  con SUV por peso, masa magra y glucemia, carga tumoral (FDG, PSMA, DOTA) y seguimiento entre
  fechas.
- **Oncología e IA:** seguimiento de lesiones, objetos de CAD/IA (SEG, GSPS, SR, RTSTRUCT),
  segmentación de órganos con TotalSegmentator (opcional), vértebras y discos; hallazgos de IA
  revisables que pueden ir al informe; nódulo pulmonar completo; lesiones hepáticas por segmento;
  modelos extra opcionales (SynthSeg, MedSAM2, autoPET, BraTS).
- **Red DICOM:** nodo DICOM y cliente DICOMweb, búsqueda en el PACS, descarga por serie,
  automatización, verificación de envíos al PACS, llamadas externas por enlace `ipe://`, línea de
  comandos o API HTTP local.
- **Visor web (servidor central):** en el navegador, sin instalar nada, en
  `http(s)://<servidor>:8043/web` (por ahora en la red interna), con pantalla estilo Weasis (barra de
  íconos con una función por botón del ratón, como en el Ipê, menú del botón derecho y paneles
  plegables con pestañas Imagen, Medidas, DICOM y PET): MPR, oblicuo, MIP, medidas con los
  números del Ipê grabadas en la base del servidor, ecografía calibrada, PET/TC con SUV, fusión,
  SUV máximo cerca del cursor y SEG como máscaras; arrastrar series a los cuadros; carga rápida en
  HTJ2K sin pérdida, progresiva y con caché del navegador, con el porcentaje disponible y el botón
  **Carga**. En la 0.99.98: **mamografía** en el protocolo del Ipê en una o **dos pantallas**, **dinámica de mama** (mapas calculados en el navegador, curvas tiempo-intensidad, mapas guardados como fusión) e **informe** en el navegador (plantillas, hallazgos de IA revisados, bloqueo de quién informa, firmar y rectificar).
- **Placas, impresión e informe:** compositor de placas, impresoras del sistema y DICOM, el programa
  como impresora DICOM, informes con BI-RADS (PDF, DICOM PDF, SR), exportación a DICOM, JPG/PNG y
  un visor HTML completo.
- **Usuarios e idiomas:** uno o varios usuarios con permisos, servidor central opcional, perfiles
  por grupo y computadora, actualización por el servidor o desde GitHub en un clic, HTTPS en la red
  interna con certificado propio, OAuth2/OIDC y contraseñas cifradas; portugués, inglés y español,
  con editor de traducciones.

## Instalación

**Windows — instalador:** `Ipe-<versión>-installer.exe` (o el paquete portátil `.zip`), en
[Releases](https://github.com/filipebarra/ipe/releases); instala en el perfil del usuario, sin
administrador, y pregunta el idioma, la carpeta del programa y la de la base.

**Windows — desde el código:** instale **Python 3.12** (marque *"Add python.exe to PATH"*), haga doble clic en
`instalar.bat` una vez y luego en `executar.bat`. Para generar el instalador de Windows vea
[installer/LEIAME.md](installer/LEIAME.md).

**macOS (experimental):** desde los [releases](https://github.com/filipebarra/ipe/releases) (sin Python), desde la
0.100.28: `Ipe-<versión>-macos-arm64.dmg` para Mac con chip Apple (M1 en adelante) o `Ipe-<versión>-macos-x86_64.dmg`
para Mac con Intel. Abra el `.dmg` y arrastre **Ipe** a Aplicaciones. El programa **no está firmado por Apple**: la
primera vez, clic derecho (o Control+clic) ▸ **Abrir** ▸ **Abrir**; si macOS dice que la app "está dañada", ejecute
`xattr -dr com.apple.quarantine /Applications/Ipe.app` en la Terminal. El paquete de macOS es nuevo y se ha usado
mucho menos que los de Windows y Linux. Desde la 0.100.32 los textos muestran las teclas del Mac (⌘, ⌥), los enlaces
`ipe://` abren el programa y **Buscar actualizaciones** instala sola la versión nueva. Límites conocidos: no hay
icono en la barra de menús; la segmentación de órganos no se probó en un Mac real. Si el programa se cierra
solo, envíe `~/Library/Logs/DicomViewer/queda.log`.

**Linux:** desde los [releases](https://github.com/filipebarra/ipe/releases) (sin Python):
- **Debian/Ubuntu:** `sudo apt install ./Ipe-<versión>-linux-amd64.deb` — el comando es `ipe-viewer`, e **Ipê**
  aparece en el menú de aplicaciones.
- **Cualquier distribución:** extraiga `Ipe-<versión>-linux-portable.tar.gz` y ejecute `Ipe/install.sh` (para su
  usuario, sin administrador; `--system` para todos, `--uninstall` para quitar).

Desde el código:
```bash
./instalar.sh
./executar.sh
```

Para probar sin estudios reales: **Ayuda ▸ Generar estudios de prueba (fantomas)**.

## Línea de comandos

```
ipe                                    abre la interfaz
ipe open --accession 123456            abre el estudio por el accession
ipe open --study-uid 1.2.3...          lo abre por el StudyInstanceUID
ipe open --accession 123 --node PACS   si no está en la base, busca en el nodo, descarga y abre
ipe "ipe://open?accession=123"         lo mismo, por el enlace
ipe import D:\ --reference             importa sin copiar
ipe info                               muestra dónde están la base, los archivos y la configuración
ipe register-url                       registra los enlaces ipe:// y dicomviewer://
```

## Dónde están los datos

`ipe info` muestra las rutas. En Windows: `%LOCALAPPDATA%\DicomViewer` (el nombre anterior del
programa, mantenido para quien actualiza). La variable `IPE_HOME` (o la antigua
`DICOMVIEWER_HOME`) cambia la carpeta. En macOS: `~/Library/Application Support/DicomViewer` (datos) y
`~/Library/Logs/DicomViewer` (registros).

## Desarrollo

Código en `src/ipe/`, pruebas en `tests/` (`python -m pytest`; generan estudios sintéticos).
**Nunca suba estudios reales, capturas con datos de pacientes ni bases de datos.**

## Licencia

[GPL-3.0-or-later](LICENSE). © Filipe Ramos Barra. Bibliotecas y modelos de terceros, con licencias y enlaces: [CREDITOS.md](CREDITOS.md).
