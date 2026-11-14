import csv
import hmac
import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db, settings
from ..internship_schemas import (
    AssignmentCreate, AttendanceCreate, BatchCreate, BatchTransition, BatchUpdate, BulkStudentStatus,
    EvaluationApproval, InternshipFeedbackCreate,
    EvaluationCreate, FollowUpCreate, FormWebhookPayload, PaymentCreate, SessionCreate,
    SessionUpdate, SettingsUpdate, StudentCreate, StudentUpdate, SubmissionCreate,
    SubmissionReview, TrainerAssignment, TrainerCreate, TrainerUpdate,
)
from ..models import (
    AppConfiguration, AuditLog, DocumentReference, InternshipApplication, InternshipAssignment,
    InternshipAttendance, InternshipBatch, InternshipBatchStudent, InternshipCertificate, InternshipTask,
    InternshipEvaluation, InternshipFollowUp, InternshipPayment, InternshipStatusHistory,
    InternshipSubmission, InternshipSyncRun, InternshipTrainingSession, InternshipProgram, LearnerFeedback,
    Lead, Notification, Role, Trainer, User,
)
from ..security import get_current_user, require_roles

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/internship-management", tags=["Internship Management"])

ADMIN = ("Super Admin", "Management")
COORDINATORS = ("Super Admin", "Management", "Internship Coordinator", "Employee / Intern")
TRAINERS = ("Super Admin", "Management", "Internship Coordinator", "Training Coordinator", "Trainer / Teacher")
FINANCE = ("Super Admin", "Management", "Finance / Accounts")
STUDENT_STATUSES = (
    "new_registration", "not_contacted", "contacted", "interested", "not_interested",
    "follow_up_required", "documents_pending", "payment_pending", "payment_verified",
    "eligible", "not_eligible", "ready_for_batch", "batch_assigned", "dropped_out", "completed",
)
ACTIVE_BATCH_STATUSES = {"confirmed", "in_progress"}
DEFAULT_SETTINGS = {
    "attendance_threshold": 75,
    "passing_score": 60,
    "unpaid_batch_approval_required": True,
    "evaluation_weights": {
        "attendance": 20, "technical_knowledge": 20, "assignments": 15,
        "practical_implementation": 15, "project_quality": 15,
        "communication": 5, "participation": 5, "problem_solving": 5,
    },
}


def role_names(user: User) -> set[str]:
    return {role.name for role in user.roles}


def is_manager(user: User) -> bool:
    return bool(role_names(user).intersection(ADMIN))


def audit(db: Session, user: User | None, action: str, entity: str, entity_id: int | str, details: str | None = None):
    db.add(AuditLog(user_id=user.id if user else None, action=action, entity_type=entity, entity_id=str(entity_id), details=details))


def record_or_404(db: Session, model, record_id: int, label: str):
    record = db.get(model, record_id)
    if record is None:
        raise HTTPException(404, f"{label} not found")
    return record


def require_trainer_batch(db: Session, batch: InternshipBatch, user: User):
    if "Trainer / Teacher" not in role_names(user) or is_manager(user):
        return
    trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
    if not trainer or batch.trainer_id != trainer.id:
        raise HTTPException(403, "This batch is not assigned to you")


def require_student_access(db: Session, application: InternshipApplication, user: User):
    if is_manager(user) or "Training Coordinator" in role_names(user):
        return
    if role_names(user).intersection({"Internship Coordinator", "Employee / Intern"}) and application.coordinator_id in {None, user.id}:
        return
    if "Trainer / Teacher" in role_names(user):
        trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
        if trainer and db.query(InternshipBatchStudent.id).join(InternshipBatch).filter(
            InternshipBatchStudent.application_id == application.id,
            InternshipBatch.trainer_id == trainer.id,
        ).first():
            return
    raise HTTPException(403, "You do not have access to this student")


def require_batch_access(db: Session, batch: InternshipBatch, user: User):
    roles = role_names(user)
    if is_manager(user) or "Training Coordinator" in roles:
        return
    if roles.intersection({"Internship Coordinator", "Employee / Intern"}) and batch.coordinator_id == user.id:
        return
    require_trainer_batch(db, batch, user)
    if "Trainer / Teacher" not in roles:
        raise HTTPException(403, "You do not have access to this batch")


def settings_values(db: Session) -> dict:
    row = db.get(AppConfiguration, "internship_management")
    return {**DEFAULT_SETTINGS, **(row.value if row and isinstance(row.value, dict) else {})}


def split_name(full_name: str) -> tuple[str, str | None]:
    parts = full_name.strip().split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else None


def normalize_phone(value: str | None) -> str | None:
    return "".join(ch for ch in (value or "") if ch.isdigit()) or None


def find_duplicate(db: Session, email: str, phone: str | None, exclude_id: int | None = None):
    query = db.query(InternshipApplication).filter(func.lower(InternshipApplication.email) == email.lower())
    if exclude_id:
        query = query.filter(InternshipApplication.id != exclude_id)
    duplicate = query.first()
    if not duplicate and phone:
        query = db.query(InternshipApplication).filter(InternshipApplication.phone.is_not(None))
        if exclude_id:
            query = query.filter(InternshipApplication.id != exclude_id)
        duplicate = next((row for row in query.all() if normalize_phone(row.phone) == normalize_phone(phone)), None)
    return duplicate


def make_lead(db: Session, full_name: str, email: str | None, phone: str | None,
              college: str | None, domain: str | None, source: str, owner_id: int | None):
    first_name, last_name = split_name(full_name)
    lead = Lead(
        first_name=first_name, last_name=last_name, email=email, phone=phone,
        organization_name=college, source=source[:60], interest=(domain or "internship")[:80],
        priority="medium", status="new", notes="Student internship registration",
        owner_id=owner_id,
    )
    db.add(lead)
    db.flush()
    return lead


def notify_internship_coordinators(db: Session, title: str, message: str, related_type: str, related_id: int):
    recipients = db.query(User).join(User.roles).filter(Role.name.in_({"Internship Coordinator", "Training Coordinator"})).distinct().all()
    for recipient in recipients:
        db.add(Notification(user_id=recipient.id, title=title, message=message,
                            related_type=related_type, related_id=related_id))


def filtered_students(db: Session, user: User, search: str | None = None, domain: str | None = None,
                      college: str | None = None, payment_status: str | None = None,
                      student_status: str | None = None, registered_from: date | None = None,
                      registered_to: date | None = None):
    query = db.query(InternshipApplication)
    if not is_manager(user):
        if role_names(user).intersection({"Internship Coordinator", "Employee / Intern"}):
            query = query.filter(or_(InternshipApplication.coordinator_id == user.id, InternshipApplication.coordinator_id.is_(None)))
        elif "Trainer / Teacher" in role_names(user):
            trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
            ids = db.query(InternshipBatchStudent.application_id).join(InternshipBatch).filter(
                InternshipBatch.trainer_id == trainer.id if trainer else False
            )
            query = query.filter(InternshipApplication.id.in_(ids))
        elif "Training Coordinator" in role_names(user):
            pass
        else:
            raise HTTPException(403, "Your role cannot access internship students")
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(or_(InternshipApplication.full_name.ilike(like), InternshipApplication.email.ilike(like),
                                 InternshipApplication.phone.ilike(like), InternshipApplication.college_name.ilike(like),
                                 InternshipApplication.selected_domain.ilike(like)))
    if domain:
        query = query.filter(InternshipApplication.selected_domain.ilike(f"%{domain.strip()}%"))
    if college:
        query = query.filter(InternshipApplication.college_name.ilike(f"%{college.strip()}%"))
    if payment_status:
        query = query.filter(InternshipApplication.payment_status == payment_status)
    if student_status:
        query = query.filter(InternshipApplication.student_status == student_status)
    if registered_from:
        query = query.filter(InternshipApplication.applied_at >= datetime.combine(registered_from, datetime.min.time()))
    if registered_to:
        query = query.filter(InternshipApplication.applied_at < datetime.combine(registered_to + timedelta(days=1), datetime.min.time()))
    return query


def student_profile(db: Session, application: InternshipApplication) -> dict:
    docs = db.query(DocumentReference).filter_by(entity_type="application", entity_id=application.id).order_by(DocumentReference.created_at.desc()).all()
    memberships = db.query(InternshipBatchStudent, InternshipBatch).join(
        InternshipBatch, InternshipBatch.id == InternshipBatchStudent.batch_id
    ).filter(InternshipBatchStudent.application_id == application.id).all()
    return {
        "student": application,
        "followups": db.query(InternshipFollowUp).filter_by(application_id=application.id).order_by(InternshipFollowUp.follow_up_at.desc()).limit(200).all(),
        "payments": db.query(InternshipPayment).filter_by(application_id=application.id).order_by(InternshipPayment.payment_date.desc()).all(),
        "feedback": db.query(LearnerFeedback).filter_by(application_id=application.id).order_by(LearnerFeedback.created_at.desc()).all(),
        "status_history": db.query(InternshipStatusHistory).filter_by(application_id=application.id).order_by(InternshipStatusHistory.changed_at.desc()).all(),
        "documents": docs,
        "batches": [{"membership": member, "batch": batch} for member, batch in memberships],
    }


@router.get("/overview")
def internship_overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    allowed = role_names(user).intersection(set(COORDINATORS) | {"Training Coordinator", "Trainer / Teacher"})
    if not allowed:
        raise HTTPException(403, "Your role cannot access internship management")
    student_query = filtered_students(db, user)
    batches = db.query(InternshipBatch)
    if not is_manager(user):
        if "Trainer / Teacher" in role_names(user):
            trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
            batches = batches.filter(InternshipBatch.trainer_id == (trainer.id if trainer else -1))
        elif role_names(user).intersection({"Internship Coordinator", "Employee / Intern"}):
            batches = batches.filter(InternshipBatch.coordinator_id == user.id)
    statuses = dict(db.query(InternshipApplication.student_status, func.count(InternshipApplication.id)).filter(
        InternshipApplication.id.in_(student_query.with_entities(InternshipApplication.id))
    ).group_by(InternshipApplication.student_status).all())
    payments = dict(db.query(InternshipApplication.payment_status, func.count(InternshipApplication.id)).filter(
        InternshipApplication.id.in_(student_query.with_entities(InternshipApplication.id))
    ).group_by(InternshipApplication.payment_status).all())
    due = student_query.filter(InternshipApplication.next_follow_up_at.is_not(None), InternshipApplication.next_follow_up_at <= datetime.utcnow() + timedelta(days=7)).order_by(InternshipApplication.next_follow_up_at).limit(10).all()
    pending_payment = student_query.filter(InternshipApplication.payment_status.in_(["pending", "partial", "rejected"])).order_by(InternshipApplication.applied_at.desc()).limit(10).all()
    sessions = db.query(InternshipTrainingSession).join(InternshipBatch).filter(
        InternshipTrainingSession.starts_at >= datetime.utcnow(), InternshipTrainingSession.status == "scheduled"
    )
    if not is_manager(user):
        if "Trainer / Teacher" in role_names(user):
            trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
            sessions = sessions.filter(InternshipBatch.trainer_id == (trainer.id if trainer else -1))
        elif role_names(user).intersection({"Internship Coordinator", "Employee / Intern"}):
            sessions = sessions.filter(InternshipBatch.coordinator_id == user.id)
    recent = student_query.order_by(InternshipApplication.applied_at.desc()).limit(8).all()
    total = student_query.count()
    confirmed_batches = batches.filter(InternshipBatch.status.in_(["confirmed", "in_progress", "completed"])).count()
    active_batches = batches.filter(InternshipBatch.status == "in_progress").count()
    active_interns = db.query(InternshipBatchStudent.application_id).join(InternshipBatch).filter(
        InternshipBatchStudent.is_active.is_(True), InternshipBatch.status == "in_progress",
        InternshipBatch.id.in_(batches.with_entities(InternshipBatch.id)),
    ).distinct().count()
    pending_batch_approvals = batches.filter(InternshipBatch.status == "pending_approval").count()
    low_attendance = []
    for application in student_query.filter(InternshipApplication.student_status == "batch_assigned").limit(100).all():
        entries = db.query(InternshipAttendance).filter_by(application_id=application.id).count()
        completed_session_count = db.query(InternshipTrainingSession.id).join(InternshipBatch).join(
            InternshipBatchStudent, InternshipBatchStudent.batch_id == InternshipBatch.id
        ).filter(InternshipBatchStudent.application_id == application.id,
                 InternshipBatchStudent.is_active.is_(True), InternshipTrainingSession.status == "completed").count()
        expected = max(entries, completed_session_count)
        if not expected:
            continue
        attended = db.query(InternshipAttendance).filter(
            InternshipAttendance.application_id == application.id,
            InternshipAttendance.status.in_(["present", "late"]),
        ).count()
        percent = round(attended * 100 / expected)
        if percent < settings_values(db)["attendance_threshold"]:
            low_attendance.append({"student": application, "attendance_percent": percent})
    missing_assignments = []
    delayed_cutoff = datetime.utcnow()
    active_rosters = db.query(InternshipBatchStudent, InternshipBatch, InternshipApplication).join(
        InternshipBatch, InternshipBatch.id == InternshipBatchStudent.batch_id
    ).join(InternshipApplication, InternshipApplication.id == InternshipBatchStudent.application_id).filter(
        InternshipBatchStudent.is_active.is_(True), InternshipBatch.status.in_(ACTIVE_BATCH_STATUSES),
        InternshipApplication.id.in_(student_query.with_entities(InternshipApplication.id)),
    ).all()
    for membership, batch, application in active_rosters:
        due_assignments = db.query(InternshipAssignment).filter(InternshipAssignment.batch_id == batch.id,
                                                               InternshipAssignment.due_at < delayed_cutoff).all()
        for assignment in due_assignments:
            submission = db.query(InternshipSubmission).filter_by(assignment_id=assignment.id, application_id=application.id).first()
            if not submission or submission.status in {"rejected_resubmission", "not_started", "in_progress"}:
                missing_assignments.append({"student": application, "assignment": assignment, "batch": batch})
    inactive_students = []
    for membership, batch, application in active_rosters:
        latest_attendance = db.query(func.max(InternshipAttendance.attendance_date)).filter_by(application_id=application.id).scalar()
        if latest_attendance is None or latest_attendance < date.today() - timedelta(days=14):
            inactive_students.append({"student": application, "batch": batch, "last_attendance": latest_attendance})
    poor_performance = [
        evaluation for evaluation in db.query(InternshipEvaluation).filter(
            InternshipEvaluation.application_id.in_(student_query.with_entities(InternshipApplication.id)),
            InternshipEvaluation.performance_score < settings_values(db)["passing_score"],
        ).order_by(InternshipEvaluation.performance_score.asc()).limit(10).all()
    ]
    pending_reviews = db.query(InternshipSubmission).join(InternshipAssignment).join(InternshipBatch).filter(
        InternshipSubmission.status.in_({"submitted", "late_submission"}),
        InternshipBatch.id.in_(batches.with_entities(InternshipBatch.id)),
    ).order_by(InternshipSubmission.submitted_at.asc()).limit(10).all()
    return {
        "total_registrations": total,
        "new_registrations": statuses.get("new_registration", 0),
        "students_contacted": sum(statuses.get(key, 0) for key in ("contacted", "interested", "not_interested", "follow_up_required")),
        "interested_students": statuses.get("interested", 0),
        "eligible_students": statuses.get("eligible", 0) + statuses.get("ready_for_batch", 0),
        "paid_students": payments.get("paid", 0),
        "active_interns": active_interns,
        "pending_batch_approvals": pending_batch_approvals,
        "free_students": payments.get("free", 0),
        "unpaid_students": sum(payments.get(key, 0) for key in ("pending", "partial", "rejected")),
        "confirmed_batches": confirmed_batches,
        "active_batches": active_batches,
        "completed_internships": statuses.get("completed", 0),
        "status_distribution": [{"status": key, "count": value} for key, value in sorted(statuses.items())],
        "payment_distribution": [{"status": key, "count": value} for key, value in sorted(payments.items())],
        "domain_distribution": [
            {"domain": domain or "Unspecified", "count": count}
            for domain, count in db.query(InternshipApplication.selected_domain, func.count(InternshipApplication.id)).filter(
                InternshipApplication.id.in_(student_query.with_entities(InternshipApplication.id))
            ).group_by(InternshipApplication.selected_domain).order_by(func.count(InternshipApplication.id).desc()).limit(8).all()
        ],
        "recent_registrations": recent,
        "upcoming_followups": due,
        "pending_payment_verification": pending_payment,
        "upcoming_sessions": sessions.order_by(InternshipTrainingSession.starts_at).limit(8).all(),
        "low_attendance_students": low_attendance[:8],
        "missing_assignments": missing_assignments[:10],
        "inactive_students": inactive_students[:10],
        "poor_performance_students": poor_performance,
        "pending_assignment_reviews": pending_reviews,
        "batches": batches.order_by(InternshipBatch.start_date.desc()).limit(12).all(),
        "total_batches": batches.count(),
    }


@router.get("/students")
def list_students(
    search: str | None = None, domain: str | None = None, college: str | None = None,
    payment_status: str | None = None, student_status: str | None = None,
    registered_from: date | None = None, registered_to: date | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    query = filtered_students(db, user, search, domain, college, payment_status, student_status, registered_from, registered_to)
    total = query.count()
    items = query.order_by(InternshipApplication.applied_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/students", status_code=201)
def create_student(data: StudentCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*COORDINATORS))):
    email = str(data.email).lower()
    phone = data.phone.strip() if data.phone else None
    duplicate = find_duplicate(db, email, phone)
    if duplicate:
        raise HTTPException(409, f"A student with this email or mobile already exists (student #{duplicate.id})")
    if data.payment_transaction_id and db.query(InternshipPayment).filter_by(transaction_id=data.payment_transaction_id).first():
        raise HTTPException(409, "That payment transaction ID is already recorded")
    if data.program_id and db.get(InternshipProgram, data.program_id) is None:
        raise HTTPException(404, "Internship program not found")
    owner_id = data.coordinator_id if is_manager(user) and data.coordinator_id else user.id
    if data.coordinator_id and not is_manager(user):
        raise HTTPException(403, "Only a manager can assign a different coordinator")
    values = data.model_dump(exclude={"email", "full_name", "coordinator_id", "payment_status", "payment_transaction_id"})
    if not values.get("selected_domain") and data.program_id:
        values["selected_domain"] = db.get(InternshipProgram, data.program_id).domain
    lead = make_lead(db, data.full_name, email, phone, data.college_name, values.get("selected_domain"), data.registration_source, owner_id)
    application = InternshipApplication(
        **values, full_name=data.full_name.strip(), email=email, phone=phone, lead_id=lead.id,
        coordinator_id=owner_id, payment_status="free" if data.payment_option == "free" else "pending",
        payment_transaction_id=None, sync_status="not_synced", updated_by_id=user.id,
    )
    db.add(application)
    db.flush()
    if data.payment_transaction_id and data.payment_amount > 0 and data.payment_option != "free":
        application.payment_transaction_id = data.payment_transaction_id
        db.add(InternshipPayment(application_id=application.id, amount=data.payment_amount,
                                 transaction_id=data.payment_transaction_id, status="pending", method="manual"))
    db.add(InternshipStatusHistory(application_id=application.id, from_status=None, to_status=application.student_status, changed_by_id=user.id, note="Registration created"))
    db.add(Notification(user_id=owner_id, title="New internship registration", message=f"{application.full_name} registered for {application.selected_domain or 'an internship program'}.", related_type="internship_application", related_id=application.id))
    audit(db, user, "internship_student.created", "internship_application", application.id, f"lead_id={lead.id}; source={application.registration_source}")
    db.commit()
    db.refresh(application)
    return application


@router.post("/students/bulk-status")
def bulk_update_student_status(data: BulkStudentStatus, db: Session = Depends(get_db), user: User = Depends(require_roles(*COORDINATORS))):
    ids = list(dict.fromkeys(data.student_ids))
    students = db.query(InternshipApplication).filter(InternshipApplication.id.in_(ids)).all()
    if len(students) != len(ids):
        raise HTTPException(404, "One or more selected students were not found")
    for application in students:
        require_student_access(db, application, user)
    for application in students:
        if application.student_status == data.student_status:
            continue
        db.add(InternshipStatusHistory(application_id=application.id, from_status=application.student_status,
                                       to_status=data.student_status, changed_by_id=user.id, note=data.note or "Bulk status update"))
        application.student_status = data.student_status
        application.updated_by_id = user.id
    audit(db, user, "internship_students.bulk_status_updated", "internship_application", ",".join(map(str, ids)), data.student_status)
    db.commit()
    return {"updated": len(students), "student_status": data.student_status}


@router.get("/students/{student_id}")
def get_student(student_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    application = record_or_404(db, InternshipApplication, student_id, "Student")
    require_student_access(db, application, user)
    return student_profile(db, application)


@router.post("/students/{student_id}/feedback", status_code=201)
def add_internship_feedback(student_id: int, data: InternshipFeedbackCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*TRAINERS))):
    application = record_or_404(db, InternshipApplication, student_id, "Student")
    require_student_access(db, application, user)
    roles = role_names(user)
    if data.feedback_type == "student" and not roles.intersection(set(COORDINATORS) | {"Training Coordinator"}):
        raise HTTPException(403, "Only coordinators can record student satisfaction feedback")
    feedback = LearnerFeedback(application_id=student_id, feedback_type=data.feedback_type, rating=data.rating,
                               comments=data.comments, placement_interest=data.placement_interest, created_by_id=user.id)
    db.add(feedback)
    db.flush()
    audit(db, user, "internship_feedback.created", "learner_feedback", feedback.id, data.feedback_type)
    db.commit()
    db.refresh(feedback)
    return feedback


@router.patch("/students/{student_id}")
def update_student(student_id: int, data: StudentUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles(*COORDINATORS))):
    application = record_or_404(db, InternshipApplication, student_id, "Student")
    require_student_access(db, application, user)
    changes = data.model_dump(exclude_unset=True)
    roles = role_names(user)
    if "coordinator_id" in changes and not is_manager(user):
        if not roles.intersection({"Internship Coordinator", "Employee / Intern"}) or changes["coordinator_id"] != user.id or application.coordinator_id is not None:
            raise HTTPException(403, "You may assign an unassigned student record to yourself; only managers may reassign students")
    if "payment_status" in changes:
        # Payment state transitions are handled by the verification endpoint.
        if changes["payment_status"] != application.payment_status or not roles.intersection(FINANCE):
            raise HTTPException(403, "Use the payment verification action to change payment status")
    if changes.get("program_id"):
        from ..models import InternshipProgram
        if not db.get(InternshipProgram, changes["program_id"]):
            raise HTTPException(404, "Internship program not found")
    if "coordinator_id" in changes:
        if changes["coordinator_id"] is not None:
            record_or_404(db, User, changes["coordinator_id"], "Assigned employee")
        if changes["coordinator_id"] and changes["coordinator_id"] != application.coordinator_id:
            db.add(Notification(user_id=changes["coordinator_id"], title="Student assigned to you",
                                message=f"{application.full_name} has been assigned to you for internship follow-up.",
                                related_type="internship_application", related_id=application.id))
    new_phone = changes.get("phone", application.phone)
    duplicate = find_duplicate(db, application.email, new_phone, exclude_id=application.id)
    if duplicate:
        raise HTTPException(409, f"Another student already uses this mobile number (student #{duplicate.id})")
    if "student_status" in changes and changes["student_status"] != application.student_status:
        db.add(InternshipStatusHistory(application_id=application.id, from_status=application.student_status,
                                       to_status=changes["student_status"], changed_by_id=user.id,
                                       note=changes.pop("status_note", None)))
    changes.pop("payment_status", None)
    for field, value in changes.items():
        setattr(application, field, value)
    application.updated_by_id = user.id
    audit(db, user, "internship_student.updated", "internship_application", application.id, ",".join(changes))
    db.commit()
    db.refresh(application)
    return application


@router.get("/export/students.csv")
def export_students(
    domain: str | None = None, college: str | None = None, payment_status: str | None = None,
    student_status: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    query = filtered_students(db, user, domain=domain, college=college, payment_status=payment_status, student_status=student_status)
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Student ID", "Name", "Email", "Mobile", "College", "Domain", "Registered", "Payment", "Student status", "Coordinator", "Next follow-up"])
    for row in query.order_by(InternshipApplication.applied_at.desc()).limit(10000):
        writer.writerow([row.id, row.full_name, row.email, row.phone or "", row.college_name or "", row.selected_domain or "",
                         row.applied_at.isoformat(), row.payment_status, row.student_status, row.coordinator_id or "",
                         row.next_follow_up_at.isoformat() if row.next_follow_up_at else ""])
    stream.seek(0)
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=internship-students.csv"})


@router.get("/followups")
def list_followups(upcoming_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(InternshipFollowUp).join(InternshipApplication)
    if not is_manager(user):
        if role_names(user).intersection({"Internship Coordinator", "Employee / Intern"}):
            query = query.filter(or_(InternshipApplication.coordinator_id == user.id, InternshipApplication.coordinator_id.is_(None)))
        elif "Trainer / Teacher" in role_names(user):
            trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
            query = query.join(InternshipBatchStudent).join(InternshipBatch).filter(InternshipBatch.trainer_id == (trainer.id if trainer else -1))
        elif "Training Coordinator" in role_names(user):
            pass
        else:
            raise HTTPException(403, "Your role cannot access follow-ups")
    if upcoming_only:
        query = query.filter(InternshipFollowUp.next_follow_up_at >= datetime.utcnow())
    return query.order_by(InternshipFollowUp.next_follow_up_at.asc().nullslast(), InternshipFollowUp.follow_up_at.desc()).limit(500).all()


@router.post("/students/{student_id}/followups", status_code=201)
def add_followup(student_id: int, data: FollowUpCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*COORDINATORS))):
    application = record_or_404(db, InternshipApplication, student_id, "Student")
    require_student_access(db, application, user)
    record = InternshipFollowUp(application_id=student_id, created_by_id=user.id,
                                follow_up_at=data.follow_up_at or datetime.utcnow(), outcome=data.outcome,
                                notes=data.notes, next_follow_up_at=data.next_follow_up_at)
    db.add(record)
    application.next_follow_up_at = data.next_follow_up_at
    if data.next_follow_up_at:
        old_status = application.student_status
        application.student_status = "follow_up_required"
        if old_status != application.student_status:
            db.add(InternshipStatusHistory(application_id=student_id, from_status=old_status,
                                           to_status=application.student_status, changed_by_id=user.id,
                                           note="Follow-up scheduled"))
    audit(db, user, "internship_followup.created", "internship_followup", student_id)
    db.commit()
    db.refresh(record)
    return record


@router.post("/students/{student_id}/payments", status_code=201)
def add_payment(student_id: int, data: PaymentCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*COORDINATORS))):
    application = record_or_404(db, InternshipApplication, student_id, "Student")
    require_student_access(db, application, user)
    if data.transaction_id and db.query(InternshipPayment).filter_by(transaction_id=data.transaction_id).first():
        raise HTTPException(409, "That payment transaction ID is already recorded")
    record = InternshipPayment(application_id=student_id, amount=data.amount, payment_date=data.payment_date,
                               method=data.method, transaction_id=data.transaction_id,
                               receipt_reference=data.receipt_reference, status="pending")
    db.add(record)
    application.payment_status = "pending"
    application.payment_transaction_id = data.transaction_id or application.payment_transaction_id
    application.student_status = "payment_pending"
    audit(db, user, "internship_payment.created", "internship_payment", student_id, f"payment_id={record.id}; amount={data.amount}")
    db.commit()
    db.refresh(record)
    return record


@router.patch("/payments/{payment_id}/verify")
def verify_payment(payment_id: int, approved: bool = Query(...), db: Session = Depends(get_db), user: User = Depends(require_roles(*FINANCE))):
    payment = record_or_404(db, InternshipPayment, payment_id, "Payment")
    if payment.status != "pending":
        raise HTTPException(409, "Only pending payments can be verified")
    application = record_or_404(db, InternshipApplication, payment.application_id, "Student")
    payment.status = "verified" if approved else "rejected"
    payment.verified_by_id = user.id
    payment.verified_at = datetime.utcnow()
    total_verified = db.query(func.coalesce(func.sum(InternshipPayment.amount), 0)).filter(
        InternshipPayment.application_id == application.id, InternshipPayment.status == "verified"
    ).scalar()
    if application.payment_option == "free":
        application.payment_status = "free"
    elif not approved:
        application.payment_status = "rejected"
    elif Decimal(str(total_verified or 0)) >= application.payment_amount and application.payment_amount > 0:
        application.payment_status = "paid"
        if application.student_status in {"payment_pending", "payment_verified"}:
            application.student_status = "payment_verified"
    else:
        application.payment_status = "partial" if total_verified else "pending"
    audit(db, user, "internship_payment.verified" if approved else "internship_payment.rejected", "internship_payment", payment.id)
    if application.coordinator_id:
        db.add(Notification(user_id=application.coordinator_id,
                            title="Student payment verified" if approved else "Student payment rejected",
                            message=f"Payment for {application.full_name} was {'verified' if approved else 'rejected'}.",
                            related_type="internship_application", related_id=application.id))
    db.commit()
    db.refresh(payment)
    return {"payment": payment, "payment_status": application.payment_status, "student_status": application.student_status}


@router.get("/payments")
def list_payments(status: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    roles = role_names(user)
    if not roles.intersection(set(FINANCE) | {"Internship Coordinator", "Employee / Intern"}):
        raise HTTPException(403, "Your role cannot access internship payments")
    query = db.query(InternshipPayment)
    if status:
        query = query.filter(InternshipPayment.status == status)
    if not is_manager(user) and "Finance / Accounts" not in roles:
        query = query.join(InternshipApplication).filter(or_(InternshipApplication.coordinator_id == user.id,
                                                             InternshipApplication.coordinator_id.is_(None)))
    return query.order_by(InternshipPayment.created_at.desc()).limit(1000).all()


def batch_dict(db: Session, batch: InternshipBatch) -> dict:
    students = db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, is_active=True).all()
    trainer = db.get(Trainer, batch.trainer_id) if batch.trainer_id else None
    return {"id": batch.id, "program_id": batch.program_id, "name": batch.name, "domain": batch.domain,
            "duration_weeks": batch.duration_weeks, "start_date": batch.start_date, "end_date": batch.end_date,
            "capacity": batch.capacity, "coordinator_id": batch.coordinator_id, "trainer_id": batch.trainer_id,
            "trainer_name": trainer.name if trainer else None, "status": batch.status,
            "unpaid_approval_required": batch.unpaid_approval_required, "confirmed_by_id": batch.confirmed_by_id,
            "confirmed_at": batch.confirmed_at, "student_count": len(students), "available_capacity": max(0, batch.capacity-len(students)),
            "students": [{"membership": item, "student": db.get(InternshipApplication, item.application_id)} for item in students]}


@router.get("/batches")
def list_batches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    roles = role_names(user)
    if not roles.intersection(set(COORDINATORS) | {"Training Coordinator", "Trainer / Teacher"}):
        raise HTTPException(403, "Your role cannot access internship batches")
    query = db.query(InternshipBatch)
    if not is_manager(user):
        if "Trainer / Teacher" in roles:
            trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
            query = query.filter(InternshipBatch.trainer_id == (trainer.id if trainer else -1))
        elif roles.intersection({"Internship Coordinator", "Employee / Intern"}):
            query = query.filter(InternshipBatch.coordinator_id == user.id)
    return [batch_dict(db, row) for row in query.order_by(InternshipBatch.start_date.desc()).limit(500).all()]


@router.post("/batches", status_code=201)
def create_batch(data: BatchCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*COORDINATORS))):
    if data.end_date < data.start_date:
        raise HTTPException(422, "Batch end date cannot be before its start date")
    if db.query(InternshipBatch).filter_by(name=data.name).first():
        raise HTTPException(409, "A batch with this name already exists")
    if data.program_id:
        from ..models import InternshipProgram
        program = record_or_404(db, InternshipProgram, data.program_id, "Internship program")
        if program.domain and program.domain.casefold() != data.domain.casefold():
            raise HTTPException(422, "Batch domain must match the selected internship program")
    if data.trainer_id:
        trainer = record_or_404(db, Trainer, data.trainer_id, "Trainer")
        if trainer.availability == "unavailable":
            raise HTTPException(409, "This trainer is marked unavailable")
    if data.coordinator_id and not is_manager(user):
        raise HTTPException(403, "Only a manager can assign a different batch coordinator")
    config = settings_values(db)
    values = data.model_dump()
    values["coordinator_id"] = data.coordinator_id or user.id
    values["unpaid_approval_required"] = (config["unpaid_batch_approval_required"]
                                           if data.unpaid_approval_required is None
                                           else data.unpaid_approval_required)
    batch = InternshipBatch(**values)
    db.add(batch)
    db.flush()
    if batch.coordinator_id and batch.coordinator_id != user.id:
        db.add(Notification(user_id=batch.coordinator_id, title="Internship batch assigned",
                            message=f"You are coordinating the new batch {batch.name}.",
                            related_type="internship_batch", related_id=batch.id))
    assigned_trainer = db.get(Trainer, batch.trainer_id) if batch.trainer_id else None
    if assigned_trainer and assigned_trainer.user_id:
        db.add(Notification(user_id=assigned_trainer.user_id, title="Internship batch assigned",
                            message=f"You have been assigned to the new batch {batch.name}.",
                            related_type="internship_batch", related_id=batch.id))
    audit(db, user, "internship_batch.created", "internship_batch", batch.id)
    db.commit()
    db.refresh(batch)
    return batch_dict(db, batch)


@router.patch("/batches/{batch_id}")
def update_batch(batch_id: int, data: BatchUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = record_or_404(db, InternshipBatch, batch_id, "Batch")
    require_batch_access(db, batch, user)
    if batch.status not in {"draft", "student_selection"}:
        raise HTTPException(409, "Batch details and roster are locked after confirmation")
    changes = data.model_dump(exclude_unset=True)
    start = changes.get("start_date", batch.start_date)
    end = changes.get("end_date", batch.end_date)
    if start and end and end < start:
        raise HTTPException(422, "Batch end date cannot be before its start date")
    if changes.get("capacity") is not None and changes["capacity"] < db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, is_active=True).count():
        raise HTTPException(409, "Capacity cannot be set below the number of selected students")
    if "trainer_id" in changes:
        if changes["trainer_id"] is not None:
            record_or_404(db, Trainer, changes["trainer_id"], "Trainer")
        if not is_manager(user):
            raise HTTPException(403, "Only a manager can assign or reassign a trainer")
    if "coordinator_id" in changes:
        if not is_manager(user):
            raise HTTPException(403, "Only a manager can reassign a batch coordinator")
        if changes["coordinator_id"] is not None:
            record_or_404(db, User, changes["coordinator_id"], "Batch coordinator")
    previous_trainer = batch.trainer_id
    for key, value in changes.items():
        setattr(batch, key, str(value) if key == "meeting_url" and value else value)
    audit(db, user, "internship_batch.updated", "internship_batch", batch.id, ",".join(changes))
    if batch.trainer_id and batch.trainer_id != previous_trainer:
        trainer = db.get(Trainer, batch.trainer_id)
        if trainer and trainer.user_id:
            db.add(Notification(user_id=trainer.user_id, title="Internship batch assigned",
                                message=f"You have been assigned to {batch.name}.",
                                related_type="internship_batch", related_id=batch.id))
    db.commit()
    db.refresh(batch)
    return batch_dict(db, batch)


@router.post("/batches/{batch_id}/students", status_code=201)
def add_batch_students(batch_id: int, application_ids: list[int], db: Session = Depends(get_db), user: User = Depends(require_roles(*COORDINATORS))):
    batch = record_or_404(db, InternshipBatch, batch_id, "Batch")
    require_batch_access(db, batch, user)
    if batch.status not in {"draft", "student_selection"}:
        raise HTTPException(409, "Confirmed batch roster is locked")
    current = db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, is_active=True).count()
    unique_ids = list(dict.fromkeys(application_ids))
    if not unique_ids:
        raise HTTPException(422, "Choose at least one student")
    new_ids = [student_id for student_id in unique_ids if not db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, application_id=student_id, is_active=True).first()]
    if current + len(new_ids) > batch.capacity:
        raise HTTPException(409, f"Batch capacity is {batch.capacity}; {batch.capacity-current} seats remain")
    for student_id in unique_ids:
        application = record_or_404(db, InternshipApplication, student_id, "Student")
        require_student_access(db, application, user)
        if application.student_status not in {"eligible", "ready_for_batch"}:
            raise HTTPException(422, f"{application.full_name} must be marked eligible before batch selection")
        if application.selected_domain and application.selected_domain.casefold() != batch.domain.casefold():
            raise HTTPException(422, f"{application.full_name} is registered for a different internship domain")
        if db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, application_id=student_id).first():
            continue
        active = db.query(InternshipBatchStudent).join(InternshipBatch).filter(
            InternshipBatchStudent.application_id == student_id,
            InternshipBatchStudent.is_active.is_(True),
            InternshipBatch.program_id == batch.program_id if batch.program_id else InternshipBatch.domain == batch.domain,
            InternshipBatch.status.in_({"draft", "student_selection", "pending_approval", "confirmed", "in_progress"}),
        ).first()
        if active and active.batch_id != batch.id:
            raise HTTPException(409, f"{application.full_name} is already enrolled in an active internship for this program")
        membership = db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, application_id=student_id).first()
        if membership:
            membership.is_active = True
            membership.added_by_id = user.id
            membership.added_at = datetime.utcnow()
        else:
            db.add(InternshipBatchStudent(batch_id=batch.id, application_id=student_id, program_id=batch.program_id, added_by_id=user.id))
    batch.status = "student_selection"
    audit(db, user, "internship_batch.students_added", "internship_batch", batch.id, f"students={','.join(map(str, unique_ids))}")
    db.commit()
    db.refresh(batch)
    return batch_dict(db, batch)


@router.delete("/batches/{batch_id}/students/{student_id}")
def remove_batch_student(batch_id: int, student_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*COORDINATORS))):
    batch = record_or_404(db, InternshipBatch, batch_id, "Batch")
    require_batch_access(db, batch, user)
    if batch.status not in {"draft", "student_selection"}:
        raise HTTPException(409, "Confirmed batch roster is locked")
    membership = db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, application_id=student_id).first()
    if not membership:
        raise HTTPException(404, "Student is not selected for this batch")
    membership.is_active = False
    audit(db, user, "internship_batch.student_removed", "internship_batch", batch.id, f"student_id={student_id}")
    db.commit()
    return batch_dict(db, batch)


def confirm_roster(db: Session, batch: InternshipBatch, user: User):
    members = db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, is_active=True).all()
    if not members:
        raise HTTPException(422, "Select at least one student before confirming the batch")
    unpaid = [m for m in members if db.get(InternshipApplication, m.application_id).payment_status not in {"paid", "free"}]
    if unpaid and batch.unpaid_approval_required:
        batch.status = "pending_approval"
        approvers = db.query(User).join(User.roles).filter(Role.name.in_(ADMIN)).all()
        for approver in approvers:
            db.add(Notification(user_id=approver.id, title="Internship batch approval required",
                                message=f"{batch.name} includes {len(unpaid)} unpaid student(s) and needs approval.",
                                related_type="internship_batch", related_id=batch.id))
        audit(db, user, "internship_batch.approval_requested", "internship_batch", batch.id, f"unpaid_students={len(unpaid)}")
        db.commit()
        return {"batch": batch_dict(db, batch), "approval_required": True, "unpaid_students": len(unpaid)}
    batch.status = "confirmed"
    batch.confirmed_by_id = user.id
    batch.confirmed_at = datetime.utcnow()
    for membership in members:
        application = db.get(InternshipApplication, membership.application_id)
        application.student_status = "batch_assigned"
        if not db.query(InternshipStatusHistory).filter_by(application_id=application.id, to_status="batch_assigned").first():
            db.add(InternshipStatusHistory(application_id=application.id, from_status="ready_for_batch", to_status="batch_assigned", changed_by_id=user.id, note=f"Batch {batch.name} confirmed"))
        recipients = {application.coordinator_id, batch.coordinator_id}
        for user_id in recipients - {None}:
            db.add(Notification(user_id=user_id, title="Internship batch confirmed", message=f"{batch.name} was confirmed with {len(members)} students.", related_type="internship_batch", related_id=batch.id))
    if batch.trainer_id:
        trainer = db.get(Trainer, batch.trainer_id)
        if trainer and trainer.user_id:
            db.add(Notification(user_id=trainer.user_id, title="Internship batch assigned", message=f"You have been assigned to {batch.name}.", related_type="internship_batch", related_id=batch.id))
    audit(db, user, "internship_batch.confirmed", "internship_batch", batch.id, f"students={len(members)}")
    db.commit()
    return {"batch": batch_dict(db, batch), "approval_required": False, "unpaid_students": 0}


@router.post("/batches/{batch_id}/confirm")
def confirm_batch(batch_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*COORDINATORS))):
    batch = record_or_404(db, InternshipBatch, batch_id, "Batch")
    require_batch_access(db, batch, user)
    if batch.status not in {"draft", "student_selection"}:
        raise HTTPException(409, "Only a draft batch can be confirmed")
    return confirm_roster(db, batch, user)


@router.post("/batches/{batch_id}/approve")
def approve_batch(batch_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    batch = record_or_404(db, InternshipBatch, batch_id, "Batch")
    if batch.status != "pending_approval":
        raise HTTPException(409, "This batch is not waiting for approval")
    batch.unpaid_approval_required = False
    batch.status = "student_selection"
    return confirm_roster(db, batch, user)


@router.post("/batches/{batch_id}/transition")
def transition_batch(batch_id: int, data: BatchTransition, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = record_or_404(db, InternshipBatch, batch_id, "Batch")
    require_batch_access(db, batch, user)
    roles = role_names(user)
    if data.status == "in_progress":
        if batch.status != "confirmed":
            raise HTTPException(409, "Only a confirmed batch can start")
        if not batch.trainer_id:
            raise HTTPException(409, "Assign a trainer before starting this batch")
    elif data.status == "completed":
        if not is_manager(user):
            raise HTTPException(403, "Only an admin or manager can complete a batch")
        if batch.status != "in_progress":
            raise HTTPException(409, "Only an in-progress batch can be completed")
        sessions = db.query(InternshipTrainingSession).filter_by(batch_id=batch.id).all()
        if not sessions or any(session.status != "completed" for session in sessions):
            raise HTTPException(409, "Complete every training session before closing the batch")
        members = db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, is_active=True).all()
        evaluations = {row.application_id: row for row in db.query(InternshipEvaluation).filter_by(batch_id=batch.id).all()}
        if any(member.application_id not in evaluations or not evaluations[member.application_id].approved_at for member in members):
            raise HTTPException(409, "Submit and approve a final evaluation for every enrolled student first")
        for member in members:
            application = db.get(InternshipApplication, member.application_id)
            old_status = application.student_status
            application.student_status = "completed"
            db.add(InternshipStatusHistory(application_id=application.id, from_status=old_status, to_status="completed",
                                           changed_by_id=user.id, note=f"Batch {batch.name} completed"))
            member.is_active = False
    elif data.status == "cancelled":
        if batch.status in {"completed", "cancelled"}:
            raise HTTPException(409, "This batch is already closed")
        if batch.status in ACTIVE_BATCH_STATUSES and not is_manager(user):
            raise HTTPException(403, "Only an admin or manager can cancel a confirmed batch")
        for member in db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, is_active=True).all():
            member.is_active = False
    batch.status = data.status
    audit(db, user, "internship_batch.status_changed", "internship_batch", batch.id, data.status)
    db.commit()
    db.refresh(batch)
    return batch_dict(db, batch)


@router.patch("/batches/{batch_id}/trainer")
def reassign_batch_trainer(batch_id: int, data: TrainerAssignment, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    batch = record_or_404(db, InternshipBatch, batch_id, "Batch")
    if batch.status in {"completed", "cancelled"}:
        raise HTTPException(409, "A closed batch cannot be reassigned")
    if data.trainer_id is not None:
        trainer = record_or_404(db, Trainer, data.trainer_id, "Trainer")
        if trainer.availability == "unavailable":
            raise HTTPException(409, "This trainer is marked unavailable")
    previous_id = batch.trainer_id
    batch.trainer_id = data.trainer_id
    if data.trainer_id:
        trainer = db.get(Trainer, data.trainer_id)
        if trainer and trainer.user_id:
            db.add(Notification(user_id=trainer.user_id, title="Internship batch assigned",
                                message=f"You have been assigned to {batch.name}.",
                                related_type="internship_batch", related_id=batch.id))
    if previous_id and previous_id != data.trainer_id:
        previous = db.get(Trainer, previous_id)
        if previous and previous.user_id:
            db.add(Notification(user_id=previous.user_id, title="Internship batch reassigned",
                                message=f"You have been removed from {batch.name}.",
                                related_type="internship_batch", related_id=batch.id))
    audit(db, user, "internship_batch.trainer_reassigned", "internship_batch", batch.id, f"{previous_id}->{data.trainer_id}")
    db.commit()
    db.refresh(batch)
    return batch_dict(db, batch)


@router.get("/trainers")
def list_trainers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not role_names(user).intersection(set(TRAINERS) | {"Employee / Intern"}):
        raise HTTPException(403, "Your role cannot view trainers")
    return db.query(Trainer).order_by(Trainer.name).limit(500).all()


@router.post("/trainers", status_code=201)
def create_trainer(data: TrainerCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    if data.user_id:
        record_or_404(db, User, data.user_id, "User")
        if db.query(Trainer).filter_by(user_id=data.user_id).first():
            raise HTTPException(409, "This user is already linked to a trainer profile")
    trainer = Trainer(**data.model_dump())
    db.add(trainer)
    db.flush()
    audit(db, user, "internship_trainer.created", "trainer", trainer.id)
    db.commit()
    db.refresh(trainer)
    return trainer


@router.patch("/trainers/{trainer_id}")
def update_trainer(trainer_id: int, data: TrainerUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    trainer = record_or_404(db, Trainer, trainer_id, "Trainer")
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(trainer, key, value)
    audit(db, user, "internship_trainer.updated", "trainer", trainer.id)
    db.commit()
    db.refresh(trainer)
    return trainer


@router.get("/sessions")
def list_sessions(batch_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(InternshipTrainingSession).join(InternshipBatch)
    if batch_id:
        query = query.filter(InternshipTrainingSession.batch_id == batch_id)
    if not is_manager(user):
        if "Trainer / Teacher" in role_names(user):
            trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
            query = query.filter(InternshipBatch.trainer_id == (trainer.id if trainer else -1))
        elif role_names(user).intersection({"Internship Coordinator", "Employee / Intern"}):
            query = query.filter(InternshipBatch.coordinator_id == user.id)
        elif "Training Coordinator" in role_names(user):
            pass
        else:
            raise HTTPException(403, "Your role cannot access training sessions")
    return query.order_by(InternshipTrainingSession.starts_at.desc()).limit(1000).all()


@router.post("/batches/{batch_id}/sessions", status_code=201)
def create_session(batch_id: int, data: SessionCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*TRAINERS))):
    batch = record_or_404(db, InternshipBatch, batch_id, "Batch")
    require_batch_access(db, batch, user)
    if batch.status not in {"confirmed", "in_progress"}:
        raise HTTPException(409, "Sessions can be scheduled after batch confirmation")
    if data.ends_at and data.ends_at <= data.starts_at:
        raise HTTPException(422, "Session end time must be after its start time")
    trainer_id = data.trainer_id or batch.trainer_id
    if trainer_id:
        record_or_404(db, Trainer, trainer_id, "Trainer")
    if "Trainer / Teacher" in role_names(user) and trainer_id != db.query(Trainer.id).filter_by(user_id=user.id).scalar():
        raise HTTPException(403, "You can only schedule sessions assigned to you")
    values = data.model_dump()
    if values.get("meeting_url"):
        values["meeting_url"] = str(values["meeting_url"])
    values.pop("trainer_id", None)
    session = InternshipTrainingSession(batch_id=batch.id, trainer_id=trainer_id, created_by_id=user.id, **values)
    db.add(session)
    db.flush()
    if batch.status == "confirmed":
        batch.status = "in_progress"
    trainer = db.get(Trainer, trainer_id) if trainer_id else None
    if trainer and trainer.user_id and trainer.user_id != user.id:
        db.add(Notification(user_id=trainer.user_id, title="Training session scheduled",
                            message=f"{session.title} is scheduled for {session.starts_at:%d %b %Y %H:%M}.",
                            related_type="internship_training_session", related_id=session.id))
    if batch.coordinator_id and batch.coordinator_id != user.id:
        db.add(Notification(user_id=batch.coordinator_id, title="Training session scheduled",
                            message=f"{session.title} was scheduled for {batch.name}.",
                            related_type="internship_training_session", related_id=session.id))
    audit(db, user, "internship_session.created", "internship_training_session", session.id)
    db.commit()
    db.refresh(session)
    return session


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, data: SessionUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles(*TRAINERS))):
    session = record_or_404(db, InternshipTrainingSession, session_id, "Session")
    batch = record_or_404(db, InternshipBatch, session.batch_id, "Batch")
    require_batch_access(db, batch, user)
    changes = data.model_dump(exclude_unset=True)
    starts = changes.get("starts_at", session.starts_at)
    ends = changes.get("ends_at", session.ends_at)
    if starts and ends and ends <= starts:
        raise HTTPException(422, "Session end time must be after its start time")
    if changes.get("trainer_id"):
        record_or_404(db, Trainer, changes["trainer_id"], "Trainer")
    if "meeting_url" in changes and changes["meeting_url"]:
        changes["meeting_url"] = str(changes["meeting_url"])
    for key, value in changes.items():
        setattr(session, key, value)
    audit(db, user, "internship_session.updated", "internship_training_session", session.id)
    db.commit()
    db.refresh(session)
    return session


@router.get("/attendance")
def list_attendance(session_id: int | None = None, application_id: int | None = None,
                    batch_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(InternshipAttendance)
    if session_id:
        query = query.filter(InternshipAttendance.session_id == session_id)
    if application_id:
        query = query.filter(InternshipAttendance.application_id == application_id)
    if batch_id:
        query = query.join(InternshipTrainingSession, InternshipAttendance.session_id == InternshipTrainingSession.id).filter(InternshipTrainingSession.batch_id == batch_id)
    if not is_manager(user):
        if "Trainer / Teacher" in role_names(user):
            trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
            assigned_session_ids = db.query(InternshipTrainingSession.id).join(InternshipBatch).filter(
                InternshipBatch.trainer_id == (trainer.id if trainer else -1)
            )
            query = query.filter(InternshipAttendance.session_id.in_(assigned_session_ids))
        elif role_names(user).intersection({"Internship Coordinator", "Employee / Intern"}):
            assigned_student_ids = db.query(InternshipApplication.id).filter(InternshipApplication.coordinator_id == user.id)
            query = query.filter(InternshipAttendance.application_id.in_(assigned_student_ids))
        elif "Training Coordinator" in role_names(user):
            pass
        else:
            raise HTTPException(403, "Your role cannot access attendance")
    return query.order_by(InternshipAttendance.attendance_date.desc()).limit(2000).all()


@router.post("/attendance", status_code=201)
def record_attendance(data: AttendanceCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*TRAINERS))):
    session = record_or_404(db, InternshipTrainingSession, data.session_id, "Session")
    batch = record_or_404(db, InternshipBatch, session.batch_id, "Batch")
    require_batch_access(db, batch, user)
    application = record_or_404(db, InternshipApplication, data.application_id, "Student")
    require_student_access(db, application, user)
    if not db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, application_id=application.id).first():
        raise HTTPException(422, "Student is not enrolled in this batch")
    existing = db.query(InternshipAttendance).filter_by(session_id=session.id, application_id=application.id).first()
    if existing:
        existing.status = data.status
        existing.notes = data.notes
        existing.recorded_by_id = user.id
        audit(db, user, "internship_attendance.updated", "internship_attendance", existing.id)
        db.commit()
        db.refresh(existing)
        return existing
    attendance = InternshipAttendance(application_id=application.id, session_id=session.id,
                                      attendance_date=session.starts_at.date(), status=data.status,
                                      recorded_by_id=user.id, notes=data.notes)
    db.add(attendance)
    db.flush()
    audit(db, user, "internship_attendance.recorded", "internship_attendance", attendance.id)
    db.commit()
    db.refresh(attendance)
    return attendance


@router.get("/progress/{student_id}")
def student_progress(student_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    application = record_or_404(db, InternshipApplication, student_id, "Student")
    require_student_access(db, application, user)
    members = db.query(InternshipBatchStudent, InternshipBatch).join(InternshipBatch).filter(InternshipBatchStudent.application_id == student_id).all()
    batches = []
    total_sessions = completed_sessions = present = attendance_count = 0
    assignment_count = submitted_count = score_total = score_count = 0
    legacy_attendances = db.query(InternshipAttendance).filter(
        InternshipAttendance.application_id == student_id, InternshipAttendance.session_id.is_(None)
    ).all()
    attendance_count += len(legacy_attendances)
    present += sum(a.status in {"present", "late"} for a in legacy_attendances)
    for member, batch in members:
        sessions = db.query(InternshipTrainingSession).filter(InternshipTrainingSession.batch_id == batch.id,
                                                              InternshipTrainingSession.status != "cancelled").all()
        session_ids = [s.id for s in sessions]
        attendances = db.query(InternshipAttendance).filter(InternshipAttendance.application_id == student_id,
                                                            InternshipAttendance.session_id.in_(session_ids or [-1])).all()
        assignments = db.query(InternshipAssignment).filter_by(batch_id=batch.id).all()
        submissions = db.query(InternshipSubmission).filter(InternshipSubmission.application_id == student_id,
                                                            InternshipSubmission.assignment_id.in_([a.id for a in assignments] or [-1])).all()
        total_sessions += len(sessions)
        completed_in_batch = sum(s.status == "completed" for s in sessions)
        completed_sessions += completed_in_batch
        attendance_count += max(completed_in_batch, len(attendances))
        present += sum(a.status in {"present", "late"} for a in attendances)
        assignment_count += len(assignments)
        submitted_count += sum(s.status == "evaluated" for s in submissions)
        scores = [float(s.score) for s in submissions if s.score is not None]
        score_total += sum(scores)
        score_count += len(scores)
        batches.append({"batch": batch, "sessions": len(sessions), "completed_sessions": completed_in_batch,
                        "assignments": len(assignments), "evaluated_assignments": sum(s.status == "evaluated" for s in submissions)})
    attendance_percent = round(present * 100 / attendance_count) if attendance_count else 0
    average_score = round(score_total / score_count, 2) if score_count else None
    progress_percent = round((completed_sessions + submitted_count) * 100 / (total_sessions + assignment_count)) if total_sessions + assignment_count else 0
    task_total = db.query(InternshipTask).filter_by(application_id=student_id).count()
    task_completed = db.query(InternshipTask).filter_by(application_id=student_id, status="completed").count()
    project_progress = round(task_completed * 100 / task_total) if task_total else None
    return {"student": application, "batches": batches, "total_sessions": total_sessions,
            "completed_sessions": completed_sessions, "remaining_sessions": max(0, total_sessions-completed_sessions),
            "attendance_percentage": attendance_percent, "assignments_assigned": assignment_count,
            "assignments_completed": submitted_count, "pending_assignments": max(0, assignment_count-submitted_count),
            "average_assignment_score": average_score, "project_progress": project_progress, "overall_progress": progress_percent}


@router.get("/assignments")
def list_assignments(batch_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(InternshipAssignment)
    if batch_id:
        query = query.filter(InternshipAssignment.batch_id == batch_id)
    if not is_manager(user):
        if "Trainer / Teacher" in role_names(user):
            trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
            query = query.join(InternshipBatch).filter(InternshipBatch.trainer_id == (trainer.id if trainer else -1))
        elif role_names(user).intersection({"Internship Coordinator", "Employee / Intern"}):
            query = query.join(InternshipBatch).filter(InternshipBatch.coordinator_id == user.id)
        elif "Training Coordinator" in role_names(user):
            pass
        else:
            raise HTTPException(403, "Your role cannot access assignments")
    return query.order_by(InternshipAssignment.due_at.asc().nullslast()).limit(1000).all()


@router.post("/assignments", status_code=201)
def create_assignment(data: AssignmentCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*TRAINERS))):
    batch = record_or_404(db, InternshipBatch, data.batch_id, "Batch")
    require_batch_access(db, batch, user)
    if batch.status not in ACTIVE_BATCH_STATUSES:
        raise HTTPException(409, "Assignments can be created for confirmed or active batches")
    assignment = InternshipAssignment(**data.model_dump(), created_by_id=user.id)
    db.add(assignment)
    db.flush()
    recipients = {batch.coordinator_id}
    trainer = db.get(Trainer, batch.trainer_id) if batch.trainer_id else None
    if trainer:
        recipients.add(trainer.user_id)
    for user_id in recipients - {None, user.id}:
        db.add(Notification(user_id=user_id, title="New internship assignment",
                            message=f"{assignment.title} was added to {batch.name}.",
                            related_type="internship_assignment", related_id=assignment.id))
    audit(db, user, "internship_assignment.created", "internship_assignment", assignment.id)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("/assignments/{assignment_id}/submissions")
def list_submissions(assignment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assignment = record_or_404(db, InternshipAssignment, assignment_id, "Assignment")
    batch = record_or_404(db, InternshipBatch, assignment.batch_id, "Batch")
    require_batch_access(db, batch, user)
    return db.query(InternshipSubmission).filter_by(assignment_id=assignment.id).order_by(InternshipSubmission.submitted_at.desc()).all()


@router.post("/assignments/{assignment_id}/submissions", status_code=201)
def submit_assignment(assignment_id: int, data: SubmissionCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*COORDINATORS))):
    assignment = record_or_404(db, InternshipAssignment, assignment_id, "Assignment")
    application = record_or_404(db, InternshipApplication, data.application_id, "Student")
    require_student_access(db, application, user)
    if not db.query(InternshipBatchStudent).filter_by(batch_id=assignment.batch_id, application_id=application.id).first():
        raise HTTPException(422, "Student is not enrolled in the assignment batch")
    submission = db.query(InternshipSubmission).filter_by(assignment_id=assignment.id, application_id=application.id).first()
    values = data.model_dump()
    if values.get("submission_link"):
        values["submission_link"] = str(values["submission_link"])
    if not values.get("submission_link") and not values.get("submission_text"):
        raise HTTPException(422, "Add a project link or submission notes")
    if submission and submission.status not in {"rejected_resubmission", "not_started", "in_progress"}:
        raise HTTPException(409, "This assignment has already been submitted")
    if submission:
        submission.submission_link = values["submission_link"]
        submission.submission_text = values["submission_text"]
        submission.status = "late_submission" if assignment.due_at and datetime.utcnow() > assignment.due_at else "submitted"
        submission.submitted_at = datetime.utcnow()
    else:
        submission = InternshipSubmission(assignment_id=assignment.id, application_id=application.id,
                                          submission_link=values["submission_link"], submission_text=values["submission_text"],
                                          status="late_submission" if assignment.due_at and datetime.utcnow() > assignment.due_at else "submitted")
        db.add(submission)
    db.flush()
    audit(db, user, "internship_submission.created", "internship_submission", submission.id)
    db.commit()
    db.refresh(submission)
    return submission


@router.patch("/submissions/{submission_id}/review")
def review_submission(submission_id: int, data: SubmissionReview, db: Session = Depends(get_db), user: User = Depends(require_roles(*TRAINERS))):
    submission = record_or_404(db, InternshipSubmission, submission_id, "Submission")
    assignment = record_or_404(db, InternshipAssignment, submission.assignment_id, "Assignment")
    batch = record_or_404(db, InternshipBatch, assignment.batch_id, "Batch")
    require_batch_access(db, batch, user)
    if data.score is not None and data.score > assignment.max_score:
        raise HTTPException(422, "Score cannot exceed the assignment maximum")
    if data.status == "evaluated" and data.score is None:
        raise HTTPException(422, "Enter a score when evaluating the submission")
    submission.status = data.status
    submission.score = data.score
    submission.feedback = data.feedback
    submission.reviewed_by_id = user.id
    submission.reviewed_at = datetime.utcnow()
    audit(db, user, "internship_submission.reviewed", "internship_submission", submission.id)
    db.commit()
    db.refresh(submission)
    return submission


def evaluation_score(scores: dict, weights: dict) -> Decimal:
    applicable = [(float(scores[key]), float(weights[key])) for key in weights if key in scores and float(weights[key]) > 0]
    weight_total = sum(weight for _, weight in applicable)
    if not weight_total:
        raise HTTPException(422, "Provide at least one criterion score with a configured weight")
    if any(score < 0 or score > 100 for score, _ in applicable):
        raise HTTPException(422, "Evaluation criteria scores must be between 0 and 100")
    return Decimal(str(round(sum(score * weight for score, weight in applicable) / weight_total, 2)))


@router.get("/evaluations")
def list_evaluations(batch_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(InternshipEvaluation)
    if batch_id:
        query = query.filter(InternshipEvaluation.batch_id == batch_id)
    if not is_manager(user):
        if "Trainer / Teacher" in role_names(user):
            trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
            query = query.join(InternshipBatch).filter(InternshipBatch.trainer_id == (trainer.id if trainer else -1))
        elif role_names(user).intersection({"Internship Coordinator", "Employee / Intern"}):
            query = query.join(InternshipBatch).filter(InternshipBatch.coordinator_id == user.id)
        elif "Training Coordinator" in role_names(user):
            pass
        else:
            raise HTTPException(403, "Your role cannot access evaluations")
    return query.order_by(InternshipEvaluation.created_at.desc()).limit(1000).all()


@router.post("/evaluations", status_code=201)
def submit_evaluation(data: EvaluationCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*TRAINERS))):
    batch = record_or_404(db, InternshipBatch, data.batch_id, "Batch")
    require_batch_access(db, batch, user)
    application = record_or_404(db, InternshipApplication, data.application_id, "Student")
    require_student_access(db, application, user)
    if not db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, application_id=application.id).first():
        raise HTTPException(422, "Student is not enrolled in this batch")
    if db.query(InternshipEvaluation).filter_by(batch_id=batch.id, application_id=application.id).first():
        raise HTTPException(409, "A final evaluation already exists for this student in this batch")
    config = settings_values(db)
    score = evaluation_score(data.criterion_scores, config["evaluation_weights"])
    record = InternshipEvaluation(
        **data.model_dump(exclude={"result"}), performance_score=score,
        result="passed" if float(score) >= float(config["passing_score"]) else "needs_improvement",
        submitted_by_id=user.id,
    )
    db.add(record)
    db.flush()
    if application.coordinator_id and application.coordinator_id != user.id:
        db.add(Notification(user_id=application.coordinator_id, title="Final evaluation submitted",
                            message=f"A final evaluation for {application.full_name} is ready for approval.",
                            related_type="internship_evaluation", related_id=record.id))
    audit(db, user, "internship_evaluation.submitted", "internship_evaluation", record.id, f"score={score}")
    db.commit()
    db.refresh(record)
    return record


@router.patch("/evaluations/{evaluation_id}/approval")
def approve_evaluation(evaluation_id: int, data: EvaluationApproval, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    evaluation = record_or_404(db, InternshipEvaluation, evaluation_id, "Evaluation")
    if evaluation.approved_at:
        raise HTTPException(409, "This evaluation has already been approved")
    evaluation.admin_remarks = data.admin_remarks
    if data.approved:
        evaluation.approved_by_id = user.id
        evaluation.approved_at = datetime.utcnow()
        if evaluation.result != "passed":
            evaluation.result = "failed"
    else:
        evaluation.result = "reevaluation_required"
    audit(db, user, "internship_evaluation.approved" if data.approved else "internship_evaluation.returned", "internship_evaluation", evaluation.id)
    db.commit()
    db.refresh(evaluation)
    return evaluation


@router.get("/certificates")
def list_certificates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not role_names(user).intersection(set(COORDINATORS) | {"Training Coordinator", "Trainer / Teacher"}):
        raise HTTPException(403, "Your role cannot access certificates")
    query = db.query(InternshipCertificate)
    if not is_manager(user) and role_names(user).intersection({"Internship Coordinator", "Employee / Intern"}):
        query = query.join(InternshipApplication).filter(or_(InternshipApplication.coordinator_id == user.id,
                                                             InternshipApplication.coordinator_id.is_(None)))
    elif "Trainer / Teacher" in role_names(user):
        trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
        query = query.join(InternshipBatchStudent, InternshipBatchStudent.application_id == InternshipCertificate.application_id).join(
            InternshipBatch, InternshipBatch.id == InternshipBatchStudent.batch_id
        ).filter(InternshipBatch.trainer_id == (trainer.id if trainer else -1)).distinct()
    return query.order_by(InternshipCertificate.created_at.desc()).limit(1000).all()


@router.post("/evaluations/{evaluation_id}/certificate", status_code=201)
def generate_certificate(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    evaluation = record_or_404(db, InternshipEvaluation, evaluation_id, "Evaluation")
    batch = record_or_404(db, InternshipBatch, evaluation.batch_id, "Batch")
    if not evaluation.approved_at or evaluation.result != "passed":
        raise HTTPException(409, "Certificate requires an approved passing evaluation")
    if batch.status != "completed":
        raise HTTPException(409, "Mark the internship batch completed before issuing certificates")
    existing = db.query(InternshipCertificate).filter_by(evaluation_id=evaluation.id).first()
    if existing:
        return existing
    progress = student_progress(evaluation.application_id, db, user)
    if progress["attendance_percentage"] < settings_values(db)["attendance_threshold"]:
        raise HTTPException(409, "Student attendance is below the certificate threshold")
    certificate = InternshipCertificate(
        application_id=evaluation.application_id, evaluation_id=evaluation.id, certificate_type="completion",
        status="issued", certificate_number=f"HRUTA-INT-{datetime.utcnow():%Y}-{secrets.token_hex(4).upper()}",
        issued_at=datetime.utcnow(),
    )
    db.add(certificate)
    db.flush()
    audit(db, user, "internship_certificate.issued", "internship_certificate", certificate.id)
    application = db.get(InternshipApplication, certificate.application_id)
    if application and application.coordinator_id:
        db.add(Notification(user_id=application.coordinator_id, title="Internship certificate available",
                            message=f"Certificate {certificate.certificate_number} has been issued for {application.full_name}.",
                            related_type="internship_certificate", related_id=certificate.id))
    db.commit()
    db.refresh(certificate)
    return certificate


@router.get("/certificates/{certificate_id}/render", response_class=HTMLResponse)
def render_certificate(certificate_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    certificate = record_or_404(db, InternshipCertificate, certificate_id, "Certificate")
    evaluation = db.get(InternshipEvaluation, certificate.evaluation_id) if certificate.evaluation_id else None
    if certificate.status != "issued" or not evaluation or evaluation.result != "passed" or not evaluation.approved_at:
        raise HTTPException(409, "This certificate is not available")
    application = record_or_404(db, InternshipApplication, certificate.application_id, "Student")
    require_student_access(db, application, user)
    from html import escape
    name = escape(application.full_name)
    domain = escape(application.selected_domain or "Internship Program")
    number = escape(certificate.certificate_number or "")
    return HTMLResponse(f"""<!doctype html><html><head><meta charset='utf-8'><title>Certificate {number}</title>
<style>body{{font-family:Georgia,serif;background:#f1f5f9;color:#172554;margin:0;padding:40px}}.cert{{max-width:900px;margin:2rem auto;padding:4rem;border:12px double #c59d32;background:white;text-align:center}}h1{{font-size:2.6rem;color:#17336b}}.name{{font-size:2rem;font-weight:bold;margin:2rem}}.meta{{color:#475569}}button{{padding:.7rem 1.2rem;border:0;border-radius:8px;background:#17336b;color:white;cursor:pointer}}@media print{{body{{background:white;padding:0}}.cert{{margin:0;max-width:none;min-height:75vh}}button{{display:none}}}}</style></head>
<body><article class='cert'><p>HRUTA SOLUTIONS</p><h1>Certificate of Completion</h1><p>This certifies that</p><div class='name'>{name}</div><p>has successfully completed the internship program in</p><h2>{domain}</h2><p class='meta'>Performance score: {evaluation.performance_score}% · Completed {evaluation.completion_date or ""}</p><p class='meta'>Certificate ID: {number}</p><button onclick='window.print()'>Print or save as PDF</button></article></body></html>""")


@router.get("/public/certificates/{certificate_number}")
def verify_certificate(certificate_number: str, db: Session = Depends(get_db)):
    certificate = db.query(InternshipCertificate).filter_by(certificate_number=certificate_number, status="issued").first()
    if not certificate:
        return {"valid": False}
    application = db.get(InternshipApplication, certificate.application_id)
    evaluation = db.get(InternshipEvaluation, certificate.evaluation_id) if certificate.evaluation_id else None
    return {"valid": bool(application and evaluation and evaluation.approved_at and evaluation.result == "passed"),
            "certificate_number": certificate.certificate_number,
            "student_name": application.full_name if application else None,
            "domain": application.selected_domain if application else None,
            "issued_at": certificate.issued_at}


@router.get("/settings")
def get_internship_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not role_names(user).intersection(set(COORDINATORS) | {"Training Coordinator", "Trainer / Teacher"}):
        raise HTTPException(403, "Your role cannot access internship settings")
    return settings_values(db)


@router.put("/settings")
def update_internship_settings(data: SettingsUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    weights = data.evaluation_weights
    if any(value < 0 or value > 100 for value in weights.values()) or round(sum(weights.values()), 2) != 100:
        raise HTTPException(422, "Evaluation weights must each be between 0 and 100 and add up to 100")
    row = db.get(AppConfiguration, "internship_management")
    values = data.model_dump()
    if row:
        row.value = values
        row.updated_by_id = user.id
    else:
        db.add(AppConfiguration(key="internship_management", value=values,
                                description="Internship lifecycle thresholds and evaluation weightage", updated_by_id=user.id))
    audit(db, user, "internship_settings.updated", "app_configuration", "internship_management")
    db.commit()
    return values


@router.get("/reports")
def internship_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    summary = internship_overview(db, user)
    student_ids = filtered_students(db, user).with_entities(InternshipApplication.id)
    feedback_rows = db.query(LearnerFeedback).filter(LearnerFeedback.application_id.in_(student_ids)).all()
    student_feedback = [row for row in feedback_rows if row.feedback_type == "student" and row.rating is not None]
    placement_interest_count = sum(row.placement_interest is True for row in student_feedback)
    batch_query = db.query(InternshipBatch)
    if not is_manager(user):
        if "Trainer / Teacher" in role_names(user):
            trainer = db.query(Trainer).filter(Trainer.user_id == user.id).first()
            batch_query = batch_query.filter(InternshipBatch.trainer_id == (trainer.id if trainer else -1))
        elif role_names(user).intersection({"Internship Coordinator", "Employee / Intern"}):
            batch_query = batch_query.filter(InternshipBatch.coordinator_id == user.id)
    scoped_batches = batch_query.order_by(InternshipBatch.start_date.desc()).limit(100).all()
    batch_performance = []
    domain_totals = {}
    trainer_totals = {}
    for batch in scoped_batches:
        evaluations = db.query(InternshipEvaluation).filter_by(batch_id=batch.id).all()
        passed = sum(row.result == "passed" for row in evaluations)
        scores = [float(row.performance_score) for row in evaluations]
        roster = db.query(InternshipBatchStudent).filter_by(batch_id=batch.id, is_active=True).count()
        row = {"batch_id": batch.id, "batch_name": batch.name, "domain": batch.domain,
               "status": batch.status, "student_count": roster, "passed": passed,
               "evaluation_count": len(evaluations), "average_score": round(sum(scores) / len(scores), 2) if scores else None,
               "trainer_id": batch.trainer_id, "trainer_name": db.get(Trainer, batch.trainer_id).name if batch.trainer_id and db.get(Trainer, batch.trainer_id) else None}
        batch_performance.append(row)
        domain = domain_totals.setdefault(batch.domain, {"domain": batch.domain, "batches": 0, "students": 0, "evaluations": 0, "passed": 0, "score_total": 0.0})
        domain["batches"] += 1; domain["students"] += roster; domain["evaluations"] += len(evaluations); domain["passed"] += passed
        domain["score_total"] += sum(scores)
        if batch.trainer_id:
            trainer = trainer_totals.setdefault(batch.trainer_id, {"trainer_id": batch.trainer_id, "trainer_name": row["trainer_name"], "batches": 0, "active_students": 0, "evaluations": 0, "passed": 0, "score_total": 0.0})
            trainer["batches"] += 1; trainer["active_students"] += roster; trainer["evaluations"] += len(evaluations)
            trainer["passed"] += passed; trainer["score_total"] += sum(scores)
    for item in list(domain_totals.values()) + list(trainer_totals.values()):
        item["average_score"] = round(item.pop("score_total") / item["evaluations"], 2) if item["evaluations"] else None
        item["pass_rate"] = round(item["passed"] * 100 / item["evaluations"], 1) if item["evaluations"] else None
    return {"summary": {key: value for key, value in summary.items() if key not in {"recent_registrations", "upcoming_followups", "pending_payment_verification", "upcoming_sessions", "low_attendance_students", "missing_assignments", "inactive_students", "poor_performance_students", "pending_assignment_reviews"}},
            "batch_performance": batch_performance,
            "domain_performance": sorted(domain_totals.values(), key=lambda item: item["students"], reverse=True),
            "trainer_performance": sorted(trainer_totals.values(), key=lambda item: item["active_students"], reverse=True),
            "feedback_summary": {"responses": len(student_feedback),
                                 "average_rating": round(sum(row.rating for row in student_feedback) / len(student_feedback), 2) if student_feedback else None,
                                 "placement_interest": placement_interest_count},
            "completion": {"completed": summary["completed_internships"], "total": summary["total_registrations"],
                           "rate": round(summary["completed_internships"] * 100 / summary["total_registrations"], 1) if summary["total_registrations"] else 0}}


def normalize_header(value: str) -> str:
    return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def map_sheet_row(headers: list[str], values: list[str], row_number: int) -> dict:
    row = {normalize_header(key): value for key, value in zip(headers, values)}
    aliases = {
        "full_name": ("full_name", "student_name", "student_full_name", "name", "full_name_of_student"),
        "email": ("email", "email_address", "student_email"),
        "phone": ("mobile", "mobile_number", "phone", "phone_number", "contact_number"),
        "whatsapp_number": ("whatsapp", "whatsapp_number", "whatsapp_no"),
        "date_of_birth": ("date_of_birth", "dob", "birth_date"),
        "college_name": ("college", "college_name", "institution"),
        "university": ("university", "university_name"),
        "degree": ("degree", "course", "program_of_study"),
        "department": ("department", "branch", "stream"),
        "current_academic_year": ("current_academic_year", "academic_year", "year_of_study"),
        "graduation_year": ("graduation_year", "year_of_graduation"),
        "selected_domain": ("internship_domain", "selected_internship_domain", "domain", "internship_interest"),
        "preferred_duration_weeks": ("duration_weeks", "preferred_duration", "internship_duration"),
        "preferred_mode": ("training_mode", "preferred_mode", "mode"),
        "technical_skills": ("technical_skills", "skills", "technical_skill"),
        "previous_experience": ("previous_experience", "experience"),
        "registration_source": ("registration_source", "source"),
        "google_form_response_id": ("response_id", "form_response_id", "google_form_response_id"),
        "payment_option": ("payment_option", "registration_type"),
        "payment_amount": ("payment_amount", "amount"),
        "payment_transaction_id": ("payment_transaction_id", "transaction_id", "payment_reference"),
    }
    mapped = {key: next((row.get(alias) for alias in candidates if row.get(alias)), None) for key, candidates in aliases.items()}
    mapped["full_name"] = mapped.get("full_name") or ""
    mapped["email"] = mapped.get("email") or ""
    mapped["google_form_response_id"] = mapped.get("google_form_response_id") or f"sheet-row-{row_number}"
    mapped["registration_source"] = "google_form"
    if mapped.get("date_of_birth"):
        try:
            mapped["date_of_birth"] = datetime.fromisoformat(str(mapped["date_of_birth"])).date()
        except ValueError:
            for date_format in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    mapped["date_of_birth"] = datetime.strptime(str(mapped["date_of_birth"]), date_format).date()
                    break
                except ValueError:
                    mapped["date_of_birth"] = None
    try:
        mapped["graduation_year"] = int(mapped["graduation_year"]) if mapped["graduation_year"] else None
    except ValueError:
        mapped["graduation_year"] = None
    try:
        mapped["preferred_duration_weeks"] = int(mapped["preferred_duration_weeks"]) if mapped["preferred_duration_weeks"] else None
    except ValueError:
        mapped["preferred_duration_weeks"] = None
    try:
        mapped["payment_amount"] = Decimal(str(mapped["payment_amount"] or "0").replace(",", ""))
    except Exception:
        mapped["payment_amount"] = Decimal("0")
    mode = (mapped.get("preferred_mode") or "").strip().lower()
    mapped["preferred_mode"] = {"offline": "onsite", "in person": "onsite"}.get(mode, mode if mode in {"online", "onsite", "hybrid"} else None)
    option = (mapped.get("payment_option") or "pending").strip().lower()
    mapped["payment_option"] = option if option in {"paid", "free", "pending", "partial"} else "pending"
    return mapped


def import_form_row(db: Session, row: dict, user_id: int | None) -> tuple[bool, bool]:
    email = str(row.get("email") or "").strip().lower()
    name = str(row.get("full_name") or "").strip()
    phone = str(row.get("phone") or "").strip() or None
    if not name or "@" not in email:
        raise ValueError("A row is missing a valid student name or email")
    response_id = str(row.get("google_form_response_id") or "")
    existing = db.query(InternshipApplication).filter_by(google_form_response_id=response_id).first() if response_id else None
    duplicate = existing or find_duplicate(db, email, phone)
    if duplicate:
        if not duplicate.google_form_response_id and response_id:
            duplicate.google_form_response_id = response_id
        duplicate.sync_status = "synced"
        duplicate.registration_source = "google_form"
        return False, True
    from ..models import InternshipProgram
    domain = row.get("selected_domain")
    program = db.query(InternshipProgram).filter(InternshipProgram.domain.ilike(domain)).first() if domain else None
    owner_id = None
    lead = make_lead(db, name, email, phone, row.get("college_name"), domain, "google_form", owner_id)
    payment_option = row.get("payment_option") or "pending"
    application = InternshipApplication(
        lead_id=lead.id, full_name=name, email=email, phone=phone,
        whatsapp_number=row.get("whatsapp_number"), college_name=row.get("college_name"),
        date_of_birth=row.get("date_of_birth"),
        university=row.get("university"), degree=row.get("degree"), department=row.get("department"),
        current_academic_year=row.get("current_academic_year"), graduation_year=row.get("graduation_year"),
        program_id=program.id if program else None, selected_domain=domain,
        preferred_duration_weeks=row.get("preferred_duration_weeks"), preferred_mode=row.get("preferred_mode"),
        technical_skills=row.get("technical_skills"), previous_experience=row.get("previous_experience"),
        registration_source="google_form", google_form_response_id=response_id,
        sync_status="synced", student_status="new_registration", payment_option=payment_option,
        payment_amount=row.get("payment_amount") or Decimal("0"),
        payment_transaction_id=row.get("payment_transaction_id"),
        payment_status="free" if payment_option == "free" else "pending", coordinator_id=owner_id,
    )
    db.add(application)
    db.flush()
    transaction_id = row.get("payment_transaction_id")
    payment_amount = row.get("payment_amount") or Decimal("0")
    if transaction_id and payment_amount > 0 and payment_option != "free":
        existing_payment = db.query(InternshipPayment).filter_by(transaction_id=transaction_id).first()
        if not existing_payment:
            db.add(InternshipPayment(application_id=application.id, amount=payment_amount,
                                     transaction_id=transaction_id, status="pending", method="manual"))
    db.add(InternshipStatusHistory(application_id=application.id, to_status="new_registration", note="Synchronized from Google Forms"))
    notify_internship_coordinators(db, "New Google Form registration",
                                   f"{name} registered for {domain or 'an internship program'} and is awaiting assignment.",
                                   "internship_application", application.id)
    audit(db, None, "google_form.registration_imported", "internship_application", application.id, f"response_id={response_id}")
    return True, False


def process_form_rows(db: Session, rows: list[list[str]], user_id: int | None, source: str) -> dict:
    run = InternshipSyncRun(source=source, status="running", triggered_by_id=user_id)
    db.add(run)
    db.flush()
    imported = duplicates = 0
    try:
        if not rows:
            raise ValueError("The configured Google Sheet returned no rows")
        headers = [str(value) for value in rows[0]]
        for row_number, values in enumerate(rows[1:], start=2):
            if not any(str(value).strip() for value in values):
                continue
            mapped = map_sheet_row(headers, [str(value) for value in values], row_number)
            created, duplicate = import_form_row(db, mapped, user_id)
            imported += int(created)
            duplicates += int(duplicate)
        run.status = "success"
        run.imported_count = imported
        run.duplicate_count = duplicates
        run.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
        return {"run": run, "imported": imported, "duplicates": duplicates}
    except Exception as exc:
        db.rollback()
        failed = InternshipSyncRun(source=source, status="failed", imported_count=0,
                                   error_message=str(exc)[:2000], triggered_by_id=user_id,
                                   completed_at=datetime.utcnow())
        db.add(failed)
        db.commit()
        logger.exception("Internship form synchronization failed")
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(502, f"Google Form synchronization failed: {exc}")


def fetch_google_sheet_rows() -> list[list[str]]:
    spreadsheet_id = settings.google_sheets_spreadsheet_id.strip()
    if not spreadsheet_id:
        raise HTTPException(409, "Configure GOOGLE_SHEETS_SPREADSHEET_ID before synchronizing")
    range_name = settings.google_sheets_range.strip() or "Form Responses 1!A:Z"
    endpoint = f"https://sheets.googleapis.com/v4/spreadsheets/{urllib.parse.quote(spreadsheet_id, safe='')}/values/{urllib.parse.quote(range_name, safe='!') }"
    headers = {}
    if settings.google_sheets_api_key:
        endpoint += "?" + urllib.parse.urlencode({"key": settings.google_sheets_api_key})
    else:
        try:
            import google.auth
            from google.auth.transport.requests import Request
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
            credentials.refresh(Request())
            headers["Authorization"] = f"Bearer {credentials.token}"
        except Exception as exc:
            raise HTTPException(503, "Configure GOOGLE_SHEETS_API_KEY for a readable sheet or server-side Google application credentials") from exc
    request = urllib.request.Request(endpoint, headers=headers)
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read())
            return payload.get("values", [])
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            last_error = HTTPException(502, f"Google Sheets API returned {exc.code}: {detail}")
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise last_error from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = HTTPException(502, "Could not connect to the Google Sheets API; synchronization failed after retries")
            if attempt == 2:
                raise last_error from exc
        time.sleep(0.5 * (2 ** attempt))
    raise last_error or HTTPException(502, "Google Sheets synchronization failed")


@router.post("/sync/google-sheets")
def sync_google_sheets(db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    try:
        rows = fetch_google_sheet_rows()
    except HTTPException as exc:
        failed = InternshipSyncRun(source="google_sheets", status="failed", error_message=str(exc.detail)[:2000],
                                   triggered_by_id=user.id, completed_at=datetime.utcnow())
        db.add(failed)
        db.commit()
        raise
    return process_form_rows(db, rows, user.id, "google_sheets")


@router.post("/sync/google-form-webhook", status_code=202)
def google_form_webhook(payload: FormWebhookPayload, x_form_webhook_secret: str = Header(default=""), db: Session = Depends(get_db)):
    secret = settings.google_form_webhook_secret
    if not secret or not hmac.compare_digest(secret, x_form_webhook_secret):
        raise HTTPException(401, "Invalid Google Form webhook secret")
    values = {str(key): str(value) if value is not None else "" for key, value in payload.values.items()}
    headers = list(values.keys())
    row = list(values.values())
    mapped = map_sheet_row(headers, row, 0)
    mapped["google_form_response_id"] = payload.response_id
    created, duplicate = import_form_row(db, mapped, None)
    run = InternshipSyncRun(source="google_form_webhook", status="success", imported_count=int(created),
                            duplicate_count=int(duplicate), completed_at=datetime.utcnow())
    db.add(run)
    db.commit()
    return {"status": "accepted", "created": created, "duplicate": duplicate}


@router.get("/sync/runs")
def list_sync_runs(db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN))):
    return db.query(InternshipSyncRun).order_by(InternshipSyncRun.started_at.desc()).limit(100).all()
