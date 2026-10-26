import os
from pathlib import Path
import requests


def run_tests(problem_id, source_code):

    test_files = {
        1: "testadd.py",
        2: "testmultiply.py",
        3: "testlargest.py"
    }

    if problem_id not in test_files:
        return 0, 0, "Error"

    test_path = Path(__file__).parent / "problems" / test_files[problem_id]
    test_code = test_path.read_text(encoding="utf-8")

    # Combine the student's code and tests
    combined_code = source_code + "\n\n" + test_code + """

passed = 0
failed = 0

for name, function in list(globals().items()):
    if name.startswith("test_") and callable(function):
        try:
            function()
            passed += 1
        except Exception:
            failed += 1

print(f"CODESITE_RESULT:{passed}:{failed}")
"""

    # Judge0 connection
    api_url = os.environ["JUDGE0_API_URL"].rstrip("/")
    api_host = os.environ["JUDGE0_API_HOST"]
    api_key = os.environ["JUDGE0_API_KEY"]

    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": api_host,
        "Content-Type": "application/json"
    }

    payload = {
        "language_id": 100,
        "source_code": combined_code
    }

    try:
        response = requests.post(
            f"{api_url}/submissions",
            headers=headers,
            json=payload,
            params={
                "base64_encoded": "false",
                "wait": "true"
            },
            timeout=30
        )

        response.raise_for_status()
        result = response.json()

    except requests.RequestException:
        return 0, 0, "Error"

    # Check Judge0 result
    status = result.get("status", {}).get("description")

    if status == "Time Limit Exceeded":
        return 0, 0, "Time Limit Exceeded"

    if status != "Accepted":
        return 0, 0, "Runtime Error"

    # Read passed and failed tests
    output = result.get("stdout") or ""

    for line in output.splitlines():
        if line.startswith("CODESITE_RESULT:"):
            _, passed, failed = line.split(":")
            return int(passed), int(failed), "Completed"

    return 0, 0, "Error"