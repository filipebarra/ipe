"""Catálogo central de ações do viewer.

Cada ação tem um identificador fixo, um nome e um grupo. O atalho de teclado é escolhido pelo
usuário em Preferências ▸ Atalhos de teclado e fica em settings.json -> "shortcuts".

**De fábrica a lista de atalhos vem quase vazia** (0.65, pedido dele: "remova todos os atalhos,
eu vou ajustar aos poucos"). Só vêm configuradas as teclas que ele pediu, em `PADROES`. Tecla de
fábrica que ele não escolheu é tecla que atrapalha: num programa de 75 ações, 70 atalhos de
fábrica significam 70 teclas que disparam algo sem ele saber. O catálogo continua inteiro — o que
está vazio é o atalho, e cada ação continua alcançável por menu e por barra.
"""

from __future__ import annotations

# Os únicos atalhos de fábrica. Qualquer outro é escolha dele, na janela de preferências.
PADROES: dict[str, str] = {
    "mg.quad_next": "Q",     # zoom por quadrante da mama; cada Q vai para o próximo, em ciclo
    "mg.next": "Right",      # → próxima etapa do protocolo de mamografia
    "mg.prev": "Left",       # ← etapa anterior
    "film.add": "F1",        # a imagem do quadro vai para o filme (no visualizador F1 é do filme)
    "film.series": "F2",     # a série do quadro no filme (inteira / intervalo)
    "view.copy": "Ctrl+C",   # a imagem do quadro, como está na tela, para a área de transferência (0.99.9)
}

# (id, nome exibido, grupo)
CATALOGO: list[tuple[str, str, str]] = [
    ("tool.wl", "Ferramenta: janela/nível", "Ferramentas"),
    ("tool.zoom", "Ferramenta: zoom", "Ferramentas"),
    ("tool.pan", "Ferramenta: pan", "Ferramentas"),
    ("tool.scroll", "Ferramenta: rolar cortes", "Ferramentas"),
    ("tool.measure", "Ferramenta: régua", "Ferramentas"),
    ("tool.angle", "Ferramenta: ângulo", "Medidas"),
    ("tool.ellipse", "Ferramenta: ROI elíptica", "Medidas"),
    ("tool.polygon", "Ferramenta: ROI poligonal / livre", "Medidas"),
    ("tool.arrow", "Ferramenta: seta", "Medidas"),
    ("tool.text", "Ferramenta: texto", "Medidas"),
    ("tool.polyline", "Ferramenta: polilinha", "Medidas"),
    ("tool.rect", "Ferramenta: ROI retangular", "Medidas"),
    ("tool.probe", "Ferramenta: intensidade (valor do pixel)", "Medidas"),
    ("tool.ruler3d", "Ferramenta: régua 3D (um ponto em cada corte)", "Medidas"),
    ("tool.pencil", "Ferramenta: lápis", "Medidas"),
    ("tool.cobb", "Ferramenta: ângulo de Cobb", "Medidas"),
    ("tool.height", "Ferramenta: diferença de altura", "Medidas"),
    ("tool.ctr", "Ferramenta: índice cardiotorácico", "Medidas"),
    ("tool.spine", "Ferramenta: rotular coluna", "Medidas"),
    ("tool.tic", "Ferramenta: curva tempo-intensidade", "Medidas"),
    ("tool.calibration", "Ferramenta: linha de calibração", "Medidas"),
    ("annot.next", "Próxima imagem com medida", "Medidas"),
    ("annot.prev", "Imagem anterior com medida", "Medidas"),
    ("annot.continuous", "Medição contínua (a ferramenta continua ativa)", "Medidas"),
    ("tool.cross", "Ferramenta: cursor 3D", "Ferramentas"),
    ("view.invert", "Inverter tons", "Imagem"),
    ("view.fit", "Ajustar à janela", "Imagem"),
    ("wl.switch", "Switch WL: próxima janela gravada no arquivo", "Imagem"),
    ("view.rotate_cw", "Girar 90° à direita", "Imagem"),
    ("view.rotate_ccw", "Girar 90° à esquerda", "Imagem"),
    ("view.rotate_180", "Girar 180°", "Imagem"),
    ("view.flip_h", "Espelhar esquerda ↔ direita", "Imagem"),
    ("view.flip_v", "Espelhar cima ↕ baixo", "Imagem"),
    ("view.orient_reset", "Voltar à orientação original", "Imagem"),
    ("view.reset", "Restaurar visualização", "Imagem"),
    ("view.cine", "Cine liga/desliga", "Imagem"),
    ("series.prev", "Série anterior no quadro", "Séries"),
    ("series.next", "Próxima série no quadro", "Séries"),
    ("key.toggle", "Marcar/desmarcar imagem-chave", "Imagens-chave"),
    ("key.show", "Mostrar imagens-chave", "Imagens-chave"),
    ("key.gravar", "Gravar imagens-chave e anotações no exame (KO + GSPS)", "Imagens-chave"),
    ("tool.quadzoom", "Ferramenta: zoom por quadrante (clique no quadro vai para o próximo)", "Imagem"),
    ("mg.quad_next", "Zoom por quadrante: próximo quadrante", "Imagem"),
    ("mg.quad_prev", "Zoom por quadrante: quadrante anterior", "Imagem"),
    ("mg.tomo", "Mamografia: pular entre 2D e tomossíntese (mesma lista)", "Mamografia"),
    ("tool.loupe", "Ferramenta: lupa", "Imagem"),
    ("mg.next", "Mamografia: próxima etapa do protocolo", "Mamografia"),
    ("mg.prev", "Mamografia: etapa anterior do protocolo", "Mamografia"),
    ("mpr.toggle", "MPR liga/desliga", "MPR"),
    ("tool.oblique", "Ferramenta: MPR oblíquo (desenhe uma linha)", "MPR"),
    ("tool.curve", "Ferramenta: MPR curvo (clique os pontos)", "MPR"),
    ("view.3d", "3D: renderização de volume", "MPR"),
    ("mpr.axial", "Reconstruir no quadro ativo: axial", "MPR"),
    ("mpr.coronal", "Reconstruir no quadro ativo: coronal", "MPR"),
    ("mpr.sagital", "Reconstruir no quadro ativo: sagital", "MPR"),
    ("dyn.open", "Avaliação dinâmica (MSI, PEI, SER e curvas)", "MPR"),
    ("phase.next", "Dinâmica: próxima fase", "Dinâmicas"),
    ("phase.prev", "Dinâmica: fase anterior", "Dinâmicas"),
    ("sync.auto", "Sincronizar: automática (mesmo ponto do paciente)", "Sincronização"),
    ("sync.manual", "Sincronizar: manual (mantém a diferença entre os quadros)", "Sincronização"),
    ("sync.link", "Ligar/desligar quadros (manual, com deslocamento)", "Sincronização"),
    ("sync.mode", "Alternar modo de sincronização (desligado / mesmo estudo / todos)", "Sincronização"),
    ("sync.register", "Alinhar automaticamente com o outro exame (registro)", "Sincronização"),
    ("sync.group", "Trocar grupo de sincronização do quadro ativo", "Sincronização"),
    ("sync.window", "Sincronizar janela/nível", "Sincronização"),
    ("sync.zoom", "Sincronizar zoom e pan", "Sincronização"),
    ("view.reflines", "Linhas de referência", "Sincronização"),
    ("view.strip", "Tira de séries (miniaturas)", "Sincronização"),
    ("study.priors", "Adicionar exame anterior", "Estudos"),
    ("view.anonymize", "Ocultar dados do paciente", "Imagem"),
    ("cad.revelar", "Revelar o CAD (ler antes, ver depois)", "Imagem"),
    ("view.mosaico", "Mosaico de cortes no quadro (2×2 → 3×3 → 4×4 → desligado)", "Imagem"),
    ("view.copy", "Copiar a imagem do quadro (área de transferência)", "Imagem"),
    ("view.annot_next", "Anotações: próximo nível (completa, parcial 1, parcial 2, ausente)", "Imagem"),
    ("study.export", "Exportar (DICOM, CD/pendrive, imagens)", "Estudos"),
    ("film.add", "Enviar a imagem do quadro ao filme", "Filme"),
    ("film.add_all", "Enviar a imagem de todos os quadros ao filme", "Filme"),
    ("film.series", "Série do quadro no filme (inteira / intervalo)…", "Filme"),
    ("film.keys", "Imagens-chave no filme", "Filme"),
    ("film.show", "Abrir o compositor de filmes", "Filme"),
    ("tool.grow", "Ferramenta: segmentar 3D (volume, SUV, TLG)", "Medidas"),
    ("lesion.panel", "Acompanhamento de lesões (painel)", "Oncologia"),
    ("report.open", "Laudo do exame", "Laudo"),
    ("overlay.toggle", "Mostrar/ocultar CAD/IA e anotações de outros sistemas", "Imagem"),
    ("mg.implant", "Mamografia: corrigir o implante", "Mamografia"),
    ("mg.enquadrar", "Mamografia: enquadrar a mama no quadro (descartar o ar)", "Mamografia"),
    ("mg.cem", "Mamografia contrastada: alternar baixa energia / recombinada", "Mamografia"),
    ("mg.slab", "Tomossíntese: próxima espessura (slab)", "Mamografia"),
    ("view.histogram", "Histograma da imagem (ou da ROI)", "Imagem"),
    ("annot.export", "Exportar medidas para planilha (CSV/Excel)", "Medidas"),
    ("roteiro.mrpi", "Medidas guiadas: MRPI e MRPI 2.0", "Medidas"),
    ("cefalometria.auto", "Cefalometria do cavum (automática)", "Medidas"),
    ("linfonodos.auto", "Mapa dos níveis linfonodais (IA)", "Medidas"),
    ("abdome.auto", "Segmentar órgãos abdominais (IA)", "Medidas"),
    ("difusao.abrir", "Difusão: ADC, DWI sintética e ADC na ROI", "Medidas"),
    ("estruturas.abrir", "Estruturas: editar máscaras (SEG / RTSTRUCT)", "Medidas"),
]

# Forma histórica (id, nome, atalho padrão, grupo), que o resto do programa e os testes usam.
ACTIONS: list[tuple[str, str, str, str]] = [
    (aid, nome, PADROES.get(aid, ""), grupo) for aid, nome, grupo in CATALOGO
]

ACTION_IDS = {a[0] for a in ACTIONS}


def shortcut_for(settings, action_id: str) -> str:
    custom = settings.get("shortcuts", {}) or {}
    if action_id in custom:
        return custom[action_id]
    return PADROES.get(action_id, "")


def label_for(action_id: str) -> str:
    for aid, nome, _grupo in CATALOGO:
        if aid == action_id:
            return nome
    return action_id
