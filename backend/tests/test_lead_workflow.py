import unittest

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Activity, Lead, Role, User
from app.routers.crm import create_lead, delete_lead, get_lead, list_leads, update_lead
from app.schemas import LeadCreate, LeadUpdate


class LeadWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            role = Role(name="Sales / Business Development")
            user = User(full_name="Sales User", email="sales@example.com", password_hash="unused")
            user.roles.append(role)
            db.add(user)
            db.commit()
            self.user_id = user.id

    def tearDown(self):
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def create_lead(self, db, user, **changes):
        payload = {
            "first_name": "Asha",
            "last_name": "Patil",
            "email": "asha@example.com",
            "phone": "+919876543210",
            "organization_name": "Pune Works",
            "interest": "IT services",
        }
        payload.update(changes)
        return create_lead_endpoint(LeadCreate(**payload), db, user)

    def test_create_list_and_server_pagination(self):
        with self.Session() as db:
            user = db.get(User, self.user_id)
            first = self.create_lead(db, user)
            self.create_lead(db, user, first_name="Ravi", email="ravi@example.com", phone="+919876543211")

            self.assertEqual(first.owner_id, self.user_id)
            rows = list_leads(search="Asha", page=1, page_size=1, db=db, user=user)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].first_name, "Asha")

    def test_update_rejects_duplicate_contact_details(self):
        with self.Session() as db:
            user = db.get(User, self.user_id)
            first = self.create_lead(db, user)
            second = self.create_lead(db, user, first_name="Ravi", email="ravi@example.com", phone="+919876543211")

            with self.assertRaises(HTTPException) as duplicate_email:
                update_lead(second.id, LeadUpdate(email=first.email), db=db, user=user)
            with self.assertRaises(HTTPException) as duplicate_phone:
                update_lead(second.id, LeadUpdate(phone=first.phone), db=db, user=user)
            self.assertEqual(duplicate_email.exception.status_code, 409)
            self.assertEqual(duplicate_phone.exception.status_code, 409)

            updated = update_lead(second.id, LeadUpdate(first_name="Ravi Kumar", priority="high"), db=db, user=user)
            self.assertEqual(updated.first_name, "Ravi Kumar")
            self.assertEqual(updated.priority, "high")

    def test_delete_blocks_linked_leads_and_deletes_orphans(self):
        with self.Session() as db:
            user = db.get(User, self.user_id)
            linked = self.create_lead(db, user)
            db.add(Activity(lead_id=linked.id, activity_type="call", subject="Intro call", owner_id=user.id))
            db.commit()

            with self.assertRaises(HTTPException) as linked_error:
                delete_lead(linked.id, db=db, user=user)
            self.assertEqual(linked_error.exception.status_code, 409)

            db.query(Activity).filter(Activity.lead_id == linked.id).delete()
            orphan = self.create_lead(db, user, first_name="Mira", email="mira@example.com", phone="+919876543212")
            delete_lead(orphan.id, db=db, user=user)
            with self.assertRaises(HTTPException) as missing:
                get_lead(orphan.id, db=db, user=user)
            self.assertEqual(missing.exception.status_code, 404)

    def test_delete_requires_record_owner(self):
        with self.Session() as db:
            user = db.get(User, self.user_id)
            other = User(full_name="Another Rep", email="other@example.com", password_hash="unused")
            db.add(other)
            db.flush()
            other_lead = Lead(first_name="Other", interest="IT services", owner_id=other.id)
            db.add(other_lead)
            db.commit()

            with self.assertRaises(HTTPException) as forbidden:
                delete_lead(other_lead.id, db=db, user=user)
            self.assertEqual(forbidden.exception.status_code, 403)

    def test_invalid_priority_is_rejected(self):
        with self.assertRaises(ValidationError):
            LeadCreate(first_name="Asha", interest="IT services", priority="urgent")


def create_lead_endpoint(payload, db, user):
    return create_lead(payload, db=db, user=user)


if __name__ == "__main__":
    unittest.main()
