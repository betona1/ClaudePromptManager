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
    path('projects/<int:pk>/screenshot/', views_api.upload_screenshot, name='api-upload-screenshot'),
    path('screenshots/<int:pk>/delete/', views_api.delete_screenshot, name='api-delete-screenshot'),
    path('projects/<int:pk>/favorite/', views_api.toggle_favorite, name='api-toggle-favorite'),
    path('projects/<int:pk>/todos/', views_api.project_todos, name='api-project-todos'),
    path('todos/<int:pk>/', views_api.project_todo_detail, name='api-todo-detail'),
    path('projects/<int:pk>/delete/', views_api.delete_project, name='api-delete-project'),
    path('stats/', views_api.stats_api, name='api-stats'),
    path('hooks/health/', views_api.hooks_health, name='api-hooks-health'),
    path('hook/prompt/', views_api.hook_prompt, name='api-hook-prompt'),
    path('hook/stop/', views_api.hook_stop, name='api-hook-stop'),
    path('hook/import/', views_api.hook_import, name='api-hook-import'),
    path('discover/', views_api.discover_services, name='api-discover'),
    path('github/accounts/', views_api.github_accounts_list, name='api-github-accounts'),
    path('github/accounts/add/', views_api.github_accounts_add, name='api-github-accounts-add'),
    path('github/accounts/<int:pk>/delete/', views_api.github_accounts_delete, name='api-github-accounts-delete'),
    path('github/repos/', views_api.github_repos, name='api-github-repos'),
    path('github/sync/', views_api.github_sync, name='api-github-sync'),
    path('execute/', views_api.execute_prompt, name='api-execute'),
    path('execute/list/', views_api.execution_list, name='api-execution-list'),
    path('execute/<int:execution_id>/stream/', views_api.execution_stream, name='api-execution-stream'),
    path('execute/<int:execution_id>/cancel/', views_api.cancel_execution_view, name='api-execution-cancel'),
    path('telegram/bots/', views_api.telegram_bots_list, name='api-telegram-bots'),
    path('telegram/bots/add/', views_api.telegram_bots_add, name='api-telegram-bots-add'),
    path('telegram/bots/<int:pk>/delete/', views_api.telegram_bots_delete, name='api-telegram-bots-delete'),
    path('telegram/bots/<int:pk>/test/', views_api.telegram_bot_test, name='api-telegram-bot-test'),
    path('telegram/bots/<int:pk>/chat-ids/add/', views_api.telegram_chat_id_add, name='api-telegram-chat-id-add'),
    path('telegram/chat-ids/<int:pk>/delete/', views_api.telegram_chat_id_delete, name='api-telegram-chat-id-delete'),
    path('prompts/<int:pk>/comments/', views_api.prompt_comments, name='api-prompt-comments'),
    path('auth/profile/', views_api.api_profile, name='api-auth-profile'),
    path('auth/token/regenerate/', views_api.api_regenerate_token, name='api-auth-regenerate-token'),
    path('', include(router.urls)),
]
