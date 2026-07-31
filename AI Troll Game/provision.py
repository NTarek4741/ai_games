"""Dedalus Machine lifecycle for the troll's AI brain.

Creates a fresh Dedalus Machine, deploys server_setup/, executes setup.sh,
and exposes an HTTPS preview URL.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import tarfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from dedalus_sdk import Dedalus

from agent import load_api_key

_HERE = Path(__file__).resolve().parent
SERVER_DIR = _HERE / "server_setup"
APP_DIR = "/home/machine/troll_app"
PORT = 8000

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "expired"}
DEAD_PHASES = {"destroyed", "failed"}
POLL_INTERVAL_S = 2
HEARTBEAT_SECONDS = 20
_BUNDLE_EXCLUDE = {"__pycache__", ".DS_Store"}
RETRYABLE_ERROR_CODES = {"execution_runner_interrupted", "exec_frame_read_timeout"}


@dataclass(frozen=True)
class MachineSpec:
    name: str = "troll"
    vcpu: int = 1
    memory_mib: int = 1024
    storage_gib: int = 2
    autosleep: str = "30m"
    create_timeout_s: int = 300
    setup_timeout_ms: int = 600_000


@dataclass
class MachineHandle:
    machine_id: str
    base_url: str
    client: Dedalus
    api_key: str
    reused: bool = False


TROLL_SPEC = MachineSpec()


def _phase(m) -> str:
    """Return a machine's lifecycle phase string."""
    return getattr(getattr(m, "status", None), "phase", "unknown")


def run_command(
    client: Dedalus,
    machine_id: str,
    command: list[str],
    *,
    timeout_ms: int = 600_000,
    retries: int = 3,
    stdin: str | None = None,
    stream: bool = False,
    log: Callable[[str], None] = print,
) -> tuple[str, str]:
    """Run a command on the remote machine and wait for completion."""
    for attempt in range(retries + 1):
        kwargs: dict = {
            "machine_id": machine_id,
            "command": command,
            "timeout_ms": timeout_ms,
        }
        if stdin is not None:
            kwargs["stdin"] = stdin
        exc = client.machines.executions.create(**kwargs)

        started_at = time.time()
        last_progress = started_at
        while exc.status not in TERMINAL_STATUSES:
            wait = (
                (exc.retry_after_ms or 0) / 1000
                if exc.status == "wake_in_progress"
                else POLL_INTERVAL_S
            )
            time.sleep(wait)
            exc = client.machines.executions.retrieve(
                machine_id=machine_id, execution_id=exc.execution_id
            )
            if stream and time.time() - last_progress >= HEARTBEAT_SECONDS:
                elapsed = int(time.time() - started_at)
                log(f"    ... still running ({elapsed}s elapsed)")
                last_progress = time.time()

        out = client.machines.executions.output(
            machine_id=machine_id, execution_id=exc.execution_id
        )
        stdout, stderr = out.stdout or "", out.stderr or ""
        if exc.status == "succeeded":
            return stdout, stderr
        if exc.error_code in RETRYABLE_ERROR_CODES and attempt < retries:
            delay = 10 * (attempt + 1)
            log(f"Transient failure ({exc.error_code}) - retrying in {delay}s...")
            time.sleep(delay)
            continue
        raise RuntimeError(
            f"Command failed on {machine_id}: {exc.status} "
            f"{exc.error_code}: {exc.error_message}\n{stderr[:2000]}"
        )
    raise RuntimeError("Unreachable")


def _build_bundle() -> tuple[bytes, str]:
    """Tar+gzip server_setup/ folder; return (bytes, sha256)."""
    entries: dict[str, bytes] = {}
    for path in sorted(SERVER_DIR.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(SERVER_DIR)
        if any(part in _BUNDLE_EXCLUDE for part in rel.parts):
            continue
        entries[rel.as_posix()] = path.read_bytes()

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for arcname in sorted(entries):
            data = entries[arcname]
            info = tarfile.TarInfo(name=arcname)
            info.size = len(data)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if arcname.endswith(".sh") else 0o644
            tar.addfile(info, io.BytesIO(data))
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(raw.getvalue())
    bundle = buf.getvalue()
    return bundle, hashlib.sha256(bundle).hexdigest()


def _upload_bytes(
    client: Dedalus,
    machine_id: str,
    data: bytes,
    remote: str,
    log: Callable[[str], None],
) -> None:
    encoded = base64.b64encode(data).decode("ascii")
    run_command(
        client,
        machine_id,
        ["/bin/bash", "-c", f"base64 -d > {remote}"],
        stdin=encoded,
        timeout_ms=120_000,
        log=log,
    )


def _deploy_and_setup(
    client: Dedalus,
    machine_id: str,
    spec: MachineSpec,
    api_key: str,
    *,
    log: Callable[[str], None],
) -> str:
    bundle, sha = _build_bundle()
    log(f"Deploying server bundle ({len(bundle)} bytes) to {APP_DIR}...")
    run_command(
        client,
        machine_id,
        ["/bin/bash", "-c", f"mkdir -p {APP_DIR}"],
        timeout_ms=10_000,
        log=log,
    )
    _upload_bytes(client, machine_id, bundle, f"{APP_DIR}/bundle.tgz", log)
    run_command(
        client,
        machine_id,
        [
            "/bin/bash",
            "-c",
            (
                f"tar -xzf {APP_DIR}/bundle.tgz -C {APP_DIR} && rm {APP_DIR}/bundle.tgz "
                f"&& chmod +x {APP_DIR}/setup.sh"
            ),
        ],
        timeout_ms=60_000,
        log=log,
    )
    log("Running server setup script...")
    run_command(
        client,
        machine_id,
        [
            "/bin/bash",
            "-c",
            f"export DEDALUS_API_KEY='{api_key}' && bash {APP_DIR}/setup.sh",
        ],
        timeout_ms=spec.setup_timeout_ms,
        stream=True,
        log=log,
    )
    log("Server setup complete")
    return sha


def _destroy_all_machines(client: Dedalus, log: Callable[[str], None]) -> None:
    """Best-effort destroy of every machine on the account (never fatal)."""
    try:
        machines = []
        cursor = None
        while True:
            kwargs: dict = {}
            if cursor:
                kwargs["cursor"] = cursor
            page = client.machines.list(**kwargs)
            machines.extend(getattr(page, "items", None) or [])
            cursor = getattr(page, "next_cursor", None)
            if not cursor:
                break
    except Exception as exc:
        log(f"Could not list machines ({exc}) - skipping cleanup")
        return

    destroyed_any = False
    for m in machines:
        if getattr(m, "desired_state", None) == "destroyed":
            continue
        try:
            log(f"Destroying existing machine: {m.machine_id}")
            client.machines.delete(machine_id=m.machine_id)
            destroyed_any = True
        except Exception as exc:
            log(f"Could not destroy {m.machine_id} ({exc}) - continuing")

    if destroyed_any:
        log("Waiting for platform to settle after cleanup...")
        time.sleep(5)


def _ensure_preview(
    client: Dedalus, machine_id: str, log: Callable[[str], None]
) -> str:
    """Create and return ready HTTPS preview URL for the machine port."""
    log("Exposing HTTPS preview port...")
    preview = client.machines.previews.create(
        machine_id=machine_id, port=PORT, protocol="https", visibility="org"
    )
    deadline = time.time() + 90
    while time.time() < deadline:
        p = client.machines.previews.retrieve(
            machine_id=machine_id, preview_id=preview.preview_id
        )
        if getattr(p, "status", None) == "ready":
            log(f"Preview URL active: {p.url}")
            return p.url
        time.sleep(POLL_INTERVAL_S)
    raise RuntimeError("Preview did not become ready within 90s")


def _wait_for_phase(
    client: Dedalus,
    machine_id: str,
    timeout_s: int,
    action: str,
    log: Callable[[str], None],
) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        phase = _phase(client.machines.retrieve(machine_id=machine_id))
        if phase == "running":
            log(f"Machine phase: running ({action} done)")
            return
        if phase in DEAD_PHASES:
            raise RuntimeError(f"Machine reached terminal state '{phase}'")
        time.sleep(POLL_INTERVAL_S)
    raise RuntimeError(f"Timed out after {timeout_s}s while {action}")


def _wait_external_health(
    base_url: str, log: Callable[[str], None], timeout_s: int = 150
) -> None:
    log("Checking external health endpoint...")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(f"{base_url}/health", timeout=8).status_code == 200:
                log("Troll AI server is online and healthy!")
                return
        except Exception:
            pass
        time.sleep(4)
    raise RuntimeError("Troll AI server failed health check")


def ensure_machine(
    spec: MachineSpec = TROLL_SPEC, *, log: Callable[[str], None] = print
) -> MachineHandle:
    """Create a fresh Dedalus Machine, deploy the AI server, and return public preview URL."""
    api_key = load_api_key()
    client = Dedalus(api_key=api_key)

    _destroy_all_machines(client, log)

    log("Creating fresh Dedalus Machine...")
    machine = client.machines.create(
        vcpu=spec.vcpu,
        memory_mib=spec.memory_mib,
        storage_gib=spec.storage_gib,
        autosleep=spec.autosleep,
    )
    machine_id = machine.machine_id
    log(f"Machine created: {machine_id}")

    _wait_for_phase(client, machine_id, spec.create_timeout_s, "creating", log)
    _deploy_and_setup(client, machine_id, spec, api_key, log=log)
    base_url = _ensure_preview(client, machine_id, log)
    _wait_external_health(base_url, log)

    return MachineHandle(
        machine_id=machine_id,
        base_url=base_url,
        client=client,
        api_key=api_key,
    )


if __name__ == "__main__":
    h = ensure_machine()
    print(f"\nTroll AI Server ready: {h.base_url}")
