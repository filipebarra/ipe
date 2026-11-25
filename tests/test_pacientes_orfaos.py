"""0.100.116: o banco não acumula pacientes sem exame (o rodapé mostrava "168 pacientes, 14 estudos")."""
from pydicom.uid import generate_uid


def _copia(ds_path, tmp, nome, serie=None, paciente=None):
    import pydicom
    ds = pydicom.dcmread(ds_path)
    if serie:
        ds.SeriesInstanceUID = serie
        ds.SOPInstanceUID = generate_uid()
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    if paciente:
        ds.PatientName, ds.PatientBirthDate = paciente
    out = tmp / nome
    ds.save_as(out)
    return out


def test_serie_nova_de_exame_existente_nao_cria_paciente(env, tmp_path, sample_dir):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    arq = sorted(p for p in sample_dir.rglob("*") if p.is_file())[0]
    Importer(db, paths.storage).import_paths([arq])
    antes = repo.counts()
    # um resultado de IA / SR do mesmo exame, com o nome escrito diferente e sem o nascimento
    outra = _copia(arq, tmp_path, "ia.dcm", serie=generate_uid(), paciente=("OUTRO^JEITO", ""))
    Importer(db, paths.storage).import_paths([outra])
    depois = repo.counts()
    assert depois["series"] == antes["series"] + 1
    assert depois["patients"] == antes["patients"]


def test_apagar_exame_limpa_os_pacientes_orfaos(env, sample_dir):
    from ipe.db.models import Patient
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    arq = sorted(p for p in sample_dir.rglob("*") if p.is_file())[0]
    Importer(db, paths.storage).import_paths([arq])
    with db.session() as s:                                     # órfãos de versões antigas
        s.add(Patient(patient_id="ORFAO1", name="ORFAO^UM"))
        s.add(Patient(patient_id="ORFAO2", name="ORFAO^DOIS"))
    assert repo.counts()["patients"] == 3
    assert repo.limpar_pacientes_sem_exame() == 2
    assert repo.counts()["patients"] == 1
    with db.session() as s:
        s.add(Patient(patient_id="ORFAO3", name="ORFAO^TRES"))
    uid = repo.search_studies(limit=5)[0].study_uid
    repo.delete_study(uid, paths.storage)
    assert repo.counts() == {"patients": 0, "studies": 0, "series": 0, "instances": 0}
