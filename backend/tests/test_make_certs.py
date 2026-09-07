"""
The certificate maker behind https on the office network (backend/make_certs.py, 2026-09-07).

A private CA, a server certificate signed by it for this machine's names and
addresses, and a chain file uvicorn can serve. Skips where there is no
openssl; Git for Windows ships one.
"""

from __future__ import annotations

import ssl
import subprocess

import pytest

import make_certs

OPENSSL = make_certs.find_openssl()
pytestmark = pytest.mark.skipif(OPENSSL is None, reason="no openssl on this machine")


def _text(*args: str) -> str:
    return subprocess.run([OPENSSL, *args], capture_output=True, text=True, check=True).stdout


def test_the_ca_signs_a_certificate_for_the_names_given(tmp_path):
    made = make_certs.make(tmp_path / "certs", ["testhost", "testhost.lan", "localhost"], ["127.0.0.1", "10.0.0.5"])
    assert made["made_ca"] and made["made_server"]
    for key in ("ca_key", "ca_crt", "server_key", "server_crt", "chain"):
        assert made[key].is_file(), key

    assert "OK" in _text("verify", "-CAfile", str(made["ca_crt"]), str(made["server_crt"]))
    san = _text("x509", "-noout", "-ext", "subjectAltName", "-in", str(made["server_crt"]))
    for want in ("DNS:testhost", "DNS:testhost.lan", "DNS:localhost", "IP Address:127.0.0.1", "IP Address:10.0.0.5"):
        assert want in san, san
    assert "CA:TRUE" in _text("x509", "-noout", "-ext", "basicConstraints", "-in", str(made["ca_crt"]))
    assert made["chain"].read_text().count("BEGIN CERTIFICATE") == 2


def test_uvicorn_can_load_the_chain_and_key(tmp_path):
    made = make_certs.make(tmp_path / "certs", ["testhost"], ["127.0.0.1"])
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(made["chain"]), str(made["server_key"]))  # raises if they do not match


def test_a_second_run_keeps_everything_and_renew_keeps_only_the_ca(tmp_path):
    out = tmp_path / "certs"
    first = make_certs.make(out, ["testhost"], ["127.0.0.1"])
    ca_before, crt_before = first["ca_crt"].read_bytes(), first["server_crt"].read_bytes()

    again = make_certs.make(out, ["testhost"], ["127.0.0.1"])
    assert not again["made_ca"] and not again["made_server"]
    assert first["server_crt"].read_bytes() == crt_before

    renewed = make_certs.make(out, ["testhost", "another"], ["127.0.0.1"], renew=True)
    assert not renewed["made_ca"] and renewed["made_server"]
    assert renewed["ca_crt"].read_bytes() == ca_before
    assert renewed["server_crt"].read_bytes() != crt_before
    assert "DNS:another" in _text("x509", "-noout", "-ext", "subjectAltName", "-in", str(renewed["server_crt"]))


def test_this_machine_is_named_first_and_loopback_is_always_in():
    names, ips = make_certs.local_names()
    import socket

    assert names[0] == socket.gethostname() and "localhost" in names
    assert "127.0.0.1" in ips
