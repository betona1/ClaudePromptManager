from django.urls import path
from . import views_web

urlpatterns = [
    path('', views_web.dashboard, name='dashboard'),
    path('projects/', views_web.project_list, name='project-list'),
    path('projects/<int:pk>/', views_web.project_detail, name='project-detail'),
    path('projects/<int:pk>/docs/<str:filename>', views_web.project_md, name='project-md'),
    path('prompts/', views_web.prompt_list, name='prompt-list'),
    path('prompts/<int:pk>/', views_web.prompt_detail, name='prompt-detail'),
    path('search/', views_web.search, name='search'),
    path('export/', views_web.export_view, name='export'),
    path('remote/', views_web.remote_execute, name='remote-execute'),
]
