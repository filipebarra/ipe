"""Modelo do filme (sem Qt): folhas, grades, células e opções. Vai para o banco como JSON."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# tamanhos de papel/filme em mm (largura x altura, retrato) e o FilmSizeID DICOM correspondente
PAPERS: dict[str, tuple[float, float, str]] = {
    "A4": (210, 297, "A4"),
    "A3": (297, 420, "A3"),
    "Carta": (215.9, 279.4, "8_5INX11IN"),
    "Filme 8×10 pol": (203.2, 254.0, "8INX10IN"),
    "Filme 10×12 pol": (254.0, 304.8, "10INX12IN"),
    "Filme 11×14 pol": (279.4, 355.6, "11INX14IN"),
    "Filme 14×14 pol": (355.6, 355.6, "14INX14IN"),
    "Filme 14×17 pol": (355.6, 431.8, "14INX17IN"),
}
LAYOUTS = ["1×1", "1×2", "2×1", "2×2", "2×3", "3×2", "3×3", "3×4", "4×3", "4×4", "4×5", "5×4", "5×5",
           "4×6", "6×5"]
OVERLAYS = {"none": "Sem textos", "min": "Mínimo (imagem, janela)", "full": "Completo (paciente e série)"}


def parse_layout(text: str) -> tuple[int, int]:
    """"3×4" -> (3 linhas, 4 colunas)."""
    a, b = text.replace("x", "×").replace("X", "×").split("×")
    return max(1, min(12, int(a))), max(1, min(12, int(b)))


@dataclass
class Cell:
    study_uid: str
    series_uid: str
    sop_uid: str
    frame_index: int = 0
    width: float | None = None       # janela (None = a da imagem)
    level: float | None = None
    zoom: float = 1.0                # sobre "ajustar à célula"
    pan_x: float = 0.0               # fração da largura/altura da célula
    pan_y: float = 0.0
    invert: bool = False
    cmap: str = ""                  # tabela de cores ("" = cinza)
    filter: str = ""                 # filtro de imagem (nitidez/suavização)
    rotation: int = 0                # 0, 90, 180, 270 (horário)
    flip_h: bool = False
    measures: bool = True            # mostrar medidas/anotações
    label: str = ""                  # descrição da série (para o texto da célula)
    # anotações só do filme (não vão para o exame): {"kind": arrow|text|pencil, "points": [[x, y]...]
    # em pixels da imagem, "text": "..."}; acompanham zoom, pan e giro da célula
    notes: list = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict) -> "Cell":
        known = Cell.__dataclass_fields__
        return Cell(**{k: v for k, v in d.items() if k in known})


@dataclass
class Sheet:
    rows: int = 2
    cols: int = 2
    paper: str = "A4"
    landscape: bool = False
    cells: list[Cell | None] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.fit_cells()

    @property
    def capacity(self) -> int:
        return self.rows * self.cols

    def fit_cells(self) -> list[Cell]:
        """Ajusta a lista ao tamanho da grade; devolve as células que sobraram (não cabem mais)."""
        extra: list[Cell] = []
        if len(self.cells) > self.capacity:
            extra = [c for c in self.cells[self.capacity:] if c is not None]
            del self.cells[self.capacity:]
        self.cells.extend([None] * (self.capacity - len(self.cells)))
        return extra

    def free_slots(self) -> list[int]:
        return [i for i, c in enumerate(self.cells) if c is None]

    def page_mm(self) -> tuple[float, float]:
        w, h, _id = PAPERS.get(self.paper, PAPERS["A4"])
        return (h, w) if self.landscape else (w, h)


@dataclass
class Film:
    name: str = "Filme sem nome"
    sheets: list[Sheet] = field(default_factory=list)
    overlay: str = "min"             # none | min | full
    header: bool = True              # cabeçalho com paciente/exame e rodapé com a folha
    anonymize: bool = False
    ruler: bool = True               # régua de escala em cada célula
    black_page: bool = False         # fundo da folha preto (filme) ou branco (papel)
    gap_mm: float = 1.0              # espaço entre as células
    margin_mm: float = 5.0
    notes_visible: bool = True       # anotações do filme (seta, texto, lápis) na tela e na impressão
    # cópia gravada no exame (0.78): séries criadas e a "impressão digital" do filme naquela hora,
    # para o Salvar não empilhar cópias iguais e perguntar antes de substituir uma diferente
    no_exame: dict = field(default_factory=dict)
    # 0.89: paciente do filme quando ele não é o do cabeçalho das imagens (filme montado com as
    # imagens que chegaram à porta da impressora, identificado pelo OCR ou à mão):
    # {"patient_name", "patient_id", "id_source": ocr|manual|exame|aguardando, "encaminhar": {...}}
    paciente: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sheets:
            self.sheets.append(Sheet())

    # ------------------------------------------------------------ montar
    def add_cells(self, cells: list[Cell], start_sheet: int = 0) -> int:
        """Coloca as células nas vagas livres a partir da folha indicada; cria folhas novas
        (com a grade da última) quando faltar lugar. Devolve o índice da última folha usada."""
        last = start_sheet
        pending = list(cells)
        i = max(0, min(start_sheet, len(self.sheets) - 1))
        while pending:
            if i >= len(self.sheets):
                ref = self.sheets[-1]
                self.sheets.append(Sheet(ref.rows, ref.cols, ref.paper, ref.landscape))
            sh = self.sheets[i]
            for slot in sh.free_slots():
                if not pending:
                    break
                sh.cells[slot] = pending.pop(0)
                last = i
            i += 1
        return last

    def set_layout(self, sheet_index: int, rows: int, cols: int) -> None:
        """Muda a grade; imagens que não cabem vão para a folha seguinte (nada se perde)."""
        sh = self.sheets[sheet_index]
        kept = [c for c in sh.cells if c is not None]
        sh.rows, sh.cols = rows, cols
        sh.cells = []
        sh.fit_cells()
        for k, c in enumerate(kept[:sh.capacity]):
            sh.cells[k] = c
        overflow = kept[sh.capacity:]
        if overflow:
            self.sheets.insert(sheet_index + 1, Sheet(rows, cols, sh.paper, sh.landscape))
            self.add_cells(overflow, sheet_index + 1)

    def image_count(self) -> int:
        return sum(1 for sh in self.sheets for c in sh.cells if c is not None)

    def study_uids(self) -> list[str]:
        out: list[str] = []
        for sh in self.sheets:
            for c in sh.cells:
                if c is not None and c.study_uid not in out:
                    out.append(c.study_uid)
        return out

    # ------------------------------------------------------------ salvar
    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Film":
        sheets = []
        for s in d.get("sheets", []):
            cells = [Cell.from_dict(c) if c else None for c in s.get("cells", [])]
            sheets.append(Sheet(int(s.get("rows", 2)), int(s.get("cols", 2)), s.get("paper", "A4"),
                                bool(s.get("landscape", False)), cells))
        known = Film.__dataclass_fields__
        opts = {k: v for k, v in d.items() if k in known and k != "sheets"}
        return Film(sheets=sheets, **opts)


def pick_frames(n_frames: int, start: int = 0, end: int | None = None, every: int = 1,
                count: int | None = None) -> list[int]:
    """Índices para "série inteira / intervalo": de start a end (inclusivo), a cada `every`,
    ou `count` imagens espalhadas por igual no intervalo."""
    if n_frames <= 0:
        return []
    end = n_frames - 1 if end is None else max(0, min(end, n_frames - 1))
    start = max(0, min(start, end))
    if count:
        count = max(1, min(count, end - start + 1))
        if count == 1:
            return [(start + end) // 2]
        return sorted({round(start + k * (end - start) / (count - 1)) for k in range(count)})
    return list(range(start, end + 1, max(1, every)))
