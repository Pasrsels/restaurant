from django.urls import path
from . views import *

app_name='users'

urlpatterns = [
    path('users/', users ,name='users'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('register/', register, name='register'),
    path('create-company/', create_company, name='create_company'),
    path('user/edit/<int:user_id>/', user_edit, name='edit_user'),
    path('user/detail/<int:user_id>/', user_detail, name='user_detail'),
    path('get-user-data/<int:user_id>/', get_user_data, name='get_user_data'),
    path('get-branch/', getBranches, name='branches'),
    path('create-branch/', createBranch, name="create_branch"),
    path('ajax/load-branches/', load_branches, name='load_branches'),
]
