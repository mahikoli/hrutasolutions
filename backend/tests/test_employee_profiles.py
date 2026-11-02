import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.extended_schemas import EmployeeProfileCreate, EmployeeProfileUpdate
from app.models import EmployeeProfile, Role, User
from app.routers.expanded import create_employee_profile, list_employees, update_employee_profile


class EmployeeProfileTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            self.admin = User(full_name="Admin User", email="admin@example.com", password_hash="unused")
            self.employee = User(full_name="Neha Shah", email="neha@example.com", password_hash="unused")
            self.manager = User(full_name="Team Manager", email="manager@example.com", password_hash="unused")
            self.admin.roles.append(Role(name="Super Admin"))
            self.employee.roles.append(Role(name="Employee / Intern"))
            db.add_all([self.admin, self.employee, self.manager])
            db.commit()
            self.admin_id = self.admin.id
            self.employee_id = self.employee.id
            self.manager_id = self.manager.id

    def tearDown(self):
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_create_and_search_profile(self):
        with self.Session() as db:
            admin = db.get(User, self.admin_id)
            profile = create_employee_profile(
                EmployeeProfileCreate(
                    user_id=self.employee_id,
                    employee_code="HR-014",
                    department="Engineering",
                    designation="Frontend Developer",
                    joining_date="2025-04-01",
                    manager_id=self.manager_id,
                ),
                db=db,
                user=admin,
            )
            self.assertEqual(profile["full_name"], "Neha Shah")
            self.assertEqual(profile["roles"], ["Employee / Intern"])
            self.assertEqual(profile["manager_id"], self.manager_id)

            rows = list_employees(search="Frontend", page=1, page_size=10, db=db, user=admin)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["employee_code"], "HR-014")

    def test_employee_management_page_only_returns_own_profile_to_employee(self):
        with self.Session() as db:
            admin = db.get(User, self.admin_id)
            create_employee_profile(EmployeeProfileCreate(user_id=self.employee_id, employee_code="HR-014"), db=db, user=admin)
            other_user = User(full_name="Another Employee", email="another@example.com", password_hash="unused")
            db.add(other_user)
            db.flush()
            create_employee_profile(EmployeeProfileCreate(user_id=other_user.id, employee_code="HR-015"), db=db, user=admin)

            employee = db.get(User, self.employee_id)
            rows = list_employees(page=1, page_size=100, db=db, user=employee)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["user_id"], self.employee_id)

    def test_reject_duplicate_user_and_employee_code(self):
        with self.Session() as db:
            admin = db.get(User, self.admin_id)
            create_employee_profile(EmployeeProfileCreate(user_id=self.employee_id, employee_code="HR-014"), db=db, user=admin)
            with self.assertRaises(HTTPException) as duplicate_user:
                create_employee_profile(EmployeeProfileCreate(user_id=self.employee_id, employee_code="HR-015"), db=db, user=admin)
            self.assertEqual(duplicate_user.exception.status_code, 409)

            second_user = User(full_name="Another Employee", email="another@example.com", password_hash="unused")
            db.add(second_user)
            db.commit()
            with self.assertRaises(HTTPException) as duplicate_code:
                create_employee_profile(EmployeeProfileCreate(user_id=second_user.id, employee_code="HR-014"), db=db, user=admin)
            self.assertEqual(duplicate_code.exception.status_code, 409)

    def test_update_profile_and_duplicate_code_guard(self):
        with self.Session() as db:
            admin = db.get(User, self.admin_id)
            first = create_employee_profile(EmployeeProfileCreate(user_id=self.employee_id, employee_code="HR-014"), db=db, user=admin)
            second_user = User(full_name="Another Employee", email="another@example.com", password_hash="unused")
            db.add(second_user)
            db.flush()
            second = create_employee_profile(EmployeeProfileCreate(user_id=second_user.id, employee_code="HR-015"), db=db, user=admin)

            updated = update_employee_profile(
                first["id"], EmployeeProfileUpdate(department="Product", designation="Product Engineer"), db=db, user=admin
            )
            self.assertEqual(updated["department"], "Product")
            with self.assertRaises(HTTPException) as duplicate_code:
                update_employee_profile(first["id"], EmployeeProfileUpdate(employee_code="HR-015"), db=db, user=admin)
            self.assertEqual(duplicate_code.exception.status_code, 409)
            self.assertTrue(db.get(EmployeeProfile, second["id"]))


if __name__ == "__main__":
    unittest.main()
