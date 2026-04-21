import json
from io import BytesIO
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import ActivityLog, Cabinet, CabinetCheck, InspectionState


User = get_user_model()


class ChecklistDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ivan",
            password="strong-pass-123",
            first_name="Иван",
        )
        self.client.login(username="ivan", password="strong-pass-123")

    def get_c1_check(self):
        self.client.get(reverse("checklist_dashboard"))
        return CabinetCheck.objects.get(cabinet__name="C1")

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("checklist_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_state_returns_round_and_seeded_cabinets(self):
        response = self.client.get(reverse("dashboard_state"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["round"]["number"], 1)
        self.assertEqual(len(payload["cabinets"]), 15)
        self.assertEqual(payload["cabinets"][0]["name"], "C1")
        self.assertEqual(payload["cabinets"][-1]["name"], "CH")

    def test_update_check_saves_status_comment_and_actor(self):
        check = self.get_c1_check()

        response = self.client.post(
            reverse("update_check", args=[check.id]),
            data=json.dumps(
                {
                    "status": CabinetCheck.Status.PROBLEM,
                    "comment": "Нужно заменить лампу",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        check.refresh_from_db()
        self.assertEqual(check.status, CabinetCheck.Status.PROBLEM)
        self.assertEqual(check.comment, "Нужно заменить лампу")
        self.assertEqual(check.updated_by, self.user)
        self.assertTrue(
            ActivityLog.objects.filter(
                action=ActivityLog.Action.RESULT_UPDATED,
                cabinet_name="C1",
                status=CabinetCheck.Status.PROBLEM,
            ).exists()
        )

    def test_reset_checklist_opens_new_round_and_clears_checks(self):
        check = self.get_c1_check()
        check.status = CabinetCheck.Status.DONE
        check.comment = "Все нормально"
        check.updated_by = self.user
        check.save()

        lab = Cabinet.objects.get(name="Lab1")
        lab.included = False
        lab.can_be_skipped = True
        lab.save()

        response = self.client.post(
            reverse("reset_checklist"),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        check.refresh_from_db()
        lab.refresh_from_db()
        state = InspectionState.objects.get(pk=1)

        self.assertEqual(state.round_number, 2)
        self.assertEqual(check.status, CabinetCheck.Status.UNCHECKED)
        self.assertEqual(check.comment, "")
        self.assertIsNone(check.updated_by)
        self.assertTrue(lab.included)
        self.assertTrue(
            ActivityLog.objects.filter(
                action=ActivityLog.Action.ALL_RESET,
                details="открыл обход №2",
            ).exists()
        )

    def test_problem_report_excel_downloads_xlsx(self):
        check = self.get_c1_check()
        check.status = CabinetCheck.Status.PROBLEM
        check.comment = "Нужно заменить лампу"
        check.updated_by = self.user
        check.save()

        response = self.client.get(reverse("problem_report_excel"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn(
            'attachment; filename="routtraker-report-round-1.xlsx"',
            response["Content-Disposition"],
        )

        with ZipFile(BytesIO(response.content)) as workbook:
            sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")

        self.assertIn("Автоотчет по обходу", sheet_xml)
        self.assertIn("C1", sheet_xml)
        self.assertIn("Нужно заменить лампу", sheet_xml)
