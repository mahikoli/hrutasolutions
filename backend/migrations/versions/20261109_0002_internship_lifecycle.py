"""Add the internship lifecycle fields and operational records.

Revision ID: 20261109_0002
Revises: 20261031_0001
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

from app import models  # noqa: F401 - register new lifecycle tables
from app.database import Base

revision = "20261109_0002"
down_revision = "20261031_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # Create only the new lifecycle tables. The bootstrap revision is deliberately
    # broad, but follow-on revisions must not create unrelated ORM tables implicitly.
    lifecycle_tables = [
        "internship_followups", "internship_payments", "internship_status_history",
        "internship_batches", "internship_batch_students", "internship_training_sessions",
        "internship_assignments", "internship_submissions", "internship_evaluations",
        "internship_sync_runs",
    ]
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in lifecycle_tables], checkfirst=True)
    inspector = sa.inspect(bind)
    app_columns = {column["name"] for column in inspector.get_columns("internship_applications")}
    additions = [
        ("whatsapp_number", sa.String(30), True, None),
        ("date_of_birth", sa.Date(), True, None),
        ("university", sa.String(200), True, None),
        ("degree", sa.String(150), True, None),
        ("department", sa.String(150), True, None),
        ("current_academic_year", sa.String(40), True, None),
        ("graduation_year", sa.Integer(), True, None),
        ("selected_domain", sa.String(150), True, None),
        ("preferred_duration_weeks", sa.Integer(), True, None),
        ("preferred_mode", sa.String(20), True, None),
        ("technical_skills", sa.Text(), True, None),
        ("previous_experience", sa.Text(), True, None),
        ("registration_source", sa.String(80), False, "manual"),
        ("google_form_response_id", sa.String(160), True, None),
        ("sync_status", sa.String(30), False, "not_synced"),
        ("student_status", sa.String(40), False, "new_registration"),
        ("payment_option", sa.String(20), False, "pending"),
        ("payment_amount", sa.Numeric(12, 2), False, "0"),
        ("payment_status", sa.String(20), False, "pending"),
        ("payment_transaction_id", sa.String(160), True, None),
        ("next_follow_up_at", sa.DateTime(), True, None),
        ("internal_remarks", sa.Text(), True, None),
        ("updated_by_id", sa.Integer(), True, None),
    ]
    for name, type_, nullable, default in additions:
        if name in app_columns:
            continue
        kwargs = {"nullable": nullable}
        if default is not None:
            kwargs["server_default"] = sa.text(f"'{default}'" if isinstance(default, str) and default != "0" else str(default))
        foreign_keys = [sa.ForeignKey("users.id", ondelete="SET NULL")] if name == "updated_by_id" else []
        op.add_column("internship_applications", sa.Column(name, type_, *foreign_keys, **kwargs))

    attendance_columns = {column["name"] for column in inspector.get_columns("internship_attendance")}
    if "session_id" not in attendance_columns:
        constraints = {constraint.get("name") for constraint in inspector.get_unique_constraints("internship_attendance")}
        with op.batch_alter_table("internship_attendance") as batch:
            if "uq_intern_attendance_day" in constraints:
                batch.drop_constraint("uq_intern_attendance_day", type_="unique")
            batch.add_column(sa.Column("session_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_internship_attendance_session", "internship_training_sessions", ["session_id"], ["id"], ondelete="CASCADE")

    certificate_columns = {column["name"] for column in inspector.get_columns("internship_certificates")}
    if "evaluation_id" not in certificate_columns:
        with op.batch_alter_table("internship_certificates") as batch:
            batch.add_column(sa.Column("evaluation_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_internship_certificate_evaluation", "internship_evaluations", ["evaluation_id"], ["id"], ondelete="SET NULL")
            batch.create_unique_constraint("uq_internship_certificate_evaluation", ["evaluation_id"])

    trainer_columns = {column["name"] for column in inspector.get_columns("trainers")}
    if "experience_years" not in trainer_columns or "availability" not in trainer_columns:
        with op.batch_alter_table("trainers") as batch:
            if "experience_years" not in trainer_columns:
                batch.add_column(sa.Column("experience_years", sa.Integer(), nullable=True))
            if "availability" not in trainer_columns:
                batch.add_column(sa.Column("availability", sa.String(20), server_default="available", nullable=False))

    feedback_columns = {column["name"] for column in inspector.get_columns("learner_feedback")}
    if "feedback_type" not in feedback_columns or "placement_interest" not in feedback_columns or "created_by_id" not in feedback_columns:
        with op.batch_alter_table("learner_feedback") as batch:
            if "feedback_type" not in feedback_columns:
                batch.add_column(sa.Column("feedback_type", sa.String(20), server_default="student", nullable=False))
            if "placement_interest" not in feedback_columns:
                batch.add_column(sa.Column("placement_interest", sa.Boolean(), nullable=True))
            if "created_by_id" not in feedback_columns:
                batch.add_column(sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))

    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("internship_applications")}
    for name, columns, unique in [
        ("ix_internship_applications_selected_domain", ["selected_domain"], False),
        ("ix_internship_applications_student_status", ["student_status"], False),
        ("ix_internship_applications_payment_status", ["payment_status"], False),
        ("ix_internship_applications_next_follow_up_at", ["next_follow_up_at"], False),
        ("ix_internship_applications_google_form_response_id", ["google_form_response_id"], True),
    ]:
        if name not in existing_indexes:
            op.create_index(name, "internship_applications", columns, unique=unique)
    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("internship_attendance")}
    if "uq_intern_attendance_legacy_day" not in existing_indexes:
        op.create_index("uq_intern_attendance_legacy_day", "internship_attendance", ["application_id", "attendance_date"], unique=True,
                        sqlite_where=sa.text("session_id IS NULL"), postgresql_where=sa.text("session_id IS NULL"))
    if "uq_intern_attendance_session" not in existing_indexes:
        op.create_index("uq_intern_attendance_session", "internship_attendance", ["application_id", "session_id"], unique=True,
                        sqlite_where=sa.text("session_id IS NOT NULL"), postgresql_where=sa.text("session_id IS NOT NULL"))


def downgrade() -> None:
    # Keep operational internship records when rolling back application code.
    # A manual data export and reviewed destructive migration are required to drop them.
    pass
