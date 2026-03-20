# CPM — Claude Prompt Manager

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-4.2+-green.svg)](https://djangoproject.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Claude Code에서 발생하는 모든 프롬프트를 **자동 캡처·관리**하는 Django 기반 CLI + Web 시스템입니다.

Claude Code hooks를 통해 프롬프트를 실시간으로 DB에 저장하고, 웹 UI로 검색·관리·분석할 수 있습니다.

## 주요 기능

- **자동 프롬프트 캡처** — Claude Code hooks로 모든 프롬프트/응답 자동 저장
- **웹 대시보드** — 프로젝트별 통계, 토큰 사용량, 작업일수 시각화
- **서비스 포트 관리** — 서버별 서비스/포트 현황 테이블 + 자동 탐색
- **인라인 편집** — 웹에서 더블클릭으로 모든 정보를 즉시 수정
- **REST API** — DRF 기반 전체 CRUD API
- **다중 서버 지원** — 원격 서버 hook으로 여러 머신의 프롬프트 통합 수집
- **CLI 도구** — 터미널에서 대시보드, 검색, 통계 확인

---

## 빠른 시작

### 요구사항

- Python 3.8+
- pip
- [Claude Code](https://claude.ai/claude-code) (hooks 자동 캡처용)

### 설치

```bash
# 1. 클론
git clone https://github.com/betona1/ClaudePromptManager.git
cd ClaudePromptManager

# 2. 의존성 설치
pip install -e .

# 3. 초기 설정 (DB 생성 + Claude Code hooks 자동 설치)
python3 manage.py cpm_setup

# 4. 웹 서버 시작
python3 manage.py cpm_web
```

브라우저에서 **http://localhost:9200** 접속

> 설치 후 Claude Code를 사용하면 모든 프롬프트가 자동으로 캡처됩니다.

---

## 환경변수 설정 (선택)

```bash
cp .env.example .env
# .env 파일을 편집하여 설정 변경
```

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CPM_SECRET_KEY` | 자동생성 | Django SECRET_KEY (비워두면 파일로 자동생성) |
| `CPM_DEBUG` | `true` | 디버그 모드 |
| `CPM_ALLOWED_HOSTS` | `*` | 허용 호스트 (쉼표 구분) |
| `CPM_WEB_PORT` | `9200` | 웹 서버 포트 |
| `CPM_SERVER` | `http://localhost:9200` | 원격 hook 서버 주소 |
| `CPM_REDIS_URL` | `redis://localhost:6379/0` | Redis URL (선택) |

---

## 웹 UI 가이드

### 대시보드 (`/`)

전체 통계 카드(총 프롬프트, 프로젝트 수, 작업일수, 토큰 사용량)와 프로젝트 카드, 서비스 포트 테이블, 최근 프롬프트를 한눈에 확인합니다.

### 인라인 편집

웹에서 **더블클릭**하면 해당 필드를 바로 수정할 수 있습니다:

| 위치 | 편집 가능 필드 |
|------|---------------|
| 대시보드 서비스 테이블 | Remarks |
| 프로젝트 상세 페이지 | 이름, 설명, URL, 배포 URL, 서버 정보 |

- `Enter` — 저장 (단일 행)
- `Ctrl+Enter` — 저장 (멀티라인)
- `Esc` — 취소

### 서비스 포트 관리

대시보드 하단의 **Service Ports** 테이블에서 전체 서비스 현황을 확인합니다.

**Auto-Discover** 버튼으로 네트워크 포트를 자동 스캔하여 서비스를 등록할 수 있습니다.

```bash
# CLI로 포트 스캔
python3 manage.py cpm_discover                       # localhost 스캔
python3 manage.py cpm_discover --host 192.168.1.100  # 특정 호스트
python3 manage.py cpm_discover --range 8000 9300     # 포트 범위 지정
```

---

## CLI 명령어

### v2 CLI (Django 기반)

```bash
cpm2 board                    # 대시보드
cpm2 log <project>            # 프로젝트 로그
cpm2 search <query>           # 검색
cpm2 web                      # 웹 서버 시작
```

### Django Management 명령어

```bash
python3 manage.py cpm_setup        # 초기 설정 (hooks + DB)
python3 manage.py cpm_import --all # 기존 기록 가져오기
python3 manage.py cpm_export       # JSON 내보내기
python3 manage.py cpm_web          # 웹 서버 (port 9200)
python3 manage.py cpm_discover     # 포트 스캔
python3 manage.py cpm_tokens       # 토큰 사용량 집계
python3 manage.py cpm_screenshot   # 프로젝트 스크린샷 캡처
```

### v1 CLI (하위호환)

```bash
cpm board                     # 대시보드
cpm stats                     # 전체 통계
cpm prompt add <project> "내용" --tag feature
cpm prompt status <ID> success --note "완료 메모"
cpm log <project>             # 프로젝트별 이력
cpm search <keyword>          # 검색
cpm export                    # JSON 내보내기
```

---

## REST API

### 엔드포인트

| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/api/projects/` | GET, POST | 프로젝트 CRUD |
| `/api/projects/{id}/` | GET, PUT, PATCH, DELETE | 프로젝트 상세 |
| `/api/prompts/` | GET, POST | 프롬프트 CRUD (필터: project, status, tag, source) |
| `/api/prompts/{id}/` | GET, PUT, PATCH, DELETE | 프롬프트 상세 |
| `/api/services/` | GET, POST | 서비스 포트 CRUD |
| `/api/services/{id}/` | GET, PUT, PATCH, DELETE | 서비스 포트 상세 |
| `/api/sessions/` | GET | Claude Code 세션 목록 |
| `/api/templates/` | GET, POST | 프롬프트 템플릿 CRUD |
| `/api/terminals/` | GET, POST | 터미널 CRUD |
| `/api/stats/` | GET | 전체 통계 |
| `/api/discover/` | POST | 서비스 자동 탐색 |
| `/api/hook/prompt/` | POST | 원격 hook: 프롬프트 수신 |
| `/api/hook/stop/` | POST | 원격 hook: 응답 수신 |

### API 사용 예시

```bash
# 프로젝트 목록
curl http://localhost:9200/api/projects/

# 프롬프트 검색
curl "http://localhost:9200/api/prompts/?search=CORS&status=fail"

# 서비스 포트 수정
curl -X PATCH http://localhost:9200/api/services/1/ \
  -H "Content-Type: application/json" \
  -d '{"remarks": "메인 개발 서버"}'

# 포트 자동 탐색
curl -X POST http://localhost:9200/api/discover/ \
  -H "Content-Type: application/json" \
  -d '{"host": "127.0.0.1", "port_range": [3000, 9300]}'
```

---

## 원격 서버 설정

다른 머신에서도 프롬프트를 수집하려면:

1. 원격 머신에 `hooks/remote_hook.py` 복사
2. 환경변수 설정:
   ```bash
   export CPM_SERVER=http://<cpm-server-ip>:9200
   ```
3. `~/.claude/settings.json`에 hook 등록:

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "python3 /path/to/remote_hook.py prompt"}]
    }],
    "Stop": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "python3 /path/to/remote_hook.py stop"}]
    }]
  }
}
```

---

## 프로젝트 구조

```
ClaudePromptManager/
├── manage.py                  # Django 진입점
├── setup.py                   # pip install -e .
├── cpm.py                     # v1 CLI (하위호환)
├── cpm_cli.py                 # v2 CLI wrapper
├── cpm/                       # Django 프로젝트 설정
│   ├── settings.py            # 환경변수 기반 설정
│   ├── urls.py
│   └── wsgi.py / asgi.py
├── core/                      # Django 앱
│   ├── models.py              # ORM 모델
│   │   ├── Project            # 프로젝트 (이름, 경로, URL, 토큰)
│   │   ├── Prompt             # 프롬프트 (내용, 상태, 태그, 응답)
│   │   ├── ServicePort        # 서비스 포트 (IP, 포트, 상태)
│   │   ├── Session            # Claude Code 세션
│   │   ├── Terminal           # 터미널
│   │   ├── Template           # 프롬프트 템플릿
│   │   └── ToolCall           # 도구 호출 기록
│   ├── serializers.py         # DRF 직렬화
│   ├── views_api.py           # REST API + 서비스 탐색
│   ├── views_web.py           # 웹 페이지 뷰
│   ├── urls_api.py / urls_web.py
│   ├── admin.py               # Django Admin (/admin/)
│   └── management/commands/   # CLI 명령어
├── hooks/                     # Claude Code hook 스크립트
│   ├── on_prompt.py           # UserPromptSubmit → DB 저장
│   ├── on_stop.py             # Stop → 응답 요약 업데이트
│   ├── remote_hook.py         # 원격 서버용 hook
│   └── shared.py              # DB/Redis 유틸
├── templates/                 # Django 템플릿 (자체 CSS, CDN 없음)
├── static/
│   ├── css/style.css          # 전체 스타일시트
│   └── js/cpm.js              # 인라인 편집 + AJAX + 탐색
└── .env.example               # 환경변수 템플릿
```

## 데이터베이스

SQLite (WAL 모드)를 사용하며, 데이터 파일은 아래 위치에 저장됩니다:

| OS | 경로 |
|----|------|
| Linux / macOS | `~/.local/share/cpm/cpm.db` |
| Windows | `%APPDATA%\cpm\cpm.db` |

### 주요 테이블

| 테이블 | 설명 |
|--------|------|
| `projects` | 프로젝트 (이름, 경로, URL, 토큰 사용량) |
| `prompts` | 프롬프트 (내용, 상태, 태그, 응답 요약, 세션) |
| `sessions` | Claude Code 세션 추적 |
| `terminals` | 터미널 세션 |
| `templates` | 프롬프트 템플릿 |
| `service_ports` | 서비스 포트 (서버, IP, 포트, 상태, 타입) |
| `tool_calls` | 도구 호출 기록 |

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| Backend | Python 3.8+ / Django 4.2+ / Django REST Framework |
| Database | SQLite (WAL mode) |
| Frontend | Vanilla JS / Self-contained CSS (외부 CDN 없음) |
| Hooks | Claude Code UserPromptSubmit / Stop hooks |
| Port Scan | Python socket + ThreadPoolExecutor |
| 배포 | pip install -e . / systemd (선택) |

## 보안

- `SECRET_KEY`는 환경변수 또는 자동생성 파일로 관리 (코드에 하드코딩 없음)
- `.env` 파일은 `.gitignore`에 포함되어 커밋되지 않음
- 원격 hook 서버 주소는 환경변수로 설정
- CSRF 토큰 기반 API 보호
- 로컬 네트워크 전용 설계 (프로덕션 배포 시 `ALLOWED_HOSTS` 설정 필요)

---

## 프롬프트 태그

| 태그 | 용도 |
|------|------|
| `bug` | 버그 수정 |
| `feature` | 기능 추가 |
| `refactor` | 리팩토링 |
| `docs` | 문서 작업 |
| `test` | 테스트 |
| `deploy` | 배포 |
| `config` | 설정 |
| `other` | 기타 |

## 라이선스

MIT License
