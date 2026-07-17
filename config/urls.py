from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from accounts.views import (
    panel_settings,
    panel_user_create,
    panel_user_edit,
    panel_user_project_access_add,
    panel_user_project_access_remove,
    profile_settings,
)
from assets.views import protected_render_asset
from projects.views import (
    add_project_user,
    create_atlas,
    create_project,
    create_render,
    create_world_folder,
    dashboard,
    delete_atlas,
    delete_render,
    edit_atlas,
    edit_project,
    edit_render,
    edit_world_folder,
    manage_projects,
    project_detail,
    remove_project_membership,
    scan_world_folders,
    world_folders,
)
from viewer.views import render_status, render_viewer, trigger_render

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('profile/', profile_settings, name='profile_settings'),
    path('settings/', panel_settings, name='panel_settings'),
    path('settings/projects/', manage_projects, name='manage_projects'),
    path('settings/projects/create/', create_project, name='create_project'),
    path('settings/projects/<int:project_id>/edit/', edit_project, name='edit_project'),
    path('settings/world-folders/', world_folders, name='world_folders'),
    path('settings/world-folders/scan/', scan_world_folders, name='scan_world_folders'),
    path('settings/world-folders/create/', create_world_folder, name='create_world_folder'),
    path('settings/world-folders/<int:world_id>/edit/', edit_world_folder, name='edit_world_folder'),
    path('settings/users/create/', panel_user_create, name='panel_user_create'),
    path('settings/users/<int:user_id>/edit/', panel_user_edit, name='panel_user_edit'),
    path(
        'settings/users/<int:user_id>/project-access/add/',
        panel_user_project_access_add,
        name='panel_user_project_access_add',
    ),
    path(
        'settings/users/<int:user_id>/project-access/<int:membership_id>/remove/',
        panel_user_project_access_remove,
        name='panel_user_project_access_remove',
    ),
    path('projects/<slug:slug>/', project_detail, name='project_detail'),
    path('projects/<slug:slug>/atlases/create/', create_atlas, name='create_atlas'),
    path('projects/<slug:slug>/users/add/', add_project_user, name='add_project_user'),
    path(
        'projects/<slug:slug>/memberships/<int:membership_id>/remove/',
        remove_project_membership,
        name='remove_project_membership',
    ),
    path('atlases/<int:atlas_id>/edit/', edit_atlas, name='edit_atlas'),
    path('atlases/<int:atlas_id>/delete/', delete_atlas, name='delete_atlas'),
    path('atlases/<int:atlas_id>/renders/create/', create_render, name='create_render'),
    path('renders/<int:render_id>/edit/', edit_render, name='edit_render'),
    path('renders/<int:render_id>/delete/', delete_render, name='delete_render'),
    path('renders/<int:render_id>/', render_viewer, name='render_viewer'),
    path('renders/<int:render_id>/status/', render_status, name='render_status'),
    path('renders/<int:render_id>/trigger/', trigger_render, name='trigger_render'),
    path(
        'renders/<int:render_id>/assets/<path:asset_path>',
        protected_render_asset,
        name='protected_render_asset',
    ),
]
