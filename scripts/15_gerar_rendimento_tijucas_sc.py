from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from _project_utils import (
    OUTPUTS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    RAW_DIR,
    ensure_directories,
    normalize_text,
    parse_int,
    print_status,
    write_csv_dicts,
)

TIJUCAS_CODIGO = "4218004"
TIJUCAS_NOME = "Tijucas"
UF_SC = "SC"
FONTE = "INEP/Censo Escolar - Taxas de Rendimento Escolar"
ATUALIZADO_EM = datetime.now().isoformat(timespec="seconds")

RAW_SEARCH_DIRS = [RAW_DIR / "rendimento_escolar", RAW_DIR]

WIDE_CSV = PROCESSED_DIR / "painel_educacao_rendimento_tijucas.csv"
LONG_CSV = PROCESSED_DIR / "painel_educacao_rendimento_tijucas_long.csv"
JSON_PATH = PROCESSED_DIR / "educacao_rendimento.json"
RELATORIO_MD = OUTPUTS_DIR / "relatorios" / "relatorio_rendimento_tijucas.md"

EXPORT_ROOT = PROJECT_ROOT / "exports" / "painel_educacao_tijucas"
EXPORT_PUBLIC_DATA = EXPORT_ROOT / "public_data"
EXPORT_DATA_PUBLISHED = EXPORT_ROOT / "data_published"
EXPORT_DATA_PROCESSED = EXPORT_ROOT / "data_processed"

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

LEGACY_HEADER_MAP = {
    1: "NU_ANO_CENSO",
    2: "NO_REGIAO",
    3: "SG_UF",
    4: "CO_MUNICIPIO",
    5: "NO_MUNICIPIO",
    6: "NO_CATEGORIA",
    7: "NO_DEPENDENCIA",
    8: "1_CAT_FUN",
    9: "1_CAT_FUN_AI",
    10: "1_CAT_FUN_AF",
    20: "1_CAT_MED",
    26: "2_CAT_FUN",
    27: "2_CAT_FUN_AI",
    28: "2_CAT_FUN_AF",
    38: "2_CAT_MED",
    44: "3_CAT_FUN",
    45: "3_CAT_FUN_AI",
    46: "3_CAT_FUN_AF",
    56: "3_CAT_MED",
}

WIDE_FIELD_MAP = [
    ("taxa_aprovacao_fundamental", "1_CAT_FUN"),
    ("taxa_aprovacao_anos_iniciais", "1_CAT_FUN_AI"),
    ("taxa_aprovacao_anos_finais", "1_CAT_FUN_AF"),
    ("taxa_aprovacao_ensino_medio", "1_CAT_MED"),
    ("taxa_reprovacao_fundamental", "2_CAT_FUN"),
    ("taxa_reprovacao_anos_iniciais", "2_CAT_FUN_AI"),
    ("taxa_reprovacao_anos_finais", "2_CAT_FUN_AF"),
    ("taxa_reprovacao_ensino_medio", "2_CAT_MED"),
    ("taxa_abandono_fundamental", "3_CAT_FUN"),
    ("taxa_abandono_anos_iniciais", "3_CAT_FUN_AI"),
    ("taxa_abandono_anos_finais", "3_CAT_FUN_AF"),
    ("taxa_abandono_ensino_medio", "3_CAT_MED"),
]

LONG_INDICATORS = [
    ("Ensino fundamental", "taxa_aprovacao", "Taxa de aprovação", "taxa_aprovacao_fundamental"),
    ("Anos iniciais", "taxa_aprovacao", "Taxa de aprovação", "taxa_aprovacao_anos_iniciais"),
    ("Anos finais", "taxa_aprovacao", "Taxa de aprovação", "taxa_aprovacao_anos_finais"),
    ("Ensino médio", "taxa_aprovacao", "Taxa de aprovação", "taxa_aprovacao_ensino_medio"),
    ("Ensino fundamental", "taxa_reprovacao", "Taxa de reprovação", "taxa_reprovacao_fundamental"),
    ("Anos iniciais", "taxa_reprovacao", "Taxa de reprovação", "taxa_reprovacao_anos_iniciais"),
    ("Anos finais", "taxa_reprovacao", "Taxa de reprovação", "taxa_reprovacao_anos_finais"),
    ("Ensino médio", "taxa_reprovacao", "Taxa de reprovação", "taxa_reprovacao_ensino_medio"),
    ("Ensino fundamental", "taxa_abandono", "Taxa de abandono", "taxa_abandono_fundamental"),
    ("Anos iniciais", "taxa_abandono", "Taxa de abandono", "taxa_abandono_anos_iniciais"),
    ("Anos finais", "taxa_abandono", "Taxa de abandono", "taxa_abandono_anos_finais"),
    ("Ensino médio", "taxa_abandono", "Taxa de abandono", "taxa_abandono_ensino_medio"),
]


def ensure_output_directories() -> None:
    ensure_directories()
    RELATORIO_MD.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    EXPORT_DATA_PUBLISHED.mkdir(parents=True, exist_ok=True)
    EXPORT_DATA_PROCESSED.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_year(text: str) -> str:
    match = re.search(r"(2014|2015|2016|2017|2018|2019|2020|2021|2022|2023|2024)", text or "")
    return match.group(1) if match else ""


def cell_value(cell, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_node = cell.find(f"{{{NS_MAIN}}}v")
    inline_node = cell.find(f"{{{NS_MAIN}}}is")

    if cell_type == "s" and value_node is not None and value_node.text:
        return shared_strings[int(value_node.text)]
    if cell_type == "inlineStr" and inline_node is not None:
        return "".join(text.text or "" for text in inline_node.findall(f".//{{{NS_MAIN}}}t"))
    if inline_node is not None:
        return "".join(text.text or "" for text in inline_node.findall(f".//{{{NS_MAIN}}}t"))
    if value_node is not None and value_node.text is not None:
        return value_node.text
    return ""


def column_index_from_ref(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref or "")
    if not letters:
        return 0
    total = 0
    for char in letters.group(0):
        total = total * 26 + (ord(char.upper()) - 64)
    return total


def normalize_sheet_name(name: str) -> str:
    return normalize_text(name).replace(" ", "")


def read_sheet_rows_from_xlsx_bytes(xlsx_bytes: bytes, sheet_name: str, header_row: int = 9, start_row: int = 10) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as xlsx:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in xlsx.namelist():
            shared_root = ET.fromstring(xlsx.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(f"{{{NS_MAIN}}}si"):
                shared_strings.append("".join(node.text or "" for node in item.findall(f".//{{{NS_MAIN}}}t")))

        workbook_root = ET.fromstring(xlsx.read("xl/workbook.xml"))
        rels_root = ET.fromstring(xlsx.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root.findall(f"{{{NS_REL}}}Relationship")}

        sheet_rid = ""
        for sheet in workbook_root.findall(f"{{{NS_MAIN}}}sheets/{{{NS_MAIN}}}sheet"):
            if normalize_sheet_name(sheet.attrib.get("name", "")) == normalize_sheet_name(sheet_name):
                sheet_rid = sheet.attrib.get(f"{{{NS_DOC_REL}}}id", "")
                break

        if not sheet_rid:
            raise ValueError(f"Aba '{sheet_name}' não encontrada no arquivo xlsx.")

        target = rel_map.get(sheet_rid, "")
        if not target:
            raise ValueError(f"Relacionamento da aba '{sheet_name}' não encontrado no arquivo xlsx.")

        worksheet_root = ET.fromstring(xlsx.read(f"xl/{target}"))

        header_map: dict[int, str] = {}
        rows_out: list[dict[str, str]] = []
        use_legacy_layout = False

        for row in worksheet_root.findall(f"{{{NS_MAIN}}}sheetData/{{{NS_MAIN}}}row"):
            row_number = parse_int(row.attrib.get("r"))
            cells = {}
            for cell in row.findall(f"{{{NS_MAIN}}}c"):
                ref = cell.attrib.get("r", "")
                col_index = column_index_from_ref(ref)
                cells[col_index] = cell_value(cell, shared_strings)

            if row_number == header_row:
                header_map = {index: str(value).strip() for index, value in cells.items() if str(value).strip()}
                if "NU_ANO_CENSO" not in header_map.values():
                    use_legacy_layout = True
                    header_map = dict(LEGACY_HEADER_MAP)
                continue

            if row_number < start_row or not header_map:
                continue

            record = {}
            has_value = False
            for index, header in header_map.items():
                value = str(cells.get(index, "")).strip()
                record[header] = value
                if value != "":
                    has_value = True
            if use_legacy_layout:
                year_value = str(record.get("NU_ANO_CENSO", "")).strip()
                if year_value == "" or not year_value.isdigit():
                    continue
            if has_value:
                rows_out.append(record)

        return rows_out


def read_xlsx_from_zip(zip_path: Path, xlsx_inner_name: str, sheet_name: str) -> list[dict[str, str]]:
    with zipfile.ZipFile(zip_path) as outer_zip:
        xlsx_bytes = outer_zip.read(xlsx_inner_name)
    return read_sheet_rows_from_xlsx_bytes(xlsx_bytes, sheet_name)


def find_rendimento_sources() -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen_years: set[str] = set()

    for search_dir in RAW_SEARCH_DIRS:
        if not search_dir.exists():
            continue

        for zip_path in sorted(search_dir.rglob("*.zip")):
            lower_name = zip_path.name.lower()
            if "tx_rend" not in lower_name:
                continue
            year = extract_year(zip_path.name)
            if not year or year in seen_years:
                continue
            with zipfile.ZipFile(zip_path) as outer_zip:
                xlsx_candidates = [name for name in outer_zip.namelist() if name.lower().endswith(".xlsx")]
                if not xlsx_candidates:
                    continue
                xlsx_inner_name = sorted(xlsx_candidates)[0]
                sources.append(
                    {
                        "year": year,
                        "path": str(zip_path),
                        "kind": "zip_xlsx",
                        "xlsx_inner_name": xlsx_inner_name,
                    }
                )
                seen_years.add(year)

        for xlsx_path in sorted(search_dir.rglob("*.xlsx")):
            lower_name = xlsx_path.name.lower()
            if "tx_rend" not in lower_name:
                continue
            year = extract_year(xlsx_path.name)
            if not year or year in seen_years:
                continue
            sources.append(
                {
                    "year": year,
                    "path": str(xlsx_path),
                    "kind": "xlsx",
                    "xlsx_inner_name": "",
                }
            )
            seen_years.add(year)

    sources.sort(key=lambda item: item["year"])
    return sources


def read_source_rows(source: dict[str, str]) -> list[dict[str, str]]:
    path = Path(source["path"])
    if source["kind"] == "zip_xlsx":
        return read_xlsx_from_zip(path, source["xlsx_inner_name"], "MUNICIPIOS")
    return read_sheet_rows_from_xlsx_bytes(path.read_bytes(), "MUNICIPIOS")


def parse_optional_float(value: str) -> float | None:
    normalized = str(value or "").strip()
    if normalized in {"", "--"}:
        return None
    try:
        return round(float(normalized.replace(",", ".")), 2)
    except ValueError:
        return None


def format_optional_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def build_wide_row(year: str, raw_row: dict[str, str], has_sc_reference: bool) -> dict[str, str]:
    row = {
        "ano": year,
        "territorio": TIJUCAS_NOME,
        "nivel_territorial": "Município",
        "codigo_municipio": TIJUCAS_CODIGO,
        "localizacao": str(raw_row.get("NO_CATEGORIA", "")).strip(),
        "dependencia": str(raw_row.get("NO_DEPENDENCIA", "")).strip(),
        "fonte": FONTE,
        "observacao_metodologica": (
            "Recorte Total, dependência administrativa Total. "
            + ("Há apenas base municipal carregada no projeto nesta etapa." if not has_sc_reference else "Há base municipal e referência estadual oficial carregadas.")
        ),
    }
    for output_field, source_field in WIDE_FIELD_MAP:
        row[output_field] = format_optional_float(parse_optional_float(raw_row.get(source_field, "")))
    return row


def build_long_rows(wide_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for wide_row in wide_rows:
        for etapa, codigo, nome, source_field in LONG_INDICATORS:
            rows.append(
                {
                    "ano": wide_row["ano"],
                    "territorio": wide_row["territorio"],
                    "nivel_territorial": wide_row["nivel_territorial"],
                    "codigo_municipio": wide_row["codigo_municipio"],
                    "etapa_ensino": etapa,
                    "indicador_codigo": codigo,
                    "indicador_nome": nome,
                    "valor": wide_row.get(source_field, ""),
                    "unidade": "%",
                    "fonte": wide_row["fonte"],
                    "observacao_metodologica": wide_row["observacao_metodologica"],
                }
            )
    return rows


def build_json_rows(wide_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for wide_row in wide_rows:
        payload = {
            "ano": parse_int(wide_row["ano"]),
            "territorio": wide_row["territorio"],
            "nivel_territorial": wide_row["nivel_territorial"],
            "codigo_municipio": parse_int(wide_row["codigo_municipio"]),
            "taxa_aprovacao_fundamental": parse_optional_float(wide_row.get("taxa_aprovacao_fundamental", "")),
            "taxa_reprovacao_fundamental": parse_optional_float(wide_row.get("taxa_reprovacao_fundamental", "")),
            "taxa_abandono_fundamental": parse_optional_float(wide_row.get("taxa_abandono_fundamental", "")),
            "taxa_aprovacao_anos_iniciais": parse_optional_float(wide_row.get("taxa_aprovacao_anos_iniciais", "")),
            "taxa_reprovacao_anos_iniciais": parse_optional_float(wide_row.get("taxa_reprovacao_anos_iniciais", "")),
            "taxa_abandono_anos_iniciais": parse_optional_float(wide_row.get("taxa_abandono_anos_iniciais", "")),
            "taxa_aprovacao_anos_finais": parse_optional_float(wide_row.get("taxa_aprovacao_anos_finais", "")),
            "taxa_reprovacao_anos_finais": parse_optional_float(wide_row.get("taxa_reprovacao_anos_finais", "")),
            "taxa_abandono_anos_finais": parse_optional_float(wide_row.get("taxa_abandono_anos_finais", "")),
            "taxa_aprovacao_ensino_medio": parse_optional_float(wide_row.get("taxa_aprovacao_ensino_medio", "")),
            "taxa_reprovacao_ensino_medio": parse_optional_float(wide_row.get("taxa_reprovacao_ensino_medio", "")),
            "taxa_abandono_ensino_medio": parse_optional_float(wide_row.get("taxa_abandono_ensino_medio", "")),
            "fonte": wide_row["fonte"],
            "observacao_metodologica": wide_row["observacao_metodologica"],
        }
        rows.append(payload)
    return rows


def build_report_markdown(
    processed_sources: list[dict[str, str]],
    years_processed: list[str],
    latest_row: dict[str, object] | None,
    state_files_found: list[str],
) -> str:
    lines = [
        "# Relatório de rendimento escolar de Tijucas",
        "",
        "## Anos processados",
        "",
        f"- {', '.join(years_processed) if years_processed else 'Nenhum ano processado.'}",
        "",
        "## Arquivos lidos",
        "",
    ]
    for source in processed_sources:
        if source["kind"] == "zip_xlsx":
            lines.append(f"- {source['year']}: `{source['path']}` -> `{source['xlsx_inner_name']}`")
        else:
            lines.append(f"- {source['year']}: `{source['path']}`")

    lines.extend(
        [
            "",
            "## Valores mais recentes de Tijucas",
            "",
        ]
    )
    if latest_row:
        lines.extend(
            [
                f"- Ano: {latest_row['ano']}",
                f"- Aprovação no ensino fundamental: {latest_row['taxa_aprovacao_fundamental']}",
                f"- Reprovação no ensino fundamental: {latest_row['taxa_reprovacao_fundamental']}",
                f"- Abandono no ensino fundamental: {latest_row['taxa_abandono_fundamental']}",
                f"- Aprovação nos anos iniciais: {latest_row['taxa_aprovacao_anos_iniciais']}",
                f"- Reprovação nos anos iniciais: {latest_row['taxa_reprovacao_anos_iniciais']}",
                f"- Abandono nos anos iniciais: {latest_row['taxa_abandono_anos_iniciais']}",
                f"- Aprovação nos anos finais: {latest_row['taxa_aprovacao_anos_finais']}",
                f"- Reprovação nos anos finais: {latest_row['taxa_reprovacao_anos_finais']}",
                f"- Abandono nos anos finais: {latest_row['taxa_abandono_anos_finais']}",
                f"- Aprovação no ensino médio: {latest_row['taxa_aprovacao_ensino_medio']}",
                f"- Reprovação no ensino médio: {latest_row['taxa_reprovacao_ensino_medio']}",
                f"- Abandono no ensino médio: {latest_row['taxa_abandono_ensino_medio']}",
            ]
        )
    else:
        lines.append("- Nenhum registro de Tijucas foi processado.")

    lines.extend(
        [
            "",
            "## Observação sobre Tijucas do Sul",
            "",
            "- O filtro do município foi feito por `CO_MUNICIPIO = 4218004`, além de `SG_UF = SC` e conferência de `NO_MUNICIPIO = Tijucas`.",
            "- Isso evita confusão com `Tijucas do Sul`, no Paraná.",
            "",
            "## Explicação dos prefixos",
            "",
            "- `1_` = Taxa de Aprovação",
            "- `2_` = Taxa de Reprovação",
            "- `3_` = Taxa de Abandono",
            "",
            "## Limitações",
            "",
            "- O projeto carregou apenas arquivos municipais de taxas de rendimento escolar.",
        ]
    )
    if state_files_found:
        lines.append("- Foram encontrados arquivos estaduais/UF no projeto.")
    else:
        lines.append("- Não foi encontrado arquivo oficial separado de UF/estado no projeto; por isso esta primeira base traz apenas Tijucas.")
    lines.extend(
        [
            "- O recorte usado foi `NO_CATEGORIA = Total` e `NO_DEPENDENCIA = Total`.",
            "- Valores `--` foram convertidos em nulo.",
            "- A leitura da planilha foi feita diretamente dos arquivos oficiais, considerando cabeçalho técnico na linha 9 e dados a partir da linha 10.",
            "",
            "## Instruções de cópia para o projeto principal",
            "",
            "- `exports/painel_educacao_tijucas/public_data/educacao_rendimento.json` → `poc_painel_tijucas/public/data/educacao/`",
            "- `exports/painel_educacao_tijucas/data_published/educacao_rendimento.json` → `poc_painel_tijucas/data/published/educacao/`",
            "- `exports/painel_educacao_tijucas/data_processed/painel_educacao_rendimento_tijucas.csv` → `poc_painel_tijucas/data/processed/educacao/`",
            "- `exports/painel_educacao_tijucas/data_processed/painel_educacao_rendimento_tijucas_long.csv` → `poc_painel_tijucas/data/processed/educacao/`",
            "",
            f"- Atualizado em: {ATUALIZADO_EM}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    ensure_output_directories()

    sources = find_rendimento_sources()
    if not sources:
        print_status("Nenhuma fonte de taxas de rendimento escolar foi encontrada em data/raw.")
        return

    state_files_found = [
        source["path"]
        for search_dir in RAW_SEARCH_DIRS
        if search_dir.exists()
        for source in [path for path in search_dir.rglob("*") if path.is_file()]
        if re.search(r"uf|ufs|estad", source.name.lower()) and "tx_rend" in source.name.lower()
    ]

    wide_rows: list[dict[str, str]] = []
    processed_sources: list[dict[str, str]] = []
    skipped_years: list[str] = []

    for source in sources:
        year = source["year"]
        print_status(f"Lendo taxas de rendimento de {year}.")
        rows = read_source_rows(source)
        matches = [
            row
            for row in rows
            if str(row.get("SG_UF", "")).strip() == UF_SC
            and str(row.get("CO_MUNICIPIO", "")).strip() == TIJUCAS_CODIGO
            and normalize_text(str(row.get("NO_MUNICIPIO", ""))) == normalize_text(TIJUCAS_NOME)
            and normalize_text(str(row.get("NO_CATEGORIA", ""))) == "total"
            and normalize_text(str(row.get("NO_DEPENDENCIA", ""))) == "total"
        ]

        if not matches:
            skipped_years.append(year)
            print_status(f"Nenhum registro Total/Total de Tijucas encontrado no ano {year}.")
            continue

        selected = matches[0]
        wide_rows.append(build_wide_row(year, selected, bool(state_files_found)))
        processed_sources.append(source)

    wide_rows.sort(key=lambda row: row["ano"])

    if not wide_rows:
        print_status("Nenhum registro de Tijucas pôde ser processado a partir das planilhas oficiais.")
        return

    long_rows = build_long_rows(wide_rows)
    json_rows = build_json_rows(wide_rows)

    write_csv_dicts(
        WIDE_CSV,
        wide_rows,
        [
            "ano",
            "territorio",
            "nivel_territorial",
            "codigo_municipio",
            "localizacao",
            "dependencia",
            "taxa_aprovacao_fundamental",
            "taxa_aprovacao_anos_iniciais",
            "taxa_aprovacao_anos_finais",
            "taxa_aprovacao_ensino_medio",
            "taxa_reprovacao_fundamental",
            "taxa_reprovacao_anos_iniciais",
            "taxa_reprovacao_anos_finais",
            "taxa_reprovacao_ensino_medio",
            "taxa_abandono_fundamental",
            "taxa_abandono_anos_iniciais",
            "taxa_abandono_anos_finais",
            "taxa_abandono_ensino_medio",
            "fonte",
            "observacao_metodologica",
        ],
    )
    write_csv_dicts(
        LONG_CSV,
        long_rows,
        [
            "ano",
            "territorio",
            "nivel_territorial",
            "codigo_municipio",
            "etapa_ensino",
            "indicador_codigo",
            "indicador_nome",
            "valor",
            "unidade",
            "fonte",
            "observacao_metodologica",
        ],
    )
    write_json(JSON_PATH, json_rows)

    write_json(EXPORT_PUBLIC_DATA / "educacao_rendimento.json", json_rows)
    write_json(EXPORT_DATA_PUBLISHED / "educacao_rendimento.json", json_rows)
    write_csv_dicts(EXPORT_DATA_PROCESSED / WIDE_CSV.name, wide_rows, list(wide_rows[0].keys()))
    write_csv_dicts(EXPORT_DATA_PROCESSED / LONG_CSV.name, long_rows, list(long_rows[0].keys()))

    latest_row = json_rows[-1] if json_rows else None
    report_markdown = build_report_markdown(processed_sources, [row["ano"] for row in wide_rows], latest_row, state_files_found)
    RELATORIO_MD.write_text(report_markdown, encoding="utf-8")

    print_status(f"Arquivo gerado: {WIDE_CSV}")
    print_status(f"Arquivo gerado: {LONG_CSV}")
    print_status(f"Arquivo gerado: {JSON_PATH}")
    print_status(f"Arquivo gerado: {RELATORIO_MD}")
    print_status(f"Arquivo gerado: {EXPORT_PUBLIC_DATA / 'educacao_rendimento.json'}")
    print_status(f"Arquivo gerado: {EXPORT_DATA_PUBLISHED / 'educacao_rendimento.json'}")
    print_status(f"Arquivo gerado: {EXPORT_DATA_PROCESSED / WIDE_CSV.name}")
    print_status(f"Arquivo gerado: {EXPORT_DATA_PROCESSED / LONG_CSV.name}")
    print_status(f"Anos processados: {[row['ano'] for row in wide_rows]}")
    if skipped_years:
        print_status(f"Anos sem registro Total/Total para Tijucas: {skipped_years}")
    if latest_row:
        print_status(
            "Valores de 2024 para Tijucas: "
            f"aprov_fund={latest_row['taxa_aprovacao_fundamental']}, "
            f"reprov_fund={latest_row['taxa_reprovacao_fundamental']}, "
            f"aband_fund={latest_row['taxa_abandono_fundamental']}, "
            f"aprov_ai={latest_row['taxa_aprovacao_anos_iniciais']}, "
            f"aprov_af={latest_row['taxa_aprovacao_anos_finais']}, "
            f"aprov_med={latest_row['taxa_aprovacao_ensino_medio']}"
        )
    print_status("Instruções de cópia para o projeto principal:")
    print_status("public_data/educacao_rendimento.json -> poc_painel_tijucas/public/data/educacao/")
    print_status("data_published/educacao_rendimento.json -> poc_painel_tijucas/data/published/educacao/")
    print_status("data_processed/painel_educacao_rendimento_tijucas.csv -> poc_painel_tijucas/data/processed/educacao/")
    print_status("data_processed/painel_educacao_rendimento_tijucas_long.csv -> poc_painel_tijucas/data/processed/educacao/")


if __name__ == "__main__":
    main()
