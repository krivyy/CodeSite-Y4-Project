# CodeSite runner
 
This folder is the part of CodeSite that actually runs students' code. In Iteration 1 I used
Judge0 for this, but after feedback I replaced it with my own runner so I'm the one
executing and configuring everything.
 
The website ("app.py") is hosted on Railway, but Railway doesn't let a normal service start
Docker containers. That's why I switched to Judge0 in the first place. To get around it, the
runner lives on its own machine, a **Railway sandbox**, and the website sends it code over
Railway's **private network**.
 
```
Browser ─▶ app.py (Railway) ─▶ run.py ──HTTP + X-Runner-Token──▶ runner.py (sandbox) ─▶ docker run python:3.12-slim
                                  ▲                                                              │
                                  └──────────────── stdout ({"status": "ok", ...}) ◀──────────────┘
```
 
1. "run.py" joins the student's code, the test file and a small harness into one Python program.
2. It sends that program to the runner along with my secret token.
3. The runner starts a brand new, locked-down container, runs the program and sends back what it printed.
4. "run.py" reads the "CODESITE_RESULT:<passed>:<failed>:<status>" line and returns the score to "app.py".

## Files
 
| File | What it does |
|---|---|
| "runner.py" | The runner itself (Flask). Checks the token, limits how many run at once, starts the container, enforces limits |
| "requirements.txt" | Flask and gunicorn |
| "setup-runner.sh" | Installs and starts everything on a new sandbox |
 
## Security
 
The runner executes code written by anyone with an account, so I locked it down in layers:
 
| Layer | Protection |
|---|---|
| Network | The runner has no public address. Only services on my Railway project's private network can reach it |
| Token | Every request needs the "X-Runner-Token" header, anything else gets a "401". I compare with "hmac.compare_digest" instead of "==" so timing doesn't leak anything |
| Container | "--network none", 128 MB memory and no swap, 0.5 CPU, "--pids-limit 64", "--read-only", "--cap-drop ALL", "no-new-privileges", runs as "nobody" |
| Time | 6 second limit, then the container is removed with "docker rm -f". I found in testing that killing "docker run" alone leaves the container running |
| Output | Capped at 64 KB. The runner keeps reading and throwing away output after the cap, otherwise the pipe fills up and Docker can't stop the container (another bug I found in testing) |
| Load | At most 3 containers at once, the rest wait their turn |
| Secrets | The container's environment only has "HOME", "HOSTNAME" and "PATH" |
 
I tested it with deliberately bad submissions (infinite loop, fork bomb, memory bomb,
internet access, writing files, huge output, reading environment variables, wrong token)
and every one was contained.
 
## Environment variables
 
| Where | Variable | Value |
|---|---|---|
| Sandbox | "RUNNER_TOKEN" | Pasted in when "setup-runner.sh" runs, and passed straight to the runner |
| Railway (CodeSite-Y4-Project) | "RUNNER_URL" | "http://[<sandbox fd12 address>]:8000", printed by "setup-runner.sh" |
| Railway (CodeSite-Y4-Project) | "RUNNER_TOKEN" | The same token |
 
I make a token on Windows with:
 
```powershell
py -c "import secrets; print(secrets.token_urlsafe(32))"
```
 
**Never commit the token.** 
 
---
 
## Deploying
 
**1. Create the sandbox and connect** (PowerShell on my laptop):
 
```powershell
railway.cmd sandbox create --private-network --idle-timeout-minutes 0; Start-Sleep 30; railway.cmd sandbox ssh
```
 
"--idle-timeout-minutes 0" stops the sandbox deleting itself when it's idle.
 
**2. Install and start the runner** (inside the sandbox, which is Linux):
 
```bash
git clone -q -b railway-launch https://github.com/krivyy/CodeSite-Y4-Project.git /opt/codesite && bash /opt/codesite/runcode/setup-runner.sh
```
 
It asks for the token. Nothing shows on screen while pasting, that's on purpose. At the end
you should see:

```
{"exit_code":0,"status":"ok","stdout":"2\n"}
RUNNER_URL=http://[fd12:....]:8000
```
 
**3. Connect the website:** in the Railway dashboard, under **CodeSite-Y4-Project → Variables**,
set "RUNNER_URL" to the printed value. Every new sandbox gets a new address, so this changes
each time. Railway redeploys automatically.
 
**4. Test on the live site:** a correct solution should give "Accepted! 3/3 tests passed.",
and "while True: pass" should give "Time Limit Exceeded."
 
## Removing the sandbox
 
```powershell
railway.cmd sandbox destroy
```
 
This deletes the sandbox. A new one can be set up any time with the steps above.
 
---
 
## Running locally (Windows, Docker Desktop)
 
**Window 1, the runner:**
 
```powershell
docker pull python:3.12-slim
py -m pip install -r runcode/requirements.txt
$env:RUNNER_TOKEN = "dev-token"
py runcode/runner.py
```
 
**Window 2, the website** (plus the usual "SECRET_KEY" and "MYSQL..." variables):
 
```powershell
$env:RUNNER_URL = "http://127.0.0.1:8000"
$env:RUNNER_TOKEN = "dev-token"
py app.py
```
 
To test the runner without the website (window 2):
 
```powershell
py -c "from run import run_tests; print(run_tests(1, 'def add(a, b):\n    return a + b'))"
```
 
This should print "(3, 0, 'Completed')".

## Checking the website can reach the runner

Connect with "railway.cmd ssh --service CodeSite-Y4-Project", then run this (Linux).
It should print b'{"ok":true}\n'.
 
```bash
/app/.venv/bin/python -c 'import urllib.request; print(urllib.request.urlopen("http://[<address>]:8000/health", timeout=5).read())'
```
