# CPM 원격 Hook 설정 가이드

윈도우 등 외부 PC에서 Claude Code 프롬프트를 ai100 서버 CPM으로 자동 전송하는 방법.

## 구조

```
[윈도우 PC]                        [ai100 서버]
Claude Code                        CPM Django (port 9200)
    │                                    │
    ├─ UserPromptSubmit ─────────────────> /api/hook/prompt/
    │   (on_prompt_remote.py)            │
    │                                    │
    └─ Stop ─────────────────────────────> /api/hook/stop/
        (on_stop_remote.py)              │
                                    [SQLite DB에 저장]
```

## 설정 방법

### 1단계: hook 파일 복사

윈도우 PC에 디렉토리를 만들고 파일 2개를 복사합니다:

```
C:\cpm\hooks\
  ├── on_prompt_remote.py
  └── on_stop_remote.py
```

파일은 CPM 소스의 `hooks/on_prompt_remote.py`, `hooks/on_stop_remote.py` 입니다.

### 2단계: 서버 주소 설정

각 파일의 `CPM_SERVER` 값을 ai100 서버 주소로 변경:

```python
CPM_SERVER = 'http://ai100서버IP:9200'
```

또는 환경변수로 설정:

```cmd
set CPM_SERVER=http://ai100서버IP:9200
```

PowerShell:
```powershell
$env:CPM_SERVER = "http://ai100서버IP:9200"
```

영구 설정 (시스템 환경변수):
```
제어판 > 시스템 > 고급 시스템 설정 > 환경 변수
변수명: CPM_SERVER
값: http://ai100서버IP:9200
```

### 3단계: Claude Code hooks 등록

윈도우에서 Claude Code의 settings 파일을 편집합니다:

**파일 위치:** `%USERPROFILE%\.claude\settings.json`

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "python C:\\cpm\\hooks\\on_prompt_remote.py"
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python C:\\cpm\\hooks\\on_stop_remote.py"
      }
    ]
  }
}
```

> **주의:** 경로의 `\`는 JSON에서 `\\`로 이스케이프해야 합니다.

### 4단계: 서버 방화벽 확인

ai100 서버에서 9200 포트가 열려있는지 확인:

```bash
# ai100 서버에서
sudo ufw allow 9200/tcp

# 또는 확인
sudo ufw status | grep 9200
```

### 5단계: 테스트

윈도우에서 연결 테스트:

```cmd
curl -X POST http://ai100서버IP:9200/api/hook/prompt/ -H "Content-Type: application/json" -d "{\"prompt\": \"test from windows\", \"session_id\": \"test-123\", \"cwd\": \"C:\\projects\\test\", \"hostname\": \"WINDOWS-PC\"}"
```

성공 시 응답:
```json
{"status": "ok", "prompt_id": 123, "project": "test"}
```

## 기존 로컬 hook과 병행 사용

로컬 DB 저장 + 원격 서버 전송을 동시에 하려면:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "python C:\\cpm\\hooks\\on_prompt.py"
      },
      {
        "type": "command",
        "command": "python C:\\cpm\\hooks\\on_prompt_remote.py"
      }
    ]
  }
}
```

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 프롬프트 안 나옴 | 서버 연결 불가 | `curl` 테스트, 방화벽 확인 |
| Claude Code 느려짐 | 서버 응답 지연 | timeout=5초라 최대 5초 대기 후 포기 |
| 프로젝트명이 다름 | cwd 경로 차이 | 웹에서 프로젝트 이름 수정 |
| Python not found | PATH 미설정 | `python3` 또는 전체 경로 사용 |

## 보안 참고

- 현재 hook API는 **인증 없이** 접근 가능합니다 (hooks가 빠르게 동작해야 하므로)
- 외부 인터넷에서 접근하려면 VPN 또는 API 키 인증 추가를 권장합니다
- 내부 네트워크에서만 사용하는 경우 방화벽으로 IP 제한 권장
