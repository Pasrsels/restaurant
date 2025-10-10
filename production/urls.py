from django.urls import path
from .views import *

app_name = "production"

urlpatterns = [
    path("plans/", ProductionListView.as_view(), name="production-list"),
    path("plan/<int:pk>/", ProductionDetailView.as_view(), name="production-detail"),
    path("create/", create_production_plan, name="create_production"),
    path("confirm/production/<int:pp_id>/", confirm_production, name="confirm_production"),
    path("confirm/production/item/", confirm_production_item, name="confirm_production_item"),
    path('confirm/', confirm, name='confirm'), # confirm the whole production
    path('declare/production/', declare_production, name="declare_production")

    path("dishes/list/", DishListView.as_view(), name="dish_list"),
    path("dish/create/", create_dish, name="create_dish"),
    path("dish/edit/<int:dish_id>/", edit_dish, name="dish_edit"),
    # path("dish/delete/<int:dish_id>/", delete_dish, name="delete_dish"),
    path("dish/json/detail/", dish_json_detail, name="dish_json_detail"),
]
