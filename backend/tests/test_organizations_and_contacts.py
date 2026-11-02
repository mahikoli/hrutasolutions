import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Activity, Contact, Organization, Role, User
from app.routers.crm import (
    create_contact,
    create_organization,
    delete_contact,
    delete_organization,
    list_organizations,
    update_contact,
    update_organization,
)
from app.schemas import ContactCreate, ContactUpdate, OrganizationCreate, OrganizationUpdate


class OrganizationAndContactTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            self.user = User(full_name="Sales User", email="sales@example.com", password_hash="unused")
            self.user.roles.append(Role(name="Sales / Business Development"))
            self.manager = User(full_name="Manager", email="manager@example.com", password_hash="unused")
            self.manager.roles.append(Role(name="Management"))
            db.add_all([self.user, self.manager])
            db.commit()
            self.user_id = self.user.id
            self.manager_id = self.manager.id

    def tearDown(self):
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_organization_create_search_and_update(self):
        with self.Session() as db:
            user = db.get(User, self.user_id)
            organization = create_organization(OrganizationCreate(name="Pune Works", industry="Technology"), db=db, user=user)
            with self.assertRaises(HTTPException) as duplicate:
                create_organization(OrganizationCreate(name="pune works"), db=db, user=user)
            self.assertEqual(duplicate.exception.status_code, 409)

            changed = update_organization(organization.id, OrganizationUpdate(name="Pune Works India"), db=db, user=user)
            self.assertEqual(changed.name, "Pune Works India")
            self.assertEqual(len(list_organizations(search="India", page=1, page_size=10, db=db, user=user)), 1)

    def test_contact_update_and_protected_delete(self):
        with self.Session() as db:
            user = db.get(User, self.user_id)
            manager = db.get(User, self.manager_id)
            first = create_organization(OrganizationCreate(name="Northstar"), db=db, user=user)
            second = create_organization(OrganizationCreate(name="Pine Labs"), db=db, user=user)
            contact = create_contact(
                ContactCreate(organization_id=first.id, first_name="Anya", email="anya@example.com"),
                db=db,
                user=user,
            )
            changed = update_contact(contact.id, ContactUpdate(organization_id=second.id, designation="Director"), db=db, user=user)
            self.assertEqual(changed.organization_id, second.id)
            self.assertEqual(changed.designation, "Director")

            db.add(Activity(contact_id=contact.id, activity_type="meeting", subject="Quarterly review", owner_id=user.id))
            db.commit()
            with self.assertRaises(HTTPException) as linked:
                delete_contact(contact.id, db=db, user=manager)
            self.assertEqual(linked.exception.status_code, 409)

            db.query(Activity).filter(Activity.contact_id == contact.id).delete()
            db.commit()
            delete_contact(contact.id, db=db, user=manager)
            self.assertIsNone(db.get(Contact, contact.id))

    def test_organization_delete_is_blocked_by_contacts(self):
        with self.Session() as db:
            user = db.get(User, self.user_id)
            manager = db.get(User, self.manager_id)
            organization = create_organization(OrganizationCreate(name="Northstar"), db=db, user=user)
            create_contact(ContactCreate(organization_id=organization.id, first_name="Anya"), db=db, user=user)
            with self.assertRaises(HTTPException) as blocked:
                delete_organization(organization.id, db=db, user=manager)
            self.assertEqual(blocked.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
