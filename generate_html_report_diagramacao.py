"""
Gerador de Relatório HTML Interativo para a Diagramação das 10 IES no Plone 6
=============================================================================

Lê 'diagramacao_migracao_relatorio.csv' e gera um painel HTML moderno,
interativo e com suporte a filtros e gráficos.
"""

import json
from pathlib import Path
import pandas as pd

DEFAULT_CSV_PATH = Path("diagramacao_migracao_relatorio.csv")
DEFAULT_HTML_PATH = Path("relatorio_diagramacao_10_ies.html")


def generate_diagramation_html_report(csv_path: Path = None, html_path: Path = None):
    input_csv = Path(csv_path) if csv_path else DEFAULT_CSV_PATH
    output_html = Path(html_path) if html_path else DEFAULT_HTML_PATH

    if not input_csv.exists():
        print(f"[ERRO] Arquivo '{input_csv}' não encontrado!")
        return

    print(f"[+] Lendo {input_csv}...")
    try:
        df = pd.read_csv(input_csv, sep=",")
        if len(df.columns) <= 1:
            df = pd.read_csv(input_csv, sep=";")
    except Exception:
        df = pd.read_csv(input_csv, sep=";")

    total_records = len(df)
    total_ies = df["sigla"].nunique() if total_records > 0 else 0
    total_success = int((df["status"] == "SUCCESS").sum()) if total_records > 0 else 0
    total_error = int((df["status"] == "ERROR").sum()) if total_records > 0 else 0
    success_rate = round((total_success / total_records) * 100, 1) if total_records > 0 else 0

    # Desempenho por IES
    if total_records > 0:
        ies_stats = df.groupby("sigla").agg(
            total=("status", "count"),
            sucesso=("status", lambda x: (x == "SUCCESS").sum()),
            erro=("status", lambda x: (x == "ERROR").sum())
        ).reset_index()
        ies_stats["taxa"] = (ies_stats["sucesso"] / ies_stats["total"] * 100).round(1)
        ies_stats = ies_stats.sort_values(by=["erro", "sigla"], ascending=[False, True])
        ies_stats_json = ies_stats.to_json(orient="records")
        records_json = df.to_json(orient="records")
    else:
        ies_stats_json = "[]"
        records_json = "[]"

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relatório de Diagramação de IES • Study in Brazil • Plone 6</title>
    <!-- Google Fonts & Chart.js -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-base: #0B1120;
            --bg-card: rgba(15, 23, 42, 0.75);
            --bg-card-hover: rgba(30, 41, 59, 0.85);
            --card-border: rgba(56, 189, 248, 0.15);
            --card-border-glow: rgba(56, 189, 248, 0.35);
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --text-accent: #38BDF8;
            --accent-green: #10B981;
            --accent-green-glow: rgba(16, 185, 129, 0.25);
            --accent-red: #EF4444;
            --accent-red-glow: rgba(239, 68, 68, 0.25);
            --accent-blue: #0284C7;
            --accent-purple: #8B5CF6;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Plus Jakarta Sans', sans-serif;
        }}

        body {{
            background-color: var(--bg-base);
            background-image: 
                radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.08) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(139, 92, 246, 0.08) 0px, transparent 50%);
            color: var(--text-main);
            min-height: 100vh;
            padding: 2rem 1.5rem;
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
            flex-wrap: wrap;
            gap: 1.5rem;
        }}

        .header-title h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #38BDF8 0%, #818CF8 50%, #C084FC 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }}

        .header-title p {{
            color: var(--text-muted);
            margin-top: 0.25rem;
            font-size: 0.95rem;
        }}

        .header-badges {{
            display: flex;
            gap: 0.75rem;
            align-items: center;
        }}

        .badge {{
            background: var(--bg-card);
            border: 1px solid var(--card-border);
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            backdrop-filter: blur(8px);
        }}

        .badge-live {{
            border-color: rgba(16, 185, 129, 0.3);
            color: var(--accent-green);
        }}

        .badge-live::before {{
            content: '';
            width: 8px;
            height: 8px;
            background: var(--accent-green);
            border-radius: 50%;
            box-shadow: 0 0 8px var(--accent-green);
        }}

        /* KPI Cards Grid */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2rem;
        }}

        .kpi-card {{
            background: var(--bg-card);
            border: 1px solid var(--card-border);
            border-radius: 1rem;
            padding: 1.5rem;
            backdrop-filter: blur(12px);
            position: relative;
            overflow: hidden;
            transition: all 0.3s ease;
        }}

        .kpi-card:hover {{
            transform: translateY(-3px);
            border-color: var(--card-border-glow);
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        }}

        .kpi-card h3 {{
            color: var(--text-muted);
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }}

        .kpi-card .value {{
            font-family: 'Outfit', sans-serif;
            font-size: 2.25rem;
            font-weight: 700;
            color: var(--text-main);
        }}

        .kpi-card .sub-value {{
            font-size: 0.8rem;
            margin-top: 0.25rem;
            color: var(--text-muted);
        }}

        .kpi-card.success .value {{
            color: var(--accent-green);
        }}

        .kpi-card.error .value {{
            color: var(--accent-red);
        }}

        /* Charts Section */
        .charts-section {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        @media (max-width: 992px) {{
            .charts-section {{
                grid-template-columns: 1fr;
            }}
        }}

        .chart-box {{
            background: var(--bg-card);
            border: 1px solid var(--card-border);
            border-radius: 1rem;
            padding: 1.5rem;
            backdrop-filter: blur(12px);
        }}

        .chart-box h2 {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .chart-container {{
            position: relative;
            height: 280px;
            width: 100%;
        }}

        /* Table Section */
        .table-section {{
            background: var(--bg-card);
            border: 1px solid var(--card-border);
            border-radius: 1rem;
            padding: 1.5rem;
            backdrop-filter: blur(12px);
            margin-bottom: 3rem;
        }}

        .controls-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }}

        .search-box {{
            position: relative;
            flex: 1;
            max-width: 400px;
        }}

        .search-box input {{
            width: 100%;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--card-border);
            border-radius: 0.5rem;
            padding: 0.65rem 1rem 0.65rem 2.5rem;
            color: var(--text-main);
            font-size: 0.9rem;
            outline: none;
            transition: all 0.2s ease;
        }}

        .search-box input:focus {{
            border-color: var(--text-accent);
            box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2);
        }}

        .search-box svg {{
            position: absolute;
            left: 0.85rem;
            top: 50%;
            transform: translateY(-50%);
            width: 16px;
            height: 16px;
            fill: var(--text-muted);
        }}

        .filter-buttons {{
            display: flex;
            gap: 0.5rem;
        }}

        .btn-filter {{
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid var(--card-border);
            color: var(--text-muted);
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .btn-filter:hover {{
            background: rgba(56, 189, 248, 0.1);
            color: var(--text-main);
        }}

        .btn-filter.active {{
            background: var(--text-accent);
            color: #0B1120;
            border-color: var(--text-accent);
        }}

        .table-wrapper {{
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }}

        th {{
            background: rgba(30, 41, 59, 0.5);
            padding: 0.85rem 1rem;
            color: var(--text-muted);
            font-weight: 600;
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

        .url-link {{
            color: var(--accent-blue);
            text-decoration: none;
            font-family: monospace;
            font-size: 0.8rem;
        }}

        .url-link:hover {{
            text-decoration: underline;
            color: var(--text-accent);
        }}

        footer {{
            text-align: center;
            color: var(--text-muted);
            font-size: 0.85rem;
            padding: 1.5rem 0;
            border-top: 1px solid var(--card-border);
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="header-title">
                <h1>Painel de Diagramação • 10 IES</h1>
                <p>Relatório de carga de conteúdo estruturado no CMS Plone 6 • Study in Brazil</p>
            </div>
            <div class="header-badges">
                <div class="badge badge-live">Status: Executado</div>
                <div class="badge">🔒 Estado: 100% Privado</div>
            </div>
        </header>

        <!-- KPI Grid -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <h3>Total de Operações</h3>
                <div class="value">{total_records}</div>
                <div class="sub-value">Home, Subpáginas e Workflows</div>
            </div>
            <div class="kpi-card">
                <h3>Instituições (IES)</h3>
                <div class="value">{total_ies}</div>
                <div class="sub-value">CEFET-MG, UFAC, UFAPE, UFJ, UFMS, UFRPE, UFRR, UFS, UFSB, UFSC</div>
            </div>
            <div class="kpi-card success">
                <h3>Sucessos</h3>
                <div class="value">{total_success}</div>
                <div class="sub-value">{success_rate}% de taxa de sucesso</div>
            </div>
            <div class="kpi-card {'error' if total_error > 0 else 'success'}">
                <h3>Falhas / Erros</h3>
                <div class="value">{total_error}</div>
                <div class="sub-value">Operações que necessitam atenção</div>
            </div>
        </div>

        <!-- Charts Section -->
        <div class="charts-section">
            <div class="chart-box">
                <h2>📊 Status de Carga por IES</h2>
                <div class="chart-container">
                    <canvas id="iesBarChart"></canvas>
                </div>
            </div>
            <div class="chart-box">
                <h2>🎯 Proporção Geral</h2>
                <div class="chart-container">
                    <canvas id="pieChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Interactive Table Section -->
        <div class="table-section">
            <div class="controls-row">
                <div class="search-box">
                    <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
                    <input type="text" id="searchInput" placeholder="Buscar por Sigla, Tipo de Página ou URL...">
                </div>
                <div class="filter-buttons">
                    <button class="btn-filter active" onclick="filterData('ALL')">Todos ({total_records})</button>
                    <button class="btn-filter" onclick="filterData('SUCCESS')">Sucesso ({total_success})</button>
                    <button class="btn-filter" onclick="filterData('ERROR')">Erros ({total_error})</button>
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
                const isSuccess = row.status === 'SUCCESS';

                tr.innerHTML = `
                    <td>${{formattedDate}}</td>
                    <td><strong>${{row.sigla}}</strong></td>
                    <td>${{row.tipo_pagina}}</td>
                    <td>
                        <span class="status-tag ${{isSuccess ? 'success' : 'error'}}">
                            ${{isSuccess ? '✓ SUCCESS' : '✕ ERROR'}}
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
            const query = document.getElementById('searchInput').value.toLowerCase();
            const filtered = rawData.filter(item => {{
                const matchesStatus = currentFilter === 'ALL' || item.status === currentFilter;
                const matchesQuery = 
                    (item.sigla && item.sigla.toLowerCase().includes(query)) ||
                    (item.tipo_pagina && item.tipo_pagina.toLowerCase().includes(query)) ||
                    (item.detalhes && item.detalhes.toLowerCase().includes(query)) ||
                    (item.url && item.url.toLowerCase().includes(query));
                return matchesStatus && matchesQuery;
            }});
            renderTable(filtered);
        }}

        document.getElementById('searchInput').addEventListener('input', applyFilters);

        // Inicialização dos Gráficos
        document.addEventListener('DOMContentLoaded', () => {{
            renderTable(rawData);

            // Gráfico de Barras por IES
            const ctxBar = document.getElementById('iesBarChart').getContext('2d');
            new Chart(ctxBar, {{
                type: 'bar',
                data: {{
                    labels: iesStats.map(i => i.sigla),
                    datasets: [
                        {{
                            label: 'Sucesso',
                            data: iesStats.map(i => i.sucesso),
                            backgroundColor: 'rgba(16, 185, 129, 0.8)',
                            borderRadius: 4
                        }},
                        {{
                            label: 'Erro',
                            data: iesStats.map(i => i.erro),
                            backgroundColor: 'rgba(239, 68, 68, 0.8)',
                            borderRadius: 4
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        x: {{ stacked: true, grid: {{ color: 'rgba(51, 65, 85, 0.2)' }}, ticks: {{ color: '#94A3B8' }} }},
                        y: {{ stacked: true, grid: {{ color: 'rgba(51, 65, 85, 0.2)' }}, ticks: {{ color: '#94A3B8' }} }}
                    }},
                    plugins: {{
                        legend: {{ labels: {{ color: '#F8FAFC' }} }}
                    }}
                }}
            }});

            // Gráfico de Pizza Geral
            const ctxPie = document.getElementById('pieChart').getContext('2d');
            new Chart(ctxPie, {{
                type: 'doughnut',
                data: {{
                    labels: ['Sucesso', 'Erro'],
                    datasets: [{{
                        data: [{total_success}, {total_error}],
                        backgroundColor: ['#10B981', '#EF4444'],
                        borderWidth: 0
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ position: 'bottom', labels: {{ color: '#F8FAFC' }} }}
                    }}
                }}
            }});
        }});
    </script>
</body>
</html>
"""

    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[OK] Relatório HTML gerado com sucesso em: '{output_html.resolve()}'")


if __name__ == "__main__":
    generate_diagramation_html_report()
