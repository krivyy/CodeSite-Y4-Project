from pathlib import Path
import tempfile
import subprocess

def run_tests(problem_id, source_code):
    # Read the problem's test cases
    test_files = {
    1: "testadd.py",
    2: "testmultiply.py",
    3: "testlargest.py"
    }

    if problem_id not in test_files:
        return 0, 0, "Error"

    test_file = Path(__file__).parent / "problems" / test_files[problem_id]
    test_code = test_file.read_text(encoding="utf-8")

    # Combine the student's solution and tests
    combined_code = source_code + "\n\n" + test_code

    # Create a temporary folder for this submission
    with tempfile.TemporaryDirectory() as folder:
        test_path = Path(folder) / "test_submission.py"
        test_path.write_text(combined_code, encoding="utf-8")

        # Run the tests inside Docker
        command = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "128m",
            "--cpus", "0.5",
            "--pids-limit", "64",
            "--read-only",
            "--tmpfs", "/tmp",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "-v", f"{folder}:/runner:ro",
            "-w", "/runner",
            "codesite-runner",
            "python", "-B", "-m", "pytest",
            "-p", "no:cacheprovider",
            "-v", "test_submission.py"
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5
            )
            summary = ""
            for line in result.stdout.splitlines():
                if " in " in line and ("passed" in line or "failed" in line):
                    summary = line

            if not summary:
                return 0, 0, "Error"
            
            print("SUMMARY:", summary)
            split = summary.replace(",", "").split()
            print(split)
            print(result.stdout)
            print(result.stderr)
            if "passed" in split:
                passed = int(split[split.index("passed") - 1])
            else:
                passed = 0

            if "failed" in split:
                failed = int(split[split.index("failed") - 1])
            else:
                failed = 0

            return passed, failed, "Completed"

        except subprocess.TimeoutExpired:
            print("Time limit exceeded.")
            return 0, 0, "Time Limit Exceeded"

if __name__ == "__main__":
    solution = "def add(a, b):\n    if a == -2:\n        return 1\n    return a + b"
    # solution = "def add(a, b):\n    return a - b"
    results = run_tests(1, solution)
    print("Results returned:", results)