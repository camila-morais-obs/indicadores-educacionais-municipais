from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from _project_utils import (
    OUTPUTS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    ensure_directories,
    normalize_text,
    parse_int,
    print_status,
    read_csv_dicts,
    write_csv_dicts,
)

ANO_REFERENCIA = "2025"
FONTE = "Censo Escolar/INEP"
ATUALIZADO_EM = datetime.now().isoformat(timespec="seconds")

MAPA_CSV = PROCESSED_DIR / "painel_educacao_tijucas_mapa_escolas.csv"
MATRICULAS_CSV = PROCESSED_DIR / "microdados_tijucas_matriculas_2025.csv"

OUTPUT_ESCOLAS_CSV = PROCESSED_DIR / "painel_educacao_tijucas_mapa_escolas_com_matriculas.csv"
OUTPUT_BAIRROS_CSV = PROCESSED_DIR / "painel_educacao_tijucas_matriculas_por_bairro_2025.csv"
OUTPUT_BAIRROS_JSON = PROCESSED_DIR / "educacao_territorio_matriculas_bairro_2025.json"
OUTPUT_ESCOLAS_JSON = PROCESSED_DIR / "educacao_mapa_escolas_com_matriculas_2025.json"
RELATORIO_MD = OUTPUTS_DIR / "relatorios" / "relatorio_territorio_matriculas_bairro.md"

EXPORT_ROOT = PROJECT_ROOT / "exports" / "painel_educacao_tijucas"
EXPORT_PUBLIC_DATA = EXPORT_ROOT / "public_data"
EXPORT_DATA_PROCESSED = EXPORT_ROOT / "data_processed"

MAT_FIELDS = [
    ("QT_MAT_BAS", "matriculas_total_educacao_basica"),
    ("QT_MAT_INF", "matriculas_educacao_infantil"),
    ("QT_MAT_FUND", "matriculas_ensino_fundamental"),
    ("QT_MAT_MED", "matriculas_ensino_medio"),
]


def ensure_output_directories() -> None:
    ensure_directories()
    RELATORIO_MD.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    EXPORT_DATA_PROCESSED.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_entity(value: str) -> str:
    return str(value or "").strip()


def parse_nullable_int(value: str) -> int | None:
    normalized = str(value or "").strip()
    if normalized in {"", "--"}:
        return None
    try:
        return int(float(normalized.replace(",", ".")))
    except ValueError:
        return None


def format_nullable_int(value: int | None) -> str:
    return "" if value is None else str(value)


def canonical_bairro(rows: list[dict[str, str]], key_field: str = "bairro") -> dict[str, str]:
    grouped_labels: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        raw = str(row.get(key_field, "") or "").strip()
        key = normalize_text(raw)
        if not key:
            key = "sem_bairro"
            raw = "SEM BAIRRO"
        grouped_labels[key][raw] += 1

    canonical: dict[str, str] = {}
    for key, variants in grouped_labels.items():
        best = sorted(variants.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))[0][0]
        canonical[key] = best.upper()
    return canonical


def build_enriched_rows(map_rows: list[dict[str, str]], matricula_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, object]]:
    map_by_id = {clean_entity(row.get("co_entidade", "")): row for row in map_rows if clean_entity(row.get("co_entidade", ""))}
    mat_by_id = {clean_entity(row.get("CO_ENTIDADE", "")): row for row in matricula_rows if clean_entity(row.get("CO_ENTIDADE", ""))}

    canonical_map = canonical_bairro(map_rows)
    enriched_rows: list[dict[str, str]] = []
    matched = 0
    map_without_matricula: list[dict[str, str]] = []
    matricula_without_map: list[dict[str, str]] = []
    matricula_without_bairro: list[dict[str, str]] = []

    for co_entidade, map_row in map_by_id.items():
        merged = dict(map_row)
        bairro_raw = str(map_row.get("bairro", "") or "").strip()
        bairro_key = normalize_text(bairro_raw) or "sem_bairro"
        merged["bairro"] = canonical_map.get(bairro_key, bairro_raw.upper() if bairro_raw else "SEM BAIRRO")

        mat_row = mat_by_id.get(co_entidade)
        if mat_row:
            matched += 1
            for source_field, output_field in MAT_FIELDS:
                merged[output_field] = format_nullable_int(parse_nullable_int(mat_row.get(source_field, "")))
            if not bairro_raw.strip():
                matricula_without_bairro.append(
                    {
                        "co_entidade": co_entidade,
                        "nome_escola": merged.get("nome_escola", ""),
                    }
                )
        else:
            for _, output_field in MAT_FIELDS:
                merged[output_field] = ""
            map_without_matricula.append(
                {
                    "co_entidade": co_entidade,
                    "nome_escola": merged.get("nome_escola", ""),
                    "bairro": merged.get("bairro", ""),
                }
            )

        enriched_rows.append(merged)

    for co_entidade, mat_row in mat_by_id.items():
        if co_entidade not in map_by_id:
            matricula_without_map.append(
                {
                    "co_entidade": co_entidade,
                    "matriculas_total_educacao_basica": format_nullable_int(parse_nullable_int(mat_row.get("QT_MAT_BAS", ""))),
                }
            )

    diagnostics = {
        "map_total": len(map_rows),
        "mat_total": len(matricula_rows),
        "matched": matched,
        "map_without_matricula": map_without_matricula,
        "matricula_without_map": matricula_without_map,
        "matricula_without_bairro": matricula_without_bairro,
    }
    return enriched_rows, diagnostics


def build_bairro_rows(enriched_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    aggregated: dict[str, dict[str, int | str]] = {}

    for row in enriched_rows:
        bairro = str(row.get("bairro", "") or "").strip() or "SEM BAIRRO"
        base = aggregated.setdefault(
            bairro,
            {
                "ano": ANO_REFERENCIA,
                "bairro": bairro,
                "escolas": 0,
                "matriculas_total_educacao_basica": 0,
                "matriculas_educacao_infantil": 0,
                "matriculas_ensino_fundamental": 0,
                "matriculas_ensino_medio": 0,
            },
        )
        base["escolas"] = int(base["escolas"]) + 1
        for _, output_field in MAT_FIELDS:
            value = parse_nullable_int(row.get(output_field, "")) or 0
            base[output_field] = int(base[output_field]) + value

    rows = [
        {
            "ano": str(item["ano"]),
            "bairro": str(item["bairro"]),
            "escolas": str(item["escolas"]),
            "matriculas_total_educacao_basica": str(item["matriculas_total_educacao_basica"]),
            "matriculas_educacao_infantil": str(item["matriculas_educacao_infantil"]),
            "matriculas_ensino_fundamental": str(item["matriculas_ensino_fundamental"]),
            "matriculas_ensino_medio": str(item["matriculas_ensino_medio"]),
        }
        for item in aggregated.values()
    ]
    rows.sort(key=lambda row: (-parse_int(row["matriculas_total_educacao_basica"]), row["bairro"]))
    return rows


def build_bairros_json(bairro_rows: list[dict[str, str]]) -> dict[str, object]:
    return {
        "ano": 2025,
        "fonte": FONTE,
        "observacao_metodologica": (
            "Matrículas agregadas por bairro a partir do vínculo entre escola, bairro e CO_ENTIDADE. "
            "Usa QT_MAT_BAS como total de matrículas da educação básica."
        ),
        "bairros": [
            {
                "bairro": row["bairro"],
                "escolas": parse_int(row["escolas"]),
                "matriculas_total_educacao_basica": parse_int(row["matriculas_total_educacao_basica"]),
                "matriculas_educacao_infantil": parse_int(row["matriculas_educacao_infantil"]),
                "matriculas_ensino_fundamental": parse_int(row["matriculas_ensino_fundamental"]),
                "matriculas_ensino_medio": parse_int(row["matriculas_ensino_medio"]),
            }
            for row in bairro_rows
        ],
    }


def build_escolas_json(enriched_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for row in enriched_rows:
        payload.append(
            {
                "ano": parse_int(row.get("ano", "")),
                "co_entidade": clean_entity(row.get("co_entidade", "")),
                "nome_escola": row.get("nome_escola", ""),
                "dependencia_administrativa": row.get("dependencia_administrativa", ""),
                "localizacao": row.get("localizacao", ""),
                "bairro": row.get("bairro", ""),
                "endereco": row.get("endereco", ""),
                "latitude": row.get("latitude", ""),
                "longitude": row.get("longitude", ""),
                "etapas_ofertadas_resumo": row.get("etapas_ofertadas_resumo", ""),
                "matriculas_total_educacao_basica": parse_nullable_int(row.get("matriculas_total_educacao_basica", "")),
                "matriculas_educacao_infantil": parse_nullable_int(row.get("matriculas_educacao_infantil", "")),
                "matriculas_ensino_fundamental": parse_nullable_int(row.get("matriculas_ensino_fundamental", "")),
                "matriculas_ensino_medio": parse_nullable_int(row.get("matriculas_ensino_medio", "")),
            }
        )
    return payload


def validate_total(bairro_rows: list[dict[str, str]], expected_total: int) -> tuple[bool, int]:
    total = sum(parse_int(row.get("matriculas_total_educacao_basica", "")) for row in bairro_rows)
    return total == expected_total, total


def build_report_markdown(
    diagnostics: dict[str, object],
    bairro_rows: list[dict[str, str]],
    final_sum: int,
) -> str:
    map_without_matricula = diagnostics["map_without_matricula"]
    matricula_without_map = diagnostics["matricula_without_map"]
    matricula_without_bairro = diagnostics["matricula_without_bairro"]

    lines = [
        "# Relatório territorial de escolas e matrículas por bairro",
        "",
        "## Resumo do merge",
        "",
        f"- Total de escolas no mapa: {diagnostics['map_total']}",
        f"- Total de escolas na base de matrículas: {diagnostics['mat_total']}",
        f"- Quantidade de escolas casadas no merge: {diagnostics['matched']}",
        f"- Escolas do mapa sem matrícula: {len(map_without_matricula)}",
        f"- Escolas da matrícula sem bairro: {len(matricula_without_bairro)}",
        f"- Escolas da matrícula sem escola no mapa: {len(matricula_without_map)}",
        f"- Soma final de matrículas: {final_sum}",
        "",
        "## Escolas do mapa sem matrícula",
        "",
    ]
    if map_without_matricula:
        for row in map_without_matricula:
            lines.append(f"- {row['co_entidade']} | {row['nome_escola']} | {row['bairro']}")
    else:
        lines.append("- Nenhuma.")

    lines.extend(
        [
            "",
            "## Escolas da matrícula sem bairro",
            "",
        ]
    )
    if matricula_without_bairro:
        for row in matricula_without_bairro:
            lines.append(f"- {row['co_entidade']} | {row['nome_escola']}")
    else:
        lines.append("- Nenhuma.")

    lines.extend(
        [
            "",
            "## Top 10 bairros por matrículas",
            "",
            "| bairro | escolas | matriculas_total_educacao_basica | matriculas_educacao_infantil | matriculas_ensino_fundamental | matriculas_ensino_medio |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in bairro_rows[:10]:
        lines.append(
            f"| {row['bairro']} | {row['escolas']} | {row['matriculas_total_educacao_basica']} | "
            f"{row['matriculas_educacao_infantil']} | {row['matriculas_ensino_fundamental']} | {row['matriculas_ensino_medio']} |"
        )

    lines.extend(
        [
            "",
            "## Observações metodológicas",
            "",
            "- O merge foi feito por `co_entidade` do mapa e `CO_ENTIDADE` da base de matrículas, ambos padronizados como string.",
            "- O recorte territorial usa apenas 2025 nesta primeira versão.",
            "- `QT_MAT_BAS` foi usado como total de matrículas da educação básica.",
            "- Variações reais de grafia de bairro foram consolidadas para agregação, como `PRAÇA/PRACA`, `JOÁIA/JOAIA` e `UNIVERSITÁRIO/UNIVERSITARIO`.",
            "- Escolas sem correspondência em matrículas foram mantidas com campos nulos de matrícula.",
            "",
            "## Instruções de cópia para o projeto principal",
            "",
            "- `exports/painel_educacao_tijucas/public_data/educacao_territorio_matriculas_bairro_2025.json` → `poc_painel_tijucas/public/data/educacao/`",
            "- `exports/painel_educacao_tijucas/public_data/educacao_mapa_escolas_com_matriculas_2025.json` → `poc_painel_tijucas/public/data/educacao/`",
            "- `exports/painel_educacao_tijucas/data_processed/painel_educacao_tijucas_mapa_escolas_com_matriculas.csv` → `poc_painel_tijucas/data/processed/educacao/`",
            "- `exports/painel_educacao_tijucas/data_processed/painel_educacao_tijucas_matriculas_por_bairro_2025.csv` → `poc_painel_tijucas/data/processed/educacao/`",
            "",
            f"- Atualizado em: {ATUALIZADO_EM}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    ensure_output_directories()

    if not MAPA_CSV.exists() or not MATRICULAS_CSV.exists():
        print_status("Arquivos de entrada não encontrados em data/processed.")
        return

    map_rows_all = read_csv_dicts(MAPA_CSV)
    matricula_rows_all = read_csv_dicts(MATRICULAS_CSV)

    map_rows = [row for row in map_rows_all if str(row.get("ano", "")).strip() == ANO_REFERENCIA]
    matricula_rows = [
        row
        for row in matricula_rows_all
        if str(row.get("NU_ANO_CENSO", "")).strip() in {"", ANO_REFERENCIA}
    ]

    if not map_rows or not matricula_rows:
        print_status("As bases de mapa ou matrículas de 2025 estão vazias.")
        return

    expected_sum = sum(parse_nullable_int(row.get("QT_MAT_BAS", "")) or 0 for row in matricula_rows)
    enriched_rows, diagnostics = build_enriched_rows(map_rows, matricula_rows)
    bairro_rows = build_bairro_rows(enriched_rows)
    sum_ok, final_sum = validate_total(bairro_rows, expected_sum)

    if not sum_ok:
        print_status(
            f"A soma final de matrículas por bairro ({final_sum}) não bate com o total esperado ({expected_sum}). Nenhum arquivo foi exportado."
        )
        return

    fieldnames_enriched = list(map_rows[0].keys()) + [field for _, field in MAT_FIELDS]
    write_csv_dicts(OUTPUT_ESCOLAS_CSV, enriched_rows, fieldnames_enriched)
    write_csv_dicts(
        OUTPUT_BAIRROS_CSV,
        bairro_rows,
        [
            "ano",
            "bairro",
            "escolas",
            "matriculas_total_educacao_basica",
            "matriculas_educacao_infantil",
            "matriculas_ensino_fundamental",
            "matriculas_ensino_medio",
        ],
    )

    bairros_json = build_bairros_json(bairro_rows)
    escolas_json = build_escolas_json(enriched_rows)
    write_json(OUTPUT_BAIRROS_JSON, bairros_json)
    write_json(OUTPUT_ESCOLAS_JSON, escolas_json)

    write_json(EXPORT_PUBLIC_DATA / OUTPUT_BAIRROS_JSON.name, bairros_json)
    write_json(EXPORT_PUBLIC_DATA / OUTPUT_ESCOLAS_JSON.name, escolas_json)
    write_csv_dicts(EXPORT_DATA_PROCESSED / OUTPUT_ESCOLAS_CSV.name, enriched_rows, fieldnames_enriched)
    write_csv_dicts(
        EXPORT_DATA_PROCESSED / OUTPUT_BAIRROS_CSV.name,
        bairro_rows,
        [
            "ano",
            "bairro",
            "escolas",
            "matriculas_total_educacao_basica",
            "matriculas_educacao_infantil",
            "matriculas_ensino_fundamental",
            "matriculas_ensino_medio",
        ],
    )

    report_markdown = build_report_markdown(diagnostics, bairro_rows, final_sum)
    RELATORIO_MD.write_text(report_markdown, encoding="utf-8")

    print_status(f"Arquivo gerado: {OUTPUT_ESCOLAS_CSV}")
    print_status(f"Arquivo gerado: {OUTPUT_BAIRROS_CSV}")
    print_status(f"Arquivo gerado: {OUTPUT_BAIRROS_JSON}")
    print_status(f"Arquivo gerado: {OUTPUT_ESCOLAS_JSON}")
    print_status(f"Arquivo gerado: {RELATORIO_MD}")
    print_status(f"Arquivo gerado: {EXPORT_PUBLIC_DATA / OUTPUT_BAIRROS_JSON.name}")
    print_status(f"Arquivo gerado: {EXPORT_PUBLIC_DATA / OUTPUT_ESCOLAS_JSON.name}")
    print_status(f"Arquivo gerado: {EXPORT_DATA_PROCESSED / OUTPUT_ESCOLAS_CSV.name}")
    print_status(f"Arquivo gerado: {EXPORT_DATA_PROCESSED / OUTPUT_BAIRROS_CSV.name}")
    print_status(f"Escolas casadas no merge: {diagnostics['matched']}")
    print_status(f"Soma final de matrículas: {final_sum}")
    print_status(
        "Top 5 bairros por matrículas: "
        + "; ".join(
            f"{row['bairro']}={row['matriculas_total_educacao_basica']}" for row in bairro_rows[:5]
        )
    )
    print_status("Instruções de cópia para o projeto principal:")
    print_status("public_data/educacao_territorio_matriculas_bairro_2025.json -> poc_painel_tijucas/public/data/educacao/")
    print_status("public_data/educacao_mapa_escolas_com_matriculas_2025.json -> poc_painel_tijucas/public/data/educacao/")
    print_status("data_processed/painel_educacao_tijucas_mapa_escolas_com_matriculas.csv -> poc_painel_tijucas/data/processed/educacao/")
    print_status("data_processed/painel_educacao_tijucas_matriculas_por_bairro_2025.csv -> poc_painel_tijucas/data/processed/educacao/")


if __name__ == "__main__":
    main()
