from __future__ import annotations

import html
import importlib.util
import re
from collections import Counter, defaultdict
from pathlib import Path

from _project_utils import (
    DIAGNOSTICOS_DIR,
    OUTPUTS_DIR,
    TABELAS_DIR,
    ensure_directories,
    normalize_text,
    parse_int,
    print_status,
    read_csv_dicts,
)

RELATORIOS_DIR = OUTPUTS_DIR / "relatorios"
RELATORIO_MD = RELATORIOS_DIR / "relatorio_insights_painel_educacao.md"
RELATORIO_HTML = RELATORIOS_DIR / "relatorio_insights_painel_educacao.html"
RELATORIO_PDF = RELATORIOS_DIR / "relatorio_insights_painel_educacao.pdf"

EXPECTED_FILES = {
    "inventario_data_raw.csv": DIAGNOSTICOS_DIR / "inventario_data_raw.csv",
    "conteudo_zips_inep.csv": DIAGNOSTICOS_DIR / "conteudo_zips_inep.csv",
    "classificacao_arquivos_internos.csv": DIAGNOSTICOS_DIR / "classificacao_arquivos_internos.csv",
    "amostras_arquivos_dados.csv": DIAGNOSTICOS_DIR / "amostras_arquivos_dados.csv",
    "colunas_por_ano.csv": TABELAS_DIR / "colunas_por_ano.csv",
    "frequencia_colunas.csv": TABELAS_DIR / "frequencia_colunas.csv",
    "colunas_candidatas_painel.csv": TABELAS_DIR / "colunas_candidatas_painel.csv",
    "resumo_tipos_arquivos_internos.csv": TABELAS_DIR / "resumo_tipos_arquivos_internos.csv",
}

THEME_CONFIGS = [
    {
        "titulo": "Rede escolar",
        "perguntas": [
            "Quantas escolas em funcionamento existem no município em cada ano?",
            "Como a rede se distribui entre dependência administrativa, localização urbana/rural e etapas ofertadas?",
            "Quais escolas aparecem de forma estável na série histórica do Censo Escolar?",
        ],
        "patterns": [
            "co_entidade",
            "no_entidade",
            "tp_dependencia",
            "tp_localizacao",
            "tp_situacao_funcionamento",
            "co_municipio",
            "no_municipio",
            "sg_uf",
            "in_inf_",
            "in_fund",
            "in_med",
            "in_eja",
            "in_esp",
            "in_prof",
        ],
        "indicadores": [
            "Escolas em funcionamento",
            "Escolas por dependência administrativa",
            "Escolas urbanas e rurais",
            "Escolas por etapa ofertada",
        ],
        "cuidados": [
            "Padronizar o conceito de escola ativa para evitar contagem indevida de unidades paralisadas ou extintas.",
            "Definir se escolas com múltiplas etapas serão contadas em cada etapa ou em uma categoria principal.",
            "Validar mudanças de código e nome de escola antes de comparar séries longas.",
        ],
    },
    {
        "titulo": "Atendimento escolar",
        "perguntas": [
            "Quantas matrículas existem por etapa de ensino em cada ano?",
            "Como evoluem as matrículas em creche, pré-escola, anos iniciais, anos finais, EJA e educação especial?",
            "Há mudanças relevantes na distribuição do atendimento ofertado no município?",
        ],
        "patterns": [
            "qt_mat_",
            "in_inf_cre",
            "in_inf_pre",
            "in_fund_ai",
            "in_fund_af",
            "in_eja",
            "in_esp",
            "tabela_matricula",
        ],
        "indicadores": [
            "Matrículas totais",
            "Matrículas em creche",
            "Matrículas em pré-escola",
            "Matrículas nos anos iniciais",
            "Matrículas nos anos finais",
            "Matrículas em EJA",
            "Matrículas em educação especial",
        ],
        "cuidados": [
            "Conferir se as variáveis representam contagem consolidada por escola ou registros individualizados, especialmente em 2025.",
            "Evitar somar tabelas consolidadas com tabelas de matrícula detalhada sem uma regra única de agregação.",
            "Registrar claramente se o indicador inclui classes comuns, classes exclusivas ou atendimento complementar.",
        ],
    },
    {
        "titulo": "Docentes e turmas",
        "perguntas": [
            "Quantos docentes e turmas aparecem na rede por ano e por etapa?",
            "Qual é a relação aproximada entre matrículas, turmas e docentes?",
            "Há concentração de oferta em poucas escolas ou etapas específicas?",
        ],
        "patterns": [
            "qt_doc_",
            "qt_tur_",
            "qt_mat_",
            "tabela_docente",
            "tabela_turma",
        ],
        "indicadores": [
            "Docentes totais",
            "Docentes por etapa",
            "Turmas totais",
            "Turmas por etapa",
            "Matrículas por turma",
            "Matrículas por docente",
        ],
        "cuidados": [
            "Tratar razões como medidas aproximadas, porque podem existir diferenças entre contagens consolidadas e tabelas detalhadas.",
            "Evitar comparar diretamente 2025 com anos anteriores sem documentar a adaptação da estrutura multi-tabela.",
            "Checar se o conceito de docente considera vínculos, funções e atuação em múltiplas etapas.",
        ],
    },
    {
        "titulo": "Infraestrutura básica",
        "perguntas": [
            "Qual a cobertura de água, energia, esgoto, banheiro, cozinha e refeitório nas escolas?",
            "As escolas do município apresentam desigualdades básicas de infraestrutura?",
            "Quais dimensões de infraestrutura são mais adequadas para acompanhamento anual?",
        ],
        "patterns": [
            "in_agua_",
            "in_energia_",
            "in_esgoto_",
            "in_banheiro",
            "in_cozinha",
            "in_refeitorio",
        ],
        "indicadores": [
            "Percentual de escolas com água potável",
            "Percentual com energia elétrica da rede pública",
            "Percentual com esgoto da rede pública",
            "Percentual com banheiro",
            "Percentual com cozinha",
            "Percentual com refeitório",
        ],
        "cuidados": [
            "Usar denominador consistente de escolas em funcionamento com informação disponível.",
            "Documentar mudanças de questionário e possíveis alterações na interpretação de presença/ausência.",
            "Separar, quando necessário, indicadores de existência física e de acesso regular ao serviço.",
        ],
    },
    {
        "titulo": "Infraestrutura pedagógica",
        "perguntas": [
            "Qual a disponibilidade de biblioteca, laboratórios, quadra e parque infantil nas escolas?",
            "Como esses recursos se distribuem entre etapas ofertadas e perfis de escola?",
            "Quais equipamentos podem ser acompanhados de forma estável na série histórica?",
        ],
        "patterns": [
            "in_biblioteca",
            "in_sala_leitura",
            "in_laboratorio_ciencias",
            "in_laboratorio_informatica",
            "in_quadra_esportes",
            "in_parque_infantil",
        ],
        "indicadores": [
            "Percentual com biblioteca ou sala de leitura",
            "Percentual com laboratório de informática",
            "Percentual com laboratório de ciências",
            "Percentual com quadra de esportes",
            "Percentual com parque infantil",
        ],
        "cuidados": [
            "Conferir se cada item representa infraestrutura exclusiva da escola ou espaço compartilhado.",
            "Evitar comparar automaticamente indicadores com baixa resposta ou mudança de nomenclatura.",
            "Esclarecer se o foco do painel será presença do recurso ou sua intensidade de uso.",
        ],
    },
    {
        "titulo": "Tecnologia e conectividade",
        "perguntas": [
            "Qual a cobertura de internet e banda larga nas escolas?",
            "Há acesso à internet para alunos e disponibilidade de computadores para uso pedagógico?",
            "Como acompanhar a infraestrutura digital sem confundir oferta potencial com uso efetivo?",
        ],
        "patterns": [
            "in_internet",
            "in_banda_larga",
            "in_internet_alunos",
            "qt_comp_aluno",
            "qt_computador",
            "in_acesso_internet_computador",
            "in_aces_internet_disp_pessoais",
        ],
        "indicadores": [
            "Percentual com internet",
            "Percentual com banda larga",
            "Percentual com internet para alunos",
            "Computadores para alunos",
        ],
        "cuidados": [
            "Diferenciar presença de internet da qualidade do serviço e da disponibilidade para uso pedagógico.",
            "Ao publicar quantidades de equipamentos, preferir agregações por rede e município em vez de detalhamento excessivo.",
            "Registrar quando o indicador for proxy e não medida oficial de conectividade escolar.",
        ],
    },
    {
        "titulo": "Acessibilidade e inclusão",
        "perguntas": [
            "Qual a presença de rampas, banheiros acessíveis, salas acessíveis e outros recursos de acessibilidade?",
            "Como evolui a capacidade declarada da rede para atender estudantes com deficiência?",
            "Há indicadores mínimos que podem ser comparados com adaptação ao longo do tempo?",
        ],
        "patterns": [
            "in_acessibilidade_",
            "in_banheiro_pne",
            "qt_salas_utilizadas_acessiveis",
            "in_dependencias_pne",
            "in_acessibilidade_inexistente",
            "qt_mat_esp",
        ],
        "indicadores": [
            "Percentual com rampas",
            "Percentual com banheiro acessível",
            "Percentual com salas acessíveis",
            "Percentual sem recurso de acessibilidade",
        ],
        "cuidados": [
            "Não tratar a existência de infraestrutura como evidência de acessibilidade plena ou atendimento adequado.",
            "Explicitar se o indicador mede presença de recurso físico, capacidade declarada ou atendimento educacional especializado.",
            "Em séries longas, revisar a consistência de nomenclaturas e fusões de categorias.",
        ],
    },
    {
        "titulo": "Gestão e participação",
        "perguntas": [
            "Que estruturas de gestão e participação escolar aparecem nos microdados?",
            "Há informação útil sobre conselho escolar, associações e proposta pedagógica?",
            "Quais elementos podem ser publicados sem gerar inferências indevidas sobre qualidade?",
        ],
        "patterns": [
            "in_orgao_",
            "tp_proposta_pedagogica",
            "qt_funcionarios",
            "qt_prof_gestao",
            "in_sala_diretoria",
            "tabela_gestor_escolar",
        ],
        "indicadores": [
            "Presença de conselho escolar",
            "Presença de associação de pais ou equivalente",
            "Escolas com estrutura mínima de gestão declarada",
        ],
        "cuidados": [
            "Evitar usar esses dados como ranking de governança escolar.",
            "Checar se a resposta é autodeclarada pela escola e se houve mudança de questionário entre anos.",
            "Publicar indicadores agregados e contextuais, não avaliações simplificadas de gestão.",
        ],
    },
    {
        "titulo": "Mapa das escolas",
        "perguntas": [
            "Onde estão as escolas da rede e quais etapas ofertam?",
            "Quais bairros concentram equipamentos educacionais?",
            "Quais escolas podem entrar em um mapa público como equipamentos, não como ranking?",
        ],
        "patterns": [
            "co_entidade",
            "no_entidade",
            "no_bairro",
            "ds_endereco",
            "nu_endereco",
            "co_cep",
            "co_municipio",
            "no_municipio",
            "sg_uf",
            "tp_localizacao",
            "in_inf_",
            "in_fund",
            "in_med",
            "in_eja",
            "in_esp",
        ],
        "indicadores": [
            "Escolas georreferenciadas",
            "Escolas por bairro",
            "Etapas ofertadas por escola",
        ],
        "cuidados": [
            "Os microdados amostrados não evidenciam coordenadas geográficas; georreferenciamento pode exigir base complementar.",
            "O mapa deve ser tratado como inventário de equipamentos públicos e privados, não como mapa de desempenho.",
            "Revisar padronização de endereço e bairro antes de publicar recortes intraurbanos.",
        ],
    },
]

INDICATOR_ROWS = [
    ("Rede escolar", "Escolas em funcionamento", ["co_entidade", "tp_situacao_funcionamento", "co_municipio"], "município/ano", "anual", "comparável com adaptação", "Exige regra explícita para considerar escolas ativas e adaptação da estrutura 2025."),
    ("Rede escolar", "Escolas por dependência administrativa", ["co_entidade", "tp_dependencia", "co_municipio"], "município/ano e rede/ano", "anual", "comparável com adaptação", "A categoria de dependência precisa ser harmonizada ao longo da série."),
    ("Rede escolar", "Escolas urbanas e rurais", ["co_entidade", "tp_localizacao", "co_municipio"], "município/ano", "anual", "comparável com adaptação", "Comparação depende da consistência da variável de localização."),
    ("Rede escolar", "Escolas por etapa ofertada", ["co_entidade", "in_inf_", "in_fund", "in_med", "in_eja", "in_esp"], "município/ano e escola/ano", "anual", "comparável com adaptação", "Escolas podem ofertar múltiplas etapas no mesmo ano."),
    ("Atendimento escolar", "Matrículas totais", ["qt_mat_bas", "co_municipio"], "município/ano", "anual", "comparável com adaptação", "Conferir se 2025 exige agregação da tabela de matrícula antes da comparação."),
    ("Atendimento escolar", "Matrículas em creche", ["qt_mat_inf_cre"], "município/ano", "anual", "comparável com adaptação", "Validar a equivalência do conceito ao longo da série."),
    ("Atendimento escolar", "Matrículas em pré-escola", ["qt_mat_inf_pre"], "município/ano", "anual", "comparável com adaptação", "Checar se a variável segue a mesma lógica em 2025."),
    ("Atendimento escolar", "Matrículas nos anos iniciais", ["qt_mat_fund_ai"], "município/ano", "anual", "comparável com adaptação", "Pode ser calculado por agregação consolidada ou por tabela detalhada."),
    ("Atendimento escolar", "Matrículas nos anos finais", ["qt_mat_fund_af"], "município/ano", "anual", "comparável com adaptação", "Documentar a fonte usada em cada ano."),
    ("Atendimento escolar", "Matrículas em EJA", ["qt_mat_eja"], "município/ano", "anual", "comparável com adaptação", "Esclarecer se inclui EJA fundamental e média de forma agregada."),
    ("Atendimento escolar", "Matrículas em educação especial", ["qt_mat_esp"], "município/ano", "anual", "comparável com adaptação", "Explicar se o foco é matrícula total ou atendimento complementar."),
    ("Docentes e turmas", "Docentes totais", ["qt_doc_bas"], "município/ano", "anual", "comparável com adaptação", "Pode exigir padronização entre tabela consolidada e tabela de docentes de 2025."),
    ("Docentes e turmas", "Docentes por etapa", ["qt_doc_inf", "qt_doc_fund", "qt_doc_med", "qt_doc_eja", "qt_doc_esp"], "município/ano", "anual", "comparável com adaptação", "Definir regra para docentes que atuam em múltiplas etapas."),
    ("Docentes e turmas", "Turmas totais", ["qt_tur_bas"], "município/ano", "anual", "comparável com adaptação", "Comparar somente após validar equivalência conceitual com 2025."),
    ("Docentes e turmas", "Turmas por etapa", ["qt_tur_inf", "qt_tur_fund", "qt_tur_med", "qt_tur_eja", "qt_tur_esp"], "município/ano", "anual", "comparável com adaptação", "Etapas devem ser agregadas com o mesmo critério em toda a série."),
    ("Docentes e turmas", "Matrículas por turma", ["qt_mat_bas", "qt_tur_bas"], "município/ano", "anual", "comparável com adaptação", "Tratar como indicador calculado localmente, não como indicador oficial do INEP."),
    ("Docentes e turmas", "Matrículas por docente", ["qt_mat_bas", "qt_doc_bas"], "município/ano", "anual", "comparável com adaptação", "A razão é útil como proxy, mas não substitui indicadores oficiais."),
    ("Infraestrutura básica", "Percentual de escolas com água potável", ["in_agua_potavel"], "município/ano", "anual", "comparável com adaptação", "Usar denominador de escolas com informação válida."),
    ("Infraestrutura básica", "Percentual com energia elétrica da rede pública", ["in_energia_rede_publica"], "município/ano", "anual", "comparável com adaptação", "Registrar se a escola tem outras fontes de energia além da rede."),
    ("Infraestrutura básica", "Percentual com esgoto da rede pública", ["in_esgoto_rede_publica"], "município/ano", "anual", "comparável com adaptação", "Evitar misturar rede pública com outras formas de esgotamento."),
    ("Infraestrutura básica", "Percentual com banheiro", ["in_banheiro"], "município/ano", "anual", "comparável com adaptação", "Esclarecer se o indicador é qualquer banheiro ou banheiro em uso."),
    ("Infraestrutura básica", "Percentual com cozinha", ["in_cozinha"], "município/ano", "anual", "comparável com adaptação", "Pode apoiar leitura sobre alimentação escolar, sem substituí-la."),
    ("Infraestrutura básica", "Percentual com refeitório", ["in_refeitorio"], "município/ano", "anual", "comparável com adaptação", "A existência do espaço não informa qualidade do serviço."),
    ("Infraestrutura pedagógica", "Percentual com biblioteca ou sala de leitura", ["in_biblioteca", "in_sala_leitura", "in_biblioteca_sala_leitura"], "município/ano", "anual", "comparável com adaptação", "Definir se as três variáveis serão tratadas como equivalentes ou complementares."),
    ("Infraestrutura pedagógica", "Percentual com laboratório de informática", ["in_laboratorio_informatica"], "município/ano", "anual", "comparável com adaptação", "Acompanhar junto com conectividade, se possível."),
    ("Infraestrutura pedagógica", "Percentual com laboratório de ciências", ["in_laboratorio_ciencias"], "município/ano", "anual", "comparável com adaptação", "Pode haver baixa frequência em escolas pequenas ou de anos iniciais."),
    ("Infraestrutura pedagógica", "Percentual com quadra de esportes", ["in_quadra_esportes"], "município/ano", "anual", "comparável com adaptação", "Esclarecer se quadras cobertas e descobertas serão agregadas."),
    ("Infraestrutura pedagógica", "Percentual com parque infantil", ["in_parque_infantil"], "município/ano", "anual", "comparável com adaptação", "Indicador é mais relevante quando combinado com oferta de educação infantil."),
    ("Tecnologia e conectividade", "Percentual com internet", ["in_internet"], "município/ano", "anual", "comparável com adaptação", "Não informa estabilidade, velocidade ou qualidade do acesso."),
    ("Tecnologia e conectividade", "Percentual com banda larga", ["in_banda_larga"], "município/ano", "anual", "comparável com adaptação", "Registrar mudanças de definição técnica caso existam nos dicionários."),
    ("Tecnologia e conectividade", "Percentual com internet para alunos", ["in_internet_alunos"], "município/ano", "anual", "comparável com adaptação", "Importante diferenciar acesso administrativo e pedagógico."),
    ("Tecnologia e conectividade", "Computadores para alunos", ["qt_comp_aluno", "qt_desktop_aluno", "qt_comp_portatil_aluno", "qt_tablet_aluno"], "município/ano", "anual", "comparável com adaptação", "Convém publicar como estoque agregado e, se útil, como taxa por matrícula."),
    ("Acessibilidade e inclusão", "Percentual com rampas", ["in_acessibilidade_rampas"], "município/ano", "anual", "comparável com adaptação", "Não equivale a acessibilidade integral da escola."),
    ("Acessibilidade e inclusão", "Percentual com banheiro acessível", ["in_banheiro_pne"], "município/ano", "anual", "comparável com adaptação", "Revisar a nomenclatura à luz dos dicionários de cada ano."),
    ("Acessibilidade e inclusão", "Percentual com salas acessíveis", ["qt_salas_utilizadas_acessiveis"], "município/ano", "anual", "comparável com adaptação", "Pode exigir transformação em indicador binário por escola antes da agregação."),
    ("Acessibilidade e inclusão", "Percentual sem recurso de acessibilidade", ["in_acessibilidade_inexistente"], "município/ano", "anual", "comparável com adaptação", "Publicar com cautela para não induzir leitura simplista sobre inclusão."),
    ("Mapa das escolas", "Escolas georreferenciadas", ["co_entidade", "no_entidade", "ds_endereco", "no_bairro"], "escola/ano e mapa", "anual", "não disponível", "Os diagnósticos amostrados não evidenciam latitude e longitude; geocodificação exigirá base complementar."),
    ("Mapa das escolas", "Escolas por bairro", ["co_entidade", "no_entidade", "no_bairro"], "bairro/ano", "anual", "comparável com adaptação", "Padronizar nomes de bairro antes de mapear ou comparar."),
    ("Mapa das escolas", "Etapas ofertadas por escola", ["co_entidade", "no_entidade", "in_inf_", "in_fund", "in_med", "in_eja", "in_esp"], "escola/ano", "anual", "comparável com adaptação", "A visualização deve enfatizar oferta de serviço, não desempenho."),
]


def ensure_report_directory() -> None:
    ensure_directories()
    RELATORIOS_DIR.mkdir(parents=True, exist_ok=True)


def load_csv_safe(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        return [], "não encontrado"
    try:
        rows = read_csv_dicts(path)
    except Exception as exc:  # pragma: no cover - tratamento operacional
        return [], f"erro ao ler: {exc}"
    return rows, f"encontrado ({len(rows)} linhas)"


def collect_datasets() -> tuple[dict[str, list[dict[str, str]]], dict[str, str]]:
    datasets: dict[str, list[dict[str, str]]] = {}
    status: dict[str, str] = {}
    for file_name, path in EXPECTED_FILES.items():
        rows, message = load_csv_safe(path)
        datasets[file_name] = rows
        status[file_name] = message
    return datasets, status


def unique_sorted(values: list[str]) -> list[str]:
    clean_values = [value for value in values if value]
    return sorted(set(clean_values), key=lambda item: (len(item), item))


def summarize_inventory(rows: list[dict[str, str]]) -> dict[str, object]:
    extension_counts = Counter((row.get("extensao") or "[sem_extensao]").lower() for row in rows)
    return {
        "total_arquivos": len(rows),
        "extensoes": dict(sorted(extension_counts.items())),
    }


def summarize_zip_content(rows: list[dict[str, str]]) -> dict[str, object]:
    years = unique_sorted([row.get("ano_detectado", "") for row in rows])
    zips = sorted({row.get("arquivo_zip", "") for row in rows if row.get("arquivo_zip")})
    return {
        "total_zips": len(zips),
        "anos_detectados": years,
    }


def summarize_internal_types(rows: list[dict[str, str]]) -> dict[str, int]:
    counter = Counter(row.get("categoria", "sem_categoria") for row in rows)
    return dict(sorted(counter.items()))


def summarize_sampled_files(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("status") != "ok":
            continue
        grouped[row.get("ano_detectado", "sem_ano")].append(row)
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def summarize_columns_per_year(rows: list[dict[str, str]]) -> dict[str, int]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        year = row.get("ano_detectado", "")
        column = row.get("coluna", "")
        if year and column:
            grouped[year].add(column)
    return {year: len(columns) for year, columns in sorted(grouped.items())}


def build_column_catalog(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    catalog = []
    for row in rows:
        column = row.get("coluna", "")
        if column:
            catalog.append(row)
    return catalog


def column_matches(column_name: str, pattern: str) -> bool:
    normalized_column = normalize_text(column_name)
    normalized_pattern = normalize_text(pattern)
    if normalized_pattern.endswith("_"):
        return normalized_column.startswith(normalized_pattern)
    return normalized_column == normalized_pattern or normalized_column.startswith(f"{normalized_pattern}_")


def detect_presence_by_prefix(column_rows: list[dict[str, str]], patterns: list[str], limit: int = 20) -> list[str]:
    matches: list[tuple[int, str]] = []
    seen: set[str] = set()
    for row in column_rows:
        column = row.get("coluna", "")
        if not column:
            continue
        if any(column_matches(column, pattern) for pattern in patterns):
            if column not in seen:
                seen.add(column)
                matches.append((parse_int(row.get("quantidade_anos")), column))
    matches.sort(key=lambda item: (-item[0], item[1]))
    selected = [column for _, column in matches[:limit]]
    if len(matches) > limit:
        selected.append("...")
    return selected


def find_columns_for_patterns(column_rows: list[dict[str, str]], patterns: list[str]) -> list[str]:
    matched_columns = detect_presence_by_prefix(column_rows, patterns, limit=8)
    return [column for column in matched_columns if column != "..."]


def format_list_or_not_found(items: list[str]) -> str:
    if not items:
        return "não encontrado"
    return ", ".join(items)


def build_theme_blocks(column_rows: list[dict[str, str]]) -> list[str]:
    blocks: list[str] = []
    for config in THEME_CONFIGS:
        matches = detect_presence_by_prefix(column_rows, config["patterns"], limit=18)
        blocks.append(f"### {config['titulo']}")
        blocks.append("")
        blocks.append("Perguntas cidadãs que o painel pode responder:")
        for question in config["perguntas"]:
            blocks.append(f"- {question}")
        blocks.append("")
        blocks.append(f"Variáveis candidatas encontradas: {format_list_or_not_found(matches)}")
        blocks.append("")
        blocks.append("Indicadores recomendados:")
        for indicator in config["indicadores"]:
            blocks.append(f"- {indicator}")
        blocks.append("")
        blocks.append("Cuidados metodológicos:")
        for caution in config["cuidados"]:
            blocks.append(f"- {caution}")
        blocks.append("")
    return blocks


def build_indicator_table(column_rows: list[dict[str, str]]) -> list[str]:
    lines = [
        "| tema | indicador | variáveis necessárias | nível recomendado de agregação | periodicidade | comparabilidade 2014-2025 | observações metodológicas |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for theme, indicator, patterns, level, periodicity, comparability, notes in INDICATOR_ROWS:
        matched_columns = find_columns_for_patterns(column_rows, patterns)
        variables_text = ", ".join(matched_columns) if matched_columns else "a confirmar no dicionário"
        lines.append(
            f"| {theme} | {indicator} | {variables_text} | {level} | {periodicity} | {comparability} | {notes} |"
        )
    return lines


def build_diagnostics_status_table(status: dict[str, str]) -> list[str]:
    lines = [
        "| arquivo de diagnóstico | situação |",
        "| --- | --- |",
    ]
    for file_name in EXPECTED_FILES:
        lines.append(f"| {file_name} | {status.get(file_name, 'não encontrado')} |")
    return lines


def build_bases_section(datasets: dict[str, list[dict[str, str]]], status: dict[str, str]) -> list[str]:
    inventory_summary = summarize_inventory(datasets["inventario_data_raw.csv"])
    zip_summary = summarize_zip_content(datasets["conteudo_zips_inep.csv"])
    category_summary = summarize_internal_types(datasets["classificacao_arquivos_internos.csv"])
    sampled_by_year = summarize_sampled_files(datasets["amostras_arquivos_dados.csv"])

    lines = ["## 2. Bases e arquivos analisados", ""]
    lines.append("Situação dos diagnósticos lidos:")
    lines.extend(build_diagnostics_status_table(status))
    lines.append("")
    lines.append(f"- Quantidade de arquivos brutos identificados em `data/raw`: {inventory_summary['total_arquivos']}.")
    lines.append(f"- Quantidade de zips identificados: {zip_summary['total_zips']}.")
    years_text = ", ".join(zip_summary["anos_detectados"]) if zip_summary["anos_detectados"] else "não encontrado"
    lines.append(f"- Anos detectados nos diagnósticos: {years_text}.")
    if inventory_summary["extensoes"]:
        ext_text = ", ".join(f"{ext}: {count}" for ext, count in inventory_summary["extensoes"].items())
        lines.append(f"- Extensões encontradas nos arquivos brutos: {ext_text}.")
    else:
        lines.append("- Extensões encontradas nos arquivos brutos: não encontrado.")

    if category_summary:
        category_text = ", ".join(f"{category}: {count}" for category, count in category_summary.items())
        lines.append(f"- Tipos de arquivos internos identificados: {category_text}.")
    else:
        lines.append("- Tipos de arquivos internos identificados: não encontrado.")
    lines.append("")
    lines.append("Principais arquivos de dados encontrados:")
    if sampled_by_year:
        for year, rows in sampled_by_year.items():
            descriptions = [
                f"{Path(row.get('arquivo_interno', '')).name} ({row.get('n_colunas', '?')} colunas)"
                for row in rows
            ]
            lines.append(f"- {year}: {', '.join(descriptions)}")
    else:
        lines.append("- não encontrado")
    lines.append("")
    return lines


def build_structure_section(datasets: dict[str, list[dict[str, str]]]) -> list[str]:
    column_counts = summarize_columns_per_year(datasets["colunas_por_ano.csv"])
    sampled_by_year = summarize_sampled_files(datasets["amostras_arquivos_dados.csv"])

    lines = ["## 3. Estrutura dos microdados por ano", ""]
    lines.append("A leitura das amostras e o resumo de colunas por ano mostram uma mudança gradual de layout ao longo da série.")
    lines.append("")
    lines.append("| ano | arquivos de dados amostrados | número de colunas distintas no ano | maior número de colunas em um arquivo | observação |")
    lines.append("| --- | --- | --- | --- | --- |")
    for year in sorted(set(column_counts) | set(sampled_by_year)):
        rows = sampled_by_year.get(year, [])
        file_count = len(rows)
        max_columns = max((parse_int(row.get("n_colunas")) for row in rows), default=0)
        if year == "2025":
            note = "estrutura separada em múltiplas tabelas temáticas"
        elif year in {"2023", "2024"}:
            note = "arquivo principal com suplemento adicional"
        elif year == "2022":
            note = "arquivo principal consolidado com ampliação de colunas"
        else:
            note = "arquivo principal consolidado"
        lines.append(
            f"| {year} | {file_count} | {column_counts.get(year, 0)} | {max_columns} | {note} |"
        )
    lines.append("")
    if column_counts:
        lines.append("Leitura técnica da estrutura:")
        if all(column_counts.get(year) == 370 for year in [str(year) for year in range(2014, 2022)] if year in column_counts):
            lines.append("- Entre 2014 e 2021, os diagnósticos apontam um arquivo principal consolidado com 370 colunas.")
        if "2022" in column_counts:
            lines.append(f"- Em 2022, o número de colunas distintas sobe para {column_counts['2022']}, indicando expansão do layout.")
        if "2023" in column_counts:
            lines.append(f"- Em 2023, o conjunto amostrado passa para {column_counts['2023']} colunas distintas e inclui suplemento de cursos técnicos.")
        if "2024" in column_counts:
            lines.append(f"- Em 2024, o conjunto amostrado chega a {column_counts['2024']} colunas distintas, mantendo suplemento específico.")
        if "2025" in column_counts:
            lines.append(
                "- Em 2025, a mudança mais importante é estrutural: os dados aparecem separados em tabelas temáticas como Escola, Matrícula, Turma, Docente, Gestor Escolar e Curso Técnico."
            )
    else:
        lines.append("Não foi possível resumir a estrutura por ano porque `colunas_por_ano.csv` não foi encontrado.")
    lines.append("")
    return lines


def build_other_bases_section() -> list[str]:
    return [
        "## 6. Indicadores que exigem outras bases",
        "",
        "Os diagnósticos desta etapa apontam que os microdados do Censo Escolar são adequados para descrever oferta, infraestrutura, matrículas agregadas e características da rede. Eles não devem ser tratados como fonte direta dos seguintes indicadores oficiais, salvo verificação posterior em outros arquivos específicos do INEP:",
        "",
        "- IDEB",
        "- Saeb",
        "- aprovação",
        "- reprovação",
        "- abandono",
        "- distorção idade-série",
        "- adequação da formação docente",
        "- indicador oficial de média de alunos por turma",
        "",
        "Esses indicadores devem ser buscados nas bases de Resultados do IDEB, Saeb e Indicadores Educacionais do INEP. Quando o painel usar proxies derivados do Censo Escolar, isso deve ser explicitado para não confundir indicador calculado localmente com indicador oficial publicado pelo INEP.",
        "",
    ]


def build_structure_2025_section() -> list[str]:
    return [
        "## 7. Cuidados com a mudança de estrutura em 2025",
        "",
        "- Entre 2014 e 2024, os diagnósticos sugerem predominância de um arquivo principal consolidado por ano, com suplementos adicionais em 2023 e 2024.",
        "- Em 2025, os arquivos amostrados aparecem separados em tabelas como Escola, Matrícula, Turma, Docente, Gestor Escolar e Curso Técnico.",
        "- Para preservar comparabilidade, recomenda-se calcular indicadores por tema e agregá-los primeiro para o nível município/ano antes de comparar com a série histórica.",
        "- Cada indicador do painel deve receber uma flag de comparabilidade:",
        "- `comparável`: mesma lógica de cálculo, mesma unidade analítica e mesmas variáveis ao longo da série.",
        "- `comparável com adaptação`: exige harmonização entre arquivo consolidado e estrutura multi-tabela de 2025.",
        "- `não comparável`: mudança conceitual ou estrutural impede comparação direta sem perda analítica.",
        "- `não disponível`: os diagnósticos não mostram variáveis suficientes para construir o indicador com segurança.",
        "",
        "Na prática, a maior parte dos indicadores do Censo Escolar desta etapa tende a ficar em `comparável com adaptação`, porque a estrutura de 2025 requer consolidação prévia por escola, tema e ano.",
        "",
    ]


def build_publication_section() -> list[str]:
    return [
        "## 8. Cuidados de publicação",
        "",
        "- Evitar ranking de escolas no painel público.",
        "- Evitar expor dados sensíveis por unidade escolar quando o recorte puder permitir inferências indevidas.",
        "- Usar o mapa das escolas como mapa de equipamentos públicos e privados de educação, não como mapa de desempenho.",
        "- Não publicar dados individualizados de estudantes, docentes ou gestores.",
        "- Explicar claramente limitações de indicadores aproximados, especialmente razões calculadas localmente e proxies.",
        "- Documentar fontes, ano de referência, regra de agregação e limitações metodológicas em cada indicador publicado.",
        "",
    ]


def build_architecture_section() -> list[str]:
    return [
        "## 9. Sugestão de arquitetura para o painel",
        "",
        "- Visão geral da educação",
        "- Rede escolar",
        "- Atendimento escolar",
        "- Infraestrutura das escolas",
        "- Tecnologia e acessibilidade",
        "- Mapa da rede",
        "- Qualidade e fluxo escolar, usando bases complementares de IDEB e Indicadores Educacionais",
        "",
        "Essa arquitetura ajuda a separar com clareza o que vem do Censo Escolar e o que exige bases complementares do INEP.",
        "",
    ]


def build_next_steps_section() -> list[str]:
    return [
        "## 10. Próximos passos",
        "",
        "- Validar dicionários e anexos metodológicos por ano.",
        "- Extrair uma base filtrada para Tijucas/SC com regras explícitas de município, escola e etapa.",
        "- Gerar indicadores agregados por município/ano antes de qualquer visualização pública.",
        "- Baixar as bases de IDEB.",
        "- Baixar as bases de Indicadores Educacionais do INEP.",
        "- Definir comparações com Santa Catarina, Brasil e municípios semelhantes.",
        "- Revisar riscos de publicação com a equipe da prefeitura antes da divulgação pública.",
        "",
    ]


def build_report_markdown(datasets: dict[str, list[dict[str, str]]], status: dict[str, str]) -> str:
    column_rows = build_column_catalog(datasets["frequencia_colunas.csv"])

    lines = [
        "# Relatório de exploração dos microdados do INEP para o painel de educação de Tijucas/SC",
        "",
        "## 1. Objetivo",
        "",
        "Este relatório organiza a leitura inicial dos microdados do Censo Escolar para apoiar a definição de indicadores do painel cidadão de educação de Tijucas/SC. O foco está em entender a estrutura dos arquivos, identificar variáveis candidatas, apontar temas viáveis para o painel e sinalizar limites metodológicos antes da construção da base final.",
        "",
    ]

    lines.extend(build_bases_section(datasets, status))
    lines.extend(build_structure_section(datasets))
    lines.append("## 4. Temas possíveis para o painel cidadão")
    lines.append("")
    lines.extend(build_theme_blocks(column_rows))
    lines.append("## 5. Indicadores recomendados")
    lines.append("")
    lines.extend(build_indicator_table(column_rows))
    lines.append("")
    lines.extend(build_other_bases_section())
    lines.extend(build_structure_2025_section())
    lines.extend(build_publication_section())
    lines.extend(build_architecture_section())
    lines.extend(build_next_steps_section())

    return "\n".join(lines).strip() + "\n"


def format_inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def parse_markdown_table(table_lines: list[str]) -> str:
    rows = []
    for line in table_lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        parts = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(parts)
    if len(rows) < 2:
        return ""
    header = rows[0]
    body = rows[2:] if len(rows) > 2 else []
    header_html = "".join(f"<th>{format_inline_markdown(cell)}</th>" for cell in header)
    body_html = []
    for row in body:
        cells = "".join(f"<td>{format_inline_markdown(cell)}</td>" for cell in row)
        body_html.append(f"<tr>{cells}</tr>")
    return "\n".join(
        [
            '<table class="report-table">',
            f"<thead><tr>{header_html}</tr></thead>",
            "<tbody>",
            *body_html,
            "</tbody>",
            "</table>",
        ]
    )


def markdown_to_html(markdown_text: str) -> str:
    html_lines = [
        "<!DOCTYPE html>",
        '<html lang="pt-BR">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Relatório de insights para o painel de educação</title>",
        "<style>",
        "body { font-family: 'Segoe UI', Arial, sans-serif; margin: 40px auto; max-width: 1100px; line-height: 1.6; color: #1f2933; padding: 0 24px; }",
        "h1, h2, h3 { color: #102a43; }",
        "table { border-collapse: collapse; width: 100%; margin: 16px 0 24px; font-size: 14px; }",
        "th, td { border: 1px solid #cbd2d9; padding: 8px 10px; text-align: left; vertical-align: top; }",
        "th { background: #f0f4f8; }",
        "code { background: #f0f4f8; padding: 1px 4px; border-radius: 4px; }",
        "ul { margin-top: 8px; margin-bottom: 16px; }",
        "p { margin: 10px 0; }",
        "</style>",
        "</head>",
        "<body>",
    ]

    lines = markdown_text.splitlines()
    paragraph_buffer: list[str] = []
    list_buffer: list[str] = []
    table_buffer: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            html_lines.append(f"<p>{format_inline_markdown(' '.join(paragraph_buffer))}</p>")
            paragraph_buffer.clear()

    def flush_list() -> None:
        if list_buffer:
            html_lines.append("<ul>")
            for item in list_buffer:
                html_lines.append(f"<li>{format_inline_markdown(item)}</li>")
            html_lines.append("</ul>")
            list_buffer.clear()

    def flush_table() -> None:
        if table_buffer:
            html_lines.append(parse_markdown_table(table_buffer))
            table_buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            flush_table()
            continue

        if stripped.startswith("|"):
            flush_paragraph()
            flush_list()
            table_buffer.append(stripped)
            continue

        if table_buffer:
            flush_table()

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            flush_list()
            level = len(heading_match.group(1))
            content = format_inline_markdown(heading_match.group(2))
            html_lines.append(f"<h{level}>{content}</h{level}>")
            continue

        if stripped.startswith("- "):
            flush_paragraph()
            list_buffer.append(stripped[2:].strip())
            continue

        flush_list()
        paragraph_buffer.append(stripped)

    flush_paragraph()
    flush_list()
    flush_table()

    html_lines.extend(["</body>", "</html>"])
    return "\n".join(line for line in html_lines if line)


def try_generate_pdf(html_path: Path, pdf_path: Path) -> tuple[bool, str]:
    if importlib.util.find_spec("weasyprint") is not None:
        from weasyprint import HTML

        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return True, "PDF gerado com weasyprint."

    if importlib.util.find_spec("reportlab") is not None:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        markdown_text = RELATORIO_MD.read_text(encoding="utf-8")
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
        story = []
        for line in markdown_text.splitlines():
            stripped = line.strip()
            if not stripped:
                story.append(Spacer(1, 8))
                continue
            if stripped.startswith("# "):
                story.append(Paragraph(html.escape(stripped[2:]), styles["Title"]))
            elif stripped.startswith("## "):
                story.append(Paragraph(html.escape(stripped[3:]), styles["Heading2"]))
            elif stripped.startswith("### "):
                story.append(Paragraph(html.escape(stripped[4:]), styles["Heading3"]))
            else:
                content = stripped[2:] if stripped.startswith("- ") else stripped
                story.append(Paragraph(html.escape(content), styles["BodyText"]))
            story.append(Spacer(1, 6))
        doc.build(story)
        return True, "PDF gerado com reportlab."

    return (
        False,
        "Nenhuma biblioteca de conversão para PDF foi encontrada. Para converter depois, você pode abrir o HTML no navegador e usar 'Imprimir > Salvar como PDF' ou instalar `weasyprint`/`reportlab`.",
    )


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    ensure_report_directory()
    datasets, status = collect_datasets()

    print_status("Gerando relatório analítico em Markdown a partir dos diagnósticos disponíveis.")
    markdown_text = build_report_markdown(datasets, status)
    write_text_file(RELATORIO_MD, markdown_text)

    print_status("Convertendo o relatório para HTML simples.")
    html_text = markdown_to_html(markdown_text)
    write_text_file(RELATORIO_HTML, html_text)

    pdf_generated, pdf_message = try_generate_pdf(RELATORIO_HTML, RELATORIO_PDF)

    print_status(f"Arquivo gerado: {RELATORIO_MD}")
    print_status(f"Arquivo gerado: {RELATORIO_HTML}")
    if pdf_generated:
        print_status(f"Arquivo gerado: {RELATORIO_PDF}")
    print_status(pdf_message)


if __name__ == "__main__":
    main()
