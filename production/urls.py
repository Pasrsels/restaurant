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
    path('declare/production/<int:plan_id>/', declare_production, name="declare_production"),
    path("dishes/list/", DishListView.as_view(), name="dish_list"),
    path("dish/create/", create_dish, name="create_dish"),
    path("dish/edit/<int:dish_id>/", edit_dish, name="dish_edit"),
    # path("dish/delete/<int:dish_id>/", delete_dish, name="delete_dish"),
    path("dish/json/detail/", dish_json_detail, name="dish_json_detail"),
    path("process-dish-declaration/<int:plan_id>/", process_dish_declaration, name="process_dish_declaration"),
    path("raw-materials/<int:production_id>/", get_raw_materials, name="get_raw_materials"),
    path("process-remaining-kgs/<int:production_id>/", process_remaining_kgs, name='process_remaining_kgs')
]
