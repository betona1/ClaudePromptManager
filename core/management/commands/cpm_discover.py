"""
cpm_discover: Scan network ports and register services.
Usage:
    python3 manage.py cpm_discover                          # localhost
    python3 manage.py cpm_discover --host 192.168.1.100
    python3 manage.py cpm_discover --range 8000 9300
"""
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from core.models import ServicePort
from core.views_api import COMMON_PORTS


class Command(BaseCommand):
    help = 'Scan ports and register discovered services'

    def add_arguments(self, parser):
        parser.add_argument('--host', default='127.0.0.1', help='Host to scan')
        parser.add_argument('--range', nargs=2, type=int, metavar=('START', 'END'),
                            help='Port range to scan')
        parser.add_argument('--timeout', type=float, default=0.5, help='Connection timeout')

    def handle(self, *args, **options):
        host = options['host']
        timeout = options['timeout']

        if options['range']:
            ports = range(options['range'][0], options['range'][1] + 1)
        else:
            ports = sorted(COMMON_PORTS.keys())

        self.stdout.write(f'Scanning {host} ({len(list(ports))} ports)...')

        open_ports = []

        def check(port):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(timeout)
                    return s.connect_ex((host, port)) == 0
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = {executor.submit(check, p): p for p in ports}
            for future in as_completed(futures):
                port = futures[future]
                if future.result():
                    open_ports.append(port)
                    service_name = COMMON_PORTS.get(port, f'Port {port}')
                    ServicePort.objects.update_or_create(
                        ip=host, port=port,
                        defaults={
                            'server_name': host,
                            'service_name': service_name,
                            'status': 'active',
                        }
                    )
                    self.stdout.write(self.style.SUCCESS(f'  OPEN  {host}:{port} ({service_name})'))
                else:
                    ServicePort.objects.filter(ip=host, port=port).update(status='inactive')

        open_ports.sort()
        self.stdout.write(self.style.SUCCESS(f'\nDone: {len(open_ports)} open ports on {host}'))
