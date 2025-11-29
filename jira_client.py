import requests
import pandas as pd
from datetime import datetime

def fetch_jira_dataframe(settings):
    """
    Fetches Jira sprint issues and normalises into the same DataFrame schema
    as your mock CSV files.
    """

    jira_cfg = settings["jira"]
    url = jira_cfg["url"]
    email = jira_cfg["email"]
    token = jira_cfg["token"]
    project_key = jira_cfg["project_key"]
    story_field = jira_cfg.get("story_points_field", "customfield_10016")

    auth = (email, token)

    # -------------------------------------------------------
    # 1. Detect active sprint (if sprint_id = "auto")
    # -------------------------------------------------------
    sprint_id = jira_cfg.get("sprint_id", "auto")
    board_id = jira_cfg.get("board_id")

    if sprint_id == "auto":
        sprint_id = get_active_sprint_id(url, auth, board_id)

    # -------------------------------------------------------
    # 2. Query Jira Search API for issues in this sprint
    # -------------------------------------------------------
    search_url = f"{url}/rest/api/3/search"

    jql = f"sprint = {sprint_id} AND project = {project_key}"

    params = {
        "jql": jql,
        "maxResults": 1000,
        "fields": "summary,status,assignee,priority,updated," + story_field
    }

    response = requests.get(search_url, params=params, auth=auth)
    response.raise_for_status()
    data = response.json()

    issues = data.get("issues", [])

    rows = []

    for item in issues:
        key = item["key"]
        fields = item["fields"]

        summary = fields.get("summary", "")
        status = fields.get("status", {}).get("name", "")
        priority = fields.get("priority", {}).get("name", "")
        assignee = fields.get("assignee", {}).get("displayName", "UNASSIGNED")
        updated = fields.get("updated", "")

        # Story points field (can be missing)
        sp = fields.get(story_field, 0)
        if sp is None:
            sp = 0

        # Determine Query_Type (Blocked / stalled / etc)
        # For now: placeholder (your existing logic downstream handles this)
        query_type = "unknown"

        rows.append({
            "Query_Type": query_type,
            "Issue_Key": key,
            "Summary": summary,
            "Status": status,
            "Assignee": assignee,
            "Priority": priority,
            "Story_Points": sp,
            "Last_Updated": updated,
            "Alert_Level": ""
        })

    df = pd.DataFrame(rows)

    # Convert updated field
    if not df.empty:
        df["Last_Updated"] = pd.to_datetime(df["Last_Updated"], errors="coerce")

    return df


def get_active_sprint_id(base_url, auth, board_id):
    """Detect active sprint from Jira Agile API."""
    url = f"{base_url}/rest/agile/1.0/board/{board_id}/sprint"
    params = {"state": "active"}

    resp = requests.get(url, params=params, auth=auth)
    resp.raise_for_status()

    data = resp.json()
    sprints = data.get("values", [])

    if not sprints:
        raise Exception("No active sprint found for this board.")

    return sprints[0]["id"]
