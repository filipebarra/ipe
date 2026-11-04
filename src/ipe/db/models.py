"""Modelo de dados: hierarquia DICOM + banco de casos.

Paciente -> Estudo -> Série -> Instância (arquivo). Comentários, listas de
casos e tags ficam em tabelas próprias. Escrito com SQLAlchemy 2 para poder
trocar SQLite por PostgreSQL no modo servidor sem reescrever.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now()


class Patient(Base):
    __tablename__ = "patient"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    issuer: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(256), default="", index=True)
    birth_date: Mapped[str] = mapped_column(String(8), default="")   # AAAAMMDD
    sex: Mapped[str] = mapped_column(String(16), default="")

    studies: Mapped[list["Study"]] = relationship(back_populates="patient",
                                                  cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("patient_id", "issuer", "name", "birth_date"),)


class Study(Base):
    __tablename__ = "study"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    patient_fk: Mapped[int] = mapped_column(ForeignKey("patient.id", ondelete="CASCADE"))
    study_date: Mapped[str] = mapped_column(String(8), default="", index=True)
    study_time: Mapped[str] = mapped_column(String(16), default="")
    accession: Mapped[str] = mapped_column(String(64), default="", index=True)
    description: Mapped[str] = mapped_column(String(256), default="")
    modalities: Mapped[str] = mapped_column(String(64), default="")    # "CT\\PT"
    referring: Mapped[str] = mapped_column(String(256), default="")
    institution: Mapped[str] = mapped_column(String(256), default="")
    patient_age: Mapped[str] = mapped_column(String(8), default="")
    # gestão local
    origin: Mapped[str] = mapped_column(String(16), default="import")  # import, received, retrieved, prefetch
    # 0.99.27: em que banco o exame está — "" = compartilhado; usuário = banco pessoal dele;
    # visivel_para = com quem o dono compartilhou (vírgulas). Os arquivos ficam no mesmo Storage.
    dono: Mapped[str] = mapped_column(String(64), default="", index=True)
    visivel_para: Mapped[str] = mapped_column(Text, default="")
    date_added: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)       # protegido do autodelete
    unread: Mapped[bool] = mapped_column(Boolean, default=True)

    patient: Mapped[Patient] = relationship(back_populates="studies")
    series: Mapped[list["Series"]] = relationship(back_populates="study",
                                                  cascade="all, delete-orphan",
                                                  order_by="Series.series_number")


class Series(Base):
    __tablename__ = "series"
    id: Mapped[int] = mapped_column(primary_key=True)
    series_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    study_fk: Mapped[int] = mapped_column(ForeignKey("study.id", ondelete="CASCADE"))
    modality: Mapped[str] = mapped_column(String(16), default="")
    series_number: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(String(256), default="")
    body_part: Mapped[str] = mapped_column(String(64), default="")
    laterality: Mapped[str] = mapped_column(String(4), default="")
    frame_of_reference: Mapped[str] = mapped_column(String(64), default="")
    # detalhes do equipamento/equipe (None = ainda não lido; bancos antigos são completados em segundo plano)
    operators: Mapped[str | None] = mapped_column(Text, nullable=True)       # (0008,1070) Operators' Name
    station: Mapped[str | None] = mapped_column(String(128), nullable=True)  # (0008,1010) Station Name
    device: Mapped[str | None] = mapped_column(String(256), nullable=True)   # fabricante + modelo
    thumbnail: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # PNG
    # série escondida pelo usuário: continua no banco e no disco, só não aparece (esconder não é apagar)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    study: Mapped[Study] = relationship(back_populates="series")
    instances: Mapped[list["Instance"]] = relationship(back_populates="series",
                                                       cascade="all, delete-orphan")


class Instance(Base):
    __tablename__ = "instance"
    id: Mapped[int] = mapped_column(primary_key=True)
    sop_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    sop_class_uid: Mapped[str] = mapped_column(String(64), default="")
    series_fk: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    instance_number: Mapped[int] = mapped_column(Integer, default=0)
    file_path: Mapped[str] = mapped_column(Text)
    in_storage: Mapped[bool] = mapped_column(Boolean, default=True)  # False = só referenciado
    transfer_syntax: Mapped[str] = mapped_column(String(64), default="")
    rows: Mapped[int] = mapped_column(Integer, default=0)
    columns: Mapped[int] = mapped_column(Integer, default=0)
    number_of_frames: Mapped[int] = mapped_column(Integer, default=1)
    # geometria para ordenar cortes pela posição real no paciente
    image_position: Mapped[str] = mapped_column(String(128), default="")      # "x\\y\\z"
    image_orientation: Mapped[str] = mapped_column(String(256), default="")   # 6 valores
    slice_location: Mapped[float | None] = mapped_column(Float, nullable=True)
    acquisition_time: Mapped[str] = mapped_column(String(16), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)

    series: Mapped[Series] = relationship(back_populates="instances")


# ---------------------------------------------------------------------------
# Banco de casos
# ---------------------------------------------------------------------------

class Comment(Base):
    __tablename__ = "comment"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16))   # study, series, instance
    target_uid: Mapped[str] = mapped_column(String(64), index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(64), default="local")
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CaseList(Base):
    __tablename__ = "case_list"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(16), default="")
    parent_fk: Mapped[int | None] = mapped_column(ForeignKey("case_list.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="normal")   # normal, meeting, folder, smart
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ordem dentro da pasta
    smart_query: Mapped[str] = mapped_column(Text, default="")        # JSON do filtro salvo
    meeting_date: Mapped[str] = mapped_column(String(8), default="")
    owner: Mapped[str] = mapped_column(String(64), default="local")
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    # 0.99.30: quem vê a lista — "" = todos (do serviço); um usuário = pessoal dele; visivel_para = escolhidos
    dono: Mapped[str] = mapped_column(String(64), default="")
    visivel_para: Mapped[str] = mapped_column(Text, default="")

    items: Mapped[list["CaseListItem"]] = relationship(back_populates="case_list",
                                                       cascade="all, delete-orphan",
                                                       order_by="CaseListItem.position")


class CaseListItem(Base):
    __tablename__ = "case_list_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    list_fk: Mapped[int] = mapped_column(ForeignKey("case_list.id", ondelete="CASCADE"))
    study_uid: Mapped[str] = mapped_column(String(64), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    friendly_name: Mapped[str] = mapped_column(String(256), default="")   # modo reunião
    clinical_summary: Mapped[str] = mapped_column(Text, default="")
    hidden_diagnosis: Mapped[str] = mapped_column(Text, default="")
    saved_view: Mapped[str] = mapped_column(Text, default="")             # JSON
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)         # separadas por vírgula
    show_series: Mapped[str | None] = mapped_column(Text, nullable=True)  # séries a abrir (vírgula); vazio = todas

    case_list: Mapped[CaseList] = relationship(back_populates="items")
    __table_args__ = (UniqueConstraint("list_fk", "study_uid"),)


class Tag(Base):
    __tablename__ = "tag"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class StudyTag(Base):
    __tablename__ = "study_tag"
    study_uid: Mapped[str] = mapped_column(String(64), primary_key=True)
    tag_fk: Mapped[int] = mapped_column(ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)


class Diagnosis(Base):
    __tablename__ = "diagnosis"
    study_uid: Mapped[str] = mapped_column(String(64), primary_key=True)
    final_dx: Mapped[str] = mapped_column(Text, default="")
    pathology: Mapped[str] = mapped_column(Text, default="")
    follow_up: Mapped[str] = mapped_column(Text, default="")
    teaching_points: Mapped[str] = mapped_column(Text, default="")


class KeyImage(Base):
    """Imagem-chave: aponta para um quadro de uma imagem original."""
    __tablename__ = "key_image"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_uid: Mapped[str] = mapped_column(String(64), index=True)
    series_uid: Mapped[str] = mapped_column(String(64))
    sop_uid: Mapped[str] = mapped_column(String(64))
    frame_index: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(64), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    __table_args__ = (UniqueConstraint("sop_uid", "frame_index"),)


class AnnotationRecord(Base):
    """Medida ou anotação desenhada sobre um quadro (régua, ângulo, ROI, seta, texto)."""
    __tablename__ = "annotation"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_uid: Mapped[str] = mapped_column(String(64), index=True)
    series_uid: Mapped[str] = mapped_column(String(64), index=True)
    sop_uid: Mapped[str] = mapped_column(String(64))
    frame_index: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(16))
    data: Mapped[str] = mapped_column(Text, default="")      # JSON: pontos e texto
    owner: Mapped[str] = mapped_column(String(64), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class LesionTrack(Base):
    """Acompanhamento de lesões de um paciente: critério escolhido e exame de base."""
    __tablename__ = "lesion_track"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    criterion: Mapped[str] = mapped_column(String(16), default="recist")
    baseline_study: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Lesion(Base):
    """Lesão acompanhada ao longo dos exames. As medidas ligadas a ela guardam o id no JSON da
    anotação ("lesion"); data (JSON) guarda o estado por exame (ausente, progressão…)."""
    __tablename__ = "lesion"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    location: Mapped[str] = mapped_column(String(128), default="")
    kind: Mapped[str] = mapped_column(String(16), default="target")     # target, nontarget, new
    nodal: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Report(Base):
    """Laudo do exame (rascunho ou assinado)."""
    __tablename__ = "report"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_uid: Mapped[str] = mapped_column(String(64), index=True)
    template: Mapped[str] = mapped_column(String(128), default="")
    title: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")    # draft, final, amended
    text: Mapped[str] = mapped_column(Text, default="")                 # texto do laudo
    fields: Mapped[str] = mapped_column(Text, default="{}")             # campos estruturados (JSON)
    author: Mapped[str] = mapped_column(String(128), default="")
    signed_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StudyRegistration(Base):
    """Alinhamento salvo entre dois estudos (para sincronizar comparações).
    Um ponto P do estudo A corresponde a P + (dx, dy, dz) no estudo B (mm)."""
    __tablename__ = "study_registration"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_a: Mapped[str] = mapped_column(String(64), index=True)
    study_b: Mapped[str] = mapped_column(String(64), index=True)
    dx: Mapped[float] = mapped_column(Float, default=0.0)
    dy: Mapped[float] = mapped_column(Float, default=0.0)
    dz: Mapped[float] = mapped_column(Float, default=0.0)
    rel: Mapped[float] = mapped_column(Float, default=0.0)   # deslocamento relativo (fração da pilha)
    method: Mapped[str] = mapped_column(String(16), default="manual")
    #: 0.99.38: o registro rígido inteiro (rotação + translação), matriz 4 × 4 em JSON que leva um ponto
    #: de A ao ponto de B; vazio = só a translação (dx, dy, dz)
    matriz: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("study_a", "study_b"),)


class RevisaoIA(Base):
    """Conferência de um resultado de IA (0.99.22, plano AW): auto, editado, aceito por quem e quando.
    `dados` guarda o resultado como ficou depois da conferência (JSON do módulo)."""
    __tablename__ = "revisao_ia"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_uid: Mapped[str] = mapped_column(String(64), index=True)
    modulo: Mapped[str] = mapped_column(String(32), default="")
    estado: Mapped[str] = mapped_column(String(16), default="auto")      # auto | editado | aceito
    editado: Mapped[bool] = mapped_column(Boolean, default=False)
    usuario: Mapped[str] = mapped_column(String(64), default="")
    quando: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    dados: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("study_uid", "modulo"),)


class AchadoIA(Base):
    """Um achado proposto por uma IA, revisável um a um (0.99.46, base comum das IAs de achado).

    Candidato com posição (mm, coordenadas do paciente), números com unidade, quem propôs (ferramenta,
    modelo, versão, série) e por que aceitou a série; o estado anda de *sugerido* para *confirmado*,
    *corrigido* ou *descartado*, com quem revisou e quando. **Nada vai sozinho ao laudo**: só o que
    foi confirmado ou corrigido."""
    __tablename__ = "achado_ia"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_uid: Mapped[str] = mapped_column(String(64), index=True)
    series_uid: Mapped[str] = mapped_column(String(64), default="")
    ferramenta: Mapped[str] = mapped_column(String(32), default="", index=True)
    rotulo: Mapped[str] = mapped_column(String(32), default="")          # "N1"
    tipo: Mapped[str] = mapped_column(String(64), default="")            # "Nódulo pulmonar"
    local: Mapped[str] = mapped_column(String(128), default="")          # "lobo superior direito"
    posicao: Mapped[str] = mapped_column(String(128), default="")        # JSON [x, y, z] em mm
    numeros: Mapped[str] = mapped_column(Text, default="")               # JSON {nome: [valor, unidade]}
    corrigidos: Mapped[str] = mapped_column(Text, default="")            # JSON, o que o médico mudou
    modelo: Mapped[str] = mapped_column(String(128), default="")
    versao: Mapped[str] = mapped_column(String(64), default="")
    elegibilidade: Mapped[str] = mapped_column(Text, default="")         # por que a série serviu, avisos
    segmento: Mapped[int] = mapped_column(Integer, default=0)            # número do segmento na SEG
    estado: Mapped[str] = mapped_column(String(16), default="sugerido")
    revisor: Mapped[str] = mapped_column(String(64), default="")
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    nota: Mapped[str] = mapped_column(Text, default="")
    lesao_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_now)


class BuscaAtiva(Base):
    """Paciente a chamar de volta (0.99.51, onda B8): o laudo assinado com BI-RADS 0 ou 3 gera o pedido.

    O prazo sai da data da assinatura + os dias da categoria (Configurações ▸ Laudos ▸ Busca ativa). O estado
    anda de *pendente* para *contatado* / *agendado* e termina em *retornou* (chegou exame de mama novo do
    paciente — conferido sozinho) ou *encerrado* (com o motivo). `historico` guarda cada passo, com quem e quando."""
    __tablename__ = "busca_ativa"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_uid: Mapped[str] = mapped_column(String(64), index=True)
    report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patient_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    patient_name: Mapped[str] = mapped_column(String(256), default="")
    study_date: Mapped[str] = mapped_column(String(8), default="")
    modalidade: Mapped[str] = mapped_column(String(16), default="")       # MG, US, MR
    categoria: Mapped[str] = mapped_column(String(4), default="")         # "0", "3"
    motivo: Mapped[str] = mapped_column(Text, default="")
    prazo: Mapped[str] = mapped_column(String(8), default="", index=True)  # AAAAMMDD
    estado: Mapped[str] = mapped_column(String(16), default="pendente", index=True)
    retorno_uid: Mapped[str] = mapped_column(String(64), default="")
    historico: Mapped[str] = mapped_column(Text, default="")              # uma linha por passo
    criado_por: Mapped[str] = mapped_column(String(128), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_now)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=_now)


class SeriesGroup(Base):
    """Séries agrupadas pelo usuário (ex.: fases de uma RM dinâmica, uma série por fase)."""
    __tablename__ = "series_group"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_uid: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128), default="Dinâmica")
    kind: Mapped[str] = mapped_column(String(16), default="dynamic")
    series_uids: Mapped[str] = mapped_column(Text, default="")        # separados por vírgula, em ordem
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class SavedFilm(Base):
    """Filme montado no compositor (folhas, layouts e ajustes por imagem), salvo como JSON."""
    __tablename__ = "saved_film"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256), default="Filme")
    study_uids: Mapped[str] = mapped_column(Text, default="")        # separados por vírgula
    patient_name: Mapped[str] = mapped_column(String(256), default="")
    sheets: Mapped[int] = mapped_column(Integer, default=1)
    images: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    printed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # última impressão
    # 0.77 (painel de filmes): quem montou, quem imprimiu, quantas vezes e para onde
    created_by: Mapped[str] = mapped_column(String(64), default="")
    printed_by: Mapped[str] = mapped_column(String(64), default="")
    print_count: Mapped[int] = mapped_column(Integer, default=0)
    print_destination: Mapped[str] = mapped_column(String(128), default="")
    # 0.89: filme montado com imagens recebidas — o paciente e de onde ele veio (vazio = filme comum)
    patient_id: Mapped[str] = mapped_column(String(64), default="")
    id_source: Mapped[str] = mapped_column(String(16), default="")


class PrintJobRecord(Base):
    """Trabalho de impressão: recebido pela impressora DICOM ou montado no compositor."""
    __tablename__ = "print_job"
    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True, default="")
    source: Mapped[str] = mapped_column(String(8), default="scp")      # scp | film
    received_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    calling_ae: Mapped[str] = mapped_column(String(32), default="")
    remote_host: Mapped[str] = mapped_column(String(64), default="")
    server: Mapped[str] = mapped_column(String(64), default="")       # servidor que recebeu
    label: Mapped[str] = mapped_column(String(256), default="")
    medium: Mapped[str] = mapped_column(String(32), default="")
    film_size: Mapped[str] = mapped_column(String(32), default="")
    sheets: Mapped[int] = mapped_column(Integer, default=0)
    images: Mapped[int] = mapped_column(Integer, default=0)
    patient_name: Mapped[str] = mapped_column(String(256), default="")
    patient_id: Mapped[str] = mapped_column(String(64), default="")
    id_source: Mapped[str] = mapped_column(String(16), default="")     # label | manual | exame
    study_uid: Mapped[str] = mapped_column(String(64), default="")     # exame criado no banco
    folder: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="new")     # new | sent | error
    destination: Mapped[str] = mapped_column(String(128), default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    modality: Mapped[str] = mapped_column(String(32), default="")      # 0.84: printing.modalidade



class PrintSendRecord(Base):
    """Histórico de envios (0.84): cada vez que um filme foi mandado, para onde, quando e por quem.

    `kind` diz de que lista é o filme — `scp` (recebido da modalidade, `ref` = id do trabalho),
    `film` (montado no compositor, `ref` = id do filme) ou `aw` (veio no exame, `ref` = UID do
    estudo). `how`: manual, regra, reimpressão ou compositor.
    """
    __tablename__ = "print_send"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), default="scp", index=True)
    ref: Mapped[str] = mapped_column(String(64), default="", index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    destination: Mapped[str] = mapped_column(String(256), default="")
    user: Mapped[str] = mapped_column(String(64), default="")
    how: Mapped[str] = mapped_column(String(16), default="manual")
    template: Mapped[str] = mapped_column(String(128), default="")   # modelo de folha usado
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    message: Mapped[str] = mapped_column(Text, default="")

# ---------------------------------------------------------------------------
# Automação
# ---------------------------------------------------------------------------

class AutomationRule(Base):
    """Busca agendada, pré-busca de anteriores ou roteamento (configuração em JSON)."""
    __tablename__ = "automation_rule"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)     # query | prior | route
    name: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[str] = mapped_column(Text, default="{}")
    owner: Mapped[str] = mapped_column(String(64), default="local")
    last_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class JobRun(Base):
    """Histórico das execuções automáticas."""
    __tablename__ = "job_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(128), default="")
    started: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    finished: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")   # ok | error
    items: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")


class DeletionLog(Base):
    __tablename__ = "deletion_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    study_uid: Mapped[str] = mapped_column(String(64))
    patient: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(String(256), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(String(16), default="trash")   # trash | purge | restore


# ---------------------------------------------------------------------------
# Rede DICOM
# ---------------------------------------------------------------------------

class DicomNode(Base):
    """Nó remoto (PACS, modalidade, outra estação)."""
    __tablename__ = "dicom_node"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="dimse")          # dimse | dicomweb
    ae_title: Mapped[str] = mapped_column(String(16), default="")
    host: Mapped[str] = mapped_column(String(256), default="")
    port: Mapped[int] = mapped_column(Integer, default=104)
    base_url: Mapped[str] = mapped_column(String(512), default="")          # DICOMweb: .../dicom-web
    # DICOMweb usa usuário e senha em vez de AE title. A senha fica **em texto claro** neste
    # banco, como o token da API: é o mesmo nível de proteção do arquivo de configuração, e o
    # usuário é avisado disso na tela do nó.
    username: Mapped[str] = mapped_column(String(128), default="")
    password: Mapped[str] = mapped_column(String(256), default="")
    verify_tls: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=True)
    retrieve: Mapped[str] = mapped_column(String(8), default="get")         # get | move
    move_destination: Mapped[str] = mapped_column(String(16), default="")  # vazio = este programa
    use_in_search: Mapped[bool] = mapped_column(Boolean, default=True)
    # nulos em bancos antigos: anteriores segue "busca"; envio fica liberado
    use_in_priors: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=True)
    use_in_send: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=True)
    # abrir o exame enquanto ele baixa (streaming); None = usar o padrão das preferências
    stream_open: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(Text, default="")
    # 0.99.26: quem vê ("" = do serviço; usuário = pessoal) e com quem foi compartilhado (vírgulas)
    dono: Mapped[str] = mapped_column(String(64), default="")
    visivel_para: Mapped[str] = mapped_column(Text, default="")


class AeIdentity(Base):
    """AE Title alternativo que o programa pode assumir numa busca, download ou envio."""
    __tablename__ = "ae_identity"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    ae_title: Mapped[str] = mapped_column(String(16))
    move_destination: Mapped[str] = mapped_column(String(16), default="")  # vazio = este programa
    allowed_nodes: Mapped[str] = mapped_column(Text, default="")           # ids separados por vírgula; vazio = todos
    note: Mapped[str] = mapped_column(Text, default="")
    dono: Mapped[str] = mapped_column(String(64), default="")              # 0.99.26: "" = do serviço
    visivel_para: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    user: Mapped[str] = mapped_column(String(64), default="local")
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(Text, default="")
    study_uid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    host: Mapped[str | None] = mapped_column(String(128), nullable=True)


class User(Base):
    """Usuário do programa (login próprio; senha com PBKDF2)."""
    __tablename__ = "app_user"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(16), default="medico")
    password_hash: Mapped[str] = mapped_column(String(256), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    created: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prefs: Mapped[str] = mapped_column(Text, default="{}")       # preferências do usuário (JSON)
    # 0.99.25: a conta do Windows/Linux deste usuário — com "entrar pela conta do sistema" ligado, quem
    # abriu o programa com essa conta entra sem digitar senha
    conta_sistema: Mapped[str] = mapped_column(String(128), default="")


class AppSetting(Base):
    """Configurações centrais (ex.: tabela de permissões dos perfis)."""
    __tablename__ = "app_setting"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="null")


Index("ix_instance_series_number", Instance.series_fk, Instance.instance_number)
