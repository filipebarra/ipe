"""Modelos de laudo de fábrica (o usuário edita, cria e apaga em Laudo → Modelos).

Campos entre chaves são preenchidos sozinhos:
{paciente} {idade} {sexo} {data_exame} {exame} {solicitante} {comparacao} {medidas} {lesoes}
{imagens_chave} {volumes} {birads} {achados_birads} {composicao} {conduta} {curva}
"""

from __future__ import annotations

PLACEHOLDERS = {
    "paciente": "Nome do paciente",
    "idade": "Idade",
    "sexo": "Sexo",
    "data_exame": "Data do exame",
    "exame": "Descrição do exame",
    "solicitante": "Médico solicitante",
    "comparacao": "Exames anteriores do paciente (datas)",
    "medidas": "Medidas feitas no exame (lista)",
    "lesoes": "Tabela do acompanhamento de lesões e a resposta (RECIST, PERCIST…)",
    "imagens_chave": "Número de imagens-chave",
    "volumes": "Segmentações 3D: volumes, SUV, TMTV e TLG",
    "birads": "Categoria BI-RADS e a conduta",
    "achados_birads": "Achados do formulário BI-RADS",
    "composicao": "Composição mamária / FGT / BPE",
    "conduta": "Conduta recomendada pela categoria BI-RADS",
    "curva": "Curvas tempo-intensidade (RM dinâmica)",
}

_MG = """MAMOGRAFIA DIGITAL BILATERAL

Técnica: incidências craniocaudais e médio-laterais oblíquas bilaterais.

Comparação: {comparacao}

Relatório:
{composicao}
{achados_birads}

Linfonodos axilares sem alterações significativas.

IMPRESSÃO:
{birads}
"""

DEFAULTS: list[dict] = [
    # ------------------------------------------------------------ mamografia
    {"id": "mg_rastreamento", "name": "Mamografia bilateral (rastreamento)", "modalities": ["MG"],
     "keywords": ["mamografia", "mammo", "rastreamento", "screening"], "birads": "mg", "text": _MG},
    {"id": "mg_diagnostica", "name": "Mamografia diagnóstica", "modalities": ["MG"],
     "keywords": ["diagnóstica", "diagnostic", "complementar"], "birads": "mg",
     "text": _MG.replace("Técnica: incidências craniocaudais e médio-laterais oblíquas bilaterais.",
                         "Técnica: incidências craniocaudais e médio-laterais oblíquas bilaterais, "
                         "complementadas com incidências adicionais direcionadas.\n\nIndicação: ")},
    {"id": "mg_tomo", "name": "Mamografia com tomossíntese", "modalities": ["MG"],
     "keywords": ["tomossíntese", "tomo", "dbt", "tomosynthesis"], "birads": "mg",
     "text": _MG.replace("MAMOGRAFIA DIGITAL BILATERAL", "MAMOGRAFIA DIGITAL COM TOMOSSÍNTESE")
                .replace("oblíquas bilaterais.", "oblíquas bilaterais, com aquisição de tomossíntese "
                         "e imagem 2D sintetizada.")},
    {"id": "mg_cem", "name": "Mamografia com contraste (CEM)", "modalities": ["MG"],
     "keywords": ["contraste", "cem", "cesm", "contrast"], "birads": "mg",
     "text": """MAMOGRAFIA COM CONTRASTE (CEM)

Técnica: imagens de baixa energia e recombinadas nas incidências craniocaudais e médio-laterais
oblíquas bilaterais, após injeção intravenosa de contraste iodado.

Comparação: {comparacao}

Imagens de baixa energia:
{composicao}

Imagens recombinadas: realce de fundo {bpe_texto}.
{achados_birads}

IMPRESSÃO:
{birads}
"""},
    {"id": "us_mamas", "name": "Ultrassonografia das mamas", "modalities": ["US"],
     "keywords": ["mama", "mamas", "breast"], "birads": "us",
     "text": """ULTRASSONOGRAFIA DAS MAMAS E AXILAS

Comparação: {comparacao}

{composicao}
{achados_birads}

Axilas sem linfonodos de aspecto atípico.

IMPRESSÃO:
{birads}
"""},
    # ------------------------------------------------------------ ressonância
    {"id": "rm_mamas", "name": "RM das mamas", "modalities": ["MR"],
     "keywords": ["mama", "mamas", "breast"], "birads": "mri",
     "text": """RESSONÂNCIA MAGNÉTICA DAS MAMAS

Técnica: sequências multiplanares ponderadas em T1 e T2, difusão e estudo dinâmico após
injeção intravenosa de gadolínio, com subtração e reconstruções.

Comparação: {comparacao}

Relatório:
{composicao}
{achados_birads}
{curva}

Implantes: ausentes.
Linfonodos axilares e mamários internos sem alterações significativas.

IMPRESSÃO:
{birads}
"""},
    {"id": "rm_cranio", "name": "RM do crânio", "modalities": ["MR"],
     "keywords": ["crânio", "cranio", "encéfalo", "encefalo", "brain", "head"],
     "text": """RESSONÂNCIA MAGNÉTICA DO CRÂNIO

Técnica: sequências multiplanares ponderadas em T1, T2, FLAIR, difusão e suscetibilidade
magnética, antes e após a injeção intravenosa de gadolínio.

Comparação: {comparacao}

Relatório:
Sulcos, fissuras e cisternas de amplitude habitual.
Sistema ventricular de dimensões normais, sem desvio da linha média.
Parênquima encefálico com sinal habitual, sem restrição à difusão.
Ausência de realces anômalos após o contraste.
Estruturas da fossa posterior sem alterações.
Principais vasos intracranianos com flow-void habitual.
{medidas}

IMPRESSÃO:
Exame sem alterações significativas.
"""},
    {"id": "rm_abdome", "name": "RM do abdome superior (fígado)", "modalities": ["MR"],
     "keywords": ["abdome", "fígado", "figado", "liver", "abdomen"],
     "text": """RESSONÂNCIA MAGNÉTICA DO ABDOME SUPERIOR

Técnica: sequências ponderadas em T1 (em fase e fora de fase), T2, difusão e estudo dinâmico
após injeção intravenosa de gadolínio.

Comparação: {comparacao}

Relatório:
Fígado de dimensões e contornos normais, com sinal habitual.
Vias biliares sem dilatação. Vesícula biliar sem alterações.
Pâncreas, baço, adrenais e rins sem alterações.
Ausência de ascite ou linfonodomegalias.
{medidas}
{lesoes}

IMPRESSÃO:
"""},
    {"id": "rm_pelve", "name": "RM da pelve", "modalities": ["MR"],
     "keywords": ["pelve", "pelvis", "próstata", "prostata", "útero", "utero", "reto"],
     "text": """RESSONÂNCIA MAGNÉTICA DA PELVE

Técnica: sequências multiplanares ponderadas em T1, T2 e difusão, antes e após contraste.

Comparação: {comparacao}

Relatório:
{medidas}

IMPRESSÃO:
"""},
    # ------------------------------------------------------------ tomografia
    {"id": "tc_cranio", "name": "TC do crânio", "modalities": ["CT"],
     "keywords": ["crânio", "cranio", "head", "brain", "encéfalo"],
     "text": """TOMOGRAFIA COMPUTADORIZADA DO CRÂNIO

Técnica: aquisição volumétrica sem contraste intravenoso.

Comparação: {comparacao}

Relatório:
Sulcos, fissuras e cisternas de amplitude habitual.
Sistema ventricular de dimensões normais, sem desvio da linha média.
Parênquima encefálico com atenuação habitual, sem coleções ou sangramentos.
Estruturas ósseas da calota sem alterações.
{medidas}

IMPRESSÃO:
Exame sem alterações significativas.
"""},
    {"id": "tc_torax", "name": "TC do tórax", "modalities": ["CT"],
     "keywords": ["tórax", "torax", "chest", "pulmão", "pulmao", "thorax"],
     "text": """TOMOGRAFIA COMPUTADORIZADA DO TÓRAX

Técnica: aquisição volumétrica com reconstruções multiplanares.

Comparação: {comparacao}

Relatório:
Traqueia e brônquios principais pérvios.
Parênquima pulmonar com atenuação habitual, sem nódulos ou consolidações.
Ausência de derrame pleural ou pneumotórax.
Mediastino centrado, sem linfonodomegalias.
Coração de dimensões normais. Ausência de derrame pericárdico.
Estruturas ósseas sem alterações significativas.
{medidas}

IMPRESSÃO:
Exame sem alterações significativas.
"""},
    {"id": "tc_angio_tep", "name": "Angio-TC do tórax (TEP)", "modalities": ["CT"],
     "keywords": ["angio", "tep", "embolia", "pulmonar", "cta"],
     "text": """ANGIOTOMOGRAFIA COMPUTADORIZADA DO TÓRAX (PROTOCOLO TEP)

Técnica: aquisição volumétrica após injeção intravenosa de contraste iodado, na fase arterial pulmonar.

Comparação: {comparacao}

Relatório:
Tronco e artérias pulmonares com contrastação adequada, sem falhas de enchimento.
Relação VD/VE preservada.
Parênquima pulmonar sem consolidações. Ausência de derrame pleural.
{medidas}

IMPRESSÃO:
Ausência de sinais de tromboembolismo pulmonar.
"""},
    {"id": "tc_abdome", "name": "TC do abdome e pelve", "modalities": ["CT"],
     "keywords": ["abdome", "abdomen", "pelve", "pelvis", "abdominal"],
     "text": """TOMOGRAFIA COMPUTADORIZADA DO ABDOME E PELVE

Técnica: aquisição volumétrica antes e após injeção intravenosa de contraste iodado.

Comparação: {comparacao}

Relatório:
Fígado de dimensões normais, contornos regulares e atenuação homogênea.
Vesícula biliar normodistendida. Vias biliares sem dilatação.
Pâncreas, baço, adrenais e rins sem alterações.
Alças intestinais de calibre e distribuição habituais.
Bexiga com paredes regulares. Ausência de ascite ou linfonodomegalias.
{medidas}

IMPRESSÃO:
Exame sem alterações significativas.
"""},
    {"id": "tc_onco", "name": "TC oncológica (estadiamento / controle)", "modalities": ["CT"],
     "keywords": ["estadiamento", "oncológico", "oncologico", "controle", "tórax abdome", "tap"],
     "text": """TOMOGRAFIA COMPUTADORIZADA DO TÓRAX, ABDOME E PELVE

Indicação: estadiamento / controle oncológico.

Técnica: aquisição volumétrica após injeção intravenosa de contraste iodado.

Comparação: {comparacao}

Relatório:
{lesoes}
{medidas}

IMPRESSÃO:
"""},
    # ------------------------------------------------------------ PET
    {"id": "pet_fdg", "name": "PET/CT com FDG (oncológico)", "modalities": ["PT", "CT"],
     "keywords": ["fdg", "pet", "oncológico", "oncologico"],
     "text": """PET/CT COM 18F-FDG

Técnica: imagens adquiridas cerca de 60 minutos após a injeção intravenosa de 18F-FDG, do vértice
do crânio à raiz das coxas, com TC de baixa dose para correção de atenuação e localização anatômica.
Glicemia no momento da injeção: ___ mg/dL.

Comparação: {comparacao}

Relatório:
{lesoes}
{volumes}
{medidas}

Captação fisiológica no encéfalo, miocárdio, fígado, trato gastrointestinal e vias urinárias.

IMPRESSÃO:
"""},
    {"id": "pet_psma", "name": "PET/CT com PSMA", "modalities": ["PT", "CT"],
     "keywords": ["psma", "próstata", "prostata"],
     "text": """PET/CT COM PSMA

Técnica: imagens adquiridas após a injeção intravenosa do radiofármaco, do vértice do crânio à raiz
das coxas, com TC de baixa dose para correção de atenuação e localização anatômica.

Comparação: {comparacao}

Relatório:
{lesoes}
{volumes}
{medidas}

Biodistribuição fisiológica do radiofármaco nas glândulas salivares e lacrimais, fígado, baço,
rins, intestino e bexiga.

IMPRESSÃO:
"""},
    {"id": "livre", "name": "Laudo livre", "modalities": [], "keywords": [],
     "text": """{exame}

Comparação: {comparacao}

Relatório:
{medidas}

IMPRESSÃO:
"""},
]


def default_templates() -> list[dict]:
    import copy
    return copy.deepcopy(DEFAULTS)


def best_template(templates: list[dict], modalities: str, description: str) -> dict | None:
    """Escolhe o modelo pela modalidade e pelas palavras da descrição do exame."""
    mods = {m.strip().upper() for m in (modalities or "").replace("/", "\\").split("\\") if m.strip()}
    desc = (description or "").lower()
    best, score = None, -1
    for t in templates:
        tm = {m.upper() for m in t.get("modalities", [])}
        s = 0
        if tm and tm & mods:
            s += 10 + len(tm & mods)
        elif tm:
            continue
        s += sum(3 for k in t.get("keywords", []) if k.lower() in desc)
        if s > score:
            best, score = t, s
    return best
