#!/usr/bin/env python3
"""Generate HTTP Basic auth credentials for JARVIS's private-LAN hosting.

The password is never stored in the clear. This derives a PBKDF2-HMAC-SHA256
digest with a fresh random salt and prints a config.local.json snippet. The
server recomputes the digest per request and compares it in constant time
(jarvis.server.verify_password), so only the salt and digest are persisted.

Usage:
    python3 scripts/make_auth.py                 # prompts for username + password
    python3 scripts/make_auth.py --username joe  # prompts for password only

The iteration count must match Config.auth_pbkdf2_iterations (default 200000).
Pass --iterations to change it in both places together.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys

DEFAULT_ITERATIONS = 200_000


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate JARVIS Basic-auth credentials.")
    parser.add_argument("--username", help="Login username (prompted if omitted).")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS,
                        help=f"PBKDF2 iterations (default {DEFAULT_ITERATIONS}); "
                             "must equal auth_pbkdf2_iterations in config.")
    args = parser.parse_args()

    username = args.username or input("Username: ").strip()
    if not username:
        print("error: username is required", file=sys.stderr)
        return 1

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("error: passwords do not match", file=sys.stderr)
        return 1
    if len(password) < 8:
        print("error: choose a password of at least 8 characters", file=sys.stderr)
        return 1

    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, args.iterations)

    snippet = {
        "auth_enabled": True,
        "auth_username": username,
        "auth_password_hash": digest.hex(),
        "auth_password_salt": salt.hex(),
        "auth_pbkdf2_iterations": args.iterations,
    }
    print("\nAdd these keys to config.local.json:\n")
    print(json.dumps(snippet, indent=2))
    print("\n(Combine with tls_cert/tls_key and a non-loopback app_host to host on the LAN.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
