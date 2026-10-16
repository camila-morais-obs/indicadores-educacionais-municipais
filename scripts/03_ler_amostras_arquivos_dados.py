from __future__ import annotations

import csv
import io
import zipfile
from itertools import islice
from statistics import mode
from typing import Iterable

try:
    import pandas as pd
except ImportError:  # pragma: no cover - dependência opcional em tempo de execução
    pd = None

from _project_utils import (
    DIAGNOSTICOS_DIR,
    PROJECT_ROOT,
    detect_year,
    ensure_directories,
    json_dumps,
    normalize_text,
    parse_bool,
    print_status,
    read_csv_dicts,
    relative_to_root,
    write_csv_dicts,
)

CLASSIFICACAO_CSV = DIAGNOSTICOS_DIR / "classificacao_arquivos_internos.csv"
AMOSTRAS_CSV = DIAGNOSTICOS_DIR / "amostras_arquivos_dados.csv"

ENCODINGS = ("utf-8", "latin1", "cp1252")
SEPARATORS = (";", ",", "|", "\t")
MAX_SAMPLE_LINES = 5000
HEAD_BYTES = 512 * 1024


def get_candidate_rows() -> list[dict[str, str]]:
    rows = read_csv_dicts(CLASSIFICACAO_CSV)
    return [
        row
        for row in rows
        if row.get("categoria") == "dados"
        and not parse_bool(row.get("is_dir"))
        and row.get("status", "ok") == "ok"
        and row.get("arquivo_interno")
    ]


def score_separator(lines: list[str], separator: str) -> tuple[int, int]:
    counts: list[int] = []
    for line in lines[:20]:
        try:
            parsed = next(csv.reader([line], delimiter=separator))
        except csv.Error:
            continue
        if len(parsed) > 1:
            counts.append(len(parsed))
    if not counts:
        return (0, 0)
    try:
        common = mode(counts)
    except Exception:
        common = max(counts)
    consistency = sum(1 for count in counts if count == common)
    return (common, consistency)


def detect_encoding_and_separator(zip_path: str, internal_file: str) -> tuple[str, str]:
    full_zip_path = PROJECT_ROOT / zip_path
    with zipfile.ZipFile(full_zip_path) as zip_file:
        with zip_file.open(internal_file) as file_obj:
            sample_bytes = file_obj.read(HEAD_BYTES)

    best_choice: tuple[int, int, str, str] | None = None
    for encoding in ENCODINGS:
        try:
            sample_text = sample_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
        lines = [line for line in sample_text.splitlines() if line.strip()]
        if not lines:
            continue
        for separator in SEPARATORS:
            common, consistency = score_separator(lines, separator)
            if common <= 1:
                continue
            candidate = (common, consistency, encoding, separator)
            if best_choice is None or candidate > best_choice:
                best_choice = candidate

    if best_choice is None:
        raise ValueError("Não foi possível detectar encoding e separador com confiança.")
    return best_choice[2], best_choice[3]


def read_with_pandas(zip_path: str, internal_file: str, encoding: str, separator: str) -> tuple[list[str], int]:
    full_zip_path = PROJECT_ROOT / zip_path
    with zipfile.ZipFile(full_zip_path) as zip_file:
        with zip_file.open(internal_file) as binary_stream:
            text_stream = io.TextIOWrapper(binary_stream, encoding=encoding, newline="")
            dataframe = pd.read_csv(
                text_stream,
                sep=separator,
                nrows=MAX_SAMPLE_LINES,
                engine="python",
                on_bad_lines="skip",
            )
    return [str(column) for column in dataframe.columns], int(len(dataframe))


def read_with_csv_module(zip_path: str, internal_file: str, encoding: str, separator: str) -> tuple[list[str], int]:
    full_zip_path = PROJECT_ROOT / zip_path
    with zipfile.ZipFile(full_zip_path) as zip_file:
        with zip_file.open(internal_file) as binary_stream:
            text_stream = io.TextIOWrapper(binary_stream, encoding=encoding, newline="")
            reader = csv.reader(text_stream, delimiter=separator)
            rows = list(islice(reader, MAX_SAMPLE_LINES + 1))

    if not rows:
        raise ValueError("Arquivo sem linhas legíveis.")

    headers = [str(value).strip() for value in rows[0]]
    if len(headers) <= 1:
        raise ValueError("Cabeçalho com uma única coluna após detecção do separador.")
    data_rows = max(len(rows) - 1, 0)
    return headers, data_rows


def sample_internal_file(row: dict[str, str]) -> dict[str, str]:
    zip_path = row["caminho_zip"]
    internal_file = row["arquivo_interno"]
    year = row.get("ano_detectado") or detect_year(zip_path, internal_file)
    result = {
        "arquivo_zip": row.get("arquivo_zip", ""),
        "arquivo_interno": internal_file,
        "ano_detectado": year,
        "separador_detectado": "",
        "encoding_detectado": "",
        "n_colunas": "",
        "nomes_colunas": "",
        "n_linhas_amostra": "",
        "status": "erro",
        "mensagem_erro": "",
        "metodo_leitura": "",
    }

    try:
        encoding, separator = detect_encoding_and_separator(zip_path, internal_file)
        result["encoding_detectado"] = encoding
        result["separador_detectado"] = "\\t" if separator == "\t" else separator
        if pd is not None:
            columns, row_count = read_with_pandas(zip_path, internal_file, encoding, separator)
            result["metodo_leitura"] = "pandas"
        else:
            columns, row_count = read_with_csv_module(zip_path, internal_file, encoding, separator)
            result["metodo_leitura"] = "fallback_csv"

        result["n_colunas"] = str(len(columns))
        result["nomes_colunas"] = json_dumps(columns)
        result["n_linhas_amostra"] = str(row_count)
        result["status"] = "ok"
        if pd is None:
            result["mensagem_erro"] = "pandas não está instalado; foi usada leitura leve via csv padrão."
        return result
    except Exception as exc:  # pragma: no cover - tratamento operacional
        result["mensagem_erro"] = str(exc)
        return result


def main() -> None:
    ensure_directories()
    candidate_rows = get_candidate_rows()

    if not candidate_rows:
        write_csv_dicts(
            AMOSTRAS_CSV,
            [],
            [
                "arquivo_zip",
                "arquivo_interno",
                "ano_detectado",
                "separador_detectado",
                "encoding_detectado",
                "n_colunas",
                "nomes_colunas",
                "n_linhas_amostra",
                "status",
                "mensagem_erro",
                "metodo_leitura",
            ],
        )
        print_status(
            "Nenhum arquivo classificado como dados foi encontrado. Rode scripts\\02_classificar_arquivos_internos.py."
        )
        return

    if pd is None:
        print_status("pandas não está disponível. O script seguirá com leitura leve de fallback para manter o diagnóstico.")
    else:
        print_status("pandas detectado. A leitura das amostras será feita com pandas.")

    results: list[dict[str, str]] = []
    for row in candidate_rows:
        print_status(f"Lendo amostra de {row['arquivo_zip']} -> {row['arquivo_interno']}")
        results.append(sample_internal_file(row))

    write_csv_dicts(
        AMOSTRAS_CSV,
        results,
        [
            "arquivo_zip",
            "arquivo_interno",
            "ano_detectado",
            "separador_detectado",
            "encoding_detectado",
            "n_colunas",
            "nomes_colunas",
            "n_linhas_amostra",
            "status",
            "mensagem_erro",
            "metodo_leitura",
        ],
    )

    success_count = sum(1 for row in results if row["status"] == "ok")
    print_status(f"Amostras salvas em: {AMOSTRAS_CSV}")
    print_status(f"Leituras com sucesso: {success_count} de {len(results)}")


if __name__ == "__main__":
    main()
