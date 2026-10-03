"""Behavioural depth tests for 2 educlaw-statereport actions previously covered by shape only.

Each action below already has a test asserting the response envelope (``is_ok``)
in ``test_statereport.py`` — ``TestSubmission.test_update_status`` for
``statereport-update-submission-status`` and ``TestValidationRule.test_update``
for ``statereport-update-validation-rule``. Those tests stay untouched; the
tests here prove what each action actually does to the database: the exact row
changed, from what to what, the rows that must NOT have changed, and one
input-validation refusal that must leave the database byte-identical.

Neither handler reaches the general ledger: ``statereport-update-submission-status``
writes only its ``sr_submission`` row plus one ``audit_log`` row, and
``statereport-update-validation-rule`` writes only its ``sr_validation_rule``
row plus one ``audit_log`` row; neither posts journals. Each success test says
so in a comment so a later reader does not add debit/credit assertions that
cannot hold.

Neither table carries money: ``sr_submission`` counts are INTEGER columns
compared exactly as ints, and ``sr_validation_rule`` has no monetary column at
all, so no Decimal-as-text assertion applies here. That is stated per test.
"""
import importlib.util
import json
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)
call_action = _helpers.call_action
ns = _helpers.ns
is_ok = _helpers.is_ok
is_error = _helpers.is_error

_SUB_MOD = _load("submission_tracking", _SCRIPTS_DIR)
SUB_ACTIONS = _SUB_MOD.ACTIONS
_DV_MOD = _load("data_validation", _SCRIPTS_DIR)
DV_ACTIONS = _DV_MOD.ACTIONS


@pytest.fixture
def env(db_path):
    conn = _helpers.get_conn(db_path)
    cid = _helpers.seed_company(conn)
    wid = _helpers.seed_collection_window(conn, cid)
    yield {"conn": conn, "company_id": cid, "window_id": wid}
    conn.close()


_SNAPSHOT_TABLES = (
    "sr_submission",
    "sr_validation_rule",
    "sr_collection_window",
    "audit_log",
)


def _snapshot(conn):
    """Full row dump of every table these actions could touch, for before/after compare."""
    snap = {}
    for table in _SNAPSHOT_TABLES:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        except Exception:
            continue
        snap[table] = sorted(
            json.dumps(dict(r), sort_keys=True, default=str) for r in rows)
    return snap


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _add_submission(s, records_submitted=50, method="flat_file"):
    r = call_action(SUB_ACTIONS["statereport-add-submission"], s["conn"], ns(
        window_id=s["window_id"], company_id=s["company_id"],
        submission_type="initial", submission_method=method,
        snapshot_id=None, linked_submission_id=None,
        submitted_at=None, submitted_by=None,
        records_submitted=records_submitted, records_accepted=None,
        records_rejected=None,
        state_confirmation_id=None, state_confirmed_at=None,
        amendment_reason=None, user_id=None,
    ))
    assert is_ok(r), r
    return r["id"]


_SUBMISSION_COLS = (
    "submission_status, records_submitted, records_accepted, "
    "records_rejected, state_confirmation_id, state_confirmed_at, "
    "collection_window_id, submission_type, submission_method, company_id"
)


def _read_submission(conn, submission_id):
    return conn.execute(
        f"SELECT {_SUBMISSION_COLS} FROM sr_submission WHERE id = ?",
        (submission_id,)).fetchone()


def _add_rule(conn, rule_code, category="demographics", severity="major",
              name="Depth Rule", description="Before"):
    r = call_action(DV_ACTIONS["statereport-add-validation-rule"], conn, ns(
        rule_code=rule_code, category=category, severity=severity,
        name=name, description=description,
        applicable_windows=None, applicable_states=None,
        is_federal_rule=None, sql_query=None,
        error_message_template=None, user_id=None,
    ))
    assert is_ok(r), r
    return r["id"]


_RULE_COLS = (
    "rule_code, category, severity, name, description, "
    "applicable_windows, applicable_states, is_federal_rule, "
    "sql_query, error_message_template, is_active"
)


def _read_rule(conn, rule_id):
    return conn.execute(
        f"SELECT {_RULE_COLS} FROM sr_validation_rule WHERE id = ?",
        (rule_id,)).fetchone()


# ---------------------------------------------------------------------------
# statereport-update-submission-status — stored row (status + counts flip)
# ---------------------------------------------------------------------------

class TestUpdateSubmissionStatusDepth:
    def test_flips_status_and_counts_and_leaves_sibling_alone(self, env):
        s, conn = env, env["conn"]
        sub_id = _add_submission(s, records_submitted=50)
        before = tuple(_read_submission(conn, sub_id))
        assert before == ("pending", 50, 0, 0, "", "",
                          s["window_id"], "initial", "flat_file", s["company_id"])
        sibling_id = _add_submission(s, records_submitted=7)
        sibling_before = tuple(_read_submission(conn, sibling_id))
        audits_before = _count(conn, "audit_log")

        r = call_action(SUB_ACTIONS["statereport-update-submission-status"], conn, ns(
            submission_id=sub_id, submission_status="completed",
            records_submitted=None, records_accepted=48,
            records_rejected=2,
            state_confirmation_id="CONF-123",
            state_confirmed_at=None,
            user_id="admin",
        ))
        assert is_ok(r), r
        assert r["submission_status"] == "completed"

        after = tuple(_read_submission(conn, sub_id))
        assert after == ("completed", 50, 48, 2, "CONF-123", "",
                         s["window_id"], "initial", "flat_file", s["company_id"])
        assert tuple(_read_submission(conn, sibling_id)) == sibling_before
        assert _count(conn, "audit_log") == audits_before + 1
        trail = conn.execute(
            "SELECT skill, action, entity_type, entity_id, new_values FROM audit_log WHERE entity_id = ? AND action = 'statereport-update-submission-status'",
            (sub_id,)).fetchall()
        assert len(trail) == 1
        assert tuple(trail[0]) == ("statereport-educlaw-statereport", "statereport-update-submission-status",
                                   "sr_submission", sub_id, '{"user_id": "admin"}')
        # No ledger legs: only the sr_submission row plus one audit_log row
        # move here; counts are INTEGERs compared exactly, never money text.

    def test_refuses_an_unknown_status_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        sub_id = _add_submission(s, records_submitted=50)
        before = _snapshot(conn)
        r = call_action(SUB_ACTIONS["statereport-update-submission-status"], conn, ns(
            submission_id=sub_id, submission_status="shipped",
            records_submitted=None, records_accepted=48,
            records_rejected=2,
            state_confirmation_id="CONF-123",
            state_confirmed_at=None,
            user_id="admin",
        ))
        assert is_error(r)
        assert r["message"] == (
            "--submission-status must be one of: "
            + ", ".join(_SUB_MOD.VALID_SUBMISSION_STATUSES))
        assert _snapshot(conn) == before
        assert tuple(_read_submission(conn, sub_id)) == (
            "pending", 50, 0, 0, "", "",
            s["window_id"], "initial", "flat_file", s["company_id"])


# ---------------------------------------------------------------------------
# statereport-update-validation-rule — stored row (field patch)
# ---------------------------------------------------------------------------

class TestUpdateValidationRuleDepth:
    def test_patches_named_fields_and_leaves_the_rest_alone(self, env):
        s, conn = env, env["conn"]
        rule_id = _add_rule(conn, "DEPTH-101")
        assert tuple(_read_rule(conn, rule_id)) == (
            "DEPTH-101", "demographics", "major", "Depth Rule", "Before",
            "[]", "[]", 0, "", "", 1)
        sibling_id = _add_rule(conn, "DEPTH-102", name="Untouched")
        sibling_before = tuple(_read_rule(conn, sibling_id))
        audits_before = _count(conn, "audit_log")

        r = call_action(DV_ACTIONS["statereport-update-validation-rule"], conn, ns(
            rule_id=rule_id, rule_code=None,
            category=None, severity="critical", name="Depth Rule Renamed",
            description="After",
            applicable_windows=None, applicable_states=None,
            is_federal_rule=None, sql_query=None,
            error_message_template=None, user_id=None,
        ))
        assert is_ok(r), r

        assert tuple(_read_rule(conn, rule_id)) == (
            "DEPTH-101", "demographics", "critical", "Depth Rule Renamed", "After",
            "[]", "[]", 0, "", "", 1)
        assert tuple(_read_rule(conn, sibling_id)) == sibling_before
        assert _count(conn, "audit_log") == audits_before + 1
        trail = conn.execute(
            "SELECT skill, action, entity_type, entity_id, new_values FROM audit_log WHERE entity_id = ? AND action = 'statereport-update-validation-rule'",
            (rule_id,)).fetchall()
        assert len(trail) == 1
        assert tuple(trail[0]) == ("statereport-educlaw-statereport", "statereport-update-validation-rule",
                                   "sr_validation_rule", rule_id, None)
        # No ledger legs: only the sr_validation_rule row plus one audit_log
        # row move here. No monetary column exists on this table, so there is
        # no Decimal-as-text assertion to make.

    def test_refuses_an_empty_patch_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        rule_id = _add_rule(conn, "DEPTH-103")
        before = _snapshot(conn)
        r = call_action(DV_ACTIONS["statereport-update-validation-rule"], conn, ns(
            rule_id=rule_id, rule_code=None,
            category=None, severity=None, name=None,
            description=None,
            applicable_windows=None, applicable_states=None,
            is_federal_rule=None, sql_query=None,
            error_message_template=None, user_id=None,
        ))
        assert is_error(r)
        assert r["message"] == "No fields to update"
        assert _snapshot(conn) == before
        assert tuple(_read_rule(conn, rule_id)) == (
            "DEPTH-103", "demographics", "major", "Depth Rule", "Before",
            "[]", "[]", 0, "", "", 1)
