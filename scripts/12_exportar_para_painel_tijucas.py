from __future__ import annotations

import csv
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
    ensure_directories,
    parse_float,
    print_status,
    read_csv_dicts,
)

EXPORT_BASE = PROJECT_ROOT / "exports" / "painel_educacao_tijucas"
DATA_PROCESSED_DIR = EXPORT_BASE / "data_processed"
DATA_PUBLISHED_DIR = EXPORT_BASE / "data_published"
PUBLIC_DATA_DIR = EXPORT_BASE / "public_data"
PUBLIC_DOWNLOADS_DIR = EXPORT_BASE / "public_downloads"
REFERENCES_DIR = EXPORT_BASE / "references"
DOCS_DIR = EXPORT_BASE / "docs"

RELATORIOS_DIR = OUTPUTS_DIR / "relatorios"

PROCESSED_FILES = [
    "painel_educacao_tijucas_rede_escolar.csv",
    "painel_educacao_tijucas_matriculas.csv",
    "painel_educacao_tijucas_docentes_turmas.csv",
    "painel_educacao_tijucas_infraestrutura.csv",
    "painel_educacao_tijucas_tecnologia_acessibilidade.csv",
    "painel_educacao_tijucas_mapa_escolas.csv",
    "painel_educacao_tijucas_indicadores_long.csv",
]

PROCESSED_PATHS = {name: PROCESSED_DIR / name for name in PROCESSED_FILES}
METADATA_PATH = PROCESSED_DIR / "metadata_educacao_tijucas.json"
REPORT_MD_PATH = RELATORIOS_DIR / "relatorio_bases_painel_educacao.md"
REPORT_HTML_PATH = RELATORIOS_DIR / "relatorio_bases_painel_educacao.html"

JSON_TARGETS = {
    "educacao_indicadores_long.json": None,
    "educacao_series_temporais.json": None,
    "educacao_cards_resumo.json": None,
    "educacao_mapa_escolas.json": None,
    "educacao_metadata.json": None,
}

PENDING_COMPLEMENTARY = [
    {
        "nome": "IDEB",
        "tema": "Qualidade e fluxo escolar",
        "descricao": "Indicador oficial de desenvolvimento da educação básica, não incluído neste pacote.",
    },
    {
        "nome": "Saeb",
        "tema": "Qualidade e fluxo escolar",
        "descricao": "Resultados do Saeb, dependentes de base complementar do INEP.",
    },
    {
        "nome": "Aprovação",
        "tema": "Qualidade e fluxo escolar",
        "descricao": "Indicador de fluxo escolar, dependente de base complementar do INEP.",
    },
    {
        "nome": "Reprovação",
        "tema": "Qualidade e fluxo escolar",
        "descricao": "Indicador de fluxo escolar, dependente de base complementar do INEP.",
    },
    {
        "nome": "Abandono",
        "tema": "Qualidade e fluxo escolar",
        "descricao": "Indicador de fluxo escolar, dependente de base complementar do INEP.",
    },
    {
        "nome": "Distorção idade-série",
        "tema": "Qualidade e fluxo escolar",
        "descricao": "Indicador educacional oficial, dependente de base complementar do INEP.",
    },
]

CARD_PRIORITY = [
    "Escolas em funcionamento",
    "Matrículas totais da educação básica",
    "Docentes totais",
    "Turmas totais",
    "Percentual de escolas com internet",
    "Percentual de escolas com água potável",
]


def ensure_export_directories() -> None:
    ensure_directories()
    for path in (
        EXPORT_BASE,
        DATA_PROCESSED_DIR,
        DATA_PUBLISHED_DIR,
        PUBLIC_DATA_DIR,
        PUBLIC_DOWNLOADS_DIR,
        REFERENCES_DIR,
        DOCS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def load_csv(path: Path) -> list[dict[str, str]]:
    return read_csv_dicts(path) if path.exists() else []


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def yaml_scalar(value: object) -> str:
    text = "" if value is None else str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_yaml_list(path: Path, root_key: str, items: list[dict[str, object]]) -> None:
    lines = [f"{root_key}:"]
    for item in items:
        lines.append("  -")
        for key, value in item.items():
            if isinstance(value, list):
                if not value:
                    lines.append(f"    {key}: []")
                else:
                    lines.append(f"    {key}:")
                    for entry in value:
                        lines.append(f"      - {yaml_scalar(entry)}")
            else:
                lines.append(f"    {key}: {yaml_scalar(value)}")
    write_text(path, "\n".join(lines).strip() + "\n")


def file_stats(path: Path) -> dict[str, object]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows = len(payload)
            years = sorted({str(item.get("ano")) for item in payload if isinstance(item, dict) and item.get("ano") not in (None, "")})
        elif isinstance(payload, dict):
            if "registros" in payload and isinstance(payload["registros"], list):
                rows = len(payload["registros"])
            elif "series" in payload and isinstance(payload["series"], list):
                rows = len(payload["series"])
            elif "cards" in payload and isinstance(payload["cards"], list):
                rows = len(payload["cards"])
            else:
                rows = len(payload)
            years = sorted({str(value) for value in payload.get("anos_disponiveis", [])}) if isinstance(payload, dict) else []
        else:
            rows = 0
            years = []
        return {
            "arquivo": path.name,
            "linhas": rows,
            "colunas": 0,
            "anos": years,
            "tamanho_bytes": path.stat().st_size,
            "tipo": "json",
        }

    rows = load_csv(path)
    columns = list(rows[0].keys()) if rows else []
    years = sorted({row.get("ano", "") for row in rows if row.get("ano")})
    return {
        "arquivo": path.name,
        "linhas": len(rows),
        "colunas": len(columns),
        "anos": years,
        "tamanho_bytes": path.stat().st_size,
        "tipo": "csv",
    }


def gather_missing_alerts(csv_rows_map: dict[str, list[dict[str, str]]]) -> list[str]:
    alerts: list[str] = []
    for file_name, rows in csv_rows_map.items():
        if not rows:
            alerts.append(f"{file_name}: arquivo vazio ou não encontrado")
            continue
        columns = [column for column in rows[0].keys() if column != "ano"]
        for column in columns:
            missing_years = sorted({row.get("ano", "") for row in rows if row.get("ano") and row.get(column, "") == ""})
            if missing_years:
                alerts.append(f"{file_name}: {column} ausente em {', '.join(missing_years)}")
    return alerts


def build_series_temporais(indicators_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for row in indicators_rows:
        key = (row.get("tema", ""), row.get("indicador", ""))
        item = grouped.setdefault(
            key,
            {
                "tema": row.get("tema", ""),
                "indicador": row.get("indicador", ""),
                "unidade": row.get("unidade", ""),
                "fonte": row.get("fonte", ""),
                "base_origem": row.get("base_origem", ""),
                "variaveis_usadas": row.get("variaveis_usadas", ""),
                "comparabilidade_2014_2025": row.get("comparabilidade_2014_2025", ""),
                "observacao_metodologica": row.get("observacao_metodologica", ""),
                "serie": [],
            },
        )
        item["serie"].append(
            {
                "ano": row.get("ano", ""),
                "valor": parse_float(row.get("valor", "")) if row.get("valor", "") not in ("", None) else None,
            }
        )

    series = list(grouped.values())
    for item in series:
        item["serie"] = sorted(item["serie"], key=lambda point: str(point.get("ano", "")))
    series.sort(key=lambda item: (item["tema"], item["indicador"]))
    return series


def build_cards_resumo(indicators_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    if not indicators_rows:
        return []
    latest_year = max(row.get("ano", "") for row in indicators_rows if row.get("ano"))
    latest_rows = [row for row in indicators_rows if row.get("ano") == latest_year]
    by_indicator = {row.get("indicador", ""): row for row in latest_rows}

    cards: list[dict[str, object]] = []
    for indicator in CARD_PRIORITY:
        row = by_indicator.get(indicator)
        if not row:
            continue
        cards.append(
            {
                "ano": latest_year,
                "tema": row.get("tema", ""),
                "indicador": indicator,
                "valor": parse_float(row.get("valor", "")) if row.get("valor", "") not in ("", None) else row.get("valor", ""),
                "unidade": row.get("unidade", ""),
                "fonte": row.get("fonte", ""),
                "observacao": row.get("observacao_metodologica", ""),
                "comparabilidade_2014_2025": row.get("comparabilidade_2014_2025", ""),
            }
        )
    return cards


def build_map_payload(map_rows: list[dict[str, str]]) -> dict[str, object]:
    years = sorted({row.get("ano", "") for row in map_rows if row.get("ano")})
    return {
        "anos_disponiveis": years,
        "registros": map_rows,
        "observacao": "Mapa de escolas deve ser tratado como localização de equipamentos educacionais, não como ranking de desempenho.",
    }


def build_metadata_payload(
    metadata: dict,
    indicators_rows: list[dict[str, str]],
    map_rows: list[dict[str, str]],
    csv_rows_map: dict[str, list[dict[str, str]]],
    alerts: list[str],
) -> dict[str, object]:
    years = sorted({row.get("ano", "") for row in indicators_rows if row.get("ano")})
    return {
        "pacote": "educacao_tijucas",
        "municipio": metadata.get("municipio", "Tijucas"),
        "uf": metadata.get("uf", "SC"),
        "fonte_principal": metadata.get("fonte_principal", "Censo Escolar/INEP"),
        "anos_disponiveis": years,
        "arquivos_csv": sorted(csv_rows_map.keys()),
        "jsons_publicados": sorted(JSON_TARGETS.keys()),
        "linhas_mapa_escolas": len(map_rows),
        "limitacoes": metadata.get("observacoes_metodologicas", []),
        "cuidados_publicacao": metadata.get("cuidados_publicacao", []),
        "alertas_variaveis_ausentes": alerts,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }


def build_indicator_catalog(indicators_rows: list[dict[str, str]], years_count: int) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for row in indicators_rows:
        indicator = row.get("indicador", "")
        if not indicator:
            continue
        item = grouped.setdefault(
            indicator,
            {
                "nome_do_indicador": indicator,
                "tema": row.get("tema", ""),
                "descricao": row.get("observacao_metodologica", "") or f"Indicador agregado de {indicator} para Tijucas/SC.",
                "fonte": row.get("fonte", ""),
                "base_de_origem": row.get("base_origem", ""),
                "variaveis_usadas": row.get("variaveis_usadas", ""),
                "periodicidade": "anual",
                "nivel_de_agregacao": row.get("nivel_agregacao", ""),
                "unidade": row.get("unidade", ""),
                "observacoes_metodologicas": row.get("observacao_metodologica", ""),
                "comparabilidade_2014_2025": row.get("comparabilidade_2014_2025", ""),
                "anos_com_dados": set(),
            },
        )
        item["anos_com_dados"].add(row.get("ano", ""))

    catalog: list[dict[str, object]] = []
    for item in grouped.values():
        years_available = sorted(year for year in item.pop("anos_com_dados") if year)
        status = "calculado" if len(years_available) == years_count else "parcial"
        catalog.append(
            {
                **item,
                "anos_com_dados": years_available,
                "status": status,
            }
        )

    for pending in PENDING_COMPLEMENTARY:
        catalog.append(
            {
                "nome_do_indicador": pending["nome"],
                "tema": pending["tema"],
                "descricao": pending["descricao"],
                "fonte": "INEP",
                "base_de_origem": "base complementar pendente",
                "variaveis_usadas": "a definir após download da base complementar",
                "periodicidade": "anual",
                "nivel_de_agregacao": "município/ano",
                "unidade": "a definir",
                "observacoes_metodologicas": "Não incluído neste pacote porque exige base complementar do INEP.",
                "comparabilidade_2014_2025": "pendente",
                "anos_com_dados": [],
                "status": "pendente_base_complementar",
            }
        )

    catalog.sort(key=lambda item: (item["tema"], item["nome_do_indicador"]))
    return catalog


def build_sources_reference(metadata: dict) -> list[dict[str, object]]:
    return [
        {
            "id": "censo_escolar_inep",
            "nome": "Censo Escolar/INEP",
            "descricao": "Fonte principal dos indicadores agregados de rede, matrículas, docentes, turmas, infraestrutura e tecnologia.",
            "periodicidade": "anual",
            "anos_disponiveis": metadata.get("anos_processados", []),
            "observacoes": [
                "Dados filtrados para Tijucas/SC.",
                "A estrutura de 2025 é multi-tabela e exige adaptação para comparabilidade.",
                "Não contém diretamente IDEB, Saeb, aprovação, reprovação, abandono e distorção idade-série.",
            ],
        },
        {
            "id": "bases_complementares_inep",
            "nome": "Bases complementares do INEP",
            "descricao": "Conjunto futuro necessário para IDEB, Saeb e indicadores oficiais de fluxo escolar.",
            "periodicidade": "anual ou bianual, conforme a base",
            "anos_disponiveis": [],
            "observacoes": [
                "Necessárias para IDEB, Saeb, aprovação, reprovação, abandono e distorção idade-série.",
                "Não incluídas no pacote atual de exportação.",
            ],
        },
    ]


def build_methodological_note() -> str:
    return "\n".join(
        [
            "# Nota metodologica da educacao de Tijucas",
            "",
            "## Escopo",
            "",
            "Esta exportacao foi preparada a partir de bases filtradas e agregadas do Censo Escolar/INEP para o municipio de Tijucas/SC.",
            "",
            "## Fonte principal",
            "",
            "- Os indicadores foram construidos a partir dos microdados do Censo Escolar/INEP.",
            "- O pacote exportado nao contem microdados brutos nem bases intermediarias.",
            "- As bases foram consolidadas para consumo em painel publico e download controlado.",
            "",
            "## Indicadores nao incluidos",
            "",
            "- IDEB, Saeb, aprovacao, reprovacao, abandono e distorcao idade-serie exigem bases complementares do INEP.",
            "- Esses indicadores nao devem ser inferidos diretamente deste pacote, salvo nova validacao metodologica com outras fontes.",
            "",
            "## Comparabilidade de 2025",
            "",
            "- Em 2025, a estrutura do Censo Escolar mudou de um arquivo consolidado para um conjunto de tabelas tematicas.",
            "- Para manter comparabilidade, os indicadores de 2025 foram agregados ao nivel escola/ano e depois consolidados para municipio/ano.",
            "- A leitura recomendada para a maior parte dos indicadores e `comparavel com adaptacao`.",
            "",
            "## Mapa das escolas",
            "",
            "- O mapa de escolas deve ser tratado como localizacao de equipamentos educacionais.",
            "- O mapa nao deve ser usado como ranking de desempenho escolar.",
            "- Coordenadas geograficas apareceram explicitamente apenas em 2025, por isso a base de mapa foi restrita a esse ano.",
            "",
            "## Privacidade",
            "",
            "- Nao ha dados individualizados de alunos neste pacote.",
            "- Nao devem ser publicados microdados de estudantes, docentes ou gestores.",
            "",
        ]
    ).strip() + "\n"


def build_readme_exportacao() -> str:
    return "\n".join(
        [
            "# README da exportacao para o painel Tijucas",
            "",
            "Copie as pastas abaixo para o repositório `poc_painel_tijucas` exatamente nos destinos informados:",
            "",
            "- `exports/painel_educacao_tijucas/data_processed/*`",
            "  → `poc_painel_tijucas/data/processed/educacao/`",
            "- `exports/painel_educacao_tijucas/data_published/*`",
            "  → `poc_painel_tijucas/data/published/educacao/`",
            "- `exports/painel_educacao_tijucas/public_data/*`",
            "  → `poc_painel_tijucas/public/data/educacao/`",
            "- `exports/painel_educacao_tijucas/public_downloads/*`",
            "  → `poc_painel_tijucas/public/downloads/educacao/`",
            "- `exports/painel_educacao_tijucas/references/*`",
            "  → `poc_painel_tijucas/references/`",
            "- `exports/painel_educacao_tijucas/docs/*`",
            "  → `poc_painel_tijucas/docs/educacao/`",
            "",
            "Observacoes:",
            "",
            "- Nao copiar `data/raw` nem `data/interim`.",
            "- Nao copiar microdados brutos.",
            "- Priorizar `public_data` para consumo do app React/Vite e `public_downloads` para os arquivos disponibilizados ao usuario.",
            "",
        ]
    ).strip() + "\n"


def markdown_to_html(markdown_text: str) -> str:
    html_lines = [
        "<!DOCTYPE html>",
        '<html lang="pt-BR">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Nota metodologica da educacao de Tijucas</title>",
        "<style>",
        "body { font-family: 'Segoe UI', Arial, sans-serif; margin: 40px auto; max-width: 960px; line-height: 1.6; color: #1f2933; padding: 0 24px; }",
        "h1, h2, h3 { color: #102a43; }",
        "code { background: #f0f4f8; padding: 1px 4px; border-radius: 4px; }",
        "ul { margin-top: 8px; margin-bottom: 16px; }",
        "</style>",
        "</head>",
        "<body>",
    ]

    def inline(text: str) -> str:
        escaped = html.escape(text)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)

    paragraph_buffer: list[str] = []
    list_buffer: list[str] = []
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            if paragraph_buffer:
                html_lines.append(f"<p>{inline(' '.join(paragraph_buffer))}</p>")
                paragraph_buffer.clear()
            if list_buffer:
                html_lines.append("<ul>")
                for item in list_buffer:
                    html_lines.append(f"<li>{inline(item)}</li>")
                html_lines.append("</ul>")
                list_buffer.clear()
            continue
        if stripped.startswith("# "):
            if paragraph_buffer:
                html_lines.append(f"<p>{inline(' '.join(paragraph_buffer))}</p>")
                paragraph_buffer.clear()
            if list_buffer:
                html_lines.append("<ul>")
                for item in list_buffer:
                    html_lines.append(f"<li>{inline(item)}</li>")
                html_lines.append("</ul>")
                list_buffer.clear()
            html_lines.append(f"<h1>{inline(stripped[2:])}</h1>")
            continue
        if stripped.startswith("## "):
            if paragraph_buffer:
                html_lines.append(f"<p>{inline(' '.join(paragraph_buffer))}</p>")
                paragraph_buffer.clear()
            if list_buffer:
                html_lines.append("<ul>")
                for item in list_buffer:
                    html_lines.append(f"<li>{inline(item)}</li>")
                html_lines.append("</ul>")
                list_buffer.clear()
            html_lines.append(f"<h2>{inline(stripped[3:])}</h2>")
            continue
        if stripped.startswith("- "):
            if paragraph_buffer:
                html_lines.append(f"<p>{inline(' '.join(paragraph_buffer))}</p>")
                paragraph_buffer.clear()
            list_buffer.append(stripped[2:])
            continue
        if list_buffer:
            html_lines.append("<ul>")
            for item in list_buffer:
                html_lines.append(f"<li>{inline(item)}</li>")
            html_lines.append("</ul>")
            list_buffer.clear()
        paragraph_buffer.append(stripped)

    if paragraph_buffer:
        html_lines.append(f"<p>{inline(' '.join(paragraph_buffer))}</p>")
    if list_buffer:
        html_lines.append("<ul>")
        for item in list_buffer:
            html_lines.append(f"<li>{inline(item)}</li>")
        html_lines.append("</ul>")
    html_lines.extend(["</body>", "</html>"])
    return "\n".join(html_lines)


def main() -> None:
    ensure_export_directories()

    missing_sources = [str(path.name) for path in list(PROCESSED_PATHS.values()) + [METADATA_PATH, REPORT_MD_PATH, REPORT_HTML_PATH] if not path.exists()]
    if missing_sources:
        print_status(f"Arquivos obrigatórios não encontrados: {', '.join(missing_sources)}")
        print_status("Rode scripts\\11_gerar_bases_painel_educacao.py antes da exportação.")
        return

    csv_rows_map = {name: load_csv(path) for name, path in PROCESSED_PATHS.items()}
    indicators_rows = csv_rows_map["painel_educacao_tijucas_indicadores_long.csv"]
    map_rows = csv_rows_map["painel_educacao_tijucas_mapa_escolas.csv"]
    metadata = load_json(METADATA_PATH)
    alerts = gather_missing_alerts(
        {
            name: rows
            for name, rows in csv_rows_map.items()
            if name != "painel_educacao_tijucas_indicadores_long.csv" and name != "painel_educacao_tijucas_mapa_escolas.csv"
        }
    )

    print_status("Copiando CSVs tratados para data_processed e public_downloads.")
    for name, source in PROCESSED_PATHS.items():
        copy_file(source, DATA_PROCESSED_DIR / name)
        copy_file(source, PUBLIC_DOWNLOADS_DIR / name)

    print_status("Gerando JSONs de publicação para o painel.")
    indicators_long_json = indicators_rows
    series_temporais_json = {
        "anos_disponiveis": sorted({row.get("ano", "") for row in indicators_rows if row.get("ano")}),
        "series": build_series_temporais(indicators_rows),
    }
    cards_resumo_json = {
        "cards": build_cards_resumo(indicators_rows),
        "observacao": "Cards resumem o último ano disponível da base agregada.",
    }
    mapa_escolas_json = build_map_payload(map_rows)
    metadata_json = build_metadata_payload(metadata, indicators_rows, map_rows, csv_rows_map, alerts)

    json_payloads = {
        "educacao_indicadores_long.json": indicators_long_json,
        "educacao_series_temporais.json": series_temporais_json,
        "educacao_cards_resumo.json": cards_resumo_json,
        "educacao_mapa_escolas.json": mapa_escolas_json,
        "educacao_metadata.json": metadata_json,
    }

    for file_name, payload in json_payloads.items():
        write_json(DATA_PUBLISHED_DIR / file_name, payload)
        write_json(PUBLIC_DATA_DIR / file_name, payload)

    print_status("Gerando catálogo de fontes e indicadores.")
    years_count = len(series_temporais_json["anos_disponiveis"])
    write_yaml_list(
        REFERENCES_DIR / "fontes_indicadores_educacao.yml",
        "fontes",
        build_sources_reference(metadata),
    )
    write_yaml_list(
        REFERENCES_DIR / "indicadores_catalogo_educacao.yml",
        "indicadores",
        build_indicator_catalog(indicators_rows, years_count),
    )

    print_status("Gerando documentação metodológica e instruções de cópia.")
    copy_file(REPORT_MD_PATH, DOCS_DIR / REPORT_MD_PATH.name)
    copy_file(REPORT_HTML_PATH, DOCS_DIR / REPORT_HTML_PATH.name)
    note_md = build_methodological_note()
    write_text(DOCS_DIR / "nota_metodologica_educacao_tijucas.md", note_md)
    write_text(EXPORT_BASE / "README_EXPORTACAO.md", build_readme_exportacao())

    export_stats_paths = []
    export_stats_paths.extend(DATA_PROCESSED_DIR.glob("*"))
    export_stats_paths.extend(DATA_PUBLISHED_DIR.glob("*"))
    export_stats_paths.extend(PUBLIC_DATA_DIR.glob("*"))
    export_stats_paths.extend(PUBLIC_DOWNLOADS_DIR.glob("*"))
    export_stats_paths.extend(REFERENCES_DIR.glob("*"))
    export_stats_paths.extend(DOCS_DIR.glob("*"))
    export_stats_paths.append(EXPORT_BASE / "README_EXPORTACAO.md")

    print_status(f"Arquivo gerado: {EXPORT_BASE / 'README_EXPORTACAO.md'}")
    for directory in (DATA_PROCESSED_DIR, DATA_PUBLISHED_DIR, PUBLIC_DATA_DIR, PUBLIC_DOWNLOADS_DIR, REFERENCES_DIR, DOCS_DIR):
        print_status(f"Pasta atualizada: {directory}")
        for path in sorted(directory.glob("*")):
            print_status(f" - {path.name}")

    csv_and_json_stats = []
    for path in sorted(DATA_PROCESSED_DIR.glob("*.csv")):
        csv_and_json_stats.append(file_stats(path))
    for path in sorted(DATA_PUBLISHED_DIR.glob("*.json")):
        csv_and_json_stats.append(file_stats(path))

    for stat in csv_and_json_stats:
        print_status(
            f"Resumo {stat['arquivo']}: registros={stat['linhas']}, colunas={stat['colunas']}, anos={stat['anos']}, tamanho_bytes={stat['tamanho_bytes']}"
        )

    if alerts:
        preview = alerts[:10]
        for alert in preview:
            print_status(f"Alerta: {alert}")
        if len(alerts) > len(preview):
            print_status(f"Alertas adicionais omitidos no terminal: {len(alerts) - len(preview)}")

    print_status("Próximos passos para integrar ao React: criar loaders para public/data/educacao, usar cards do último ano, séries de educacao_series_temporais.json e mapa apenas para equipamentos educacionais.")


if __name__ == "__main__":
    main()
