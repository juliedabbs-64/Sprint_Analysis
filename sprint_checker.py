import os
import csv
import json
import pandas as pd
import random
import requests
import smtplib
import ssl
from jira_client import fetch_jira_dataframe
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# =========================================================
#  SPRINT HEALTH CHECKER
# =========================================================

class SprintHealthChecker:
    def __init__(self):
        with open("settings.json", "r") as f:
            full_cfg = json.load(f)

        # Select profile
        self.mode = full_cfg.get("mode", "mock")
        self.config = full_cfg["profiles"][self.mode]

        # Jira config
        jira_cfg = self.config["jira"]
        self.jira_url = jira_cfg["url"]
        self.jira_email = jira_cfg["email"]
        self.jira_token = jira_cfg["token"]
        self.project_key = jira_cfg["project_key"]

        # Auth only needed in live mode
        self.auth = (self.jira_email, self.jira_token) if jira_cfg.get("enabled") else None

        # Alerts
        alerts_cfg = self.config["alerts"]
        self.alerts_enabled = alerts_cfg["enabled"]
        self.destinations = alerts_cfg.get("destinations", {})

    # -----------------------------------------------------
    # JIRA QUERY (LIVE OR MOCK)
    # -----------------------------------------------------
    def run_query(self, jql):

        # ================================
        # MOCK MODE — unchanged
        # ================================
        if self.mode == "mock":
            return self._mock_data(jql)

        # ================================
        # LIVE MODE — Jira client + JQL filtering
        # ================================
        if self.config["jira"]["enabled"]:
            df = fetch_jira_dataframe(self.config["jira"])
            rows = df.to_dict(orient="records")

            filtered = []

            for r in rows:
                status = r["Status"]
                assignee = r["Assignee"]
                updated = r["Last_Updated"]
                priority = r["Priority"]

                # BLOCKERS
                if 'Blocked' in jql and status == 'Blocked':
                    filtered.append(r)

                # STALLED (In Progress)
                elif 'status = "In Progress"' in jql and status == 'In Progress':
                    filtered.append(r)

                # UNASSIGNED HIGH PRIORITY
                elif 'assignee is EMPTY' in jql and assignee == 'UNASSIGNED':
                    filtered.append(r)

                # DONE
                elif 'status = Done' in jql and status == 'Done':
                    filtered.append(r)

            return filtered

        # fallback
        return []

    # -----------------------------------------------------
    # MOCK MODE — REALISTIC ISSUES
    # -----------------------------------------------------
    def _mock_data(self, jql):
        today = datetime.now()

        def make(key, summary, status, assignee, priority, days_ago, sp, blockers=0):
            return {
                "key": key,
                "fields": {
                    "summary": summary,
                    "status": {"name": status},
                    "assignee": {"displayName": assignee} if assignee else None,
                    "priority": {"name": priority},
                    "updated": (today - timedelta(days=days_ago)).isoformat(),
                    "customfield_10024": sp,
                    "issuelinks": [{"type": {"outward": "blocks"}}] * blockers
                }
            }

        # DONE items
        done_items = [
            make("GK-101", "Migrate legacy reports to new BI platform",
                 "Done", "Alice Smith", "Medium", 1, 5),

            make("GK-109", "Fix table ordering crash on Android",
                 "Done", "Bob Jones", "High", 2, 3),

            make("GK-113", "Improve menu recommendation algorithm",
                 "Done", "Diana Prince", "Medium", 3, 8)
        ]

        if "status = Done" in jql:
            return done_items

        # BLOCKERS
        if "Blocked" in jql:
            return [
                make("GK-124", "POS integration blocked by payment gateway timeout",
                     "Blocked", "Alice Smith", "Highest", 2, 5, blockers=2),

                make("GK-131", "Hotel booking API rate limited by external provider",
                     "Blocked", "Bob Jones", "High", 1, 2, blockers=1)
            ]

        # STALLED
        if "updated <=" in jql:
            return [
                make("GK-115", "Update menu pricing across pub chain",
                     "In Progress", "Charlie Brown", "Medium", 4, 3),

                make("GK-119", "Refactor loyalty points calculation",
                     "In Progress", "Diana Prince", "Medium", 6, 3)
            ]

        # UNASSIGNED
        if "assignee is EMPTY" in jql:
            return [
                make("GK-130", "URGENT: Fix production bug in table ordering app",
                     "To Do", None, "Highest", 0, 3)
            ]

        return done_items

    # -----------------------------------------------------
    # CSV GENERATION (MOCK & LIVE SAFE)
    # -----------------------------------------------------
    def generate_csv(self):
        Path("./reports").mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        csv_file = f"./reports/{self.mode.upper()}_sprint_health_{timestamp}.csv"

        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Query_Type", "Issue_Key", "Summary", "Status", "Assignee",
                "Priority", "Story_Points", "Last_Updated", "Alert_Level"
            ])

            queries = {
                "blockers": f'project = {self.project_key} AND status = "Blocked"',
                "stalled": f'project = {self.project_key} AND status = "In Progress" AND updated <= -2d',
                "unassigned": f'project = {self.project_key} AND assignee is EMPTY AND priority = High',
                "done": f'project = {self.project_key} AND status = Done'
            }

            for name, jql in queries.items():
                issues = self.run_query(jql)

                for issue in issues:

                    # MOCK MODE
                    if "fields" in issue:
                        fields = issue["fields"]
                        key = issue["key"]
                        summary = fields["summary"][:60]
                        status = fields["status"]["name"]
                        assignee = fields["assignee"]["displayName"] if fields["assignee"] else "UNASSIGNED"
                        priority = fields["priority"]["name"] if fields.get("priority") else "None"
                        story_points = fields.get("customfield_10024", 3)
                        updated = fields["updated"][:10]

                    # LIVE MODE
                    else:
                        key = issue["Issue_Key"]
                        summary = issue["Summary"][:60]
                        status = issue["Status"]
                        assignee = issue["Assignee"]
                        priority = issue["Priority"]
                        story_points = issue.get("Story_Points", 0)
                        updated = (
                            issue["Last_Updated"][:10]
                            if isinstance(issue["Last_Updated"], str)
                            else ""
                        )

                    writer.writerow([
                        name, key, summary, status, assignee, priority,
                        story_points, updated,
                        "CRITICAL" if name == "blockers"
                        else "WARNING" if name == "stalled"
                        else "HIGH" if name == "unassigned"
                        else "DONE"
                    ])

        return csv_file

    # -----------------------------------------------------
    # Extract critical from CSV
    # -----------------------------------------------------
    def _get_critical_issues(self, csv_file):
        try:
            with open(csv_file) as f:
                return [r for r in csv.DictReader(f) if r["Alert_Level"] == "CRITICAL"]
        except FileNotFoundError:
            return []

    # -----------------------------------------------------
    # ALERT ROUTER
    # -----------------------------------------------------
    def send_alerts(self, csv_file):
        critical = self._get_critical_issues(csv_file)

        if not critical:
            print("✅ No critical alerts to send.")
            return

        print(f"📊 Sending alerts for {len(critical)} critical issues...\n")

        for dest_type, cfg in self.destinations.items():
            if not cfg.get("enabled"):
                continue

            try:
                if dest_type == "slack":
                    self._send_slack(critical, cfg)
                elif dest_type == "email":
                    self._send_email(critical, cfg)
            except Exception as e:
                print(f"❌ Failed sending to {dest_type}: {e}")

    def _send_slack(self, issues, cfg):
        url = cfg["webhook_url"]
        msg = f"🔴 {len(issues)} Sprint Blockers Detected\n"
        for i in issues:
            msg += f"• {i['Issue_Key']} — {i['Summary']} ({i['Assignee']})\n"

        r = requests.post(url, json={"text": msg}, timeout=10)
        r.raise_for_status()
        print("📢 Slack alert sent ✔")

    def _send_email(self, issues, cfg):
        msg = MIMEMultipart()
        msg["From"] = cfg["from_address"]
        msg["To"] = ", ".join(cfg["to_addresses"])
        msg["Subject"] = "[SPRINT ALERT] Critical blockers detected"

        body = "CRITICAL BLOCKERS:\n\n"
        for i in issues:
            body += f"{i['Issue_Key']} — {i['Summary']} ({i['Assignee']})\n"

        msg.attach(MIMEText(body, "plain"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as s:
            s.starttls(context=ctx)
            s.login(cfg["username"], cfg["password"])
            s.send_message(msg)

        print("📧 Email alert sent ✔")


# =========================================================
# ANALYSIS FOR CONSOLE
# =========================================================
def analyse_csv(csv_file):
    with open(csv_file) as f:
        rows = list(csv.DictReader(f))

    insights = []

    blockers = [r for r in rows if r["Alert_Level"] == "CRITICAL"]
    stalled = [r for r in rows if r["Alert_Level"] == "WARNING"]
    unassigned = [r for r in rows if r["Alert_Level"] == "HIGH"]

    if blockers:
        insights.append(f"🔴 {len(blockers)} BLOCKERS:")
        for b in blockers:
            insights.append(f" • {b['Issue_Key']} — {b['Summary']} ({b['Assignee']})")

    if stalled:
        insights.append(f"\n⚠️ {len(stalled)} stalled items:")
        for s in stalled:
            insights.append(f" • {s['Issue_Key']} — {s['Assignee']} (last updated {s['Last_Updated']})")

    if unassigned:
        insights.append("\n❗ Unassigned high priority:")
        for u in unassigned:
            insights.append(f" • {u['Issue_Key']} — {u['Summary']}")

    done = [r for r in rows if r["Alert_Level"] == "DONE"]
    if done:
        insights.append(f"\n✅ {len(done)} items completed this sprint")

    return "\n".join(insights)


# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    from insights_service import run_insights
    from dashboard import generate_dashboard

    checker = SprintHealthChecker()
    csv_file = checker.generate_csv()

    print("\n📊 DAILY ANALYSIS:\n")
    print(analyse_csv(csv_file))
    print("\n" + "="*60 + "\n")

    checker.send_alerts(csv_file)

    print("\n📡 Running Insights Service...")
    run_insights(csv_file)

    print("\n📊 Generating Dashboard...")
    generate_dashboard(csv_file)
