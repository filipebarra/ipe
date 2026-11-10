"""0.100.7: fibroglandular (FGT) e realce de fundo (BPE) da RM de mama, num fantoma com a resposta conhecida: duas
mamas com gordura clara e glândula escura numa fração conhecida (diferente em cada lado), pele, músculo peitoral
escuro na frente da parede, pulmão fechado pelo corpo e um degradê de bobina de ±30%."""
import numpy as np
import pytest

from ipe.imaging import mama_fgt as F

AX = [1, 0, 0, 0, 1, 0]       # axial: colunas para a esquerda (+x), linhas para trás (+y)
VOX = (3.0, 1.0, 1.0)


def _fantoma(frac_dir=0.20, frac_esq=0.55, campo=0.3, fonte="t1", semente=1, implante=False):
    rng = np.random.default_rng(semente)
    nz, ny, nx = 16, 170, 220
    zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    vol = np.zeros((nz, ny, nx), np.float32)
    # tórax: um bloco atrás das mamas, com os pulmões escuros dentro (fechados pelo corpo)
    torax = (yy >= 95) & (yy < 165) & (xx >= 10) & (xx < 210)
    pulmao = (yy >= 112) & (yy < 155) & (((xx >= 25) & (xx < 95)) | ((xx >= 125) & (xx < 195)))
    # mamas: semielipses na frente
    verdade = {}
    mamas = np.zeros_like(torax)
    gl = np.zeros_like(torax)
    for nome, cx, frac in (("direita", 55, frac_dir), ("esquerda", 165, frac_esq)):
        m = (((xx - cx) / 48.0) ** 2 + ((yy - 95) / 75.0) ** 2 < 1) & (yy < 95)
        mamas |= m
        # glândula: uma região central contígua com a fração pedida do miolo (sem pele)
        miolo = m & (((xx - cx) / 44.0) ** 2 + ((yy - 95) / 71.0) ** 2 < 1) & (yy < 84)   # gordura retromamária antes do peitoral
        cy = 35 if (implante and nome == "direita") else 70   # com implante, a glândula fica na frente dele
        d = ((xx - cx) / 44.0) ** 2 + ((yy - cy) / 45.0) ** 2
        lim = np.quantile(d[miolo], frac)
        g = miolo & (d <= lim)
        if implante and nome == "direita":
            g &= yy < 52
        gl |= g
        verdade[nome] = frac
    corpo = torax | mamas
    vol[corpo] = 1000.0                                   # gordura (T1 sem saturação: clara)
    # glândula: entremeada de gordura (textura de ±25%), como a de verdade — um bloco liso seria implante
    textura = rng.normal(0, 1, vol.shape).astype(np.float32)
    from ipe.imaging.morfologia import suavizar
    textura = suavizar(textura, (0, 2, 2))
    textura /= textura[gl].std() + 1e-6
    vol[gl] = 320.0 * (1 + 0.25 * textura[gl])
    vol[torax & (yy < 103)] = 360.0                       # peitoral: faixa escura de 8 mm na frente da parede
    vol[torax & (yy >= 103)] = 420.0                      # parede torácica
    vol[pulmao] = 15.0
    imp = np.zeros_like(torax)
    if implante:                                          # atrás da glândula da direita, liso e homogêneo
        imp = (((xx - 55) / 34.0) ** 2 + ((yy - 74) / 20.0) ** 2 < 1) & mamas
        vol[imp] = 400.0
    pele = corpo & ~(np.roll(corpo, 2, 1) & np.roll(corpo, -2, 1) & np.roll(corpo, 2, 2) & np.roll(corpo, -2, 2))
    vol[pele & mamas] = 600.0
    vol *= (1.0 + campo * (xx - nx / 2) / (nx / 2)).astype(np.float32)   # bobina: ±30% de um lado ao outro
    vol += rng.normal(0, 15, vol.shape).astype(np.float32)
    vol = np.clip(vol, 0, None)
    if fonte == "fs":                                     # com saturação: gordura escura, glândula intermediária
        fs = np.where(gl, 500.0, np.where(mamas | torax, 120.0, 0.0)).astype(np.float32)
        fs[pulmao] = 10.0
        vol = fs + rng.normal(0, 10, fs.shape).astype(np.float32)
    if implante:
        return np.clip(vol, 0, None), gl, mamas, imp
    return np.clip(vol, 0, None), gl, mamas, verdade


def _verdade(r, gl):
    """A fração verdadeira de glândula na mesma região que o programa mediu (a mama sem pele e sem peitoral)."""
    return {nome: 100 * (gl & m).sum() / m.sum()
            for nome, m in zip(("direita", "esquerda"), F.lados(r.mama, r.eixo_lr, r.sentido_lr))}


def test_fgt_no_t1_sem_saturacao():
    vol, gl, mamas, verdade = _fantoma()
    r = F.segmentar(vol, AX, VOX, F.FONTE_T1)
    lado = {l.nome: l for l in r.lados}
    v = _verdade(r, gl)
    assert lado["direita"].fgt_pct == pytest.approx(v["direita"], abs=3)
    assert lado["esquerda"].fgt_pct == pytest.approx(v["esquerda"], abs=3)
    # a região medida é a mama: perde a pele, a borda e, onde a glândula encosta no peitoral, a faixa junto dele
    assert 0.7 < r.mama.sum() / mamas.sum() < 1.0
    assert lado["direita"].faixa == "a" and lado["esquerda"].faixa == F.faixa(v["esquerda"], F.FAIXAS_FGT) == "b"
    # o peitoral (escuro, encostado na parede) não vira glândula
    assert not (r.fgt[:, 95:103, :]).any()
    # a glândula achada é a verdadeira (Dice alto)
    dice = 2 * (r.fgt & gl).sum() / (r.fgt.sum() + gl.sum())
    assert dice > 0.85, dice
    assert "Otsu" in r.texto_metodo


def test_sem_correcao_do_campo_erraria():
    """O degradê da bobina de ±30% mudaria o lado claro: a correção é o que mantém os dois lados certos."""
    vol, gl, mamas, verdade = _fantoma(campo=0.45)
    r = F.segmentar(vol, AX, VOX, F.FONTE_T1)
    v = _verdade(r, gl)
    for l in r.lados:
        assert l.fgt_pct == pytest.approx(v[l.nome], abs=4), (l.nome, l.fgt_pct)


def test_dixon_e_saturado():
    vol, gl, mamas, verdade = _fantoma(campo=0.0)
    gordura = np.where(gl, 60.0, np.where(vol > 500, 900.0, vol * 0.3)).astype(np.float32)
    agua = np.where(gl, 700.0, 80.0).astype(np.float32) * (vol > 50)
    r = F.segmentar(None, AX, VOX, F.FONTE_DIXON, gordura=gordura, agua=agua)
    lado = {l.nome: l for l in r.lados}
    assert lado["esquerda"].fgt_pct == pytest.approx(_verdade(r, gl)["esquerda"], abs=3)
    assert r.limiar == 0.5
    vfs, gl2, _, verd = _fantoma(fonte="fs")
    r2 = F.segmentar(vfs, AX, VOX, F.FONTE_FS)
    assert {l.nome: l for l in r2.lados}["direita"].fgt_pct == pytest.approx(_verdade(r2, gl2)["direita"], abs=5)
    assert any("menos confiável" in a for a in r2.avisos)


def test_realce_de_fundo_so_no_fgt():
    vol, gl, mamas, verdade = _fantoma(campo=0.0)
    r = F.segmentar(vol, AX, VOX, F.FONTE_T1)
    pre = np.where(gl, 300.0, 200.0).astype(np.float32)
    pos = pre.copy()
    # na mama direita, 80% da glândula realça 60%; na esquerda, 10% realça 60% (o resto, 5%)
    rng = np.random.default_rng(3)
    dire, esq = F.lados(r.mama, r.eixo_lr, r.sentido_lr)
    for lado, frac in ((dire, 0.8), (esq, 0.1)):
        sel = gl & lado
        sorteio = rng.random(sel.sum()) < frac
        v = np.full(sel.sum(), 1.05, np.float32)
        v[sorteio] = 1.6
        pos[sel] = pre[sel] * v
    pos[~gl & mamas] = pre[~gl & mamas] * 3.0             # a gordura "realçando" não pode entrar na conta
    F.medir_bpe(r, r.fgt, list(F.lados(r.mama, r.eixo_lr, r.sentido_lr)), pre, pos)
    lado = {l.nome: l for l in r.lados}
    assert lado["direita"].bpe_pct == pytest.approx(80, abs=8) and lado["direita"].bpe_faixa == "acentuado"
    assert lado["esquerda"].bpe_pct == pytest.approx(10, abs=8) and lado["esquerda"].bpe_faixa == "minimo"
    txt = " ".join(F.frases(r))
    assert "Tecido fibroglandular estimado" in txt and "Realce do tecido fibroglandular" in txt
    assert "categoria" in txt and "a critério do médico" in txt


def test_implante_sai_da_conta():
    vol, gl, mamas, imp = _fantoma(implante=True, campo=0.0)
    r = F.segmentar(vol, AX, VOX, F.FONTE_T1)
    assert r.implante_ml > 0.7 * imp.sum() * 3 / 1000
    assert not (r.fgt & imp).any() and (r.mama & imp).sum() < 0.05 * imp.sum()
    v = _verdade(r, gl)
    assert {l.nome: l for l in r.lados}["direita"].fgt_pct == pytest.approx(v["direita"], abs=4)
    assert any("Implante" in a for a in r.avisos) and "Implante identificado" in " ".join(F.frases(r))
    # sem implante, nada é tomado por implante (a glândula tem gordura entremeada)
    vol2, gl2, _, _ = _fantoma(campo=0.0)
    assert F.segmentar(vol2, AX, VOX, F.FONTE_T1).implante_ml == 0


def test_reamostrar_entre_grades():
    m = np.zeros((10, 20, 20), bool)
    m[4:6, 5:10, 5:10] = True
    a1 = np.diag([2.0, 1.0, 1.0, 1.0])                    # cortes de 2 mm, pixel de 1 mm
    a2 = np.diag([1.0, 2.0, 2.0, 1.0])                    # cortes de 1 mm, pixel de 2 mm
    out = F.reamostrar(m, a1, (20, 10, 10), a2)
    # cada voxel do destino vale o voxel da origem que contém o centro dele
    for k, j, i in np.ndindex(out.shape):
        z, y, x = k * 1.0 / 2.0, j * 2.0, i * 2.0
        a, b, c = int(np.rint(z)), int(np.rint(y)), int(np.rint(x))
        esperado = 0 <= a < 10 and 0 <= b < 20 and 0 <= c < 20 and m[a, b, c]
        assert out[k, j, i] == esperado, (k, j, i)
    assert out.sum() > 0
