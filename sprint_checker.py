import os
import csv
import requests
import random
import json
from datetime import datetime, timedelta
from pathlib import Path

class SprintHealthChecker:
    def __init__(self):
        # Load settings ONCE
        with open("settings.json", "r") as f:
            self.config = json.load(f)
        
        self.mode = self.config["mode"]
        self.jira_cfg = self.config["jira"]
        
        self.jira_url = self.jira_cfg["url"]
        self.jira_email = self.jira_cfg["email"]
        self.jira_token = self.jira_cfg["token"]
        self.project_key = self.jira_cfg["project_key"]
        
        # Auth only for live mode
        self.auth = (self.jira_email, self.jira_token) if self.mode == "live" else None
    
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
            # Return BOTH critical issues
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
            writer.writerow(["Query_Type", "Issue_Key", "Summary", "Status", "Assignee", "Priority", "Story_Points", "Last_Updated", "Alert_Level"])
            
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
                        name, issue["key"], fields["summary"][:60], fields["status"]["name"],
                        fields["assignee"]["displayName"] if fields["assignee"] else "UNASSIGNED",
                        fields["priority"]["name"] if fields.get("priority") else "None",
                        fields.get("customfield_10024", random.choice([2, 3, 5])),
                        fields["updated"][:10],
                        "CRITICAL" if name == "blockers" else "WARNING" if name == "stalled" else "HIGH"
                    ])
        
        return csv_file

# ============================================
# STANDALONE FUNCTION (NOT in the class)
# ============================================
def send_slack_alert(csv_file, webhook_url):
    """Send critical alerts to Slack"""
    if not webhook_url:
        print("⚠️ No webhook URL set, skipping alerts")
        return
    
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        critical = [r for r in reader if r["Alert_Level"] == "CRITICAL"]
    
    if not critical:
        print("✅ No critical alerts to send")
        return
    
    message = f"🔴 {len(critical)} Sprint Blockers Detected\n"
    for issue in critical:
        message += f"\n*Issue:* {issue['Issue_Key']}"
        message += f"\n*Summary:* {issue['Summary']}"
        message += f"\n*Assignee:* {issue['Assignee']}\n"
    
    try:
        payload = {"text": message}
        response = requests.post(webhook_url, json=payload, timeout=10)
        print(f"📢 Alert sent to Slack: {response.status_code}")
    except Exception as e:
        print(f"❌ Alert failed: {str(e)}")

# ============================================
# MAIN EXECUTION (NOT in the class)
# ============================================
if __name__ == "__main__":
    # === CONFIG ===
    SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"
    
    # === RUN ===
    checker = SprintHealthChecker()  # ✅ NO mode parameter here
    csv_file = checker.generate_csv()
    
    # === ALERT ===
    send_slack_alert(csv_file, SLACK_WEBHOOK_URL)