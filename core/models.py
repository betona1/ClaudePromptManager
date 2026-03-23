from django.db import models


STATUS_CHOICES = [
    ('wip', 'WIP'),
    ('success', 'Success'),
    ('fail', 'Fail'),
]

TAG_CHOICES = [
    ('bug', 'Bug'),
    ('feature', 'Feature'),
    ('refactor', 'Refactor'),
    ('docs', 'Docs'),
    ('test', 'Test'),
    ('deploy', 'Deploy'),
    ('config', 'Config'),
    ('other', 'Other'),
]

SOURCE_CHOICES = [
    ('manual', 'Manual'),
    ('hook', 'Hook'),
    ('import', 'Import'),
]

TERMINAL_STATUS_CHOICES = [
    ('active', 'Active'),
    ('inactive', 'Inactive'),
]

SERVICE_TYPE_CHOICES = [
    ('dev', 'Dev'),
    ('prod', 'Prod'),
    ('api', 'API'),
    ('db', 'Database'),
    ('cache', 'Cache'),
    ('other', 'Other'),
]

SERVICE_STATUS_CHOICES = [
    ('active', 'Active'),
    ('inactive', 'Inactive'),
    ('unknown', 'Unknown'),
]

PROTOCOL_CHOICES = [
    ('http', 'HTTP'),
    ('https', 'HTTPS'),
    ('tcp', 'TCP'),
]


class Project(models.Model):
    name = models.CharField(max_length=255, unique=True)
    path = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    url = models.URLField(blank=True, null=True, help_text='Project web URL for screenshot capture')
    deploy_url = models.URLField(blank=True, null=True, help_text='Production/deployed URL')
    server_info = models.CharField(max_length=500, blank=True, null=True, help_text='Server/host info (e.g. 100서버, 80서버, MacBook)')
    github_url = models.URLField(blank=True, null=True, help_text='GitHub repository URL')
    screenshot = models.CharField(max_length=500, blank=True, null=True, help_text='Screenshot file path')
    favorited = models.BooleanField(default=False, help_text='Heart-marked active project')
    # Token usage (aggregated from session files)
    total_input_tokens = models.BigIntegerField(default=0)
    total_output_tokens = models.BigIntegerField(default=0)
    total_cache_read_tokens = models.BigIntegerField(default=0)
    total_cache_create_tokens = models.BigIntegerField(default=0)

    class Meta:
        db_table = 'projects'
        ordering = ['-updated_at']

    def __str__(self):
        return self.name


class ProjectScreenshot(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='screenshots')
    filepath = models.CharField(max_length=500)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'project_screenshots'
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"{self.project.name} - {self.filepath}"


class Terminal(models.Model):
    name = models.CharField(max_length=255, unique=True)
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='terminals'
    )
    session_id = models.CharField(max_length=255, blank=True, null=True)
    memo = models.TextField(blank=True, null=True)
    last_activity = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # v2 additions
    pid = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=TERMINAL_STATUS_CHOICES, default='inactive')
    cwd = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'terminals'
        ordering = ['-last_activity', '-created_at']

    def __str__(self):
        return self.name


class Prompt(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE,
        related_name='prompts'
    )
    terminal = models.ForeignKey(
        Terminal, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='prompts'
    )
    content = models.TextField()
    response_summary = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='wip')
    tag = models.CharField(max_length=20, choices=TAG_CHOICES, blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='children'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    # v2 additions
    session_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='manual')
    duration_ms = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = 'prompts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project'], name='idx_prompts_project_v2'),
            models.Index(fields=['status'], name='idx_prompts_status_v2'),
            models.Index(fields=['tag'], name='idx_prompts_tag_v2'),
            models.Index(fields=['parent'], name='idx_prompts_parent_v2'),
        ]

    def __str__(self):
        return f"#{self.id} [{self.status}] {self.content[:50]}"


class Template(models.Model):
    name = models.CharField(max_length=255, unique=True)
    content = models.TextField()
    tag = models.CharField(max_length=20, choices=TAG_CHOICES, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'templates'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Session(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sessions'
    )
    terminal = models.ForeignKey(
        Terminal, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sessions'
    )
    project_path = models.TextField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    ended_at = models.DateTimeField(blank=True, null=True)
    message_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'sessions'
        ordering = ['-started_at']

    def __str__(self):
        return f"Session {self.id[:8]}..."


class ToolCall(models.Model):
    prompt = models.ForeignKey(
        Prompt, on_delete=models.CASCADE, null=True, blank=True,
        related_name='tool_calls'
    )
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, null=True, blank=True,
        related_name='tool_calls'
    )
    tool_name = models.CharField(max_length=255)
    tool_input_summary = models.TextField(blank=True, null=True)
    success = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tool_calls'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tool_name} ({'ok' if self.success else 'fail'})"


class ServicePort(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='services'
    )
    server_name = models.CharField(max_length=255)
    ip = models.GenericIPAddressField()
    port = models.IntegerField()
    service_name = models.CharField(max_length=255)
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPE_CHOICES, default='dev')
    protocol = models.CharField(max_length=10, choices=PROTOCOL_CHOICES, default='http')
    status = models.CharField(max_length=20, choices=SERVICE_STATUS_CHOICES, default='unknown')
    remarks = models.TextField(blank=True, null=True)
    # Docker deployment info
    is_docker = models.BooleanField(default=False)
    docker_image = models.CharField(max_length=500, blank=True, default='')
    docker_container = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'service_ports'
        unique_together = [('ip', 'port')]
        ordering = ['server_name', 'port']

    def __str__(self):
        return f"{self.server_name} {self.ip}:{self.port} ({self.service_name})"


EXECUTION_STATUS_CHOICES = [
    ('queued', 'Queued'),
    ('running', 'Running'),
    ('completed', 'Completed'),
    ('failed', 'Failed'),
    ('cancelled', 'Cancelled'),
]


class Execution(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='executions'
    )
    prompt = models.ForeignKey(
        Prompt, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='executions'
    )
    command = models.TextField(help_text='The prompt sent to Claude Code')
    cwd = models.TextField(help_text='Working directory for execution')
    status = models.CharField(max_length=20, choices=EXECUTION_STATUS_CHOICES, default='queued')
    output = models.TextField(blank=True, default='')
    error = models.TextField(blank=True, default='')
    exit_code = models.IntegerField(null=True, blank=True)
    pid = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    duration_ms = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'executions'
        ordering = ['-created_at']

    def __str__(self):
        return f"Exec #{self.id} [{self.status}] {self.command[:50]}"


TODO_CATEGORY_CHOICES = [
    ('task', 'Task'),
    ('deploy', 'Deploy'),
]


class ProjectTodo(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='todos'
    )
    title = models.CharField(max_length=500)
    category = models.CharField(max_length=20, choices=TODO_CATEGORY_CHOICES, default='task')
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'project_todos'
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        check = '[x]' if self.is_completed else '[ ]'
        return f"{check} {self.title}"


class GitHubAccount(models.Model):
    username = models.CharField(max_length=255, unique=True)
    token = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True, default='')
    avatar_url = models.URLField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'github_accounts'
        ordering = ['username']

    def __str__(self):
        return self.username


class TelegramBot(models.Model):
    bot_token = models.CharField(max_length=500, unique=True)
    bot_username = models.CharField(max_length=255)
    bot_name = models.CharField(max_length=255, blank=True, default='')
    chat_id = models.CharField(max_length=100, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'telegram_bots'
        ordering = ['-created_at']

    def __str__(self):
        return f"@{self.bot_username}"


class TelegramChatId(models.Model):
    bot = models.ForeignKey(TelegramBot, on_delete=models.CASCADE, related_name='chat_ids')
    chat_id = models.CharField(max_length=100)
    label = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'telegram_chat_ids'
        unique_together = [('bot', 'chat_id')]
        ordering = ['created_at']

    def __str__(self):
        return f"{self.chat_id} ({self.label})" if self.label else self.chat_id
