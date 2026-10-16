from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from _project_utils import (
    DIAGNOSTICOS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    RAW_DIR,
    ensure_directories,
    normalize_text,
    parse_int,
    print_status,
    read_csv_dicts,
    write_csv_dicts,
)

AMOSTRAS_CSV = DIAGNOSTICOS_DIR / "amostras_arquivos_dados.csv"
CODIGOS_TIJUCAS_CSV = DIAGNOSTICOS_DIR / "codigos_municipio_tijucas_detectados.csv"

ESCOLAS_CSV = PROCESSED_DIR / "microdados_tijucas_escolas_2014_2025.csv"
MATRICULAS_2025_CSV = PROCESSED_DIR / "microdados_tijucas_matriculas_2025.csv"
TURMAS_2025_CSV = PROCESSED_DIR / "microdados_tijucas_turmas_2025.csv"
DOCENTES_2025_CSV = PROCESSED_DIR / "microdados_tijucas_docentes_2025.csv"
GESTORES_2025_CSV = PROCESSED_DIR / "microdados_tijucas_gestores_2025.csv"

TARGET_FILES = {
    "escolas": ESCOLAS_CSV,
    "matriculas_2025": MATRICULAS_2025_CSV,
    "turmas_2025": TURMAS_2025_CSV,
    "docentes_2025": DOCENTES_2025_CSV,
    "gestores_2025": GESTORES_2025_CSV,
}

TARGET_BASENAMES = {
    "Tabela_Escola_2025.csv": "escolas",
    "Tabela_Matricula_2025.csv": "matriculas_2025",
    "Tabela_Turma_2025.csv": "turmas_2025",
    "Tabela_Docente_2025.csv": "docentes_2025",
    "Tabela_Gestor_Escolar_2025.csv": "gestores_2025",
}


def ensure_processed_directory() -> None:
    ensure_directories()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def get_sample_rows() -> list[dict[str, str]]:
    rows = read_csv_dicts(AMOSTRAS_CSV)
    return [row for row in rows if row.get("status") == "ok" and row.get("arquivo_interno")]


def classify_sample_file(row: dict[str, str]) -> str | None:
    internal_name = Path(row.get("arquivo_interno", "")).name
    if internal_name in TARGET_BASENAMES:
        return TARGET_BASENAMES[internal_name]

    year = row.get("ano_detectado", "")
    if year and year != "2025" and internal_name.lower().startswith("microdados_ed_basica_") and internal_name.lower().endswith(".csv"):
        return "escolas"

    return None


def select_files_to_process(sample_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for row in sample_rows:
        target_type = classify_sample_file(row)
        if not target_type:
            continue
        key = (row.get("arquivo_zip", ""), row.get("arquivo_interno", ""))
        if key in seen:
            continue
        seen.add(key)
        item = dict(row)
        item["target_type"] = target_type
        selected.append(item)

    priority = {"escolas": 0, "matriculas_2025": 1, "turmas_2025": 2, "docentes_2025": 3, "gestores_2025": 4}
    selected.sort(
        key=lambda row: (
            priority.get(row["target_type"], 99),
            parse_int(row.get("ano_detectado")),
            row.get("arquivo_interno", ""),
        )
    )
    return selected


def normalize_separator(separator: str) -> str:
    return "\t" if separator == "\\t" else separator


def municipality_matches_tijucas(row: dict[str, str], known_codes: set[str]) -> bool:
    city_name = normalize_text(row.get("NO_MUNICIPIO", ""))
    state = normalize_text(row.get("SG_UF", ""))
    code = (row.get("CO_MUNICIPIO", "") or "").strip()
    uf_code = (row.get("CO_UF", "") or "").strip()

    if "tijucas" in city_name and (not state or state == "sc" or uf_code == "42"):
        return True
    if code and code in known_codes and (not state or state == "sc" or uf_code == "42"):
        return True
    return False


def build_metadata_row(row: dict[str, str], sample: dict[str, str]) -> dict[str, str]:
    enriched = dict(row)
    enriched["ano_arquivo"] = sample.get("ano_detectado", "")
    enriched["arquivo_zip_origem"] = sample.get("arquivo_zip", "")
    enriched["arquivo_interno_origem"] = sample.get("arquivo_interno", "")
    return enriched


def collect_fieldnames(rows: list[dict[str, str]]) -> list[str]:
    preferred = ["ano_arquivo", "arquivo_zip_origem", "arquivo_interno_origem"]
    fieldnames: list[str] = []

    for field in preferred:
        if any(field in row for row in rows):
            fieldnames.append(field)

    for row in rows:
        for field in row.keys():
            if field not in fieldnames:
                fieldnames.append(field)
    return fieldnames


def stream_csv_from_zip(sample: dict[str, str]):
    zip_path_value = sample.get("caminho_zip", "")
    zip_path = PROJECT_ROOT / zip_path_value if zip_path_value else RAW_DIR / sample["arquivo_zip"]
    separator = normalize_separator(sample.get("separador_detectado", ";"))
    encoding = sample.get("encoding_detectado", "utf-8")
    internal_name = sample["arquivo_interno"]

    with zipfile.ZipFile(zip_path) as zip_file:
        with zip_file.open(internal_name) as binary_stream:
            text_stream = io.TextIOWrapper(binary_stream, encoding=encoding, newline="")
            reader = csv.DictReader(text_stream, delimiter=separator)
            for row in reader:
                yield row


def process_school_files(
    samples: list[dict[str, str]],
) -> tuple[list[dict[str, str]], set[str], set[str], list[dict[str, str]], dict[str, int]]:
    school_rows: list[dict[str, str]] = []
    known_codes: set[str] = set()
    entity_ids_2025: set[str] = set()
    municipality_records: list[dict[str, str]] = []
    counts = {"escolas": 0}

    municipality_counter: dict[tuple[str, str, str, str], int] = defaultdict(int)

    for sample in samples:
        if sample["target_type"] != "escolas":
            continue

        print_status(f"Lendo e filtrando escolas: {sample['arquivo_interno']}")
        matched_rows = 0
        for row in stream_csv_from_zip(sample):
            if not municipality_matches_tijucas(row, known_codes):
                continue

            matched_rows += 1
            code = (row.get("CO_MUNICIPIO", "") or "").strip()
            city = (row.get("NO_MUNICIPIO", "") or "").strip()
            state = (row.get("SG_UF", "") or "").strip()
            year = sample.get("ano_detectado", "")

            if code:
                known_codes.add(code)
            if year == "2025":
                entity_id = (row.get("CO_ENTIDADE", "") or "").strip()
                if entity_id:
                    entity_ids_2025.add(entity_id)

            municipality_counter[(year, code, city, state)] += 1
            school_rows.append(build_metadata_row(row, sample))

        counts["escolas"] += matched_rows
        print_status(f"Registros de escolas filtrados neste arquivo: {matched_rows}")

    for (year, code, city, state), quantity in sorted(municipality_counter.items()):
        municipality_records.append(
            {
                "ano": year,
                "co_municipio": code,
                "no_municipio": city,
                "sg_uf": state,
                "quantidade_registros": str(quantity),
            }
        )

    return school_rows, known_codes, entity_ids_2025, municipality_records, counts


def process_auxiliary_2025_files(
    samples: list[dict[str, str]],
    entity_ids_2025: set[str],
) -> tuple[dict[str, list[dict[str, str]]], dict[str, int]]:
    results = {target_type: [] for target_type in TARGET_FILES if target_type != "escolas"}
    counts = {target_type: 0 for target_type in TARGET_FILES if target_type != "escolas"}

    if not entity_ids_2025:
        print_status("Nenhuma escola de Tijucas foi identificada em 2025. As tabelas auxiliares de 2025 serão geradas vazias.")
        return results, counts

    for sample in samples:
        target_type = sample["target_type"]
        if target_type == "escolas":
            continue

        print_status(f"Lendo e filtrando {target_type}: {sample['arquivo_interno']}")
        matched_rows = 0
        for row in stream_csv_from_zip(sample):
            entity_id = (row.get("CO_ENTIDADE", "") or "").strip()
            if not entity_id or entity_id not in entity_ids_2025:
                continue
            matched_rows += 1
            results[target_type].append(build_metadata_row(row, sample))

        counts[target_type] += matched_rows
        print_status(f"Registros filtrados para {target_type}: {matched_rows}")

    return results, counts


def save_processed_output(path: Path, rows: list[dict[str, str]]) -> None:
    if rows:
        fieldnames = collect_fieldnames(rows)
    else:
        fieldnames = ["ano_arquivo", "arquivo_zip_origem", "arquivo_interno_origem"]
    write_csv_dicts(path, rows, fieldnames)


def main() -> None:
    ensure_processed_directory()
    sample_rows = get_sample_rows()

    if not sample_rows:
        print_status("Arquivo de amostras não encontrado ou vazio. Rode scripts\\03_ler_amostras_arquivos_dados.py antes.")
        return

    files_to_process = select_files_to_process(sample_rows)
    if not files_to_process:
        print_status("Nenhum arquivo-alvo foi identificado nos diagnósticos. Verifique outputs\\diagnosticos\\amostras_arquivos_dados.csv.")
        return

    print_status(f"Arquivos-alvo identificados para extração filtrada: {len(files_to_process)}")

    school_rows, known_codes, entity_ids_2025, municipality_records, school_counts = process_school_files(files_to_process)
    aux_results, aux_counts = process_auxiliary_2025_files(files_to_process, entity_ids_2025)

    save_processed_output(ESCOLAS_CSV, school_rows)
    save_processed_output(MATRICULAS_2025_CSV, aux_results["matriculas_2025"])
    save_processed_output(TURMAS_2025_CSV, aux_results["turmas_2025"])
    save_processed_output(DOCENTES_2025_CSV, aux_results["docentes_2025"])
    save_processed_output(GESTORES_2025_CSV, aux_results["gestores_2025"])

    write_csv_dicts(
        CODIGOS_TIJUCAS_CSV,
        municipality_records,
        ["ano", "co_municipio", "no_municipio", "sg_uf", "quantidade_registros"],
    )

    print_status(f"Códigos de município detectados para Tijucas: {sorted(known_codes) if known_codes else 'nenhum'}")
    print_status(f"Entidades escolares identificadas em 2025: {len(entity_ids_2025)}")
    print_status(f"Arquivo gerado: {ESCOLAS_CSV}")
    print_status(f"Arquivo gerado: {MATRICULAS_2025_CSV}")
    print_status(f"Arquivo gerado: {TURMAS_2025_CSV}")
    print_status(f"Arquivo gerado: {DOCENTES_2025_CSV}")
    print_status(f"Arquivo gerado: {GESTORES_2025_CSV}")
    print_status(f"Arquivo gerado: {CODIGOS_TIJUCAS_CSV}")
    print_status(
        "Resumo da extração filtrada: "
        f"escolas={school_counts['escolas']}, "
        f"matriculas_2025={aux_counts['matriculas_2025']}, "
        f"turmas_2025={aux_counts['turmas_2025']}, "
        f"docentes_2025={aux_counts['docentes_2025']}, "
        f"gestores_2025={aux_counts['gestores_2025']}"
    )


if __name__ == "__main__":
    main()
