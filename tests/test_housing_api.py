import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bcn_housing.api import router, validation_exception_handler
from bcn_housing.database import Base, configure_sqlite_engine, get_db
from bcn_housing.demo_data import seed_demo_properties
from bcn_housing.models import CustomerRequirement, Lead, Property
from fastapi.exceptions import RequestValidationError


class HousingApiTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "ADMIN_USERNAME": "demo-admin",
            "ADMIN_PASSWORD": "A-secure-demo-password-983!",
            "ADMIN_TOKEN_SECRET": "test-token-secret-that-is-at-least-32-bytes",
        })
        self.environment.start()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        configure_sqlite_engine(self.engine)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.add_exception_handler(RequestValidationError, validation_exception_handler)

        def override_get_db():
            with self.sessions() as session:
                yield session

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.environment.stop()

    def login(self):
        response = self.client.post(
            "/api/admin/login",
            json={"username": "demo-admin", "password": "A-secure-demo-password-983!"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def create_requirement(self, **overrides):
        data = {
            "transaction_type": "RENT",
            "budget_min": 900,
            "budget_max": 1600,
            "preferred_locations": ["Barcelona"],
            "property_type": "apartment",
            "bedrooms_min": 1,
            "area_min_sqm": 45,
            "contact_name": "Demo Customer",
            "contact_email": "customer@example.test",
        }
        data.update(overrides)
        response = self.client.post("/api/requirements", json=data)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_customer_submission_is_persisted_and_private(self):
        submitted = self.create_requirement()
        self.assertTrue(submitted["id"])
        self.assertTrue(submitted["lead_id"])
        self.assertNotIn("customer_email", submitted)
        self.assertEqual(
            self.client.get(f"/api/requirements/{submitted['id']}/matches").status_code,
            200,
        )
        with self.sessions() as db:
            requirement = db.get(CustomerRequirement, submitted["id"])
            lead = db.scalar(select(Lead).where(Lead.requirement_id == submitted["id"]))
            self.assertEqual(requirement.contact_email, "customer@example.test")
            self.assertEqual(lead.status, "NEW")
        self.assertEqual(self.client.get("/api/admin/leads").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/leads", headers={"Authorization": "Bearer invalid"}).status_code, 401)

    def test_invalid_budget_or_missing_contact_is_rejected(self):
        inverted = self.client.post(
            "/api/requirements",
            json={"transaction_type": "BUY", "budget_min": 1000, "budget_max": 500, "contact_name": "A", "contact_email": "a@example.test"},
        )
        self.assertEqual(inverted.status_code, 422)
        missing_contact = self.client.post(
            "/api/requirements",
            json={"transaction_type": "BUY", "contact_name": "A"},
        )
        self.assertEqual(missing_contact.status_code, 422)
        bad_type = self.client.post(
            "/api/requirements",
            json={"transaction_type": "SOMETHING", "contact_name": "A", "contact_phone": "12345678"},
        )
        self.assertEqual(bad_type.status_code, 422)
        non_finite_budget = self.client.post(
            "/api/requirements",
            content=b'{"transaction_type":"BUY","budget_max":NaN,"contact_name":"A","contact_email":"a@example.test"}',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(non_finite_budget.status_code, 422)

    def test_customer_to_viewing_admin_lead_workflow(self):
        auth = self.login()
        property_response = self.client.post(
            "/api/admin/properties",
            headers=auth,
            json={
                "transaction_type": "RENT",
                "title": "[DEMO] Test apartment",
                "location": "Barcelona",
                "neighborhood": "Eixample",
                "price": 1300,
                "area_sqm": 60,
                "bedrooms": 2,
                "property_type": "apartment",
                "data_label": "DEMO",
            },
        )
        self.assertEqual(property_response.status_code, 201, property_response.text)
        property_id = property_response.json()["id"]
        property_status = self.client.patch(
            f"/api/admin/properties/{property_id}/status",
            headers=auth,
            json={"status": "UNAVAILABLE"},
        )
        self.assertEqual(property_status.status_code, 200, property_status.text)
        self.assertEqual(self.client.get(f"/api/properties/{property_id}").status_code, 404)
        property_status = self.client.patch(
            f"/api/admin/properties/{property_id}/status",
            headers=auth,
            json={"status": "AVAILABLE"},
        )
        self.assertEqual(property_status.status_code, 200, property_status.text)

        submitted = self.create_requirement()
        matches = self.client.get(f"/api/requirements/{submitted['id']}/matches").json()
        self.assertEqual(matches["match_count"], 1)
        self.assertEqual(matches["method"], "deterministic_rules")
        self.assertEqual(matches["matches"][0]["match_score"], 100)
        self.assertNotIn("contact", matches["matches"][0])

        viewing = self.client.post(
            "/api/viewing-requests",
            json={"requirement_id": submitted["id"], "property_id": property_id, "customer_notes": "Weekend preferred"},
        )
        self.assertEqual(viewing.status_code, 201, viewing.text)
        self.assertNotIn("contact", viewing.json())
        self.assertEqual(self.client.get("/api/admin/leads", headers=auth).status_code, 200)

        agent = self.client.post(
            "/api/admin/agents",
            headers=auth,
            json={
                "profile_type": "INDEPENDENT",
                "name": "Demo Agent",
                "service_areas": ["Barcelona"],
                "specializations": ["RENT"],
                "languages": ["zh", "en"],
                "contact_email": "agent@example.test",
            },
        )
        self.assertEqual(agent.status_code, 201, agent.text)
        agent_id = agent.json()["id"]
        agent_status = self.client.patch(
            f"/api/admin/agents/{agent_id}/status",
            headers=auth,
            json={"active": False},
        )
        self.assertEqual(agent_status.status_code, 200, agent_status.text)
        agent_status = self.client.patch(
            f"/api/admin/agents/{agent_id}/status",
            headers=auth,
            json={"active": True, "verified": True},
        )
        self.assertEqual(agent_status.status_code, 200, agent_status.text)

        assigned = self.client.put(
            f"/api/admin/leads/{submitted['lead_id']}/agent",
            headers=auth,
            json={"agent_id": agent_id},
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        changed = self.client.patch(
            f"/api/admin/leads/{submitted['lead_id']}/status",
            headers=auth,
            json={"status": "VIEWING_SCHEDULED"},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        note = self.client.post(
            f"/api/admin/leads/{submitted['lead_id']}/notes",
            headers=auth,
            json={"note": "Customer contacted; schedule confirmed."},
        )
        self.assertEqual(note.status_code, 201, note.text)
        lead = self.client.get(f"/api/admin/leads/{submitted['lead_id']}", headers=auth).json()
        self.assertEqual(lead["status"], "VIEWING_SCHEDULED")
        self.assertEqual(lead["assigned_agent"]["id"], agent_id)
        self.assertEqual(len(lead["notes"]), 1)
        self.assertGreaterEqual(len(lead["history"]), 3)

        viewing_admin = self.client.get("/api/admin/viewing-requests", headers=auth)
        self.assertEqual(viewing_admin.status_code, 200, viewing_admin.text)
        self.assertEqual(viewing_admin.json()["viewing_requests"][0]["customer"]["email"], "customer@example.test")
        update = self.client.patch(
            f"/api/admin/viewing-requests/{viewing.json()['id']}",
            headers=auth,
            json={"status": "SCHEDULED", "assigned_agent_id": agent_id, "report_references": []},
        )
        self.assertEqual(update.status_code, 200, update.text)

    def test_no_match_is_explained_and_contact_is_not_public(self):
        submitted = self.create_requirement(preferred_locations=["Badalona"])
        auth = self.login()
        property_response = self.client.post(
            "/api/admin/properties",
            headers=auth,
            json={
                "transaction_type": "RENT",
                "title": "[DEMO] Barcelona test home",
                "location": "Barcelona",
                "price": 1200,
                "area_sqm": 55,
                "property_type": "apartment",
            },
        )
        self.assertEqual(property_response.status_code, 201)
        matches = self.client.get(f"/api/requirements/{submitted['id']}/matches").json()
        self.assertEqual(matches["match_count"], 0)
        self.assertEqual(len(matches["excluded_properties"]), 1)
        self.assertIn(
            "Property is outside the preferred locations",
            matches["excluded_properties"][0]["incompatible_requirements"],
        )
        public_property = self.client.get(f"/api/properties/{property_response.json()['id']}").json()
        self.assertNotIn("contact_email", public_property)

    def test_demo_seed_is_explicitly_labeled_and_idempotent(self):
        with self.sessions() as db:
            seed_demo_properties(db)
            seed_demo_properties(db)
            properties = db.scalars(select(Property)).all()
            self.assertEqual(len(properties), 3)
            self.assertTrue(all(item.data_label == "DEMO" for item in properties))
            self.assertTrue(all(item.source == "DEMO ONLY" for item in properties))


if __name__ == "__main__":
    unittest.main()
