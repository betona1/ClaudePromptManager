# CPM 기술 아키텍처 문서

## 목차

1. [시스템 개요](#시스템-개요)
2. [아키텍처 다이어그램](#아키텍처-다이어그램)
3. [데이터베이스 스키마](#데이터베이스-스키마)
4. [인증 시스템](#인증-시스템)
5. [Federation 프로토콜](#federation-프로토콜)
6. [Hook 시스템](#hook-시스템)
7. [API 레퍼런스](#api-레퍼런스)
8. [배포](#배포)

---

## 시스템 개요

CPM은 Claude Code의 프롬프트를 자동 수집하는 Django 기반 시스템입니다.

### 핵심 구성요소

```
┌──────────────────────────────────────────────────────┐
│                   CPM Server (Django)                 │
│                                                      │
│  ┌─────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │ Web UI  │  │ REST API │  │ Federation API    │   │
│  │ (SSR)   │  │ (DRF)    │  │ (HMAC-signed)     │   │
│  └────┬────┘  └────┬─────┘  └────────┬──────────┘   │
│       │            │                 │               │
│  ┌────┴────────────┴─────────────────┴──────────┐   │
│  │              Django ORM (models.py)           │   │
│  └──────────────────────┬────────────────────────┘   │
│                         │                            │
│  ┌──────────────────────┴────────────────────────┐   │
│  │           SQLite (WAL mode, /data/cpm.db)     │   │
│  └───────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
         ▲                    ▲                ▲
         │                    │                │
    ┌────┴────┐         ┌────┴────┐     ┌─────┴──────┐
    │ Browser │         │ Claude  │     │ Remote CPM │
    │ (User)  │         │ Code    │     │ Server     │
    └─────────┘         │ Hooks   │     └────────────┘
                        └─────────┘
```

### 기술 스택

| 계층 | 기술 | 비고 |
|------|------|------|
| Web Framework | Django 4.2+ | SSR 템플릿 + DRF API |
| Auth | django-allauth | GitHub OAuth Provider |
| Database | SQLite (WAL) | 단일 파일, 동시 읽기 지원 |
| Frontend | Vanilla JS + CSS | 외부 CDN 의존성 없음 |
| Federation | stdlib만 사용 | urllib, hmac, hashlib |
| 배포 | Docker + gunicorn + whitenoise | 정적 파일 자체 서빙 |

---

## 데이터베이스 스키마

### 핵심 테이블 (19개)

```
┌─────────────────┐       ┌─────────────────┐
│    projects      │───────│    prompts       │
│─────────────────│ 1:N   │─────────────────│
│ id               │       │ id               │
│ name (unique)    │       │ project_id (FK)  │
│ path             │       │ content          │
│ owner_id (FK)    │──┐    │ response_summary │
│ visibility       │  │    │ status           │
│ github_url       │  │    │ tag              │
│ favorited        │  │    │ source           │
│ total_*_tokens   │  │    │ session_id       │
│ created/updated  │  │    │ tmux_session     │
└─────────────────┘  │    │ created_at       │
                     │    └─────────────────┘
                     │              │
┌─────────────────┐  │    ┌────────┴────────┐
│  auth_user       │──┘    │   comments       │
│─────────────────│        │─────────────────│
│ id               │        │ prompt_id (FK)  │
│ username         │        │ author_id (FK)  │
│ ...              │        │ content          │
└────────┬────────┘        └─────────────────┘
         │
┌────────┴────────┐       ┌─────────────────┐
│  user_profiles   │       │    follows        │
│─────────────────│       │─────────────────│
│ user_id (1:1)   │       │ follower_id (FK) │
│ github_username  │       │ following_id(FK) │
│ avatar_url       │       │ created_at       │
│ bio              │       └─────────────────┘
│ api_token (idx)  │
│ is_admin         │
└─────────────────┘
```

### Federation 테이블

```
┌──────────────────┐      ┌──────────────────┐
│ server_identity   │      │ federated_servers │
│──────────────────│      │──────────────────│
│ server_name       │      │ url (unique)      │
│ server_url        │      │ name              │
│ shared_secret     │      │ status            │
└──────────────────┘      │ our_token         │
                          │ their_token       │
                          │ shared_secret     │
                          │ error_count       │
                          │ requests_today    │
                          │ last_sync_at      │
                          └────────┬─────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
   ┌──────────┴──────┐  ┌────────┴────────┐  ┌───────┴───────┐
   │ federated_subs   │  │ federated_users  │  │ fed_comments   │
   │─────────────────│  │─────────────────│  │───────────────│
   │ server_id (FK)  │  │ username         │  │ prompt_id     │
   │ remote_proj_id  │  │ server_id (FK)  │  │ fed_prompt_id │
   │ remote_proj_name│  │ federated_id    │  │ author_name   │
   │ last_prompt_id  │  │ avatar_url       │  │ content       │
   │ is_active       │  └─────────────────┘  └───────────────┘
   └────────┬────────┘
            │
   ┌────────┴────────┐
   │ federated_prompts│
   │─────────────────│
   │ subscription (FK)│
   │ remote_prompt_id │
   │ remote_user (FK) │
   │ content          │
   │ response_summary │
   │ remote_created_at│
   └─────────────────┘
```

### 접근 제어 (Visibility)

```python
# core/permissions.py
def visible_projects_queryset(user):
    if not user.is_authenticated:
        return Project.objects.filter(visibility='public')

    return Project.objects.filter(
        Q(visibility='public') |                    # 공개
        Q(owner=user) |                             # 본인
        Q(visibility='friends', owner__in=friends)  # 상호 팔로우
    )
```

---

## 인증 시스템

### 인증 방식 (2가지)

| 방식 | 대상 | 구현 |
|------|------|------|
| Session | 브라우저 사용자 | Django SessionAuth + allauth |
| Bearer Token | Hook / API 클라이언트 | `core/authentication.py` |

### Session 인증 (GitHub OAuth)

```
User → "Login with GitHub" → GitHub OAuth → callback
     → allauth user_signed_up signal → UserProfile 자동 생성
     → 첫 유저 = admin, 기존 프로젝트 소유권 자동 할당
```

### API Token 인증

```
Hook → POST /api/hook/prompt/
     → Header: Authorization: Bearer <token>
     → APITokenAuthentication: UserProfile.api_token lookup (indexed)
     → request.user = token 소유자
     → 프로젝트에 owner 자동 할당
```

```python
# core/authentication.py
class APITokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token = extract_bearer_token(request)
        if not token:
            return None  # anonymous fallback (하위호환)
        profile = UserProfile.objects.get(api_token=token)
        return (profile.user, token)
```

**하위호환**: 토큰 없는 요청도 anonymous로 정상 처리됩니다.

---

## Federation 프로토콜

### 개요

CPM Federation은 각 서버가 독립적으로 운영되면서 서로의 공개 프로젝트를 구독·동기화하는 P2P 프로토콜입니다.

### 메타데이터 엔드포인트

```
GET /.well-known/cpm-federation

{
  "protocol_version": "1.0",
  "server_name": "my-cpm",
  "server_url": "https://cpm.example.com",
  "user_count": 3,
  "public_project_count": 42
}
```

### 페어링 프로토콜

```
Server A (요청자)                    Server B (승인자)
     │                                    │
     │  1. GET /.well-known/cpm-federation│
     │───────────────────────────────────→│
     │←───────────────────────────────────│ metadata
     │                                    │
     │  2. POST /api/federation/pair/request/
     │    { server_url, server_name, token_A }
     │───────────────────────────────────→│
     │←───────────────────────────────────│ { status: pending, token_B }
     │                                    │
     │         (B 관리자가 웹에서 Accept)   │
     │                                    │
     │  3. POST /api/federation/pair/confirm/
     │←───────────────────────────────────│ { status: active, token_B }
     │                                    │
     │  shared_secret = SHA256(sort([token_A, token_B]))
     │  양쪽 모두 active 상태              │
```

### HMAC 서명

```python
# 서명 생성
body_hash = SHA256(request_body)
message = f"{METHOD}\n{PATH}\n{TIMESTAMP}\n{body_hash}"
signature = HMAC-SHA256(shared_secret, message)

# 요청 헤더
X-CPM-Signature: <hex_signature>
X-CPM-Timestamp: <unix_timestamp>
```

**보안 규칙**:
- 타임스탬프 +-5분 허용
- 일일 요청 제한: 서버당 1,000건
- 연속 5회 실패 → 자동 suspended
- 관리자가 서버 block 가능

### 동기화 방식

#### Push (실시간, 주 방식)

```
Prompt 저장 → post_save signal
  → project.visibility == 'public'?
    → daemon thread 생성
      → 각 active FederatedServer에 HMAC 서명 후 POST
        → /api/federation/push/prompts/
```

```python
# core/signals.py
@receiver(post_save, sender='core.Prompt')
def push_prompt_to_federation(sender, instance, created, **kwargs):
    if not created or instance.project.visibility != 'public':
        return
    threading.Thread(target=_do_push_prompt, args=(instance.id,), daemon=True).start()
```

#### Pull (폴백, cron 기반)

```bash
# crontab -e
*/5 * * * * cd /app && python manage.py cpm_federation sync
```

```
cpm_federation sync
  → 각 active subscription에 대해
    → GET /api/federation/projects/{id}/prompts/?after={cursor}
    → FederatedPrompt 생성 (중복 방지: unique_together)
    → cursor 업데이트
```

### Federation 데이터 흐름

```
[Server A]                           [Server B]
  Prompt 생성                              │
     │                                     │
     ├── Push ──────────────────────────→ FederatedPrompt 저장
     │   (HMAC signed POST)                │
     │                                     ├── Feed에 표시
     │                                     │
     │   ←── Pull (5분마다) ───────────── cursor 기반 polling
     │                                     │
     │   ←── Comment Push ────────────── FederatedComment 저장
```

---

## Hook 시스템

### 아키텍처

```
Claude Code
  │
  ├── UserPromptSubmit event
  │     └── on_prompt.py
  │           ├── 로컬 DB 저장 (shared.py → SQLite)
  │           └── 원격 서버 전송 (shared.py → remote_post)
  │                 └── POST /api/hook/prompt/
  │                       Authorization: Bearer <token>
  │
  └── Stop event
        └── on_stop.py
              ├── 로컬 DB 업데이트
              └── 원격 서버 전송
                    └── POST /api/hook/stop/
```

### Hook 모드

| 모드 | 파일 | 설명 |
|------|------|------|
| 로컬+원격 | `on_prompt.py` + `on_stop.py` | SQLite 직접 저장 + 서버 전송 |
| 원격 전용 | `remote_hook.py` | 서버에만 전송 (Windows 호환) |

### Hook 헬스 체크

대시보드에서 hook 상태를 자동 감지합니다:

1. `~/.claude/settings.json` 확인 (로컬)
2. 없으면 DB에서 최근 hook 활동 확인 (Docker/원격)
3. hook source 프롬프트가 존재하면 OK

### tmux 세션 감지

Hook이 실행 시 `tmux display-message -p '#S'`로 현재 tmux 세션명을 캡처합니다.
프로젝트 상세 페이지에서 tmux 세션별로 프롬프트를 필터링할 수 있습니다.

---

## API 레퍼런스

### 인증

| 방식 | 헤더 | 대상 |
|------|------|------|
| Bearer Token | `Authorization: Bearer <token>` | Hook, API 클라이언트 |
| Session | Cookie (자동) | 브라우저 |
| 없음 | — | Anonymous (public 데이터만) |

### Core API

```
GET    /api/projects/                    # 프로젝트 목록
POST   /api/projects/                    # 프로젝트 생성
GET    /api/projects/{id}/               # 프로젝트 상세
PATCH  /api/projects/{id}/               # 프로젝트 수정
DELETE /api/projects/{id}/               # 프로젝트 삭제

GET    /api/prompts/                     # 프롬프트 목록 (?search=&status=&tag=)
GET    /api/prompts/{id}/                # 프롬프트 상세
GET    /api/prompts/{id}/comments/       # 댓글 목록
POST   /api/prompts/{id}/comments/       # 댓글 작성 (로그인 필요)

POST   /api/hook/prompt/                 # Hook: 프롬프트 수신
POST   /api/hook/stop/                   # Hook: 응답 수신
POST   /api/hook/import/                 # Hook: 기록 가져오기

GET    /api/auth/profile/                # 현재 유저 프로필
POST   /api/auth/token/regenerate/       # API Token 재생성
GET    /api/stats/                       # 전체 통계
```

### Federation API

```
GET    /.well-known/cpm-federation       # 서버 메타데이터

GET    /api/federation/projects/         # 공개 프로젝트 목록
GET    /api/federation/projects/{id}/prompts/?after=0&limit=50
                                         # 프로젝트 프롬프트 (cursor)

POST   /api/federation/pair/request/     # 페어링 요청
POST   /api/federation/pair/accept/      # 페어링 승인 (관리자)
POST   /api/federation/pair/confirm/     # 페어링 확인 (자동)

POST   /api/federation/servers/add/      # 서버 추가 (관리자)
POST   /api/federation/servers/action/   # 서버 block/unblock/delete

POST   /api/federation/subscribe/        # 프로젝트 구독
POST   /api/federation/unsubscribe/      # 구독 해제

POST   /api/federation/push/prompts/     # 프롬프트 Push (HMAC)
POST   /api/federation/push/comment/     # 댓글 Push (HMAC)

GET    /api/federation/status/           # Federation 상태
GET    /api/federation/explore/{id}/     # 원격 서버 탐색
```

---

## 배포

### Docker (권장)

```yaml
# docker-compose.yml
services:
  cpm:
    build: .
    ports:
      - "9200:9200"
    volumes:
      - /path/to/data:/data
    environment:
      - CPM_DATA_DIR=/data
      - CPM_DEBUG=false
      - GITHUB_OAUTH_CLIENT_ID=xxx
      - GITHUB_OAUTH_SECRET=xxx
```

```bash
docker compose up -d cpm
docker exec cpm python manage.py cpm_federation init --name "my-cpm" --url "https://..."
```

### 직접 설치

```bash
pip install -e .
python3 manage.py migrate
python3 manage.py cpm_setup
python3 manage.py cpm_web  # 또는 gunicorn cpm.wsgi:application -b 0.0.0.0:9200
```

### 포트 배정

| 서비스 | 포트 |
|--------|------|
| Django Web | 9200 |
| WebSocket (Phase 2) | 9201 |
| Redis (선택) | 6379 |

### 데이터 위치

| 환경 | 경로 |
|------|------|
| Docker | `/data/cpm.db` (볼륨 마운트) |
| Linux | `~/.local/share/cpm/cpm.db` |
| Windows | `%APPDATA%\cpm\cpm.db` |

---

## 파일 구조 상세

```
core/
├── models.py              # 19개 ORM 모델
├── views_api.py            # REST API (DRF ViewSet + function views)
├── views_web.py            # 웹 페이지 (SSR, 13개 뷰)
├── views_federation.py     # Federation API (15개 엔드포인트)
├── urls_api.py             # API URL 라우팅
├── urls_web.py             # 웹 URL 라우팅
├── urls_federation.py      # Federation URL 라우팅
├── authentication.py       # APITokenAuthentication
├── permissions.py          # can_view_project, visible_projects_queryset
├── signals.py              # allauth signup + federation push
├── federation_auth.py      # HMAC-SHA256 서명/검증
├── serializers.py          # DRF 직렬화
├── admin.py                # Django Admin (13개 모델 등록)
├── apps.py                 # CoreConfig (signals import)
└── management/commands/
    ├── cpm_setup.py        # 초기 설정
    ├── cpm_import.py       # 기존 기록 가져오기
    ├── cpm_export.py       # JSON 내보내기
    ├── cpm_web.py          # 웹 서버 시작
    ├── cpm_discover.py     # 포트 스캔
    ├── cpm_tokens.py       # 토큰 사용량 집계
    ├── cpm_screenshot.py   # 스크린샷 캡처
    ├── cpm_telegram.py     # Telegram 봇
    └── cpm_federation.py   # Federation 관리 (init/status/sync)
```
