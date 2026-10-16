from __future__ import annotations

import csv
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DIAGNOSTICOS_DIR = OUTPUTS_DIR / "diagnosticos"
TABELAS_DIR = OUTPUTS_DIR / "tabelas_resumo"

YEAR_PATTERN = re.compile(r"(?<!\d)(2014|2015|2016|2017|2018|2019|2020|2021|2022|2023|2024|2025)(?!\d)")


def ensure_directories() -> None:
    for path in (
        DATA_DIR,
        RAW_DIR,
        INTERIM_DIR,
        PROCESSED_DIR,
        OUTPUTS_DIR,
        DIAGNOSTICOS_DIR,
        TABELAS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def print_status(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    try:
        print(formatted)
    except UnicodeEncodeError:
        safe_text = formatted.encode("cp1252", errors="replace").decode("cp1252")
        print(safe_text)


def to_mb(num_bytes: int | float | None) -> float:
    if not num_bytes:
        return 0.0
    return round(float(num_bytes) / (1024 * 1024), 4)


def relative_to_root(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_accents.lower().strip()


def detect_year(*values: str) -> str:
    for value in values:
        match = YEAR_PATTERN.search(value or "")
        if match:
            return match.group(1)
    return ""


def read_csv_dicts(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        return list(reader)


def write_csv_dicts(csv_path: Path, rows: Iterable[dict], fieldnames: list[str]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "sim", "yes"}


def parse_float(value: str | float | int | None, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int(value: str | int | None, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def json_loads_list(value: str) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []
