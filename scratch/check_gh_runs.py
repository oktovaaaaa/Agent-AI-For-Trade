import urllib.request
import json

url = "https://api.github.com/repos/oktovaaaaa/Agent-AI-For-Trade/actions/runs?per_page=20"
req = urllib.request.Request(url, headers={"User-Agent": "Python"})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())

print("Runs:")
for r in data.get("workflow_runs", []):
    print(f"Run #{r.get('run_number')}: conclusion={r.get('conclusion')}, event={r.get('event')}, created_at={r.get('created_at')}, id={r.get('id')}")

# For failed runs, check jobs
for r in data.get("workflow_runs", []):
    if r.get("conclusion") == "failure":
        run_id = r.get("id")
        jobs_url = f"https://api.github.com/repos/oktovaaaaa/Agent-AI-For-Trade/actions/runs/{run_id}/jobs"
        req_jobs = urllib.request.Request(jobs_url, headers={"User-Agent": "Python"})
        try:
            with urllib.request.urlopen(req_jobs) as jresp:
                jdata = json.loads(jresp.read().decode())
                print(f"\n--- Jobs for Run #{r.get('run_number')} ({run_id}) ---")
                for job in jdata.get("jobs", []):
                    print(f"Job: {job.get('name')}, conclusion={job.get('conclusion')}")
                    for step in job.get("steps", []):
                        if step.get("conclusion") == "failure":
                            print(f"  FAILED STEP: {step.get('name')}, conclusion={step.get('conclusion')}")
        except Exception as e:
            print(f"Error fetching jobs for {run_id}: {e}")
        break

