from django.contrib import admin
from .models import Project, Terminal, Prompt, Template, Session, ToolCall, ServicePort


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'path', 'created_at', 'updated_at']
    search_fields = ['name', 'path', 'description']


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
