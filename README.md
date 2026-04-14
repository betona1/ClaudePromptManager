# CPM — Claude Prompt Manager

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-4.2+-green.svg)](https://djangoproject.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Claude Code에서 발생하는 모든 프롬프트를 **자동 캡처·관리**하는 Django 기반 Web 시스템입니다.

Claude Code hooks를 통해 프롬프트를 실시간으로 DB에 저장하고, 웹 UI로 검색·관리·분석할 수 있습니다.
**멀티유저(Google/GitHub OAuth)**, **관리자 승인제**, **서버 간 Federation**을 지원하여 팀 공유 및 분산 협업이 가능합니다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **자동 프롬프트 캡처** | Claude Code hooks로 모든 프롬프트/응답 자동 저장 (중간 입력 자동 복구 포함) |
| **Google/GitHub OAuth** | Google 간편 로그인 + GitHub OAuth 지원, 관리자 승인 후 이용 가능 |
| **관리자 승인제** | 새 사용자 가입 시 관리자가 승인해야 대시보드 접근 가능 |
| **개인/커뮤니티 분리** | 내 프로젝트 대시보드 + 공유 프로젝트 커뮤니티 페이지 |
| **Google Sheets 연동** | 프롬프트를 사용자별 Google Sheets에 자동 기록 |
| **웹 대시보드** | 프로젝트별 통계, 토큰 사용량, 작업일수 시각화 |
| **댓글 & 팔로우** | 프롬프트 댓글, 유저 팔로우/친구 시스템 |
| **Federation** | 서버 간 P2P 연합 (Mastodon 방식) |
| **Docker 배포** | Docker Compose로 원클릭 배포 |
| **REST API** | DRF 기반 전체 CRUD API + Token 인증 |

---

## 목차

1. [빠른 시작](#빠른-시작)
2. [배포 가이드 (운영 서버)](#배포-가이드-운영-서버)
3. [Google OAuth 설정](#google-oauth-설정)
4. [GitHub OAuth 설정](#github-oauth-설정)
5. [도메인 & HTTPS 설정 (Cloudflare Tunnel)](#도메인--https-설정-cloudflare-tunnel)
6. [사용자 매뉴얼](#사용자-매뉴얼)
7. [관리자 매뉴얼](#관리자-매뉴얼)
8. [원격 Hook 설정 (다른 PC에서 프롬프트 전송)](#원격-hook-설정)
9. [Google Sheets 연동](#google-sheets-연동)
10. [Federation (서버 간 연합)](#federation-서버-간-연합)
11. [CLI & API](#cli--api)
12. [환경변수 전체 목록](#환경변수-전체-목록)

---

## 빠른 시작

### 로컬 설치 (개발/개인용)

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

### Docker 설치 (서버 배포용)

```bash
# 1. 클론
git clone https://github.com/betona1/ClaudePromptManager.git
cd ClaudePromptManager

# 2. 환경변수 설정
cp .env.example .env
# .env 파일 편집 (아래 배포 가이드 참조)

# 3. Docker 실행
docker compose up -d
```

브라우저에서 **http://서버IP:9200** 접속

**초기 관리자 계정**: `admin` / `1234` (첫 실행 시 자동 생성, 반드시 비밀번호 변경)

---

## 배포 가이드 (운영 서버)

### Step 1: 기본 설정

```bash
# .env 파일 편집
cp .env.example .env
nano .env
```

```bash
# ── 필수 설정 ──
CPM_DEBUG=false
CPM_ALLOWED_HOSTS=cpm.yourdomain.com,localhost
delpasswd=your_delete_password

# ── Google OAuth (권장) ──
GOOGLE_OAUTH_CLIENT_ID=your_google_client_id
GOOGLE_OAUTH_SECRET=your_google_secret

# ── GitHub OAuth (선택) ──
GITHUB_OAUTH_CLIENT_ID=your_github_client_id
GITHUB_OAUTH_SECRET=your_github_secret
```

### Step 2: Docker 실행

```bash
docker compose up -d

# 로그 확인
docker compose logs -f
```

### Step 3: 초기 관리자 설정

1. `http://서버IP:9200` 접속
2. Google로 로그인 (또는 `admin`/`1234`로 로그인)
3. **첫 번째 로그인한 사용자**가 자동으로 관리자 + 승인됨
4. 이후 가입하는 사용자는 관리자 승인 필요

> **중요**: `admin`/`1234` 계정은 Google OAuth 설정 전 초기 접근용입니다.
> Google OAuth로 로그인하면 해당 계정이 관리자가 됩니다.
> 이후 `admin` 계정은 Settings에서 삭제 가능합니다.

### Step 4: Docker 업데이트

```bash
git pull
docker compose build --no-cache
docker compose down && docker compose up -d
```

---

## Google OAuth 설정

Google 계정으로 간편 로그인을 구현합니다.

### 1. Google Cloud Console 설정

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 프로젝트 선택 (또는 새 프로젝트 생성)
3. **API 및 서비스** → **사용자 인증 정보**
4. **+ 사용자 인증 정보 만들기** → **OAuth 클라이언트 ID**
5. 애플리케이션 유형: **웹 애플리케이션**
6. 이름: `CPM` (자유)

### 2. 승인된 리디렉션 URI 추가

**중요**: 아래 URI를 정확히 입력해야 합니다.

```
https://cpm.yourdomain.com/accounts/google/login/callback/
```

로컬 테스트도 필요하면:
```
http://localhost:9200/accounts/google/login/callback/
```

### 3. OAuth 동의 화면 설정

처음 OAuth 클라이언트를 만들 때 동의 화면 설정이 필요합니다:

1. **API 및 서비스** → **OAuth 동의 화면**
2. User Type: **외부** 선택
3. 앱 이름: `CPM`
4. 사용자 지원 이메일: 본인 이메일
5. 개발자 연락처: 본인 이메일
6. 범위(Scopes): `email`, `profile` 추가
7. 테스트 사용자: 테스트할 Google 계정 이메일 추가

> **참고**: "테스트" 상태에서는 테스트 사용자로 등록된 이메일만 로그인 가능합니다.
> 누구나 로그인할 수 있게 하려면 "게시" 상태로 변경하세요.

### 4. .env 설정

```bash
GOOGLE_OAUTH_CLIENT_ID=123456789-xxxx.apps.googleusercontent.com
GOOGLE_OAUTH_SECRET=GOCSPX-xxxxxxxxxx
```

### 5. 서버 재시작

```bash
# Docker
docker compose down && docker compose up -d

# 로컬
python3 manage.py cpm_web
```

로그인 페이지에 **"Google로 로그인"** 버튼이 자동으로 나타납니다.

---

## GitHub OAuth 설정

### 1. GitHub OAuth App 생성

1. [GitHub Developer Settings](https://github.com/settings/developers) → **New OAuth App**
2. **Homepage URL**: `https://cpm.yourdomain.com`
3. **Authorization callback URL**: `https://cpm.yourdomain.com/accounts/github/login/callback/`
4. **Register application** 클릭

### 2. .env 설정

```bash
GITHUB_OAUTH_CLIENT_ID=Iv1_xxxxxxxxxxxx
GITHUB_OAUTH_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. 서버 재시작

로그인 페이지에 **"GitHub로 로그인"** 버튼이 자동으로 나타납니다.

> **참고**: Google OAuth와 GitHub OAuth를 동시에 사용할 수 있습니다.

---

## 도메인 & HTTPS 설정 (Cloudflare Tunnel)

외부에서 HTTPS로 접속하려면 Cloudflare Tunnel을 사용할 수 있습니다.

### 1. Cloudflare Tunnel 설치 및 생성

```bash
# cloudflared 설치 (Ubuntu/Debian)
curl -L https://pkg.cloudflare.com/cloudflared-stable-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# 로그인
cloudflared login

# 터널 생성
cloudflared tunnel create cpm-tunnel
```

### 2. config.yml 설정

```yaml
# /etc/cloudflared/config.yml
tunnel: YOUR_TUNNEL_ID
credentials-file: /home/user/.cloudflared/YOUR_TUNNEL_ID.json

ingress:
  - hostname: cpm.yourdomain.com
    service: http://localhost:9200
  - service: http_status:404
```

### 3. DNS 라우팅

```bash
cloudflared tunnel route dns cpm-tunnel cpm.yourdomain.com
```

### 4. 서비스 시작

```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

### 5. CPM .env 설정

```bash
CPM_ALLOWED_HOSTS=cpm.yourdomain.com,localhost
```

> `CPM_ALLOWED_HOSTS`에 도메인을 넣으면 CSRF_TRUSTED_ORIGINS가 자동으로 설정됩니다.

---

## 사용자 매뉴얼

### 회원가입 & 로그인

1. **cpm.yourdomain.com** 접속
2. **"Google로 로그인"** 클릭 → Google 계정 선택
3. 최초 로그인 시 **"승인 대기중"** 페이지가 표시됩니다
4. 관리자가 승인하면 대시보드에 접근할 수 있습니다

> Username/Password 로그인도 가능합니다 (회원가입 페이지에서 계정 생성).

### 대시보드 (`/`)

로그인 후 메인 페이지입니다. **내 프로젝트만** 표시됩니다.

| 영역 | 설명 |
|------|------|
| **통계 카드** | 총 프롬프트, 오늘/어제/주간/월간 카운트, 토큰 사용량 |
| **프로젝트 카드** | 프로젝트별 프롬프트 수, 작업일수, 스크린샷 미리보기 |
| **최근 프롬프트** | 최신 15개 프롬프트 타임라인 |
| **서비스 포트** | 등록된 서비스/포트 현황 테이블 |

#### 프로젝트 카드 기능

- **즐겨찾기** — 카드 hover → 하트 아이콘 클릭 (상단 고정)
- **Claude Code 뱃지** — hook/import로 수집된 프로젝트 표시
- **Todo 뱃지** — 진행률 표시, 클릭 → Todo 모달
- **가시성 뱃지** — 잠금(private) / 사람(friends) 아이콘
- **스크린샷** — 카메라 아이콘 클릭 → 미리보기

### 커뮤니티 (`/community/`)

다른 사용자들이 공개한 프로젝트를 볼 수 있습니다.

| 탭 | 설명 |
|----|------|
| **Community** | 전체 공개(public) 프로젝트 |
| **Friends** | 상호 팔로우 유저의 프로젝트 |

### 프로젝트 상세 (`/projects/<id>/`)

프로젝트의 전체 프롬프트 목록, 필터, 통계를 확인합니다.

- **필터**: 상태(wip/success/fail), 태그, 소스, tmux 세션별
- **검색**: 프롬프트 내용/응답/노트 검색
- **인라인 편집**: 프롬프트 더블클릭 → 직접 수정 (Enter 저장, Esc 취소)
- **MD 파일 보기**: 프로젝트 디렉토리의 마크다운 파일 열기

### 프로필 (`/@username/`)

사용자의 공개 프로필 페이지입니다.

- 공개 프로젝트 목록
- 팔로워/팔로잉 수
- Follow/Unfollow 버튼

### 설정 (`/settings/`)

| 항목 | 설명 |
|------|------|
| **API Token** | Hook 인증용 토큰 확인/재생성/복사 |
| **Bio** | 프로필 소개문 수정 |
| **Google Sheets** | 시트 URL, 탭 이름, 활성화 설정 |
| **Project Visibility** | 새 프로젝트 기본 공개범위 안내 |
| **Hook Setup** | 원격 머신 환경변수 안내 |

### 프로젝트 공개범위

프로젝트 상세 페이지에서 변경할 수 있습니다.

| 설정 | 누가 볼 수 있나 |
|------|----------------|
| `public` | 모든 사용자 (기본값) |
| `private` | 소유자만 |
| `friends` | 소유자 + 상호 팔로우 친구 |

### 통계 (`/stats/`)

일별/주별/월별 프롬프트 통계를 차트로 확인합니다.

- 활동 타임라인 (시간/일 단위)
- 상태/태그/프로젝트/소스 분포 차트
- 기간 네비게이션 (이전/다음)

---

## 관리자 매뉴얼

### 관리자 계정

- **첫 번째로 로그인한 사용자**가 자동으로 관리자가 됩니다
- Docker 초기 설치 시 `admin`/`1234` 기본 계정이 생성됩니다
- 관리자는 `is_admin=True`, `is_approved=True`

### 사용자 승인

새 사용자가 Google/GitHub로 로그인하면 **"승인 대기중"** 상태가 됩니다.

1. 관리자 계정으로 로그인
2. **Settings** (`/settings/`) 페이지 이동
3. **"Admin: User Management"** 섹션에서:
   - **승인 대기중** 사용자 목록 확인
   - **Approve** — 사용자 승인 (대시보드 접근 허용)
   - **Reject** — 사용자 삭제 (계정 완전 삭제)
4. **전체 사용자 테이블**에서 모든 사용자의 상태/역할 확인

### 프로젝트 삭제

대시보드에서 프로젝트 카드 hover → × 클릭 → 삭제 비밀번호 입력

```bash
# .env에서 삭제 비밀번호 설정
delpasswd=your_password
```

### 서버 관리 명령어

```bash
# Docker 컨테이너 접속
docker compose exec cpm bash

# 관리자 쉘
docker compose exec cpm python manage.py shell

# 사용자 목록 확인
docker compose exec cpm python manage.py shell -c "
from core.models import UserProfile
for p in UserProfile.objects.all():
    print(f'{p.user.username}: admin={p.is_admin}, approved={p.is_approved}, email={p.user.email}')
"

# 수동으로 사용자 승인
docker compose exec cpm python manage.py shell -c "
from core.models import UserProfile
UserProfile.objects.filter(user__username='target_user').update(is_approved=True)
"

# 로그 확인
docker compose logs -f
```

---

## 원격 Hook 설정

다른 PC에서 Claude Code를 사용할 때 프롬프트를 CPM 서버로 자동 전송합니다.

### 방법 1: 웹에서 다운로드 (권장)

1. CPM 웹 → **Setup** (`/setup/`) 페이지
2. **Windows** 또는 **Linux** 패키지 다운로드
3. 안내에 따라 설치

### 방법 2: 수동 설정

```bash
# 1. 환경변수 설정 (~/.bashrc 또는 ~/.zshrc)
export CPM_SERVER=https://cpm.yourdomain.com
export CPM_API_TOKEN=your_token_here    # /settings/ 에서 확인

# 2. Claude Code hooks 설정 (~/.claude/settings.json)
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "python3 ~/cpm-hooks/on_prompt_remote.py"}]
    }],
    "Stop": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "python3 ~/cpm-hooks/on_stop_remote.py"}]
    }]
  }
}

# 3. 기존 기록 가져오기
python3 ~/cpm-hooks/import_history.py
```

### API Token 확인

1. CPM 웹 로그인
2. **Settings** (`/settings/`) 페이지
3. **API Token** 섹션에서 복사

---

## Google Sheets 연동

프롬프트를 자동으로 Google Sheets에 기록합니다.

### 서버 관리자 설정

1. [Google Cloud Console](https://console.cloud.google.com/) → **API 및 서비스** → **라이브러리**
2. "Google Sheets API" 검색 → **사용 설정**
3. **사용자 인증 정보** → **서비스 계정 만들기**
4. 서비스 계정 → **키** → **키 추가** → JSON 다운로드
5. `.env` 설정:

```bash
GOOGLE_SHEETS_CREDENTIALS=/path/to/service-account.json
# 또는 Docker용 인라인:
# GOOGLE_SHEETS_CREDENTIALS_JSON='{"type":"service_account",...}'
```

### 사용자 설정

1. Google Sheets에서 새 스프레드시트 생성
2. 서비스 계정 이메일을 **편집자**로 공유 (Settings 페이지에서 이메일 확인)
3. **Settings** → **Google Sheets** 섹션:
   - Sheet URL 붙여넣기
   - 시트 탭 이름 입력 (선택)
   - 자동 기록 활성화 체크
   - Save → Test Connection

### 기록 포맷

| ID | 날짜 | 프로젝트 | 프롬프트 | 응답 요약 | 상태 | 태그 |
|----|------|---------|---------|----------|------|------|
| 1234 | 2026-04-14 15:30 | cpm | Fix bug... | Fixed by... | success | bug |

### 과거 데이터 일괄 동기화

```bash
python3 manage.py cpm_sheets_sync              # 전체
python3 manage.py cpm_sheets_sync --days 30    # 최근 30일
python3 manage.py cpm_sheets_sync --user name  # 특정 유저
python3 manage.py cpm_sheets_sync --dry-run    # 미리보기
```

---

## Federation (서버 간 연합)

각자 CPM 서버를 운영하면서 서로의 프롬프트를 구독·공유할 수 있습니다.

### 설정

```bash
# 서버 아이덴티티 생성
python3 manage.py cpm_federation init --name "my-cpm" --url "https://cpm.example.com"

# 상태 확인
python3 manage.py cpm_federation status

# 동기화 (cron 5분 권장)
python3 manage.py cpm_federation sync
```

### 서버 페어링

1. `/federation/` → **Servers** 탭 → 원격 서버 URL 입력 → **Add Server**
2. 상대 서버 관리자가 **Accept** → 양쪽 `active`

### 보안

- HMAC-SHA256 서명
- 타임스탬프 +-5분 허용
- 일일 요청 제한: 서버당 1,000건
- 연속 5회 실패 → 자동 suspended

---

## CLI & API

### CLI 명령어

```bash
python3 manage.py cpm_setup              # 초기 설정
python3 manage.py cpm_import --all       # 기존 기록 가져오기
python3 manage.py cpm_web                # 웹 서버 (port 9200)
python3 manage.py cpm_discover           # 포트 스캔
python3 manage.py cpm_tokens             # 토큰 사용량 집계
python3 manage.py cpm_sheets_sync        # Google Sheets 일괄 동기화
python3 manage.py cpm_federation init    # Federation 초기화
python3 manage.py cpm_federation sync    # Federation 동기화

cpm2 board                               # 대시보드
cpm2 log <project>                       # 프로젝트 로그
cpm2 web                                 # 웹 서버
```

### REST API

| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/api/projects/` | GET, POST | 프로젝트 CRUD |
| `/api/prompts/` | GET, POST | 프롬프트 CRUD |
| `/api/prompts/{id}/comments/` | GET, POST | 댓글 |
| `/api/services/` | GET, POST | 서비스 포트 CRUD |
| `/api/hook/prompt/` | POST | 원격 hook: 프롬프트 수신 |
| `/api/hook/stop/` | POST | 원격 hook: 응답 수신 |
| `/api/auth/profile/` | GET | 현재 유저 프로필 |
| `/api/stats/` | GET | 전체 통계 |

### API 인증

```bash
# Bearer Token
curl -H "Authorization: Bearer YOUR_TOKEN" https://cpm.yourdomain.com/api/prompts/

# Session (브라우저 로그인 상태)
# Django 세션 쿠키 자동 사용
```

---

## 환경변수 전체 목록

```bash
cp .env.example .env
```

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CPM_SECRET_KEY` | 자동생성 | Django SECRET_KEY |
| `CPM_DEBUG` | `true` | 디버그 모드 (`false` 권장) |
| `CPM_ALLOWED_HOSTS` | `*` | 허용 호스트 (쉼표 구분, CSRF 자동 설정) |
| `CPM_DATA_DIR` | OS별 기본값 | 데이터 디렉토리 (Docker: `/data`) |
| `CPM_SERVER` | `http://localhost:9200` | 원격 hook 서버 주소 |
| `CPM_API_TOKEN` | (없음) | API 인증 토큰 |
| `GOOGLE_OAUTH_CLIENT_ID` | (없음) | Google OAuth 클라이언트 ID |
| `GOOGLE_OAUTH_SECRET` | (없음) | Google OAuth 시크릿 |
| `GITHUB_OAUTH_CLIENT_ID` | (없음) | GitHub OAuth 클라이언트 ID |
| `GITHUB_OAUTH_SECRET` | (없음) | GitHub OAuth 시크릿 |
| `GOOGLE_SHEETS_CREDENTIALS` | (없음) | Google 서비스 계정 JSON 파일 경로 |
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | (없음) | Google 서비스 계정 JSON 인라인 |
| `delpasswd` | (없음) | 프로젝트 삭제 비밀번호 |
| `GITHUB_TOKEN` | (없음) | GitHub 레포 동기화용 토큰 |
| `GITHUB_USERNAME` | (없음) | GitHub 유저명 |
| `GUNICORN_WORKERS` | `2` | Gunicorn 워커 수 |
| `GUNICORN_THREADS` | `2` | Gunicorn 스레드 수 |

---

## 프로젝트 구조

```
ClaudePromptManager/
├── manage.py
├── setup.py
├── Dockerfile / docker-compose.yml
├── docker-entrypoint.sh
├── cpm/                          # Django 프로젝트 설정
│   ├── settings.py
│   └── urls.py
├── core/                         # Django 앱
│   ├── models.py                 # ORM 모델
│   ├── views_web.py              # 웹 페이지 뷰
│   ├── views_api.py              # REST API
│   ├── views_federation.py       # Federation API
│   ├── signals.py                # OAuth + federation + Sheets signal
│   ├── google_sheets.py          # Google Sheets 래퍼
│   └── management/commands/      # CLI 명령어
├── hooks/                        # Claude Code hook 스크립트
│   ├── on_prompt.py              # 프롬프트 캡처
│   ├── on_stop.py                # 응답 요약
│   └── shared.py                 # DB/Redis 유틸
├── templates/                    # Django 템플릿
├── static/                       # CSS/JS
└── docs/                         # 추가 문서
    ├── INSTALL.md
    ├── ARCHITECTURE.md
    ├── PROMPT_CAPTURE.md
    └── REMOTE_HOOKS_SETUP.md
```

## 기술 스택

| 분류 | 기술 |
|------|------|
| Backend | Python 3.8+ / Django 4.2+ / DRF |
| Auth | django-allauth (Google + GitHub OAuth) |
| Database | SQLite (WAL mode) |
| Frontend | Vanilla JS / Self-contained CSS |
| Federation | HMAC-SHA256 / urllib |
| 배포 | Docker / gunicorn + whitenoise |

## 라이선스

MIT License
