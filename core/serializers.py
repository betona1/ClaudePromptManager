from rest_framework import serializers
from .models import Project, Terminal, Prompt, Template, Session, ToolCall, ServicePort


class ProjectSerializer(serializers.ModelSerializer):
    prompt_count = serializers.IntegerField(read_only=True, default=0)
    success_count = serializers.IntegerField(read_only=True, default=0)
    fail_count = serializers.IntegerField(read_only=True, default=0)
    wip_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Project
        fields = '__all__'


class TerminalSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True, default=None)

    class Meta:
        model = Terminal
        fields = '__all__'


class PromptSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = Prompt
        fields = '__all__'


class PromptDetailSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    terminal_name = serializers.CharField(source='terminal.name', read_only=True, default=None)
    children = serializers.SerializerMethodField()

    class Meta:
        model = Prompt
        fields = '__all__'

    def get_children(self, obj):
        children = obj.children.all()[:20]
        return PromptSerializer(children, many=True).data


class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = '__all__'


class SessionSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True, default=None)

    class Meta:
        model = Session
        fields = '__all__'


class ServicePortSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True, default=None)

    class Meta:
        model = ServicePort
        fields = '__all__'
