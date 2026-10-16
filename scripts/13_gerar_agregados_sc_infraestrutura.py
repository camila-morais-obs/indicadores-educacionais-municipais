from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from _project_utils import (
    DIAGNOSTICOS_DIR,
    OUTPUTS_DIR,
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
SC_WIDE_CSV = PROCESSED_DIR / "painel_educacao_sc_infraestrutura.csv"
SC_LONG_CSV = PROCESSED_DIR / "painel_educacao_sc_infraestrutura_long.csv"
RELATORIO_MD = OUTPUTS_DIR / "relatorios" / "relatorio_agregados_sc_infraestrutura.md"

TERRITORIO = "Santa Catarina"
NIVEL_TERRITORIAL = "Estado"
FONTE = "Censo Escolar/INEP"
ATUALIZADO_EM = datetime.now().isoformat(timespec="seconds")


@dataclass(frozen=True)
class IndicatorSpec:
    column: str
    indicator: str
    theme: str
    fields: tuple[str, ...]
    observation: str
    use_numeric_positive: bool = False


INDICATOR_SPECS: list[IndicatorSpec] = [
    IndicatorSpec(
        column="perc_escolas_agua_potavel",
        indicator="Percentual de escolas com água potável",
        theme="Infraestrutura básica",
        fields=("IN_AGUA_POTAVEL",),
        observation="Percentual de escolas ativas com presença declarada de água potável.",
    ),
    IndicatorSpec(
        column="perc_escolas_agua_rede_publica",
        indicator="Percentual de escolas com água da rede pública",
        theme="Infraestrutura básica",
        fields=("IN_AGUA_REDE_PUBLICA",),
        observation="Percentual de escolas ativas com abastecimento declarado pela rede pública.",
    ),
    IndicatorSpec(
        column="perc_escolas_energia_rede_publica",
        indicator="Percentual de escolas com energia elétrica da rede pública",
        theme="Infraestrutura básica",
        fields=("IN_ENERGIA_REDE_PUBLICA",),
        observation="Percentual de escolas ativas com energia elétrica declarada da rede pública.",
    ),
    IndicatorSpec(
        column="perc_escolas_esgoto_rede_publica",
        indicator="Percentual de escolas com esgoto da rede pública",
        theme="Infraestrutura básica",
        fields=("IN_ESGOTO_REDE_PUBLICA",),
        observation="Percentual de escolas ativas com esgotamento sanitário declarado pela rede pública.",
    ),
    IndicatorSpec(
        column="perc_escolas_banheiro",
        indicator="Percentual de escolas com banheiro",
        theme="Infraestrutura básica",
        fields=("IN_BANHEIRO",),
        observation="Percentual de escolas ativas com presença declarada de banheiro.",
    ),
    IndicatorSpec(
        column="perc_escolas_cozinha",
        indicator="Percentual de escolas com cozinha",
        theme="Infraestrutura básica",
        fields=("IN_COZINHA",),
        observation="Percentual de escolas ativas com presença declarada de cozinha.",
    ),
    IndicatorSpec(
        column="perc_escolas_refeitorio",
        indicator="Percentual de escolas com refeitório",
        theme="Infraestrutura básica",
        fields=("IN_REFEITORIO",),
        observation="Percentual de escolas ativas com presença declarada de refeitório.",
    ),
    IndicatorSpec(
        column="perc_escolas_biblioteca_ou_sala_leitura",
        indicator="Percentual de escolas com biblioteca ou sala de leitura",
        theme="Infraestrutura pedagógica",
        fields=("IN_BIBLIOTECA", "IN_SALA_LEITURA", "IN_BIBLIOTECA_SALA_LEITURA"),
        observation="Presença considerada quando ao menos uma variável de biblioteca, sala de leitura ou variável combinada é igual a 1.",
    ),
    IndicatorSpec(
        column="perc_escolas_laboratorio_informatica",
        indicator="Percentual de escolas com laboratório de informática",
        theme="Infraestrutura pedagógica",
        fields=("IN_LABORATORIO_INFORMATICA",),
        observation="Percentual de escolas ativas com presença declarada de laboratório de informática.",
    ),
    IndicatorSpec(
        column="perc_escolas_laboratorio_ciencias",
        indicator="Percentual de escolas com laboratório de ciências",
        theme="Infraestrutura pedagógica",
        fields=("IN_LABORATORIO_CIENCIAS",),
        observation="Percentual de escolas ativas com presença declarada de laboratório de ciências.",
    ),
    IndicatorSpec(
        column="perc_escolas_quadra_esportes",
        indicator="Percentual de escolas com quadra de esportes",
        theme="Infraestrutura pedagógica",
        fields=("IN_QUADRA_ESPORTES",),
        observation="Percentual de escolas ativas com presença declarada de quadra de esportes.",
    ),
    IndicatorSpec(
        column="perc_escolas_parque_infantil",
        indicator="Percentual de escolas com parque infantil",
        theme="Infraestrutura pedagógica",
        fields=("IN_PARQUE_INFANTIL",),
        observation="Percentual de escolas ativas com presença declarada de parque infantil.",
    ),
    IndicatorSpec(
        column="perc_escolas_internet",
        indicator="Percentual de escolas com internet",
        theme="Tecnologia e conectividade",
        fields=("IN_INTERNET",),
        observation="Percentual de escolas ativas com presença declarada de internet.",
    ),
    IndicatorSpec(
        column="perc_escolas_banda_larga",
        indicator="Percentual de escolas com banda larga",
        theme="Tecnologia e conectividade",
        fields=("IN_BANDA_LARGA",),
        observation="Percentual de escolas ativas com banda larga declarada.",
    ),
    IndicatorSpec(
        column="perc_escolas_internet_alunos",
        indicator="Percentual de escolas com internet para alunos",
        theme="Tecnologia e conectividade",
        fields=("IN_INTERNET_ALUNOS",),
        observation="Percentual de escolas ativas com uso declarado de internet para alunos.",
    ),
    IndicatorSpec(
        column="perc_escolas_internet_aprendizagem",
        indicator="Percentual de escolas com internet para aprendizagem",
        theme="Tecnologia e conectividade",
        fields=("IN_INTERNET_APRENDIZAGEM",),
        observation="Percentual de escolas ativas com uso declarado de internet em processos de aprendizagem.",
    ),
    IndicatorSpec(
        column="perc_escolas_acessibilidade_rampas",
        indicator="Percentual de escolas com rampas de acessibilidade",
        theme="Acessibilidade",
        fields=("IN_ACESSIBILIDADE_RAMPAS",),
        observation="Percentual de escolas ativas com presença declarada de rampas de acessibilidade.",
    ),
    IndicatorSpec(
        column="perc_escolas_banheiro_acessivel",
        indicator="Percentual de escolas com banheiro acessível",
        theme="Acessibilidade",
        fields=("IN_BANHEIRO_PNE",),
        observation="Mesma proxy usada atualmente em Tijucas: presença declarada de banheiro acessível.",
    ),
    IndicatorSpec(
        column="perc_escolas_salas_acessiveis",
        indicator="Percentual de escolas com salas acessíveis",
        theme="Acessibilidade",
        fields=("QT_SALAS_UTILIZADAS_ACESSIVEIS",),
        observation="Percentual de escolas ativas com pelo menos uma sala acessível declarada.",
        use_numeric_positive=True,
    ),
    IndicatorSpec(
        column="perc_escolas_sem_recurso_acessibilidade",
        indicator="Percentual de escolas sem recurso de acessibilidade",
        theme="Acessibilidade",
        fields=("IN_ACESSIBILIDADE_INEXISTENTE",),
        observation="Percentual de escolas ativas com inexistência declarada de recurso de acessibilidade.",
    ),
]


def ensure_output_directories() -> None:
    ensure_directories()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    RELATORIO_MD.parent.mkdir(parents=True, exist_ok=True)


def normalize_separator(separator: str) -> str:
    return "\t" if separator == "\\t" else separator


def format_number(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:.{decimals}f}"


def as_presence(value: str) -> bool:
    normalized = str(value or "").strip()
    if normalized == "":
        return False
    return normalized in {"1", "S", "SIM", "True", "true"} or parse_int(normalized) > 0


def row_is_sc(row: dict[str, str]) -> bool:
    sg_uf = normalize_text(row.get("SG_UF", ""))
    co_uf = str(row.get("CO_UF", "") or "").strip()
    return sg_uf == "sc" or co_uf == "42"


def classify_school_sample(row: dict[str, str]) -> bool:
    internal_name = Path(row.get("arquivo_interno", "")).name.lower()
    year = (row.get("ano_detectado") or "").strip()
    if year == "2025":
        return internal_name == "tabela_escola_2025.csv"
    return internal_name.startswith("microdados_ed_basica_") and internal_name.endswith(".csv")


def get_school_samples() -> list[dict[str, str]]:
    rows = read_csv_dicts(AMOSTRAS_CSV)
    selected: list[dict[str, str]] = []
    seen_years: set[str] = set()

    for row in rows:
        if row.get("status") != "ok":
            continue
        if not classify_school_sample(row):
            continue
        year = (row.get("ano_detectado") or "").strip()
        if not year or year in seen_years:
            continue
        seen_years.add(year)
        selected.append(row)

    selected.sort(key=lambda item: parse_int(item.get("ano_detectado", "0")))
    return selected


def stream_csv_from_zip(sample: dict[str, str]):
    zip_path = RAW_DIR / sample["arquivo_zip"]
    separator = normalize_separator(sample.get("separador_detectado", ";"))
    encoding = sample.get("encoding_detectado", "utf-8")
    internal_name = sample["arquivo_interno"]

    with zipfile.ZipFile(zip_path) as zip_file:
        with zip_file.open(internal_name) as binary_stream:
            text_stream = io.TextIOWrapper(binary_stream, encoding=encoding, newline="", errors="replace")
            reader = csv.DictReader(text_stream, delimiter=separator)
            for row in reader:
                yield row


def spec_lookup() -> dict[str, IndicatorSpec]:
    return {spec.column: spec for spec in INDICATOR_SPECS}


def build_comparability(year: str, has_value: bool) -> str:
    if not has_value:
        return "não disponível"
    if year == "2025":
        return "comparável com adaptação"
    return "comparável"


def build_indicator_observation(spec: IndicatorSpec, year: str, status_note: str, missing_note: str = "") -> str:
    parts = [spec.observation, status_note]
    if year == "2025":
        parts.append("Em 2025 o cálculo foi feito a partir da Tabela_Escola_2025.csv, por causa da mudança estrutural da base.")
    if missing_note:
        parts.append(missing_note)
    return " ".join(part for part in parts if part).strip()


def aggregate_year(sample: dict[str, str]) -> tuple[dict[str, str], list[dict[str, str]], dict[str, object]]:
    year = (sample.get("ano_detectado") or "").strip()
    print_status(f"Processando Santa Catarina no ano {year}: {sample['arquivo_interno']}")

    all_entities: set[str] = set()
    active_entities: set[str] = set()
    field_available_all = defaultdict(bool)
    field_available_active = defaultdict(bool)
    numerator_all = {spec.column: set() for spec in INDICATOR_SPECS}
    numerator_active = {spec.column: set() for spec in INDICATOR_SPECS}

    status_available = False
    missing_entity_rows = 0
    matched_rows = 0

    for row in stream_csv_from_zip(sample):
        if not row_is_sc(row):
            continue

        matched_rows += 1
        entity = str(row.get("CO_ENTIDADE", "") or "").strip()
        if not entity:
            missing_entity_rows += 1
            continue

        all_entities.add(entity)

        status_value = str(row.get("TP_SITUACAO_FUNCIONAMENTO", "") or "").strip()
        if status_value != "":
            status_available = True
        is_active = parse_int(status_value) == 1 if status_value != "" else False
        if is_active:
            active_entities.add(entity)

        for spec in INDICATOR_SPECS:
            for field in spec.fields:
                value = str(row.get(field, "") or "").strip()
                if value != "":
                    field_available_all[field] = True
                    if is_active:
                        field_available_active[field] = True

            has_presence = False
            for field in spec.fields:
                value = str(row.get(field, "") or "").strip()
                if spec.use_numeric_positive:
                    if value != "" and parse_int(value) > 0:
                        has_presence = True
                        break
                elif as_presence(value):
                    has_presence = True
                    break

            if has_presence:
                numerator_all[spec.column].add(entity)
                if is_active:
                    numerator_active[spec.column].add(entity)

    use_active = status_available and bool(active_entities)
    denominator_entities = active_entities if use_active else all_entities
    field_available = field_available_active if use_active else field_available_all
    numerators = numerator_active if use_active else numerator_all

    if use_active:
        status_note = "Foram consideradas preferencialmente escolas em funcionamento, com TP_SITUACAO_FUNCIONAMENTO = 1, replicando a lógica usada para Tijucas."
    elif status_available:
        status_note = "A variável TP_SITUACAO_FUNCIONAMENTO estava presente, mas não produziu base ativa utilizável; foi usado o total filtrado de escolas de SC."
    else:
        status_note = "A variável TP_SITUACAO_FUNCIONAMENTO não estava disponível com valores preenchidos para o recorte estadual; foi usado o total filtrado de escolas de SC."

    wide_row = {
        "ano": year,
        "territorio": TERRITORIO,
        "nivel_territorial": NIVEL_TERRITORIAL,
        "escolas_total_base_infraestrutura": str(len(denominator_entities)),
    }
    long_rows: list[dict[str, str]] = []
    missing_indicators: list[str] = []
    generated_indicators: list[str] = []

    for spec in INDICATOR_SPECS:
        available_fields = [field for field in spec.fields if field_available[field]]
        if not denominator_entities or not available_fields:
            wide_row[spec.column] = ""
            missing_indicators.append(spec.column)
            missing_note = (
                f"Variáveis não disponíveis ou sem preenchimento no recorte estadual: {', '.join(spec.fields)}."
                if not available_fields
                else "Não foi possível calcular porque o denominador de escolas ficou vazio."
            )
            long_rows.append(
                {
                    "ano": year,
                    "territorio": TERRITORIO,
                    "nivel_territorial": NIVEL_TERRITORIAL,
                    "tema": spec.theme,
                    "indicador": spec.indicator,
                    "valor": "",
                    "unidade": "%",
                    "numerador": "",
                    "denominador": "",
                    "variavel_usada": " | ".join(spec.fields),
                    "fonte": FONTE,
                    "comparabilidade": "não disponível",
                    "observacao_metodologica": build_indicator_observation(spec, year, status_note, missing_note),
                }
            )
            continue

        numerator_value = len(numerators[spec.column])
        denominator_value = len(denominator_entities)
        percentage = round((numerator_value / denominator_value) * 100, 2) if denominator_value else None
        wide_row[spec.column] = format_number(percentage)
        generated_indicators.append(spec.column)
        long_rows.append(
            {
                "ano": year,
                "territorio": TERRITORIO,
                "nivel_territorial": NIVEL_TERRITORIAL,
                "tema": spec.theme,
                "indicador": spec.indicator,
                "valor": format_number(percentage),
                "unidade": "%",
                "numerador": str(numerator_value),
                "denominador": str(denominator_value),
                "variavel_usada": " | ".join(available_fields),
                "fonte": FONTE,
                "comparabilidade": build_comparability(year, True),
                "observacao_metodologica": build_indicator_observation(spec, year, status_note),
            }
        )

    wide_row["fonte"] = FONTE
    wide_row["observacao_metodologica"] = (
        f"{status_note} Arquivo de origem no ano: {sample['arquivo_interno']}. "
        "Indicadores calculados como percentual de escolas com presença declarada da infraestrutura ou recurso."
    )

    summary = {
        "year": year,
        "arquivo_interno": sample["arquivo_interno"],
        "denominator": len(denominator_entities),
        "matched_rows": matched_rows,
        "missing_entity_rows": missing_entity_rows,
        "generated_indicators": generated_indicators,
        "missing_indicators": missing_indicators,
        "status_note": status_note,
        "used_active_filter": use_active,
    }
    return wide_row, long_rows, summary


def build_report_markdown(
    summaries: list[dict[str, object]],
    wide_rows: list[dict[str, str]],
    long_rows: list[dict[str, str]],
) -> str:
    years = [str(summary["year"]) for summary in summaries]
    all_generated = sorted({indicator for summary in summaries for indicator in summary["generated_indicators"]})
    all_missing = sorted({indicator for summary in summaries for indicator in summary["missing_indicators"]})
    latest_year = years[-1] if years else ""
    latest_row = next((row for row in wide_rows if row.get("ano") == latest_year), {})

    lines = [
        "# Relatório dos agregados estaduais de infraestrutura escolar de Santa Catarina",
        "",
        "## Anos processados",
        "",
        f"- {', '.join(years) if years else 'Nenhum ano processado.'}",
        "",
        "## Arquivo interno usado em cada ano",
        "",
        "| ano | arquivo_interno | escolas no denominador | filtro de escolas ativas | linhas filtradas SC | linhas sem CO_ENTIDADE |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for summary in summaries:
        lines.append(
            f"| {summary['year']} | {summary['arquivo_interno']} | {summary['denominator']} | "
            f"{'sim' if summary['used_active_filter'] else 'não'} | {summary['matched_rows']} | {summary['missing_entity_rows']} |"
        )

    lines.extend(
        [
            "",
            "## Indicadores gerados",
            "",
        ]
    )
    if all_generated:
        for indicator in all_generated:
            lines.append(f"- {indicator}")
    else:
        lines.append("- Nenhum indicador foi calculado.")

    lines.extend(
        [
            "",
            "## Indicadores ausentes",
            "",
        ]
    )
    if all_missing:
        for indicator in all_missing:
            lines.append(f"- {indicator}")
    else:
        lines.append("- Nenhum indicador ausente no conjunto processado.")

    lines.extend(
        [
            "",
            "## Denominadores por ano",
            "",
            "| ano | escolas_total_base_infraestrutura |",
            "| --- | --- |",
        ]
    )
    for row in wide_rows:
        lines.append(f"| {row['ano']} | {row['escolas_total_base_infraestrutura']} |")

    lines.extend(
        [
            "",
            "## Observações sobre 2025",
            "",
            "- O ano de 2025 foi calculado a partir de `Tabela_Escola_2025.csv`.",
            "- A comparabilidade dos indicadores disponíveis em 2025 foi marcada como `comparável com adaptação`.",
            "- Indicadores ausentes em 2025 foram mantidos em branco e registrados como `não disponível`.",
            "",
            "## Principais valores do último ano disponível",
            "",
            f"- Ano de referência: {latest_year or 'não disponível'}",
        ]
    )
    if latest_row:
        for spec in INDICATOR_SPECS:
            value = latest_row.get(spec.column, "")
            if value != "":
                lines.append(f"- {spec.column}: {value}%")
    else:
        lines.append("- Não houve resultados para resumir.")

    lines.extend(
        [
            "",
            "## Alertas metodológicos",
            "",
            "- A unidade de análise é escola.",
            "- A lógica de cálculo replica a base de Tijucas: prioridade para escolas em funcionamento e presença em variáveis `IN_*` quando igual a 1.",
            "- Para `perc_escolas_biblioteca_ou_sala_leitura`, a presença foi considerada quando ao menos uma das variáveis `IN_BIBLIOTECA`, `IN_SALA_LEITURA` ou `IN_BIBLIOTECA_SALA_LEITURA` apareceu com valor de presença.",
            "- Para `perc_escolas_banheiro_acessivel`, foi usada a mesma proxy atual de Tijucas: `IN_BANHEIRO_PNE`.",
            "- Para `perc_escolas_salas_acessiveis`, a presença foi considerada quando `QT_SALAS_UTILIZADAS_ACESSIVEIS > 0`.",
            "- Não foram exportados microdados estaduais; apenas agregados anuais leves.",
            "",
            "## Arquivos gerados",
            "",
            f"- `{SC_WIDE_CSV}`",
            f"- `{SC_LONG_CSV}`",
            f"- `{RELATORIO_MD}`",
            "",
            "## Total de registros gerados",
            "",
            f"- Formato wide: {len(wide_rows)} linhas",
            f"- Formato longo: {len(long_rows)} linhas",
            f"- Atualizado em: {ATUALIZADO_EM}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    ensure_output_directories()

    if not AMOSTRAS_CSV.exists():
        print_status("Diagnóstico de amostras não encontrado. Rode scripts\\03_ler_amostras_arquivos_dados.py antes.")
        return

    samples = get_school_samples()
    if not samples:
        print_status("Nenhum arquivo de escola foi identificado em outputs\\diagnosticos\\amostras_arquivos_dados.csv.")
        return

    print_status(f"Arquivos anuais de escola identificados para agregação estadual: {len(samples)}")

    wide_rows: list[dict[str, str]] = []
    long_rows: list[dict[str, str]] = []
    summaries: list[dict[str, object]] = []

    for sample in samples:
        wide_row, long_year_rows, summary = aggregate_year(sample)
        wide_rows.append(wide_row)
        long_rows.extend(long_year_rows)
        summaries.append(summary)

    wide_fieldnames = [
        "ano",
        "territorio",
        "nivel_territorial",
        "escolas_total_base_infraestrutura",
        "perc_escolas_agua_potavel",
        "perc_escolas_internet",
        "perc_escolas_refeitorio",
        "perc_escolas_banheiro_acessivel",
        "perc_escolas_biblioteca_ou_sala_leitura",
        "perc_escolas_laboratorio_informatica",
        "perc_escolas_quadra_esportes",
        "perc_escolas_agua_rede_publica",
        "perc_escolas_energia_rede_publica",
        "perc_escolas_esgoto_rede_publica",
        "perc_escolas_banheiro",
        "perc_escolas_cozinha",
        "perc_escolas_laboratorio_ciencias",
        "perc_escolas_parque_infantil",
        "perc_escolas_banda_larga",
        "perc_escolas_internet_alunos",
        "perc_escolas_internet_aprendizagem",
        "perc_escolas_acessibilidade_rampas",
        "perc_escolas_salas_acessiveis",
        "perc_escolas_sem_recurso_acessibilidade",
        "fonte",
        "observacao_metodologica",
    ]
    long_fieldnames = [
        "ano",
        "territorio",
        "nivel_territorial",
        "tema",
        "indicador",
        "valor",
        "unidade",
        "numerador",
        "denominador",
        "variavel_usada",
        "fonte",
        "comparabilidade",
        "observacao_metodologica",
    ]

    write_csv_dicts(SC_WIDE_CSV, wide_rows, wide_fieldnames)
    write_csv_dicts(SC_LONG_CSV, long_rows, long_fieldnames)

    report_markdown = build_report_markdown(summaries, wide_rows, long_rows)
    RELATORIO_MD.write_text(report_markdown, encoding="utf-8")

    latest_year = max((row["ano"] for row in wide_rows), default="")
    latest_row = next((row for row in wide_rows if row["ano"] == latest_year), {})
    latest_values = [
        f"{column}={latest_row[column]}%"
        for column in latest_row
        if column.startswith("perc_") and latest_row.get(column, "") != ""
    ]
    missing_by_year = {
        summary["year"]: summary["missing_indicators"]
        for summary in summaries
        if summary["missing_indicators"]
    }

    print_status(f"Arquivo gerado: {SC_WIDE_CSV}")
    print_status(f"Arquivo gerado: {SC_LONG_CSV}")
    print_status(f"Arquivo gerado: {RELATORIO_MD}")
    print_status(f"Anos processados: {[summary['year'] for summary in summaries]}")
    for summary in summaries:
        print_status(
            f"Denominador {summary['year']}: {summary['denominator']} escolas; "
            f"indicadores gerados={len(summary['generated_indicators'])}; "
            f"indicadores ausentes={len(summary['missing_indicators'])}"
        )
    print_status(f"Indicadores gerados no conjunto: {sorted({row['indicador'] for row in long_rows if row['valor'] != ''})}")
    print_status(f"Indicadores ausentes por ano: {missing_by_year if missing_by_year else 'nenhum'}")
    print_status(f"Valores de SC no último ano ({latest_year}): {latest_values if latest_values else 'nenhum valor disponível'}")


if __name__ == "__main__":
    main()
