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

    # Runner connection
    runner_url = os.environ["RUNNER_URL"].rstrip("/")
    runner_token = os.environ["RUNNER_TOKEN"]

    try:
        response = requests.post(
            f"{runner_url}/run",
            headers={"X-Runner-Token": runner_token},
            json={"code": combined_code},
            timeout=30
        )

        response.raise_for_status()
        result = response.json()

    except (requests.RequestException, ValueError):
        return 0, 0, "Error"

    # Check the runner's result
    status = result.get("status")

    if status == "time_limit":
        return 0, 0, "Time Limit Exceeded"

    if status != "ok" or result.get("exit_code") != 0:
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