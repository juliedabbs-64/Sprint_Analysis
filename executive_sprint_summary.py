import sys
import subprocess
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader
import base64
from io import BytesIO


# ==========================================================
# KPI ENGINE
# ==========================================================
def compute_kpis(df):
    committed = df["Story_Points"].sum()
    completed = df[df["Status"] == "Done"]["Story_Points"].sum()
    delivery_pct = round((completed / committed * 100), 1) if committed else 0
    carryover = committed - completed

    blockers = len(df[df["Status"] == "Blocked"])
    stalled = len(df[(df["Status"] == "In Progress") & (df["Alert_Level"] == "WARNING")])
    unassigned = len(df[df["Assignee"].str.upper() == "UNASSIGNED"])

    # Risk messages (simple list)
    risks = []
    if blockers: risks.append(f"{blockers} blockers are impacting throughput.")
    if stalled: risks.append(f"{stalled} items show prolonged inactivity.")
    if unassigned: risks.append("Unassigned high-priority work is delaying flow.")
    if carryover > committed * 0.4: risks.append(f"{carryover} SP likely rolling to next sprint.")
    if not risks: risks.append("No major risks detected.")

    # Simple recommendations
    recs = []
    if blockers: recs.append("Escalate dependency blockers within 24h.")
    if stalled: recs.append("Introduce aged-WIP triage at daily standup.")
    if unassigned: recs.append("Prevent unassigned high-priority items entering sprint.")
    if delivery_pct < 80: recs.append("Reduce WIP or slice stories smaller next sprint.")
    if not recs: recs.append("Flow appears stable — maintain current practices.")

    return {
        "committed": int(committed),
        "completed": int(completed),
        "delivery_pct": delivery_pct,
        "carryover": int(carryover),
        "risks": risks,
        "recs": recs,
    }


# ==========================================================
# REAL BURNDOWN (ACTUAL VS IDEAL)
# ==========================================================
def generate_burndown_chart(df):
    plt.switch_backend('agg')

    green = "#6C8C7A"
    gold = "#C7A76C"
    heritage_green = "#0A3A2A"
    offwhite = "#F8F5ED"

    df["Last_Updated"] = pd.to_datetime(df["Last_Updated"])
    start_date = df["Last_Updated"].min()
    end_date = df["Last_Updated"].max()

    sprint_days = pd.date_range(start=start_date, end=end_date, freq="D")
    committed = df["Story_Points"].sum()

    done_df = df[df["Status"] == "Done"]
    completion_map = (
        done_df.groupby("Last_Updated")["Story_Points"]
        .sum()
        .reindex(sprint_days, fill_value=0)
    )

    remaining_actual = []
    remaining = committed
    for day in sprint_days:
        remaining -= completion_map.loc[day]
        remaining_actual.append(remaining)

    # Ideal line
    ideal = [
        committed - (committed / (len(sprint_days)-1)) * i
        for i in range(len(sprint_days))
    ]

    fig, ax = plt.subplots(figsize=(10,5))
    fig.patch.set_facecolor(heritage_green)
    ax.set_facecolor(heritage_green)

    ax.plot(sprint_days, remaining_actual, color=green, linewidth=3, label="Actual")
    ax.plot(sprint_days, ideal, color=gold, linestyle="--", linewidth=2, label="Ideal")

    ax.set_title("Burndown Chart", color=gold)
    ax.set_ylabel("Remaining Story Points", color=offwhite)
    ax.set_xlabel("Date", color=offwhite)
    ax.tick_params(colors=offwhite)
    ax.legend(facecolor=heritage_green, labelcolor=offwhite)

    buffer = BytesIO()
    plt.tight_layout()
    plt.savefig(buffer, format="png", transparent=False)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ==========================================================
# REAL VELOCITY
# ==========================================================
def generate_velocity_chart(df):
    plt.switch_backend('agg')

    gold = "#C7A76C"
    heritage_green = "#0A3A2A"
    offwhite = "#F8F5ED"

    completed = df[df["Status"] == "Done"]["Story_Points"].sum()

    fig, ax = plt.subplots(figsize=(5,4))
    fig.patch.set_facecolor(heritage_green)
    ax.set_facecolor(heritage_green)

    ax.bar(["This Sprint"], [completed], color=gold)
    ax.set_title("Velocity (Story Points Completed)", color=gold)
    ax.set_ylabel("Story Points", color=offwhite)
    ax.tick_params(colors=offwhite)

    buffer = BytesIO()
    plt.tight_layout()
    plt.savefig(buffer, format="png", transparent=False)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ==========================================================
# REAL CFD (Story Points per Status)
# ==========================================================
def get_cfd_table(df):
    order = ["To Do", "In Progress", "Blocked", "Done"]
    counts = df.groupby("Status")["Issue_Key"].count().reindex(order, fill_value=0)
    points = df.groupby("Status")["Story_Points"].sum().reindex(order, fill_value=0)

    return [
        {"status": s, "count": int(counts[s]), "points": int(points[s])}
        for s in order
    ]


def generate_cfd_chart(df):
    plt.switch_backend('agg')

    sage = "#6C8C7A"
    gold = "#C7A76C"
    heritage_green = "#0A3A2A"
    offwhite = "#F8F5ED"

    sp_by_status = df.groupby("Status")["Story_Points"].sum().reindex(
        ["To Do", "In Progress", "Blocked", "Done"], fill_value=0
    )

    fig, ax = plt.subplots(figsize=(5,4))
    fig.patch.set_facecolor(heritage_green)
    ax.set_facecolor(heritage_green)

    ax.bar(sp_by_status.index, sp_by_status.values, color=sage)
    ax.set_title("Cumulative Flow (Story Points)", color=gold)
    ax.set_ylabel("Story Points", color=offwhite)
    ax.tick_params(colors=offwhite)
    for tick in ax.get_xticklabels():
        tick.set_rotation(20)

    buffer = BytesIO()
    plt.tight_layout()
    plt.savefig(buffer, format="png", transparent=False)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ==========================================================
# HTML GENERATION (JINJA TEMPLATE)
# ==========================================================
def generate_executive_html(df):
    kpis = compute_kpis(df)

    burndown_png = generate_burndown_chart(df)
    velocity_png = generate_velocity_chart(df)
    cfd_png = generate_cfd_chart(df)
    cfd_table = get_cfd_table(df)

    base_dir = Path(__file__).resolve().parent
    template_dir = base_dir / "templates"

    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("executive_template.html")

    html = template.render(
        kpis=kpis,
        burndown_png=burndown_png,
        velocity_png=velocity_png,
        cfd_png=cfd_png,
        cfd_table=cfd_table
    )
    return html


# ==========================================================
# EXECUTIVE SUMMARY WRAPPER
# ==========================================================
def generate_executive_summary(csv_path):
    df = pd.read_csv(csv_path)

    html_output = generate_executive_html(df)

    reports_dir = Path("./executive_reports")
    reports_dir.mkdir(exist_ok=True)

    html_file = reports_dir / "exec_summary.html"
    html_file.write_text(html_output, encoding="utf-8")

    return {
        "html": str(html_file),
        "pdf": None,
        "pptx": None
    }


# ==========================================================
# CLI ENTRYPOINT
# ==========================================================
if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python executive_sprint_summary.py <CSV|mock|live|latest>")
        sys.exit(1)

    arg = sys.argv[1]
    csv_path = None

    if arg in ["mock", "live"]:
        subprocess.run(["python", "sprint_checker.py", arg], check=True)
        reports_dir = Path("./reports")
        csv_files = sorted(reports_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime)
        csv_path = csv_files[-1] if csv_files else None

    elif arg == "latest":
        reports_dir = Path("./reports")
        csv_files = sorted(reports_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime)
        csv_path = csv_files[-1] if csv_files else None

    else:
        csv_path = Path(arg)

    if not csv_path or not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    print(f"Generating executive sprint summary from: {csv_path}")

    outputs = generate_executive_summary(str(csv_path))

    print("\nGenerated files:")
    print(f"HTML: {outputs['html']}")
