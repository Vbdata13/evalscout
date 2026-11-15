#!/bin/sh
set -eu
umask 077
mkdir -p /logs/verifier
chmod 700 /logs/verifier
exec python3 -I /tests/verify.py
