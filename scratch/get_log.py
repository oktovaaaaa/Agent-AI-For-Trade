import urllib.request
import zipfile
import io

token = "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"
run_id = 42191437501  # Run #75

logs_url = f"https://api.github.com/repos/oktovaaaaa/Agent-AI-For-Trade/actions/runs/{run_id}/logs"
req = urllib.request.Request(logs_url, headers={
    "User-Agent": "Python",
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json"
})

try:
    with urllib.request.urlopen(req) as resp:
        content = resp.read()
        z = zipfile.ZipFile(io.BytesIO(content))
        for name in z.namelist():
            if "Commit" in name or "Push" in name:
                print("=== LOG:", name, "===")
                print(z.read(name).decode("utf-8", errors="replace"))
            elif "Pemantauan" in name:
                lines = z.read(name).decode("utf-8", errors="replace").splitlines()
                print("=== LAST 40 LINES OF", name, "===")
                print("\n".join(lines[-40:]))
except Exception as e:
    print("Error:", e)
