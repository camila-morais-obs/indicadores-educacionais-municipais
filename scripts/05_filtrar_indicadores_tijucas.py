from __future__ import annotations

from _project_utils import (
    TABELAS_DIR,
    ensure_directories,
    normalize_text,
    parse_int,
    print_status,
    read_csv_dicts,
    write_csv_dicts,
)

FREQUENCIA_COLUNAS_CSV = TABELAS_DIR / "frequencia_colunas.csv"
COLUNAS_CANDIDATAS_CSV = TABELAS_DIR / "colunas_candidatas_painel.csv"

TERM_GROUPS = {
    "municipio": ("municipio", "co_municipio", "cod_municipio", "id_municipio", "no_municipio"),
    "uf": ("uf", "sg_uf"),
    "escola": ("escola", "co_entidade", "no_entidade"),
    "ideb_indicador": ("ideb",),
    "fluxo_rendimento": ("rendimento", "aprov", "repro", "abandono"),
    "matricula": ("matricula",),
    "etapa_ensino": ("etapa", "ensino"),
    "rede_dependencia": ("rede", "dependencia"),
}


def infer_group(matches: list[str]) -> str:
    for group_name, keywords in TERM_GROUPS.items():
        if any(keyword in matches for keyword in keywords):
            return group_name
    return "outro"


def main() -> None:
    ensure_directories()
    rows = read_csv_dicts(FREQUENCIA_COLUNAS_CSV)

    if not rows:
        write_csv_dicts(
            COLUNAS_CANDIDATAS_CSV,
            [],
            ["coluna", "termos_encontrados", "categoria_sugerida", "quantidade_anos", "anos_detectados", "quantidade_arquivos"],
        )
        print_status(
            "Arquivo de frequência de colunas não encontrado ou vazio. Rode scripts\\04_resumo_colunas_por_ano.py antes."
        )
        return

    candidate_rows: list[dict[str, str]] = []
    for row in rows:
        normalized_column = normalize_text(row.get("coluna", ""))
        matched_terms: list[str] = []
        for keywords in TERM_GROUPS.values():
            for keyword in keywords:
                if keyword in normalized_column and keyword not in matched_terms:
                    matched_terms.append(keyword)

        if not matched_terms:
            continue

        candidate_rows.append(
            {
                "coluna": row.get("coluna", ""),
                "termos_encontrados": " | ".join(matched_terms),
                "categoria_sugerida": infer_group(matched_terms),
                "quantidade_anos": row.get("quantidade_anos", "0"),
                "anos_detectados": row.get("anos_detectados", ""),
                "quantidade_arquivos": row.get("quantidade_arquivos", "0"),
            }
        )

    candidate_rows.sort(
        key=lambda row: (
            -parse_int(row["quantidade_anos"]),
            -parse_int(row["quantidade_arquivos"]),
            row["categoria_sugerida"],
            row["coluna"],
        )
    )

    write_csv_dicts(
        COLUNAS_CANDIDATAS_CSV,
        candidate_rows,
        ["coluna", "termos_encontrados", "categoria_sugerida", "quantidade_anos", "anos_detectados", "quantidade_arquivos"],
    )
    print_status(f"Colunas candidatas para o painel salvas em: {COLUNAS_CANDIDATAS_CSV}")
    print_status(f"Quantidade de colunas candidatas encontradas: {len(candidate_rows)}")


if __name__ == "__main__":
    main()
