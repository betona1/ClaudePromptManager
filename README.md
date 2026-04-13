# CPM — Claude Prompt Manager

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-4.2+-green.svg)](https://djangoproject.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Claude Code에서 발생하는 모든 프롬프트를 **자동 캡처·관리**하는 Django 기반 CLI + Web 시스템입니다.

Claude Code hooks를 통해 프롬프트를 실시간으로 DB에 저장하고, 웹 UI로 검색·관리·분석할 수 있습니다.
**멀티유저(GitHub OAuth)** 와 **서버 간 Federation**을 지원하여, 팀 공유 및 분산 협업이 가능합니다.

## 주요 기능

- **자동 프롬프트 캡처** — Claude Code hooks로 모든 프롬프트/응답 자동 저장
- **웹 대시보드** — 프로젝트별 통계, 토큰 사용량, 작업일수 시각화
- **멀티유저** — GitHub OAuth 로그인, 프로젝트 소유권, 공개범위 설정 (public/private/friends)
- **댓글 시스템** — 프롬프트에 대한 댓글 (AJAX 기반)
- **팔로우/친구** — 일방향 팔로우, 상호 팔로우 = 친구 (friends-only 프로젝트 공유)
- **Federation** — 서버 간 P2P 연합 (Mastodon 방식), 프롬프트 실시간 동기화
- **프로젝트 Todo/Goals** — 프로젝트별 목표 설정 + 체크리스트 + 배포 마일스톤
- **GitHub 연동** — 다중 GitHub 계정 레포 동기화, 프로젝트 자동 생성
- **즐겨찾기 & 필터** — 활성 프로젝트 하트 마크, ALL/즐겨찾기 토글 필터
- **원격 실행** — 브라우저에서 Claude Code 명령 원격 실행 (SSE 스트리밍)
- **서비스 포트 관리** — 서버별 서비스/포트 현황 테이블 + 자동 탐색
- **다중 서버 지원** — 원격 서버 hook으로 여러 머신의 프롬프트 통합 수집 (Windows 포함)
- **Docker 배포** — Docker Compose로 원클릭 배포
- **REST API** — DRF 기반 전체 CRUD API
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

### Docker 배포

```bash
# docker-compose.yml이 있는 디렉토리에서
docker compose up -d cpm
```

---

## 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 편집하여 설정 변경
```

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CPM_SECRET_KEY` | 자동생성 | Django SECRET_KEY |
| `CPM_DEBUG` | `true` | 디버그 모드 |
| `CPM_ALLOWED_HOSTS` | `*` | 허용 호스트 (쉼표 구분) |
| `CPM_DATA_DIR` | OS별 기본값 | 데이터 디렉토리 (Docker: `/data`) |
| `CPM_SERVER` | `http://localhost:9200` | 원격 hook 서버 주소 |
| `CPM_API_TOKEN` | (없음) | API 인증 토큰 (멀티유저 모드) |
| `GITHUB_OAUTH_CLIENT_ID` | (없음) | GitHub OAuth 앱 Client ID |
| `GITHUB_OAUTH_SECRET` | (없음) | GitHub OAuth 앱 Secret |
| `delpasswd` | (없음) | 프로젝트 삭제 비밀번호 |

---

## 멀티유저 시스템

### GitHub OAuth 설정

1. [GitHub Developer Settings](https://github.com/settings/developers) → **New OAuth App**
2. **Homepage URL**: `http://your-server:9200`
3. **Authorization callback URL**: `http://your-server:9200/accounts/github/login/callback/`
4. 발급된 Client ID와 Secret을 환경변수에 설정:
   ```bash
   GITHUB_OAUTH_CLIENT_ID=your_client_id
   GITHUB_OAUTH_SECRET=your_secret
   ```
5. Django Admin(`/admin/`)에서 **Sites** → `example.com`을 실제 도메인으로 변경
6. **Social Applications** → GitHub 앱 추가 (Client ID, Secret, Sites 연결)

### 사용자 기능

| 기능 | 설명 |
|------|------|
| **로그인** | 네비게이션 "Login with GitHub" 클릭 |
| **프로필** | `/@username/` — 공개 프로젝트, 팔로워/팔로잉 수 |
| **설정** | `/settings/` — API Token 확인/재생성, bio 수정 |
| **팔로우** | 프로필 페이지에서 Follow/Unfollow |
| **댓글** | 프롬프트 상세 페이지에서 AJAX 댓글 |

### 대시보드 탭

| 탭 | 대상 | 설명 |
|---|---|---|
| **My Projects** | `owner=me` | 내 프로젝트 (로그인 기본) |
| **Community** | `visibility=public` | 전체 공개 프로젝트 |
| **Friends** | 상호팔로우 유저의 프로젝트 | 친구 프로젝트 |

비로그인 시 Community만 표시됩니다.

### 프로젝트 공개범위

| 설정 | 누가 볼 수 있나 |
|------|----------------|
| `public` | 모든 사용자 (기본값) |
| `private` | 소유자만 |
| `friends` | 소유자 + 상호 팔로우 친구 |

### API Token 인증 (Hook용)

멀티유저 환경에서 hook이 프롬프트를 특정 유저의 프로젝트로 저장하려면:

```bash
# 1. /settings/ 페이지에서 API Token 확인
# 2. 환경변수에 설정
export CPM_API_TOKEN=your_token_here
```

Hook이 `Authorization: Bearer <token>` 헤더로 유저를 식별합니다.
토큰 없이 요청하면 anonymous로 처리됩니다 (하위호환).

---

## Federation (서버 간 연합)

각자 CPM 서버를 운영하면서 서로의 프롬프트를 구독·공유할 수 있습니다.

### 초기 설정

```bash
# 서버 아이덴티티 생성
python3 manage.py cpm_federation init \
  --name "my-cpm" \
  --url "https://cpm.example.com"

# 상태 확인
python3 manage.py cpm_federation status
```

### 서버 페어링

1. 웹 UI `/federation/` → **Servers** 탭
2. 원격 서버 URL 입력 → **Add Server**
3. 상대 서버 관리자가 **Accept** 클릭
4. 양쪽 모두 `active` 상태가 되면 연결 완료

### 프로젝트 구독

1. `/federation/` → **Explore** 탭
2. 페어링된 서버 선택
3. 원격 공개 프로젝트 목록에서 **Subscribe** 클릭

### 동기화 방식

| 방식 | 설명 |
|------|------|
| **Push (실시간)** | public 프로젝트에 프롬프트 생성 시 자동 전송 |
| **Pull (폴백)** | `python3 manage.py cpm_federation sync` (cron 5분 권장) |

### Federation Feed

`/federation/` → **Feed** 탭에서 로컬 + 원격 프롬프트를 시간순으로 통합 조회합니다.
- 초록 뱃지: 로컬 서버 프롬프트
- 파란 뱃지: 원격 서버 프롬프트

### 보안

- HMAC-SHA256 서명으로 서버 간 인증
- 타임스탬프 +-5분 허용
- 일일 요청 제한: 서버당 1,000건
- 연속 5회 실패 시 자동 suspended
- 관리자가 서버 block 가능

### Well-Known 엔드포인트

```bash
curl https://cpm.example.com/.well-known/cpm-federation
```
```json
{
  "protocol_version": "1.0",
  "server_name": "my-cpm",
  "server_url": "https://cpm.example.com",
  "user_count": 3,
  "public_project_count": 42
}
```

---

## 웹 UI 가이드

### 대시보드 (`/`)

전체 통계 카드(총 프롬프트, 프로젝트 수, 작업일수, 토큰 사용량)와 프로젝트 카드, 서비스 포트 테이블, 최근 프롬프트를 한눈에 확인합니다.

#### 프로젝트 카드 기능

- **즐겨찾기** — 카드 hover 시 하트 아이콘, 클릭으로 토글
- **Claude Code 뱃지** — hook/import로 수집된 프로젝트 표시
- **Todo 뱃지** — 진행률 표시, 클릭으로 Todo 모달
- **스크린샷 미리보기** — 카메라 아이콘으로 확인
- **소유자 아바타** — Community/Friends 탭에서 표시

### 프로젝트 Todo/Goals

1. 대시보드 카드의 보라색 뱃지 클릭 → Todo 모달
2. **Task 목표** — 일반 목표 추가
3. **Deploy 마일스톤** — 배포 마일스톤 추가
4. **체크 완료** — 체크박스 클릭 시 완료 처리 + 날짜 기록

### 원격 실행 (`/remote/`)

브라우저에서 Claude Code 명령을 원격 실행합니다. SSE 스트리밍으로 실시간 출력.

### 인라인 편집

더블클릭으로 필드 수정. `Enter` 저장, `Esc` 취소.

---

## CLI 명령어

```bash
# Django Management
python3 manage.py cpm_setup             # 초기 설정
python3 manage.py cpm_import --all      # 기존 기록 가져오기
python3 manage.py cpm_web               # 웹 서버 (port 9200)
python3 manage.py cpm_discover          # 포트 스캔
python3 manage.py cpm_tokens            # 토큰 사용량 집계
python3 manage.py cpm_federation init   # Federation 초기화
python3 manage.py cpm_federation status # Federation 상태
python3 manage.py cpm_federation sync   # Federation 동기화

# v2 CLI
cpm2 board                    # 대시보드
cpm2 log <project>            # 프로젝트 로그
cpm2 web                      # 웹 서버
```

---

## REST API

### 주요 엔드포인트

| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/api/projects/` | GET, POST | 프로젝트 CRUD |
| `/api/prompts/` | GET, POST | 프롬프트 CRUD |
| `/api/prompts/{id}/comments/` | GET, POST | 댓글 조회/작성 |
| `/api/services/` | GET, POST | 서비스 포트 CRUD |
| `/api/hook/prompt/` | POST | 원격 hook: 프롬프트 수신 |
| `/api/hook/stop/` | POST | 원격 hook: 응답 수신 |
| `/api/auth/profile/` | GET | 현재 유저 프로필 |
| `/api/auth/token/regenerate/` | POST | API Token 재생성 |
| `/api/stats/` | GET | 전체 통계 |

### Federation API

| 경로 | 설명 |
|------|------|
| `/.well-known/cpm-federation` | 서버 메타데이터 |
| `/api/federation/projects/` | 공개 프로젝트 목록 |
| `/api/federation/projects/{id}/prompts/` | 프로젝트 프롬프트 (cursor 기반) |
| `/api/federation/pair/request/` | 페어링 요청 |
| `/api/federation/pair/accept/` | 페어링 승인 |
| `/api/federation/servers/add/` | 서버 추가 (관리자) |
| `/api/federation/subscribe/` | 프로젝트 구독 |
| `/api/federation/push/prompts/` | 프롬프트 Push (HMAC 인증) |
| `/api/federation/status/` | Federation 상태 |
| `/api/federation/explore/{server_id}/` | 원격 서버 탐색 |

### API 인증

```bash
# Bearer Token (멀티유저)
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:9200/api/prompts/

# Session (브라우저 로그인)
# Django 세션 쿠키 자동 사용
```

---

## 프로젝트 구조

```
ClaudePromptManager/
├── manage.py
├── setup.py
├── Dockerfile / docker-compose.yml
├── cpm/                          # Django 프로젝트 설정
│   ├── settings.py
│   └── urls.py
├── core/                         # Django 앱
│   ├── models.py                 # ORM 모델 (19개 테이블)
│   ├── views_api.py              # REST API
│   ├── views_web.py              # 웹 페이지 뷰
│   ├── views_federation.py       # Federation API
│   ├── authentication.py         # API Token 인증
│   ├── permissions.py            # 접근 제어
│   ├── signals.py                # allauth + federation push
│   ├── federation_auth.py        # HMAC 서명/검증
│   └── management/commands/      # CLI 명령어
├── hooks/                        # Claude Code hook 스크립트
│   ├── on_prompt.py              # 프롬프트 캡처
│   ├── on_stop.py                # 응답 요약
│   ├── remote_hook.py            # 원격 서버용
│   └── shared.py                 # DB/Redis 유틸
├── templates/                    # Django 템플릿
├── static/css/ + js/             # 프론트엔드
└── docs/                         # 문서
    ├── ARCHITECTURE.md           # 기술 아키텍처
    └── REMOTE_HOOKS_SETUP.md     # 원격 Hook 설정
```

## 기술 스택

| 분류 | 기술 |
|------|------|
| Backend | Python 3.8+ / Django 4.2+ / DRF |
| Auth | django-allauth (GitHub OAuth) |
| Database | SQLite (WAL mode) |
| Frontend | Vanilla JS / Self-contained CSS |
| Federation | HMAC-SHA256 / urllib (외부 의존성 없음) |
| 배포 | Docker / pip install / gunicorn + whitenoise |

## 라이선스

MIT License
