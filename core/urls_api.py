from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views_api

router = DefaultRouter()
router.register(r'projects', views_api.ProjectViewSet, basename='project')
router.register(r'terminals', views_api.TerminalViewSet, basename='terminal')
router.register(r'prompts', views_api.PromptViewSet, basename='prompt')
router.register(r'templates', views_api.TemplateViewSet, basename='template')
router.register(r'sessions', views_api.SessionViewSet, basename='session')
router.register(r'services', views_api.ServicePortViewSet, basename='service')

urlpatterns = [
    path('stats/', views_api.stats_api, name='api-stats'),
    path('hook/prompt/', views_api.hook_prompt, name='api-hook-prompt'),
    path('hook/stop/', views_api.hook_stop, name='api-hook-stop'),
    path('discover/', views_api.discover_services, name='api-discover'),
    path('', include(router.urls)),
]
