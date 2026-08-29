from django.urls import path
from apps.pods.views import PodSettingsView

urlpatterns = [
    path("config/", PodSettingsView.as_view(), name="pod-settings"),
]
