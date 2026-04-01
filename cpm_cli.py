#!/usr/bin/env python3
"""
CPM v2 CLI — Simplified command wrapper for Django management commands.

Usage:
    cpm2 setup              # Install hooks + init DB
    cpm2 web [--port 9200]  # Start web server
    cpm2 import [--all]     # Import from Claude Code history
    cpm2 export [--project name] [--output file.json]
    cpm2 board              # Dashboard (CLI)
    cpm2 log <project>      # Project prompt log
    cpm2 search <keyword>   # Search prompts
    cpm2 status <id> <ok|fail|wip>  # Change prompt status
    cpm2 project add <name> [--path p] [--desc d]
    cpm2 project list
"""
import os
import sys
import argparse

# Set Django settings before any Django imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cpm.settings')

# Add the cpm project directory to path
CPM_DIR = os.path.dirname(os.path.abspath(__file__))
if CPM_DIR not in sys.path:
    sys.path.insert(0, CPM_DIR)


def setup_django():
    import django
    django.setup()


def cmd_setup(args):
    setup_django()
    from django.core.management import call_command
    call_command('cpm_setup')


def cmd_web(args):
    setup_django()
    from django.core.management import call_command
    call_command('cpm_web', port=args.port)


def cmd_import(args):
    setup_django()
    from django.core.management import call_command
    kwargs = {}
    if args.history:
        kwargs['history'] = True
    elif args.sessions:
        kwargs['sessions'] = True
    else:
        kwargs['all'] = True
    call_command('cpm_import', **kwargs)


def cmd_export(args):
    setup_django()
    from django.core.management import call_command
    kwargs = {}
    if args.project:
        kwargs['project'] = args.project
    if args.output:
        kwargs['output'] = args.output
    call_command('cpm_export', **kwargs)


def cmd_board(args):
    setup_django()
    from core.models import Project, Prompt
    from django.db.models import Count, Q

    projects = Project.objects.annotate(
        total=Count('prompts'),
        ok=Count('prompts', filter=Q(prompts__status='success')),
        ng=Count('prompts', filter=Q(prompts__status='fail')),
        wip=Count('prompts', filter=Q(prompts__status='wip')),
    ).order_by('-updated_at')

    total = Prompt.objects.count()
    success = Prompt.objects.filter(status='success').count()
    fail = Prompt.objects.filter(status='fail').count()
    wip = Prompt.objects.filter(status='wip').count()

    print(f"\n{'='*50}")
    print(f"  CPM Dashboard")
    print(f"  Total: {total}  OK: {success}  Fail: {fail}  WIP: {wip}")
    print(f"{'='*50}")
    for p in projects:
        print(f"  {p.name:<20} {p.total:>4} ({p.ok} ok, {p.ng} fail, {p.wip} wip)")
    print()


def cmd_log(args):
    setup_django()
    from core.models import Project, Prompt

    try:
        project = Project.objects.get(name=args.project)
    except Project.DoesNotExist:
        try:
            project = Project.objects.get(id=int(args.project))
        except (Project.DoesNotExist, ValueError):
            print(f"Project '{args.project}' not found")
            return

    qs = project.prompts.order_by('-created_at')
    if args.status:
        qs = qs.filter(status=args.status)
    if args.limit:
        qs = qs[:args.limit]

    print(f"\n=== {project.name} ({project.path or ''}) ===\n")
    for pr in qs:
        icon = {'success': 'OK', 'fail': 'NG', 'wip': '..'}[pr.status]
        content = pr.content[:60].replace('\n', ' ')
        print(f"  #{pr.id:<5} [{icon}] {content}")
        if pr.response_summary:
            resp = pr.response_summary[:70].replace('\n', ' ')
            print(f"         -> {resp}")
    print()


def cmd_search(args):
    setup_django()
    from core.models import Prompt
    from django.db.models import Q

    keyword = args.keyword
    results = Prompt.objects.select_related('project').filter(
        Q(content__icontains=keyword) |
        Q(response_summary__icontains=keyword) |
        Q(note__icontains=keyword)
    ).order_by('-created_at')[:args.limit]

    print(f"\nSearch: '{keyword}' ({len(results)} results)\n")
    for pr in results:
        content = pr.content[:60].replace('\n', ' ')
        print(f"  #{pr.id:<5} [{pr.status}] {pr.project.name}: {content}")
    print()


def cmd_status(args):
    setup_django()
    from core.models import Prompt

    try:
        prompt = Prompt.objects.get(id=args.id)
    except Prompt.DoesNotExist:
        print(f"Prompt #{args.id} not found")
        return

    status_map = {'ok': 'success', 'fail': 'fail', 'wip': 'wip', 'success': 'success'}
    new_status = status_map.get(args.new_status, args.new_status)
    prompt.status = new_status
    prompt.save(update_fields=['status', 'updated_at'])
    print(f"Prompt #{args.id} -> {new_status}")


def cmd_project_add(args):
    setup_django()
    from core.models import Project

    try:
        Project.objects.create(
            name=args.name,
            path=args.path or '',
            description=args.desc or '',
        )
        print(f"Project '{args.name}' created")
    except Exception as e:
        print(f"Error: {e}")


def cmd_project_list(args):
    setup_django()
    from core.models import Project
    from django.db.models import Count

    projects = Project.objects.annotate(cnt=Count('prompts')).order_by('-updated_at')
    for p in projects:
        print(f"  [{p.id}] {p.name:<20} {p.cnt:>4} prompts  {p.path or ''}")
    if not projects:
        print("  No projects")


def build_parser():
    parser = argparse.ArgumentParser(prog='cpm2', description='CPM v2 — Claude Prompt Manager')
    sub = parser.add_subparsers(dest='command')

    sub.add_parser('setup', help='Install hooks + init DB')

    p_web = sub.add_parser('web', help='Start web server')
    p_web.add_argument('--port', type=int, default=9200)

    p_imp = sub.add_parser('import', aliases=['import-history'], help='Import from Claude Code history')
    p_imp.add_argument('--history', action='store_true')
    p_imp.add_argument('--sessions', action='store_true')
    p_imp.add_argument('--all', action='store_true', default=True)

    p_exp = sub.add_parser('export', help='Export to JSON')
    p_exp.add_argument('--project', '-p')
    p_exp.add_argument('--output', '-o', default='cpm_export.json')

    sub.add_parser('board', aliases=['b'], help='Dashboard')

    p_log = sub.add_parser('log', aliases=['l'], help='Project prompt log')
    p_log.add_argument('project', help='Project name or ID')
    p_log.add_argument('--status', '-s', choices=['wip', 'success', 'fail'])
    p_log.add_argument('--limit', '-n', type=int, default=30)

    p_search = sub.add_parser('search', help='Search prompts')
    p_search.add_argument('keyword')
    p_search.add_argument('--limit', '-n', type=int, default=20)

    p_st = sub.add_parser('status', help='Change prompt status')
    p_st.add_argument('id', type=int)
    p_st.add_argument('new_status', choices=['ok', 'fail', 'wip', 'success'])

    p_proj = sub.add_parser('project', aliases=['p'], help='Project management')
    p_proj_sub = p_proj.add_subparsers(dest='subcmd')

    p_pa = p_proj_sub.add_parser('add', help='Add project')
    p_pa.add_argument('name')
    p_pa.add_argument('--path', '-p')
    p_pa.add_argument('--desc', '-d')

    p_proj_sub.add_parser('list', aliases=['ls'], help='List projects')

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cmd = args.command
    routes = {
        'setup': cmd_setup,
        'web': cmd_web,
        'import': cmd_import,
        'import-history': cmd_import,
        'export': cmd_export,
        'board': cmd_board, 'b': cmd_board,
        'log': cmd_log, 'l': cmd_log,
        'search': cmd_search,
        'status': cmd_status,
    }

    if cmd in routes:
        routes[cmd](args)
    elif cmd in ('project', 'p'):
        subcmd = getattr(args, 'subcmd', None)
        if subcmd == 'add':
            cmd_project_add(args)
        elif subcmd in ('list', 'ls'):
            cmd_project_list(args)
        elif subcmd is None:
            cmd_project_list(args)
        else:
            parser.print_help()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
