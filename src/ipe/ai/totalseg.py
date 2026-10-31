"""Segmentação de órgãos abdominais com o TotalSegmentator (0.98, etapa E1: manual, por série).

Pedido dele: segmentar órgãos abdominais com o TotalSegmentator, gravar as máscaras e uma tabela
com as medidas (em OT) no próprio exame. Começa manual (botão direito numa série, no banco e no
visualizador); a configuração por regra e o automático na chegada vêm depois.

**Por que um trabalhador separado.** O TotalSegmentator precisa de PyTorch e nnU-Net (centenas de
MB a alguns GB) e de multiprocessamento — não cabe dentro do pacote do programa. Ele mora num
ambiente Python próprio, criado uma vez pelo `instalar_segmentacao.bat` em
`%LOCALAPPDATA%\\DicomViewer\\segmentacao` (`venv` + `pesos`). O programa conversa com ele por
arquivos (`ai/totalseg_worker.py`): se ele cair, o visualizador não cai junto.

**Licença.** Só tarefas abertas (Apache-2.0): `total` (TC), `total_mr` (RM), `liver_segments` e
`liver_segments_mr` (Couinaud — o autor as marca como menos robustas). Nenhuma exige licença.

**A grade.** O volume vai como o MPR o monta (k, j, i), com a matriz afim em RAS; a segmentação
volta na mesma grade, voxel por voxel. É por isso que a máscara cai no lugar sem reamostrar nada
aqui.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

#: o que marca as séries desta função: ficam só neste computador (o envio ao PACS as pula)
MARCA = "· TotalSegmentator"
#: as marcas das séries que o CAD/IA grava (ficam só neste computador): TotalSegmentator e SynthSeg (0.99.17)
MARCAS_IA = (MARCA, "· SynthSeg")
DESC_SEG = f"Órgãos abdominais {MARCA}"
DESC_TABELA = f"Volumetria abdominal {MARCA}"
SERIE_SEG, SERIE_TABELA = 970, 971

CHAVE_PYTHON = "seg.python"          # caminho do Python do ambiente (vazio = o lugar padrão)
CHAVE_RAPIDO = "seg.rapido"          # modo rápido (3 mm) na TC; na RM o próprio modelo usa 3 mm
CHAVE_COUINAUD = "seg.couinaud"      # segmentos do fígado
CHAVE_ESTRUTURAS = "seg.estruturas"  # quais estruturas (nomes do TotalSegmentator)
# Preferências ▸ CAD/IA (0.99): automático na chegada e para onde mandar depois
CHAVE_AUTO = "seg.auto"                      # segmentar sozinho quando o exame chegar
CHAVE_EXAME_CONTEM = "seg.exame_contem"      # descrição do exame contém (A|B|C; vazio = qualquer)
CHAVE_MODALIDADES = "seg.modalidades"        # ["CT", "MR"]
CHAVE_PRIOR_CT = "seg.prioridade_ct"         # séries, em ordem de preferência (A|B|C)
CHAVE_PRIOR_MR = "seg.prioridade_mr"
CHAVE_ESPESSURA = "seg.espessura_max"        # mm; 0 = sem limite
CHAVE_MIN_CORTES = "seg.min_cortes"
CHAVE_DESTINOS = "seg.destinos"              # ids de nós DICOM para mandar SEG e tabela depois

PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "ABD|ABDOME|ABDOMEN|ABDÔMEN|FIGADO|FÍGADO|PANCREAS|PÂNCREAS|RIM|RINS|RENAL|"
                        "BACO|BAÇO|ENTERO|COLANGIO|TORAX E ABDOME|TÓRAX E ABDOME",
    CHAVE_MODALIDADES: ["CT", "MR"],
    CHAVE_PRIOR_CT: "PORTAL|VENOSA|VENOSO|PARENQUIMA|PARÊNQUIMA|ABD|ABDOME|ABDOMEN",
    CHAVE_PRIOR_MR: "PORTAL|VENOSA|POS|PÓS|T1|DIXON|IN PHASE|T2",
    CHAVE_ESPESSURA: 3.0,
    CHAVE_MIN_CORTES: 40,
    CHAVE_DESTINOS: [],
    CHAVE_RAPIDO: True,
    CHAVE_COUINAUD: True,
}
#: séries que nunca servem para segmentar órgãos
_NUNCA = ("SCOUT", "TOPO", "LOCALIZ", "SURVIEW", "MIP", "MINIP", "VR ", "DOSE", "PLANEJ", "CALIBR",
          "BOLUS", "SMARTPREP", "TRACKER", "TRIGGER", "SUBTRA", "DIFUS", "DWI", "ADC", "MAPA")
#: segmentações em curso (manual ou automática): uma por vez — em CPU, duas só ficam mais lentas
EM_CURSO: set = set()

#: (nome no TotalSegmentator, nome na tela, grupo, vem marcada, cor)
ESTRUTURAS = [
    ("liver", "Fígado", "orgaos", True, (166, 98, 55)),
    ("spleen", "Baço", "orgaos", True, (150, 60, 80)),
    ("kidney_left", "Rim E", "orgaos", True, (60, 110, 200)),
    ("kidney_right", "Rim D", "orgaos", True, (90, 140, 230)),
    ("pancreas", "Pâncreas", "orgaos", True, (230, 190, 90)),
    ("adrenal_gland_left", "Adrenal E", "orgaos", True, (240, 120, 40)),
    ("adrenal_gland_right", "Adrenal D", "orgaos", True, (250, 150, 70)),
    ("gallbladder", "Vesícula biliar", "orgaos", True, (70, 170, 70)),
    ("stomach", "Estômago", "orgaos", False, (200, 150, 200)),
    ("duodenum", "Duodeno", "orgaos", False, (180, 120, 170)),
    ("small_bowel", "Intestino delgado", "orgaos", False, (200, 170, 140)),
    ("colon", "Cólon", "orgaos", False, (160, 130, 90)),
    ("urinary_bladder", "Bexiga", "orgaos", False, (230, 230, 120)),
    ("prostate", "Próstata", "orgaos", False, (120, 200, 200)),
    ("esophagus", "Esôfago", "outras", False, (210, 160, 160)),
    ("aorta", "Aorta", "outras", False, (220, 50, 50)),
    ("inferior_vena_cava", "Veia cava inferior", "outras", False, (70, 70, 200)),
    ("portal_vein_and_splenic_vein", "Veias porta e esplênica", "outras", False, (120, 90, 220)),
]
NOMES = {n: pt for n, pt, *_ in ESTRUTURAS}
GRUPO = {n: g for n, _pt, g, *_ in ESTRUTURAS}
CORES = {n: c for n, _pt, _g, _p, c in ESTRUTURAS}
PADRAO = [n for n, _pt, _g, p, _c in ESTRUTURAS if p]
CORES_SEGMENTOS = [(230, 80, 80), (240, 160, 60), (230, 220, 70), (120, 200, 90),
                   (60, 190, 190), (80, 130, 230), (150, 100, 220), (220, 100, 190)]


# ------------------------------------------------------------------ onde mora o ambiente
def pasta_base() -> Path:
    """%LOCALAPPDATA%\\DicomViewer\\segmentacao no Windows (~/.local/share/DicomViewer/... no Linux)."""
    from platformdirs import user_data_dir

    from ipe import DATA_NAME
    return Path(user_data_dir(DATA_NAME, appauthor=False)) / "segmentacao"


def python_do_ambiente(settings=None) -> Path | None:
    escolhido = str(settings.get(CHAVE_PYTHON, "") or "") if settings is not None else ""
    candidatos = [Path(escolhido)] if escolhido else []
    base = pasta_base() / "venv"
    candidatos += [base / "Scripts" / "python.exe", base / "bin" / "python"]
    return next((c for c in candidatos if c.is_file()), None)


def instalado(settings=None) -> bool:
    return python_do_ambiente(settings) is not None


def motivo_nao_instalado() -> str:
    return ("A segmentação automática ainda não está instalada neste computador. Rode uma vez o "
            "instalar_segmentacao.bat (na pasta do programa): ele cria o ambiente do TotalSegmentator "
            f"em {pasta_base()} e baixa os modelos dos órgãos abdominais.")


def caminho_do_trabalhador() -> Path:
    """O .py do trabalhador: ao lado deste módulo (código-fonte) ou na pasta de recursos do pacote
    (o PyInstaller compila os módulos, mas este vai como arquivo — ver o spec)."""
    perto = Path(__file__).with_name("totalseg_worker.py")
    if perto.is_file():
        return perto
    from ipe.core.runtime import resource_dir
    return resource_dir() / "ai" / "totalseg_worker.py"


# ------------------------------------------------------------------ o que pedir
def serve(modalidade: str) -> bool:
    return (modalidade or "").upper() in ("CT", "MR")


def estruturas(settings=None) -> list[str]:
    v = settings.get(CHAVE_ESTRUTURAS, None) if settings is not None else None
    lista = [n for n in (v or PADRAO) if n in NOMES]
    return lista or list(PADRAO)


def tarefas(modalidade: str, settings=None) -> list[dict]:
    """As tarefas do TotalSegmentator para esta modalidade, na ordem em que rodam."""
    mr = (modalidade or "").upper() == "MR"
    roi = estruturas(settings)
    rapido = bool(config(settings, CHAVE_RAPIDO))
    couinaud = bool(config(settings, CHAVE_COUINAUD))
    # todas as estruturas da lista existem nas duas tarefas (total e total_mr), com o mesmo nome
    out = [{"nome": "total_mr" if mr else "total", "roi": roi, "fast": rapido and not mr,
            "rotulo": "órgãos abdominais"}]
    if couinaud:
        out.append({"nome": "liver_segments_mr" if mr else "liver_segments",
                    "rotulo": "segmentos do fígado (Couinaud)"})
    return out


# ------------------------------------------------------------------ a grade
def afim_ras(vol) -> np.ndarray:
    """Matriz afim (nibabel, RAS) do array (i, j, k) — o volume do MPR transposto.

    O MPR guarda o paciente em LPS (DICOM): p = origem + i·dx·linha + j·dy·coluna + k·passo.
    O NIfTI quer RAS: troca o sinal de x e y."""
    m = np.eye(4)
    m[:3, 0] = vol.row_dir * vol.dx
    m[:3, 1] = vol.col_dir * vol.dy
    m[:3, 2] = vol.slice_vec
    m[:3, 3] = vol.origin
    return np.diag([-1.0, -1.0, 1.0, 1.0]) @ m


# ------------------------------------------------------------------ medidas
@dataclass
class Estrutura:
    nome: str                  # nome do TotalSegmentator (liver, liver_segment_4…)
    rotulo: str                # nome na tela
    grupo: str                 # orgaos | outras | segmentos
    mascara: np.ndarray        # bool (k, j, i) do recorte
    offset: tuple              # (k0, j0, i0)
    voxels: int
    ml: float
    hu: float | None = None
    cor: tuple = (200, 200, 200)
    nota: str = ""
    pct_figado: float | None = None


@dataclass
class Resultado:
    estruturas: list = field(default_factory=list)
    modalidade: str = ""
    versao: str = ""
    segundos: float = 0.0
    tarefas: list = field(default_factory=list)
    soma_segmentos: float | None = None
    figado: float | None = None

    def por_grupo(self, g: str) -> list:
        return [e for e in self.estruturas if e.grupo == g]

    def ml(self, nome: str) -> float | None:
        e = next((x for x in self.estruturas if x.nome == nome), None)
        return e.ml if e is not None else None


def _recorte(m: np.ndarray):
    ks = np.flatnonzero(m.any(axis=(1, 2)))
    js = np.flatnonzero(m.any(axis=(0, 2)))
    is_ = np.flatnonzero(m.any(axis=(0, 1)))
    k0, k1, j0, j1, i0, i1 = ks[0], ks[-1] + 1, js[0], js[-1] + 1, is_[0], is_[-1] + 1
    return m[k0:k1, j0:j1, i0:i1].copy(), (int(k0), int(j0), int(i0))


def medir(vol, rotulos: dict, modalidade: str) -> Resultado:
    """`rotulos`: {tarefa: (array uint8 (k,j,i), {id: nome})}. Volume (mL) e, na TC, HU médio."""
    res = Resultado(modalidade=(modalidade or "").upper())
    ml_voxel = vol.dx * vol.dy * vol.dz / 1000.0
    ct = res.modalidade == "CT"
    ordem = {n: i for i, (n, *_r) in enumerate(ESTRUTURAS)}
    achadas = []
    for tarefa, (lab, classes) in rotulos.items():
        if lab.shape != vol.data.shape:
            raise ValueError(f"{tarefa}: grade {lab.shape} diferente do volume {vol.data.shape}")
        segmentos = tarefa.startswith("liver_segments")
        for cid, nome in classes.items():
            if not segmentos and nome not in NOMES:
                continue
            m = lab == int(cid)
            n = int(m.sum())
            if not n:
                continue
            masc, off = _recorte(m)
            hu = float(vol.data[m].mean()) if ct else None
            if segmentos:
                num = int(nome.rsplit("_", 1)[-1])
                e = Estrutura(nome, f"Segmento {num}", "segmentos", masc, off, n, n * ml_voxel, hu,
                              CORES_SEGMENTOS[(num - 1) % 8])
            else:
                e = Estrutura(nome, NOMES[nome], GRUPO[nome], masc, off, n, n * ml_voxel, hu, CORES[nome])
                if not ct and nome.startswith("adrenal"):
                    e.nota = "baixa confiança na RM"
            achadas.append(e)
    achadas.sort(key=lambda e: (e.grupo == "segmentos", e.grupo == "outras",
                                ordem.get(e.nome, 100 + int(e.nome.rsplit("_", 1)[-1]) if e.grupo == "segmentos" else 999)))
    res.estruturas = achadas
    res.figado = res.ml("liver")
    segs = res.por_grupo("segmentos")
    if segs:
        res.soma_segmentos = sum(e.ml for e in segs)
        for e in segs:
            e.pct_figado = 100.0 * e.ml / res.soma_segmentos
    return res


# ------------------------------------------------------------------ o trabalho
class Falhou(RuntimeError):
    """A segmentação não terminou; a mensagem é para a tela."""


@dataclass
class Trabalho:
    """Uma segmentação de uma série: preparar → (rodar o trabalhador) → ler → gravar."""
    repo: object
    cache: object
    settings: object
    study_uid: str
    series_uid: str
    simular: bool = False                      # testes: o trabalhador devolve rótulos conhecidos
    pasta: Path | None = None
    vol: object = None
    frames: list = field(default_factory=list)
    modalidade: str = ""
    descricao_serie: str = ""
    lista_tarefas: list = field(default_factory=list)
    #: outra lista de tarefas (a coluna, 0.99.2) e o mínimo de cortes dela — vazio = órgãos abdominais
    tarefas_proprias: list | None = None
    min_cortes: int = 20
    #: modalidades aceitas (a cefalometria, 0.99.15, é só TC) e o texto da recusa
    modalidades: tuple = ("CT", "MR")
    motivo_modalidade: str = "A segmentação de órgãos é só para TC e RM."

    def preparar(self, progresso=None) -> None:
        from ipe.imaging.series import build_frames
        from ipe.imaging.volume import VolumeError, build_volume
        serie = next((s for s in self.repo.series_for_study(self.study_uid, ocultas=True)
                      if s.series_uid == self.series_uid), None)
        if serie is None:
            raise Falhou("Série não encontrada no banco.")
        self.modalidade = (serie.modality or "").upper()
        if self.modalidade not in self.modalidades:
            raise Falhou(self.motivo_modalidade)
        self.descricao_serie = serie.description or ""
        self.frames = build_frames(self.repo.instances_for_series(self.series_uid), self.series_uid)
        try:
            self.vol = build_volume(self.frames, self.cache, progress=progresso)
        except VolumeError as e:
            raise Falhou(f"Não deu para montar o volume desta série: {e}") from e
        if self.vol.data.shape[0] < self.min_cortes:
            raise Falhou(f"A série tem poucos cortes para segmentar (menos de {self.min_cortes}).")
        self.lista_tarefas = (self.tarefas_proprias(self.modalidade, self.settings) if callable(self.tarefas_proprias)
                              else self.tarefas_proprias) or tarefas(self.modalidade, self.settings)
        self.pasta = Path(tempfile.mkdtemp(prefix="dv_totalseg_"))
        np.save(self.pasta / "volume.npy", self.vol.data)
        job = {"affine": afim_ras(self.vol).tolist(), "tarefas": self.lista_tarefas, "device": "cpu",
               "simular": self.simular}
        (self.pasta / "job.json").write_text(json.dumps(job), encoding="utf-8")

    def comando(self) -> tuple[str, list[str], dict]:
        """(programa, argumentos, variáveis de ambiente) para rodar o trabalhador."""
        if self.simular:
            py = Path(sys.executable)
        else:
            py = python_do_ambiente(self.settings)
            if py is None:
                raise Falhou(motivo_nao_instalado())
        import os
        env = dict(os.environ)
        env["TOTALSEG_HOME_DIR"] = str(pasta_base() / "pesos")
        env["DIPY_HOME"] = str(pasta_base() / "pesos" / "dipy")          # SynthSeg (0.99.17)
        env["PYTHONIOENCODING"] = "utf-8"
        for k in ("PYTHONPATH", "PYTHONHOME"):        # o ambiente da segmentação é outro Python
            env.pop(k, None)
        return str(py), [str(caminho_do_trabalhador()), str(self.pasta)], env

    def rodar_aqui(self, ao_ler_linha=None) -> None:
        """Roda o trabalhador e espera (testes e linha de comando; a tela usa QProcess)."""
        prog, args, env = self.comando()
        p = subprocess.Popen([prog, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=env, text=True, encoding="utf-8", errors="replace")
        for linha in p.stdout:
            if ao_ler_linha is not None:
                ao_ler_linha(linha.rstrip())
        p.wait()

    def ler(self) -> Resultado:
        rotulos, versao, segundos = self.ler_rotulos()
        res = medir(self.vol, rotulos, self.modalidade)
        res.versao, res.segundos, res.tarefas = versao, segundos, list(rotulos)
        return res

    def ler_rotulos(self) -> tuple[dict, str, float]:
        """({tarefa: (rótulos uint8 (k,j,i), {id: nome})}, versão, segundos) — o que o trabalhador deixou."""
        arq = self.pasta / "resultado.json" if self.pasta else None
        if arq is None or not arq.exists():
            raise Falhou("O TotalSegmentator parou sem deixar resultado (falta de memória?).")
        r = json.loads(arq.read_text(encoding="utf-8"))
        if not r.get("ok"):
            log.warning("TotalSegmentator: %s\n%s", r.get("erro"), r.get("detalhe", ""))
            if "dipy" in str(r.get("erro", "")).lower() and "module" in str(r.get("erro", "")).lower():
                raise Falhou("O SynthSeg ainda não está instalado neste computador: rode de novo o "
                             "instalar_segmentacao (ele acrescenta a DIPY e os pesos do SynthSeg).")
            raise Falhou(f"O TotalSegmentator não terminou: {r.get('erro') or 'erro desconhecido'}")
        rotulos = {}
        self.extras = {}
        self.versao = r.get("versao", "")
        for nome, info in r["tarefas"].items():
            lab = np.load(self.pasta / f"rotulos_{nome}.npy")
            rotulos[nome] = (lab, {int(k): v for k, v in info["classes"].items()})
            fino = self.pasta / f"rotulos_{nome}_1mm.npy"
            if fino.exists() and info.get("afim_1mm"):          # SynthSeg: a segmentação a 1 mm (0.99.18)
                self.extras[nome] = (np.load(fino), np.asarray(info["afim_1mm"], float))
        return rotulos, r.get("versao", ""), sum(float(i.get("segundos", 0)) for i in r["tarefas"].values())

    extras: dict = field(default_factory=dict)          # tarefa -> (rótulos a 1 mm (i,j,k), afim RAS)
    versao: str = ""

    def limpar(self) -> None:
        if self.pasta is not None:
            shutil.rmtree(self.pasta, ignore_errors=True)
            self.pasta = None


def series_locais(repo, study_uid: str) -> set[str]:
    """As séries desta função no exame (ficam só neste computador)."""
    try:
        return {s.series_uid for s in repo.series_for_study(study_uid)
                if any(m in (s.description or "") for m in MARCAS_IA)}
    except Exception:  # noqa: BLE001
        return set()



# ------------------------------------------------------------------ preferências e escolha da série
def config(settings, chave):
    if settings is None:
        return PADROES.get(chave)
    try:
        v = settings.get(chave, PADROES.get(chave))
    except Exception:  # noqa: BLE001
        v = PADROES.get(chave)
    return PADROES.get(chave) if v is None else v


def _sem_acento(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").upper()


def _padroes(texto: str) -> list[str]:
    return [_sem_acento(p.strip()) for p in (texto or "").split("|") if p.strip()]


#: as chaves de cada ferramenta que escolhe série sozinha (a coluna tem as suas, em ai/coluna.py)
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_MR, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES}


def exame_serve(info: dict, settings=None, perfil: dict | None = None, ler=None) -> bool:
    """O exame que chegou é para segmentar sozinho? Modalidade e pedaço da descrição."""
    perfil, ler = perfil or PERFIL, ler or config
    mods = {m.upper() for m in (ler(settings, perfil["modalidades"]) or [])} & {"CT", "MR"}
    tem = (info.get("modalities") or "").upper()
    if not any(m in tem for m in mods):
        return False
    pads = _padroes(ler(settings, perfil["exame_contem"]))
    return not pads or any(p in _sem_acento(info.get("description", "")) for p in pads)


def _espessura(repo, series_uid: str) -> float | None:
    import pydicom
    inst = repo.instances_for_series(series_uid)
    if not inst:
        return None
    try:
        ds = pydicom.dcmread(inst[0]["path"], stop_before_pixels=True, force=True,
                             specific_tags=["SliceThickness", "ImageType"])
        v = ds.get("SliceThickness")
        return float(v) if v not in (None, "") else None
    except Exception:  # noqa: BLE001
        return None


def escolher_serie(repo, study_uid: str, settings=None, perfil: dict | None = None, ler=None,
                   min_absoluto: int = 20) -> tuple[str | None, str]:
    """(series_uid, "") ou (None, motivo). A primeira da lista de prioridade que aparecer na
    descrição; dentro do mesmo nível, a de mais cortes. Fora: localizador, MIP, difusão…, série curta
    e série mais grossa que o limite. `perfil`/`ler`: as chaves e o leitor de outra ferramenta (coluna)."""
    perfil, ler = perfil or PERFIL, ler or config
    mods = {m.upper() for m in (ler(settings, perfil["modalidades"]) or [])} & {"CT", "MR"}
    minimo = int(ler(settings, perfil["min_cortes"]) or 0)
    limite = float(ler(settings, perfil["espessura"]) or 0)
    excluir = tuple(perfil.get("excluir", ()))
    candidatas = []
    for s in repo.series_for_study(study_uid):
        mod = (s.modality or "").upper()
        if mod not in mods:
            continue
        desc = _sem_acento(s.description or "")
        if "TOTALSEGMENTATOR" in desc or "SYNTHSEG" in desc or any(x in desc for x in _NUNCA + excluir):
            continue
        n = len(repo.instances_for_series(s.series_uid))
        if n < max(minimo, min_absoluto):
            continue
        candidatas.append((s, mod, desc, n))
    if not candidatas:
        return None, "nenhuma série de TC/RM com cortes suficientes"
    escolhidas = []
    for s, mod, desc, n in candidatas:
        pads = _padroes(ler(settings, perfil["prior_ct"] if mod == "CT" else perfil["prior_mr"]))
        nivel = next((k for k, p in enumerate(pads) if p in desc), len(pads) if pads else 0)
        escolhidas.append((nivel, -n, s.series_uid, mod))
    escolhidas.sort()
    for nivel, _n, uid, _mod in escolhidas:
        esp = _espessura(repo, uid)
        if limite and esp is not None and esp > limite + 1e-6:
            continue
        return uid, ""
    return None, f"nenhuma série com até {limite:g} mm de espessura"


def ja_segmentado(repo, study_uid: str, descricao: str = DESC_SEG) -> bool:
    """O exame já tem a série desta ferramenta (órgãos por padrão; a coluna passa a dela)."""
    try:
        return any((s.description or "") == descricao for s in repo.series_for_study(study_uid))
    except Exception:  # noqa: BLE001
        return False
