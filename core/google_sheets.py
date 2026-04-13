"""
CPM Google Sheets integration.

Provides automatic prompt logging to user-configured Google Sheets.
Requires a Google Cloud service account JSON key file.

Environment variables:
  GOOGLE_SHEETS_CREDENTIALS      — path to service account JSON file
  GOOGLE_SHEETS_CREDENTIALS_JSON — inline JSON string (alternative)
"""
import json
import logging
import os
import re
import threading

logger = logging.getLogger(__name__)

_client_lock = threading.Lock()
_cached_client = None


def _get_credentials_info():
    """Return (credentials_dict, service_email) or (None, None)."""
    # Try file path first
    cred_path = os.environ.get('GOOGLE_SHEETS_CREDENTIALS', '')
    if cred_path and os.path.isfile(cred_path):
        try:
            with open(cred_path, 'r') as f:
                info = json.load(f)
            return info, info.get('client_email', '')
        except Exception:
            pass

    # Try inline JSON
    cred_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_JSON', '')
    if cred_json:
        try:
            info = json.loads(cred_json)
            return info, info.get('client_email', '')
        except Exception:
            pass

    return None, None


def get_service_email():
    """Return the service account email, or empty string if not configured."""
    _, email = _get_credentials_info()
    return email or ''


def is_available():
    """Check if Google Sheets integration is available (credentials configured)."""
    info, _ = _get_credentials_info()
    return info is not None


def get_gspread_client():
    """Get or create a cached gspread client using service account credentials."""
    global _cached_client
    with _client_lock:
        if _cached_client is not None:
            return _cached_client
        try:
            import gspread
        except ImportError:
            logger.debug("gspread not installed")
            return None

        info, _ = _get_credentials_info()
        if not info:
            return None

        try:
            client = gspread.service_account_from_dict(info)
            _cached_client = client
            return client
        except Exception as e:
            logger.warning(f"Failed to create gspread client: {e}")
            return None


def _extract_spreadsheet_key(url):
    """Extract spreadsheet key from a Google Sheets URL."""
    # https://docs.google.com/spreadsheets/d/SPREADSHEET_KEY/edit...
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url)
    return m.group(1) if m else None


def _get_or_create_worksheet(spreadsheet, sheet_name):
    """Get existing worksheet or create a new one with headers."""
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except Exception:
        # Worksheet doesn't exist, create it
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=7)

    # Check if headers exist
    try:
        first_row = ws.row_values(1)
    except Exception:
        first_row = []

    if not first_row or first_row[0] != 'ID':
        ws.update('A1:G1', [['ID', '날짜', '프로젝트', '프롬프트', '응답 요약', '상태', '태그']])

    return ws


def append_prompt_to_sheet(profile, prompt):
    """Append a prompt row to the user's Google Sheet.

    Args:
        profile: UserProfile instance with google_sheet_url/name set
        prompt: Prompt instance to log
    """
    if not profile.google_sheet_enabled or not profile.google_sheet_url:
        return False

    client = get_gspread_client()
    if not client:
        return False

    key = _extract_spreadsheet_key(profile.google_sheet_url)
    if not key:
        logger.warning(f"Invalid Google Sheet URL: {profile.google_sheet_url}")
        return False

    try:
        spreadsheet = client.open_by_key(key)
        sheet_name = profile.google_sheet_name or profile.github_username
        ws = _get_or_create_worksheet(spreadsheet, sheet_name)

        # Truncate long content for sheet readability
        content = (prompt.content or '')[:500]
        summary = (prompt.response_summary or '')[:500]
        created = prompt.created_at.strftime('%Y-%m-%d %H:%M') if prompt.created_at else ''

        row = [
            prompt.id,
            created,
            prompt.project.name if prompt.project else '',
            content,
            summary,
            prompt.status or '',
            prompt.tag or '',
        ]
        ws.append_row(row, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        logger.warning(f"Google Sheets append failed for {profile.github_username}: {e}")
        return False


def update_prompt_in_sheet(profile, prompt):
    """Update an existing prompt row (e.g., when response_summary arrives).

    Finds the row by prompt ID and updates the response_summary and status columns.
    """
    if not profile.google_sheet_enabled or not profile.google_sheet_url:
        return False

    client = get_gspread_client()
    if not client:
        return False

    key = _extract_spreadsheet_key(profile.google_sheet_url)
    if not key:
        return False

    try:
        spreadsheet = client.open_by_key(key)
        sheet_name = profile.google_sheet_name or profile.github_username
        ws = spreadsheet.worksheet(sheet_name)

        # Find the row with this prompt ID (column A)
        cell = ws.find(str(prompt.id), in_column=1)
        if not cell:
            # Row not found — try appending instead
            return append_prompt_to_sheet(profile, prompt)

        row_num = cell.row
        summary = (prompt.response_summary or '')[:500]
        status = prompt.status or ''

        # Update columns E (response summary) and F (status)
        ws.update(f'E{row_num}:F{row_num}', [[summary, status]])
        return True
    except Exception as e:
        logger.warning(f"Google Sheets update failed for {profile.github_username}: {e}")
        return False


def test_sheet_connection(profile):
    """Test connection to the user's Google Sheet.

    Returns: dict with 'ok' (bool), 'message' (str), 'sheet_title' (str)
    """
    result = {'ok': False, 'message': '', 'sheet_title': ''}

    if not profile.google_sheet_url:
        result['message'] = 'Sheet URL이 설정되지 않았습니다.'
        return result

    client = get_gspread_client()
    if not client:
        result['message'] = '서버에 Google 서비스 계정이 설정되지 않았습니다. 관리자에게 문의하세요.'
        return result

    key = _extract_spreadsheet_key(profile.google_sheet_url)
    if not key:
        result['message'] = '유효하지 않은 Google Sheets URL입니다.'
        return result

    try:
        spreadsheet = client.open_by_key(key)
        result['sheet_title'] = spreadsheet.title

        sheet_name = profile.google_sheet_name or profile.github_username
        _get_or_create_worksheet(spreadsheet, sheet_name)

        result['ok'] = True
        result['message'] = f'연결 성공! 스프레드시트: "{spreadsheet.title}", 시트: "{sheet_name}"'
        return result
    except Exception as e:
        err_str = str(e)
        if '403' in err_str or 'PERMISSION_DENIED' in err_str:
            service_email = get_service_email()
            result['message'] = f'권한 없음. 시트를 서비스 계정({service_email})과 편집자로 공유하세요.'
        elif '404' in err_str or 'not found' in err_str.lower():
            result['message'] = '스프레드시트를 찾을 수 없습니다. URL을 확인하세요.'
        else:
            result['message'] = f'연결 실패: {err_str}'
        return result
