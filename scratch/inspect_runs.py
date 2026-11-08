import urllib.request
import json

token = "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"
url = "https://api.github.com/repos/oktovaaaaa/Agent-AI-For-Trade/actions/runs?per_page=50"
req = urllib.request.Request(url, headers={
    "User-Agent": "Python",
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json"
})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())

for r in data.get("workflow_runs", []):
    created = r.get("created_at")
    if "2026-11-05" in created or "2026-11-04" in created:
        print(f"Run #{r.get('run_number')} ({r.get('name')}): event={r.get('event')}, conclusion={r.get('conclusion')}, created_at={r.get('created_at')}, updated_at={r.get('updated_at')}")
