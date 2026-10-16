from __future__ import annotations

import html
import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from _project_utils import (
    OUTPUTS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    TABELAS_DIR,
    ensure_directories,
    normalize_text,
    parse_float,
    parse_int,
    print_status,
    read_csv_dicts,
    write_csv_dicts,
)

RELATORIOS_DIR = OUTPUTS_DIR / "relatorios"
EXPORTS_DIR = PROJECT_ROOT / "exports" / "painel_educacao_tijucas"

ESCOLAS_CSV = PROCESSED_DIR / "microdados_tijucas_escolas_2014_2025.csv"
MATRICULAS_2025_CSV = PROCESSED_DIR / "microdados_tijucas_matriculas_2025.csv"
TURMAS_2025_CSV = PROCESSED_DIR / "microdados_tijucas_turmas_2025.csv"
DOCENTES_2025_CSV = PROCESSED_DIR / "microdados_tijucas_docentes_2025.csv"
GESTORES_2025_CSV = PROCESSED_DIR / "microdados_tijucas_gestores_2025.csv"

REDE_ESCOLAR_CSV = PROCESSED_DIR / "painel_educacao_tijucas_rede_escolar.csv"
MATRICULAS_CSV = PROCESSED_DIR / "painel_educacao_tijucas_matriculas.csv"
DOCENTES_TURMAS_CSV = PROCESSED_DIR / "painel_educacao_tijucas_docentes_turmas.csv"
INFRAESTRUTURA_CSV = PROCESSED_DIR / "painel_educacao_tijucas_infraestrutura.csv"
TECNOLOGIA_CSV = PROCESSED_DIR / "painel_educacao_tijucas_tecnologia_acessibilidade.csv"
MAPA_CSV = PROCESSED_DIR / "painel_educacao_tijucas_mapa_escolas.csv"
INDICADORES_LONG_CSV = PROCESSED_DIR / "painel_educacao_tijucas_indicadores_long.csv"
METADATA_JSON = PROCESSED_DIR / "metadata_educacao_tijucas.json"

RELATORIO_MD = RELATORIOS_DIR / "relatorio_bases_painel_educacao.md"
RELATORIO_HTML = RELATORIOS_DIR / "relatorio_bases_painel_educacao.html"

DEPENDENCIA_MAP = {"1": "Federal", "2": "Estadual", "3": "Municipal", "4": "Privada"}
LOCALIZACAO_MAP = {"1": "Urbana", "2": "Rural"}
ATUALIZADO_EM = datetime.now().isoformat(timespec="seconds")


def ensure_output_directories() -> None:
    ensure_directories()
    RELATORIOS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_csv_safe(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return read_csv_dicts(path)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_year(row: dict[str, str]) -> str:
    return (row.get("NU_ANO_CENSO") or row.get("ano_arquivo") or "").strip()


def get_entity(row: dict[str, str]) -> str:
    return (row.get("CO_ENTIDADE") or "").strip()


def merge_rows_by_school(
    school_rows: list[dict[str, str]],
    extra_tables: list[list[dict[str, str]]],
) -> list[dict[str, str]]:
    merged: dict[tuple[str, str], dict[str, str]] = {}

    for row in school_rows:
        key = (get_year(row), get_entity(row))
        if not key[0] or not key[1]:
            continue
        merged[key] = dict(row)

    for table_rows in extra_tables:
        for row in table_rows:
            key = (get_year(row), get_entity(row))
            if not key[0] or not key[1]:
                continue
            base = merged.setdefault(
                key,
                {
                    "NU_ANO_CENSO": key[0],
                    "CO_ENTIDADE": key[1],
                    "ano_arquivo": key[0],
                },
            )
            for field, value in row.items():
                if field in {"NU_ANO_CENSO", "CO_ENTIDADE"}:
                    continue
                if value != "":
                    base[field] = value

    return sorted(merged.values(), key=lambda row: (get_year(row), get_entity(row)))


def rows_by_year(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        year = get_year(row)
        if year:
            grouped[year].append(row)
    return dict(sorted(grouped.items()))


def values_available(rows: list[dict[str, str]], field: str) -> bool:
    return any(field in row and str(row.get(field, "")).strip() != "" for row in rows)


def numeric_value(row: dict[str, str], field: str) -> int:
    return parse_int(row.get(field, "0"))


def positive_numeric(row: dict[str, str], field: str) -> bool:
    return numeric_value(row, field) > 0


def positive_in_any(row: dict[str, str], fields: list[str]) -> bool:
    for field in fields:
        if field in row and str(row.get(field, "")).strip() != "":
            if positive_numeric(row, field):
                return True
    return False


def as_presence(row: dict[str, str], field: str) -> bool:
    value = str(row.get(field, "")).strip()
    if value == "":
        return False
    return value in {"1", "S", "SIM", "True", "true"} or parse_int(value) > 0


def add_missing(missing_registry: dict[str, list[str]], output_name: str, year: str, variables: list[str], reason: str) -> None:
    label = f"{year}: {', '.join(variables)} ({reason})"
    if label not in missing_registry[output_name]:
        missing_registry[output_name].append(label)


def active_school_rows(rows: list[dict[str, str]], missing_registry: dict[str, list[str]], output_name: str, year: str) -> list[dict[str, str]]:
    if not rows:
        return []
    if not values_available(rows, "TP_SITUACAO_FUNCIONAMENTO"):
        add_missing(missing_registry, output_name, year, ["TP_SITUACAO_FUNCIONAMENTO"], "usado total de escolas filtradas")
        return rows
    active = [row for row in rows if parse_int(row.get("TP_SITUACAO_FUNCIONAMENTO")) == 1]
    return active if active else rows


def sum_field(rows: list[dict[str, str]], field: str, missing_registry: dict[str, list[str]], output_name: str, year: str) -> int | None:
    if not values_available(rows, field):
        add_missing(missing_registry, output_name, year, [field], "variável ausente")
        return None
    return sum(numeric_value(row, field) for row in rows)


def sum_first_available(
    rows: list[dict[str, str]],
    options: list[list[str]],
    missing_registry: dict[str, list[str]],
    output_name: str,
    year: str,
) -> tuple[int | None, list[str], str]:
    for option in options:
        if all(values_available(rows, field) for field in option):
            return sum(sum(numeric_value(row, field) for field in option) for row in rows), option, "ok"
        if len(option) == 1 and values_available(rows, option[0]):
            return sum(numeric_value(row, option[0]) for row in rows), option, "ok"
    flattened = [field for option in options for field in option]
    add_missing(missing_registry, output_name, year, flattened, "nenhuma combinação disponível")
    return None, flattened, "missing"


def count_distinct_entities(rows: list[dict[str, str]], condition=None) -> int:
    entities = set()
    for row in rows:
        entity = get_entity(row)
        if not entity:
            continue
        if condition is not None and not condition(row):
            continue
        entities.add(entity)
    return len(entities)


def count_entities_with_positive(
    rows: list[dict[str, str]],
    fields: list[str],
    missing_registry: dict[str, list[str]],
    output_name: str,
    year: str,
) -> int | None:
    if not any(values_available(rows, field) for field in fields):
        add_missing(missing_registry, output_name, year, fields, "nenhuma variável disponível")
        return None
    return count_distinct_entities(rows, lambda row: positive_in_any(row, fields))


def percentage_from_presence(
    rows: list[dict[str, str]],
    fields: list[str],
    missing_registry: dict[str, list[str]],
    output_name: str,
    year: str,
    use_numeric_positive: bool = False,
) -> float | None:
    if not rows:
        return None
    available_fields = [field for field in fields if values_available(rows, field)]
    if not available_fields:
        add_missing(missing_registry, output_name, year, fields, "nenhuma variável disponível")
        return None

    def condition(row: dict[str, str]) -> bool:
        for field in available_fields:
            if use_numeric_positive:
                if positive_numeric(row, field):
                    return True
            elif as_presence(row, field):
                return True
        return False

    numerator = count_distinct_entities(rows, condition)
    denominator = count_distinct_entities(rows)
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100, 2)


def map_dependency(value: str) -> str:
    return DEPENDENCIA_MAP.get(str(parse_int(value)), value or "")


def map_location(value: str) -> str:
    return LOCALIZACAO_MAP.get(str(parse_int(value)), value or "")


def build_stage_summary(row: dict[str, str]) -> str:
    labels: list[str] = []
    checks = [
        ("Educação infantil", ["QT_MAT_INF", "IN_COMUM_CRECHE", "IN_COMUM_PRE"]),
        ("Creche", ["QT_MAT_INF_CRE", "IN_COMUM_CRECHE"]),
        ("Pré-escola", ["QT_MAT_INF_PRE", "IN_COMUM_PRE"]),
        ("Ensino fundamental", ["QT_MAT_FUND", "IN_COMUM_FUND_AI", "IN_COMUM_FUND_AF"]),
        ("Fundamental anos iniciais", ["QT_MAT_FUND_AI", "IN_COMUM_FUND_AI"]),
        ("Fundamental anos finais", ["QT_MAT_FUND_AF", "IN_COMUM_FUND_AF"]),
        ("Ensino médio", ["QT_MAT_MED", "IN_COMUM_MEDIO_MEDIO", "IN_COMUM_MEDIO_INTEGRADO", "IN_COMUM_MEDIO_FIC", "IN_COMUM_MEDIO_NORMAL"]),
        ("EJA", ["QT_MAT_EJA", "IN_EJA"]),
        ("Educação especial", ["QT_MAT_ESP", "IN_ESPECIAL_EXCLUSIVA", "IN_ESP_EXCLUSIVA_CRECHE", "IN_ESP_EXCLUSIVA_PRE", "IN_ESP_EXCLUSIVA_FUND_AI", "IN_ESP_EXCLUSIVA_FUND_AF", "IN_ESP_EXCLUSIVA_MEDIO_MEDIO", "IN_ESP_EXCLUSIVA_EJA_FUND", "IN_ESP_EXCLUSIVA_EJA_MEDIO"]),
    ]
    for label, fields in checks:
        if any((field in row and str(row.get(field, "")).strip() != "" and (positive_numeric(row, field) or as_presence(row, field))) for field in fields):
            labels.append(label)
    return " | ".join(labels)


def format_number(value: int | float | None, decimals: int = 2) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


def build_rede_escolar(rows_by_year_map: dict[str, list[dict[str, str]]], missing_registry: dict[str, list[str]]) -> list[dict[str, str]]:
    output_name = REDE_ESCOLAR_CSV.name
    result: list[dict[str, str]] = []

    for year, year_rows in rows_by_year_map.items():
        active_rows = active_school_rows(year_rows, missing_registry, output_name, year)
        row = {
            "ano": year,
            "escolas_funcionamento_total": str(count_distinct_entities(active_rows)),
            "escolas_municipais": str(count_distinct_entities(active_rows, lambda item: parse_int(item.get("TP_DEPENDENCIA")) == 3)),
            "escolas_estaduais": str(count_distinct_entities(active_rows, lambda item: parse_int(item.get("TP_DEPENDENCIA")) == 2)),
            "escolas_privadas": str(count_distinct_entities(active_rows, lambda item: parse_int(item.get("TP_DEPENDENCIA")) == 4)),
            "escolas_federais": str(count_distinct_entities(active_rows, lambda item: parse_int(item.get("TP_DEPENDENCIA")) == 1)),
            "escolas_urbanas": str(count_distinct_entities(active_rows, lambda item: parse_int(item.get("TP_LOCALIZACAO")) == 1)),
            "escolas_rurais": str(count_distinct_entities(active_rows, lambda item: parse_int(item.get("TP_LOCALIZACAO")) == 2)),
        }

        school_metric_fields = {
            "escolas_com_educacao_infantil": ["QT_MAT_INF", "QT_MAT_INF_CRE", "QT_MAT_INF_PRE", "IN_COMUM_CRECHE", "IN_COMUM_PRE"],
            "escolas_com_creche": ["QT_MAT_INF_CRE", "IN_COMUM_CRECHE"],
            "escolas_com_pre_escola": ["QT_MAT_INF_PRE", "IN_COMUM_PRE"],
            "escolas_com_fundamental": ["QT_MAT_FUND", "QT_MAT_FUND_AI", "QT_MAT_FUND_AF", "IN_COMUM_FUND_AI", "IN_COMUM_FUND_AF"],
            "escolas_com_fundamental_anos_iniciais": ["QT_MAT_FUND_AI", "IN_COMUM_FUND_AI"],
            "escolas_com_fundamental_anos_finais": ["QT_MAT_FUND_AF", "IN_COMUM_FUND_AF"],
            "escolas_com_eja": ["QT_MAT_EJA", "IN_EJA"],
            "escolas_com_educacao_especial": ["QT_MAT_ESP", "QT_MAT_ESP_CC", "QT_MAT_ESP_CE", "IN_ESPECIAL_EXCLUSIVA", "IN_ESP_EXCLUSIVA_CRECHE", "IN_ESP_EXCLUSIVA_PRE", "IN_ESP_EXCLUSIVA_FUND_AI", "IN_ESP_EXCLUSIVA_FUND_AF", "IN_ESP_EXCLUSIVA_MEDIO_MEDIO", "IN_ESP_EXCLUSIVA_EJA_FUND", "IN_ESP_EXCLUSIVA_EJA_MEDIO"],
        }
        for column, fields in school_metric_fields.items():
            count = count_entities_with_positive(active_rows, fields, missing_registry, output_name, year)
            row[column] = "" if count is None else str(count)

        result.append(row)
    return result


def build_matriculas(rows_by_year_map: dict[str, list[dict[str, str]]], missing_registry: dict[str, list[str]]) -> list[dict[str, str]]:
    output_name = MATRICULAS_CSV.name
    result: list[dict[str, str]] = []
    variable_map = {
        "matriculas_total_educacao_basica": ["QT_MAT_BAS"],
        "matriculas_educacao_infantil": ["QT_MAT_INF"],
        "matriculas_creche": ["QT_MAT_INF_CRE"],
        "matriculas_pre_escola": ["QT_MAT_INF_PRE"],
        "matriculas_ensino_fundamental": ["QT_MAT_FUND"],
        "matriculas_fundamental_anos_iniciais": ["QT_MAT_FUND_AI"],
        "matriculas_fundamental_anos_finais": ["QT_MAT_FUND_AF"],
        "matriculas_ensino_medio": ["QT_MAT_MED"],
        "matriculas_eja": ["QT_MAT_EJA"],
        "matriculas_educacao_especial": ["QT_MAT_ESP"],
        "matriculas_tempo_integral": ["QT_MAT_BAS_INT"],
    }
    for year, year_rows in rows_by_year_map.items():
        row = {"ano": year}
        for column, fields in variable_map.items():
            value = sum_field(year_rows, fields[0], missing_registry, output_name, year)
            row[column] = "" if value is None else str(value)
        result.append(row)
    return result


def build_docentes_turmas(
    rows_by_year_map: dict[str, list[dict[str, str]]],
    missing_registry: dict[str, list[str]],
) -> list[dict[str, str]]:
    output_name = DOCENTES_TURMAS_CSV.name
    result: list[dict[str, str]] = []
    variable_map = {
        "docentes_total": "QT_DOC_BAS",
        "docentes_educacao_infantil": "QT_DOC_INF",
        "docentes_ensino_fundamental": "QT_DOC_FUND",
        "docentes_fundamental_anos_iniciais": "QT_DOC_FUND_AI",
        "docentes_fundamental_anos_finais": "QT_DOC_FUND_AF",
        "docentes_ensino_medio": "QT_DOC_MED",
        "turmas_total": "QT_TUR_BAS",
        "turmas_educacao_infantil": "QT_TUR_INF",
        "turmas_ensino_fundamental": "QT_TUR_FUND",
        "turmas_fundamental_anos_iniciais": "QT_TUR_FUND_AI",
        "turmas_fundamental_anos_finais": "QT_TUR_FUND_AF",
        "turmas_ensino_medio": "QT_TUR_MED",
    }

    for year, year_rows in rows_by_year_map.items():
        row = {"ano": year}
        computed: dict[str, int | None] = {}
        for column, field in variable_map.items():
            value = sum_field(year_rows, field, missing_registry, output_name, year)
            computed[column] = value
            row[column] = "" if value is None else str(value)

        matriculas_total = sum_field(year_rows, "QT_MAT_BAS", missing_registry, output_name, year)
        turmas_total = computed["turmas_total"]
        docentes_total = computed["docentes_total"]

        row["matriculas_por_turma_aproximado"] = (
            format_number(round(matriculas_total / turmas_total, 4), 4)
            if matriculas_total is not None and turmas_total not in (None, 0)
            else ""
        )
        row["matriculas_por_docente_aproximado"] = (
            format_number(round(matriculas_total / docentes_total, 4), 4)
            if matriculas_total is not None and docentes_total not in (None, 0)
            else ""
        )
        if turmas_total in (None, 0):
            add_missing(missing_registry, output_name, year, ["QT_TUR_BAS"], "não foi possível calcular matrícula por turma")
        if docentes_total in (None, 0):
            add_missing(missing_registry, output_name, year, ["QT_DOC_BAS"], "não foi possível calcular matrícula por docente")
        result.append(row)
    return result


def build_infraestrutura(
    rows_by_year_map: dict[str, list[dict[str, str]]],
    missing_registry: dict[str, list[str]],
) -> list[dict[str, str]]:
    output_name = INFRAESTRUTURA_CSV.name
    result: list[dict[str, str]] = []
    percentage_fields = {
        "perc_escolas_agua_potavel": ["IN_AGUA_POTAVEL"],
        "perc_escolas_agua_rede_publica": ["IN_AGUA_REDE_PUBLICA"],
        "perc_escolas_energia_rede_publica": ["IN_ENERGIA_REDE_PUBLICA"],
        "perc_escolas_esgoto_rede_publica": ["IN_ESGOTO_REDE_PUBLICA"],
        "perc_escolas_banheiro": ["IN_BANHEIRO"],
        "perc_escolas_cozinha": ["IN_COZINHA"],
        "perc_escolas_refeitorio": ["IN_REFEITORIO"],
        "perc_escolas_biblioteca_ou_sala_leitura": ["IN_BIBLIOTECA", "IN_SALA_LEITURA", "IN_BIBLIOTECA_SALA_LEITURA"],
        "perc_escolas_laboratorio_informatica": ["IN_LABORATORIO_INFORMATICA"],
        "perc_escolas_laboratorio_ciencias": ["IN_LABORATORIO_CIENCIAS"],
        "perc_escolas_quadra_esportes": ["IN_QUADRA_ESPORTES"],
        "perc_escolas_parque_infantil": ["IN_PARQUE_INFANTIL"],
        "perc_escolas_patio_coberto": ["IN_PATIO_COBERTO"],
        "perc_escolas_patio_descoberto": ["IN_PATIO_DESCOBERTO"],
    }
    for year, year_rows in rows_by_year_map.items():
        active_rows = active_school_rows(year_rows, missing_registry, output_name, year)
        row = {
            "ano": year,
            "escolas_total_base_infraestrutura": str(count_distinct_entities(active_rows)),
        }
        for column, fields in percentage_fields.items():
            value = percentage_from_presence(active_rows, fields, missing_registry, output_name, year)
            row[column] = format_number(value)
        result.append(row)
    return result


def build_tecnologia(
    rows_by_year_map: dict[str, list[dict[str, str]]],
    missing_registry: dict[str, list[str]],
) -> list[dict[str, str]]:
    output_name = TECNOLOGIA_CSV.name
    result: list[dict[str, str]] = []
    percentage_fields = {
        "perc_escolas_internet": ["IN_INTERNET"],
        "perc_escolas_banda_larga": ["IN_BANDA_LARGA"],
        "perc_escolas_internet_alunos": ["IN_INTERNET_ALUNOS"],
        "perc_escolas_internet_aprendizagem": ["IN_INTERNET_APRENDIZAGEM"],
        "perc_escolas_acessibilidade_rampas": ["IN_ACESSIBILIDADE_RAMPAS"],
        "perc_escolas_banheiro_acessivel": ["IN_BANHEIRO_PNE"],
        "perc_escolas_salas_acessiveis": ["QT_SALAS_UTILIZADAS_ACESSIVEIS"],
        "perc_escolas_sem_recurso_acessibilidade": ["IN_ACESSIBILIDADE_INEXISTENTE"],
    }
    for year, year_rows in rows_by_year_map.items():
        active_rows = active_school_rows(year_rows, missing_registry, output_name, year)
        row = {"ano": year}
        for column, fields in percentage_fields.items():
            use_numeric_positive = column == "perc_escolas_salas_acessiveis"
            value = percentage_from_presence(
                active_rows,
                fields,
                missing_registry,
                output_name,
                year,
                use_numeric_positive=use_numeric_positive,
            )
            row[column] = format_number(value)

        total_computadores = sum_field(active_rows, "QT_COMPUTADOR", missing_registry, output_name, year)
        row["total_computadores"] = "" if total_computadores is None else str(total_computadores)

        total_comp_alunos, used_fields, _ = sum_first_available(
            active_rows,
            [["QT_COMP_ALUNO"], ["QT_DESKTOP_ALUNO", "QT_COMP_PORTATIL_ALUNO", "QT_TABLET_ALUNO"]],
            missing_registry,
            output_name,
            year,
        )
        row["total_computadores_alunos"] = "" if total_comp_alunos is None else str(total_comp_alunos)
        if used_fields != ["QT_COMP_ALUNO"] and total_comp_alunos is not None:
            add_missing(missing_registry, output_name, year, ["QT_COMP_ALUNO"], "usado somatório alternativo de equipamentos de alunos")
        result.append(row)
    return result


def build_mapa(
    rows_by_year_map: dict[str, list[dict[str, str]]],
    missing_registry: dict[str, list[str]],
) -> tuple[list[dict[str, str]], list[str]]:
    output_name = MAPA_CSV.name
    years_with_coordinates = []
    for year, year_rows in rows_by_year_map.items():
        if any(str(row.get("LATITUDE", "")).strip() and str(row.get("LONGITUDE", "")).strip() for row in year_rows):
            years_with_coordinates.append(year)

    map_years = years_with_coordinates
    if years_with_coordinates == ["2025"]:
        print_status("Latitude/longitude aparecem apenas em 2025. A base de mapa será gerada apenas para 2025.")
    elif not years_with_coordinates:
        add_missing(missing_registry, output_name, "todos", ["LATITUDE", "LONGITUDE"], "coordenadas não encontradas")
    else:
        map_years = sorted(rows_by_year_map.keys())

    result: list[dict[str, str]] = []
    for year in map_years:
        for row in rows_by_year_map.get(year, []):
            result.append(
                {
                    "ano": year,
                    "co_entidade": get_entity(row),
                    "nome_escola": row.get("NO_ENTIDADE", ""),
                    "dependencia_administrativa": map_dependency(row.get("TP_DEPENDENCIA", "")),
                    "localizacao": map_location(row.get("TP_LOCALIZACAO", "")),
                    "bairro": row.get("NO_BAIRRO", ""),
                    "endereco": row.get("DS_ENDERECO", ""),
                    "cep": row.get("CO_CEP", ""),
                    "latitude": row.get("LATITUDE", ""),
                    "longitude": row.get("LONGITUDE", ""),
                    "etapas_ofertadas_resumo": build_stage_summary(row),
                }
            )
    return result, years_with_coordinates


def build_indicator_rows(
    wide_rows: list[dict[str, str]],
    specs: dict[str, dict[str, str]],
    source_file: str,
    source_base: str,
) -> list[dict[str, str]]:
    indicators: list[dict[str, str]] = []
    for row in wide_rows:
        year = row.get("ano", "")
        for column, config in specs.items():
            value = row.get(column, "")
            if value == "":
                continue
            indicators.append(
                {
                    "ano": year,
                    "tema": config["tema"],
                    "indicador": config["indicador"],
                    "valor": value,
                    "unidade": config["unidade"],
                    "fonte": "Censo Escolar/INEP",
                    "base_origem": source_base,
                    "variaveis_usadas": config["variaveis"],
                    "nivel_agregacao": "município/ano",
                    "comparabilidade_2014_2025": config["comparabilidade"],
                    "observacao_metodologica": config["observacao"],
                    "atualizado_em": ATUALIZADO_EM,
                }
            )
    return indicators


def build_indicadores_long(
    rede_rows: list[dict[str, str]],
    matriculas_rows: list[dict[str, str]],
    docentes_rows: list[dict[str, str]],
    infraestrutura_rows: list[dict[str, str]],
    tecnologia_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    specs = {
        REDE_ESCOLAR_CSV.name: {
            "escolas_funcionamento_total": {
                "tema": "Rede escolar",
                "indicador": "Escolas em funcionamento",
                "unidade": "escolas",
                "variaveis": "CO_ENTIDADE, TP_SITUACAO_FUNCIONAMENTO",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Usa escolas filtradas de Tijucas/SC. Em 2025 a comparabilidade depende da estrutura multi-tabela.",
            },
            "escolas_municipais": {
                "tema": "Rede escolar",
                "indicador": "Escolas municipais",
                "unidade": "escolas",
                "variaveis": "CO_ENTIDADE, TP_DEPENDENCIA",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Contagem de escolas ativas com TP_DEPENDENCIA=3.",
            },
            "escolas_estaduais": {
                "tema": "Rede escolar",
                "indicador": "Escolas estaduais",
                "unidade": "escolas",
                "variaveis": "CO_ENTIDADE, TP_DEPENDENCIA",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Contagem de escolas ativas com TP_DEPENDENCIA=2.",
            },
            "escolas_privadas": {
                "tema": "Rede escolar",
                "indicador": "Escolas privadas",
                "unidade": "escolas",
                "variaveis": "CO_ENTIDADE, TP_DEPENDENCIA",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Contagem de escolas ativas com TP_DEPENDENCIA=4.",
            },
            "escolas_federais": {
                "tema": "Rede escolar",
                "indicador": "Escolas federais",
                "unidade": "escolas",
                "variaveis": "CO_ENTIDADE, TP_DEPENDENCIA",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Contagem de escolas ativas com TP_DEPENDENCIA=1.",
            },
            "escolas_urbanas": {
                "tema": "Rede escolar",
                "indicador": "Escolas urbanas",
                "unidade": "escolas",
                "variaveis": "CO_ENTIDADE, TP_LOCALIZACAO",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Contagem de escolas ativas com TP_LOCALIZACAO=1.",
            },
            "escolas_rurais": {
                "tema": "Rede escolar",
                "indicador": "Escolas rurais",
                "unidade": "escolas",
                "variaveis": "CO_ENTIDADE, TP_LOCALIZACAO",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Contagem de escolas ativas com TP_LOCALIZACAO=2.",
            },
            "escolas_com_educacao_infantil": {
                "tema": "Rede escolar",
                "indicador": "Escolas com educação infantil",
                "unidade": "escolas",
                "variaveis": "QT_MAT_INF, QT_MAT_INF_CRE, QT_MAT_INF_PRE, IN_COMUM_CRECHE, IN_COMUM_PRE",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Identifica oferta pela presença de matrículas ou flags equivalentes.",
            },
            "escolas_com_creche": {
                "tema": "Rede escolar",
                "indicador": "Escolas com creche",
                "unidade": "escolas",
                "variaveis": "QT_MAT_INF_CRE, IN_COMUM_CRECHE",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Identifica oferta pela presença de matrículas ou flags equivalentes.",
            },
            "escolas_com_pre_escola": {
                "tema": "Rede escolar",
                "indicador": "Escolas com pré-escola",
                "unidade": "escolas",
                "variaveis": "QT_MAT_INF_PRE, IN_COMUM_PRE",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Identifica oferta pela presença de matrículas ou flags equivalentes.",
            },
            "escolas_com_fundamental": {
                "tema": "Rede escolar",
                "indicador": "Escolas com ensino fundamental",
                "unidade": "escolas",
                "variaveis": "QT_MAT_FUND, QT_MAT_FUND_AI, QT_MAT_FUND_AF, IN_COMUM_FUND_AI, IN_COMUM_FUND_AF",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Identifica oferta pela presença de matrículas ou flags equivalentes.",
            },
            "escolas_com_fundamental_anos_iniciais": {
                "tema": "Rede escolar",
                "indicador": "Escolas com fundamental anos iniciais",
                "unidade": "escolas",
                "variaveis": "QT_MAT_FUND_AI, IN_COMUM_FUND_AI",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Identifica oferta pela presença de matrículas ou flags equivalentes.",
            },
            "escolas_com_fundamental_anos_finais": {
                "tema": "Rede escolar",
                "indicador": "Escolas com fundamental anos finais",
                "unidade": "escolas",
                "variaveis": "QT_MAT_FUND_AF, IN_COMUM_FUND_AF",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Identifica oferta pela presença de matrículas ou flags equivalentes.",
            },
            "escolas_com_eja": {
                "tema": "Rede escolar",
                "indicador": "Escolas com EJA",
                "unidade": "escolas",
                "variaveis": "QT_MAT_EJA, IN_EJA",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Identifica oferta pela presença de matrículas ou flags equivalentes.",
            },
            "escolas_com_educacao_especial": {
                "tema": "Rede escolar",
                "indicador": "Escolas com educação especial",
                "unidade": "escolas",
                "variaveis": "QT_MAT_ESP, QT_MAT_ESP_CC, QT_MAT_ESP_CE, IN_ESPECIAL_EXCLUSIVA e derivados",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Trata a presença de matrículas/flags de educação especial como proxy de oferta.",
            },
        },
        MATRICULAS_CSV.name: {
            "matriculas_total_educacao_basica": {
                "tema": "Atendimento escolar",
                "indicador": "Matrículas totais da educação básica",
                "unidade": "matrículas",
                "variaveis": "QT_MAT_BAS",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma das matrículas filtradas para escolas de Tijucas/SC.",
            },
            "matriculas_educacao_infantil": {
                "tema": "Atendimento escolar",
                "indicador": "Matrículas em educação infantil",
                "unidade": "matrículas",
                "variaveis": "QT_MAT_INF",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma das matrículas filtradas para escolas de Tijucas/SC.",
            },
            "matriculas_creche": {
                "tema": "Atendimento escolar",
                "indicador": "Matrículas em creche",
                "unidade": "matrículas",
                "variaveis": "QT_MAT_INF_CRE",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma das matrículas filtradas para escolas de Tijucas/SC.",
            },
            "matriculas_pre_escola": {
                "tema": "Atendimento escolar",
                "indicador": "Matrículas em pré-escola",
                "unidade": "matrículas",
                "variaveis": "QT_MAT_INF_PRE",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma das matrículas filtradas para escolas de Tijucas/SC.",
            },
            "matriculas_ensino_fundamental": {
                "tema": "Atendimento escolar",
                "indicador": "Matrículas em ensino fundamental",
                "unidade": "matrículas",
                "variaveis": "QT_MAT_FUND",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma das matrículas filtradas para escolas de Tijucas/SC.",
            },
            "matriculas_fundamental_anos_iniciais": {
                "tema": "Atendimento escolar",
                "indicador": "Matrículas em anos iniciais",
                "unidade": "matrículas",
                "variaveis": "QT_MAT_FUND_AI",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma das matrículas filtradas para escolas de Tijucas/SC.",
            },
            "matriculas_fundamental_anos_finais": {
                "tema": "Atendimento escolar",
                "indicador": "Matrículas em anos finais",
                "unidade": "matrículas",
                "variaveis": "QT_MAT_FUND_AF",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma das matrículas filtradas para escolas de Tijucas/SC.",
            },
            "matriculas_ensino_medio": {
                "tema": "Atendimento escolar",
                "indicador": "Matrículas em ensino médio",
                "unidade": "matrículas",
                "variaveis": "QT_MAT_MED",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma das matrículas filtradas para escolas de Tijucas/SC.",
            },
            "matriculas_eja": {
                "tema": "Atendimento escolar",
                "indicador": "Matrículas em EJA",
                "unidade": "matrículas",
                "variaveis": "QT_MAT_EJA",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma das matrículas filtradas para escolas de Tijucas/SC.",
            },
            "matriculas_educacao_especial": {
                "tema": "Atendimento escolar",
                "indicador": "Matrículas em educação especial",
                "unidade": "matrículas",
                "variaveis": "QT_MAT_ESP",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma das matrículas filtradas para escolas de Tijucas/SC.",
            },
            "matriculas_tempo_integral": {
                "tema": "Atendimento escolar",
                "indicador": "Matrículas em tempo integral",
                "unidade": "matrículas",
                "variaveis": "QT_MAT_BAS_INT",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Indicador calculado apenas quando a variável está disponível no ano.",
            },
        },
        DOCENTES_TURMAS_CSV.name: {
            "docentes_total": {
                "tema": "Docentes e turmas",
                "indicador": "Docentes totais",
                "unidade": "docentes",
                "variaveis": "QT_DOC_BAS",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de docentes filtrados para escolas de Tijucas/SC.",
            },
            "docentes_educacao_infantil": {
                "tema": "Docentes e turmas",
                "indicador": "Docentes em educação infantil",
                "unidade": "docentes",
                "variaveis": "QT_DOC_INF",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de docentes filtrados para escolas de Tijucas/SC.",
            },
            "docentes_ensino_fundamental": {
                "tema": "Docentes e turmas",
                "indicador": "Docentes em ensino fundamental",
                "unidade": "docentes",
                "variaveis": "QT_DOC_FUND",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de docentes filtrados para escolas de Tijucas/SC.",
            },
            "docentes_fundamental_anos_iniciais": {
                "tema": "Docentes e turmas",
                "indicador": "Docentes em anos iniciais",
                "unidade": "docentes",
                "variaveis": "QT_DOC_FUND_AI",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de docentes filtrados para escolas de Tijucas/SC.",
            },
            "docentes_fundamental_anos_finais": {
                "tema": "Docentes e turmas",
                "indicador": "Docentes em anos finais",
                "unidade": "docentes",
                "variaveis": "QT_DOC_FUND_AF",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de docentes filtrados para escolas de Tijucas/SC.",
            },
            "docentes_ensino_medio": {
                "tema": "Docentes e turmas",
                "indicador": "Docentes em ensino médio",
                "unidade": "docentes",
                "variaveis": "QT_DOC_MED",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de docentes filtrados para escolas de Tijucas/SC.",
            },
            "turmas_total": {
                "tema": "Docentes e turmas",
                "indicador": "Turmas totais",
                "unidade": "turmas",
                "variaveis": "QT_TUR_BAS",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de turmas filtradas para escolas de Tijucas/SC.",
            },
            "turmas_educacao_infantil": {
                "tema": "Docentes e turmas",
                "indicador": "Turmas em educação infantil",
                "unidade": "turmas",
                "variaveis": "QT_TUR_INF",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de turmas filtradas para escolas de Tijucas/SC.",
            },
            "turmas_ensino_fundamental": {
                "tema": "Docentes e turmas",
                "indicador": "Turmas em ensino fundamental",
                "unidade": "turmas",
                "variaveis": "QT_TUR_FUND",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de turmas filtradas para escolas de Tijucas/SC.",
            },
            "turmas_fundamental_anos_iniciais": {
                "tema": "Docentes e turmas",
                "indicador": "Turmas em anos iniciais",
                "unidade": "turmas",
                "variaveis": "QT_TUR_FUND_AI",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de turmas filtradas para escolas de Tijucas/SC.",
            },
            "turmas_fundamental_anos_finais": {
                "tema": "Docentes e turmas",
                "indicador": "Turmas em anos finais",
                "unidade": "turmas",
                "variaveis": "QT_TUR_FUND_AF",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de turmas filtradas para escolas de Tijucas/SC.",
            },
            "turmas_ensino_medio": {
                "tema": "Docentes e turmas",
                "indicador": "Turmas em ensino médio",
                "unidade": "turmas",
                "variaveis": "QT_TUR_MED",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Soma de turmas filtradas para escolas de Tijucas/SC.",
            },
            "matriculas_por_turma_aproximado": {
                "tema": "Docentes e turmas",
                "indicador": "Matrículas por turma aproximado",
                "unidade": "razão",
                "variaveis": "QT_MAT_BAS, QT_TUR_BAS",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Razão calculada localmente. Não é indicador oficial do INEP.",
            },
            "matriculas_por_docente_aproximado": {
                "tema": "Docentes e turmas",
                "indicador": "Matrículas por docente aproximado",
                "unidade": "razão",
                "variaveis": "QT_MAT_BAS, QT_DOC_BAS",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Razão calculada localmente. Não é indicador oficial do INEP.",
            },
        },
        INFRAESTRUTURA_CSV.name: {
            column: {
                "tema": "Infraestrutura",
                "indicador": column.replace("perc_escolas_", "").replace("_", " "),
                "unidade": "%",
                "variaveis": column,
                "comparabilidade": "comparável com adaptação",
                "observacao": "Percentual de escolas ativas com a característica indicada.",
            }
            for column in [
                "perc_escolas_agua_potavel",
                "perc_escolas_agua_rede_publica",
                "perc_escolas_energia_rede_publica",
                "perc_escolas_esgoto_rede_publica",
                "perc_escolas_banheiro",
                "perc_escolas_cozinha",
                "perc_escolas_refeitorio",
                "perc_escolas_biblioteca_ou_sala_leitura",
                "perc_escolas_laboratorio_informatica",
                "perc_escolas_laboratorio_ciencias",
                "perc_escolas_quadra_esportes",
                "perc_escolas_parque_infantil",
                "perc_escolas_patio_coberto",
                "perc_escolas_patio_descoberto",
            ]
        },
        TECNOLOGIA_CSV.name: {
            "perc_escolas_internet": {
                "tema": "Tecnologia e acessibilidade",
                "indicador": "Percentual de escolas com internet",
                "unidade": "%",
                "variaveis": "IN_INTERNET",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Percentual de escolas ativas com internet declarada.",
            },
            "perc_escolas_banda_larga": {
                "tema": "Tecnologia e acessibilidade",
                "indicador": "Percentual de escolas com banda larga",
                "unidade": "%",
                "variaveis": "IN_BANDA_LARGA",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Percentual de escolas ativas com banda larga declarada.",
            },
            "perc_escolas_internet_alunos": {
                "tema": "Tecnologia e acessibilidade",
                "indicador": "Percentual de escolas com internet para alunos",
                "unidade": "%",
                "variaveis": "IN_INTERNET_ALUNOS",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Percentual de escolas ativas com internet para alunos declarada.",
            },
            "perc_escolas_internet_aprendizagem": {
                "tema": "Tecnologia e acessibilidade",
                "indicador": "Percentual de escolas com internet para aprendizagem",
                "unidade": "%",
                "variaveis": "IN_INTERNET_APRENDIZAGEM",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Percentual de escolas ativas com uso declarado para aprendizagem.",
            },
            "total_computadores": {
                "tema": "Tecnologia e acessibilidade",
                "indicador": "Total de computadores",
                "unidade": "equipamentos",
                "variaveis": "QT_COMPUTADOR",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Total de computadores apenas quando a variável está disponível no ano.",
            },
            "total_computadores_alunos": {
                "tema": "Tecnologia e acessibilidade",
                "indicador": "Total de computadores para alunos",
                "unidade": "equipamentos",
                "variaveis": "QT_COMP_ALUNO ou soma de equipamentos de alunos",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Quando QT_COMP_ALUNO não existe, usa soma alternativa de equipamentos para alunos.",
            },
            "perc_escolas_acessibilidade_rampas": {
                "tema": "Tecnologia e acessibilidade",
                "indicador": "Percentual de escolas com rampas",
                "unidade": "%",
                "variaveis": "IN_ACESSIBILIDADE_RAMPAS",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Percentual de escolas ativas com presença declarada do recurso.",
            },
            "perc_escolas_banheiro_acessivel": {
                "tema": "Tecnologia e acessibilidade",
                "indicador": "Percentual de escolas com banheiro acessível",
                "unidade": "%",
                "variaveis": "IN_BANHEIRO_PNE",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Percentual de escolas ativas com presença declarada do recurso.",
            },
            "perc_escolas_salas_acessiveis": {
                "tema": "Tecnologia e acessibilidade",
                "indicador": "Percentual de escolas com salas acessíveis",
                "unidade": "%",
                "variaveis": "QT_SALAS_UTILIZADAS_ACESSIVEIS",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Percentual de escolas ativas com pelo menos uma sala acessível declarada.",
            },
            "perc_escolas_sem_recurso_acessibilidade": {
                "tema": "Tecnologia e acessibilidade",
                "indicador": "Percentual de escolas sem recurso de acessibilidade",
                "unidade": "%",
                "variaveis": "IN_ACESSIBILIDADE_INEXISTENTE",
                "comparabilidade": "comparável com adaptação",
                "observacao": "Percentual de escolas ativas com inexistência declarada de recurso de acessibilidade.",
            },
        },
    }

    indicators = []
    indicators.extend(build_indicator_rows(rede_rows, specs[REDE_ESCOLAR_CSV.name], REDE_ESCOLAR_CSV.name, REDE_ESCOLAR_CSV.name))
    indicators.extend(build_indicator_rows(matriculas_rows, specs[MATRICULAS_CSV.name], MATRICULAS_CSV.name, MATRICULAS_CSV.name))
    indicators.extend(build_indicator_rows(docentes_rows, specs[DOCENTES_TURMAS_CSV.name], DOCENTES_TURMAS_CSV.name, DOCENTES_TURMAS_CSV.name))
    indicators.extend(build_indicator_rows(infraestrutura_rows, specs[INFRAESTRUTURA_CSV.name], INFRAESTRUTURA_CSV.name, INFRAESTRUTURA_CSV.name))
    indicators.extend(build_indicator_rows(tecnologia_rows, specs[TECNOLOGIA_CSV.name], TECNOLOGIA_CSV.name, TECNOLOGIA_CSV.name))
    return indicators


def file_stats(path: Path) -> dict[str, object]:
    rows = load_csv_safe(path)
    years = sorted({row.get("ano", "") for row in rows if row.get("ano")})
    columns = list(rows[0].keys()) if rows else []
    return {
        "arquivo": path.name,
        "linhas": len(rows),
        "colunas": len(columns),
        "anos": years,
        "tamanho_bytes": path.stat().st_size if path.exists() else 0,
        "colunas_lista": columns,
    }


def markdown_to_html(markdown_text: str) -> str:
    html_lines = [
        "<!DOCTYPE html>",
        '<html lang="pt-BR">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Relatório das bases do painel de educação</title>",
        "<style>",
        "body { font-family: 'Segoe UI', Arial, sans-serif; margin: 40px auto; max-width: 1100px; line-height: 1.6; color: #1f2933; padding: 0 24px; }",
        "h1, h2, h3 { color: #102a43; }",
        "table { border-collapse: collapse; width: 100%; margin: 16px 0 24px; font-size: 14px; }",
        "th, td { border: 1px solid #cbd2d9; padding: 8px 10px; text-align: left; vertical-align: top; }",
        "th { background: #f0f4f8; }",
        "code { background: #f0f4f8; padding: 1px 4px; border-radius: 4px; }",
        "</style>",
        "</head>",
        "<body>",
    ]

    lines = markdown_text.splitlines()
    paragraph_buffer: list[str] = []
    list_buffer: list[str] = []
    table_buffer: list[str] = []

    def format_inline(text: str) -> str:
        escaped = html.escape(text)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        return escaped

    def flush_paragraph() -> None:
        if paragraph_buffer:
            html_lines.append(f"<p>{format_inline(' '.join(paragraph_buffer))}</p>")
            paragraph_buffer.clear()

    def flush_list() -> None:
        if list_buffer:
            html_lines.append("<ul>")
            for item in list_buffer:
                html_lines.append(f"<li>{format_inline(item)}</li>")
            html_lines.append("</ul>")
            list_buffer.clear()

    def flush_table() -> None:
        if not table_buffer:
            return
        rows = []
        for line in table_buffer:
            parts = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows.append(parts)
        if len(rows) >= 2:
            header = rows[0]
            body = rows[2:]
            html_lines.append("<table>")
            html_lines.append("<thead><tr>" + "".join(f"<th>{format_inline(cell)}</th>" for cell in header) + "</tr></thead>")
            html_lines.append("<tbody>")
            for row in body:
                html_lines.append("<tr>" + "".join(f"<td>{format_inline(cell)}</td>" for cell in row) + "</tr>")
            html_lines.append("</tbody></table>")
        table_buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            flush_table()
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            flush_list()
            table_buffer.append(stripped)
            continue
        if table_buffer:
            flush_table()
        if stripped.startswith("### "):
            flush_paragraph()
            flush_list()
            html_lines.append(f"<h3>{format_inline(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            html_lines.append(f"<h2>{format_inline(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            flush_list()
            html_lines.append(f"<h1>{format_inline(stripped[2:])}</h1>")
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            list_buffer.append(stripped[2:])
            continue
        flush_list()
        paragraph_buffer.append(stripped)

    flush_paragraph()
    flush_list()
    flush_table()
    html_lines.extend(["</body>", "</html>"])
    return "\n".join(html_lines)


def build_report_markdown(
    stats: list[dict[str, object]],
    indicators_long: list[dict[str, str]],
    missing_registry: dict[str, list[str]],
    years_with_coordinates: list[str],
) -> str:
    generated_files = [stat["arquivo"] for stat in stats]
    generated_indicator_names = sorted({row["indicador"] for row in indicators_long})
    missing_lines = []
    for output_name, issues in sorted(missing_registry.items()):
        if not issues:
            continue
        missing_lines.append(f"### {output_name}")
        missing_lines.append("")
        for issue in issues:
            missing_lines.append(f"- {issue}")
        missing_lines.append("")

    lines = [
        "# Relatório das bases finais do painel de educação de Tijucas/SC",
        "",
        "## Arquivos finais gerados",
        "",
        "| arquivo | linhas | colunas | anos cobertos | tamanho (bytes) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for stat in stats:
        years_text = " | ".join(stat["anos"]) if stat["anos"] else "-"
        lines.append(
            f"| {stat['arquivo']} | {stat['linhas']} | {stat['colunas']} | {years_text} | {stat['tamanho_bytes']} |"
        )
    lines.extend(
        [
            "",
            "## Indicadores calculados",
            "",
        ]
    )
    for indicator in generated_indicator_names:
        lines.append(f"- {indicator}")
    lines.extend(
        [
            "",
            "## Indicadores não calculados e motivo",
            "",
            "- IDEB, Saeb, aprovação, reprovação, abandono e distorção idade-série não foram incluídos porque exigem bases complementares do INEP.",
            "- Indicadores dependentes de variáveis ausentes em algum ano foram deixados em branco na base final correspondente e registrados nas observações abaixo.",
            "",
            "## Variáveis ausentes relevantes",
            "",
        ]
    )
    if missing_lines:
        lines.extend(missing_lines)
    else:
        lines.append("- Não foram registradas ausências relevantes além das limitações já conhecidas de 2025.")
        lines.append("")

    lines.extend(
        [
            "## Limitações",
            "",
            "- As bases finais são derivadas do Censo Escolar/INEP filtrado para Tijucas/SC.",
            "- Razões como matrículas por turma e matrículas por docente são aproximações locais e não indicadores oficiais do INEP.",
            "- Indicadores com variáveis ausentes em algum ano permanecem vazios naquele recorte temporal.",
            "",
            "## Cuidados sobre 2025",
            "",
            "- Em 2025, a estrutura deixou de ser um arquivo consolidado e passou a ser multi-tabela.",
            "- Para preservar comparabilidade, a geração das bases agregou as tabelas temáticas de 2025 ao nível escola/ano antes de produzir os indicadores municipais.",
            "- A maior parte dos indicadores deve ser interpretada como `comparável com adaptação` ao longo de 2014-2025.",
        ]
    )
    if years_with_coordinates == ["2025"]:
        lines.append("- O arquivo de mapa foi gerado apenas para 2025 porque latitude e longitude só apareceram de forma explícita nesse ano.")
    lines.extend(
        [
            "",
            "## Orientação para uso no projeto principal do painel",
            "",
            "- Copiar apenas os arquivos finais da pasta `exports/painel_educacao_tijucas/`.",
            "- Não levar microdados brutos nem bases intermediárias para o projeto principal.",
            "- Tratar `painel_educacao_tijucas_indicadores_long.csv` como base principal para cartões, séries e comparações anuais.",
            "- Usar `painel_educacao_tijucas_mapa_escolas.csv` apenas como mapa de equipamentos educacionais.",
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def copy_exports(files: list[Path]) -> None:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for path in files:
        if path.exists():
            shutil.copy2(path, EXPORTS_DIR / path.name)


def main() -> None:
    ensure_output_directories()

    school_rows = load_csv_safe(ESCOLAS_CSV)
    matriculas_2025_rows = load_csv_safe(MATRICULAS_2025_CSV)
    turmas_2025_rows = load_csv_safe(TURMAS_2025_CSV)
    docentes_2025_rows = load_csv_safe(DOCENTES_2025_CSV)
    gestores_2025_rows = load_csv_safe(GESTORES_2025_CSV)

    if not school_rows:
        print_status("Base filtrada de escolas não encontrada. Rode scripts\\08_extrair_tijucas_microdados.py antes.")
        return

    print_status("Unificando a base escolar filtrada com as tabelas auxiliares de 2025.")
    unified_rows = merge_rows_by_school(
        school_rows,
        [matriculas_2025_rows, turmas_2025_rows, docentes_2025_rows, gestores_2025_rows],
    )
    rows_year_map = rows_by_year(unified_rows)

    missing_registry: dict[str, list[str]] = defaultdict(list)

    print_status("Gerando base final de rede escolar.")
    rede_rows = build_rede_escolar(rows_year_map, missing_registry)
    print_status("Gerando base final de matrículas.")
    matriculas_rows = build_matriculas(rows_year_map, missing_registry)
    print_status("Gerando base final de docentes e turmas.")
    docentes_turmas_rows = build_docentes_turmas(rows_year_map, missing_registry)
    print_status("Gerando base final de infraestrutura.")
    infraestrutura_rows = build_infraestrutura(rows_year_map, missing_registry)
    print_status("Gerando base final de tecnologia e acessibilidade.")
    tecnologia_rows = build_tecnologia(rows_year_map, missing_registry)
    print_status("Gerando base final de mapa das escolas.")
    mapa_rows, years_with_coordinates = build_mapa(rows_year_map, missing_registry)
    print_status("Gerando base consolidada em formato longo.")
    indicadores_long_rows = build_indicadores_long(
        rede_rows,
        matriculas_rows,
        docentes_turmas_rows,
        infraestrutura_rows,
        tecnologia_rows,
    )

    write_csv_dicts(REDE_ESCOLAR_CSV, rede_rows, list(rede_rows[0].keys()) if rede_rows else ["ano"])
    write_csv_dicts(MATRICULAS_CSV, matriculas_rows, list(matriculas_rows[0].keys()) if matriculas_rows else ["ano"])
    write_csv_dicts(DOCENTES_TURMAS_CSV, docentes_turmas_rows, list(docentes_turmas_rows[0].keys()) if docentes_turmas_rows else ["ano"])
    write_csv_dicts(INFRAESTRUTURA_CSV, infraestrutura_rows, list(infraestrutura_rows[0].keys()) if infraestrutura_rows else ["ano"])
    write_csv_dicts(TECNOLOGIA_CSV, tecnologia_rows, list(tecnologia_rows[0].keys()) if tecnologia_rows else ["ano"])
    write_csv_dicts(MAPA_CSV, mapa_rows, list(mapa_rows[0].keys()) if mapa_rows else ["ano"])
    write_csv_dicts(
        INDICADORES_LONG_CSV,
        indicadores_long_rows,
        list(indicadores_long_rows[0].keys()) if indicadores_long_rows else [
            "ano",
            "tema",
            "indicador",
            "valor",
            "unidade",
            "fonte",
            "base_origem",
            "variaveis_usadas",
            "nivel_agregacao",
            "comparabilidade_2014_2025",
            "observacao_metodologica",
            "atualizado_em",
        ],
    )

    generated_files = [
        REDE_ESCOLAR_CSV,
        MATRICULAS_CSV,
        DOCENTES_TURMAS_CSV,
        INFRAESTRUTURA_CSV,
        TECNOLOGIA_CSV,
        MAPA_CSV,
        INDICADORES_LONG_CSV,
    ]

    indicators_not_included = [
        "IDEB",
        "Saeb",
        "aprovação",
        "reprovação",
        "abandono",
        "distorção idade-série",
    ]
    metadata_payload = {
        "nome_do_pacote": "painel_educacao_tijucas",
        "municipio": "Tijucas",
        "uf": "SC",
        "fonte_principal": "Censo Escolar/INEP",
        "bases_utilizadas": [
            ESCOLAS_CSV.name,
            MATRICULAS_2025_CSV.name,
            TURMAS_2025_CSV.name,
            DOCENTES_2025_CSV.name,
            GESTORES_2025_CSV.name,
        ],
        "anos_processados": sorted(rows_year_map.keys()),
        "arquivos_gerados": [path.name for path in generated_files] + [METADATA_JSON.name, RELATORIO_HTML.name],
        "indicadores_gerados": sorted({row["indicador"] for row in indicadores_long_rows}),
        "indicadores_nao_incluidos": indicators_not_included,
        "observacoes_metodologicas": [
            "Fonte principal: Censo Escolar/INEP.",
            "As bases finais foram filtradas para Tijucas/SC e agregadas para consumo em painel público.",
            "Matrículas por turma e matrículas por docente são aproximações locais, não indicadores oficiais do INEP.",
            "Em 2025, a comparabilidade exige adaptação porque a estrutura passou a ser multi-tabela.",
            "Se latitude e longitude apareceram apenas em 2025, a base de mapa foi restrita a esse ano.",
            "Estes arquivos não contêm diretamente IDEB, Saeb, aprovação, reprovação, abandono e distorção idade-série, salvo se alguma variável específica tiver sido encontrada.",
            "Para esses indicadores, será necessário baixar bases complementares do INEP.",
        ],
        "cuidados_publicacao": [
            "Evitar ranking de escolas.",
            "Não publicar dados individualizados de estudantes, docentes ou gestores.",
            "Usar a base de mapa como inventário de equipamentos educacionais, não como mapa de desempenho.",
            "Documentar a fonte, o ano de referência e a comparabilidade de cada indicador no painel.",
        ],
        "data_geracao": ATUALIZADO_EM,
    }
    write_json(METADATA_JSON, metadata_payload)

    stats_paths = generated_files + [METADATA_JSON]
    stats = [file_stats(path) for path in generated_files]

    report_markdown = build_report_markdown(stats, indicadores_long_rows, missing_registry, years_with_coordinates)
    RELATORIO_MD.write_text(report_markdown, encoding="utf-8")
    RELATORIO_HTML.write_text(markdown_to_html(report_markdown), encoding="utf-8")

    export_files = generated_files + [METADATA_JSON, RELATORIO_HTML]
    copy_exports(export_files)

    print_status(f"Arquivo gerado: {REDE_ESCOLAR_CSV}")
    print_status(f"Arquivo gerado: {MATRICULAS_CSV}")
    print_status(f"Arquivo gerado: {DOCENTES_TURMAS_CSV}")
    print_status(f"Arquivo gerado: {INFRAESTRUTURA_CSV}")
    print_status(f"Arquivo gerado: {TECNOLOGIA_CSV}")
    print_status(f"Arquivo gerado: {MAPA_CSV}")
    print_status(f"Arquivo gerado: {INDICADORES_LONG_CSV}")
    print_status(f"Arquivo gerado: {METADATA_JSON}")
    print_status(f"Arquivo gerado: {RELATORIO_MD}")
    print_status(f"Arquivo gerado: {RELATORIO_HTML}")
    print_status(f"Arquivos exportados para: {EXPORTS_DIR}")

    for stat in stats:
        print_status(
            f"Resumo {stat['arquivo']}: linhas={stat['linhas']}, colunas={stat['colunas']}, anos={stat['anos']}, tamanho_bytes={stat['tamanho_bytes']}"
        )

    if missing_registry:
        for output_name, issues in sorted(missing_registry.items()):
            preview = "; ".join(issues[:5])
            print_status(f"Variáveis ausentes ou adaptações em {output_name}: {preview}")

    print_status("Comparabilidade 2025: tratar a maior parte dos indicadores como 'comparável com adaptação'.")
    print_status("Recomendação de exportação: usar apenas os arquivos em exports\\painel_educacao_tijucas no projeto principal do painel.")


if __name__ == "__main__":
    main()
