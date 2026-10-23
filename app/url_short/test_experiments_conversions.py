import json
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from .experiments import VISITOR_COOKIE, activate_experiment, select_experiment_variant
from .forms import ExperimentCreateForm
from .models import ClickEvent, ConversionEvent, Experiment, ExperimentVariant, urlModel
from .services import ensure_personal_workspace


User = get_user_model()


class ExperimentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.user)
        self.link = urlModel.objects.create(
            workspace=self.workspace,
            owner=self.user,
            shorturl="experiment-link",
            longurl="https://fallback.example",
        )

    def create_experiment(self, weights=(50, 50)):
        experiment = Experiment.objects.create(
            link=self.link,
            name="Landing page test",
            created_by=self.user,
        )
        variants = [
            ExperimentVariant.objects.create(
                experiment=experiment,
                name="A",
                destination_url="https://a.example",
                weight=weights[0],
            ),
            ExperimentVariant.objects.create(
                experiment=experiment,
                name="B",
                destination_url="https://b.example",
                weight=weights[1],
            ),
        ]
        return experiment, variants

    def test_form_rejects_weights_that_do_not_total_100(self):
        form = ExperimentCreateForm(
            {
                "name": "Bad weights",
                "assignment_strategy": Experiment.AssignmentStrategy.DETERMINISTIC,
                "variant_a_name": "A",
                "variant_a_url": "https://a.example",
                "variant_a_weight": 70,
                "variant_b_name": "B",
                "variant_b_url": "https://b.example",
                "variant_b_weight": 20,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("total exactly 100", str(form.non_field_errors()))

    def test_activation_rejects_invalid_weights(self):
        experiment, _ = self.create_experiment((60, 30))
        with self.assertRaises(ValidationError):
            activate_experiment(experiment)
        experiment.refresh_from_db()
        self.assertEqual(experiment.status, Experiment.Status.DRAFT)

    def test_deterministic_assignment_is_stable_for_cookie(self):
        experiment, _ = self.create_experiment()
        activate_experiment(experiment)
        factory = RequestFactory()
        first_request = factory.get("/experiment-link")
        first_request.COOKIES[VISITOR_COOKIE] = "stable-visitor"
        second_request = factory.get("/experiment-link")
        second_request.COOKIES[VISITOR_COOKIE] = "stable-visitor"
        first = select_experiment_variant(self.link, first_request)
        second = select_experiment_variant(self.link, second_request)
        self.assertEqual(first.variant, second.variant)

    def test_redirect_attributes_variant_and_sets_visitor_cookie(self):
        experiment, variants = self.create_experiment()
        activate_experiment(experiment)
        response = self.client.get("/experiment-link")
        self.assertIn(response.url, {"https://a.example", "https://b.example"})
        self.assertIn(VISITOR_COOKIE, response.cookies)
        event = ClickEvent.objects.get()
        self.assertIn(event.experiment_variant, variants)


class ConversionTrackingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.user)
        self.link = urlModel.objects.create(
            workspace=self.workspace,
            owner=self.user,
            shorturl="conversion-link",
            longurl="https://shop.example/product?sku=1",
            conversion_tracking_enabled=True,
        )

    def click_token(self):
        response = self.client.get("/conversion-link")
        query = parse_qs(urlsplit(response.url).query)
        self.assertEqual(query["sku"], ["1"])
        self.assertIn("ol_click", query)
        return query["ol_click"][0]

    def test_conversion_is_attributed_to_click_and_link(self):
        token = self.click_token()
        response = self.client.post(
            "/api/conversions/",
            data=json.dumps(
                {
                    "token": token,
                    "event_type": "PURCHASE",
                    "monetary_value": "149.99",
                    "currency": "inr",
                    "deduplication_key": "order-42",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        conversion = ConversionEvent.objects.get()
        self.assertEqual(conversion.link, self.link)
        self.assertEqual(conversion.click.short_url, self.link)
        self.assertEqual(conversion.currency, "INR")

    def test_duplicate_conversion_key_is_idempotent(self):
        token = self.click_token()
        payload = {
            "token": token,
            "event_type": "SIGNUP",
            "deduplication_key": "signup-42",
        }
        first = self.client.post(
            "/api/conversions/", data=json.dumps(payload), content_type="application/json"
        )
        second = self.client.post(
            "/api/conversions/", data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        self.assertEqual(ConversionEvent.objects.count(), 1)

    def test_invalid_conversion_token_is_rejected(self):
        response = self.client.post(
            "/api/conversions/",
            data=json.dumps({"token": "not-a-token", "event_type": "SIGNUP"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ConversionEvent.objects.exists())
