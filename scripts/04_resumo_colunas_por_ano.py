from __future__ import annotations

from collections import defaultdict

from _project_utils import (
    DIAGNOSTICOS_DIR,
    TABELAS_DIR,
    ensure_directories,
    json_loads_list,
    parse_int,
    print_status,
    read_csv_dicts,
    write_csv_dicts,
)

AMOSTRAS_CSV = DIAGNOSTICOS_DIR / "amostras_arquivos_dados.csv"
COLUNAS_POR_ANO_CSV = TABELAS_DIR / "colunas_por_ano.csv"
FREQUENCIA_COLUNAS_CSV = TABELAS_DIR / "frequencia_colunas.csv"


def main() -> None:
    ensure_directories()
    rows = read_csv_dicts(AMOSTRAS_CSV)
    valid_rows = [row for row in rows if row.get("status") == "ok" and row.get("nomes_colunas")]

    if not valid_rows:
        write_csv_dicts(
            COLUNAS_POR_ANO_CSV,
            [],
            ["ano_detectado", "coluna", "quantidade_arquivos", "arquivos_exemplo"],
        )
        write_csv_dicts(
            FREQUENCIA_COLUNAS_CSV,
            [],
            ["coluna", "quantidade_anos", "anos_detectados", "quantidade_arquivos"],
        )
        print_status(
            "Nenhuma amostra válida foi encontrada. Rode scripts\\03_ler_amostras_arquivos_dados.py antes deste resumo."
        )
        return

    by_year_and_column: dict[tuple[str, str], dict[str, object]] = {}
    by_column: dict[str, dict[str, object]] = {}

    for row in valid_rows:
        year = row.get("ano_detectado") or "sem_ano"
        source = f"{row.get('arquivo_zip', '')}::{row.get('arquivo_interno', '')}"
        columns = json_loads_list(row.get("nomes_colunas", ""))
        for column in columns:
            year_key = (year, column)
            year_item = by_year_and_column.setdefault(
                year_key,
                {
                    "ano_detectado": year,
                    "coluna": column,
                    "quantidade_arquivos": 0,
                    "arquivos_exemplo": [],
                },
            )
            year_item["quantidade_arquivos"] = int(year_item["quantidade_arquivos"]) + 1
            if len(year_item["arquivos_exemplo"]) < 3 and source not in year_item["arquivos_exemplo"]:
                year_item["arquivos_exemplo"].append(source)

            column_item = by_column.setdefault(
                column,
                {
                    "coluna": column,
                    "anos_detectados": set(),
                    "quantidade_arquivos": 0,
                },
            )
            column_item["anos_detectados"].add(year)
            column_item["quantidade_arquivos"] = int(column_item["quantidade_arquivos"]) + 1

    by_year_rows = [
        {
            "ano_detectado": item["ano_detectado"],
            "coluna": item["coluna"],
            "quantidade_arquivos": str(item["quantidade_arquivos"]),
            "arquivos_exemplo": " | ".join(item["arquivos_exemplo"]),
        }
        for item in by_year_and_column.values()
    ]
    by_year_rows.sort(key=lambda row: (row["ano_detectado"], row["coluna"]))

    frequency_rows = []
    for item in by_column.values():
        years_sorted = sorted(item["anos_detectados"])
        frequency_rows.append(
            {
                "coluna": item["coluna"],
                "quantidade_anos": str(len(years_sorted)),
                "anos_detectados": " | ".join(years_sorted),
                "quantidade_arquivos": str(item["quantidade_arquivos"]),
            }
        )
    frequency_rows.sort(
        key=lambda row: (
            -parse_int(row["quantidade_anos"]),
            -parse_int(row["quantidade_arquivos"]),
            row["coluna"],
        )
    )

    write_csv_dicts(
        COLUNAS_POR_ANO_CSV,
        by_year_rows,
        ["ano_detectado", "coluna", "quantidade_arquivos", "arquivos_exemplo"],
    )
    write_csv_dicts(
        FREQUENCIA_COLUNAS_CSV,
        frequency_rows,
        ["coluna", "quantidade_anos", "anos_detectados", "quantidade_arquivos"],
    )

    print_status(f"Colunas por ano salvas em: {COLUNAS_POR_ANO_CSV}")
    print_status(f"Frequência das colunas salva em: {FREQUENCIA_COLUNAS_CSV}")


if __name__ == "__main__":
    main()
