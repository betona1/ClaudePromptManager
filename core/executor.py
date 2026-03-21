"""
CPM Executor: Runs Claude Code CLI as subprocess and streams output.
"""
import subprocess
import threading
import time
import os
import signal
from datetime import datetime

# Global dict tracking running processes: {execution_id: subprocess.Popen}
_running_processes = {}

CLAUDE_BINARY = os.environ.get('CPM_CLAUDE_BIN', 'claude')
DEFAULT_TIMEOUT = int(os.environ.get('CPM_EXEC_TIMEOUT', '600'))  # 10 min
MAX_OUTPUT_SIZE = 500_000  # 500KB


def execute_claude(execution_id, prompt_text, cwd, timeout=None):
    """
    Generator that yields (event_type, data) tuples for SSE streaming.
    Event types: 'start', 'output', 'error', 'done'
    """
    from core.models import Execution, Prompt

    timeout = timeout or DEFAULT_TIMEOUT

    env = os.environ.copy()
    # Prevent nested Claude Code session detection
    env.pop('CLAUDE_CODE_ENTRYPOINT', None)
    env.pop('CLAUDECODE', None)

    cmd = [
        CLAUDE_BINARY,
        '-p', prompt_text,
        '--output-format', 'text',
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            preexec_fn=os.setsid,
        )
    except FileNotFoundError:
        yield ('error', 'Claude CLI not found. Is "claude" installed?')
        Execution.objects.filter(id=execution_id).update(
            status='failed', error='Claude CLI not found',
            completed_at=datetime.now()
        )
        return
    except Exception as e:
        yield ('error', f'Failed to start: {e}')
        Execution.objects.filter(id=execution_id).update(
            status='failed', error=str(e),
            completed_at=datetime.now()
        )
        return

    _running_processes[execution_id] = proc

    Execution.objects.filter(id=execution_id).update(
        status='running', pid=proc.pid,
        started_at=datetime.now()
    )

    yield ('start', f'{{"pid": {proc.pid}}}')

    accumulated_output = []
    start_time = time.time()

    # Timeout killer thread
    def kill_on_timeout():
        time.sleep(timeout)
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass

    timer = threading.Thread(target=kill_on_timeout, daemon=True)
    timer.start()

    try:
        for line in iter(proc.stdout.readline, b''):
            text = line.decode('utf-8', errors='replace')
            accumulated_output.append(text)
            yield ('output', text.rstrip('\n'))

            if time.time() - start_time > timeout:
                break

        proc.wait(timeout=5)

        stderr_output = proc.stderr.read().decode('utf-8', errors='replace')

        elapsed_ms = int((time.time() - start_time) * 1000)
        full_output = ''.join(accumulated_output)[:MAX_OUTPUT_SIZE]

        final_status = 'completed' if proc.returncode == 0 else 'failed'

        Execution.objects.filter(id=execution_id).update(
            status=final_status,
            output=full_output,
            error=stderr_output[:5000] if stderr_output else '',
            exit_code=proc.returncode,
            completed_at=datetime.now(),
            duration_ms=elapsed_ms,
        )

        # Update linked Prompt record
        exec_obj = Execution.objects.filter(id=execution_id).first()
        if exec_obj and exec_obj.prompt_id:
            Prompt.objects.filter(id=exec_obj.prompt_id).update(
                response_summary=full_output[:500],
                status='success' if proc.returncode == 0 else 'fail',
                duration_ms=elapsed_ms,
            )

        yield ('done', f'{{"exit_code": {proc.returncode}, "duration_ms": {elapsed_ms}}}')

    except Exception as e:
        yield ('error', str(e))
        Execution.objects.filter(id=execution_id).update(
            status='failed', error=str(e),
            completed_at=datetime.now()
        )
    finally:
        _running_processes.pop(execution_id, None)
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass


def cancel_execution(execution_id):
    """Cancel a running execution."""
    proc = _running_processes.get(execution_id)
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        from core.models import Execution
        Execution.objects.filter(id=execution_id).update(
            status='cancelled',
            completed_at=datetime.now()
        )
        _running_processes.pop(execution_id, None)
        return True
    return False
