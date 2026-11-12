"""Conferência do SynthSR sem PyTorch (0.100.23): a U-Net em NumPy, com as mesmas decisões da versão em PyTorch
do trabalhador (totalseg_worker._rede_synthsr), no cérebro-modelo MNI152 (nilearn) degradado para cortes de 5 mm.

Uso: IPE_SYNTHSR_H5=/caminho/SynthSR_v10_210712.h5 python tools/conferir_synthsr.py [t1|t2]
Precisa de numpy, h5py, scipy, nibabel e nilearn. Resultado de 12/11/2026: correlação com o T1 de 1 mm no encéfalo
0,89 (entrada T1 de 5 mm) e 0,88 (entrada de contraste invertido; a interpolação linear dá −0,90)."""
import os, sys, time
import importlib

import h5py, numpy as np, nibabel as nib

nilearn = importlib.import_module("nilearn")          # só desta conferência; não faz parte do programa
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "ipe", "ai"))
W = importlib.import_module("totalseg_worker")

H5 = os.environ.get("IPE_SYNTHSR_H5", "SynthSR_v10_210712.h5")
h = h5py.File(H5, "r")

def conv(x, nome, ativa=True):
    g = h[nome][nome]
    K = np.asarray(g["kernel:0"], np.float32); b = np.asarray(g["bias:0"], np.float32)
    kd = K.shape[0]; cin, cout = K.shape[3], K.shape[4]
    C, D, Hh, Ww = x.shape
    assert C == cin, (nome, C, cin)
    p = kd // 2
    xp = np.pad(x, ((0, 0), (p, p), (p, p), (p, p))) if p else x
    out = np.empty((cout, D, Hh, Ww), np.float32)
    passo = 8
    for d0 in range(0, D, passo):
        d1 = min(D, d0 + passo)
        acc = np.zeros((cout, (d1 - d0) * Hh * Ww), np.float32)
        for a in range(kd):
            for bb in range(kd):
                for c in range(kd):
                    blk = xp[:, d0 + a:d1 + a, bb:bb + Hh, c:c + Ww].reshape(cin, -1)
                    acc += K[a, bb, c].T @ blk
        acc += b[:, None]
        if ativa:
            acc = np.where(acc > 0, acc, np.expm1(np.minimum(acc, 0)))      # ELU
        out[:, d0:d1] = acc.reshape(cout, d1 - d0, Hh, Ww)
    return out

def bn(x, nome):
    g = h[nome][nome]
    ga, be, mu, var = (np.asarray(g[k], np.float32) for k in ("gamma:0", "beta:0", "moving_mean:0", "moving_variance:0"))
    s = ga / np.sqrt(var + 1e-3)
    return x * s[:, None, None, None] + (be - mu * s)[:, None, None, None]

def pool(x):
    C, D, Hh, Ww = x.shape
    return x.reshape(C, D // 2, 2, Hh // 2, 2, Ww // 2, 2).max(axis=(2, 4, 6))

def sobe(x):
    return x.repeat(2, 1).repeat(2, 2).repeat(2, 3)

def prever(S):
    x = np.ascontiguousarray(S)[None].astype(np.float32)
    saltos = []
    for n in range(5):
        x = conv(x, f"unet_conv_downarm_{n}_0"); x = conv(x, f"unet_conv_downarm_{n}_1")
        if n < 4:
            saltos.append(x)
        x = bn(x, f"unet_bn_down_{n}")
        if n < 4:
            x = pool(x)
    for n in range(4):
        x = np.concatenate([saltos.pop(), sobe(x)], 0)
        x = conv(x, f"unet_conv_uparm_{5 + n}_0"); x = conv(x, f"unet_conv_uparm_{5 + n}_1")
        x = bn(x, f"unet_bn_up_{n}")
    return conv(x, "unet_likelihood", ativa=False)[0]

d = os.path.join(os.path.dirname(nilearn.__file__), "datasets", "data")
ler = lambda n: nib.load(os.path.join(d, f"mni_icbm152_{n}_tal_nlin_sym_09a_converted.nii.gz"))
t1i = ler("t1"); T1 = t1i.get_fdata().astype(np.float32); A = t1i.affine
GM = ler("gm").get_fdata() / 255.0; WM = ler("wm").get_fdata() / 255.0
modo = sys.argv[1] if len(sys.argv) > 1 else "t1"
ent = T1.copy()
if modo == "t2":                                   # contraste invertido dentro da cabeça
    cab = T1 > 0.1 * T1.max()
    ent = np.where(cab, T1.max() * 1.1 - T1, 0).astype(np.float32)
n5 = T1.shape[0] // 5
grosso = ent[:n5 * 5].reshape(n5, 5, *ent.shape[1:]).mean(1)       # sagital de 5 mm
Ag = A.copy(); Ag[:3, 0] *= 5; Ag[:3, 3] = A[:3, 3] + A[:3, 0] * 2
print("entrada", grosso.shape, flush=True)
t0 = time.time()
img, afim1 = W._synthsr(np.ascontiguousarray(grosso.transpose(2, 1, 0)), Ag, espelho=False, prever=prever)
print("saida", img.shape, round(time.time() - t0), "s", flush=True)
out = img.astype(np.float32) / W.ESCALA_SYNTHSR
# de volta à grade do modelo (as duas são de 1 mm e alinhadas: só deslocamento)
des = np.round(np.linalg.inv(A) @ afim1 @ [0, 0, 0, 1])[:3].astype(int)
print("deslocamento", des, "passos", np.diag(afim1)[:3])
ref = np.zeros_like(T1); 
sx = [slice(max(0, des[e]), min(T1.shape[e], des[e] + out.shape[e])) for e in range(3)]
so = [slice(sx[e].start - des[e], sx[e].stop - des[e]) for e in range(3)]
rec = np.zeros_like(T1); rec[tuple(sx)] = out[tuple(so)]
cer = (GM + WM) > 0.5
cer[: sx[0].start] = False; cer[sx[0].stop:] = False
r = np.corrcoef(rec[cer], T1[cer])[0, 1]
# linha de base: a entrada reamostrada linear
base, ab = W._a_1mm_ras(grosso, Ag)
db = np.round(np.linalg.inv(A) @ ab @ [0, 0, 0, 1])[:3].astype(int)
recb = np.zeros_like(T1)
sb = [slice(max(0, db[e]), min(T1.shape[e], db[e] + base.shape[e])) for e in range(3)]
recb[tuple(sb)] = base[tuple(slice(s.start - db[e], s.stop - db[e]) for e, s in enumerate(sb))]
rb = np.corrcoef(recb[cer], T1[cer])[0, 1]
wm, gm = rec[(WM > 0.9) & cer].mean(), rec[(GM > 0.9) & cer].mean()
print(f"MODO {modo}: correlacao com o T1 de 1 mm no encefalo: SynthSR {r:.3f} | linear {rb:.3f}")
print(f"saida: branca {wm:.1f} cinzenta {gm:.1f} razao {wm / gm:.2f} | fora da cabeca {rec[T1 < 5].mean():.1f} | max {rec.max():.0f}")
