from django.urls import path
from apps.pods.views import (
    PodCreateView,
    PodJoinByLinkView,
    PodJoinView,
    PodListView,
)

urlpatterns = [
    path("", PodListView.as_view(), name="pod-list"),
    path("novo/", PodCreateView.as_view(), name="pod-create"),
    path("entrar/", PodJoinByLinkView.as_view(), name="pod-join-by-link"),
    path("entrar/<uuid:token>/", PodJoinView.as_view(), name="pod-join"),
]
