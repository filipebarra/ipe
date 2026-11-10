"""Máscara da mama na RM: o que é mama, e não parede torácica, coração ou mediastino.

Por que ela precisa existir. A máscara que o mapa cinético usa é só "o pré-contraste tem sinal"
(pré ≥ 10% do sinal de referência). Isso basta para não classificar ar, mas não separa mama de
tórax — e medindo no acervo do usuário, **mais da metade dessa máscara fica atrás da mama**, na
faixa onde o realce rápido é mais comum (47 a 68% dela realça > 100%). Para o mapa pouco importa:
o médico olha a lesão. Para qualquer número **do exame inteiro** — realce de fundo do parênquima,
angiovolume total — é fatal: seria o coração entrando na conta.

Como se corta. O limite posterior da mama é a parede torácica, e quem a denuncia é o **pulmão**:
indo da frente para trás, atravessa-se ar, pele, gordura e glândula, músculo peitoral e então uma
região grande e escura que é pulmão. Em cada linha procura-se a primeira interrupção larga do
corpo; onde ela existe, é a parede. Linhas sem interrupção (acima do ápice pulmonar, abaixo do
seio costofrênico, cortes mediais onde há mediastino no lugar do pulmão) herdam o limite das
vizinhas — primeiro dentro do corte, depois dos cortes ao lado. Nada de valor fixo em milímetros:
mama grande e mama pequena têm paredes em lugares diferentes.

O que esta máscara **não** é: segmentação de glândula. Ela mantém gordura, pele, vasos da mama e
o **músculo peitoral** — quem marca a parede é o pulmão, e o músculo está na frente dele; separar
músculo de glândula por sinal não dá em T1 com saturação de gordura, e chutar uma espessura em
milímetros seria inventar número. Fica dentro, e a máscara diz que fica. Separar fibroglandular de
gordura é outra conta (a da densidade), com outro limiar.
"""

from __future__ import annotations

import numpy as np

# Lado máximo da grade reduzida em que o pulmão é procurado.
LADO_MAX = 160
# Nomes internos do que a máscara conseguiu fazer (chave de programa, não texto de tela).
MODO_PAREDE = "corte na parede torácica"
MODO_SEM_PAREDE = "sem parede encontrada"
MODO_SEM_CORTE = "sem corte posterior"



def eixo_anterior_posterior(orientation) -> tuple[int, int]:
    """Qual eixo da imagem anda de anterior para posterior, e em que sentido.

    Devolve (eixo, sentido): eixo 0 = linhas, 1 = colunas; sentido +1 quando o índice cresce
    para posterior (o y do DICOM cresce para posterior), −1 quando cresce para anterior.
    Devolve (-1, 0) quando nenhum dos dois eixos da imagem é predominantemente A-P — é o caso
    do axial, em que o A-P anda nas linhas, e do coronal, em que não anda na imagem.
    """
    ori = np.asarray(orientation, float).ravel()
    if ori.size != 6:
        return (-1, 0)
    col_dir, row_dir = ori[:3], ori[3:]          # colunas (i), linhas (j)
    y_col, y_lin = abs(float(col_dir[1])), abs(float(row_dir[1]))
    if max(y_col, y_lin) < 0.7:
        return (-1, 0)
    if y_col >= y_lin:
        return (1, 1 if col_dir[1] > 0 else -1)
    return (0, 1 if row_dir[1] > 0 else -1)


# ---------------------------------------------------------------------------
# Pulmão: o buraco escuro que o corpo fecha
# ---------------------------------------------------------------------------

def _propagar(semente: np.ndarray, livre: np.ndarray, voltas: int = 12) -> np.ndarray:
    """Alastra `semente` por dentro de `livre` (conectividade 6), com varreduras por eixo.

    Cada varredura usa duas somas acumuladas em vez de dilatar um pixel por vez: dentro de um
    trecho livre, o alcance salta de uma vez só. Doze idas e voltas bastam para um tórax; sem
    isso, uma dilatação por volta levaria centenas.
    """
    atual = semente & livre
    for _ in range(voltas):
        antes = atual.sum()
        for eixo in range(3):
            n = atual.shape[eixo]
            forma = [1, 1, 1]
            forma[eixo] = n
            idx = np.arange(n).reshape(forma)
            for inverter in (False, True):
                a = np.flip(atual, eixo) if inverter else atual
                m = np.flip(livre, eixo) if inverter else livre
                bloqueio = np.maximum.accumulate(np.where(m, -1, idx), axis=eixo)
                ultima = np.maximum.accumulate(np.where(a, idx, -1), axis=eixo)
                prop = ultima > bloqueio
                prop = np.flip(prop, eixo) if inverter else prop
                atual = atual | (prop & livre)
        if atual.sum() == antes:
            break
    return atual


def _pulmoes(corpo: np.ndarray, reduz: int = 1) -> np.ndarray:
    """Regiões escuras **fechadas pelo corpo**: pulmão (e traqueia). O ar de fora fica de fora.

    É o que separa pulmão de ar do ambiente sem depender de quão escuro o pulmão está: o ar de
    fora encosta na borda da imagem, o pulmão não. Medir vão de 8 mm no sinal não serviu — num
    exame do acervo o pulmão tinha sinal demais e a parede saiu no fim das costas; noutro, um
    buraco dentro da mama virou parede e cortou 76% do tecido.
    """
    escuro = ~corpo
    borda = np.zeros_like(escuro)
    # Só as bordas **dentro do corte**: o ar do ambiente cerca o paciente no plano da imagem.
    # As faces de cima e de baixo da pilha não entram — num sagital de mama o pulmão encosta no
    # corte mais lateral, e semear ali faria o pulmão virar "ar de fora" e sumir.
    borda[:, 0] = borda[:, -1] = True
    borda[:, :, 0] = borda[:, :, -1] = True
    externo = _propagar(borda & escuro, escuro)
    return escuro & ~externo


def _limite_por_linha(pulmao2d: np.ndarray) -> np.ndarray:
    """Para cada linha, a primeira coluna de pulmão (ou -1). Colunas crescendo para posterior."""
    tem = pulmao2d.any(axis=1)
    primeiro = np.argmax(pulmao2d, axis=1).astype(np.int32)
    return np.where(tem, primeiro, -1).astype(np.int32)


def _preencher(limites: np.ndarray) -> np.ndarray:
    """Linhas sem interrupção herdam o limite das que têm (mediana das conhecidas por perto)."""
    conhecidos = limites >= 0
    if not conhecidos.any():
        return limites
    idx = np.flatnonzero(conhecidos)
    out = limites.astype(np.float64)
    out[~conhecidos] = np.interp(np.flatnonzero(~conhecidos), idx, limites[idx].astype(float))
    return np.rint(out).astype(np.int32)


def _suavizar(limites: np.ndarray, janela: int = 9) -> np.ndarray:
    """Mediana móvel: um corte isolado não pode mover a parede."""
    if janela < 3 or limites.size < janela:
        return limites
    meia = janela // 2
    esticado = np.pad(limites, meia, mode="edge")
    janelas = np.lib.stride_tricks.sliding_window_view(esticado, janela)
    return np.median(janelas, axis=1).astype(np.int32)


def mascara_da_mama(pre: np.ndarray, referencia: float, orientation, pixel_mm=(1.0, 1.0),
                    sinal_min_pct: float = 10.0) -> tuple[np.ndarray, dict]:
    """Máscara da mama no volume pré-contraste `(nz, ny, nx)`.

    Devolve (máscara booleana, explicação). A explicação diz o que foi feito e por quê, para a
    tela: máscara que o usuário não entende é máscara em que ele não confia.
    """
    pre = np.asarray(pre)
    corpo = pre >= float(referencia) * float(sinal_min_pct) / 100.0
    eixo, sentido = eixo_anterior_posterior(orientation)
    info = {"corpo_frac": float(corpo.mean()), "eixo_ap": eixo, "sentido": sentido}
    if eixo < 0:
        info["modo"] = MODO_SEM_CORTE
        info["texto"] = ("Plano sem eixo anterior-posterior na imagem: a máscara é só o tecido com "
                         f"pré-contraste ≥ {sinal_min_pct:.0f}% da referência.")
        return corpo, info
    # trabalha com as colunas crescendo para posterior
    vista = np.swapaxes(corpo, 1, 2) if eixo == 0 else corpo
    if sentido < 0:
        vista = vista[:, :, ::-1]
    n_cortes, n_lin, n_col = vista.shape
    # Achar o pulmão é questão de forma, não de detalhe: numa grade reduzida sai o mesmo contorno
    # em uma fração do tempo. Em 512² inteiro o alastramento não terminava em dois minutos.
    f = max(1, int(np.ceil(max(n_lin, n_col) / float(LADO_MAX))))
    pulmao = _pulmoes(vista[:, ::f, ::f])
    n_lin_r = pulmao.shape[1]
    limites = np.empty((n_cortes, n_lin), np.int32)
    achados = np.empty(n_cortes, np.int32)
    linhas_cheias = np.arange(n_lin)
    linhas_red = np.arange(n_lin_r) * f
    for k in range(n_cortes):
        bruto = _limite_por_linha(pulmao[k])
        achados[k] = int((bruto >= 0).sum())
        if not achados[k]:
            limites[k] = -1
            continue
        reduzido = _suavizar(_preencher(bruto)) * f
        limites[k] = np.rint(np.interp(linhas_cheias, linhas_red, reduzido)).astype(np.int32)
    # cortes sem pulmão nenhum (os mais mediais, com mediastino no lugar) herdam o vizinho
    vazios = achados == 0
    if vazios.all():
        info["modo"] = MODO_SEM_PAREDE
        info["texto"] = ("Não achei o pulmão neste exame, então não dá para dizer onde acaba a "
                         "mama: a máscara é só o tecido com pré-contraste ≥ "
                         f"{sinal_min_pct:.0f}% da referência, parede torácica inclusive.")
        return corpo, info
    if vazios.any():
        bons = np.flatnonzero(~vazios)
        for k in np.flatnonzero(vazios):
            limites[k] = limites[int(bons[np.argmin(np.abs(bons - k))])]
    colunas = np.arange(n_col)[None, None, :]
    dentro = colunas < limites[:, :, None]
    saida = vista & dentro
    if sentido < 0:
        saida = saida[:, :, ::-1]
    saida = np.swapaxes(saida, 1, 2) if eixo == 0 else saida
    info["modo"] = MODO_PAREDE
    info["limites"] = limites          # por corte e linha, a 1ª coluna de pulmão (colunas crescendo para trás)
    info["linhas_com_parede"] = float(np.mean(achados / max(n_lin_r, 1)))
    info["reducao"] = f
    info["cortes_com_pulmao"] = float(np.mean(~vazios))
    info["mama_frac"] = float(saida.mean())
    info["cortado_frac"] = float(1.0 - saida.sum() / max(corpo.sum(), 1))
    cortado = 100 * info["cortado_frac"]
    info["texto"] = (f"Mama: tecido com pré-contraste ≥ {sinal_min_pct:.0f}% da referência, até a "
                     f"parede torácica (a primeira coluna de pulmão, indo para trás). Tirou "
                     f"{cortado:.0f}% do tecido, atrás da parede. O músculo peitoral fica dentro: "
                     f"quem marca a parede é o pulmão, e o músculo está na frente dele.")
    return saida, info
