"""Textos do site do Ipê (GitHub Pages), em inglês, português e espanhol — inglês primeiro.

Cada texto é T(en, pt, es). O site é organizado por tarefa do dia ("o que você quer fazer hoje?"), não por
lista de ferramentas: o Ipê é grande, e cada página mostra só o caminho de uma tarefa, com um vídeo curto,
os passos e onde fica cada coisa no programa.

Vídeos: os clipes curtos (sem som, em laço) ficam em `site/media/clipes/<idioma>/<nome>.mp4`, gravados do
próprio Ipê com exames de exemplo anonimizados. Os tutoriais longos têm um campo `youtube`: vazio, o site toca
o MP4 daqui; com o código do vídeo, mostra o YouTube.
"""
from __future__ import annotations

LINGUAS = ("en", "pt", "es")            # a primeira é a raiz do site
NOME_DA_LINGUA = {"en": "English", "pt": "Português", "es": "Español"}
REPO = "https://github.com/filipebarra/ipe"


def T(en: str, pt: str, es: str) -> dict:
    return {"en": en, "pt": pt, "es": es}


# ----------------------------------------------------------------------------------------------- textos gerais
GERAL = {
    "titulo": T("Ipê — DICOM viewer for research and teaching", "Ipê — visualizador DICOM para pesquisa e ensino",
                "Ipê — visor DICOM para investigación y docencia"),
    "descricao": T(
        "Free and open-source DICOM workstation for Windows, macOS and Linux, with a web viewer, breast imaging, "
        "PET/CT, AI segmentation, reporting and teaching case packs.",
        "Estação de trabalho DICOM livre e de código aberto para Windows, macOS e Linux, com visualizador web, "
        "mama, PET/CT, segmentação por IA, laudos e pacotes de casos para ensino.",
        "Estación de trabajo DICOM libre y de código abierto para Windows, macOS y Linux, con visor web, mama, "
        "PET/TC, segmentación por IA, informes y paquetes de casos para docencia."),
    "menu_tarefas": T("What do you want to do?", "O que você quer fazer?", "¿Qué quiere hacer?"),
    "menu_comecar": T("Get started", "Começar", "Empezar"),
    "menu_videos": T("Videos", "Vídeos", "Vídeos"),
    "video_em_ingles": T("in English", "em inglês", "en inglés"),
    "menu_baixar": T("Download", "Baixar", "Descargar"),
    "hero_titulo": T("A complete DICOM workstation.\nFree, for every system.",
                     "Uma estação DICOM completa.\nLivre, para todos os sistemas.",
                     "Una estación DICOM completa.\nLibre, para todos los sistemas."),
    "hero_texto": T(
        "Ipê opens CT, MR, mammography, PET/CT, nuclear medicine, ultrasound and radiography — with "
        "reconstructions, AI segmentation, reports and a viewer in the browser. Made by a breast radiologist, "
        "open source under GPL-3.0.",
        "O Ipê abre TC, RM, mamografia, PET/CT, medicina nuclear, ultrassom e raios X — com reconstruções, "
        "segmentação por IA, laudos e um visualizador no navegador. Feito por um radiologista de mama, código "
        "aberto sob a GPL-3.0.",
        "Ipê abre TC, RM, mamografía, PET/TC, medicina nuclear, ecografía y radiografía — con reconstrucciones, "
        "segmentación por IA, informes y un visor en el navegador. Hecho por un radiólogo de mama, código "
        "abierto bajo la GPL-3.0."),
    "hero_baixar": T("Download Ipê", "Baixar o Ipê", "Descargar Ipê"),
    "hero_ver": T("See what it does", "Ver o que ele faz", "Ver qué hace"),
    "hero_sistemas": T("Windows · macOS · Linux · any browser", "Windows · macOS · Linux · qualquer navegador",
                       "Windows · macOS · Linux · cualquier navegador"),
    "tarefas_titulo": T("What do you want to do today?", "O que você quer fazer hoje?", "¿Qué quiere hacer hoy?"),
    "tarefas_texto": T(
        "Ipê does a lot. Pick a task: each page shows a short video, the steps and where each thing is.",
        "O Ipê faz muita coisa. Escolha uma tarefa: cada página mostra um vídeo curto, os passos e onde fica cada "
        "coisa.",
        "Ipê hace mucho. Elija una tarea: cada página muestra un video corto, los pasos y dónde está cada cosa."),
    "ver_tarefa": T("See how", "Ver como", "Ver cómo"),
    "passos": T("Step by step", "Passo a passo", "Paso a paso"),
    "recursos": T("What else is here", "O que mais tem aqui", "Qué más hay aquí"),
    "onde": T("Where", "Onde", "Dónde"),
    "videos_relacionados": T("Tutorials", "Tutoriais", "Tutoriales"),
    "proxima": T("Next task", "Próxima tarefa", "Siguiente tarea"),
    "anterior": T("Previous task", "Tarefa anterior", "Tarea anterior"),
    "todas": T("All tasks", "Todas as tarefas", "Todas las tareas"),
    "clipe_legenda": T("Recorded in Ipê with anonymized example studies.",
                       "Gravado no Ipê com exames de exemplo anonimizados.",
                       "Grabado en Ipê con estudios de ejemplo anonimizados."),
    "clipe_pausar": T("Pause", "Pausar", "Pausar"),
    "clipe_tocar": T("Play", "Tocar", "Reproducir"),
    "aviso": T(
        "Not intended for diagnostic use. Ipê is a research and teaching tool, not a registered medical device.",
        "Não destinado a uso diagnóstico. O Ipê é uma ferramenta de pesquisa e ensino, não um dispositivo médico "
        "registrado.",
        "No destinado a uso diagnóstico. Ipê es una herramienta de investigación y docencia, no un dispositivo "
        "médico registrado."),
    "rodape_licenca": T("Open source · GPL-3.0-or-later · © Filipe Ramos Barra",
                        "Código aberto · GPL-3.0-or-later · © Filipe Ramos Barra",
                        "Código abierto · GPL-3.0-or-later · © Filipe Ramos Barra"),
    "rodape_codigo": T("Source code", "Código-fonte", "Código fuente"),
    "rodape_creditos": T("Credits and licenses", "Créditos e licenças", "Créditos y licencias"),
    "rodape_historico": T("Release history", "Histórico de versões", "Historial de versiones"),
    "rodape_guia": T("User guide (PDF, Portuguese)", "Guia do usuário (PDF)", "Guía del usuario (PDF, portugués)"),
    "sugerir_lingua": T("This page is also in English.", "Esta página também está em português.",
                        "Esta página también está en español."),
    "sugerir_ir": T("Switch", "Mudar", "Cambiar"),
    "por_que_titulo": T("Why “Ipê”?", "Por que “Ipê”?", "¿Por qué “Ipê”?"),
    "por_que_texto": T(
        "In Brasília, in the middle of the dry season, the ipê trees bloom and the landscape changes. And there is a "
        "coincidence: ipê is in Fil<b>ipe</b>. Ipê was created by a breast radiologist who moved to macOS because of "
        "OsiriX and Horos and always wanted a complete program for Windows and Linux too. It is written with the "
        "help of Claude (Anthropic), working as a senior programmer on the author's requests — the clinical decisions "
        "and the checking on real studies remain his.",
        "Em Brasília, no meio da seca, os ipês florescem e a paisagem muda. E há uma coincidência: ipê está em "
        "Fil<b>ipe</b>. O Ipê foi criado por um radiologista de mama que migrou para o macOS por causa do OsiriX e do "
        "Horos e sempre quis um programa completo também para Windows e Linux. É escrito com a ajuda do Claude "
        "(Anthropic), que trabalha como programador sênior a pedido do autor — as decisões clínicas e a conferência "
        "em exames reais continuam dele.",
        "En Brasilia, en plena sequía, florecen los ipês y el paisaje cambia. Y hay una coincidencia: ipê está en "
        "Fil<b>ipe</b>. Ipê fue creado por un radiólogo de mama que pasó a macOS por OsiriX y Horos y siempre quiso "
        "un programa completo también para Windows y Linux. Está escrito con la ayuda de Claude (Anthropic), que "
        "trabaja como programador sénior a pedido del autor — las decisiones clínicas y la verificación en estudios "
        "reales siguen siendo suyas."),
    "por_que_mais": T("Read the full story", "Ler a história completa", "Leer la historia completa"),
    "destaques_titulo": T("At a glance", "Em resumo", "En resumen"),
    "videos_titulo": T("Videos", "Vídeos", "Vídeos"),
    "videos_texto": T(
        "Tutorials step by step, with subtitles. Short clips of each task are on the task pages.",
        "Tutoriais passo a passo, com legendas. Os clipes curtos de cada tarefa estão nas páginas das tarefas.",
        "Tutoriales paso a paso, con subtítulos. Los clips cortos de cada tarea están en las páginas de las tareas."),
    "em_breve": T("More tutorials are coming.", "Mais tutoriais em breve.", "Más tutoriales pronto."),
    "assistir_youtube": T("Watch on YouTube", "Ver no YouTube", "Ver en YouTube"),
    "baixar_video": T("Download the video", "Baixar o vídeo", "Descargar el video"),
}

# destaques da página inicial: (número/ícone, texto)
DESTAQUES = [
    ("3", T("systems — Windows, macOS and Linux — plus any browser through Ipê Web",
            "sistemas — Windows, macOS e Linux — e qualquer navegador pelo Ipê Web",
            "sistemas — Windows, macOS y Linux — y cualquier navegador con Ipê Web")),
    ("0", T("cost and nothing to register: open source, GPL-3.0", "custo e nenhum cadastro: código aberto, GPL-3.0",
            "costo y ningún registro: código abierto, GPL-3.0")),
    ("1", T("database for everything, PostgreSQL bundled — nothing to install",
            "banco para tudo, PostgreSQL embutido — nada a instalar",
            "base para todo, PostgreSQL incluido — nada que instalar")),
    ("EN·PT·ES", T("languages, with a translation editor for others", "idiomas, com editor de tradução para outros",
                   "idiomas, con editor de traducción para otros")),
]

# ------------------------------------------------------------------------------------------------------ tarefas
# Cada tarefa: slug, ícone (nome em ICONES do gerador), título, frase, clipe principal, clipes extras, passos
# (lista de T), recursos [(nome, texto, onde)], vídeos (ids de TUTORIAIS).
TAREFAS = [
    {
        "slug": "read",
        "icone": "olho",
        "titulo": T("Read a study", "Ler um exame", "Leer un estudio"),
        "frase": T("Find the study, open it, scroll, adjust the window, measure and compare with priors.",
                   "Ache o exame, abra, role, ajuste a janela, meça e compare com os anteriores.",
                   "Encuentre el estudio, ábralo, desplace, ajuste la ventana, mida y compare con los previos."),
        "clipe": "ler",
        "cartao": "layout",            # imagem do cartão na página inicial (sem isto, a do clipe)
        "extras": [
            ("banco", T("The Database: search by name, ID, accession or description; the series of the selected study "
                        "on the right.",
                        "O Banco de dados: busca por nome, ID, accession ou descrição; à direita, as séries do exame "
                        "escolhido.",
                        "La Base de datos: búsqueda por nombre, ID, accession o descripción; a la derecha, las series "
                        "del estudio elegido.")),
            ("layout", T("Several series side by side, moving together (automatic sync by position in the patient).",
                         "Várias séries lado a lado, andando juntas (sincronização automática pela posição no "
                         "paciente).",
                         "Varias series lado a lado, moviéndose juntas (sincronización automática por la posición en "
                         "el paciente).")),
            ("mpr", T("MPR: the three planes from one CT series, with reference lines.",
                      "MPR: os três planos a partir de uma série de TC, com linhas de referência.",
                      "MPR: los tres planos a partir de una serie de TC, con líneas de referencia.")),
        ],
        "passos": [
            T("In the <b>Database</b>, type part of the name, ID or accession in the search box (use <code>|</code> "
              "for several terms).",
              "No <b>Banco de dados</b>, digite parte do nome, ID ou accession na busca (use <code>|</code> para vários "
              "termos).",
              "En la <b>Base de datos</b>, escriba parte del nombre, ID o accession en la búsqueda (use <code>|</code> "
              "para varios términos)."),
            T("Double-click the study. It opens in its own tab, with the series in the thumbnail strip on the left.",
              "Dê dois cliques no exame. Ele abre numa aba própria, com as séries na tira de miniaturas à esquerda.",
              "Doble clic en el estudio. Se abre en su propia pestaña, con las series en la tira de miniaturas a la "
              "izquierda."),
            T("Mouse wheel: slices. Each mouse button has its own tool — choose it in the toolbar (<b>Window</b>, "
              "<b>Pan</b>, <b>Zoom</b>, <b>Scroll</b>, <b>Ruler</b>…).",
              "Roda do mouse: cortes. Cada botão do mouse tem sua ferramenta — escolha na barra (<b>Janela</b>, "
              "<b>Pan</b>, <b>Zoom</b>, <b>Rolar</b>, <b>Régua</b>…).",
              "Rueda del ratón: cortes. Cada botón del ratón tiene su herramienta — elíjala en la barra "
              "(<b>Ventana</b>, <b>Pan</b>, <b>Zoom</b>, <b>Desplazar</b>, <b>Regla</b>…)."),
            T("Drag a thumbnail onto a viewport to show another series; <b>Layout</b> sets how many viewports.",
              "Arraste uma miniatura para um quadro para mostrar outra série; <b>Layout</b> escolhe quantos quadros.",
              "Arrastre una miniatura a un cuadro para mostrar otra serie; <b>Layout</b> elige cuántos cuadros."),
            T("<b>Priors</b> shows the patient's earlier studies above the strip — click one to compare.",
              "<b>Anteriores</b> mostra os exames antigos do paciente acima da tira — clique para comparar.",
              "<b>Previos</b> muestra los estudios anteriores del paciente sobre la tira — haga clic para comparar."),
            T("<b>Ctrl+C</b> copies the viewport as you see it, in high resolution.",
              "<b>Ctrl+C</b> copia o quadro como está na tela, em alta resolução.",
              "<b>Ctrl+C</b> copia el cuadro tal como se ve, en alta resolución."),
        ],
        "recursos": [
            (T("Measurements", "Medidas", "Mediciones"),
             T("Ruler, angle, Cobb, ROIs with mean and SD, arrow and text; all listed in one panel, exportable to a "
               "spreadsheet and to DICOM SR.",
               "Régua, ângulo, Cobb, ROIs com média e DP, seta e texto; todas num painel, exportáveis para planilha e "
               "para DICOM SR.",
               "Regla, ángulo, Cobb, ROI con media y DE, flecha y texto; todas en un panel, exportables a hoja de "
               "cálculo y a DICOM SR."),
             T("Ruler ▸ (arrow next to it)", "Régua ▸ (setinha ao lado)", "Regla ▸ (flecha al lado)")),
            (T("MPR and 3D", "MPR e 3D", "MPR y 3D"),
             T("Orthogonal, oblique and curved MPR, MIP slabs, volume rendering, STL/OBJ export.",
               "MPR ortogonal, oblíqua e curva, MIP com espessura, volume 3D, exportação STL/OBJ.",
               "MPR ortogonal, oblicuo y curvo, MIP con espesor, volumen 3D, exportación STL/OBJ."),
             T("MPR · 3D", "MPR · 3D", "MPR · 3D")),
            (T("Several monitors", "Vários monitores", "Varios monitores"),
             T("All monitors work as one workstation, with a layout per monitor and hanging protocols.",
               "Todos os monitores como uma só estação, com layout por monitor e protocolos de exibição.",
               "Todos los monitores como una sola estación, con diseño por monitor y protocolos de visualización."),
             T("Monitor", "Monitor", "Monitor")),
            (T("Key images", "Imagens-chave", "Imágenes clave"),
             T("Star the images that matter; they go to the report and are saved as DICOM.",
               "Marque as imagens importantes; elas vão para o laudo e ficam gravadas em DICOM.",
               "Marque las imágenes importantes; van al informe y se guardan en DICOM."),
             T("Key", "Chave", "Clave")),
            (T("Test studies", "Exames de teste", "Estudios de prueba"),
             T("No studies yet? Ipê generates synthetic phantoms to try everything.",
               "Sem exames ainda? O Ipê gera fantomas sintéticos para testar tudo.",
               "¿Sin estudios todavía? Ipê genera fantomas sintéticos para probarlo todo."),
             T("Help ▸ Generate test studies", "Ajuda ▸ Gerar exames de teste", "Ayuda ▸ Generar estudios de prueba")),
        ],
        "videos": [],
    },
    {
        "slug": "mammography",
        "icone": "mama",
        "titulo": T("Read mammography", "Ler mamografia", "Leer mamografía"),
        "frase": T("Hanging protocol step by step, tomosynthesis, breast density and vascular calcifications.",
                   "Protocolo de exibição passo a passo, tomossíntese, densidade mamária e calcificações vasculares.",
                   "Protocolo de visualización paso a paso, tomosíntesis, densidad mamaria y calcificaciones "
                   "vasculares."),
        "clipe": "mamo",
        "extras": [],
        "passos": [
            T("Open the mammogram: it comes up in the breast hanging protocol, with CC and MLO facing each other.",
              "Abra a mamografia: ela já entra no protocolo de mama, com CC e MLO frente a frente.",
              "Abra la mamografía: entra en el protocolo de mama, con CC y MLO enfrentadas."),
            T("The <b>stage</b> list walks through the protocol (4 views, CC, MLO, priors…); the arrows go to the next "
              "stage.",
              "A lista <b>etapa</b> percorre o protocolo (4 incidências, CC, MLO, anteriores…); as setas vão para a "
              "próxima.",
              "La lista <b>etapa</b> recorre el protocolo (4 proyecciones, CC, MLO, previos…); las flechas pasan a la "
              "siguiente."),
            T("With tomosynthesis, switch a viewport to the slices and scroll; the depth indicator shows where you are.",
              "Com tomossíntese, troque o quadro para os cortes e role; o indicador mostra a profundidade.",
              "Con tomosíntesis, cambie el cuadro a los cortes y desplace; el indicador muestra la profundidad."),
            T("<b>Density</b>: the network suggests the category and shows the mask; you confirm or correct.",
              "<b>Densidade</b>: a rede sugere a categoria e mostra a máscara; você confirma ou corrige.",
              "<b>Densidad</b>: la red sugiere la categoría y muestra la máscara; usted confirma o corrige."),
            T("<b>Vessels</b>: vascular calcifications graded with several scales side by side, for you to review.",
              "<b>Vasos</b>: calcificações vasculares graduadas em várias escalas lado a lado, para você revisar.",
              "<b>Vasos</b>: calcificaciones vasculares graduadas con varias escalas lado a lado, para revisar."),
        ],
        "recursos": [
            (T("Quadrant zoom", "Zoom por quadrante", "Zoom por cuadrante"),
             T("Four areas (posterior/anterior × superior/inferior), in all viewports together; also in Ipê Web.",
               "Quatro áreas (posterior/anterior × superior/inferior), em todos os quadros juntos; também no Ipê Web.",
               "Cuatro áreas (posterior/anterior × superior/inferior), en todos los cuadros juntos; también en Ipê Web."),
             T("Q key · Quadrant", "Tecla Q · Quadrante", "Tecla Q · Cuadrante")),
            (T("Two screens", "Duas telas", "Dos pantallas"),
             T("The protocol spreads across monitors, with breast framing and quadrants.",
               "O protocolo se distribui pelos monitores, com enquadramento da mama e quadrantes.",
               "El protocolo se distribuye por los monitores, con encuadre de la mama y cuadrantes."),
             T("Monitor", "Monitor", "Monitor")),
            (T("Batch from a spreadsheet", "Em lote, por planilha", "En lote, desde una hoja"),
             T("Fetch a list of mammograms from the PACS, measure density and calcifications, export to Excel — for "
               "research.",
               "Busca uma lista de mamografias no PACS, mede densidade e calcificações e exporta em Excel — para "
               "pesquisa.",
               "Trae una lista de mamografías del PACS, mide densidad y calcificaciones y exporta a Excel — para "
               "investigación."),
             T("Database ▸ Breast", "Banco ▸ Mama", "Base ▸ Mama")),
            (T("In the browser too", "No navegador também", "También en el navegador"),
             T("Ipê Web shows mammography in the same protocol, on one or two screens.",
               "O Ipê Web mostra a mamografia no mesmo protocolo, em uma ou duas telas.",
               "Ipê Web muestra la mamografía en el mismo protocolo, en una o dos pantallas."),
             T("Ipê Web", "Ipê Web", "Ipê Web")),
        ],
        "videos": [],
    },
    {
        "slug": "breast-mri",
        "icone": "curva",
        "titulo": T("Breast MRI and dynamics", "RM de mama e dinâmica", "RM de mama y dinámica"),
        "frase": T("Synchronized sequences, kinetic map, curves and lesion distances.",
                   "Sequências sincronizadas, mapa cinético, curvas e distâncias da lesão.",
                   "Secuencias sincronizadas, mapa cinético, curvas y distancias de la lesión."),
        "clipe": "rm_mama",
        "extras": [],
        "passos": [
            T("Open the breast MRI: T2, pre-contrast and the phases come up side by side and move together.",
              "Abra a RM de mama: T2, pré-contraste e as fases entram lado a lado e andam juntas.",
              "Abra la RM de mama: T2, precontraste y las fases aparecen lado a lado y se mueven juntas."),
            T("<b>Breast dynamic</b> (in <b>Applications</b>) builds the subtraction, SER/PEI/MSI maps and the 6-colour "
              "kinetic map, in any plane.",
              "<b>Dinâmica da mama</b> (em <b>Aplicações</b>) monta a subtração, os mapas SER/PEI/MSI e o mapa "
              "cinético de 6 cores, em qualquer plano.",
              "<b>Dinámica de mama</b> (en <b>Aplicaciones</b>) arma la sustracción, los mapas SER/PEI/MSI y el mapa "
              "cinético de 6 colores, en cualquier plano."),
            T("Click the lesion for its time-intensity curve; measure it to get the angiovolume and the kinetic "
              "pattern.",
              "Clique na lesão para ver a curva tempo-intensidade; meça para ter o angiovolume e o padrão cinético.",
              "Haga clic en la lesión para ver la curva tiempo-intensidad; mídala para tener el angiovolumen y el "
              "patrón cinético."),
            T("Distances to skin, nipple and pectoralis come with the lesion.",
              "As distâncias à pele, ao mamilo e ao peitoral vêm com a lesão.",
              "Las distancias a la piel, al pezón y al pectoral vienen con la lesión."),
        ],
        "recursos": [
            (T("Your own layouts", "Seus layouts", "Sus diseños"),
             T("Pre-set parameters and layouts (series and colour per viewport) for the dynamic study.",
               "Parâmetros e layouts prontos (séries e cor por quadro) para a dinâmica.",
               "Parámetros y diseños listos (series y color por cuadro) para la dinámica."),
             T("Settings", "Configurações", "Configuración")),
            (T("Diffusion", "Difusão", "Difusión"),
             T("ADC on any MR, not only the breast.", "ADC em qualquer RM, não só na mama.",
               "ADC en cualquier RM, no solo en la mama."),
             T("Applications", "Aplicações", "Aplicaciones")),
        ],
        "videos": [],
    },
    {
        "slug": "pet-oncology",
        "icone": "alvo",
        "titulo": T("PET/CT and oncology", "PET/CT e oncologia", "PET/TC y oncología"),
        "frase": T("Fusion, SUV, MIP in 3D, tumour burden and lesions followed across studies.",
                   "Fusão, SUV, MIP em 3D, carga tumoral e lesões acompanhadas entre exames.",
                   "Fusión, SUV, MIP en 3D, carga tumoral y lesiones seguidas entre estudios."),
        "clipe": "pet",
        "extras": [
            ("pet3d", T("PET MIP in 3D, rotating.", "MIP do PET em 3D, girando.", "MIP del PET en 3D, girando.")),
        ],
        "passos": [
            T("Open the PET/CT. Drag the PET series onto the CT viewport to fuse them.",
              "Abra o PET/CT. Arraste a série do PET sobre o quadro da TC para fundir.",
              "Abra el PET/TC. Arrastre la serie del PET sobre el cuadro de la TC para fusionar."),
            T("SUV by body weight, lean mass or with glucose correction — the maximum SUV near the cursor is shown.",
              "SUV por peso, massa magra ou com correção de glicose — o SUV máximo perto do cursor aparece na tela.",
              "SUV por peso, masa magra o con corrección de glucosa — el SUV máximo cerca del cursor aparece en "
              "pantalla."),
            T("<b>3D</b> ▸ MIP turns the PET into a rotating projection.",
              "<b>3D</b> ▸ MIP transforma o PET numa projeção que gira.",
              "<b>3D</b> ▸ MIP convierte el PET en una proyección que gira."),
            T("<b>Lesions</b> keeps each lesion with its measurements across dates.",
              "<b>Lesões</b> guarda cada lesão com suas medidas ao longo das datas.",
              "<b>Lesiones</b> guarda cada lesión con sus mediciones a lo largo de las fechas."),
        ],
        "recursos": [
            (T("Tumour burden", "Carga tumoral", "Carga tumoral"),
             T("FDG, PSMA and DOTA: MTV, TLG and lesion count, with follow-up.",
               "FDG, PSMA e DOTA: MTV, TLG e número de lesões, com acompanhamento.",
               "FDG, PSMA y DOTA: MTV, TLG y número de lesiones, con seguimiento."),
             T("Applications", "Aplicações", "Aplicaciones")),
            (T("Nuclear medicine", "Medicina nuclear", "Medicina nuclear"),
             T("Renogram, gastric emptying, HIDA, thyroid, parathyroid and more — Ipê returns the numbers.",
               "Renograma, esvaziamento gástrico, HIDA, tireoide, paratireoide e outros — o Ipê dá os números.",
               "Renograma, vaciamiento gástrico, HIDA, tiroides, paratiroides y otros — Ipê da los números."),
             T("Applications", "Aplicações", "Aplicaciones")),
        ],
        "videos": [],
    },
    {
        "slug": "ai",
        "icone": "faisca",
        "titulo": T("AI and segmentation", "IA e segmentação", "IA y segmentación"),
        "frase": T("Organs, vertebrae, interactive segmentation and findings that you review before they count.",
                   "Órgãos, vértebras, segmentação interativa e achados que você revisa antes de valerem.",
                   "Órganos, vértebras, segmentación interactiva y hallazgos que usted revisa antes de que cuenten."),
        "clipe": "orgaos",
        "extras": [
            ("coluna", T("Vertebrae and discs labelled automatically on spine MRI.",
                         "Vértebras e discos identificados automaticamente na RM de coluna.",
                         "Vértebras y discos identificados automáticamente en la RM de columna.")),
        ],
        "passos": [
            T("Install the AI part once (it is separate and large): the installation window shows the progress.",
              "Instale a parte de IA uma vez (é separada e grande): a janela de instalação mostra o andamento.",
              "Instale la parte de IA una vez (es aparte y grande): la ventana de instalación muestra el avance."),
            T("Open a CT and press <b>AI</b>: choose the task (organs, vertebrae, nodules…). It can also run by itself "
              "when a study arrives.",
              "Abra uma TC e aperte <b>IA</b>: escolha a tarefa (órgãos, vértebras, nódulos…). Também pode rodar "
              "sozinha quando o exame chega.",
              "Abra una TC y pulse <b>IA</b>: elija la tarea (órganos, vértebras, nódulos…). También puede correr "
              "sola cuando llega el estudio."),
            T("<b>AI tasks</b> shows what is running, with cancel.",
              "<b>Tarefas de IA</b> mostra o que está rodando, com cancelar.",
              "<b>Tareas de IA</b> muestra lo que está corriendo, con cancelar."),
            T("Results come as masks you can switch on and off (<b>CAD/AI</b>) and as findings to confirm, correct or "
              "discard.",
              "O resultado vem como máscaras que ligam e desligam (<b>CAD/IA</b>) e achados para confirmar, corrigir "
              "ou descartar.",
              "El resultado viene como máscaras que se encienden y apagan (<b>CAD/IA</b>) y hallazgos para "
              "confirmar, corregir o descartar."),
        ],
        "recursos": [
            (T("Organ volumes", "Volume dos órgãos", "Volumen de los órganos"),
             T("A table of organ volumes, saved with the study.", "Uma tabela com o volume dos órgãos, gravada no "
               "exame.", "Una tabla con el volumen de los órganos, guardada en el estudio."),
             T("AI", "IA", "IA")),
            (T("Interactive segmentation", "Segmentação interativa", "Segmentación interactiva"),
             T("Draw a box around a structure and MedSAM2 segments it; edit with the Structures tools.",
               "Desenhe uma caixa em volta da estrutura e o MedSAM2 segmenta; edite com as ferramentas de Estruturas.",
               "Dibuje una caja alrededor de la estructura y MedSAM2 la segmenta; edite con las herramientas de "
               "Estructuras."),
             T("Structures", "Estruturas", "Estructuras")),
            (T("Neuro", "Neuro", "Neuro"),
             T("Evans index, callosal angle, hippocampal volumes, MRPI, synthetic T1 and FLAIR lesions.",
               "Índice de Evans, ângulo calosal, volume dos hipocampos, MRPI, T1 sintético e lesões em FLAIR.",
               "Índice de Evans, ángulo calloso, volumen de los hipocampos, MRPI, T1 sintético y lesiones en FLAIR."),
             T("Applications", "Aplicações", "Aplicaciones")),
        ],
        "videos": [],
    },
    {
        "slug": "reports",
        "icone": "folha",
        "titulo": T("Reports and diagrams", "Laudos e esquemas", "Informes y esquemas"),
        "frase": T("Templates, key images, guide diagrams, PDF and DICOM SR.",
                   "Modelos, imagens-chave, esquemas-guia, PDF e DICOM SR.",
                   "Plantillas, imágenes clave, esquemas guía, PDF y DICOM SR."),
        "clipe": "esquema",
        "extras": [],
        "passos": [
            T("<b>Report</b> opens the report window with templates (CT, MG, MR, PET) and BI-RADS.",
              "<b>Laudo</b> abre a janela do laudo com modelos (TC, MG, RM, PET) e BI-RADS.",
              "<b>Informe</b> abre la ventana del informe con plantillas (TC, MG, RM, PET) y BI-RADS."),
            T("Reviewed AI findings and measurements can go into the text.",
              "Achados de IA revisados e medidas podem entrar no texto.",
              "Hallazgos de IA revisados y mediciones pueden entrar en el texto."),
            T("<b>Diagram</b>: draw on a guide drawing (face, thyroid, breasts, prostate sectors…) and save it in the "
              "study.",
              "<b>Esquema</b>: desenhe sobre um desenho-guia (face, tireoide, mamas, setores da próstata…) e grave no "
              "exame.",
              "<b>Esquema</b>: dibuje sobre un dibujo guía (cara, tiroides, mamas, sectores de la próstata…) y "
              "guárdelo en el estudio."),
            T("Tick <b>Diagrams in the report</b> and <b>Key images</b> to include them; sign to produce the PDF and "
              "the DICOM SR.",
              "Marque <b>Esquemas no laudo</b> e <b>Imagens-chave</b> para incluir; assine para gerar o PDF e o "
              "DICOM SR.",
              "Marque <b>Esquemas en el informe</b> e <b>Imágenes clave</b> para incluirlos; firme para generar el "
              "PDF y el DICOM SR."),
        ],
        "recursos": [
            (T("Your own diagrams", "Seus esquemas", "Sus esquemas"),
             T("Upload a drawing and turn it into a template, in Ipê or in the browser.",
               "Envie um desenho e transforme em modelo, no Ipê ou no navegador.",
               "Suba un dibujo y conviértalo en plantilla, en Ipê o en el navegador."),
             T("Settings ▸ Diagrams", "Configurações ▸ Esquemas", "Configuración ▸ Esquemas")),
            (T("PI-RADS for prostate MRI", "PI-RADS na RM de próstata", "PI-RADS en la RM de próstata"),
             T("Volume and PSA density (ellipsoid or automatic), each lesion on the sector map with T2, diffusion, DCE "
               "and ADC, the v2.1 category, report text and SR. Research AI models install separately, after you "
               "accept their license, and their output is marked “not for diagnosis”.",
               "Volume e densidade do PSA (elipsoide ou automático), cada lesão no mapa de setores com T2, difusão, DCE "
               "e ADC, a categoria do v2.1, o texto do laudo e o SR. Os modelos de IA de pesquisa se instalam à parte, "
               "depois de aceita a licença, e o que sai deles vem marcado “não usar para diagnóstico”.",
               "Volumen y densidad del PSA (elipsoide o automático), cada lesión en el mapa de sectores con T2, "
               "difusión, DCE y ADC, la categoría v2.1, el texto del informe y el SR. Los modelos de IA de investigación "
               "se instalan aparte, tras aceptar su licencia, y lo que sale de ellos viene marcado “no usar para "
               "diagnóstico”."),
             T("Viewer ▸ PI-RADS", "Visualizador ▸ PI-RADS", "Visor ▸ PI-RADS")),
            (T("Films and printing", "Filmes e impressão", "Películas e impresión"),
             T("Film composer; print to paper, PDF or a DICOM printer; Ipê can also receive films from modalities.",
               "Compositor de filmes; impressão em papel, PDF ou impressora DICOM; o Ipê também recebe filmes dos "
               "equipamentos.",
               "Compositor de películas; impresión en papel, PDF o impresora DICOM; Ipê también recibe películas de "
               "los equipos."),
             T("Film · Prints", "Filme · Impressões", "Película · Impresiones")),
        ],
        "videos": [],
    },
    {
        "slug": "teaching",
        "icone": "capelo",
        "titulo": T("Teach with cases", "Ensinar com casos", "Enseñar con casos"),
        "frase": T("Case lists, meeting mode and case packs that open in any browser.",
                   "Listas de casos, modo reunião e pacotes de casos que abrem em qualquer navegador.",
                   "Listas de casos, modo reunión y paquetes de casos que abren en cualquier navegador."),
        "clipe": "web_caso",
        "extras": [],
        "passos": [
            T("Select the studies in the Database (Ctrl+click) ▸ right-click ▸ <b>Organize ▸ Add to list ▸ New "
              "list…</b>",
              "Selecione os exames no Banco (Ctrl+clique) ▸ botão direito ▸ <b>Organizar ▸ Adicionar à lista ▸ Nova "
              "lista…</b>",
              "Seleccione los estudios en la Base (Ctrl+clic) ▸ botón derecho ▸ <b>Organizar ▸ Agregar a la lista ▸ "
              "Nueva lista…</b>"),
            T("Right-click the list ▸ <b>Organize list</b>: case name, history, answer, report, biopsy, teaching notes "
              "and the series to show.",
              "Botão direito na lista ▸ <b>Organizar lista</b>: nome do caso, história, resposta, laudo, biópsia, "
              "notas de ensino e as séries a mostrar.",
              "Botón derecho en la lista ▸ <b>Organizar la lista</b>: nombre del caso, historia, respuesta, informe, "
              "biopsia, notas docentes y las series a mostrar."),
            T("Open each study and mark the findings (arrow, text, ruler): they appear only when the student asks for "
              "the result.",
              "Abra cada exame e marque os achados (seta, texto, régua): eles só aparecem quando o aluno pede o "
              "resultado.",
              "Abra cada estudio y marque los hallazgos (flecha, texto, regla): solo aparecen cuando el alumno pide el "
              "resultado."),
            T("Right-click the list ▸ <b>Export case pack</b>: a folder with the anonymized cases and the viewer "
              "inside. Hand it over on a USB stick or copy it to a website.",
              "Botão direito na lista ▸ <b>Exportar pacote de casos</b>: uma pasta com os casos anonimizados e o "
              "visualizador dentro. Entregue num pen drive ou copie para um site.",
              "Botón derecho en la lista ▸ <b>Exportar paquete de casos</b>: una carpeta con los casos anonimizados y "
              "el visor dentro. Entréguela en un pendrive o cópiela a un sitio web."),
        ],
        "recursos": [
            (T("Meeting mode", "Modo reunião", "Modo reunión"),
             T("Present a list case by case, hiding the answer until you reveal it.",
               "Apresente uma lista caso a caso, escondendo a resposta até você revelar.",
               "Presente una lista caso por caso, ocultando la respuesta hasta revelarla."),
             T("Lists ▸ Meeting mode", "Listas ▸ Modo reunião", "Listas ▸ Modo reunión")),
            (T("Smart lists", "Listas inteligentes", "Listas inteligentes"),
             T("Lists that fill themselves by a filter (modality, description, tags…).",
               "Listas que se preenchem sozinhas por um filtro (modalidade, descrição, tags…).",
               "Listas que se llenan solas por un filtro (modalidad, descripción, etiquetas…)."),
             T("Lists", "Listas", "Listas")),
            (T("Opens anywhere", "Abre em qualquer lugar", "Abre en cualquier lugar"),
             T("The pack has launchers for Windows, Mac and Linux; nothing is installed and nothing leaves the "
               "computer.",
               "O pacote tem lançadores para Windows, Mac e Linux; nada é instalado e nada sai do computador.",
               "El paquete tiene lanzadores para Windows, Mac y Linux; no se instala nada y nada sale del equipo."),
             T("“Abrir casos”", "“Abrir casos”", "“Abrir casos”")),
        ],
        "videos": ["curso"],
    },
    {
        "slug": "server-web",
        "icone": "nuvem",
        "titulo": T("Server, PACS and Ipê Web", "Servidor, PACS e Ipê Web", "Servidor, PACS e Ipê Web"),
        "frase": T("One database for the whole team and a viewer in the browser, on a computer or a phone.",
                   "Um banco para a equipe toda e um visualizador no navegador, no computador ou no celular.",
                   "Una base para todo el equipo y un visor en el navegador, en la computadora o el teléfono."),
        "clipe": "web",
        "extras": [
            ("web_celular", T("Ipê Web on a phone.", "O Ipê Web no celular.", "Ipê Web en el teléfono.")),
        ],
        "passos": [
            T("Run Ipê as the central server on one machine (Windows or Linux; <code>ipe server</code> runs without a "
              "window).",
              "Rode o Ipê como servidor central numa máquina (Windows ou Linux; <code>ipe server</code> roda sem "
              "janela).",
              "Ejecute Ipê como servidor central en una máquina (Windows o Linux; <code>ipe server</code> corre sin "
              "ventana)."),
            T("On each workstation, point Ipê to the server: same database, users and settings for everyone.",
              "Em cada estação, aponte o Ipê para o servidor: mesmo banco, usuários e configurações para todos.",
              "En cada estación, apunte Ipê al servidor: misma base, usuarios y configuración para todos."),
            T("In any browser, open <code>https://&lt;server&gt;:8043/web</code> and log in with the Ipê user — "
              "measurements made there show up in Ipê and vice versa.",
              "Em qualquer navegador, abra <code>https://&lt;servidor&gt;:8043/web</code> e entre com o usuário do "
              "Ipê — as medidas feitas lá aparecem no Ipê e vice-versa.",
              "En cualquier navegador, abra <code>https://&lt;servidor&gt;:8043/web</code> e ingrese con el usuario "
              "de Ipê — las mediciones hechas allí aparecen en Ipê y viceversa."),
            T("Add your PACS and modalities as DICOM nodes (<b>PACS</b>): search, download, and send.",
              "Cadastre o PACS e os equipamentos como nós DICOM (<b>PACS</b>): buscar, baixar e enviar.",
              "Registre el PACS y los equipos como nodos DICOM (<b>PACS</b>): buscar, descargar y enviar."),
        ],
        "recursos": [
            (T("DICOM management", "Gestão DICOM", "Gestión DICOM"),
             T("Checks that the studies from the modalities reached the PACS and sends what is missing.",
               "Confere se os exames dos equipamentos chegaram ao PACS e envia o que faltou.",
               "Verifica que los estudios de los equipos llegaron al PACS y envía lo que falta."),
             T("Management", "Gestão", "Gestión")),
            (T("Users and permissions", "Usuários e permissões", "Usuarios y permisos"),
             T("Profiles for doctors, technicians and administrators; HTTPS with Ipê's own certificate.",
               "Perfis para médicos, técnicos e administradores; HTTPS com certificado próprio do Ipê.",
               "Perfiles para médicos, técnicos y administradores; HTTPS con certificado propio de Ipê."),
             T("Users", "Usuários", "Usuarios")),
            (T("Automation", "Automação", "Automatización"),
             T("Routing, scheduled queries, rules by modality and AI on arrival.",
               "Roteamento, buscas agendadas, regras por modalidade e IA na chegada.",
               "Enrutamiento, búsquedas programadas, reglas por modalidad e IA a la llegada."),
             T("Settings ▸ Network", "Configurações ▸ Rede", "Configuración ▸ Red")),
        ],
        "videos": [],
    },
]

# ------------------------------------------------------------------------------------------------- tutoriais
# arquivo: site/media/tutoriais/<id>-<lingua>.mp4 (e o pôster .jpg); youtube: {lingua: código} quando publicado
TUTORIAIS = {
    "curso": {
        "titulo": T("How to build a course with cases", "Como montar um curso com casos",
                    "Cómo armar un curso con casos"),
        "texto": T("Select studies, add history, answer, biopsy and teaching notes, mark the images and export a case "
                   "pack that opens in the browser.",
                   "Selecionar exames, colocar história, resposta, biópsia e notas de ensino, marcar as imagens e "
                   "exportar um pacote de casos que abre no navegador.",
                   "Seleccionar estudios, poner historia, respuesta, biopsia y notas docentes, marcar las imágenes y "
                   "exportar un paquete de casos que abre en el navegador."),
        "duracao": "3:01",
        "youtube": {},
    },
    # 0.100.91: os tutoriais em vídeo (em inglês, com o texto na tela; a narração vem depois)
    "v01": {
        "grupo": "ia",
        "titulo": T('Abdominal organ segmentation (AI)', 'Segmentação de órgãos abdominais (IA)', 'Segmentación de órganos abdominales (IA)'),
        "texto": T('This video shows abdominal organ segmentation in Ipê: the AI outlines the liver with its eight Couinaud segments, the spleen, kidneys, pancreas, adrenals and gallbladder, with the volume of each one.',
                   'Este vídeo mostra a segmentação dos órgãos abdominais no Ipê: a IA contorna o fígado com os oito segmentos de Couinaud, o baço, os rins, o pâncreas, as adrenais e a vesícula, com o volume de cada um.',
                   'Este video muestra la segmentación de órganos abdominales en Ipê: la IA contornea el hígado con sus ocho segmentos de Couinaud, el bazo, los riñones, el páncreas, las suprarrenales y la vesícula, con el volumen de cada uno.'),
        "duracao": "1:39",
        "youtube": {},
    },
    "v05": {
        "grupo": "ia",
        "titulo": T('Body composition at L3 (AI)', 'Composição corporal em L3 (IA)', 'Composición corporal en L3 (IA)'),
        "texto": T('This video shows body composition in Ipê: on an abdominal CT, the AI finds the L3 vertebra and measures skeletal muscle and visceral, subcutaneous and intermuscular fat, plus the attenuation of the liver and spleen.',
                   'Este vídeo mostra a composição corporal no Ipê: numa TC de abdome, a IA acha a vértebra L3 e mede o músculo esquelético e a gordura visceral, subcutânea e intermuscular, além da atenuação do fígado e do baço.',
                   'Este video muestra la composición corporal en Ipê: en una TC de abdomen, la IA encuentra la vértebra L3 y mide el músculo esquelético y la grasa visceral, subcutánea e intermuscular, además de la atenuación del hígado y del bazo.'),
        "duracao": "1:52",
        "youtube": {},
    },
    "v10": {
        "grupo": "ia",
        "titulo": T('Spine levels and the transitional vertebra (AI)', 'Níveis da coluna e vértebra de transição (IA)', 'Niveles de la columna y vértebra de transición (IA)'),
        "texto": T('This video shows how Ipê names the vertebrae and the discs on a spine CT or MR, and how to adjust the numbering when there is a transitional vertebra.',
                   'Este vídeo mostra como o Ipê dá nome às vértebras e aos discos numa TC ou RM de coluna, e como ajustar a numeração quando há uma vértebra de transição.',
                   'Este video muestra cómo Ipê nombra las vértebras y los discos en una TC o RM de columna, y cómo ajustar la numeración cuando hay una vértebra de transición.'),
        "duracao": "1:31",
        "youtube": {},
    },
    "v19": {
        "grupo": "ia",
        "titulo": T('Reviewing AI findings and sending them to the report', 'Revisar os achados de IA e mandar ao laudo', 'Revisar los hallazgos de IA y enviarlos al informe'),
        "texto": T('Every AI in Ipê leaves its results as suggestions. This video shows how to review them: go to the image, confirm, correct or discard each finding, and send what you confirmed to the report.',
                   'Toda IA do Ipê deixa os resultados como sugestões. Este vídeo mostra como revisar: ir até a imagem, confirmar, corrigir ou descartar cada achado, e mandar ao laudo o que você confirmou.',
                   'Cada IA de Ipê deja sus resultados como sugerencias. Este video muestra cómo revisarlos: ir a la imagen, confirmar, corregir o descartar cada hallazgo, y enviar al informe lo que confirmó.'),
        "duracao": "1:40",
        "youtube": {},
    },
    "v23": {
        "grupo": "mama",
        "titulo": T('Mammography display protocols', 'Protocolos de exibição da mamografia', 'Protocolos de visualización de la mamografía'),
        "texto": T('This video shows how Ipê displays a mammogram: the protocol with its stages, the comparison with priors, the quadrant zoom, tomosynthesis with slab and MIP, and the use of two monitors.',
                   'Este vídeo mostra como o Ipê apresenta uma mamografia: o protocolo com as etapas, a comparação com os anteriores, o zoom por quadrante, a tomossíntese com espessura e MIP, e o uso de dois monitores.',
                   'Este video muestra cómo Ipê presenta una mamografía: el protocolo con sus etapas, la comparación con los anteriores, el zoom por cuadrante, la tomosíntesis con espesor y MIP, y el uso de dos monitores.'),
        "duracao": "2:12",
        "youtube": {},
    },
    "v24": {
        "grupo": "mama",
        "titulo": T('Breast density', 'Densidade mamária', 'Densidad mamaria'),
        "texto": T('This video shows breast density in Ipê: a neural network suggests the BI-RADS category from the four views, you confirm it or change it, send it to the report, and review many exams in a queue.',
                   'Este vídeo mostra a densidade mamária no Ipê: uma rede neural sugere a categoria BI-RADS a partir das quatro incidências, você confirma ou troca, manda ao laudo e revisa muitos exames numa fila.',
                   'Este video muestra la densidad mamaria en Ipê: una red neuronal sugiere la categoría BI-RADS a partir de las cuatro incidencias, usted la confirma o la cambia, la envía al informe y revisa muchos estudios en una fila.'),
        "duracao": "1:57",
        "youtube": {},
    },
    "v35": {
        "grupo": "pet",
        "titulo": T('PET/CT reading', 'Leitura do PET/CT', 'Lectura del PET/CT'),
        "texto": T('This video shows how to read a PET/CT in Ipê: the PET reading layout, jumping from the MIP to the slices, finding the maximum SUV, measuring a region, and the liver and mediastinum references.',
                   'Este vídeo mostra como ler um PET/CT no Ipê: o arranjo da leitura do PET, pular do MIP para os cortes, achar o SUV máximo, medir uma região e as referências de fígado e mediastino.',
                   'Este video muestra cómo leer un PET/CT en Ipê: el arreglo de lectura del PET, saltar del MIP a los cortes, buscar el SUV máximo, medir una región y las referencias de hígado y mediastino.'),
        "duracao": "2:01",
        "youtube": {},
    },
    "v38": {
        "grupo": "pet",
        "titulo": T('Fusion: PET over CT', 'Fusão: PET sobre a TC', 'Fusión: PET sobre la TC'),
        "texto": T('This video shows how to overlay one series on another in Ipê, such as PET on CT: choosing the series, adjusting opacity, color and window, and carrying the fusion to the three planes.',
                   'Este vídeo mostra como sobrepor uma série a outra no Ipê, como o PET sobre a TC: escolher a série, ajustar opacidade, cor e janela, e levar a fusão aos três planos.',
                   'Este video muestra cómo superponer una serie sobre otra en Ipê, como el PET sobre la TC: elegir la serie, ajustar la opacidad, el color y la ventana, y llevar la fusión a los tres planos.'),
        "duracao": "1:28",
        "youtube": {},
    },
    "v39": {
        "grupo": "vis",
        "titulo": T('MPR, oblique and curved reformats', 'MPR, oblíquo e curvo', 'MPR, reformateo oblicuo y curvo'),
        "texto": T('This video shows multiplanar reformats in Ipê: the three planes, the crosshair, slab thickness with MIP, an oblique plane, and a curved plane along a structure.',
                   'Este vídeo mostra as reconstruções multiplanares no Ipê: os três planos, a cruz, a espessura com MIP, um plano oblíquo e um plano curvo ao longo de uma estrutura.',
                   'Este video muestra las reconstrucciones multiplanares en Ipê: los tres planos, la cruz, el espesor con MIP, un plano oblicuo y un plano curvo a lo largo de una estructura.'),
        "duracao": "1:47",
        "youtube": {},
    },
    "v40": {
        "grupo": "vis",
        "titulo": T('3D: volume rendering, cutting and presets', '3D: renderização de volume, cortes e presets', '3D: renderizado de volumen, cortes y presets'),
        "texto": T('This video shows the 3D in Ipê: opening a volume, rotating it, choosing a preset, cutting the volume to look inside, and the surface and MIP modes.',
                   'Este vídeo mostra o 3D no Ipê: abrir um volume, girar, escolher um preset, cortar o volume para ver por dentro, e os modos superfície e MIP.',
                   'Este video muestra el 3D en Ipê: abrir un volumen, girarlo, elegir un preset, cortar el volumen para ver por dentro, y los modos superficie y MIP.'),
        "duracao": "1:47",
        "youtube": {},
    },
    "v41": {
        "grupo": "vis",
        "titulo": T('Structures: editing segmentation masks', 'Estruturas: editar máscaras de segmentação', 'Estructuras: editar máscaras de segmentación'),
        "texto": T('This video shows the Structures window in Ipê, where you correct segmentation masks: importing the AI masks, painting with the brush, correcting, the extra tools, and saving as DICOM SEG or RTSTRUCT.',
                   'Este vídeo mostra a janela Estruturas do Ipê, onde se corrigem as máscaras de segmentação: importar as máscaras da IA, pintar com o pincel, corrigir, as ferramentas extras e gravar como DICOM SEG ou RTSTRUCT.',
                   'Este video muestra la ventana Estructuras de Ipê, donde se corrigen las máscaras de segmentación: importar las máscaras de la IA, pintar con el pincel, corregir, las herramientas extra y guardar como DICOM SEG o RTSTRUCT.'),
        "duracao": "1:58",
        "youtube": {},
    },
    "v42": {
        "grupo": "vis",
        "titulo": T('3D segmentation by click', 'Segmentação 3D por clique', 'Segmentación 3D con un clic'),
        "texto": T('This video shows the 3D segmentation by click in Ipê: one click on a lesion grows the region in three dimensions and gives volume, SUV and TLG, ready for the report and for follow-up.',
                   'Este vídeo mostra a segmentação 3D por clique no Ipê: um clique numa lesão faz a região crescer em três dimensões e dá volume, SUV e TLG, prontos para o laudo e o seguimento.',
                   'Este video muestra la segmentación 3D con un clic en Ipê: un clic en una lesión hace crecer la región en tres dimensiones y da volumen, SUV y TLG, listos para el informe y el seguimiento.'),
        "duracao": "1:41",
        "youtube": {},
    },
    "v43": {
        "grupo": "vis",
        "titulo": T('Export a 3D model (STL, OBJ, GLB, 3MF)', 'Exportar um modelo 3D (STL, OBJ, GLB, 3MF)', 'Exportar un modelo 3D (STL, OBJ, GLB, 3MF)'),
        "texto": T('This video shows how to turn what you see into a 3D model in Ipê, for 3D printing, Blender, PowerPoint or the browser: from the 3D view, with the AI segmentations as colored parts.',
                   'Este vídeo mostra como transformar o que você vê num modelo 3D no Ipê, para impressão 3D, Blender, PowerPoint ou o navegador: a partir do 3D, com as segmentações da IA como peças coloridas.',
                   'Este video muestra cómo convertir lo que ve en un modelo 3D en Ipê, para impresión 3D, Blender, PowerPoint o el navegador: desde la vista 3D, con las segmentaciones de la IA como piezas de colores.'),
        "duracao": "1:31",
        "youtube": {},
    },
    "v44": {
        "grupo": "vis",
        "titulo": T('3D ruler, intensity profile and calibration', 'Régua 3D, perfil de intensidade e calibração', 'Regla 3D, perfil de intensidad y calibración'),
        "texto": T('This video shows three measuring tools in Ipê: the 3D ruler between two slices, the intensity profile along a line, the pixel value, and calibration for images without a known scale.',
                   'Este vídeo mostra ferramentas de medida do Ipê: a régua 3D entre dois cortes, o perfil de intensidade ao longo de uma linha, o valor do pixel e a calibração para imagens sem escala conhecida.',
                   'Este video muestra herramientas de medición de Ipê: la regla 3D entre dos cortes, el perfil de intensidad a lo largo de una línea, el valor del píxel y la calibración para imágenes sin escala conocida.'),
        "duracao": "1:50",
        "youtube": {},
    },
}

#: os grupos da página de vídeos, na ordem
GRUPOS_DE_TUTORIAIS = [
    ("ia", T("Artificial intelligence", "Inteligência artificial", "Inteligencia artificial")),
    ("mama", T("Breast imaging", "Mama", "Mama")),
    ("pet", T("PET/CT and oncology", "PET/CT e oncologia", "PET/CT y oncología")),
    ("vis", T("Viewer: MPR, 3D and segmentation", "Visualizador: MPR, 3D e segmentação",
              "Visor: MPR, 3D y segmentación")),
]

# --------------------------------------------------------------------------------------------------- começar
COMECAR = {
    "titulo": T("Get started", "Começar", "Empezar"),
    "texto": T("Install, choose how Ipê will be used and bring in your studies.",
               "Instale, escolha como o Ipê será usado e traga seus exames.",
               "Instale, elija cómo se usará Ipê y traiga sus estudios."),
    "sistemas": [
        ("Windows", T("<code>Ipe-&lt;version&gt;-installer.exe</code>: installs in your user profile, no administrator "
                      "rights. The first screen asks for the language.",
                      "<code>Ipe-&lt;versão&gt;-installer.exe</code>: instala no seu perfil, sem pedir administrador. A "
                      "primeira tela pergunta o idioma.",
                      "<code>Ipe-&lt;versión&gt;-installer.exe</code>: instala en su perfil, sin pedir administrador. "
                      "La primera pantalla pregunta el idioma.")),
        ("macOS", T("<code>.dmg</code> for Apple silicon or Intel. Not signed by Apple: the first time, right-click ▸ "
                    "Open. Experimental.",
                    "<code>.dmg</code> para chip Apple ou Intel. Sem assinatura da Apple: na primeira vez, botão "
                    "direito ▸ Abrir. Experimental.",
                    "<code>.dmg</code> para chip Apple o Intel. Sin firma de Apple: la primera vez, clic derecho ▸ "
                    "Abrir. Experimental.")),
        ("Linux", T("<code>.deb</code> for Debian/Ubuntu (<code>sudo apt install ./Ipe-…deb</code>) or the portable "
                    "<code>.tar.gz</code> for any distribution.",
                    "<code>.deb</code> para Debian/Ubuntu (<code>sudo apt install ./Ipe-…deb</code>) ou o "
                    "<code>.tar.gz</code> portátil para qualquer distribuição.",
                    "<code>.deb</code> para Debian/Ubuntu (<code>sudo apt install ./Ipe-…deb</code>) o el "
                    "<code>.tar.gz</code> portátil para cualquier distribución.")),
    ],
    "passos": [
        T("On the first run, choose: <b>one user</b>, <b>several users on this computer</b> or <b>central server</b>. "
          "You can change it later.",
          "Na primeira vez, escolha: <b>um usuário</b>, <b>vários usuários neste computador</b> ou <b>servidor "
          "central</b>. Dá para mudar depois.",
          "La primera vez, elija: <b>un usuario</b>, <b>varios usuarios en esta computadora</b> o <b>servidor "
          "central</b>. Se puede cambiar después."),
        T("Bring studies in: <b>Import</b> (folder, CD/DVD, ZIP — or drag onto the window) or <b>PACS</b> to search "
          "and download.",
          "Traga exames: <b>Importar</b> (pasta, CD/DVD, ZIP — ou arraste para a janela) ou <b>PACS</b> para buscar "
          "e baixar.",
          "Traiga estudios: <b>Importar</b> (carpeta, CD/DVD, ZIP — o arrástrelos a la ventana) o <b>PACS</b> para "
          "buscar y descargar."),
        T("No studies at hand? <b>Help ▸ Generate test studies</b> creates phantoms to try everything.",
          "Sem exames à mão? <b>Ajuda ▸ Gerar exames de teste</b> cria fantomas para testar tudo.",
          "¿Sin estudios a mano? <b>Ayuda ▸ Generar estudios de prueba</b> crea fantomas para probarlo todo."),
        T("Updates: <b>Help ▸ Check for updates</b>, straight from GitHub or through your server.",
          "Atualizações: <b>Ajuda ▸ Procurar atualizações</b>, direto do GitHub ou pelo seu servidor.",
          "Actualizaciones: <b>Ayuda ▸ Buscar actualizaciones</b>, directo de GitHub o por su servidor."),
    ],
    "ia": T("The AI part (organ segmentation and other models) is optional and installed separately, from inside Ipê.",
            "A parte de IA (segmentação de órgãos e outros modelos) é opcional e instalada à parte, de dentro do Ipê.",
            "La parte de IA (segmentación de órganos y otros modelos) es opcional y se instala aparte, desde Ipê."),
}
