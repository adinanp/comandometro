from django.urls import path
from .views import CardSearchView

urlpatterns = [
    path("buscar/", CardSearchView.as_view(), name="card-search"),
]
