from django.contrib import admin
from .models import (
    Project, ProjectScreenshot, ProjectTodo, Terminal, Prompt, Template,
    Session, ToolCall, ServicePort, UserProfile, Follow, Comment,
    ServerIdentity, FederatedServer, FederatedSubscription, FederatedPrompt,
    FederatedUser, FederatedComment,
)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'path', 'created_at', 'updated_at']
    search_fields = ['name', 'path', 'description']


@admin.register(ProjectScreenshot)
class ProjectScreenshotAdmin(admin.ModelAdmin):
    list_display = ['id', 'project', 'filepath', 'order', 'created_at']
    list_filter = ['project']


@admin.register(ProjectTodo)
class ProjectTodoAdmin(admin.ModelAdmin):
    list_display = ['id', 'project', 'title', 'category', 'is_completed', 'sort_order', 'created_at']
    list_filter = ['is_completed', 'category', 'project']
    search_fields = ['title']


@admin.register(Terminal)
class TerminalAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'project', 'status', 'pid', 'last_activity']
    list_filter = ['status']
    search_fields = ['name', 'memo']


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ['id', 'project', 'status', 'tag', 'source', 'content_short', 'created_at']
    list_filter = ['status', 'tag', 'source']
    search_fields = ['content', 'response_summary', 'note']

    def content_short(self, obj):
        return obj.content[:80] if obj.content else ''
    content_short.short_description = 'Content'


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'tag', 'created_at']
    search_fields = ['name', 'content']


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'project', 'project_path', 'started_at', 'message_count']
    search_fields = ['id', 'project_path']


@admin.register(ToolCall)
class ToolCallAdmin(admin.ModelAdmin):
    list_display = ['id', 'tool_name', 'success', 'created_at']
    list_filter = ['tool_name', 'success']


@admin.register(ServicePort)
class ServicePortAdmin(admin.ModelAdmin):
    list_display = ['id', 'server_name', 'ip', 'port', 'service_name', 'service_type', 'status', 'project']
    list_filter = ['service_type', 'status', 'server_name']
    search_fields = ['server_name', 'ip', 'service_name', 'remarks']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['id', 'github_username', 'is_admin', 'created_at']
    search_fields = ['github_username']


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ['id', 'follower', 'following', 'created_at']


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'prompt', 'author', 'created_at']
    list_filter = ['author']


# ── Federation ──

@admin.register(ServerIdentity)
class ServerIdentityAdmin(admin.ModelAdmin):
    list_display = ['id', 'server_name', 'server_url', 'created_at']


@admin.register(FederatedServer)
class FederatedServerAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'url', 'status', 'last_sync_at', 'error_count', 'requests_today']
    list_filter = ['status']


@admin.register(FederatedSubscription)
class FederatedSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'server', 'remote_project_name', 'is_active', 'last_prompt_id']
    list_filter = ['is_active']


@admin.register(FederatedPrompt)
class FederatedPromptAdmin(admin.ModelAdmin):
    list_display = ['id', 'subscription', 'remote_prompt_id', 'status', 'remote_created_at']


@admin.register(FederatedUser)
class FederatedUserAdmin(admin.ModelAdmin):
    list_display = ['id', 'federated_id', 'username', 'server']


@admin.register(FederatedComment)
class FederatedCommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'author_name', 'author_federated_id', 'created_at']
