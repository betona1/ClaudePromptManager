from django.urls import path
from django.views.generic import RedirectView
from . import views_web

urlpatterns = [
    path('', views_web.dashboard, name='dashboard'),
    path('projects/', views_web.project_list, name='project-list'),
    path('projects/<int:pk>/', views_web.project_detail, name='project-detail'),
    path('projects/<int:pk>/docs/<str:filename>', views_web.project_md, name='project-md'),
    path('prompts/', views_web.prompt_list, name='prompt-list'),
    path('prompts/<int:pk>/', views_web.prompt_detail, name='prompt-detail'),
    path('stats/', views_web.statistics, name='statistics'),
    path('search/', views_web.search, name='search'),
    path('export/', views_web.export_view, name='export'),
    path('remote/', views_web.remote_execute, name='remote-execute'),
    path('setup/', views_web.setup_guide, name='setup-guide'),
    path('setup/download/<str:filename>', views_web.download_hook, name='download-hook'),
    # Federation
    path('federation/', views_web.federation_page, name='federation'),
    # User pages
    path('login/github/', RedirectView.as_view(url='/accounts/github/login/'), name='github_login'),
    path('login/google/', RedirectView.as_view(url='/accounts/google/login/'), name='google_login'),
    path('community/', views_web.community_page, name='community'),
    path('settings/', views_web.user_settings, name='user-settings'),
    path('@<str:username>/', views_web.user_profile, name='user-profile'),
    path('@<str:username>/follow/', views_web.follow_user, name='follow-user'),
    path('@<str:username>/unfollow/', views_web.unfollow_user, name='unfollow-user'),
]
