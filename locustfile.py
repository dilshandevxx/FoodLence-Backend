import random
import uuid
from locust import HttpUser, task, between


class FoodLenceLoadTestUser(HttpUser):
    """
    Simulates high-concurrency mobile app users scanning food labels,
    authenticating, and managing dietary profiles.
    Target: 100 concurrent virtual users with sub-second response times.
    """
    wait_time = between(1, 3)

    sample_ocr_payloads = [
        "Ingredients: enriched wheat flour, skimmed milk powder, pasteurized whole eggs, roasted peanuts, soy lecithin.",
        "Ingredients: water, cane sugar, carbonated water, citric acid (E330), artificial color (E102, INS 110), preservative (E211).",
        "Ingredients: white rice, pure water, sunflower oil, sea salt, black pepper.",
        "Ingredients: oats, almond flour, cashew nuts, honey, chia seeds, dark chocolate (cocoa mass, sugar, cocoa butter).",
        "Ingredients: durum wheat semolina, tomatoes, extra virgin olive oil, basil, garlic, sea salt.",
    ]

    def on_start(self):
        """
        Authenticate a synthetic virtual user before starting test scenarios.
        """
        self.auth_token = None
        self.user_email = f"loadtest_{uuid.uuid4().hex[:8]}@foodlence.com"
        self.password = "LoadTestPass123!"

        # Register
        reg_payload = {
            "email": self.user_email,
            "password": self.password,
            "full_name": "Load Test Virtual User",
        }
        res = self.client.post("/api/v1/auth/register", json=reg_payload)
        if res.status_code == 201:
            data = res.json()
            self.auth_token = data.get("access_token")
        else:
            # Attempt login fallback
            login_res = self.client.post(
                "/api/v1/auth/login",
                json={"email": self.user_email, "password": self.password},
            )
            if login_res.status_code == 200:
                self.auth_token = login_res.json().get("access_token")

    @task(5)
    def analyze_food_label(self):
        """
        Highest frequency task: Simulates mobile client posting OCR text for real-time analysis.
        Target SLA: < 100ms backend inference execution latency.
        """
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        payload = {
            "ocr_text": random.choice(self.sample_ocr_payloads),
            "has_ingredient_keywords": True,
            "active_profile_allergens": ["peanut", "milk", "gluten"],
            "profile_name": "Active Load Tester",
        }

        with self.client.post(
            "/api/v1/analyze",
            json=payload,
            headers=headers,
            catch_response=True,
            name="/api/v1/analyze",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "safety_verdict" in data:
                    response.success()
                else:
                    response.failure("Missing safety_verdict in payload")
            else:
                response.failure(f"HTTP {response.status_code}: {response.text}")

    @task(2)
    def get_profiles(self):
        """
        Simulates dietary profile retrieval when user switches tabs in mobile app.
        """
        if not self.auth_token:
            return

        headers = {"Authorization": f"Bearer {self.auth_token}"}
        self.client.get(
            "/api/v1/profiles/",
            headers=headers,
            name="/api/v1/profiles",
        )

    @task(1)
    def health_check(self):
        """
        Simulates load balancer and container orchestrator health probing.
        """
        self.client.get("/health", name="/health")
