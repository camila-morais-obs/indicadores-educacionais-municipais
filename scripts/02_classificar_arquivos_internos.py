from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from _project_utils import (
    DIAGNOSTICOS_DIR,
    TABELAS_DIR,
    normalize_text,
    parse_bool,
    parse_float,
    read_csv_dicts,
    ensure_directories,
    print_status,
    write_csv_dicts,
)

CONTEUDO_ZIPS_CSV = DIAGNOSTICOS_DIR / "conteudo_zips_inep.csv"
CLASSIFICACAO_CSV = DIAGNOSTICOS_DIR / "classificacao_arquivos_internos.csv"
RESUMO_CSV = TABELAS_DIR / "resumo_tipos_arquivos_internos.csv"

DICIONARIO_KEYWORDS = ("dicionario", "layout", "variavel", "variaveis", "metadado")
LEIAME_KEYWORDS = ("leia_me", "leia me", "readme", "read_me", "leiame")
DOCUMENTO_KEYWORDS = ("manual", "instrucoes", "instrucao", "metodologia", "nota tecnica", "documentacao")
OUTRO_KEYWORDS = ("md5", "checksum")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".svg"}
SPREADSHEET_EXTENSIONS = {".xls", ".xlsx", ".ods"}
DATA_EXTENSIONS = {".csv", ".txt", ".tsv", ".dat"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx"}


def classify_row(row: dict[str, str]) -> str:
    if parse_bool(row.get("is_dir")):
        return "pasta"

    path_obj = Path(row.get("arquivo_interno", ""))
    normalized_name = normalize_text(path_obj.name)
    extension = (row.get("extensao_interna") or "").lower()

    if any(keyword in normalized_name for keyword in OUTRO_KEYWORDS):
        return "outro"
    if any(keyword in normalized_name for keyword in DICIONARIO_KEYWORDS):
        return "dicionario"
    if any(keyword in normalized_name for keyword in LEIAME_KEYWORDS):
        return "leia_me"
    if extension in SPREADSHEET_EXTENSIONS:
        return "planilha"
    if extension in IMAGE_EXTENSIONS:
        return "imagem"
    if any(keyword in normalized_name for keyword in DOCUMENTO_KEYWORDS):
        return "documento_tecnico"
    if extension in DOCUMENT_EXTENSIONS:
        return "documento_tecnico"
    if extension in DATA_EXTENSIONS:
        return "dados"
    return "outro"


def build_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    aggregated: dict[tuple[str, str, str], dict[str, float | int | str]] = {}
    for row in rows:
        key = (
            row.get("ano_detectado") or "",
            row.get("categoria") or "outro",
            row.get("extensao_interna") or "",
        )
        current = aggregated.setdefault(
            key,
            {
                "ano_detectado": key[0],
                "categoria": key[1],
                "extensao_interna": key[2],
                "quantidade_arquivos": 0,
                "tamanho_total_mb": 0.0,
            },
        )
        current["quantidade_arquivos"] = int(current["quantidade_arquivos"]) + 1
        current["tamanho_total_mb"] = float(current["tamanho_total_mb"]) + parse_float(row.get("tamanho_mb"))

    summary_rows = []
    for item in aggregated.values():
        summary_rows.append(
            {
                "ano_detectado": item["ano_detectado"],
                "categoria": item["categoria"],
                "extensao_interna": item["extensao_interna"],
                "quantidade_arquivos": str(item["quantidade_arquivos"]),
                "tamanho_total_mb": f"{float(item['tamanho_total_mb']):.4f}",
            }
        )
    return sorted(summary_rows, key=lambda row: (row["ano_detectado"], row["categoria"], row["extensao_interna"]))


def main() -> None:
    ensure_directories()
    rows = read_csv_dicts(CONTEUDO_ZIPS_CSV)

    if not rows:
        write_csv_dicts(
            CLASSIFICACAO_CSV,
            [],
            [
                "arquivo_zip",
                "caminho_zip",
                "arquivo_interno",
                "extensao_interna",
                "tamanho_mb",
                "compress_size_mb",
                "is_dir",
                "ano_detectado",
                "status",
                "mensagem_erro",
                "categoria",
            ],
        )
        write_csv_dicts(
            RESUMO_CSV,
            [],
            ["ano_detectado", "categoria", "extensao_interna", "quantidade_arquivos", "tamanho_total_mb"],
        )
        print_status(
            "Arquivo de conteúdo dos zips não encontrado ou vazio. Rode primeiro scripts\\01_listar_arquivos_zip.py."
        )
        return

    classified_rows: list[dict[str, str]] = []
    category_counter = defaultdict(int)

    for row in rows:
        category = classify_row(row)
        new_row = dict(row)
        new_row["categoria"] = category
        classified_rows.append(new_row)
        category_counter[category] += 1

    write_csv_dicts(
        CLASSIFICACAO_CSV,
        classified_rows,
        list(classified_rows[0].keys()),
    )
    summary_rows = build_summary(classified_rows)
    write_csv_dicts(
        RESUMO_CSV,
        summary_rows,
        ["ano_detectado", "categoria", "extensao_interna", "quantidade_arquivos", "tamanho_total_mb"],
    )

    print_status(f"Classificação salva em: {CLASSIFICACAO_CSV}")
    print_status(f"Resumo salvo em: {RESUMO_CSV}")
    print_status(f"Arquivos internos por categoria: {dict(sorted(category_counter.items()))}")


if __name__ == "__main__":
    main()
