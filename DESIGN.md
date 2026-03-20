# CPM (Claude Prompt Manager) 설계 문서

## 1. 개요

여러 Claude Code 터미널을 동시에 사용할 때 **프롬프트(명령어)를 프로젝트별로 기록·추적·검색**하는 CLI 도구.

### 해결하는 문제
- 3~4개 Claude Code 터미널을 열어놓으면 어떤 창에 무슨 질문을 했는지 헷갈림
- 프롬프트 이력이 남지 않아 같은 질문을 반복하게 됨
- 성공/실패 여부를 체계적으로 추적할 수 없음

### 핵심 원칙
- **CLI-first**: Claude Code와 같은 터미널 환경에서 바로 사용
- **크로스플랫폼**: Linux(서버) + Windows(데스크탑) 모두 동작
- **단일 파일**: 외부 서비스 의존 없이 SQLite로 로컬 완결
- **rich fallback**: rich 라이브러리 없어도 plain text로 동작

---

## 2. 기술 스택

| 항목 | 선택 | 이유 |
|------|------|------|
| 언어 | Python 3.8+ | 기존 개발 환경, 크로스플랫폼 |
| DB | SQLite (WAL 모드) | 설치 불필요, 단일 파일, 충분한 성능 |
| CLI 파서 | argparse (표준 라이브러리) | 외부 의존성 없음 |
| 터미널 UI | rich (선택적) | 테이블·패널·컬러 출력, 없으면 plain text |
| 직렬화 | JSON (내보내기/가져오기용) | 가독성, git 추적 가능 |
| 패키징 | setuptools (entry_points) | `pip install -e .` → `cpm` 명령어 등록 |

---

## 3. 디렉토리 구조

```
cpm/
├── cpm.py              # 메인 애플리케이션 (단일 파일)
├── setup.py            # pip 설치용
├── README.md           # 사용법 가이드
├── DESIGN.md           # 이 문서
├── CLAUDE.md           # Claude Code 작업 컨텍스트
└── tests/
    └── test_cpm.py     # 테스트
```

### 데이터 저장 위치

| OS | 경로 |
|----|------|
| Linux/Mac | `~/.local/share/cpm/cpm.db` |
| Windows | `%APPDATA%\cpm\cpm.db` |

환경변수 `XDG_DATA_HOME` (Linux) 또는 `APPDATA` (Windows) 를 따름.

---

## 4. 데이터베이스 스키마

### 4.1 projects (프로젝트)

```sql
CREATE TABLE projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,      -- 프로젝트 식별자 (예: myvoice)
    path        TEXT,                       -- 프로젝트 경로 (예: /home/user/myvoice)
    description TEXT,                       -- 설명
    created_at  TEXT DEFAULT (datetime('now','localtime')),
    updated_at  TEXT DEFAULT (datetime('now','localtime'))
);
```

### 4.2 terminals (터미널)

```sql
CREATE TABLE terminals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,       -- 터미널 이름 (예: myvoice-1)
    project_id  INTEGER,                    -- 연결된 프로젝트
    session_id  TEXT,                        -- 자동 감지된 세션 ID
    memo        TEXT,                        -- 메모 (예: "메인 개발용")
    last_activity TEXT,                      -- 마지막 활동 시각
    created_at  TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);
```

### 4.3 prompts (프롬프트) — 핵심 테이블

```sql
CREATE TABLE prompts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER NOT NULL,      -- 소속 프로젝트
    terminal_id      INTEGER,               -- 사용한 터미널
    content          TEXT NOT NULL,          -- 프롬프트 내용
    response_summary TEXT,                   -- Claude 응답 요약
    status           TEXT DEFAULT 'wip',     -- wip | success | fail
    tag              TEXT,                    -- bug | feature | refactor | ...
    note             TEXT,                    -- 추가 메모
    parent_id        INTEGER,               -- 부모 프롬프트 ID (후속작업 연결)
    created_at       TEXT DEFAULT (datetime('now','localtime')),
    updated_at       TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (terminal_id) REFERENCES terminals(id) ON DELETE SET NULL,
    FOREIGN KEY (parent_id) REFERENCES prompts(id) ON DELETE SET NULL
);
```

### 4.4 templates (프롬프트 템플릿)

```sql
CREATE TABLE templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,       -- 템플릿 이름
    content     TEXT NOT NULL,              -- 템플릿 내용
    tag         TEXT,                        -- 기본 태그
    description TEXT,                        -- 설명
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);
```

### 4.5 인덱스

```sql
CREATE INDEX idx_prompts_project ON prompts(project_id);
CREATE INDEX idx_prompts_status  ON prompts(status);
CREATE INDEX idx_prompts_tag     ON prompts(tag);
CREATE INDEX idx_prompts_parent  ON prompts(parent_id);
```

### 4.6 ER 다이어그램

```
projects 1──N prompts N──1 terminals
                │
                │ parent_id (self-ref)
                ▼
             prompts (후속작업 체인)

templates (독립 — use 시 prompts로 복사)
```

---

## 5. CLI 명령어 체계

### 5.1 명령어 구조

```
cpm <command> [subcommand] [args] [options]
```

모든 명령어에 단축키(alias) 지원:

| 전체 | 단축 |
|------|------|
| `project` | `p` |
| `terminal` | `t` |
| `prompt` | `pr` |
| `template` | `tpl` |
| `board` | `b` |
| `log` | `l` |

서브커맨드 없이 입력하면 `list` 기본 실행:
- `cpm project` → `cpm project list`
- `cpm terminal` → `cpm terminal list`

### 5.2 프로젝트 관리

```bash
# 추가
cpm project add <이름> [--path 경로] [--desc 설명]
cpm p add myvoice --path /home/user/myvoice --desc "AI TTS 앱"

# 삭제 (프롬프트 있으면 --force 필요)
cpm project remove <이름|ID> [--force]
cpm p rm myvoice --force

# 목록
cpm project list
cpm p ls
```

### 5.3 터미널 관리

```bash
# 추가 (세션 ID 자동 감지)
cpm terminal add <이름> [--project 프로젝트] [--session 세션ID] [--memo 메모]
cpm t add myvoice-1 -p myvoice -m "메인 개발용"

# 삭제
cpm terminal remove <이름|ID>

# 메모 수정
cpm terminal memo <이름|ID> "새 메모"

# 목록
cpm terminal list
```

세션 ID 자동 감지 우선순위:
1. `$TMUX_PANE` → `tmux:<pane_id>`
2. `$STY` → `screen:<session>`
3. `$PPID` 또는 `$TERM_SESSION_ID` → `pid:<id>`

### 5.4 프롬프트 관리 (핵심)

```bash
# 저장
cpm prompt add <프로젝트> "내용" [옵션]
  --tag, -t      태그 (bug|feature|refactor|docs|test|deploy|config|other)
  --terminal, -T 터미널 이름 또는 ID
  --parent, -P   부모 프롬프트 ID (후속작업 연결)
  --status, -s   초기 상태 (기본: wip)

# 상태 변경
cpm prompt status <ID> <success|fail|wip> [--note "메모"]
cpm pr st 15 success -n "API 완성"

# 응답 요약 저장
cpm prompt response <ID> "요약 내용"
cpm pr res 15 "app.py에 /api/preview 엔드포인트 추가"

# 프롬프트 연결
cpm prompt link <자식ID> <부모ID>
cpm pr link 17 15

# 검색
cpm prompt search [키워드] [--project 필터] [--status 필터] [--tag 필터] [--limit N]
cpm pr search "CORS" -p myvoice -s fail
cpm pr s --tag bug --limit 10
```

### 5.5 조회 명령어

```bash
# 프롬프트 상세 (응답요약, 노트, 후속작업 체인 표시)
cpm show <ID>

# 프로젝트별 이력
cpm log <프로젝트> [--status fail] [--tag bug] [--limit 30]

# 전체 대시보드 (프로젝트별 성공/실패/진행중 + 최근 실패 목록)
cpm board

# 통계
cpm stats
```

### 5.6 템플릿

```bash
# 등록
cpm template add <이름> "내용" [--tag feature] [--desc 설명]
cpm tpl add code-review "이 코드를 리뷰해줘. 버그, 성능, 가독성 관점으로" -t refactor

# 목록
cpm template list

# 사용 (프롬프트로 복사)
cpm template use <이름|ID> <프로젝트>
cpm tpl use code-review myvoice

# 삭제
cpm template remove <이름|ID>
```

### 5.7 내보내기 / 가져오기

```bash
# JSON 내보내기 (전체 데이터)
cpm export [--output cpm_backup.json]

# JSON 가져오기
cpm import cpm_backup.json
```

---

## 6. 출력 설계

### 6.1 rich 모드 (rich 설치 시)

`cpm board` 출력 예시:

```
╔══════════════════════════════════════════════════════════╗
║  📊 CPM Dashboard                                       ║
║  전체 프롬프트: 51  ✅ 36  ❌ 7  🔄 8                   ║
╠══════════════════════════════════════════════════════════╣

        프로젝트별 현황
┌────────────────┬──────────┬────┬────┬────┬──────┬─────────────────┐
│ 프로젝트       │ 설명     │ ✅ │ ❌ │ 🔄 │ 합계 │ 최근 프롬프트    │
├────────────────┼──────────┼────┼────┼────┼──────┼─────────────────┤
│ myvoice        │ AI TTS   │ 18 │  3 │  2 │   23 │ 음성 프리뷰...  │
│ 901planner     │ AI 멘토링│ 12 │  1 │  2 │   15 │ 쿼트 검색...    │
│ bitic-web      │ 홈페이지 │  6 │  0 │  2 │    8 │ 섹션3 반응형... │
│ jebudo-tide    │ 조석 앱  │  5 │  0 │  0 │    5 │ 완료            │
└────────────────┴──────────┴────┴────┴────┴──────┴─────────────────┘

  ⚠️ 최근 실패 프롬프트
  #42 [myvoice] CORS 에러 수정 — nginx 설정 확인 필요
  #38 [myvoice] 음성 프로파일 저장 — DB 연결 실패
```

`cpm show 15` 출력 예시:

```
╭─────────────────────────────────────────────╮
│ 프롬프트 #15  ✅                             │
│                                             │
│ 프로젝트: myvoice                            │
│ 터미널:  myvoice-1                           │
│ 태그:    feature                             │
│ 상태:    success                             │
│ 생성:    2025-03-20 14:30                    │
│                                             │
│ 내용:                                        │
│ FastAPI에 음성 프리뷰 엔드포인트 추가해줘      │
│                                             │
│ 응답 요약:                                   │
│ app.py에 /api/preview POST 추가, WAV 스트리밍│
│                                             │
│ 노트:                                        │
│ 프리뷰 API 완성, 테스트 통과                  │
│                                             │
│ 후속 작업:                                   │
│   → #17 🔄 프리뷰 타임아웃 설정 추가          │
│   → #19 ✅ 프리뷰 캐싱 적용                  │
╰─────────────────────────────────────────────╯
```

### 6.2 plain text 모드 (rich 없을 때)

동일한 정보를 ASCII 문자로 표현:

```
=== CPM Dashboard ===
전체: 51  ✓36  ✗7  ~8

프로젝트        ✓    ✗    ~    합계
--------------------------------------
myvoice        18    3    2     23
901planner     12    1    2     15
bitic-web       6    0    2      8
jebudo-tide     5    0    0      5
```

---

## 7. 상태 모델

### 7.1 프롬프트 상태

```
[생성] → wip (🔄 진행중)
           │
           ├──→ success (✅ 성공)
           │
           └──→ fail (❌ 실패)
                    │
                    └──→ 후속 프롬프트 생성 (parent_id 연결)
                              │
                              └──→ success / fail / wip
```

상태는 자유롭게 변경 가능 (fail → wip → success 등).

### 7.2 태그 목록

| 태그 | 용도 | 사용 예시 |
|------|------|-----------|
| `bug` | 버그 수정 | "CORS 에러 수정해줘" |
| `feature` | 기능 추가 | "음성 프리뷰 기능 추가" |
| `refactor` | 리팩토링 | "코드 구조 개선해줘" |
| `docs` | 문서 작업 | "README 업데이트" |
| `test` | 테스트 | "유닛 테스트 작성해줘" |
| `deploy` | 배포 | "Cloudflare Pages 배포 설정" |
| `config` | 설정 | "nginx.conf 수정" |
| `other` | 기타 | 분류 어려운 작업 |

---

## 8. 프롬프트 연결 (체이닝)

후속작업을 `parent_id`로 연결하여 작업 흐름을 추적:

```
#15 [feature] "음성 프리뷰 엔드포인트 추가" ✅
 └─ #17 [bug] "프리뷰 타임아웃 에러 수정" ❌
     └─ #20 [bug] "타임아웃 값을 30초로 증가" ✅
 └─ #19 [feature] "프리뷰 결과 캐싱 적용" ✅
```

`cpm show 15` 실행 시 하위 체인 전체 표시.
`cpm prompt link 20 17` 으로 사후 연결도 가능.

---

## 9. 터미널 세션 관리

### 9.1 자동 감지

환경변수로 현재 터미널 세션을 자동 감지:

```python
감지 우선순위:
1. $TMUX_PANE     → "tmux:%17"
2. $STY           → "screen:12345.pts-0"
3. $PPID          → "pid:12345"
4. $TERM_SESSION_ID → 해당 값
```

### 9.2 수동 관리

```bash
# 터미널 등록
cpm t add myvoice-1 -p myvoice -m "메인 개발 — FastAPI 작업"

# 메모 업데이트
cpm t memo myvoice-1 "CORS 디버깅 중"

# 프롬프트 저장 시 터미널 지정
cpm pr add myvoice "CORS 수정" --terminal myvoice-1
```

터미널 목록에 마지막 작업 내용이 자동 표시됨.

---

## 10. JSON 내보내기/가져오기

### 10.1 내보내기 포맷

```json
{
  "exported_at": "2025-03-20T14:30:00",
  "projects": [
    {
      "id": 1,
      "name": "myvoice",
      "path": "/home/user/myvoice",
      "description": "AI TTS 앱",
      "created_at": "2025-03-15 10:00:00",
      "updated_at": "2025-03-20 14:00:00"
    }
  ],
  "terminals": [...],
  "prompts": [...],
  "templates": [...]
}
```

### 10.2 사용 시나리오

- **백업**: `cpm export -o ~/backup/cpm_20250320.json`
- **머신 이동**: Windows → Linux로 데이터 이전
- **git 추적**: 프로젝트 폴더에 JSON 저장 후 버전 관리

---

## 11. 설치 및 실행 환경

### 11.1 Linux 설치

```bash
# 프로젝트 클론 또는 복사
cd ~/cpm

# 설치 (editable 모드)
pip install -e . --break-system-packages

# 또는 가상환경에서
python -m venv .venv
source .venv/bin/activate
pip install -e .

# 확인
cpm --help
cpm stats
```

### 11.2 Windows 설치

```powershell
cd E:\cpm
pip install -e .

# 확인
cpm --help
```

### 11.3 의존성

| 패키지 | 필수 | 용도 |
|--------|------|------|
| Python 3.8+ | ✅ | 런타임 |
| sqlite3 | ✅ | DB (표준 라이브러리) |
| argparse | ✅ | CLI (표준 라이브러리) |
| rich | ❌ (권장) | 터미널 UI 미화 |

---

## 12. 실사용 워크플로우

### 12.1 일일 작업 흐름

```bash
# 1. 아침: 현황 확인
cpm board
cpm log myvoice --status fail       # 어제 실패한 것 확인

# 2. 작업 시작: 프롬프트 기록 → Claude Code에 입력
cpm pr add myvoice "어제 실패한 CORS 문제 해결. nginx.conf 확인" -t bug -P 42

# 3. 작업 완료: 결과 기록
cpm pr st 45 success -n "nginx.conf에 add_header 추가로 해결"
cpm pr res 45 "nginx.conf 수정, Access-Control-Allow-Origin 헤더 추가"

# 4. 다른 프로젝트 전환
cpm pr add bitic-web "섹션3 모바일 반응형 깨짐 수정" -t bug -T bitic-1

# 5. 퇴근 전: 현황 확인
cpm board
```

### 12.2 다중 터미널 관리

```
터미널1 (myvoice-1)          터미널2 (bitic-1)          터미널3 (901-1)
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ Claude Code      │    │ Claude Code      │    │ Claude Code      │
│ (MyVoice 작업)   │    │ (홈페이지 작업)   │    │ (901 Planner)   │
└──────────────────┘    └──────────────────┘    └──────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
cpm pr add myvoice ..    cpm pr add bitic-web ..  cpm pr add 901planner ..
  -T myvoice-1             -T bitic-1               -T 901-1
```

각 터미널에서 작업 전 `cpm pr add` 실행 → 어떤 창에서 무슨 작업했는지 기록됨.

---

## 13. 향후 확장 계획

### Phase 2 (선택적)
- **웹 UI**: FastAPI + HTML로 브라우저 기반 대시보드
- **자동 기록**: Claude Code hooks 연동으로 프롬프트 자동 캡처
- **Markdown 리포트**: 주간/월간 작업 보고서 자동 생성

### Phase 3 (아이디어)
- **다중 사용자**: 팀 단위 프롬프트 공유
- **AI 분석**: 실패 패턴 분석, 프롬프트 개선 제안
- **클라우드 동기화**: Windows ↔ Linux 간 DB 동기화
