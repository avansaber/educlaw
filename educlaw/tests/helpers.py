"""Test helper functions for EduClaw tests.

Separate from conftest.py so they can be explicitly imported without
pytest conftest discovery conflicts.
"""
import argparse
import json
import pytest


def call(fn, conn, args, capsys):
    """Invoke a domain function, capture its JSON output, return the dict.

    Since ok() and err() both call sys.exit(), we catch SystemExit here.
    The JSON is printed to stdout before the exit.
    """
    with pytest.raises(SystemExit):
        fn(conn, args)
    captured = capsys.readouterr()
    return json.loads(captured.out)


def make_args(**kwargs):
    """Build an argparse.Namespace that mimics CLI output.

    All argparse attributes start as None (like real argparse does when
    a flag is omitted), then kwargs override them.
    """
    defaults = {
        "company_id": None, "user_id": None, "search": None,
        "limit": 50, "offset": 0,
        # students
        "student_id": None, "applicant_id": None, "first_name": None,
        "last_name": None, "middle_name": None, "date_of_birth": None,
        "gender": None, "email": None, "phone": None, "alternate_phone": None,
        "address": None, "grade_level": None, "applying_for_program_id": None,
        "applying_for_term_id": None, "application_date": None,
        "documents": None, "previous_school": None, "previous_school_address": None,
        "transfer_records": None, "emergency_contact": None,
        "applicant_status": None, "review_notes": None, "reviewed_by": None,
        "student_status": None, "current_program_id": None, "cohort_year": None,
        "enrollment_date": None, "graduation_date": None, "registration_hold": None,
        "directory_info_opt_out": None, "academic_standing": None, "naming_series": None,
        # guardian
        "guardian_id": None, "guardian_info": None, "relationship": None,
        "is_primary_contact": None, "is_emergency_contact": None,
        "has_custody": None, "can_pickup": None, "receives_communications": None,
        "employer": None, "occupation": None,
        # ferpa
        "data_category": None, "access_type": None, "access_reason": None,
        "ip_address": None, "is_emergency_access": None, "consent_type": None,
        "consent_date": None, "consent_id": None, "granted_by": None,
        "granted_by_relationship": None, "revoked_date": None,
        "third_party_name": None, "purpose": None,
        # academic year/term
        "year_id": None, "academic_year_id": None, "term_id": None,
        "academic_term_id": None, "name": None, "start_date": None, "end_date": None,
        "is_active": None, "term_type": None, "term_status": None,
        "enrollment_start_date": None, "enrollment_end_date": None,
        "grade_submission_deadline": None,
        # room
        "room_id": None, "room_number": None, "building": None,
        "capacity": None, "room_type": None, "facilities": None,
        # program
        "program_id": None, "program_type": None, "department_id": None,
        "description": None, "total_credits_required": None, "duration_years": None,
        "prerequisites": None, "is_published": None,
        # course
        "course_id": None, "course_code": None, "course_type": None,
        "credit_hours": None, "max_enrollment": None, "is_default": None,
        # section
        "section_id": None, "section_number": None, "section_status": None,
        "instructor_id": None, "days_of_week": None, "start_time": None,
        "end_time": None, "waitlist_enabled": None, "waitlist_max": None,
        # enrollment
        "enrollment_id": None, "enrollment_status": None, "drop_reason": None,
        "waitlist_status": None, "is_repeat": None, "grade_type": None,
        # grading
        "scale_id": None, "grading_scale_id": None, "entries": None,
        "plan_id": None, "categories": None, "category_id": None,
        "assessment_id": None, "max_points": None, "allows_extra_credit": None,
        "sort_order": None, "results": None, "points_earned": None,
        "is_exempt": None, "is_late": None, "graded_by": None,
        "submitted_by": None, "is_grade_submitted": None,
        "new_letter_grade": None, "new_grade_points": None,
        "amended_by": None, "reason": None, "revenue_account_id": None,
        "due_date": None, "due_date_from": None, "due_date_to": None,
        # attendance
        "attendance_id": None, "attendance_date": None,
        "attendance_date_from": None, "attendance_date_to": None,
        "attendance_status": None, "late_minutes": None,
        "comments": None, "marked_by": None, "source": None,
        "records": None, "threshold": None,
        # staff
        "employee_id": None, "credentials": None, "specializations": None,
        "max_teaching_load_hours": None, "office_location": None,
        "office_hours": None, "bio": None,
        # fees
        "fee_category_id": None, "structure_id": None, "scholarship_id": None,
        "scholarship_status": None, "discount_type": None, "discount_amount": None,
        "applies_to_category_id": None, "approved_by": None, "amount": None,
        "items": None, "code": None, "publish_date": None,
        # communications
        "announcement_id": None, "announcement_status": None, "title": None,
        "body": None, "priority": None, "audience_type": None,
        "audience_filter": None, "expiry_date": None, "published_by": None,
        "recipient_type": None, "recipient_id": None, "notification_type": None,
        "message": None, "reference_type": None, "reference_id": None,
        "sent_via": None, "is_read": None, "sent_by": None,
        "date_from": None, "date_to": None,
        # misc
        "category_id": None, "db_path": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)
