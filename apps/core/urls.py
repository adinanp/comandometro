from django.urls import path
from . import views
from .views.dashboard import DashboardView

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
]
