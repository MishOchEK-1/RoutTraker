from django.contrib.auth import views as auth_views
from django.urls import path

from . import views


urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.checklist_dashboard, name="checklist_dashboard"),
    path("api/state/", views.dashboard_state, name="dashboard_state"),
    path("api/checks/<int:check_id>/", views.update_check, name="update_check"),
    path(
        "api/cabinets/<int:cabinet_id>/toggle/",
        views.toggle_cabinet,
        name="toggle_cabinet",
    ),
    path("api/reset/", views.reset_checklist, name="reset_checklist"),
]
