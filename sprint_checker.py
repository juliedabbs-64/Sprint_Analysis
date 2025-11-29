import os
import csv
import json
import random
import requests
import smtplib
import ssl
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
            self.config = json.load(f)

        self.mode = self.config["mode"]
        self.jira_url = self.config["jira"]["url"]
        self.jira_email = self.config["jira"]["email"]
        self.jira_token = self.config["jira"]["token"]
        self.project_key = self.config["jira"]["project_key"]

        # Auth (only used in LIVE mode)
        self.auth = (self.jira_email, self.jira_token) if self.mode == "live" else None

        # Alerts
        self.alerts_enabled = self.config["alerts"]["enabled"]
        self.destinations = self.config["alerts"].get("destinations", {})

    # -----------------------------------------------------
    # JIRA QUERY (LIVE OR MOCK)
    # -----------------------------------------------------
    def run_query(self, jql):
        if self.mode == "mock":
            return self._mock_data(jql)

        url = f"{self.jira_url}/rest/api/3/search"
        params = {
            "jql": jql,
            "fields": "key,summary,status,assignee,priority,updated,issuelinks,customfield_10024",
            "maxResults": 200
        }
        response = requests.get(url, params=params, auth=self.auth, timeout=30)
        response.raise_for_status()
        return response.json()["issues"]

    # -----------------------------------------------------
    # MOCK MODE — NOW WITH DONE ITEMS
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

        # ===== DONE ITEMS =====
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

        # ===== BLOCKERS =====
        if "Blocked" in jql:
            return [
                make("GK-124", "POS integration blocked by payment gateway timeout",
                     "Blocked", "Alice Smith", "Highest", 2, 5, blockers=2),

                make("GK-131", "Hotel booking API rate limited by external provider",
                     "Blocked", "Bob Jones", "High", 1, 2, blockers=1)
            ]

        # ===== STALLED =====
        if "updated <=" in jql:
            return [
                make("GK-115", "Update menu pricing across pub chain",
                     "In Progress", "Charlie Brown", "Medium", 4, 3),

                make("GK-119", "Refactor loyalty points calculation",
                     "In Progress", "Diana Prince", "Medium", 6, 3)
            ]

        # ===== UNASSIGNED =====
        if "assignee is EMPTY" in jql:
            return [
                make("GK-130", "URGENT: Fix production bug in table ordering app",
                     "To Do", None, "Highest", 0, 3)
            ]

        return done_items

    # -----------------------------------------------------
    # CSV GENERATION (ADDS DONE ITEMS)
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
                    fields = issue["fields"]
                    writer.writerow([
                        name,
                        issue["key"],
                        fields["summary"][:60],
                        fields["status"]["name"],
                        fields["assignee"]["displayName"] if fields["assignee"] else "UNASSIGNED",
                        fields["priority"]["name"] if fields.get("priority") else "None",
                        fields.get("customfield_10024", 3),
                        fields["updated"][:10],
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
