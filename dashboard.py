import os
import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
from pathlib import Path


# --------------------------------------------------------
# Utility: Load CSV
# --------------------------------------------------------
def load_sprint_csv(csv_path):
    df = pd.read_csv(csv_path)
    return df


# --------------------------------------------------------
# Utility: Sprint Health Score
# --------------------------------------------------------
def calculate_sprint_health(df):
    blockers = len(df[df["Alert_Level"] == "CRITICAL"])
    stalled = len(df[df["Alert_Level"] == "WARNING"])
    unassigned = len(df[(df["Alert_Level"] == "HIGH") & (df["Assignee"] == "UNASSIGNED")])

    score = 100
    score -= blockers * 25
    score -= stalled * 10
    score -= unassigned * 5

    return max(score, 5)


# --------------------------------------------------------
# Generate Dashboard
# --------------------------------------------------------
def generate_dashboard(csv_path):

    df = load_sprint_csv(csv_path)

    # Output folders
    output_dir = Path("./dashboards")
    template_dir = Path("./templates")

    output_dir.mkdir(exist_ok=True)
    template_dir.mkdir(exist_ok=True)

    # Data groups
    blockers = df[df["Alert_Level"] == "CRITICAL"]
    stalled = df[df["Alert_Level"] == "WARNING"]
    unassigned = df[(df["Alert_Level"] == "HIGH") & (df["Assignee"] == "UNASSIGNED")]
    done = df[df["Alert_Level"] == "DONE"]

    # ============================================
    # STORY POINT BAR CHART (VERTICAL BARS)
    # ============================================
    # Plotly — vertical story point bar chart
    sp_chart = go.Figure()

    # Sort by story points descending
    df_sorted = df.sort_values(by="Story_Points", ascending=False)

    sp_chart.add_trace(go.Bar(
        x=df_sorted["Assignee"],
        y=df_sorted["Story_Points"],
        marker_color="#0a2342",
        text=df_sorted["Story_Points"],
        textposition="outside"
    ))

    sp_chart.update_layout(
        title="Story Points Completed by Assignee",
        xaxis_title="Assignee",
        yaxis_title="Story Points",
        template="plotly_white",
        height=450,
        margin=dict(l=40, r=40, t=60, b=120),
        xaxis=dict(tickangle=-45)   # Tilt names to avoid overlap
    )

    sp_div = sp_chart.to_html(full_html=False)


    # ============================================
    # Render Jinja Template
    # ============================================
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("dashboard_template.html")

    html = template.render(
        date=datetime.now().strftime("%Y-%m-%d"),
        health_score=calculate_sprint_health(df),
        blockers=blockers.to_dict(orient="records"),
        stalled=stalled.to_dict(orient="records"),
        unassigned=unassigned.to_dict(orient="records"),
        done=done.to_dict(orient="records"),
        sp_chart=sp_div
    )

    # Output file
    output_path = output_dir / "daily_standup_dashboard_v2.html"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"📊 Dashboard generated: {output_path}")
    return str(output_path)
