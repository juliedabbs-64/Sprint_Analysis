📊 Sprint Health Checker

A lightweight, portable tool that scans Jira sprints, identifies blockers, and automatically notifies your team (via Slack or other channels you add later). Designed for Engineering Managers, Team Leads, and Scrum Masters to prepare for daily stand-ups.

🚀 Features

Mock Mode — No Jira token needed. Generates realistic GreeneKing-style issues for testing.

Live Mode — Connects directly to Jira Cloud using API token.

CSV Reporting — Outputs a timestamped sprint health report.

Critical Alert Detection — Detects real sprint blockers using JQL and sends an alert.

Slack Notifications — Posts a summary of critical issues to a configured Slack channel.

Portable Configuration — Uses settings.json for Jira and alert settings (ignored in Git to protect secrets).

📁 Repository Structure
sprint_checker/
│
├── sprint_checker.py          # Main execution script
├── settings.example.json      # Template without secrets
├── settings.json              # Your real config (ignored in Git)
├── reports/                   # Generated CSV files
├── README.md                  # Project documentation
└── .gitignore                 # Ensures secrets/reports aren’t committed

⚙️ Setup Instructions
1️⃣ Install dependencies

This script only needs the requests library:

pip install requests

2️⃣ Create your settings file

Copy the template:

cp settings.example.json settings.json


Edit settings.json to include:

Jira Cloud URL

Jira email

Jira API token

Project key

Slack webhook URL

This file contains secrets — do not commit it.

🧪 Running the Script
🔹 Mock mode (no Jira token required)
python sprint_checker.py

🔹 Live mode (connect to Jira Cloud)
python sprint_checker.py live


Output:

A CSV file in ./reports/

A Slack alert only if critical blockers are found

📉 Generated CSV Format

The CSV includes:

Query_Type (blockers/stalled/unassigned)

Issue_Key

Summary

Status

Assignee

Priority

Story Points

Last Updated

Alert_Level (CRITICAL / WARNING / HIGH)

🔔 Slack Alerts

If the script finds CRITICAL issues (blockers), it sends a Slack message:

🔴 2 Sprint Blockers Detected
Issue: GK-124
Summary: ...
Assignee: ...
Issue: GK-131
Summary: ...
Assignee: ...


More alert channels (Teams, Email) can be added later.

🛡 Security Notes

settings.json must NOT be committed — it contains sensitive tokens.

Only commit settings.example.json with placeholder values.

Jira tokens should be stored securely (environment variables recommended for production).

🧭 Roadmap

Planned enhancements:

⚠️ Slack: Add WARNING/HIGH alerts

💬 Teams integration (Adaptive Cards)

📧 Email escalation for critical blockers

👤 Assignee direct notifications

👥 Team lead escalation logic

⏰ Scheduled daily run (cron / Power Automate)

🤝 Contributing

Pull requests are welcome.
For major changes, please open an issue first to discuss what you'd like to change.