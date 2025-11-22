import os
import csv
import requests
import random
import json
import smtplib
import ssl
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class SprintHealthChecker:
    def __init__(self):
        # Load settings ONCE
        with open("settings.json", "r") as f:
            self.config = json.load(f)

        # Mode
        self.mode = self.config["mode"]

        # Jira settings
        self.jira_url = self.config["jira"]["url"]
        self.jira_email = self.config["jira"]["email"]
        self.jira_token = self.config["jira"]["token"]
        self.project_key = self.config["jira"]["project_key"]

        # Auth only for live mode
        self.auth = (self.jira_email, self.jira_token) if self.mode == "live" else None

        # NEW: Multi-channel alert configuration
        self.alerts_enabled = self.config["alerts"]["enabled"]
        self.destinations = self.config["alerts"].get("destinations", {})

    def run_query(self, jql):
        if self.mode == "mock":
            return self._mock_data(jql)

        # LIVE: Real API call
        url = f"{self.jira_url}/rest/api/3/search"
        params = {"jql": jql, "fields": "key,summary,status,assignee,priority,updated,issuelinks", "maxResults": 100}

        response = requests.get(url, params=params, auth=self.auth, timeout=30)
        response.raise_for_status()
        return response.json()["issues"]

    def _mock_data(self, jql):
        """GreeneKing mock data - single source of truth"""
        today = datetime.now()
        def make(key, summary, status, assignee, priority, days_ago, blockers=0):
            return {
                "key": key,
                "fields": {
                    "summary": summary,
                    "status": {"name": status},
                    "assignee": {"displayName": assignee} if assignee else None,
                    "priority": {"name": priority},
                    "updated": (today - timedelta(days=days_ago)).isoformat(),
                    "issuelinks": [{"type": {"outward": "blocks"}}] * blockers,
                    "customfield_10024": random.choice([1, 2, 3, 5])
                }
            }

        if "Blocked" in jql:
            return [
                make("GK-124", "POS integration blocked by payment gateway timeout", "Blocked", "Alice Smith", "Highest", 1, 2),
                make("GK-131", "Hotel booking API rate limited by external provider", "Blocked", "Bob Jones", "High", 0, 1),
            ]
        elif "updated <=" in jql:
            return [
                make("GK-115", "Update menu pricing across pub chain", "In Progress", "Charlie Brown", "Medium", 3),
                make("GK-119", "Refactor customer loyalty points calculation", "In Progress", "Diana Prince", "Medium", 5),
            ]
        elif "assignee is EMPTY" in jql:
            return [make("GK-130", "URGENT: Fix production bug in table ordering app", "To Do", None, "Highest", 0)]
        return [make("GK-125", "Implement staff rostering feature", "In Progress", "Eve Adams", "High", 0)]

    def generate_csv(self):
        """Generate the report"""
        Path("./reports").mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        csv_file = f"./reports/{self.mode.upper()}_sprint_health_{timestamp}.csv"

        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Query_Type", "Issue_Key", "Summary", "Status", "Assignee",
                "Priority", "Story_Points", "Last_Updated", "Alert_Level"
            ])

            queries = {
                "blockers": f'project = {self.project_key} AND sprint in openSprints() AND (labels = "blocked" OR status = "Blocked")',
                "stalled": f'project = {self.project_key} AND sprint in openSprints() AND status = "In Progress" AND updated <= -2d',
                "unassigned": f'project = {self.project_key} AND sprint in openSprints() AND assignee is EMPTY AND priority = High'
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
                        fields.get("customfield_10024", random.choice([2, 3, 5])),
                        fields["updated"][:10],
                        "CRITICAL" if name == "blockers" else "WARNING" if name == "stalled" else "HIGH"
                    ])

        return csv_file

    def _get_critical_issues(self, csv_file):
        """Helper: Extract critical issues from CSV"""
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                return [r for r in reader if r["Alert_Level"] == "CRITICAL"]
        except FileNotFoundError:
            print(f"❌ CSV file not found: {csv_file}")
            return []

    def send_alerts(self, csv_file):
        """Route alerts to all enabled destinations"""
        if not self.alerts_enabled:
            print("⚠️ Alerts are disabled globally")
            return

        if not self.destinations:
            print("⚠️ No alert destinations configured")
            return

        critical_issues = self._get_critical_issues(csv_file)
        
        if not critical_issues:
            print("✅ No critical alerts to send")
            return

        print(f"📊 Found {len(critical_issues)} critical issue(s), routing to enabled destinations...\n")

        for dest_type, config in self.destinations.items():
            if not config.get("enabled", False):
                continue

            try:
                if dest_type == "slack":
                    self._send_slack_alert(critical_issues, config)
                elif dest_type == "teams":
                    self._send_teams_alert(critical_issues, config)
                elif dest_type == "email":
                    self._send_email_alert(critical_issues, config)
                else:
                    print(f"⚠️ Unknown destination type: '{dest_type}'")
            except Exception as e:
                print(f"❌ Alert failed for {dest_type}: {str(e)}")

    def _send_slack_alert(self, issues, config):
        """Send alert to Slack webhook"""
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            print("⚠️ Slack: No webhook URL configured")
            return

        message = f"🔴 {len(issues)} Sprint Blockers Detected\n"
        for issue in issues:
            message += f"\n*Issue:* {issue['Issue_Key']}"
            message += f"\n*Summary:* {issue['Summary']}"
            message += f"\n*Assignee:* {issue['Assignee']}\n"

        response = requests.post(webhook_url, json={"text": message}, timeout=10)
        response.raise_for_status()
        print(f"📢 Slack alert sent: HTTP {response.status_code}")

    def _send_teams_alert(self, issues, config):
        """Send alert to Microsoft Teams webhook"""
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            print("⚠️ Teams: No webhook URL configured")
            return

        # Teams uses a slightly different payload format
        message = f"🔴 **{len(issues)} Sprint Blockers Detected**<br><br>"
        for issue in issues:
            message += f"**Issue:** {issue['Issue_Key']}<br>"
            message += f"**Summary:** {issue['Summary']}<br>"
            message += f"**Assignee:** {issue['Assignee']}<br><br>"

        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": "FF0000",
            "summary": f"{len(issues)} Sprint Blockers",
            "sections": [{
                "activityTitle": "Sprint Health Alert",
                "activitySubtitle": "Critical blockers require attention",
                "text": message
            }]
        }

        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"📢 Teams alert sent: HTTP {response.status_code}")

    def _send_email_alert(self, issues, config):
        """Send alert via SMTP email"""
        required_fields = ["smtp_server", "smtp_port", "username", "password", 
                          "from_address", "to_addresses"]
        
        missing = [f for f in required_fields if not config.get(f)]
        if missing:
            print(f"⚠️ Email: Missing required fields: {', '.join(missing)}")
            return

        # Build email message
        subject = f"{config.get('subject_prefix', '[SPRINT ALERT]')} {len(issues)} Critical Blocker(s) Detected"
        
        # Plain text body
        body = f"""
Sprint Health Alert
===================

🔴 {len(issues)} CRITICAL BLOCKER(S) DETECTED

Details:
--------
"""
        for issue in issues:
            body += f"\nIssue: {issue['Issue_Key']}"
            body += f"\nSummary: {issue['Summary']}"
            body += f"\nAssignee: {issue['Assignee']}"
            body += f"\nPriority: {issue['Priority']}"
            body += f"\nLast Updated: {issue['Last_Updated']}\n"

        # Create message
        msg = MIMEMultipart()
        msg['From'] = config["from_address"]
        msg['To'] = ', '.join(config["to_addresses"])
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Send email
        context = ssl.create_default_context()
        with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
            server.starttls(context=context)
            server.login(config["username"], config["password"])
            server.send_message(msg)

        to_list = ', '.join(config["to_addresses"])
        print(f"📧 Email alert sent to: {to_list}")

def analyse_csv(csv_file):
    with open(csv_file, 'r') as f:
        rows = list(csv.DictReader(f))

    insights = []

    # 1. BLOCKERS
    blockers = [r for r in rows if r["Alert_Level"] == "CRITICAL"]
    if blockers:
        insights.append(f"🔴 There are {len(blockers)} active BLOCKERS. Sprint is at risk.")
        for b in blockers:
            insights.append(f"   • {b['Issue_Key']} ({b['Assignee']}) — {b['Summary']}")

    # 2. STALLED
    stalled = [r for r in rows if r["Alert_Level"] == "WARNING"]
    if stalled:
        insights.append(f"\n⚠️ {len(stalled)} items stalled (no progress for 2+ days):")
        for s in stalled:
            insights.append(f"   • {s['Issue_Key']} — {s['Assignee']} hasn't updated since {s['Last_Updated']}")

    # 3. HIGH PRIORITY UNASSIGNED
    unassigned = [r for r in rows if r["Alert_Level"] == "HIGH" and r["Assignee"] == "UNASSIGNED"]
    if unassigned:
        insights.append("\n❗ High priority items with NO ASSIGNEE:")
        for u in unassigned:
            insights.append(f"   • {u['Issue_Key']} — {u['Summary']} (needs assignment TODAY)")
        insights.append("👉 Suggestion: Drop a low-priority item and assign this ASAP.")

    # 4. WORKLOAD ANALYSIS
    workload = {}
    for r in rows:
        person = r["Assignee"]
        sp = int(r["Story_Points"]) if r["Story_Points"].isdigit() else 0
        workload[person] = workload.get(person, 0) + sp

    overloaded = [p for p, total in workload.items() if total >= 13 and p != "UNASSIGNED"]
    if overloaded:
        insights.append("\n📈 Potential overload:")
        for p in overloaded:
            insights.append(f"   • {p} has {workload[p]} story points.")

    if not insights:
        insights.append("✅ Sprint looks healthy. No major risks identified.")

    return "\n".join(insights)

if __name__ == "__main__":
    checker = SprintHealthChecker()
    csv_file = checker.generate_csv()

    # Daily AI Analysis
    analysis = analyse_csv(csv_file)
    print("\n📊 DAILY AI ANALYSIS:")
    print(analysis)
    print("\n" + "="*60 + "\n")

    # Multi-channel alerting
    checker.send_alerts(csv_file)