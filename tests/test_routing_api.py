import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from scripts.routing_api import create_app


class RoutingApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(engine=object())
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()

    @patch("scripts.routing_api.route_rescue_dispatch")
    def test_mock_rescue_alert_payload_calls_rescue_router(self, route_dispatch):
        route_dispatch.return_value = {
            "status": "feasible",
            "scenario_id": "SC-RTN-F1",
            "route": {"geometry": {"type": "LineString", "coordinates": []}},
        }
        response = self.client.post("/route", json={
            "mode": "rescue_dispatch",
            "alert_id": "MOCK-ALERT-001",
            "facility_id": "FAC-RTN-D01",
            "incident_record_id": "RTN220012-01",
        })

        self.assertEqual(200, response.status_code)
        self.assertEqual("MOCK-ALERT-001", response.json()["alert_id"])
        self.assertEqual("rescue_dispatch", response.json()["route_type"])
        self.assertEqual("feasible", response.json()["result"]["status"])
        route_dispatch.assert_called_once_with(
            self.app.state.engine,
            "FAC-RTN-D01",
            "RTN220012-01",
        )

    @patch("scripts.routing_api.plan_evacuation")
    def test_mock_evacuation_alert_calls_scenario_planner(self, plan):
        plan.return_value = {
            "status": "partial",
            "scenario": {"scenario_id": "SC-RTN-F1"},
            "origins": [],
        }
        response = self.client.post("/route", json={
            "mode": "evacuation",
            "alert_id": "MOCK-EVAC-001",
            "scenario_id": "SC-RTN-F1",
        })

        self.assertEqual(200, response.status_code)
        self.assertEqual("evacuation", response.json()["route_type"])
        self.assertEqual("partial", response.json()["result"]["status"])
        plan.assert_called_once_with(self.app.state.engine, "SC-RTN-F1")

    def test_rejects_missing_route_identifiers(self):
        response = self.client.post("/route", json={
            "mode": "rescue_dispatch",
            "alert_id": "MOCK-ALERT-BAD",
            "facility_id": "FAC-RTN-D01",
        })

        self.assertEqual(422, response.status_code)

    def test_rejects_unknown_payload_fields(self):
        response = self.client.post("/route", json={
            "mode": "evacuation",
            "scenario_id": "SC-RTN-F1",
            "location": {"latitude": 6.7, "longitude": 80.4},
        })

        self.assertEqual(422, response.status_code)

    def test_maps_unknown_database_identifiers_to_client_error(self):
        with patch(
            "scripts.routing_api.route_rescue_dispatch",
            side_effect=ValueError("Unknown incident_record_id: missing"),
        ):
            response = self.client.post("/route", json={
                "mode": "rescue_dispatch",
                "facility_id": "FAC-RTN-D01",
                "incident_record_id": "missing",
            })

        self.assertEqual(422, response.status_code)
        self.assertIn("Unknown incident_record_id", response.json()["detail"])

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())

    def test_map_page_and_client_script_are_served(self):
        page = self.client.get("/map")
        script = self.client.get("/static/route_map.js")

        self.assertEqual(200, page.status_code)
        self.assertIn("maplibre-gl@5.6.2", page.text)
        self.assertIn('src="/static/route_map.js"', page.text)
        self.assertEqual(200, script.status_code)
        self.assertIn('fetch("/route"', script.text)

    def test_root_redirects_to_map(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(307, response.status_code)
        self.assertEqual("/map", response.headers["location"])


if __name__ == "__main__":
    unittest.main()
