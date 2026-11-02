import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.extended_schemas import SupportTicketCreate, SupportTicketUpdate
from app.models import Contact, Notification, Organization, Role, SupportTicket, User
from app.routers.expanded import create_support_ticket, list_support_tickets, update_support_ticket


class SupportTicketTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            sales_role = Role(name="Sales / Business Development")
            manager_role = Role(name="Management")
            self.sales = User(full_name="Sales User", email="sales@example.com", password_hash="unused")
            self.manager = User(full_name="Manager", email="manager@example.com", password_hash="unused")
            self.sales.roles.append(sales_role)
            self.manager.roles.append(manager_role)
            db.add_all([self.sales, self.manager])
            db.commit()
            self.sales_id = self.sales.id
            self.manager_id = self.manager.id

    def tearDown(self):
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def payload(self, **changes):
        values = {"subject": "Cannot access portal", "description": "The client receives an access denied page."}
        values.update(changes)
        return SupportTicketCreate(**values)

    def test_create_assign_and_scope_to_creator_or_assignee(self):
        with self.Session() as db:
            sales = db.get(User, self.sales_id)
            manager = db.get(User, self.manager_id)
            ticket = create_support_ticket(self.payload(), db=db, user=sales)
            self.assertEqual(ticket.status, "open")
            self.assertEqual(ticket.assignee_id, sales.id)

            assigned = create_support_ticket(self.payload(subject="Billing question", assignee_id=sales.id), db=db, user=manager)
            self.assertEqual(assigned.assignee_id, sales.id)
            self.assertEqual(db.query(Notification).filter_by(related_id=assigned.id, related_type="support_ticket").count(), 1)

            rows = list_support_tickets(page=1, page_size=10, db=db, user=sales)
            self.assertEqual({row.id for row in rows}, {ticket.id, assigned.id})

    def test_support_manager_assignment_and_contact_consistency(self):
        with self.Session() as db:
            manager = db.get(User, self.manager_id)
            first_org = Organization(name="Northstar Ltd")
            second_org = Organization(name="Pine Labs")
            db.add_all([first_org, second_org])
            db.flush()
            contact = Contact(organization_id=first_org.id, first_name="Anya")
            db.add(contact)
            db.commit()

            with self.assertRaises(HTTPException) as mismatch:
                create_support_ticket(
                    self.payload(organization_id=second_org.id, contact_id=contact.id), db=db, user=manager
                )
            self.assertEqual(mismatch.exception.status_code, 422)

    def test_ticket_resolution_requires_details_and_records_them(self):
        with self.Session() as db:
            sales = db.get(User, self.sales_id)
            ticket = create_support_ticket(self.payload(), db=db, user=sales)
            with self.assertRaises(HTTPException) as missing_resolution:
                update_support_ticket(ticket.id, SupportTicketUpdate(status="resolved"), db=db, user=sales)
            self.assertEqual(missing_resolution.exception.status_code, 422)

            updated = update_support_ticket(
                ticket.id,
                SupportTicketUpdate(status="resolved", resolution="Reset the account and confirmed sign-in."),
                db=db,
                user=sales,
            )
            self.assertEqual(updated.status, "resolved")
            self.assertEqual(updated.resolution, "Reset the account and confirmed sign-in.")

    def test_only_support_managers_can_reassign(self):
        with self.Session() as db:
            sales = db.get(User, self.sales_id)
            ticket = create_support_ticket(self.payload(), db=db, user=sales)
            with self.assertRaises(HTTPException) as forbidden:
                update_support_ticket(ticket.id, SupportTicketUpdate(assignee_id=self.manager_id), db=db, user=sales)
            self.assertEqual(forbidden.exception.status_code, 403)

    def test_ticket_search_and_filter(self):
        with self.Session() as db:
            sales = db.get(User, self.sales_id)
            self.create_ticket = create_support_ticket(self.payload(), db=db, user=sales)
            self.create_ticket.status = "waiting"
            db.commit()
            rows = list_support_tickets(search="portal", status="waiting", page=1, page_size=10, db=db, user=sales)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].status, "waiting")


if __name__ == "__main__":
    unittest.main()
