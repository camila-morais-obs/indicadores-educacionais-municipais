# Exploração leve de microdados do INEP

Este projeto organiza uma etapa inicial de exploração dos arquivos brutos do INEP para apoiar a construção de uma base leve voltada a um painel público do município de Tijucas/SC. O foco desta fase é diagnosticar a estrutura dos arquivos, entender o conteúdo dos zips sem extração massiva e identificar colunas candidatas antes de qualquer carga grande em memória.

## Estrutura de pastas

```text
explorar_dados_ideb/
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── docs/
├── notebooks/
├── outputs/
│   ├── diagnosticos/
│   └── tabelas_resumo/
├── scripts/
├── README.md
└── .gitignore
```

## Ordem recomendada de execução

Execute os scripts nesta ordem no PowerShell:

```powershell
python scripts\01_listar_arquivos_zip.py
python scripts\02_classificar_arquivos_internos.py
python scripts\03_ler_amostras_arquivos_dados.py
python scripts\04_resumo_colunas_por_ano.py
python scripts\05_filtrar_indicadores_tijucas.py
```

## O que cada script gera

### `01_listar_arquivos_zip.py`

- Verifica a estrutura básica do projeto e cria diretórios faltantes.
- Gera um inventário de `data/raw` sem alterar arquivos originais.
- Lista o conteúdo interno dos `.zip` sem extração completa.

Saídas:

- `outputs/diagnosticos/inventario_data_raw.csv`
- `outputs/diagnosticos/conteudo_zips_inep.csv`

### `02_classificar_arquivos_internos.py`

- Classifica arquivos internos em categorias como `dados`, `dicionario`, `leia_me`, `documento_tecnico`, `planilha`, `imagem`, `pasta` e `outro`.
- Resume quantidade e tamanho por ano, categoria e extensão.

Saídas:

- `outputs/diagnosticos/classificacao_arquivos_internos.csv`
- `outputs/tabelas_resumo/resumo_tipos_arquivos_internos.csv`

### `03_ler_amostras_arquivos_dados.py`

- Tenta ler amostras leves de arquivos classificados como `dados`, sem extrair tudo.
- Detecta encoding e separador.
- Registra cabeçalhos e quantidade de linhas da amostra.

Saída:

- `outputs/diagnosticos/amostras_arquivos_dados.csv`

Observação:

- O script usa `pandas` quando a biblioteca está instalada.
- Se `pandas` não estiver disponível, o script faz uma leitura leve de fallback para manter o diagnóstico operacional.
- Para suporte completo e leitura mais robusta, instale:

```powershell
pip install pandas openpyxl
```

### `04_resumo_colunas_por_ano.py`

- Consolida as colunas encontradas por ano.
- Ajuda a identificar mudanças de layout entre os arquivos.

Saídas:

- `outputs/tabelas_resumo/colunas_por_ano.csv`
- `outputs/tabelas_resumo/frequencia_colunas.csv`

### `05_filtrar_indicadores_tijucas.py`

- Lê os diagnósticos de colunas.
- Procura nomes de colunas candidatas para o painel de Tijucas/SC.

Saída:

- `outputs/tabelas_resumo/colunas_candidatas_painel.csv`

## Regras do projeto

- Não apagar, mover ou alterar arquivos originais em `data/raw`.
- Não extrair todos os zips de forma massiva sem necessidade.
- Priorizar diagnósticos leves antes de dataframes grandes.
- Usar caminhos com `pathlib`.
- Salvar CSVs com `encoding="utf-8-sig"` sempre que possível.

## Versionamento

Os diretórios `data/raw` e `data/interim` não devem ser versionados. Arquivos brutos compactados e artefatos pesados também devem permanecer fora do controle de versão.


## Fontes de dados e obtenção dos microdados

O projeto utiliza dados públicos do Instituto Nacional de Estudos e Pesquisas Educacionais Anísio Teixeira (INEP/MEC), obtidos por meio do portal oficial:

**Fonte:** [INEP — Censo Escolar: Resultados](https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/censo-escolar/resultados)

### Procedimento de coleta

Os arquivos foram baixados manualmente, ano a ano, em formato ZIP, e armazenados no diretório `data/raw/`.

O acervo local contempla:

- **Microdados do Censo Escolar:** 2014 a 2025.
- **Taxas de rendimento escolar por município:** 2014 a 2024.

Os arquivos foram mantidos com nomes padronizados, como `microdados_censo_escolar_2024.zip` e `tx_rend_municipios_2024.zip`, para facilitar sua identificação e processamento pelos scripts Python.

### Armazenamento e reprodução

Os arquivos brutos não são versionados no GitHub devido ao seu volume, de aproximadamente 0,67 GB.

Para reproduzir as análises, é necessário obter os arquivos correspondentes no portal do INEP e armazená-los em `data/raw/`, preservando a nomenclatura esperada pelos scripts.

Os arquivos originais são mantidos sem alterações; os procedimentos de leitura, tratamento e geração de indicadores são executados pelos scripts do projeto.
