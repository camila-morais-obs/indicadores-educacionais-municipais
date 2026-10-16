from __future__ import annotations

import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from _project_utils import (
    DIAGNOSTICOS_DIR,
    PROJECT_ROOT,
    RAW_DIR,
    detect_year,
    ensure_directories,
    print_status,
    relative_to_root,
    to_mb,
    write_csv_dicts,
)

INVENTARIO_CSV = DIAGNOSTICOS_DIR / "inventario_data_raw.csv"
CONTEUDO_ZIPS_CSV = DIAGNOSTICOS_DIR / "conteudo_zips_inep.csv"


def build_inventory(raw_dir: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for path in sorted(item for item in raw_dir.rglob("*") if item.is_file()):
        relative_raw = path.relative_to(raw_dir)
        records.append(
            {
                "caminho_relativo": relative_to_root(path),
                "nome_arquivo": path.name,
                "extensao": path.suffix.lower(),
                "tamanho_mb": f"{to_mb(path.stat().st_size):.4f}",
                "pasta_pai": relative_to_root(path.parent),
                "nivel_profundidade": str(max(len(relative_raw.parts) - 1, 0)),
                "data_modificacao": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )
    return records


def list_zip_contents(zip_paths: list[Path]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for zip_path in zip_paths:
        zip_relative = relative_to_root(zip_path)
        year_from_zip = detect_year(zip_path.name, zip_relative)
        print_status(f"Lendo zip sem extrair: {zip_relative}")
        try:
            with zipfile.ZipFile(zip_path) as zip_file:
                for info in zip_file.infolist():
                    internal_name = info.filename
                    internal_path = Path(internal_name)
                    records.append(
                        {
                            "arquivo_zip": zip_path.name,
                            "caminho_zip": zip_relative,
                            "arquivo_interno": internal_name,
                            "extensao_interna": internal_path.suffix.lower(),
                            "tamanho_mb": f"{to_mb(info.file_size):.4f}",
                            "compress_size_mb": f"{to_mb(info.compress_size):.4f}",
                            "is_dir": str(info.is_dir()),
                            "ano_detectado": detect_year(zip_path.name, internal_name, year_from_zip),
                            "status": "ok",
                            "mensagem_erro": "",
                        }
                    )
        except (OSError, zipfile.BadZipFile) as exc:
            records.append(
                {
                    "arquivo_zip": zip_path.name,
                    "caminho_zip": zip_relative,
                    "arquivo_interno": "",
                    "extensao_interna": "",
                    "tamanho_mb": "",
                    "compress_size_mb": "",
                    "is_dir": "False",
                    "ano_detectado": year_from_zip,
                    "status": "erro",
                    "mensagem_erro": str(exc),
                }
            )
            print_status(f"Falha ao ler {zip_relative}: {exc}")
    return records


def main() -> None:
    ensure_directories()

    print_status(f"Pasta base: {PROJECT_ROOT}")
    print_status(f"Pasta raw: {RAW_DIR}")
    print_status(f"raw existe: {RAW_DIR.exists()}")

    if not RAW_DIR.exists():
        write_csv_dicts(
            INVENTARIO_CSV,
            [],
            [
                "caminho_relativo",
                "nome_arquivo",
                "extensao",
                "tamanho_mb",
                "pasta_pai",
                "nivel_profundidade",
                "data_modificacao",
            ],
        )
        write_csv_dicts(
            CONTEUDO_ZIPS_CSV,
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
            ],
        )
        print_status("Diretório data/raw não encontrado. CSVs de diagnóstico foram criados vazios.")
        return

    files_in_raw = sorted(item for item in RAW_DIR.rglob("*") if item.is_file())
    inventory = build_inventory(RAW_DIR)
    write_csv_dicts(
        INVENTARIO_CSV,
        inventory,
        [
            "caminho_relativo",
            "nome_arquivo",
            "extensao",
            "tamanho_mb",
            "pasta_pai",
            "nivel_profundidade",
            "data_modificacao",
        ],
    )

    extension_counter = Counter(path.suffix.lower() or "[sem_extensao]" for path in files_in_raw)
    print_status(f"Quantidade de arquivos encontrados em raw: {len(files_in_raw)}")
    print_status(f"Extensões encontradas em raw: {dict(sorted(extension_counter.items()))}")

    zip_paths = sorted(path for path in files_in_raw if path.suffix.lower() == ".zip")
    print_status(f"Quantidade de zips encontrados: {len(zip_paths)}")

    if not zip_paths:
        write_csv_dicts(
            CONTEUDO_ZIPS_CSV,
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
            ],
        )
        print_status("Nenhum arquivo .zip foi encontrado em data/raw.")
        entries = sorted(RAW_DIR.rglob("*"))[:100]
        for entry in entries:
            kind = "dir" if entry.is_dir() else "file"
            print_status(f"Entrada em raw ({kind}): {relative_to_root(entry)}")
        print_status("Encerrando após listar as primeiras 100 entradas encontradas em raw.")
        return

    zip_records = list_zip_contents(zip_paths)
    write_csv_dicts(
        CONTEUDO_ZIPS_CSV,
        zip_records,
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
        ],
    )
    print_status(f"Inventário salvo em: {INVENTARIO_CSV}")
    print_status(f"Conteúdo interno dos zips salvo em: {CONTEUDO_ZIPS_CSV}")


if __name__ == "__main__":
    main()
