"""
cpm_export: Export CPM data to JSON.
Usage: python manage.py cpm_export [--project name] [--output file.json]
"""
import json
from datetime import datetime
from django.core.management.base import BaseCommand
from core.models import Project, Terminal, Prompt, Template, Session


class Command(BaseCommand):
    help = 'Export CPM data to JSON'

    def add_arguments(self, parser):
        parser.add_argument('--project', '-p', help='Export specific project only')
        parser.add_argument('--output', '-o', default='cpm_export.json', help='Output file path')

    def handle(self, *args, **options):
        project_filter = options['project']
        output_path = options['output']

        data = {
            'exported_at': datetime.now().isoformat(),
            'version': 'v2',
        }

        projects_qs = Project.objects.all()
        if project_filter:
            projects_qs = projects_qs.filter(name=project_filter)

        data['projects'] = list(projects_qs.values())
        project_ids = list(projects_qs.values_list('id', flat=True))

        prompts_qs = Prompt.objects.filter(project_id__in=project_ids)
        data['prompts'] = list(prompts_qs.values())

        data['terminals'] = list(Terminal.objects.all().values())
        data['templates'] = list(Template.objects.all().values())
        data['sessions'] = list(Session.objects.filter(project_id__in=project_ids).values())

        # Convert datetime objects to strings
        def convert_dt(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        def clean_data(items):
            for item in items:
                for k, v in item.items():
                    item[k] = convert_dt(v)
            return items

        for key in ['projects', 'prompts', 'terminals', 'templates', 'sessions']:
            clean_data(data[key])

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        self.stdout.write(self.style.SUCCESS(f'Exported to {output_path}'))
        self.stdout.write(f'  Projects: {len(data["projects"])}')
        self.stdout.write(f'  Prompts: {len(data["prompts"])}')
        self.stdout.write(f'  Sessions: {len(data["sessions"])}')
