# CLAUDE.md — CPM (Claude Prompt Manager) v2

## 프로젝트 개요
Claude Code 프롬프트를 자동 캡처·관리하는 Django 기반 CLI + Web 시스템.
Claude Code hooks로 프롬프트를 자동 DB 저장, 웹 UI로 검색·관리.

## 기술 스택
- Python 3.8+ / Django 4.2+ / DRF / SQLite (WAL 모드)
- Claude Code hooks (UserPromptSubmit, Stop)
- Tailwind CSS (CDN) / Vanilla JS
- Redis (선택적, Phase 2 실시간용)

## 디렉토리 구조
```
cpm/
├── manage.py                  # Django 진입점
├── setup.py                   # pip install
├── cpm.py                     # v1 CLI (하위호환)
├── cpm_cli.py                 # v2 CLI wrapper
├── cpm/                       # Django 프로젝트 설정
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py / asgi.py
├── core/                      # Django 앱
│   ├── models.py              # ORM 모델
│   ├── serializers.py         # DRF 직렬화
│   ├── views_api.py           # REST API
│   ├── views_web.py           # 웹 페이지 뷰
│   ├── urls_api.py / urls_web.py
│   ├── admin.py
│   └── management/commands/   # cpm_setup, cpm_import, cpm_export, cpm_web
├── hooks/                     # Claude Code hook 스크립트
│   ├── on_prompt.py           # UserPromptSubmit → DB INSERT
│   ├── on_stop.py             # Stop → 응답 요약 UPDATE
│   └── shared.py              # DB/Redis 유틸
├── templates/                 # Django 템플릿 (Tailwind)
├── static/                    # CSS/JS
└── tests/
```

## DB 위치
- Linux: `~/.local/share/cpm/cpm.db`
- Windows: `%APPDATA%\cpm\cpm.db`

## 주요 테이블
- `projects` — 프로젝트 (name, path, description)
- `terminals` — 터미널 세션 (name, project_id, pid, status, cwd)
- `prompts` — 프롬프트 (content, status, tag, response_summary, session_id, source)
- `templates` — 프롬프트 템플릿
- `sessions` — Claude Code 세션 추적
- `tool_calls` — 도구 호출 기록 (Phase 4)

## 환경 변수 (.env)
```
delpasswd=YOUR_PASSWORD    # 프로젝트 삭제 비밀번호 (필수)
```
- `.env` 파일에 `delpasswd=` 뒤에 비밀번호 입력 후 서버 재시작하면 적용
- 대시보드에서 프로젝트 카드 hover → × 클릭 → 비밀번호 입력 → 삭제
- 비밀번호 미설정 시 삭제 기능 비활성화

## 포트 배정
- Django Web: **9200**
- WebSocket: **9201** (Phase 2)
- Redis: 6379

## 개발 명령어
```bash
# 설치
pip install -e . --break-system-packages

# 초기 설정 (hooks 설치 + DB)
python manage.py cpm_setup

# 과거 기록 가져오기
python manage.py cpm_import --all

# 웹 서버 시작
python manage.py cpm_web          # http://localhost:9200
cpm2 web                          # 동일

# CLI
cpm2 board                        # 대시보드
cpm2 log <project>                # 프로젝트 로그
cpm2 search <keyword>             # 검색

# v1 CLI (하위호환)
cpm board
cpm stats

# 마이그레이션
python manage.py makemigrations core
python manage.py migrate
```

## 코딩 규칙
- Django ORM 사용 (raw SQL 최소화)
- hooks는 독립 실행 (Django 없이도 동작, shared.py의 직접 SQLite 접근)
- 상태값: wip / success / fail
- 소스: hook / import / manual
- 태그: bug / feature / refactor / docs / test / deploy / config / other
- JSON 내보내기 시 ensure_ascii=False (한글 보존)
- USE_TZ=False (localtime 사용, v1 호환)

## 주의사항
- hooks는 Claude Code를 절대 블로킹하면 안됨 (모든 예외 무시)
- hooks는 stdout에 반드시 `{}` 출력 (정상 통과 신호)
- 기존 cpm.py는 보존 (v1 하위호환)
