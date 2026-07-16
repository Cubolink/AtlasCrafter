from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from assets.views import protected_render_asset
from projects.views import dashboard, project_detail
from viewer.views import render_viewer, trigger_render

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('projects/<slug:slug>/', project_detail, name='project_detail'),
    path('renders/<int:render_id>/', render_viewer, name='render_viewer'),
    path('renders/<int:render_id>/trigger/', trigger_render, name='trigger_render'),
    path(
        'renders/<int:render_id>/assets/<path:asset_path>',
        protected_render_asset,
        name='protected_render_asset',
    ),
]
