"""
The Funnel watchdog's decisions (ops/funnel-watch/funnel_watch.py).

Chad, 2026-09-11: "tailscale has to be restarted everymorning to get funnel
back up... can we create a script to toggle the funnel everymorning?" What
lapses is the public DNS record; the script asks ts.net's authoritative
servers and Tailscale's own directly and acts only when every server that
answered says the record is gone or points at the tailnet address, twice in
a row: first a re-apply of the funnel command, then, twenty minutes on, the
off-and-on toggle, thirty minutes between toggles, and never when Funnel is
off in tailscaled on purpose. Pinned here without touching the network or
tailscale.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "ops" / "funnel-watch" / "funnel_watch.py"
spec = importlib.util.spec_from_file_location("funnel_watch", SCRIPT)
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)

INGRESS = {"Status": 0, "Answer": ["199.38.181.54", "209.177.145.137"]}
TAILNET = {"Status": 0, "Answer": ["100.95.128.97"]}
NXDOMAIN = {"Status": 3, "Answer": []}
NOW = datetime(2026, 9, 11, 14, 0, tzinfo=timezone.utc)

DIG_OK = (
    ";; Got answer:\n;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 4711\n"
    ";; flags: qr aa rd; QUERY: 1, ANSWER: 2, AUTHORITY: 0, ADDITIONAL: 1\n\n;; ANSWER SECTION:\n"
    "estimating.tail5fb2cd.ts.net. 5\tIN\tA\t199.38.181.54\nestimating.tail5fb2cd.ts.net. 5\tIN\tA\t209.177.145.137\n"
)
DIG_NX = ";; Got answer:\n;; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 4712\n;; flags: qr aa rd; QUERY: 1, ANSWER: 0, AUTHORITY: 1, ADDITIONAL: 0\n"
DIG_TAILNET = ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 4713\n\n;; ANSWER SECTION:\nestimating.tail5fb2cd.ts.net. 5 IN A 100.95.128.97\n"


def _minutes(m: int) -> datetime:
    return NOW + timedelta(minutes=m)


def test_dig_output_is_read():
    assert fw.parse_dig(DIG_OK, 0) == {"Status": 0, "Answer": ["199.38.181.54", "209.177.145.137"]}
    assert fw.parse_dig(DIG_NX, 0) == {"Status": 3, "Answer": []}
    assert fw.parse_dig(DIG_TAILNET, 0) == {"Status": 0, "Answer": ["100.95.128.97"]}
    assert fw.parse_dig("", 9) is None                       # no server reached
    assert fw.parse_dig("garbage", 0) is None


def test_the_record_is_read_the_way_the_two_mornings_looked():
    assert fw.classify({s: INGRESS for s in fw.SERVERS})[0] == "ok"
    assert fw.classify({s: NXDOMAIN for s in fw.SERVERS})[0] == "broken"          # 2026-09-10
    assert fw.classify({s: TAILNET for s in fw.SERVERS})[0] == "broken"           # 2026-09-11
    # propagation in progress: ns2 has it, ns1 not yet — healthy, do not act again
    status, detail = fw.classify({"ns1.dnsimple.com": NXDOMAIN, "ns2.dnsimple-edge.net": INGRESS})
    assert status == "ok" and "ns1.dnsimple.com: NXDOMAIN" in detail and "ns2.dnsimple-edge.net: 199.38.181.54 209.177.145.137" in detail
    # a server that could not be reached is not a verdict
    assert fw.classify({"ns1.dnsimple.com": None, "199.247.155.53": NXDOMAIN})[0] == "broken"
    assert fw.classify({"ns1.dnsimple.com": None, "199.247.155.53": None})[0] == "unknown"


def test_a_broken_spell_reapplies_first_then_toggles():
    action, s = fw.decide("broken", True, {}, NOW)
    assert (action, s["broken_streak"]) == ("wait", 1)
    action, s = fw.decide("broken", True, s, _minutes(5))
    assert action == "reapply" and s["attempts"] == 1 and s["broken_streak"] == 0 and s["last_attempt"].startswith("2026-09-11T14:05")
    # still broken while the re-applied record propagates: the twenty-minute cooldown holds
    action, s = fw.decide("broken", True, s, _minutes(10))
    assert action == "wait"
    action, s = fw.decide("broken", True, s, _minutes(15))
    assert action == "cooldown"
    action, s = fw.decide("broken", True, s, _minutes(25))
    assert action == "toggle" and s["attempts"] == 2 and s["last_action"] == "toggle"
    # a toggle gets thirty minutes; after that, toggle again
    action, s = fw.decide("broken", True, s, _minutes(30))
    action, s = fw.decide("broken", True, s, _minutes(45))
    assert action == "cooldown"
    action, s = fw.decide("broken", True, s, _minutes(60))
    assert action == "toggle" and s["attempts"] == 3


def test_an_ok_check_ends_the_spell():
    _, s = fw.decide("broken", True, {}, NOW)
    _, s = fw.decide("broken", True, s, _minutes(5))          # reapply
    action, s = fw.decide("ok", True, s, _minutes(15))
    assert (action, s["broken_streak"], s["attempts"], s["last_status"]) == ("none", 0, 0, "ok")
    # the next spell, a day later, starts gently again
    _, s = fw.decide("broken", True, s, _minutes(24 * 60))
    action, s = fw.decide("broken", True, s, _minutes(24 * 60 + 5))
    assert action == "reapply"


def test_funnel_switched_off_on_purpose_is_left_alone():
    _, s = fw.decide("broken", False, {}, NOW)
    action, s = fw.decide("broken", False, s, _minutes(5))
    assert action == "off-locally" and "last_attempt" not in s
    action, _ = fw.decide("broken", None, s, _minutes(10))
    assert action == "unknown-locally"
    action, _ = fw.decide("unknown", True, s, _minutes(10))
    assert action == "none"


def test_the_check_only_needs_the_standard_library_and_dig():
    text = SCRIPT.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith(("import ", "from ")):
            mod = line.split()[1].split(".")[0]
            assert mod in {"__future__", "argparse", "ipaddress", "json", "os", "re", "subprocess", "sys", "time", "datetime", "pathlib"}, line
    assert '"dig"' in text
