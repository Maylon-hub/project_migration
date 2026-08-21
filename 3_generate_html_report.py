"""
Gerador de Relatório HTML Interativo de Migração IES - Plone 6
==============================================================

Lê o arquivo 'migracao_relatorio.csv' e gera um painel HTML (relatorio_migracao.html)
moderno, responsivo, interativo e visualmente impactante.
"""

import json
from pathlib import Path
import pandas as pd

CSV_PATH = Path("migracao_relatorio_atualizado.csv")
HTML_OUTPUT_PATH = Path("relatorio_migracao_atualizado.html")


def generate_html_report(csv_path: Path = None, html_path: Path = None):
    input_csv = Path(csv_path) if csv_path else CSV_PATH
    output_html = Path(html_path) if html_path else HTML_OUTPUT_PATH

    if not input_csv.exists():
        fallback_csv = Path("migracao_relatorio.csv")
        if fallback_csv.exists() and not csv_path:
            input_csv = fallback_csv
            print(f"[AVISO] Arquivo '{CSV_PATH}' nao encontrado. Usando fallback: '{input_csv}'")
        else:
            print(f"[ERRO] Arquivo {input_csv} nao encontrado!")
            return

    print(f"[+] Lendo {input_csv}...")
    df = pd.read_csv(input_csv)

    total_records = len(df)
    total_ies = df["sigla"].nunique()
    total_success = int((df["status"] == "SUCCESS").sum())
    total_error = int((df["status"] == "ERROR").sum())
    success_rate = round((total_success / total_records) * 100, 1) if total_records > 0 else 0

    # Tempo de execução
    start_time = df["timestamp"].min()
    end_time = df["timestamp"].max()

    # Estatísticas por Tipo de Página
    tipo_stats = df.groupby(["tipo_pagina", "status"]).size().unstack(fill_value=0).reset_index()
    if "SUCCESS" not in tipo_stats.columns:
        tipo_stats["SUCCESS"] = 0
    if "ERROR" not in tipo_stats.columns:
        tipo_stats["ERROR"] = 0

    # Desempenho por IES
    ies_stats = df.groupby("sigla").agg(
        total=("status", "count"),
        sucesso=("status", lambda x: (x == "SUCCESS").sum()),
        erro=("status", lambda x: (x == "ERROR").sum())
    ).reset_index()
    ies_stats["taxa"] = (ies_stats["sucesso"] / ies_stats["total"] * 100).round(1)
    ies_stats = ies_stats.sort_values(by=["erro", "sigla"], ascending=[False, True])

    # Prepara JSON para tabela interativa no JS
    records_json = df.to_json(orient="records")
    ies_stats_json = ies_stats.to_json(orient="records")

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relatório de Migração IES - Study in Brazil (Plone 6)</title>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-dark: #0f172a;
            --card-bg: #1e293b;
            --card-border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-blue: #38bdf8;
            --accent-green: #22c55e;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --accent-purple: #a855f7;
            --glass-bg: rgba(30, 41, 59, 0.7);
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Plus Jakarta Sans', sans-serif;
        }}

        body {{
            background-color: var(--bg-dark);
            color: var(--text-main);
            min-height: 100vh;
            padding: 2rem;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        /* Header */
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 2rem;
            border-bottom: 1px solid var(--card-border);
            margin-bottom: 2rem;
        }}

        .logo-area h1 {{
            font-size: 1.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        .logo-area p {{
            color: var(--text-muted);
            font-size: 0.95rem;
            margin-top: 0.25rem;
        }}

        .badge-portal {{
            background: rgba(56, 189, 248, 0.1);
            color: var(--accent-blue);
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }}

        /* KPI Grid */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .kpi-card {{
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            position: relative;
            overflow: hidden;
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}

        .kpi-card:hover {{
            transform: translateY(-4px);
            border-color: var(--accent-blue);
        }}

        .kpi-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
        }}

        .kpi-card.green::before {{ background: var(--accent-green); }}
        .kpi-card.blue::before {{ background: var(--accent-blue); }}
        .kpi-card.red::before {{ background: var(--accent-red); }}
        .kpi-card.purple::before {{ background: var(--accent-purple); }}

        .kpi-title {{
            color: var(--text-muted);
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .kpi-value {{
            font-size: 2.2rem;
            font-weight: 800;
            margin: 0.5rem 0;
        }}

        .kpi-subtitle {{
            font-size: 0.8rem;
            color: var(--text-muted);
        }}

        /* Analytics Section */
        .analytics-grid {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        @media (max-width: 1024px) {{
            .analytics-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        .chart-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
        }}

        .card-header h3 {{
            font-size: 1.1rem;
            font-weight: 700;
        }}

        /* Table Controls */
        .table-section {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
        }}

        .controls-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.5rem;
            flex-wrap: wrap;
        }}

        .search-box {{
            position: relative;
            flex: 1;
            min-width: 280px;
        }}

        .search-box input {{
            width: 100%;
            background: #0f172a;
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 0.75rem 1rem 0.75rem 2.5rem;
            color: var(--text-main);
            font-size: 0.9rem;
            outline: none;
            transition: border-color 0.2s;
        }}

        .search-box input:focus {{
            border-color: var(--accent-blue);
        }}

        .search-box svg {{
            position: absolute;
            left: 0.85rem;
            top: 50%;
            transform: translateY(-50%);
            width: 18px;
            height: 18px;
            fill: var(--text-muted);
        }}

        .filter-buttons {{
            display: flex;
            gap: 0.5rem;
        }}

        .btn-filter {{
            background: #0f172a;
            border: 1px solid var(--card-border);
            color: var(--text-muted);
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .btn-filter.active, .btn-filter:hover {{
            background: var(--accent-blue);
            color: #000;
            border-color: var(--accent-blue);
        }}

        /* Data Table */
        .table-wrapper {{
            overflow-x: auto;
            max-height: 500px;
            overflow-y: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }}

        th {{
            background: #0f172a;
            color: var(--text-muted);
            padding: 1rem;
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 10;
            border-bottom: 1px solid var(--card-border);
        }}

        td {{
            padding: 0.85rem 1rem;
            border-bottom: 1px solid rgba(51, 65, 85, 0.4);
        }}

        tr:hover td {{
            background: rgba(56, 189, 248, 0.03);
        }}

        .status-tag {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.3rem 0.75rem;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 0.75rem;
        }}

        .status-tag.success {{
            background: rgba(34, 197, 94, 0.15);
            color: var(--accent-green);
            border: 1px solid rgba(34, 197, 94, 0.3);
        }}

        .status-tag.error {{
            background: rgba(239, 68, 68, 0.15);
            color: var(--accent-red);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }}

        .status-tag.skipped {{
            background: rgba(148, 163, 184, 0.15);
            color: var(--text-muted);
            border: 1px solid rgba(148, 163, 184, 0.3);
        }}

        .url-link {{
            color: var(--accent-blue);
            text-decoration: none;
            word-break: break-all;
        }}

        .url-link:hover {{
            text-decoration: underline;
        }}

        /* Footer */
        footer {{
            margin-top: 3rem;
            text-align: center;
            color: var(--text-muted);
            font-size: 0.85rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--card-border);
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="logo-area">
                <h1>🚀 Dashboard de Migração Plone 6</h1>
                <p>Portal Study in Brazil — Status detalhado da execução de automação</p>
            </div>
            <div class="badge-portal">
                CMS Plone 6 REST API
            </div>
        </header>

        <!-- KPI Grid -->
        <div class="kpi-grid">
            <div class="kpi-card blue">
                <div class="kpi-title">Instituições (IES)</div>
                <div class="kpi-value">{total_ies}</div>
                <div class="kpi-subtitle">Total de universidades mapeadas</div>
            </div>

            <div class="kpi-card green">
                <div class="kpi-title">Taxa de Sucesso</div>
                <div class="kpi-value">{success_rate}%</div>
                <div class="kpi-subtitle">{total_success} de {total_records} operações concluídas</div>
            </div>

            <div class="kpi-card red">
                <div class="kpi-title">Operações com Erro</div>
                <div class="kpi-value">{total_error}</div>
                <div class="kpi-subtitle">Ações que requerem verificação manual</div>
            </div>

            <div class="kpi-card purple">
                <div class="kpi-title">Total de Requisições</div>
                <div class="kpi-value">{total_records}</div>
                <div class="kpi-subtitle">Páginas criadas + Publicações de workflow</div>
            </div>
        </div>

        <!-- Analytics Grid -->
        <div class="analytics-grid">
            <!-- Gráfico de Pizza/Barras por Tipo de Página -->
            <div class="chart-card">
                <div class="card-header">
                    <h3>Status por Tipo de Operação</h3>
                </div>
                <canvas id="pageTypeChart" height="120"></canvas>
            </div>

            <!-- Resumo de IES com Pendências -->
            <div class="chart-card">
                <div class="card-header">
                    <h3>IES com Maior Índice de Falha</h3>
                </div>
                <canvas id="iesErrorChart" height="120"></canvas>
            </div>
        </div>

        <!-- Interactive Table Section -->
        <div class="table-section">
            <div class="controls-row">
                <div class="search-box">
                    <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
                    <input type="text" id="searchInput" placeholder="Buscar por Sigla, Tipo ou URL...">
                </div>
                <div class="filter-buttons">
                    <button class="btn-filter active" onclick="filterData('ALL')">Todos ({total_records})</button>
                    <button class="btn-filter" onclick="filterData('SUCCESS')">Sucesso ({total_success})</button>
                    <button class="btn-filter" onclick="filterData('ERROR')">Erros ({total_error})</button>
                    <button class="btn-filter" onclick="filterData('SKIPPED')">Ignoradas / Manuais</button>
                </div>
            </div>

            <div class="table-wrapper">
                <table id="reportTable">
                    <thead>
                        <tr>
                            <th>Data / Hora</th>
                            <th>Sigla IES</th>
                            <th>Tipo de Página</th>
                            <th>Status</th>
                            <th>Detalhes</th>
                            <th>URL no Portal</th>
                        </tr>
                    </thead>
                    <tbody id="tableBody">
                        <!-- Gerado via JavaScript -->
                    </tbody>
                </table>
            </div>
        </div>

        <footer>
            Relatório gerado automaticamente • Automação PloneRestClient • Study in Brazil
        </footer>
    </div>

    <script>
        const rawData = {records_json};
        const iesStats = {ies_stats_json};
        let currentFilter = 'ALL';

        // Renderiza Tabela
        function renderTable(data) {{
            const tbody = document.getElementById('tableBody');
            tbody.innerHTML = '';

            data.forEach(row => {{
                const tr = document.createElement('tr');
                const formattedDate = new Date(row.timestamp).toLocaleString('pt-BR');
                let tagClass = 'error';
                let tagLabel = '✕ ERROR';
                if (row.status === 'SUCCESS') {{
                    tagClass = 'success';
                    tagLabel = '✓ SUCCESS';
                }} else if (row.status === 'SKIPPED') {{
                    tagClass = 'skipped';
                    tagLabel = '⏭ SKIPPED';
                }}

                tr.innerHTML = `
                    <td>${{formattedDate}}</td>
                    <td><strong>${{row.sigla}}</strong></td>
                    <td>${{row.tipo_pagina}}</td>
                    <td>
                        <span class="status-tag ${{tagClass}}">
                            ${{tagLabel}}
                        </span>
                    </td>
                    <td>${{row.detalhes}}</td>
                    <td><a href="${{row.url}}" target="_blank" class="url-link">${{row.url}}</a></td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        // Filtros e Busca
        function filterData(status) {{
            currentFilter = status;
            document.querySelectorAll('.btn-filter').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            applyFilters();
        }}

        function applyFilters() {{
            const searchVal = document.getElementById('searchInput').value.toLowerCase();
            const filtered = rawData.filter(row => {{
                const matchesStatus = currentFilter === 'ALL' || row.status === currentFilter;
                const matchesSearch = row.sigla.toLowerCase().includes(searchVal) ||
                                      row.tipo_pagina.toLowerCase().includes(searchVal) ||
                                      row.url.toLowerCase().includes(searchVal) ||
                                      row.detalhes.toLowerCase().includes(searchVal);
                return matchesStatus && matchesSearch;
            }});
            renderTable(filtered);
        }}

        document.getElementById('searchInput').addEventListener('input', applyFilters);

        // Renderiza Gráficos
        window.onload = function() {{
            renderTable(rawData);

            // Chart 1: Status por Tipo de Página
            const pageTypes = [...new Set(rawData.map(r => r.tipo_pagina))];
            const successCounts = pageTypes.map(pt => rawData.filter(r => r.tipo_pagina === pt && r.status === 'SUCCESS').length);
            const errorCounts = pageTypes.map(pt => rawData.filter(r => r.tipo_pagina === pt && r.status === 'ERROR').length);

            new Chart(document.getElementById('pageTypeChart'), {{
                type: 'bar',
                data: {{
                    labels: pageTypes,
                    datasets: [
                        {{ label: 'Sucesso', data: successCounts, backgroundColor: '#22c55e' }},
                        {{ label: 'Erro', data: errorCounts, backgroundColor: '#ef4444' }}
                    ]
                }},
                options: {{
                    responsive: true,
                    scales: {{
                        x: {{ stacked: true, grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }},
                        y: {{ stacked: true, grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }}
                    }},
                    plugins: {{
                        legend: {{ labels: {{ color: '#f8fafc' }} }}
                    }}
                }}
            }});

            // Chart 2: Top IES com mais erros
            const topErrors = iesStats.filter(i => i.erro > 0).slice(0, 5);
            new Chart(document.getElementById('iesErrorChart'), {{
                type: 'doughnut',
                data: {{
                    labels: topErrors.map(i => i.sigla),
                    datasets: [{{
                        data: topErrors.map(i => i.erro),
                        backgroundColor: ['#ef4444', '#f59e0b', '#a855f7', '#38bdf8', '#64748b']
                    }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{ position: 'bottom', labels: {{ color: '#f8fafc' }} }}
                    }}
                }}
            }});
        }};
    </script>
</body>
</html>
"""

    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[OK] Relatorio HTML gerado com sucesso em: '{output_html.resolve()}'")


if __name__ == "__main__":
    generate_html_report()
