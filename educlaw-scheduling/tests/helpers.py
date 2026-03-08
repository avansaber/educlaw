"""Shared test helpers for EduClaw Advanced Scheduling tests.

Separated from conftest.py so test files can import them explicitly
without conflicting with the project-root conftest.py.
"""
import argparse
import contextlib
import io
import json


def call(fn, conn, args):
    """Invoke a domain function and return the parsed JSON response.

    ok()  → {"status": "ok",    ...data...}
    err() → {"status": "error", "message": "..."}

    Both print to stdout and call sys.exit(); we capture stdout and
    catch SystemExit to recover the response.
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            fn(conn, args)
    except SystemExit:
        pass
    output = buf.getvalue().strip()
    if output:
        return json.loads(output)
    return {}


def A(**kwargs):
    """Build an argparse.Namespace (mimics parsed CLI args)."""
    return argparse.Namespace(**kwargs)
