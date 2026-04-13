# CPM 설치 가이드 (초보자용)

이 문서는 CPM (Claude Prompt Manager)을 처음부터 설치·운영하는 방법을 단계별로 설명합니다.

---

## 목차

1. [사전 준비](#1-사전-준비)
2. [CPM 설치](#2-cpm-설치)
3. [첫 실행](#3-첫-실행)
4. [Claude Code 연동 확인](#4-claude-code-연동-확인)
5. [GitHub 로그인 설정 (선택)](#5-github-로그인-설정-선택)
6. [Google Sheets 연동 (선택)](#6-google-sheets-연동-선택)
7. [원격 서버 설정 (선택)](#7-원격-서버-설정-선택)
8. [Docker 배포 (선택)](#8-docker-배포-선택)
9. [문제 해결](#9-문제-해결)

---

## 1. 사전 준비

### Python 3.8+ 설치

**Linux (Ubuntu/Debian)**:
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
```

**macOS** (Homebrew):
```bash
brew install python3 git
```

**Windows**:
1. [python.org](https://www.python.org/downloads/)에서 Python 3.8+ 다운로드
2. 설치 시 "Add Python to PATH" 체크
3. [Git for Windows](https://git-scm.com/download/win) 설치

### Python 버전 확인
```bash
python3 --version
# Python 3.8.0 이상이면 OK
```

### Claude Code 설치

CPM은 [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview)의 hook 기능을 사용하여 프롬프트를 자동 캡처합니다.

```bash
# Claude Code가 이미 설치되어 있는지 확인
claude --version
```

아직 없다면 [Claude Code 공식 문서](https://docs.anthropic.com/en/docs/claude-code/overview)를 참고하여 설치하세요.

---

## 2. CPM 설치

### Step 1: 소스 코드 다운로드

```bash
git clone https://github.com/betona1/ClaudePromptManager.git
cd ClaudePromptManager
```

### Step 2: 의존성 설치

```bash
# Linux/macOS
pip install -e .

# 권한 문제가 발생하면:
pip install -e . --break-system-packages

# 또는 가상환경 사용 (권장):
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e .
```

### Step 3: 초기 설정

```bash
python3 manage.py cpm_setup
```

이 명령은 다음을 자동 수행합니다:
- SQLite 데이터베이스 생성 (`~/.local/share/cpm/cpm.db`)
- 테이블 마이그레이션
- Claude Code hooks 자동 설치 (`~/.claude/hooks/`)

출력 예시:
```
[CPM Setup] Running migrations...
[CPM Setup] Installing Claude Code hooks...
[CPM Setup] Hook installed: ~/.claude/hooks/UserPromptSubmit.py
[CPM Setup] Hook installed: ~/.claude/hooks/Stop.py
[CPM Setup] Setup complete! Run 'python3 manage.py cpm_web' to start.
```

### Step 4: 환경변수 설정 (선택)

```bash
cp .env.example .env
```

`.env` 파일을 편집하여 필요한 설정을 추가합니다:
```bash
# 프로젝트 삭제 비밀번호 (설정하면 웹에서 프로젝트 삭제 가능)
delpasswd=your_password_here
```

---

## 3. 첫 실행

### 웹 서버 시작

```bash
python3 manage.py cpm_web
```

출력:
```
Starting CPM web server on http://0.0.0.0:9200
```

### 브라우저에서 접속

브라우저를 열고 **http://localhost:9200** 에 접속합니다.

처음에는 데이터가 비어 있습니다. Claude Code를 사용하면 프롬프트가 자동으로 표시됩니다.

### 기존 기록 가져오기 (선택)

이전에 Claude Code를 사용한 적이 있다면 과거 기록을 가져올 수 있습니다:

```bash
python3 manage.py cpm_import --all
```

---

## 4. Claude Code 연동 확인

### Hook 설치 확인

```bash
ls ~/.claude/hooks/
# UserPromptSubmit.json  Stop.json  (또는 유사한 파일)
```

### 테스트

1. 아무 프로젝트 디렉토리에서 Claude Code를 실행합니다:
   ```bash
   cd ~/my-project
   claude
   ```

2. 프롬프트를 입력합니다 (예: "Hello, test prompt")

3. CPM 웹 (http://localhost:9200)에서 해당 프롬프트가 표시되는지 확인합니다.

### 프롬프트가 안 보이는 경우

1. **Hook 파일 확인**: `~/.claude/hooks/` 디렉토리에 파일이 있는지 확인
2. **cpm_setup 재실행**: `python3 manage.py cpm_setup`
3. **수동 확인**: DB에 데이터가 있는지 확인
   ```bash
   python3 manage.py shell -c "from core.models import Prompt; print(Prompt.objects.count())"
   ```

---

## 5. GitHub 로그인 설정 (선택)

멀티유저 환경에서 각 사용자를 구분하려면 GitHub OAuth 로그인을 설정합니다.

> **참고**: GitHub OAuth를 설정하지 않으면 "Login with GitHub" 버튼이 자동으로 숨겨지며, 싱글유저 모드로 동작합니다.

### Step 1: GitHub OAuth App 생성

1. **GitHub** 로그인 → [Settings → Developer settings → OAuth Apps](https://github.com/settings/developers)
2. **"New OAuth App"** 클릭
3. 아래 정보 입력:

| 항목 | 값 | 예시 |
|------|---|------|
| Application name | CPM | Claude Prompt Manager |
| Homepage URL | 서버 주소 | `http://localhost:9200` |
| Authorization callback URL | 서버 주소 + 콜백 경로 | `http://localhost:9200/accounts/github/login/callback/` |

> **중요**: Authorization callback URL 끝에 `/`를 반드시 포함하세요.

4. **"Register application"** 클릭
5. **Client ID**를 복사합니다
6. **"Generate a new client secret"** 클릭 → **Client Secret**을 복사합니다

### Step 2: 환경변수 설정

`.env` 파일에 추가:
```bash
GITHUB_OAUTH_CLIENT_ID=Iv1.xxxxxxxxxxxxxxxxxx
GITHUB_OAUTH_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Step 3: 서버 재시작

```bash
# Ctrl+C로 기존 서버 중지 후
python3 manage.py cpm_web
```

서버가 시작되면 GitHub SocialApp이 자동으로 생성됩니다.

### Step 4: 로그인 테스트

1. http://localhost:9200 접속
2. 우측 상단 **"Login with GitHub"** 버튼 클릭
3. GitHub 인증 페이지에서 승인
4. CPM으로 리다이렉트 → 프로필 자동 생성

### 첫 번째 로그인 유저 = 관리자

처음 로그인한 유저는 자동으로 **관리자**가 되며, 기존의 소유자 없는 프로젝트를 모두 할당받습니다.

### 외부 서버에서 사용 시

`localhost` 대신 실제 도메인이나 IP를 사용하세요:
```
Homepage URL: http://your-server.com:9200
Callback URL: http://your-server.com:9200/accounts/github/login/callback/
```

`.env`에 추가:
```bash
CPM_ALLOWED_HOSTS=your-server.com,localhost
```

---

## 6. Google Sheets 연동 (선택)

프롬프트를 Google Sheets에 자동 기록합니다. 각 유저가 자신의 시트에 독립적으로 기록 가능.

### Step 1: Google Cloud 서비스 계정 생성 (관리자 1회)

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 프로젝트가 없으면 **새 프로젝트 만들기** → 프로젝트 이름 입력 → **만들기**
3. 좌측 메뉴 → **API 및 서비스** → **라이브러리**
4. "Google Sheets API" 검색 → **사용 설정** 클릭
5. 좌측 메뉴 → **API 및 서비스** → **사용자 인증 정보**
6. **"+ 사용자 인증 정보 만들기"** → **"서비스 계정"** 선택
7. 서비스 계정 이름 입력 (예: `cpm-sheets`) → **만들기 및 계속** → **완료**
8. 생성된 서비스 계정 클릭 → **키** 탭
9. **"키 추가"** → **"새 키 만들기"** → **JSON** → **만들기**
10. JSON 파일이 다운로드됩니다 → **안전한 위치에 저장**

### Step 2: 환경변수 설정

```bash
# .env 파일에 추가
GOOGLE_SHEETS_CREDENTIALS=/path/to/your-service-account-key.json
```

예시:
```bash
GOOGLE_SHEETS_CREDENTIALS=/home/user/cpm-sheets-key.json
```

### Step 3: CPM 서버 재시작

```bash
python3 manage.py cpm_web
```

### Step 4: 유저별 시트 설정

1. **Google Sheets** 에서 새 스프레드시트 생성
2. 스프레드시트를 서비스 계정 이메일과 **편집자**로 공유:
   - 시트 우측 상단 **"공유"** 클릭
   - 서비스 계정 이메일 입력 (예: `cpm-sheets@my-project-123.iam.gserviceaccount.com`)
   - **역할: "편집자"** 선택 → **보내기**

   > 서비스 계정 이메일은 CPM `/settings/` 페이지에 표시됩니다.

3. CPM 웹 → **Settings** (`/settings/`) 페이지:
   - **Sheet URL**: 스프레드시트 URL 붙여넣기
   - **시트 탭 이름**: 원하는 탭 이름 (비워두면 GitHub 유저명 사용)
   - **자동 기록 활성화**: 체크
   - **Save** 클릭

4. **Test Connection** 버튼으로 연결 확인

### Step 5: 동작 확인

1. Claude Code에서 프롬프트 입력
2. CPM 웹에서 프롬프트 확인
3. Google Sheets에서 새 행이 추가되었는지 확인

### 과거 데이터 일괄 동기화

```bash
# 전체 동기화
python3 manage.py cpm_sheets_sync

# 최근 7일만
python3 manage.py cpm_sheets_sync --days 7

# 미리보기 (실제 기록 안 함)
python3 manage.py cpm_sheets_sync --dry-run
```

---

## 7. 원격 서버 설정 (선택)

여러 머신의 프롬프트를 하나의 CPM 서버로 통합 수집합니다.

### 중앙 서버 (프롬프트를 수집하는 서버)

```bash
# 일반적인 CPM 설치 후 웹 서버 시작
python3 manage.py cpm_web
```

### 원격 머신 (프롬프트를 보내는 머신)

```bash
# 환경변수 설정
export CPM_SERVER=http://central-server:9200
export CPM_API_TOKEN=your_token_here   # 멀티유저 모드 시 필요

# remote_hook 설치
python3 manage.py cpm_setup --remote
```

자세한 내용: [docs/REMOTE_HOOKS_SETUP.md](REMOTE_HOOKS_SETUP.md)

---

## 8. Docker 배포 (선택)

### docker-compose.yml

```yaml
version: '3.8'
services:
  cpm:
    build: .
    ports:
      - "9200:9200"
    volumes:
      - cpm_data:/data
    environment:
      - CPM_DATA_DIR=/data
      - CPM_ALLOWED_HOSTS=*
      - GITHUB_OAUTH_CLIENT_ID=${GITHUB_OAUTH_CLIENT_ID}
      - GITHUB_OAUTH_SECRET=${GITHUB_OAUTH_SECRET}
      - GOOGLE_SHEETS_CREDENTIALS_JSON=${GOOGLE_SHEETS_CREDENTIALS_JSON}
    restart: unless-stopped

volumes:
  cpm_data:
```

### 실행

```bash
docker compose up -d cpm
```

---

## 9. 문제 해결

### "Login with GitHub" 버튼이 없다

GitHub OAuth 환경변수가 설정되지 않았습니다. `.env` 파일에 `GITHUB_OAUTH_CLIENT_ID`와 `GITHUB_OAUTH_SECRET`을 추가하고 서버를 재시작하세요.

### "Login with GitHub" 클릭 시 404 에러

1. `.env`의 `GITHUB_OAUTH_CLIENT_ID`와 `GITHUB_OAUTH_SECRET` 값이 올바른지 확인
2. 서버 재시작: `python3 manage.py cpm_web`
3. 마이그레이션 확인: `python3 manage.py migrate`

### 프롬프트가 캡처되지 않는다

1. Hook 설치 확인: `ls ~/.claude/hooks/`
2. 재설치: `python3 manage.py cpm_setup`
3. DB 위치 확인: `ls ~/.local/share/cpm/cpm.db`
4. Claude Code 재시작 후 다시 시도

### Claude 작업 중 입력한 프롬프트가 누락된다

Claude Code가 tool을 실행하는 도중에 입력한 메시지는 즉시 기록되지 않습니다.
**하지만 Claude가 응답을 완료하면 `on_stop.py` hook이 자동으로 복구합니다.**

- 복구된 프롬프트는 `source='hook-queue'`로 표시됩니다.
- 상세 기술 문서: [docs/PROMPT_CAPTURE.md](PROMPT_CAPTURE.md)

### Google Sheets에 기록이 안 된다

1. 서비스 계정 JSON 파일 경로 확인
2. 서비스 계정 이메일을 시트에 **편집자**로 공유했는지 확인
3. `/settings/` → **Test Connection** 버튼으로 진단
4. 과거 데이터 복구: `python3 manage.py cpm_sheets_sync`

### pip install 에러

```bash
# 가상환경 사용
python3 -m venv venv
source venv/bin/activate
pip install -e .

# 또는 --break-system-packages 옵션
pip install -e . --break-system-packages
```

### 포트 9200이 이미 사용 중

```bash
# 다른 포트로 실행
python3 manage.py cpm_web --port 8080
```

### DB를 초기화하고 싶다

```bash
# DB 파일 삭제
rm ~/.local/share/cpm/cpm.db

# 재설정
python3 manage.py cpm_setup
```

---

## 업데이트

```bash
cd ClaudePromptManager
git pull
pip install -e .
python3 manage.py migrate
python3 manage.py cpm_web
```

---

## 추가 문서

- [README.md](../README.md) — 프로젝트 개요 및 전체 기능
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — 시스템 아키텍처
- [docs/PROMPT_CAPTURE.md](PROMPT_CAPTURE.md) — 프롬프트 캡처 기술 문서
- [docs/REMOTE_HOOKS_SETUP.md](REMOTE_HOOKS_SETUP.md) — 원격 Hook 설정
