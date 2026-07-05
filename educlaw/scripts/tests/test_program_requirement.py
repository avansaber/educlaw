"""L1 pytest tests for educlaw program-requirement CRUD (M33 Item 4 / B11).

Covers the two new actions that fill edu-get-program's previously-permanently-empty
`requirements` array:
  - edu-add-program-requirement  (writer for educlaw_program_requirement)
  - edu-list-program-requirements (reader by program)
plus the round-trip through edu-get-program (which already JOIN-reads the table).
"""
import importlib.util
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
get_conn = _helpers.get_conn
is_ok = _helpers.is_ok
is_error = _helpers.is_error
seed_company = _helpers.seed_company
seed_program = _helpers.seed_program
seed_course = _helpers.seed_course

ACADEMICS_ACTIONS = _load("academics", _SCRIPTS_DIR).ACTIONS


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def setup(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    pid = seed_program(conn, cid)
    crs_id = seed_course(conn, cid, code="MATH101")
    yield {"conn": conn, "company_id": cid, "program_id": pid, "course_id": crs_id}
    conn.close()


def _add_req(conn, program_id, course_id, requirement_type="required",
             credit_category=None, min_grade=None, company_id=None):
    return call_action(ACADEMICS_ACTIONS["edu-add-program-requirement"], conn, ns(
        program_id=program_id, course_id=course_id,
        requirement_type=requirement_type, credit_category=credit_category,
        min_grade=min_grade, company_id=company_id, user_id=None,
    ))


# ── add-program-requirement ──────────────────────────────────────────────────

class TestAddProgramRequirement:
    def test_happy_path(self, setup):
        s = setup
        r = _add_req(s["conn"], s["program_id"], s["course_id"], "core",
                     credit_category="STEM", min_grade="C")
        assert is_ok(r)
        assert r["program_id"] == s["program_id"]
        assert r["course_id"] == s["course_id"]
        assert r["requirement_type"] == "core"
        assert r["id"]

    def test_row_actually_written(self, setup):
        s = setup
        r = _add_req(s["conn"], s["program_id"], s["course_id"])
        row = s["conn"].execute(
            "SELECT program_id, course_id, requirement_type, credit_category, min_grade "
            "FROM educlaw_program_requirement WHERE id = ?", (r["id"],)).fetchone()
        assert row is not None
        assert dict(row)["requirement_type"] == "required"

    def test_optional_fields_persist(self, setup):
        s = setup
        r = _add_req(s["conn"], s["program_id"], s["course_id"], "elective",
                     credit_category="Humanities", min_grade="D")
        row = dict(s["conn"].execute(
            "SELECT credit_category, min_grade FROM educlaw_program_requirement WHERE id = ?",
            (r["id"],)).fetchone())
        assert row["credit_category"] == "Humanities"
        assert row["min_grade"] == "D"

    def test_missing_program_id_errors(self, setup):
        s = setup
        r = _add_req(s["conn"], None, s["course_id"])
        assert is_error(r)

    def test_missing_course_id_errors(self, setup):
        s = setup
        r = _add_req(s["conn"], s["program_id"], None)
        assert is_error(r)

    def test_invalid_requirement_type_errors(self, setup):
        s = setup
        r = _add_req(s["conn"], s["program_id"], s["course_id"], "bogus")
        assert is_error(r)

    def test_unknown_program_errors(self, setup):
        s = setup
        r = _add_req(s["conn"], "no-such-program", s["course_id"])
        assert is_error(r)

    def test_unknown_course_errors(self, setup):
        s = setup
        r = _add_req(s["conn"], s["program_id"], "no-such-course")
        assert is_error(r)

    def test_duplicate_pair_errors_cleanly(self, setup):
        s = setup
        r1 = _add_req(s["conn"], s["program_id"], s["course_id"])
        assert is_ok(r1)
        r2 = _add_req(s["conn"], s["program_id"], s["course_id"], "elective")
        assert is_error(r2)
        assert "already a requirement" in (r2.get("error", "") + r2.get("message", ""))

    def test_company_mismatch_errors(self, setup):
        s = setup
        other = seed_company(s["conn"])
        r = _add_req(s["conn"], s["program_id"], s["course_id"], company_id=other)
        assert is_error(r)

    def test_company_match_ok(self, setup):
        s = setup
        r = _add_req(s["conn"], s["program_id"], s["course_id"], company_id=s["company_id"])
        assert is_ok(r)


# ── list-program-requirements ────────────────────────────────────────────────

class TestListProgramRequirements:
    def test_lists_with_course_info(self, setup):
        s = setup
        c2 = seed_course(s["conn"], s["company_id"], code="ENG201")
        _add_req(s["conn"], s["program_id"], s["course_id"], "core")
        _add_req(s["conn"], s["program_id"], c2, "elective")

        r = call_action(ACADEMICS_ACTIONS["edu-list-program-requirements"], s["conn"],
                        ns(program_id=s["program_id"]))
        assert is_ok(r)
        assert r["count"] == 2
        codes = {row["course_code"] for row in r["requirements"]}
        assert codes == {"MATH101", "ENG201"}
        # joined course fields present
        assert all("course_name" in row and "credit_hours" in row for row in r["requirements"])

    def test_empty_program_returns_zero(self, setup):
        s = setup
        r = call_action(ACADEMICS_ACTIONS["edu-list-program-requirements"], s["conn"],
                        ns(program_id=s["program_id"]))
        assert is_ok(r)
        assert r["count"] == 0
        assert r["requirements"] == []

    def test_unknown_program_errors(self, setup):
        s = setup
        r = call_action(ACADEMICS_ACTIONS["edu-list-program-requirements"], s["conn"],
                        ns(program_id="no-such-program"))
        assert is_error(r)


# ── round-trip: edu-get-program now returns requirements ─────────────────────

class TestGetProgramIncludesRequirements:
    def test_get_program_returns_requirement(self, setup):
        s = setup
        _add_req(s["conn"], s["program_id"], s["course_id"], "required",
                 credit_category="STEM", min_grade="C")

        r = call_action(ACADEMICS_ACTIONS["edu-get-program"], s["conn"],
                        ns(program_id=s["program_id"]))
        assert is_ok(r)
        assert len(r["requirements"]) == 1
        req = r["requirements"][0]
        assert req["course_id"] == s["course_id"]
        assert req["requirement_type"] == "required"
        assert req["course_code"] == "MATH101"
        assert req["credit_category"] == "STEM"

    def test_get_program_empty_before_any_requirement(self, setup):
        s = setup
        r = call_action(ACADEMICS_ACTIONS["edu-get-program"], s["conn"],
                        ns(program_id=s["program_id"]))
        assert is_ok(r)
        assert r["requirements"] == []
