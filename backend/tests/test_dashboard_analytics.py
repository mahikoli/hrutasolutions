import unittest
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    EmployeeProfile, Invoice, Lead, Opportunity, Organization, PaymentTransaction,
    Project, Refund, Role, User,
)
from app.routers.crm import dashboard_analytics, dashboard_summary


class DashboardAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def tearDown(self):
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_management_analytics_reflect_database_records(self):
        today = date.today()
        now = datetime.combine(today, time(12, 0))
        with self.Session() as db:
            manager = User(full_name="CRM Manager", email="manager@example.com", password_hash="unused")
            manager.roles.append(Role(name="Management"))
            db.add(manager)
            db.flush()
            db.add_all([
                EmployeeProfile(user_id=manager.id, employee_code="EMP-ANALYTICS"),
                Organization(name="Analytics Client", organization_type="client"),
            ])

            db.add_all([
                Lead(first_name="Asha", interest="IT services", source="Website", status="converted", owner_id=manager.id, created_at=now),
                Lead(first_name="Ravi", interest="Training", source="Referral", status="qualified", owner_id=manager.id, created_at=now),
                Opportunity(name="Won project", stage="won", expected_value=Decimal("1250.00"), owner_id=manager.id),
                Project(name="Active build", status="active", project_manager_id=manager.id),
                Project(name="Finished build", status="completed", project_manager_id=manager.id),
            ])
            invoice = Invoice(invoice_number="INV-ANALYTICS", description="Service", amount=Decimal("200"))
            db.add(invoice)
            db.flush()
            payment = PaymentTransaction(
                invoice_id=invoice.id, amount=Decimal("100"), payment_date=today,
                method="bank_transfer", recorded_by_id=manager.id,
            )
            db.add(payment)
            db.flush()
            db.add(Refund(
                payment_id=payment.id, amount=Decimal("25"), status="processed",
                processed_at=now,
            ))
            db.commit()

            result = dashboard_analytics(months=6, db=db, user=manager)
            summary = dashboard_summary(db=db, user=manager)

        current_month = today.strftime("%Y-%m")
        current_revenue = next(row for row in result["revenue_monthly"] if row["month"] == current_month)
        current_leads = next(row for row in result["lead_conversion_monthly"] if row["month"] == current_month)
        self.assertEqual(current_revenue["net_received"], "75.00")
        self.assertEqual(current_leads["leads"], 2)
        self.assertEqual(current_leads["converted"], 1)
        self.assertEqual(current_leads["conversion_rate"], 50.0)
        self.assertEqual(result["project_status_distribution"], [
            {"status": "active", "count": 1}, {"status": "completed", "count": 1}
        ])
        self.assertEqual(result["sales_performance"][0]["won_value"], "1250.00")
        self.assertEqual(result["lead_sources"], [
            {"source": "Referral", "leads": 1, "converted": 0},
            {"source": "Website", "leads": 1, "converted": 1},
        ])
        self.assertEqual(summary["clients_total"], 1)
        self.assertEqual(summary["employees_total"], 1)
        self.assertEqual(summary["lead_conversion_rate"], 50.0)
        self.assertEqual(summary["monthly_revenue"], "75.00")

    def test_sales_analytics_are_limited_to_the_current_user(self):
        today = date.today()
        now = datetime.combine(today, time(12, 0))
        with self.Session() as db:
            sales = User(full_name="Sales Rep", email="rep@example.com", password_hash="unused")
            sales.roles.append(Role(name="Sales / Business Development"))
            other = User(full_name="Other Rep", email="other@example.com", password_hash="unused")
            db.add_all([sales, other])
            db.flush()
            db.add_all([
                Lead(first_name="Mine", interest="IT services", source="Website", status="converted", owner_id=sales.id, created_at=now),
                Lead(first_name="Theirs", interest="Training", source="Referral", status="qualified", owner_id=other.id, created_at=now),
                Opportunity(name="My deal", stage="won", expected_value=Decimal("300"), owner_id=sales.id),
                Opportunity(name="Their deal", stage="won", expected_value=Decimal("900"), owner_id=other.id),
            ])
            db.commit()

            result = dashboard_analytics(months=3, db=db, user=sales)

        current_leads = next(row for row in result["lead_conversion_monthly"] if row["month"] == today.strftime("%Y-%m"))
        self.assertEqual(current_leads["leads"], 1)
        self.assertEqual(result["lead_sources"], [{"source": "Website", "leads": 1, "converted": 1}])
        self.assertEqual(result["sales_performance"], [{"employee": "Sales Rep", "won_deals": 1, "won_value": "300.00"}])
        self.assertIsNone(result["revenue_monthly"])
        self.assertIsNone(result["project_status_distribution"])


if __name__ == "__main__":
    unittest.main()
