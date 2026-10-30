# Ipê

**Visor DICOM para investigación y docencia**, en Python (PySide6), para Windows y Linux. Nació
como estación de lectura de imagen mamaria y creció para cubrir TC, RM, PET/TC, medicina nuclear,
ecografía y radiografía, con red DICOM, placas, impresión e informe.

> **No destinado a uso diagnóstico.** Ipê no es un dispositivo médico registrado. No use sus
> imágenes, medidas o resultados para informar estudios, decidir conductas ni tratar pacientes.

*Otros idiomas: [Português](README.md) · [English](README.en.md) · Historial de versiones:
[CHANGELOG.es.md](CHANGELOG.es.md)*

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
  ZIP o arrastrando; varias ubicaciones; listas de casos; copias anonimizadas; corrección de tags
  que graba una copia; compresión sin pérdida con verificación píxel a píxel.
- **Visor:** varios layouts, varios monitores como una sola estación, protocolos de visualización,
  ventana/nivel, zoom, cine, filtros, escalas de color editables, sincronización automática o
  manual, cursor 3D y líneas de referencia, anotaciones en cuatro niveles, Ctrl+C copia el cuadro
  en alta resolución, estudios anteriores en la tira de miniaturas.
- **Reconstrucciones y 3D:** MPR ortogonal, oblicuo y curvo, slab, volume rendering, superficie,
  recorte, fusión PET/TC, exportación de malla 3D (STL, OBJ, PLY, GLB, 3MF), 4D cardíaco, DSA.
- **Medidas:** regla, ángulo, Cobb, ROIs, ecografía calibrada, panel de medidas, DICOM SR,
  segmentación 3D con volumen y tres ejes perpendiculares.
- **Mama:** mamografía y tomosíntesis por etapas entre monitores, encuadre de la mama, implante,
  densidad mamaria (tres métodos), RM dinámica con MSI/PEI/SER y mapa cinético de 6 colores,
  medida de la lesión y distancias a la piel, al pezón y al pectoral.
- **Medicina nuclear:** NM multi-frame, ANT/POST y media geométrica, ROIs y curvas, renograma,
  vaciamiento gástrico, DISIDA, salivales, DMSA, paratiroides, captación tiroidea y tránsito.
- **Oncología e IA:** seguimiento de lesiones, objetos de CAD/IA (SEG, GSPS, SR, RTSTRUCT),
  segmentación de órganos con TotalSegmentator (opcional), vértebras y discos.
- **Red DICOM:** nodo DICOM y cliente DICOMweb, búsqueda en el PACS, descarga por serie,
  automatización, verificación de envíos al PACS, llamadas externas por enlace `ipe://`, línea de
  comandos o API HTTP local.
- **Placas, impresión e informe:** compositor de placas, impresoras del sistema y DICOM, el programa
  como impresora DICOM, informes con BI-RADS (PDF, DICOM PDF, SR), exportación a DICOM, JPG/PNG y
  un visor HTML completo.
- **Usuarios e idiomas:** uno o varios usuarios con permisos, servidor central opcional;
  portugués, inglés y español, con editor de traducciones.

## Instalación

**Windows:** instale **Python 3.12** (marque *"Add python.exe to PATH"*), haga doble clic en
`instalar.bat` una vez y luego en `executar.bat`. Para generar el instalador de Windows vea
[installer/LEIAME.md](installer/LEIAME.md).

**Linux:**
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
`DICOMVIEWER_HOME`) cambia la carpeta.

## Desarrollo

Código en `src/ipe/`, pruebas en `tests/` (`python -m pytest`; generan estudios sintéticos).
**Nunca suba estudios reales, capturas con datos de pacientes ni bases de datos.**

## Licencia

[GPL-3.0-or-later](LICENSE). © Filipe Ramos Barra. Bibliotecas y modelos de terceros, con licencias y enlaces: [CREDITOS.md](CREDITOS.md).
