import csv
import json
import smtplib
import ssl
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# -------------------------------------------------------
# LOAD SETTINGS
# -------------------------------------------------------
with open("settings.json", "r") as f:
    SETTINGS = json.load(f)

EMAIL_CFG = SETTINGS["alerts"]["destinations"]["email"]


# -------------------------------------------------------
# LOAD CSV + STRUCTURE DATA
# -------------------------------------------------------
def load_csv(csv_file):
    with open(csv_file, "r") as f:
        return list(csv.DictReader(f))


# -------------------------------------------------------
# TEAM STANDUP SUMMARY (SAFE TO SHARE)
# -------------------------------------------------------
def build_team_standup_summary(rows):
    lines = []
    lines.append("DAILY STANDUP SUMMARY\n")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}\n")
    lines.append("=" * 60 + "\n")

    blockers = [r for r in rows if r["Alert_Level"] == "CRITICAL"]
    stalled = [r for r in rows if r["Alert_Level"] == "WARNING"]
    unassigned = [r for r in rows if r["Alert_Level"] == "HIGH" and r["Assignee"] == "UNASSIGNED"]

    if blockers:
        lines.append(f"🔴 *{len(blockers)} BLOCKERS*:\n")
        for b in blockers:
            lines.append(f" • {b['Issue_Key']} — {b['Summary']} ({b['Assignee']})")
    else:
        lines.append("No blockers today.")

    lines.append("\n")

    if stalled:
        lines.append(f"⚠️ *{len(stalled)} Stalled Items (>2 days inactivity)*:\n")
        for s in stalled:
            lines.append(f" • {s['Issue_Key']} — {s['Assignee']} (Last updated {s['Last_Updated']})")
    else:
        lines.append("No stalled items.")

    lines.append("\n")

    if unassigned:
        lines.append("❗ *Unassigned High Priority Work*:\n")
        for u in unassigned:
            lines.append(f" • {u['Issue_Key']} — {u['Summary']}")
    else:
        lines.append("No unassigned high-priority items.")

    return "\n".join(lines)


# -------------------------------------------------------
# PRIVATE MANAGER INSIGHTS (FOR JULIE ONLY)
# -------------------------------------------------------
def build_private_manager_report(rows):
    lines = []
    lines.append("PRIVATE MANAGER INSIGHTS REPORT")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("=" * 60 + "\n")

    # BLOCKERS
    blockers = [r for r in rows if r["Alert_Level"] == "CRITICAL"]
    if blockers:
        lines.append(f"🔴 BLOCKERS ({len(blockers)}) — Direct Risk\n")
        for b in blockers:
            lines.append(f" • {b['Issue_Key']} — {b['Summary']} ({b['Assignee']})")

        lines.append("\nManagement Action:")
        lines.append(" • Ensure each assignee provides root-cause + ETA for unblocking.")
        lines.append(" • Verify dependencies across teams.")

    # STALLED
    stalled = [r for r in rows if r["Alert_Level"] == "WARNING"]
    if stalled:
        lines.append("\n⚠️ STALLED WORK (>2 days no movement)\n")
        for s in stalled:
            lines.append(f" • {s['Issue_Key']} — {s['Assignee']} (Last activity {s['Last_Updated']})")

        lines.append("\nRisk:")
        lines.append(" • Potential lack of clarity / technical blockers unreported.")
        lines.append(" • Ask each developer for a plan to move forward today.")

    # HIGH PRIORITY UNASSIGNED
    high_unassigned = [r for r in rows if r["Alert_Level"] == "HIGH" and r["Assignee"] == "UNASSIGNED"]
    if high_unassigned:
        lines.append("\n❗HIGH PRIORITY UNASSIGNED WORK\n")
        for u in high_unassigned:
            lines.append(f" • {u['Issue_Key']} — {u['Summary']}")

        lines.append("\nManagement Action:")
        lines.append(" • Reassign immediately. Drop a low-value item if necessary.")

    # Workload Analysis
    workload = {}
    for r in rows:
        sp = int(r["Story_Points"]) if r["Story_Points"].isdigit() else 0
        workload[r["Assignee"]] = workload.get(r["Assignee"], 0) + sp

    overloaded = [p for p, sp in workload.items() if sp >= 13 and p != "UNASSIGNED"]

    if overloaded:
        lines.append("\n📈 POTENTIAL OVERLOAD\n")
        for p in overloaded:
            lines.append(f" • {p}: {workload[p]} story points allocated.")
        lines.append("\nAction:")
        lines.append(" • Rebalance workload or postpone low-priority items.")

    lines.append("\nEnd of report.\n")

    return "\n".join(lines)


# -------------------------------------------------------
# DIRECTOR-LEVEL SNAPSHOT (EXECUTIVE SUMMARY)
# -------------------------------------------------------
def build_director_snapshot(rows):
    blockers = len([r for r in rows if r["Alert_Level"] == "CRITICAL"])
    stalled = len([r for r in rows if r["Alert_Level"] == "WARNING"])
    unassigned = len([r for r in rows if r["Alert_Level"] == "HIGH" and r["Assignee"] == "UNASSIGNED"])

    return f"""
Director-Level Sprint Snapshot
==============================

📌 Date: {datetime.now().strftime('%Y-%m-%d')}

🔴 Critical Blockers: {blockers}
⚠️ Stalled Items: {stalled}
❗ Unassigned High Priority Items: {unassigned}

Overall Assessment:
-------------------
{"HIGH RISK — blocker resolution required immediately." if blockers else
 "MODERATE RISK — monitor stalled work closely." if stalled else
 "LOW RISK — sprint progressing normally."}

"""


# -------------------------------------------------------
# EMAIL SENDER
# -------------------------------------------------------
def send_private_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = f"Engineering Insights Service <{EMAIL_CFG['from_address']}>"
    msg["To"] = ", ".join(EMAIL_CFG["to_addresses"])
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    ctx = ssl.create_default_context()

    with smtplib.SMTP(EMAIL_CFG["smtp_server"], EMAIL_CFG["smtp_port"]) as server:
        server.starttls(context=ctx)
        server.login(EMAIL_CFG["username"], EMAIL_CFG["password"])
        server.send_message(msg)

    print("📧 Private email sent.")


# -------------------------------------------------------
# MAIN ENTRY
# -------------------------------------------------------
def run_insights(csv_file):
    rows = load_csv(csv_file)

    team_summary = build_team_standup_summary(rows)
    private_report = build_private_manager_report(rows)
    director_summary = build_director_snapshot(rows)

    full_email = (
        "TEAM STANDUP SUMMARY\n\n" +
        team_summary +
        "\n\n\nPRIVATE MANAGER INSIGHTS\n\n" +
        private_report +
        "\n\nDIRECTOR SNAPSHOT\n\n" +
        director_summary
    )

    send_private_email(
        subject="Daily Engineering Insights Report",
        body=full_email
    )


if __name__ == "__main__":
    print("Provide the CSV file path to run analysis.")
