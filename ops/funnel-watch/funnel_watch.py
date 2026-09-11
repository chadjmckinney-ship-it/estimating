#!/usr/bin/env python3
"""
funnel-watch: keep the box's Tailscale Funnel reachable from the public internet.

Chad, 2026-09-11: "I am noticing tailscale has to be restarted everymorning to
get funnel back up... can we create a script to toggle the funnel everymorning?"

What lapses is the PUBLIC DNS record for the node's name. Tailscale publishes
the Funnel ingress addresses for `estimating.tail5fb2cd.ts.net` when Funnel is
turned on, and roughly a day later the public servers answer NXDOMAIN, or the
node's own 100.x address, instead. The node itself stays registered with the
ingress, the ingress still proxies (`/health` answers 200 when reached at the
ingress address directly), and `tailscale funnel status` says on. Restarting
tailscaled does not renew the record (2026-09-11 09:04, restart, record still
wrong at 09:09); `tailscale funnel --https=443 off` then `on` does (2026-09-10
07:57 and 2026-09-11 09:14) — but the `off` deletes the record at once and the
public recursive resolvers cached that NXDOMAIN for up to an hour afterwards.

So, every five minutes (ops/funnel-watch/funnel-watch.timer):

  * ask ts.net's authoritative servers and Tailscale's own DNS server
    directly, with dig — not the box's resolver, which routes ts.net to
    Tailscale and always answers the tailnet address, and not the public
    recursive resolvers, whose caches lag;
  * healthy = at least one server returned a public address;
    broken  = every server that answered said NXDOMAIN or gave a CGNAT
    (100.64/10) address; unknown = no server answered;
  * after two consecutive broken checks, act: the first attempt of a broken
    spell re-applies `tailscale funnel --bg ... on` alone, which never deletes
    the record; if the record is still gone twenty minutes later, the next
    attempt toggles off and on (the fix that is known to work); thirty
    minutes after a toggle it may toggle again; every attempt is logged with
    what it did, so the log says which one brings the record back;
  * if Funnel is off in tailscaled itself, somebody turned it off on purpose:
    leave it alone and say so.

State and a transitions-only log live in ~/estimating/logs/. Every run prints
one line to stdout, which systemd keeps in the journal:
`journalctl --user -u funnel-watch --since today`.

    python3 funnel_watch.py            # one check, act if needed
    python3 funnel_watch.py --dry-run  # one check, report, never act
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

NAME = "estimating.tail5fb2cd.ts.net"
BACKEND = "https+insecure://127.0.0.1:8001"
# ts.net's authoritative servers (dig NS ts.net) and Tailscale's own server,
# the one tailscaled routes ts.net queries to.
SERVERS = ["ns1.dnsimple.com", "ns2.dnsimple-edge.net", "ns3.dnsimple.com", "ns4.dnsimple-edge.org", "199.247.155.53"]
CGNAT = ipaddress.ip_network("100.64.0.0/10")
BROKEN_CHECKS_BEFORE_ACTING = 2
COOLDOWN = {"reapply": timedelta(minutes=20), "toggle": timedelta(minutes=30)}
LOG_DIR = Path(os.environ.get("FUNNEL_WATCH_DIR", str(Path.home() / "estimating" / "logs")))
STATE = LOG_DIR / "funnel-watch.state.json"
LOG = LOG_DIR / "funnel-watch.log"

_STATUS = re.compile(r"status: ([A-Z]+)")
_A = re.compile(r"^\S+\s+\d+\s+IN\s+A\s+(\S+)\s*$", re.M)


# ------------------------------------------------------------------ the checks


def parse_dig(text: str, rc: int) -> dict | None:
    """dig's `+noall +comments +answer` output as {'Status': 0|3|..., 'Answer': [ips]}; None when no server answered."""
    if rc != 0:
        return None
    m = _STATUS.search(text)
    if not m:
        return None
    status = {"NOERROR": 0, "NXDOMAIN": 3}.get(m.group(1), 2)
    return {"Status": status, "Answer": _A.findall(text)}


def query(server: str, name: str = NAME) -> dict | None:
    try:
        out = subprocess.run(
            ["dig", f"@{server}", name, "A", "+noall", "+comments", "+answer", "+time=5", "+tries=1"],
            capture_output=True, text=True, timeout=25,
        )
    except Exception:  # noqa: BLE001 — a server we could not ask is "no answer", not a verdict
        return None
    return parse_dig(out.stdout, out.returncode)


def classify(answers: dict[str, dict | None]) -> tuple[str, str]:
    """('ok' | 'broken' | 'unknown', a one-line account of what each server said)."""
    seen = healthy = False
    parts = []
    for who, a in answers.items():
        if a is None:
            parts.append(f"{who}: no answer")
            continue
        seen = True
        ips = a.get("Answer") or []
        if not ips:
            parts.append(f"{who}: NXDOMAIN" if a.get("Status") == 3 else f"{who}: empty")
            continue
        parts.append(f"{who}: {' '.join(ips)}")
        if any(ipaddress.ip_address(ip) not in CGNAT for ip in ips):
            healthy = True
    status = "unknown" if not seen else ("ok" if healthy else "broken")
    return status, "; ".join(parts)


def funnel_on() -> bool | None:
    """Whether tailscaled itself has Funnel on for the name; None when it could not be asked."""
    try:
        out = subprocess.run(["tailscale", "serve", "status", "--json"], capture_output=True, text=True, timeout=20)
    except Exception:  # noqa: BLE001
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        cfg = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    allow = cfg.get("AllowFunnel") or {}
    return any(bool(v) for v in allow.values())


# ---------------------------------------------------------------- the decision


def decide(status: str, on: bool | None, state: dict, now: datetime) -> tuple[str, dict]:
    """What to do this run, and the state to keep. Pure, so it can be tested.

    Returns one of: none, wait, cooldown, off-locally, unknown-locally, reapply, toggle.
    A broken spell starts at the first broken check and ends at the first ok
    one; its first attempt is a re-apply, every later one a toggle."""
    new = dict(state)
    new["last_check"] = now.isoformat(timespec="seconds")
    new["last_status"] = status
    if status != "broken":
        new["broken_streak"] = 0
        new["attempts"] = 0
        return "none", new
    new["broken_streak"] = int(state.get("broken_streak", 0)) + 1
    if on is False:
        return "off-locally", new
    if on is None:
        return "unknown-locally", new
    if new["broken_streak"] < BROKEN_CHECKS_BEFORE_ACTING:
        return "wait", new
    last_action, last_at = state.get("last_action"), state.get("last_attempt")
    if last_at and int(state.get("attempts", 0)) > 0 and now - datetime.fromisoformat(last_at) < COOLDOWN.get(last_action, COOLDOWN["toggle"]):
        return "cooldown", new
    action = "reapply" if int(state.get("attempts", 0)) == 0 else "toggle"
    new["attempts"] = int(state.get("attempts", 0)) + 1
    new["last_action"] = action
    new["last_attempt"] = now.isoformat(timespec="seconds")
    new["broken_streak"] = 0
    return action, new


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=60)


def reapply() -> str:
    on = _run(["tailscale", "funnel", "--bg", "--https=443", BACKEND])
    return f"on rc={on.returncode}" + (f" ({on.stderr.strip()[:120]})" if on.returncode else "")


def toggle() -> str:
    off = _run(["tailscale", "funnel", "--https=443", "off"])
    time.sleep(5)
    on = _run(["tailscale", "funnel", "--bg", "--https=443", BACKEND])
    return f"off rc={off.returncode} on rc={on.returncode}" + (f" ({on.stderr.strip()[:120]})" if on.returncode else "")


# ------------------------------------------------------------------- the run


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_state(state: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def log(line: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {line}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="keep the public Funnel record alive")
    ap.add_argument("--dry-run", action="store_true", help="check and report; never act")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    answers = {server: query(server) for server in SERVERS}
    status, detail = classify(answers)
    on = funnel_on()
    state = load_state()
    action, new_state = decide(status, on, state, now)
    changed = state.get("last_status") != status

    line = f"{status} ({detail}); funnel {'on' if on else 'off' if on is False else 'unknown'} locally; {action}"
    if action in ("reapply", "toggle"):
        if args.dry_run:
            line += " [dry run: not done]"
            new_state = dict(state, last_check=new_state["last_check"], last_status=status,
                             broken_streak=int(state.get("broken_streak", 0)) + 1)
        else:
            line += "; " + (reapply() if action == "reapply" else toggle())
    print(line)
    if changed or action in ("reapply", "toggle", "off-locally"):
        log(line)
    save_state(new_state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
