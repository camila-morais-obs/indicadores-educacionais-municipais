from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from _project_utils import (
    OUTPUTS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    ensure_directories,
    parse_float,
    print_status,
    read_csv_dicts,
    write_csv_dicts,
)

ANOS_COMPARATIVO = ["2019", "2020", "2021", "2022", "2023", "2024"]
ANO_FOTOGRAFIA = "2024"
FONTE = "Censo Escolar/INEP"
ATUALIZADO_EM = datetime.now().isoformat(timespec="seconds")
OBSERVACAO_PADRAO = (
    "A comparação com Santa Catarina foi restrita a indicadores de infraestrutura escolar com maior "
    "estabilidade conceitual na série recente do Censo Escolar. Indicadores mais específicos, proxies "
    "ou sujeitos a diferenças de preenchimento são apresentados apenas para Tijucas nesta primeira "
    "versão, até validação metodológica adicional."
)

TIJUCAS_INFRA_CSV = PROCESSED_DIR / "painel_educacao_tijucas_infraestrutura.csv"
TIJUCAS_TEC_CSV = PROCESSED_DIR / "painel_educacao_tijucas_tecnologia_acessibilidade.csv"
SC_WIDE_CSV = PROCESSED_DIR / "painel_educacao_sc_infraestrutura.csv"
SC_LONG_CSV = PROCESSED_DIR / "painel_educacao_sc_infraestrutura_long.csv"
METADATA_SOURCE_JSON = PROCESSED_DIR / "metadata_educacao_tijucas.json"

COMPARATIVO_CSV = PROCESSED_DIR / "painel_educacao_comparativo_tijucas_sc_2019_2024.csv"
COMPARATIVO_JSON = PROCESSED_DIR / "educacao_comparativo_sc.json"
COMPARATIVO_2024_JSON = PROCESSED_DIR / "educacao_comparativo_sc_2024.json"
APENAS_TIJUCAS_JSON = PROCESSED_DIR / "educacao_indicadores_apenas_tijucas.json"
RELATORIO_MD = OUTPUTS_DIR / "relatorios" / "relatorio_comparativo_tijucas_sc_infraestrutura_2019_2024.md"

EXPORT_ROOT = PROJECT_ROOT / "exports" / "painel_educacao_tijucas"
EXPORT_PUBLIC_DATA = EXPORT_ROOT / "public_data"
EXPORT_DATA_PUBLISHED = EXPORT_ROOT / "data_published"
EXPORT_DATA_PROCESSED = EXPORT_ROOT / "data_processed"
EXPORT_METADATA_PUBLIC = EXPORT_PUBLIC_DATA / "educacao_metadata.json"
EXPORT_METADATA_PUBLISHED = EXPORT_DATA_PUBLISHED / "educacao_metadata.json"
EXPORT_METADATA_ROOT = EXPORT_ROOT / "metadata_educacao_tijucas.json"


COMPARABLE_INDICATORS = [
    {
        "codigo": "perc_escolas_internet",
        "nome": "Escolas com internet",
        "tema": "Tecnologia e conectividade",
        "origem_tijucas": "tecnologia",
        "indicador_sc_long": "Percentual de escolas com internet",
        "observacao": "Indicador incluído no comparativo estadual por apresentar maior estabilidade conceitual na série recente do Censo Escolar.",
    },
    {
        "codigo": "perc_escolas_refeitorio",
        "nome": "Escolas com refeitório",
        "tema": "Infraestrutura básica",
        "origem_tijucas": "infraestrutura",
        "indicador_sc_long": "Percentual de escolas com refeitório",
        "observacao": "Indicador incluído no comparativo estadual por apresentar maior estabilidade conceitual na série recente do Censo Escolar.",
    },
    {
        "codigo": "perc_escolas_biblioteca_ou_sala_leitura",
        "nome": "Escolas com biblioteca ou sala de leitura",
        "tema": "Infraestrutura pedagógica",
        "origem_tijucas": "infraestrutura",
        "indicador_sc_long": "Percentual de escolas com biblioteca ou sala de leitura",
        "observacao": "Para este indicador, considera-se presença quando existe biblioteca, sala de leitura ou a variável combinada de biblioteca/sala de leitura.",
    },
    {
        "codigo": "perc_escolas_laboratorio_informatica",
        "nome": "Escolas com laboratório de informática",
        "tema": "Infraestrutura pedagógica",
        "origem_tijucas": "infraestrutura",
        "indicador_sc_long": "Percentual de escolas com laboratório de informática",
        "observacao": "Indicador incluído no comparativo estadual por apresentar maior estabilidade conceitual na série recente do Censo Escolar.",
    },
    {
        "codigo": "perc_escolas_quadra_esportes",
        "nome": "Escolas com quadra de esportes",
        "tema": "Infraestrutura pedagógica",
        "origem_tijucas": "infraestrutura",
        "indicador_sc_long": "Percentual de escolas com quadra de esportes",
        "observacao": "Indicador incluído no comparativo estadual por apresentar maior estabilidade conceitual na série recente do Censo Escolar.",
    },
    {
        "codigo": "perc_escolas_banheiro_acessivel",
        "nome": "Escolas com banheiro acessível",
        "tema": "Acessibilidade",
        "origem_tijucas": "tecnologia",
        "indicador_sc_long": "Percentual de escolas com banheiro acessível",
        "observacao": "Banheiro acessível foi mantido como proxy de acessibilidade por ser mais simples e estável do que outras medidas mais específicas nesta primeira versão comparativa.",
    },
]

TIJUCAS_ONLY_INDICATORS = [
    {
        "indicador_codigo": "perc_escolas_agua_potavel",
        "indicador_nome": "Escolas com água potável",
        "tema": "Infraestrutura básica",
        "motivo_sem_comparacao": "Indicador mais específico, sujeito a validação adicional de comparabilidade estadual.",
    },
    {
        "indicador_codigo": "perc_escolas_agua_rede_publica",
        "indicador_nome": "Escolas com água da rede pública",
        "tema": "Infraestrutura básica",
        "motivo_sem_comparacao": "Indicador mais específico, sujeito a validação adicional de comparabilidade estadual.",
    },
    {
        "indicador_codigo": "perc_escolas_banda_larga",
        "indicador_nome": "Escolas com banda larga",
        "tema": "Tecnologia e conectividade",
        "motivo_sem_comparacao": "Indicador mais específico, sujeito a diferenças de preenchimento e validação adicional de comparabilidade estadual.",
    },
    {
        "indicador_codigo": "perc_escolas_internet_alunos",
        "indicador_nome": "Escolas com internet para alunos",
        "tema": "Tecnologia e conectividade",
        "motivo_sem_comparacao": "Indicador mais específico, sujeito a diferenças de interpretação de uso ao longo da série.",
    },
    {
        "indicador_codigo": "perc_escolas_internet_aprendizagem",
        "indicador_nome": "Escolas com internet para aprendizagem",
        "tema": "Tecnologia e conectividade",
        "motivo_sem_comparacao": "Indicador mais específico, sujeito a diferenças de interpretação de uso ao longo da série.",
    },
    {
        "indicador_codigo": "perc_escolas_acessibilidade_rampas",
        "indicador_nome": "Escolas com rampas de acessibilidade",
        "tema": "Acessibilidade",
        "motivo_sem_comparacao": "Indicador mais específico, sujeito a validação adicional de comparabilidade estadual.",
    },
    {
        "indicador_codigo": "perc_escolas_salas_acessiveis",
        "indicador_nome": "Escolas com salas acessíveis",
        "tema": "Acessibilidade",
        "motivo_sem_comparacao": "Indicador proxy baseado em quantidade e sujeito a diferenças de preenchimento.",
    },
    {
        "indicador_codigo": "perc_escolas_sem_recurso_acessibilidade",
        "indicador_nome": "Escolas sem recurso de acessibilidade",
        "tema": "Acessibilidade",
        "motivo_sem_comparacao": "Indicador proxy negativo, sujeito a diferenças de interpretação e preenchimento.",
    },
]


def ensure_output_directories() -> None:
    ensure_directories()
    RELATORIO_MD.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    EXPORT_DATA_PUBLISHED.mkdir(parents=True, exist_ok=True)
    EXPORT_DATA_PROCESSED.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def round_one_decimal(value: float) -> float:
    return round(value, 1)


def format_one_decimal(value: float) -> str:
    return f"{round_one_decimal(value):.1f}"


def index_by_year(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {str(row.get("ano", "")).strip(): row for row in rows if str(row.get("ano", "")).strip()}


def index_sc_long(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    indexed: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (str(row.get("ano", "")).strip(), str(row.get("indicador", "")).strip())
        if key[0] and key[1]:
            indexed[key] = row
    return indexed


def build_comparative_observation(config: dict[str, str]) -> str:
    return (
        f"{config['observacao']} "
        "A comparação usa escolas em funcionamento como denominador e foi restrita à série 2019-2024."
    )


def build_comparison_outputs() -> tuple[list[dict[str, str]], list[dict[str, object]], list[dict[str, object]], list[str]]:
    tijucas_infra_rows = read_csv_dicts(TIJUCAS_INFRA_CSV)
    tijucas_tec_rows = read_csv_dicts(TIJUCAS_TEC_CSV)
    sc_wide_rows = read_csv_dicts(SC_WIDE_CSV)
    sc_long_rows = read_csv_dicts(SC_LONG_CSV)

    if not tijucas_infra_rows or not tijucas_tec_rows or not sc_wide_rows or not sc_long_rows:
        raise FileNotFoundError(
            "Uma ou mais bases de entrada não foram encontradas ou estão vazias. Verifique as saídas anteriores em data/processed."
        )

    tijucas_infra_by_year = index_by_year(tijucas_infra_rows)
    tijucas_tec_by_year = index_by_year(tijucas_tec_rows)
    sc_wide_by_year = index_by_year(sc_wide_rows)
    sc_long_index = index_sc_long(sc_long_rows)

    csv_rows: list[dict[str, str]] = []
    json_rows: list[dict[str, object]] = []
    missing_entries: list[str] = []

    for year in ANOS_COMPARATIVO:
        sc_wide_row = sc_wide_by_year.get(year, {})
        tijucas_infra_row = tijucas_infra_by_year.get(year, {})
        tijucas_tec_row = tijucas_tec_by_year.get(year, {})

        if not sc_wide_row or not tijucas_infra_row or not tijucas_tec_row:
            missing_entries.append(f"{year}: bases anuais ausentes para uma das fontes processadas.")
            continue

        for config in COMPARABLE_INDICATORS:
            codigo = config["codigo"]
            tijucas_source_row = tijucas_tec_row if config["origem_tijucas"] == "tecnologia" else tijucas_infra_row
            tijucas_raw = str(tijucas_source_row.get(codigo, "")).strip()
            sc_raw = str(sc_wide_row.get(codigo, "")).strip()
            sc_long_meta = sc_long_index.get((year, config["indicador_sc_long"]))

            if not tijucas_raw or not sc_raw or not sc_long_meta:
                missing_entries.append(f"{year}: {codigo} ausente para Tijucas ou Santa Catarina.")
                continue

            tijucas_value = round_one_decimal(parse_float(tijucas_raw))
            sc_value = round_one_decimal(parse_float(sc_raw))
            diff_value = round_one_decimal(tijucas_value - sc_value)
            observacao = build_comparative_observation(config)

            csv_rows.append(
                {
                    "ano": year,
                    "indicador_codigo": codigo,
                    "indicador_nome": config["nome"],
                    "tema": config["tema"],
                    "tijucas": format_one_decimal(tijucas_value),
                    "santa_catarina": format_one_decimal(sc_value),
                    "diferenca_tijucas_sc": format_one_decimal(diff_value),
                    "unidade": "%",
                    "fonte": FONTE,
                    "comparabilidade": "comparável",
                    "grupo_exibicao": "comparavel_sc",
                    "observacao_metodologica": observacao,
                }
            )
            json_rows.append(
                {
                    "ano": int(year),
                    "indicador_codigo": codigo,
                    "indicador_nome": config["nome"],
                    "tema": config["tema"],
                    "tijucas": tijucas_value,
                    "santa_catarina": sc_value,
                    "diferenca_tijucas_sc": diff_value,
                    "unidade": "%",
                    "fonte": FONTE,
                    "comparabilidade": "comparável",
                    "grupo_exibicao": "comparavel_sc",
                    "observacao_metodologica": observacao,
                }
            )

    json_2024_rows = [row for row in json_rows if row["ano"] == int(ANO_FOTOGRAFIA)]
    return csv_rows, json_rows, json_2024_rows, missing_entries


def build_tijucas_only_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in TIJUCAS_ONLY_INDICATORS:
        rows.append(
            {
                "indicador_codigo": item["indicador_codigo"],
                "indicador_nome": item["indicador_nome"],
                "tema": item["tema"],
                "grupo_exibicao": "apenas_tijucas",
                "motivo_sem_comparacao": item["motivo_sem_comparacao"],
                "observacao_metodologica": "Apresentado apenas para Tijucas nesta primeira versão pública.",
            }
        )
    return rows


def update_exported_metadata() -> list[Path]:
    if not METADATA_SOURCE_JSON.exists():
        return []

    source_metadata = load_json(METADATA_SOURCE_JSON)
    if not source_metadata:
        return []

    augmented = dict(source_metadata)
    augmented["comparativo_estadual_disponivel"] = True
    augmented["janela_comparativo_estadual"] = "2019-2024"
    augmented["ano_fotografia_comparativo_estadual"] = 2024
    augmented["comparativo_2025_incluido"] = False
    augmented["motivo_exclusao_2025"] = "Mudança estrutural nos microdados do Censo Escolar em 2025."
    augmented["indicadores_com_comparacao_sc"] = [item["codigo"] for item in COMPARABLE_INDICATORS]
    augmented["indicadores_apenas_tijucas"] = [item["indicador_codigo"] for item in TIJUCAS_ONLY_INDICATORS]
    augmented["observacao_comparativo_estadual"] = OBSERVACAO_PADRAO

    written_paths = []
    for target in (EXPORT_METADATA_PUBLIC, EXPORT_METADATA_PUBLISHED, EXPORT_METADATA_ROOT):
        write_json(target, augmented)
        written_paths.append(target)
    return written_paths


def build_report_markdown(
    csv_rows: list[dict[str, str]],
    json_2024_rows: list[dict[str, object]],
    missing_entries: list[str],
) -> str:
    lines = [
        "# Relatório metodológico do comparativo Tijucas x Santa Catarina em infraestrutura escolar (2019-2024)",
        "",
        "## Justificativa para usar 2019-2024",
        "",
        "- A série comparativa pública foi restrita a 2019-2024 para reduzir risco de mudanças de questionário e ruído histórico da parte mais antiga da série.",
        "- O recorte privilegia a série recente do Censo Escolar, com foco em indicadores considerados mais estáveis, clássicos e comparáveis.",
        "",
        "## Justificativa para excluir 2025",
        "",
        "- O ano de 2025 não foi incluído na série comparativa pública porque os microdados do Censo Escolar passaram por mudança estrutural.",
        "- Em 2025, os indicadores estaduais ficaram classificados como `comparável com adaptação`, o que recomenda cautela adicional antes de publicação comparativa.",
        "",
        "## Texto metodológico padrão",
        "",
        f"- {OBSERVACAO_PADRAO}",
        "",
        "## Indicadores com comparação Santa Catarina",
        "",
    ]
    for item in COMPARABLE_INDICATORS:
        lines.append(f"- {item['codigo']}: {item['nome']}")

    lines.extend(
        [
            "",
            "## Indicadores apresentados apenas para Tijucas",
            "",
        ]
    )
    for item in TIJUCAS_ONLY_INDICATORS:
        lines.append(f"- {item['indicador_codigo']}: {item['motivo_sem_comparacao']}")

    lines.extend(
        [
            "",
            "## Valores de 2024: Tijucas x Santa Catarina",
            "",
            "| indicador_codigo | indicador_nome | tijucas | santa_catarina | diferenca_tijucas_sc |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in json_2024_rows:
        lines.append(
            f"| {row['indicador_codigo']} | {row['indicador_nome']} | {row['tijucas']:.1f} | {row['santa_catarina']:.1f} | {row['diferenca_tijucas_sc']:.1f} |"
        )

    lines.extend(
        [
            "",
            "## Observação metodológica para biblioteca/sala de leitura",
            "",
            "- O indicador considera presença quando existe biblioteca, sala de leitura ou a variável combinada de biblioteca/sala de leitura, seguindo a lógica já adotada nas bases processadas.",
            "",
            "## Observação metodológica para banheiro acessível como proxy",
            "",
            "- O comparativo usa `banheiro acessível` como proxy de acessibilidade por ser uma medida mais simples e estável do que outros indicadores mais específicos nesta primeira versão pública.",
            "",
        ]
    )

    if missing_entries:
        lines.extend(
            [
                "## Entradas não incluídas por ausência ou inconsistência",
                "",
            ]
        )
        for entry in missing_entries:
            lines.append(f"- {entry}")
        lines.append("")

    lines.extend(
        [
            "## Instruções de cópia para o projeto principal",
            "",
            "- `exports/painel_educacao_tijucas/data_processed/painel_educacao_comparativo_tijucas_sc_2019_2024.csv` → `poc_painel_tijucas/data/processed/educacao/`",
            "- `exports/painel_educacao_tijucas/public_data/educacao_comparativo_sc.json` → `poc_painel_tijucas/public/data/educacao/`",
            "- `exports/painel_educacao_tijucas/public_data/educacao_comparativo_sc_2024.json` → `poc_painel_tijucas/public/data/educacao/`",
            "- `exports/painel_educacao_tijucas/public_data/educacao_indicadores_apenas_tijucas.json` → `poc_painel_tijucas/public/data/educacao/`",
            "- `exports/painel_educacao_tijucas/data_published/educacao_comparativo_sc.json` → `poc_painel_tijucas/data/published/educacao/`",
            "- `exports/painel_educacao_tijucas/data_published/educacao_comparativo_sc_2024.json` → `poc_painel_tijucas/data/published/educacao/`",
            "- `exports/painel_educacao_tijucas/data_published/educacao_indicadores_apenas_tijucas.json` → `poc_painel_tijucas/data/published/educacao/`",
            "",
            "## Orientação para o painel",
            "",
            "- Use `educacao_comparativo_sc_2024.json` como base principal do gráfico “Tijucas x Santa Catarina — 2024”.",
            "- Use `educacao_comparativo_sc.json` para séries comparativas entre 2019 e 2024.",
            "- Use `educacao_indicadores_apenas_tijucas.json` para separar no front-end os indicadores exibidos só para Tijucas.",
            "",
            f"- Atualizado em: {ATUALIZADO_EM}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    ensure_output_directories()

    csv_rows, json_rows, json_2024_rows, missing_entries = build_comparison_outputs()
    tijucas_only_rows = build_tijucas_only_rows()

    csv_fieldnames = [
        "ano",
        "indicador_codigo",
        "indicador_nome",
        "tema",
        "tijucas",
        "santa_catarina",
        "diferenca_tijucas_sc",
        "unidade",
        "fonte",
        "comparabilidade",
        "grupo_exibicao",
        "observacao_metodologica",
    ]
    write_csv_dicts(COMPARATIVO_CSV, csv_rows, csv_fieldnames)
    write_json(COMPARATIVO_JSON, json_rows)
    write_json(COMPARATIVO_2024_JSON, json_2024_rows)
    write_json(APENAS_TIJUCAS_JSON, tijucas_only_rows)

    public_json_targets = [
        EXPORT_PUBLIC_DATA / "educacao_comparativo_sc.json",
        EXPORT_PUBLIC_DATA / "educacao_comparativo_sc_2024.json",
        EXPORT_PUBLIC_DATA / "educacao_indicadores_apenas_tijucas.json",
    ]
    published_json_targets = [
        EXPORT_DATA_PUBLISHED / "educacao_comparativo_sc.json",
        EXPORT_DATA_PUBLISHED / "educacao_comparativo_sc_2024.json",
        EXPORT_DATA_PUBLISHED / "educacao_indicadores_apenas_tijucas.json",
    ]

    write_json(public_json_targets[0], json_rows)
    write_json(public_json_targets[1], json_2024_rows)
    write_json(public_json_targets[2], tijucas_only_rows)
    write_json(published_json_targets[0], json_rows)
    write_json(published_json_targets[1], json_2024_rows)
    write_json(published_json_targets[2], tijucas_only_rows)
    write_csv_dicts(EXPORT_DATA_PROCESSED / COMPARATIVO_CSV.name, csv_rows, csv_fieldnames)

    metadata_paths = update_exported_metadata()
    report_markdown = build_report_markdown(csv_rows, json_2024_rows, missing_entries)
    RELATORIO_MD.write_text(report_markdown, encoding="utf-8")

    print_status(f"Arquivo gerado: {COMPARATIVO_CSV}")
    print_status(f"Arquivo gerado: {COMPARATIVO_JSON}")
    print_status(f"Arquivo gerado: {COMPARATIVO_2024_JSON}")
    print_status(f"Arquivo gerado: {APENAS_TIJUCAS_JSON}")
    print_status(f"Arquivo gerado: {RELATORIO_MD}")
    print_status(f"Arquivo gerado: {EXPORT_DATA_PROCESSED / COMPARATIVO_CSV.name}")
    for path in public_json_targets + published_json_targets:
        print_status(f"Arquivo gerado: {path}")
    for metadata_path in metadata_paths:
        print_status(f"Metadata exportado/atualizado: {metadata_path}")

    print_status(f"Indicadores com comparação SC: {[item['codigo'] for item in COMPARABLE_INDICATORS]}")
    print_status(f"Indicadores apenas Tijucas: {[item['indicador_codigo'] for item in TIJUCAS_ONLY_INDICATORS]}")
    print_status(f"Anos disponíveis no comparativo: {sorted({row['ano'] for row in csv_rows})}")
    if missing_entries:
        preview = "; ".join(missing_entries[:10])
        print_status(f"Entradas não incluídas por ausência ou inconsistência: {preview}")

    for row in json_2024_rows:
        print_status(
            f"2024 {row['indicador_codigo']}: Tijucas={row['tijucas']:.1f}%, "
            f"SC={row['santa_catarina']:.1f}%, diferença={row['diferenca_tijucas_sc']:.1f} p.p."
        )

    print_status("Instruções de cópia para o projeto principal:")
    print_status(
        "data_processed/painel_educacao_comparativo_tijucas_sc_2019_2024.csv -> poc_painel_tijucas/data/processed/educacao/"
    )
    print_status(
        "public_data/educacao_comparativo_sc.json -> poc_painel_tijucas/public/data/educacao/"
    )
    print_status(
        "public_data/educacao_comparativo_sc_2024.json -> poc_painel_tijucas/public/data/educacao/"
    )
    print_status(
        "public_data/educacao_indicadores_apenas_tijucas.json -> poc_painel_tijucas/public/data/educacao/"
    )
    print_status(
        "data_published/educacao_comparativo_sc.json -> poc_painel_tijucas/data/published/educacao/"
    )
    print_status(
        "data_published/educacao_comparativo_sc_2024.json -> poc_painel_tijucas/data/published/educacao/"
    )
    print_status(
        "data_published/educacao_indicadores_apenas_tijucas.json -> poc_painel_tijucas/data/published/educacao/"
    )


if __name__ == "__main__":
    main()
