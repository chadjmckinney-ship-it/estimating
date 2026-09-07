"""
Certificates for https on the office network (2026-09-07).

    python backend/make_certs.py                     # certs\\ for this machine's name and addresses
    python backend/make_certs.py --name office-pc    # an extra name the office will type
    python backend/make_certs.py --renew             # a fresh server certificate from the same CA

What it makes, in certs\\ (never committed — see .gitignore):

    ca.key, ca.crt          a private certificate authority, good for ten years.
                            ca.crt is the one file the office installs.
    server.key              this machine's private key
    server.crt              its certificate, signed by the CA, for the machine's
                            name, its fully-qualified name, localhost and every
                            IPv4 it has right now, plus any --name / --ip given;
                            825 days, the longest every browser still trusts
    server-chain.crt        server.crt followed by ca.crt — what run.ps1 serves

run.ps1 serves https whenever server.key and server-chain.crt exist (-Http
to refuse). The office PCs trust the CA once each, in an elevated prompt:

    certutil -addstore -f Root certs\\ca.crt

(double-clicking ca.crt → Install Certificate → Local Machine → Trusted Root
Certification Authorities does the same). Chrome and Edge read that store;
Firefox needs security.enterprise_roots.enabled or its own import.

Needs openssl; Git for Windows ships one and this looks there.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CERTS = ROOT / "certs"
CA_DAYS = 3650
SERVER_DAYS = 825


def find_openssl() -> str | None:
    found = shutil.which("openssl")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\Git\usr\bin\openssl.exe",
        r"C:\Program Files\Git\mingw64\bin\openssl.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def _run(openssl: str, *args: str) -> str:
    done = subprocess.run([openssl, *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"openssl {args[0]} failed:\n{done.stderr.strip()}")
    return done.stdout


def local_names() -> tuple[list[str], list[str]]:
    """This machine's names and IPv4 addresses, the hostname first."""
    host = socket.gethostname()
    names = [host]
    fqdn = socket.getfqdn()
    if fqdn and "." in fqdn and fqdn.lower() != host.lower():
        names.append(fqdn)
    names.append("localhost")
    ips = {"127.0.0.1"}
    try:
        ips |= {a[4][0] for a in socket.getaddrinfo(host, None, socket.AF_INET)}
    except socket.gaierror:
        pass
    return names, sorted(ips)


def make(
    out: Path,
    names: list[str],
    ips: list[str],
    *,
    renew: bool = False,
    days: int = SERVER_DAYS,
    openssl: str | None = None,
) -> dict[str, Path]:
    """Write the CA (once) and the server certificate (once, or again with renew)."""
    openssl = openssl or find_openssl()
    if not openssl:
        raise FileNotFoundError(
            "openssl not found. Git for Windows ships one (C:\\Program Files\\Git\\usr\\bin); "
            "install Git, or put openssl on PATH."
        )
    out.mkdir(parents=True, exist_ok=True)
    ca_key, ca_crt = out / "ca.key", out / "ca.crt"
    made_ca = False
    if not (ca_key.exists() and ca_crt.exists()):
        _run(
            openssl, "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-sha256",
            "-days", str(CA_DAYS), "-keyout", str(ca_key), "-out", str(ca_crt),
            "-subj", "/CN=S and S Estimating local CA",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        )
        made_ca = True

    srv_key, srv_crt, chain = out / "server.key", out / "server.crt", out / "server-chain.crt"
    made_server = False
    if renew or not (srv_key.exists() and srv_crt.exists() and chain.exists()):
        csr, ext = out / "server.csr", out / "server.ext"
        _run(
            openssl, "req", "-new", "-newkey", "rsa:2048", "-nodes", "-sha256",
            "-keyout", str(srv_key), "-out", str(csr), "-subj", f"/CN={names[0]}",
        )
        san = ",".join([f"DNS:{n}" for n in names] + [f"IP:{i}" for i in ips])
        ext.write_text(
            "basicConstraints=CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=serverAuth\n"
            f"subjectAltName={san}\n",
            encoding="ascii",
        )
        _run(
            openssl, "x509", "-req", "-sha256", "-days", str(days), "-in", str(csr),
            "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
            "-out", str(srv_crt), "-extfile", str(ext),
        )
        chain.write_text(srv_crt.read_text(encoding="ascii") + ca_crt.read_text(encoding="ascii"), encoding="ascii")
        csr.unlink(missing_ok=True)
        ext.unlink(missing_ok=True)
        made_server = True

    return {
        "ca_key": ca_key, "ca_crt": ca_crt, "server_key": srv_key, "server_crt": srv_crt,
        "chain": chain, "made_ca": made_ca, "made_server": made_server,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", action="append", default=[], help="an extra DNS name for the certificate (repeatable)")
    ap.add_argument("--ip", action="append", default=[], help="an extra IPv4 address (repeatable)")
    ap.add_argument("--renew", action="store_true", help="a new server certificate from the existing CA")
    ap.add_argument("--out", default=str(CERTS), help=argparse.SUPPRESS)
    args = ap.parse_args()

    names, ips = local_names()
    for n in args.name:
        if n not in names:
            names.append(n)
    for i in args.ip:
        if i not in ips:
            ips.append(i)
    try:
        made = make(Path(args.out), names, ips, renew=args.renew)
    except (FileNotFoundError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1

    out = Path(args.out)
    print(f"{'made' if made['made_ca'] else 'kept'}    {made['ca_crt']}   (the CA — install this on each PC)")
    print(f"{'made' if made['made_server'] else 'kept'}    {made['chain']}   for {', '.join(names)} and {', '.join(ips)}")
    print()
    print("run.ps1 now serves https. Once per PC, in an elevated prompt:")
    print(f"    certutil -addstore -f Root {out / 'ca.crt'}")
    print(f"then open https://{names[0]}:8001/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
