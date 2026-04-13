# CPM 프롬프트 캡처 & 누락 방지 기술 문서

## 개요

CPM은 Claude Code에서 발생하는 **모든 프롬프트**를 자동으로 캡처합니다.
이 문서는 캡처 메커니즘, 발생 가능한 누락 상황, 그리고 각 상황별 자동/수동 복구 방법을 기술합니다.

---

## 1. 프롬프트 캡처 아키텍처

### 1.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                     Claude Code 실행 환경                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [사용자 프롬프트 입력]                                           │
│       │                                                         │
│       ▼                                                         │
│  ┌──────────────────────┐    ┌─────────────────────────────┐   │
│  │ UserPromptSubmit Hook│    │ transcript JSONL 파일        │   │
│  │ (on_prompt.py)       │    │ (Claude Code 자동 기록)       │   │
│  │                      │    │                             │   │
│  │ • stdin에서 JSON 읽기 │    │ • 모든 사용자 메시지 기록     │   │
│  │ • SQLite INSERT      │    │ • 중간 입력 = queue-operation│   │
│  │ • print('{}') 출력   │    │ • tool 결과도 기록           │   │
│  └──────────┬───────────┘    └──────────────┬──────────────┘   │
│             │                               │                   │
│             ▼                               │                   │
│  [Claude 응답 생성 + Tool 실행]               │                   │
│       │                                     │                   │
│       ▼                                     ▼                   │
│  ┌──────────────────────────────────────────────────┐          │
│  │ Stop Hook (on_stop.py)                           │          │
│  │                                                  │          │
│  │ 1. 마지막 wip 프롬프트 → 응답요약 UPDATE          │          │
│  │ 2. transcript 파싱 → queue-operation 메시지 발견   │          │
│  │ 3. DB에 없는 메시지 → INSERT (source='hook-queue') │          │
│  │ 4. Google Sheets 동기화 (daemon thread)           │          │
│  └──────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 두 가지 캡처 경로

| 경로 | Hook | 트리거 시점 | 저장 방식 | source 값 |
|------|------|------------|----------|----------|
| **경로 1: 직접 캡처** | `on_prompt.py` | 사용자가 프롬프트 입력 즉시 | SQLite 직접 INSERT | `hook` |
| **경로 2: 복구 캡처** | `on_stop.py` | Claude 응답 완료 시 | transcript 파싱 → INSERT | `hook-queue` |

### 1.3 원격 서버 경로 (추가)

원격 머신에서 CPM 서버로 전송하는 경우:

| 경로 | 방식 | 트리거 | 저장 방식 | Google Sheets |
|------|------|--------|----------|--------------|
| **경로 3: 원격 API** | `POST /api/hook/prompt/` | on_prompt.py의 remote_post() | Django ORM save() | signal → daemon thread |
| **경로 4: 원격 Stop** | `POST /api/hook/stop/` | on_stop.py의 remote_post() | Django ORM update() | signal → daemon thread |

---

## 2. 누락이 발생할 수 있는 상황

### 2.1 상황별 분류

| # | 상황 | DB 누락 | Sheets 누락 | 자동 복구 | 수동 조치 |
|---|------|---------|-------------|----------|----------|
| 1 | Claude tool 실행 중 사용자 추가 입력 | X (on_stop에서 복구) | X (복구 후 append) | **O** | 불필요 |
| 2 | Google Sheets 서비스 계정 미설정 | X | **O** | X | `cpm_sheets_sync` |
| 3 | 유저가 Sheets URL 미입력/비활성화 | X | **O** | X | 설정 후 `cpm_sheets_sync` |
| 4 | 시트에 서비스 계정 공유 안 함 | X | **O** | X | 시트 공유 후 `cpm_sheets_sync` |
| 5 | Google API 일시 장애 | X | **O** | X | `cpm_sheets_sync` |
| 6 | Claude Code가 비정상 종료 (crash) | **O** (on_stop 미실행) | **O** | X | 다음 세션 시작 시 자동 복구 안 됨 |
| 7 | CPM hook이 settings.json에서 삭제됨 | **O** | **O** | X | `python3 manage.py cpm_setup` |
| 8 | SQLite DB 파일 손상/삭제 | **O** | X (이미 기록분) | X | 백업 복원 |

### 2.2 상세 설명

#### 상황 1: Claude tool 실행 중 추가 입력 (자동 복구됨)

```
08:26:58 [사용자] "기존에 누락된것도 업데이트되나?"     ← on_prompt.py → DB 기록 O
         [Claude] 파일 편집 중...
08:29:32 [사용자] "누락테스트 문자.1"                  ← hook 미발동, transcript에 queue-operation
08:29:39 [사용자] "누락테스트문자 2."                  ← hook 미발동, transcript에 queue-operation
08:29:45 [사용자] "누락테스트문자 3"                   ← hook 미발동, transcript에 queue-operation
         [Claude] 응답 완료
         → on_stop.py 실행
         → transcript 파싱: 3개 queue-operation 발견
         → DB 중복 체크 후 INSERT (source='hook-queue')
```

**Claude Code의 동작 방식:**
- 사용자가 Claude 응답 중에 메시지를 입력하면 `UserPromptSubmit` hook이 **호출되지 않음**
- 대신 Claude Code가 내부적으로 `queue-operation` (operation=enqueue)로 transcript JSONL에 기록
- CPM의 `on_stop.py`가 이 transcript를 파싱하여 누락분을 자동 복구

**transcript JSONL 포맷:**
```json
{
  "type": "queue-operation",
  "operation": "enqueue",
  "timestamp": "2026-04-13T23:29:32.500Z",
  "sessionId": "4fe8c415-...",
  "content": "누락테스트 문자.1"
}
```

**복구 로직 (on_stop.py → recover_queued_messages):**
1. transcript JSONL 파일 열기
2. `type=queue-operation` + `operation=enqueue` 항목 추출
3. 각 항목의 content를 DB에서 `session_id + content` 조합으로 중복 체크
4. 미존재 시 INSERT (`source='hook-queue'`, `status='success'`)

#### 상황 6: Claude Code 비정상 종료

Stop hook이 실행되지 않으므로 마지막 프롬프트의 응답 요약이 없고, 중간 입력 복구도 안 됩니다.
이 경우 프롬프트는 `status='wip'`으로 남으며, 다음에 같은 프로젝트에서 작업 시 웹 대시보드에서 확인 가능합니다.

#### 상황 7: Hook 설정 삭제됨

Claude Code 업데이트나 설정 초기화로 hooks가 삭제될 수 있습니다.
CPM은 이를 방지하기 위해:
1. `on_prompt.py`가 실행될 때마다 `settings.json`을 `settings.hooks.backup.json`으로 백업
2. 대시보드에서 "Hook 수집 중단됨" 경고 표시
3. `cpm_setup` 명령으로 hooks 재설치

---

## 3. source 필드 값 정리

| source | 의미 | 캡처 시점 |
|--------|------|----------|
| `hook` | on_prompt.py에서 직접 캡처 | 사용자 입력 즉시 |
| `hook-queue` | on_stop.py에서 transcript 파싱 복구 | Claude 응답 완료 시 |
| `import` | `cpm_import` 명령으로 과거 기록 가져오기 | 수동 실행 |
| `manual` | 웹 UI 또는 API로 수동 등록 | 수동 |

---

## 4. Google Sheets 연동

### 4.1 동기화 경로

```
┌───────────────┐     ┌───────────────┐     ┌─────────────────┐
│ on_prompt.py  │     │ on_stop.py    │     │ Django Signal   │
│ (로컬 hook)   │     │ (로컬 hook)   │     │ (원격 API)      │
│               │     │               │     │                 │
│ shared.py     │     │ shared.py     │     │ signals.py      │
│ google_sheets │     │ google_sheets │     │ sync_prompt_to  │
│ _append()     │     │ _update()     │     │ _google_sheets()│
└───────┬───────┘     └───────┬───────┘     └────────┬────────┘
        │                     │                      │
        └─────────────┬───────┘──────────────────────┘
                      ▼
              Google Sheets API
              (daemon thread)
              (print('{}') 이후)
```

### 4.2 설정 방법

#### Step 1: Google Cloud 서비스 계정 (서버 관리자)

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. **프로젝트 선택** (또는 새 프로젝트 생성)
3. **API 및 서비스** → **라이브러리** → "Google Sheets API" 검색 → **사용 설정**
4. **API 및 서비스** → **사용자 인증 정보** → **+ 사용자 인증 정보 만들기** → **서비스 계정**
   - 서비스 계정 이름: `cpm-sheets` (임의)
   - 역할: 불필요 (시트 공유로 권한 부여)
5. 생성된 서비스 계정 클릭 → **키** 탭 → **키 추가** → **새 키 만들기** → **JSON** → 다운로드
6. 다운로드된 JSON 파일을 서버에 배치:
   ```bash
   # 예시
   sudo mkdir -p /etc/cpm
   sudo cp ~/Downloads/cpm-sheets-xxxx.json /etc/cpm/service-account.json
   sudo chmod 600 /etc/cpm/service-account.json
   ```
7. 환경변수 설정:
   ```bash
   # .env 파일 또는 시스템 환경변수
   GOOGLE_SHEETS_CREDENTIALS=/etc/cpm/service-account.json

   # Docker의 경우 인라인 JSON 사용 가능
   GOOGLE_SHEETS_CREDENTIALS_JSON='{"type":"service_account",...}'
   ```
8. CPM 서버 재시작

#### Step 2: 시트 공유 및 CPM 설정 (각 사용자)

1. [Google Sheets](https://sheets.google.com)에서 새 스프레드시트 생성
2. **공유** 버튼 → 서비스 계정 이메일 입력 (예: `cpm-sheets@my-project.iam.gserviceaccount.com`)
   - 권한: **편집자**
3. CPM 웹 접속 → `/settings/` 페이지
4. **Google Sheets Integration** 섹션:
   - **Sheet URL**: 스프레드시트 URL 붙여넣기
   - **시트 탭 이름**: 원하는 탭 이름 (비워두면 GitHub 유저명 사용)
   - **자동 기록 활성화**: 체크
5. **Save** → **Test Connection** 클릭하여 연결 확인

#### Step 3: 과거 데이터 일괄 동기화

```bash
# 전체 프롬프트 동기화
python3 manage.py cpm_sheets_sync

# 최근 30일만
python3 manage.py cpm_sheets_sync --days 30

# 특정 유저만
python3 manage.py cpm_sheets_sync --user your_username

# 특정 프로젝트만
python3 manage.py cpm_sheets_sync --project my-project

# 미리보기 (실제 기록 안 함)
python3 manage.py cpm_sheets_sync --dry-run
```

### 4.3 시트 기록 포맷

| 컬럼 | 내용 | 예시 |
|------|------|------|
| A: ID | 프롬프트 DB ID | 10745 |
| B: 날짜 | 생성 시간 | 2026-04-14 08:37 |
| C: 프로젝트 | 프로젝트 이름 | cpm |
| D: 프롬프트 | 사용자 입력 (500자 제한) | Fix login bug... |
| E: 응답 요약 | Claude 응답 요약 (500자 제한) | Fixed by... |
| F: 상태 | wip / success / fail | success |
| G: 태그 | bug / feature / refactor 등 | bug |

- 프롬프트 입력 시: A~D, F=wip 기록
- Claude 응답 완료 시: E(응답 요약), F(상태) 업데이트

---

## 5. 트러블슈팅

### "Hook 수집 중단됨" 경고

**원인**: `~/.claude/settings.json`에 CPM hooks가 없음
**해결**:
```bash
python3 manage.py cpm_setup
```
또는 백업에서 복원:
```bash
cp ~/.claude/settings.hooks.backup.json ~/.claude/settings.json
```

### Google Sheets "권한 없음" 오류

**원인**: 시트를 서비스 계정과 공유하지 않음
**해결**: Google Sheets → 공유 → 서비스 계정 이메일을 편집자로 추가

### 중간 입력이 DB에 없음

**원인**: on_stop.py가 아직 실행되지 않음 (현재 턴 진행 중)
**확인**: Claude 응답 완료 후 DB 확인
```bash
python3 -c "
import sqlite3
from pathlib import Path
conn = sqlite3.connect(str(Path.home() / '.local/share/cpm/cpm.db'))
conn.row_factory = sqlite3.Row
for r in conn.execute('SELECT id,content,source FROM prompts WHERE source=\"hook-queue\" ORDER BY id DESC LIMIT 5'):
    print(f'[{r[\"id\"]}] {r[\"source\"]} | {r[\"content\"][:60]}')
"
```

### 프롬프트가 wip 상태로 남아있음

**원인**: Claude Code가 비정상 종료되어 Stop hook이 실행되지 않음
**확인**:
```bash
python3 -c "
import sqlite3
from pathlib import Path
conn = sqlite3.connect(str(Path.home() / '.local/share/cpm/cpm.db'))
for r in conn.execute('SELECT COUNT(*) FROM prompts WHERE status=\"wip\"'):
    print(f'WIP prompts: {r[0]}')
"
```

---

## 6. 성능 영향

| 작업 | 실행 시점 | 소요 시간 | Claude 블로킹 |
|------|----------|----------|--------------|
| on_prompt.py SQLite INSERT | 즉시 | ~5ms | X (print('{}') 먼저) |
| on_prompt.py Google Sheets append | daemon thread | ~1-2초 | X |
| on_stop.py 응답 업데이트 | 응답 완료 | ~5ms | X (print('{}') 먼저) |
| on_stop.py transcript 파싱 | 응답 완료 | ~10-50ms (파일 크기 의존) | X |
| on_stop.py queue 복구 INSERT | 응답 완료 | ~5ms per row | X |
| on_stop.py Google Sheets update | daemon thread | ~1-2초 | X |

> **핵심 원칙**: `print('{}')` (Claude Code 통과 신호)를 **항상 먼저 출력**하고, 외부 API 호출은 모두 daemon thread에서 실행합니다. Claude Code는 어떤 상황에서도 대기하지 않습니다.
