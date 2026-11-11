"""
CodeSite runner service.

Runs Python code in a locked-down, throw-away Docker container and returns
what it printed
"""

import hmac
import os
import subprocess
import threading
import uuid

from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 128 * 1024

RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
IMAGE = os.environ.get("SANDBOX_IMAGE", "python:3.12-slim")

TIME_LIMIT = 6                    # seconds the container may run
MAX_OUTPUT_BYTES = 64 * 1024      # stop (and kill) if it prints more than this
OOM_EXIT_CODE = 137               # exit code when the kernel kills it for using too much memory

# Only 3 containers may run at the same time
slots = threading.BoundedSemaphore(3)


def docker_command(container_name):
    return [
        "docker", "run",
        "--rm",                                  # delete the container when it stops
        "-i",                                    # the code is sent in on stdin
        "--name", container_name,
        "--network", "none",                     # no internet or network access
        "--memory", "128m",
        "--memory-swap", "128m",                 # no swap
        "--cpus", "0.5",
        "--pids-limit", "64",                    # stops fork bombs
        "--read-only",                           # can't change the filesystem
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "--cap-drop", "ALL",                     # no Linux capabilities
        "--security-opt", "no-new-privileges",
        "--user", "65534:65534",                 # run as "nobody", not root
        IMAGE,
        "python", "-I", "-B", "-",               # run the program read from stdin
    ]


def kill_container(container_name):
    try:
        subprocess.run(["docker", "rm", "-f", container_name],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except subprocess.TimeoutExpired:
        pass


def run_in_sandbox(code):
    container_name = f"codesite-{uuid.uuid4().hex[:16]}"
    process = subprocess.Popen(
        docker_command(container_name),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    output = bytearray()
    too_much_output = threading.Event()

    def read_output():
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                break
            if too_much_output.is_set():
                continue
            if len(output) + len(chunk) > MAX_OUTPUT_BYTES:
                too_much_output.set()
                threading.Thread(target=kill_container, args=(container_name,), daemon=True).start()
                continue
            output.extend(chunk)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()

    try:
        process.stdin.write(code.encode("utf-8"))
        process.stdin.close()
    except BrokenPipeError:
        pass

    timed_out = False
    try:
        process.wait(timeout=TIME_LIMIT)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_container(container_name)
        process.kill()
        process.wait()

    reader.join(timeout=5)

    if too_much_output.is_set():
        return {"status": "output_limit"}
    if timed_out:
        return {"status": "time_limit"}
    if process.returncode == OOM_EXIT_CODE:
        return {"status": "memory_limit"}
    if process.returncode == 125:
        return {"status": "error"}   # If Docker fails to start a container

    return {
        "status": "ok",
        "exit_code": process.returncode,
        "stdout": output.decode("utf-8", "replace"),
    }


@app.get("/health")
def health():
    return jsonify(ok=True)


@app.post("/run")
def run():
    sent_token = request.headers.get("X-Runner-Token", "")
    if not RUNNER_TOKEN or not hmac.compare_digest(sent_token, RUNNER_TOKEN):
        return jsonify(error="Unauthorised"), 401

    data = request.get_json(silent=True) or {}
    code = data.get("code")
    if not isinstance(code, str) or not code.strip():
        return jsonify(error="No code sent."), 400

    with slots:
        return jsonify(run_in_sandbox(code))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
