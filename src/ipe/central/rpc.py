"""Métodos do banco que os clientes podem chamar no servidor central, e a permissão de cada um."""

from __future__ import annotations

# método -> permissão exigida ("" = qualquer usuário logado)
RPC_METHODS: dict[str, str] = {
    # leitura de exames
    "search_studies": "view", "find_study_uids": "view", "study_info": "view", "series_for_study": "view",
    "series_meta": "view", "series_info": "view", "instances_for_series": "view", "study_uids_present": "view",
    "instance_counts": "view", "studies_of_patient": "view", "other_studies_same_patient": "view",
    "counts": "view", "has_thumbnail": "view", "files_for_study": "view", "sop_uids_for_study": "view",
    # o que o médico marca (central)
    "comments": "view", "add_comment": "view", "mark_opened": "view",
    "key_images": "view", "key_image_set": "view", "toggle_key_image": "view",
    "annotations_for_series": "view", "save_annotation": "view", "delete_annotation": "view",
    "annotation_counts": "view", "count_annotations": "view",
    "get_registration": "view", "save_registration": "view",
    "series_groups": "view", "series_group": "view", "save_series_group": "view", "delete_series_group": "view",
    # lesões e laudos
    "lesions": "view", "save_lesion": "view", "delete_lesion": "view", "lesion_track": "view",
    "save_lesion_track": "view", "annotations_for_studies": "view",
    "reports": "view", "report": "view", "report_counts": "view",
    "save_report": "report", "delete_report": "report", "sign_report": "sign_report",
    "report_templates": "view", "save_report_templates": "report",
    # listas de casos
    # (leitura liberada para a interface não quebrar; quem não tem a permissão nem vê o painel)
    "case_lists": "view", "case_list_tree": "view", "case_list_info": "view",
    "smart_study_uids": "view", "study_uids_in_list": "view", "list_items": "view",
    "lists_of_study": "view", "create_case_list": "case_lists", "update_case_list": "case_lists",
    "delete_case_list": "case_lists", "duplicate_case_list": "case_lists", "add_to_case_list": "case_lists",
    "update_list_item": "case_lists", "remove_from_case_list": "case_lists", "reorder_case_list": "case_lists",
    # filmes
    "films": "view", "film_data": "view", "study_uids_in_films": "view",
    "save_film": "print", "mark_film_printed": "print", "delete_film": "print",
    # proteção e exclusão
    "set_locked": "delete", "delete_study": "delete",
    # usuários e configurações centrais
    "users": "users", "user_count": "users", "save_user": "users", "set_password": "users",
    "delete_user": "users", "access_log": "users", "set_app_setting": "users", "get_app_setting": "",
    "audit": "",
}

# métodos cujo argumento de caminho é do servidor (o cliente não manda)
SERVER_STORAGE_ARG = {"delete_study"}
