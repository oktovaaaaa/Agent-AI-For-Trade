import urllib.request
import json

# Check job details for Run #75 (id 42191437501)
run_id = 42191437501
jobs_url = f"https://api.github.com/repos/oktovaaaaa/Agent-AI-For-Trade/actions/runs/{run_id}/jobs"
req = urllib.request.Request(jobs_url, headers={"User-Agent": "Python"})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())

for job in data.get("jobs", []):
    print(f"Job: {job.get('name')}")
    for step in job.get("steps", []):
        print(f"  Step: {step.get('name')} | Status: {step.get('status')} | Conclusion: {step.get('conclusion')}")


