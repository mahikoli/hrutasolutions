from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


StudentStatus = Literal[
    "new_registration", "not_contacted", "contacted", "interested", "not_interested",
    "follow_up_required", "documents_pending", "payment_pending", "payment_verified",
    "eligible", "not_eligible", "ready_for_batch", "batch_assigned", "dropped_out",
    "completed",
]


class StudentCreate(StrictModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    whatsapp_number: str | None = Field(default=None, max_length=30)
    date_of_birth: date | None = None
    college_name: str | None = Field(default=None, max_length=200)
    university: str | None = Field(default=None, max_length=200)
    degree: str | None = Field(default=None, max_length=150)
    department: str | None = Field(default=None, max_length=150)
    current_academic_year: str | None = Field(default=None, max_length=40)
    graduation_year: int | None = Field(default=None, ge=2000, le=2100)
    program_id: int | None = None
    selected_domain: str | None = Field(default=None, max_length=150)
    preferred_duration_weeks: int | None = Field(default=None, gt=0, le=260)
    preferred_mode: Literal["online", "onsite", "hybrid"] | None = None
    technical_skills: str | None = None
    previous_experience: str | None = None
    coordinator_id: int | None = None
    registration_source: str = Field(default="manual", max_length=80)
    payment_option: Literal["paid", "free", "pending", "partial"] = "pending"
    payment_amount: Decimal = Field(default=Decimal("0"), ge=0)
    payment_transaction_id: str | None = Field(default=None, max_length=160)
    payment_status: Literal["pending", "partial", "paid", "free", "rejected", "verified"] = "pending"
    student_status: StudentStatus = "new_registration"
    internal_remarks: str | None = None


class StudentUpdate(StrictModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    whatsapp_number: str | None = Field(default=None, max_length=30)
    date_of_birth: date | None = None
    college_name: str | None = Field(default=None, max_length=200)
    university: str | None = Field(default=None, max_length=200)
    degree: str | None = Field(default=None, max_length=150)
    department: str | None = Field(default=None, max_length=150)
    current_academic_year: str | None = Field(default=None, max_length=40)
    graduation_year: int | None = Field(default=None, ge=2000, le=2100)
    program_id: int | None = None
    selected_domain: str | None = Field(default=None, max_length=150)
    preferred_duration_weeks: int | None = Field(default=None, gt=0, le=260)
    preferred_mode: Literal["online", "onsite", "hybrid"] | None = None
    technical_skills: str | None = None
    previous_experience: str | None = None
    coordinator_id: int | None = None
    payment_option: Literal["paid", "free", "pending", "partial"] | None = None
    payment_amount: Decimal | None = Field(default=None, ge=0)
    payment_transaction_id: str | None = Field(default=None, max_length=160)
    payment_status: Literal["pending", "partial", "paid", "free", "rejected", "verified"] | None = None
    student_status: StudentStatus | None = None
    next_follow_up_at: datetime | None = None
    internal_remarks: str | None = None


class BulkStudentStatus(StrictModel):
    student_ids: list[int] = Field(min_length=1, max_length=500)
    student_status: StudentStatus
    note: str | None = Field(default=None, max_length=1000)


class InternshipFeedbackCreate(StrictModel):
    feedback_type: Literal["student", "trainer"] = "student"
    rating: int = Field(ge=1, le=5)
    comments: str | None = Field(default=None, max_length=5000)
    placement_interest: bool | None = None


class FollowUpCreate(StrictModel):
    notes: str = Field(min_length=1, max_length=5000)
    outcome: str | None = Field(default=None, max_length=120)
    follow_up_at: datetime | None = None
    next_follow_up_at: datetime | None = None


class PaymentCreate(StrictModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_date: date = Field(default_factory=date.today)
    method: str = Field(default="manual", max_length=40)
    transaction_id: str | None = Field(default=None, max_length=160)
    receipt_reference: str | None = Field(default=None, max_length=500)


class BatchCreate(StrictModel):
    program_id: int | None = None
    name: str = Field(min_length=2, max_length=150)
    domain: str = Field(min_length=2, max_length=150)
    duration_weeks: int = Field(gt=0, le=260)
    start_date: date
    end_date: date
    capacity: int = Field(gt=0, le=1000)
    coordinator_id: int | None = None
    trainer_id: int | None = None
    unpaid_approval_required: bool | None = None


class BatchUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    domain: str | None = Field(default=None, min_length=2, max_length=150)
    duration_weeks: int | None = Field(default=None, gt=0, le=260)
    start_date: date | None = None
    end_date: date | None = None
    capacity: int | None = Field(default=None, gt=0, le=1000)
    coordinator_id: int | None = None
    trainer_id: int | None = None
    unpaid_approval_required: bool | None = None


class BatchTransition(StrictModel):
    status: Literal["in_progress", "completed", "cancelled"]


class TrainerAssignment(StrictModel):
    trainer_id: int | None


class TrainerCreate(StrictModel):
    user_id: int | None = None
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    expertise: str | None = None
    experience_years: int | None = Field(default=None, ge=0, le=80)
    availability: Literal["available", "busy", "unavailable"] = "available"


class TrainerUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    expertise: str | None = None
    experience_years: int | None = Field(default=None, ge=0, le=80)
    availability: Literal["available", "busy", "unavailable"] | None = None


class SessionCreate(StrictModel):
    session_number: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=200)
    topic: str | None = Field(default=None, max_length=200)
    description: str | None = None
    trainer_id: int | None = None
    starts_at: datetime
    ends_at: datetime | None = None
    meeting_url: HttpUrl | None = None
    resources: str | None = None


class SessionUpdate(StrictModel):
    session_number: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=2, max_length=200)
    topic: str | None = Field(default=None, max_length=200)
    description: str | None = None
    trainer_id: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    meeting_url: HttpUrl | None = None
    resources: str | None = None
    status: Literal["scheduled", "completed", "cancelled"] | None = None
    remarks: str | None = None


class AttendanceCreate(StrictModel):
    session_id: int
    application_id: int
    status: Literal["present", "absent", "late", "excused"]
    notes: str | None = None


class AssignmentCreate(StrictModel):
    batch_id: int
    title: str = Field(min_length=2, max_length=200)
    description: str | None = None
    due_at: datetime | None = None
    max_score: Decimal = Field(default=Decimal("100"), gt=0, max_digits=8, decimal_places=2)


class SubmissionCreate(StrictModel):
    application_id: int
    submission_link: HttpUrl | None = None
    submission_text: str | None = None


class SubmissionReview(StrictModel):
    status: Literal["evaluated", "rejected_resubmission"]
    score: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    feedback: str | None = None


class EvaluationCreate(StrictModel):
    batch_id: int
    application_id: int
    criterion_scores: dict[str, float] = Field(default_factory=dict)
    result: Literal["evaluation_pending", "under_evaluation", "passed", "needs_improvement", "failed", "reevaluation_required"] = "under_evaluation"
    trainer_feedback: str | None = None
    final_project_details: str | None = None
    completion_date: date | None = None


class EvaluationApproval(StrictModel):
    approved: bool
    admin_remarks: str | None = None


class SettingsUpdate(StrictModel):
    attendance_threshold: int = Field(default=75, ge=0, le=100)
    passing_score: float = Field(default=60, ge=0, le=100)
    unpaid_batch_approval_required: bool = True
    evaluation_weights: dict[str, float] = Field(default_factory=lambda: {
        "attendance": 20, "technical_knowledge": 20, "assignments": 15,
        "practical_implementation": 15, "project_quality": 15,
        "communication": 5, "participation": 5, "problem_solving": 5,
    })


class FormWebhookPayload(StrictModel):
    response_id: str = Field(min_length=1, max_length=160)
    values: dict[str, str | int | float | bool | None]
