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
runtime_error = False

for name, function in list(globals().items()):
    if name.startswith("test_") and callable(function):
        try:
            function()
            passed += 1
        except AssertionError:
            failed += 1
        except Exception:
            runtime_error = True
            break

if runtime_error:
    print("CODESITE_RESULT:0:0:RUNTIME_ERROR")
else:
    print(f"CODESITE_RESULT:{passed}:{failed}:COMPLETED")
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
        "source_code": combined_code,
        "cpu_time_limit": 2,
        "wall_time_limit": 5,
        "memory_limit": 128000
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
            parts = line.split(":")

            if parts[3] == "RUNTIME_ERROR":
                return 0, 0, "Runtime Error"

            if parts[3] == "COMPLETED":
                return int(parts[1]), int(parts[2]), "Completed"

    return 0, 0, "Error"