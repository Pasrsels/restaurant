from django.urls import path
from .views import ProductionListView

urlpatterns = [
    path("plans/", ProductionListView.as_view(), name="production-list"),
]
