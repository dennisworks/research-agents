"""Deterministic coverage for scripts/manual-poll.sh.

The script shells out to curl/flock/docker; here we stub all three with fake
executables on PATH (no network, no real docker, no real lock), copy the script
into a sandbox repo layout, and assert the control flow: agent-control
registration, worker exit-code propagation, log routing, and the guarantee that
the console can never block the actual run.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manual-poll.sh"

FAKE_CURL = """#!/bin/sh
echo "CURL $*" >> "$CURL_CALLS"
url=""
for a in "$@"; do url="$a"; done
case "$url" in
  */api/research/prompt/manual) printf '%s' "${PENDING_STATUS:-200}" ;;
  */runs/external) printf '{"run_id":"testrid","log_path":"%s"}' "$AC_LOG" ;;
  *) : ;;
esac
"""

FAKE_FLOCK = "#!/bin/sh\nexit 0\n"

FAKE_DOCKER = """#!/bin/sh
echo "DOCKER $*" >> "$DOCKER_CALLS"
echo "worker output line"
exit "${DOCKER_EXIT:-0}"
"""


def _sandbox(tmp_path: Path, *, agent_control: bool) -> dict:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "scripts" / "manual-poll.sh").write_text(SCRIPT.read_text())

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("curl", FAKE_CURL), ("flock", FAKE_FLOCK), ("docker", FAKE_DOCKER)):
        p = bin_dir / name
        p.write_text(body)
        p.chmod(0o755)

    env_lines = ["PUBLISH_URL=http://stub", "PUBLISH_TOKEN=x"]
    if agent_control:
        env_lines += ["AGENT_CONTROL_URL=http://console", "AGENT_CONTROL_TOKEN=t"]
    (tmp_path / ".env").write_text("\n".join(env_lines) + "\n")

    return {
        "curl_calls": tmp_path / "curl_calls.txt",
        "docker_calls": tmp_path / "docker_calls.txt",
        "ac_log": tmp_path / "console.log",
        "bin": bin_dir,
        "script": tmp_path / "scripts" / "manual-poll.sh",
    }


def _run(paths: dict, **extra_env) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = f"{paths['bin']}{os.pathsep}{env['PATH']}"
    env["CURL_CALLS"] = str(paths["curl_calls"])
    env["DOCKER_CALLS"] = str(paths["docker_calls"])
    env["AC_LOG"] = str(paths["ac_log"])
    env.update(extra_env)
    return subprocess.run(
        ["sh", str(paths["script"])],
        env=env,
        capture_output=True,
        text=True,
    )


def _calls(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def test_success_registers_and_finalizes(tmp_path):
    paths = _sandbox(tmp_path, agent_control=True)
    r = _run(paths, DOCKER_EXIT="0")

    assert r.returncode == 0
    curl = _calls(paths["curl_calls"])
    assert "/runs/external" in curl  # start registered
    assert "/runs/external/testrid/finish" in curl  # finalized
    assert '"status":"success"' in curl and '"exit_code":0' in curl
    assert "worker output line" in paths["ac_log"].read_text()  # routed to console log
    assert "success" in r.stdout


def test_failure_propagates_exit_and_dumps_log(tmp_path):
    paths = _sandbox(tmp_path, agent_control=True)
    r = _run(paths, DOCKER_EXIT="1")

    assert r.returncode == 1  # worker exit code propagates
    curl = _calls(paths["curl_calls"])
    assert '"status":"failed"' in curl and '"exit_code":1' in curl
    assert "FAILED" in r.stdout
    assert "worker output line" in r.stdout  # full output surfaced to cron log


def test_no_agent_control_still_runs(tmp_path):
    paths = _sandbox(tmp_path, agent_control=False)
    r = _run(paths, DOCKER_EXIT="0")

    assert r.returncode == 0
    assert "/runs/external" not in _calls(paths["curl_calls"])  # registration skipped
    assert _calls(paths["docker_calls"])  # worker still ran


def test_unwritable_console_path_never_blocks_worker(tmp_path):
    # The console hands back a log_path we can't write to; the worker must still
    # run (and the run still finalizes) rather than being blocked by it.
    paths = _sandbox(tmp_path, agent_control=True)
    paths["ac_log"] = Path("/no/such/dir/console.log")
    r = _run(paths, DOCKER_EXIT="0")

    assert r.returncode == 0
    assert _calls(paths["docker_calls"])  # worker ran despite the bad path
    assert "/runs/external/testrid/finish" in _calls(paths["curl_calls"])
