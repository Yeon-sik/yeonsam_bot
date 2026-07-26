# 연삼이 | Project Detail

> 이 문서는 연삼이 저장소의 Discord 봇, 정적 게임 가이드, SQLite 운영 데이터,
> Steam 패치 알림과 배포 경계를 설명합니다. 빠른 개요는
> [Project_Intro.md](./Project_Intro.md)를 참고합니다.

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | Active |
| 적용 범위 | 제품 기능 커밋 `d000f83`과 `feat/project-docs-notion` 문서 자동화 |
| 최종 갱신 | 2026-07-27T00:07:09+09:00 |
| 검증 환경 | Python 3.12.13, Node.js 22, Windows 로컬 환경 |
| 문서 진실 원천 | Git 저장소의 `docs/Project_Detail.md` |
| 공개 경계 | 코드·테스트·공개 배포 파일만 사용, 실제 서버 식별자와 운영 데이터 제외 |

---

## 1. 문서 목적과 범위

### 포함

- Discord bot 프로세스의 시작·종료와 command 등록
- 신규 서버 설정과 멤버 환영 흐름
- JSON 기반 게임 가이드 검색·선택형 UI
- Steam 공식 뉴스 기반 서버별 패치 알림
- SQLite 설정·구독·지표·runtime state
- 정적 GitHub Pages와 Docker/임시 Actions 실행 경로
- 로컬 테스트와 공개 사이트 응답 검증
- Git Markdown을 Notion 전용 페이지에 미러링하는 문서 자동화

### 제외

- Discord Developer Portal 설정과 실제 gateway 연결 성공
- 실제 서버의 slash command, welcome event, 패치 메시지 E2E
- Steam API의 현재 응답과 장시간 polling 안정성
- Docker image·Compose·영속 볼륨의 실환경 동작
- 사용자 수, 서버 수, 매출, 성능, 장애율 같은 운영 성과
- 게임 정보의 공식성·최신성 및 이미지 자산의 권리 보증

## 2. 문제 맥락과 제약

Discord 기반 협동 게임 서버는 신규 멤버 안내, 역할·채널 권한, 게임 공략,
공식 업데이트 전달을 반복해서 운영합니다. 이 정보가 Discord 메시지, 외부 웹,
관리자 개인 메모로 분산되면 신규 멤버 경험과 정보 최신성이 관리자의 수작업에
의존합니다.

프로젝트는 다음 제약 안에서 작은 운영 단위를 먼저 완성했습니다.

- 별도 웹 백엔드 없이 GitHub Pages로 공개 가이드를 제공
- Discord 이벤트와 UI는 `discord.py` 범위에서 구현
- 소규모 단일 프로세스 운영에 맞춰 SQLite 사용
- 공개 Steam News API만 패치 공급원으로 사용
- 게임 콘텐츠를 Git에서 검토할 수 있는 JSON으로 유지
- 실제 운영 환경 증거가 없는 기능은 저장소 검증과 분리

## 3. 사용자와 핵심 흐름

| 사용자 | 목표 | 핵심 흐름 |
| --- | --- | --- |
| Discord 서버 관리자 | 환영 기능을 서버에 맞게 구성 | `/설정` → 채널 → 문구·링크 → 권한 진단 → 테스트 |
| 신규 멤버 | 서버 안내를 받고 닉네임을 설정 | member join → 환영 embed → profile modal |
| 게임 사용자 | 필요한 공략 항목을 빠르게 탐색 | `/도움` 또는 항목검색 → 게임 → 주제 → 항목 |
| 서버 관리자 | 새 패치 소식을 지정 채널에 전달 | 게임·채널 구독 → cursor 시드 → 새 Steam 글 발송 |
| 웹 방문자 | 전체 가이드를 링크로 열람 | 랜딩 → 게임 페이지 → JSON 기반 카드·레코드 |

## 4. 범위와 구현 현황

| 기능 | 구현 상태 | 검증 수준 | 확인 근거 | 남은 위험 |
| --- | --- | --- | --- | --- |
| 프로세스 시작·Cog 로드 | 구현 완료 | 저장소 검증 | [main.py](../bot/main.py) | 실제 Discord 연결 미검증 |
| 서버 설정 UI | 구현 완료 | 저장소 검증·일부 단위 테스트 | [settings.py](../bot/cogs/settings.py) | interaction E2E 없음 |
| 신규 멤버 환영 | 구현 완료 | embed 단위 테스트 | [welcome.py](../bot/cogs/welcome.py) | 실제 member join 미검증 |
| 게임 검색·탐색 | 구현 완료 | 구조·정적 검사 | [yeonsam.py](../bot/cogs/yeonsam.py) | 25개 선택 제한 |
| 패치 알림 | 구현 완료 | parser·cursor 단위 테스트 | [patch_alerts.py](../bot/cogs/patch_alerts.py) | Steam·Discord E2E 없음 |
| SQLite 저장 | 구현 완료 | 단위 테스트 | [storage.py](../bot/utils/storage.py) | 다중 프로세스 검증 없음 |
| GitHub Pages | 구현 완료 | 공개 HTTP 응답 확인 | [deploy-pages.yml](../.github/workflows/deploy-pages.yml) | Actions 최근 실행은 별도 검증 필요 |
| Docker 운영 경로 | 구성 완료 | 저장소 검증 | [Dockerfile](../Dockerfile) | build·기동 미검증 |
| Notion 문서 미러 | 기능 브랜치에 구성 | 로컬 검증 예정 | [project-docs-notion.yml](../.github/workflows/project-docs-notion.yml) | Secret·페이지 접근 전 미발행 |

## 5. 시스템 아키텍처

```text
Discord 사용자
  → slash command / event / persistent view
  → bot/cogs
       ├─ settings / welcome
       ├─ yeonsam guide browser
       └─ patch alerts
  → bot/utils
       ├─ SQLite storage
       ├─ shared game JSON loader
       ├─ Steam News client
       └─ validation / invite / embed builders
  → Discord response

웹 방문자
  → GitHub Pages HTML
  → docs/assets/game-page.js
  → docs/games/*/*.json
  → 카드·몬스터·레코드·가이드 렌더링

GitHub main 변경
  ├─ docs/** → GitHub Pages 배포
  └─ project docs → 검증 → 승인된 Notion 전용 페이지 미러
```

### 컴포넌트 책임

| 컴포넌트 | 책임 | 의존성 | 실패 시 영향 |
| --- | --- | --- | --- |
| `bot/main.py` | bot lifecycle, command sync, `/health`, 공통 metric | Discord, storage | 명령·이벤트 전체 중단 |
| `bot/cogs/settings.py` | 관리자 온보딩과 진단 | Discord UI, storage | 서버 설정 변경 불가 |
| `bot/cogs/yeonsam.py` | 가이드 검색·선택·embed | 공유 JSON, 이미지 | 가이드 탐색 일부 또는 전체 실패 |
| `bot/cogs/patch_alerts.py` | 구독 관리와 polling | Steam, Discord, storage | 새 패치 알림 지연·누락 |
| `bot/utils/storage.py` | 설정·지표·cursor 영속화 | SQLite, `BOT_DATA_DIR` | 서버별 상태 유실 또는 갱신 실패 |
| `game-page.js` | 게임 JSON의 웹 렌더링 | 정적 JSON, HTML fallback | 웹 가이드 축소 또는 fallback 표시 |
| Pages workflow | 공개 설정 주입과 정적 배포 | GitHub Actions Variables | 설치 CTA·상태 정보 미설정 |
| project docs workflow | 문서 검증과 Notion replace-only 미러 | GitHub Environment Secrets | 검증 실패 또는 발행 중단 |

### 데이터 흐름

```text
관리자 입력
  → 권한·URL 검증
  → guild_settings
  → welcome embed / setup UI

Steam News payload
  → article 정규화
  → last_seen_id 비교
  → 최대 최근 항목 순차 발송
  → 성공한 항목까지 cursor 갱신

게임 JSON
  ├─ Python catalog / search / Discord embed
  └─ JavaScript fetch / web card / hash route
```

## 6. 도메인 모델과 불변식

### SQLite 데이터

| 데이터 | 생명주기 | 진실 원천 | 주요 규칙 |
| --- | --- | --- | --- |
| 길드 설정 | 서버 등록부터 제거까지 | `guild_settings` | 길드별 환영 채널·문구·링크 |
| 일별 지표 | 날짜·길드·metric 단위 | `daily_metrics` | 충돌 시 값 원자 증가 |
| 패치 구독 | 관리자 설정부터 삭제까지 | `patch_subscriptions` | 길드·게임 조합당 한 cursor |
| runtime state | 프로세스 운영 상태 | `runtime_state` | legacy migration과 전역 상태 기록 |

불변식은 다음과 같습니다.

1. 런타임 비밀값은 환경변수에서 읽고 Git 문서에 저장하지 않습니다.
2. 길드별 설정과 구독은 다른 길드 데이터와 분리합니다.
3. 길드 제거 이벤트는 해당 길드의 설정·구독·지표를 삭제합니다.
4. 패치 알림은 최초 설정 시 최신 항목을 cursor로 시드해 과거 글 일괄 발송을
   피합니다.
5. 발송 실패 시 성공하지 않은 다음 항목으로 cursor를 앞당기지 않습니다.

### 공유 게임 콘텐츠

공통 최상위 계약은 `slug`, `name`, `profileImage`, `description`, `guides`입니다.
`guides`는 게임에 따라 다음 형태를 사용합니다.

- `monsters`: 몬스터 카드와 상세 수치
- `groups.entries`: 맵·아이템·업그레이드 같은 레코드
- `sections.cards`: 이미지 단계형 가이드
- `content`: 텍스트 중심 가이드

`pagePath`와 `botRenderAllGuides`는 선택적인 탐색 힌트입니다. 반면 JSON의
top-level `install`은 현재 주 렌더 경로에서 소비되지 않으므로, 필드 존재만으로
사용자에게 설치 가이드가 노출된다고 간주하지 않습니다.

## 7. 핵심 기술 의사결정

### 결정 1. 공유 JSON으로 Discord와 웹 콘텐츠 통합

- **상황**: 같은 공략을 두 UI에 수동 복사하면 내용이 빠르게 어긋납니다.
- **제약**: 정적 사이트에는 별도 API 서버가 없습니다.
- **선택**: Git에 추적되는 게임 JSON을 Python과 JavaScript가 함께 읽습니다.
- **근거**: 작은 프로젝트에서 별도 CMS보다 검토·배포 비용이 낮습니다.
- **결과**: 한 변경으로 Discord와 웹 데이터를 갱신할 수 있습니다.
- **비용과 위험**: 정식 schema와 동등성 테스트가 없고, HTML inline fallback이
  일부 콘텐츠를 복제합니다.
- **재검토 조건**: 콘텐츠 작성자가 늘거나 schema 변형이 추가될 때입니다.

### 결정 2. 운영 상태를 JSON에서 SQLite로 이관

- **상황**: 서버 설정, 구독 cursor, 일별 metric을 단일 JSON에 쓰면 동시 갱신과
  부분 업데이트가 취약합니다.
- **제약**: 현재 운영 모델은 단일 봇 프로세스와 로컬 영속 볼륨입니다.
- **선택**: 표준 라이브러리 SQLite와 작은 repository 함수 집합을 사용합니다.
- **근거**: 별도 DB 서버 없이 transaction과 upsert를 사용할 수 있습니다.
- **결과**: 설정·구독 round-trip, 스레드 기반 metric 증가, 길드 삭제를 테스트할
  수 있게 됐습니다.
- **비용과 위험**: 다중 프로세스나 여러 호스트로 확장하면 SQLite 파일 경계와
  locking 전략을 다시 검토해야 합니다.

### 결정 3. Steam 공식 News API와 cursor 방식 사용

- **상황**: 관리자가 게임 공지를 반복해서 확인하고 전달합니다.
- **선택**: 공개 `ISteamNews/GetNewsForApp/v2` 결과를 정규화하고 서버별 마지막
  article ID 이후의 항목만 발송합니다.
- **근거**: 비공식 scraping보다 공급원과 응답 계약이 명확합니다.
- **결과**: Lethal Company와 R.E.P.O.의 서버별 채널 구독을 구성했습니다.
- **비용과 위험**: 실제 API 장애, rate limit, payload 변화에 대한 장시간
  운영 검증과 backoff 정책이 남아 있습니다.

### 결정 4. Git Markdown을 원본으로, Notion을 읽기 전용 미러로 사용

- **상황**: 저장소 문서와 Notion을 모두 수동 수정하면 근거와 버전이 갈립니다.
- **선택**: 이 두 Markdown을 canonical source로 두고, `main`의 승인된 revision만
  전용 Notion 페이지에 replace-only 방식으로 발행합니다.
- **안전장치**: 기본 `manual` 모드, 정확한 `PUBLISH` 확인, protected Environment,
  모든 페이지 preflight, source fingerprint를 사용합니다.
- **비용과 위험**: 최초 integration, 페이지 공유, Environment Secret 설정은
  사용자가 한 번 수행해야 합니다.

## 8. 외부 연동과 실패 경계

| 외부 대상 | 목적 | 인증·공개값 | 실패 처리 | 현재 검증 |
| --- | --- | --- | --- | --- |
| Discord API | command, event, message, profile UI | bot token은 환경변수 | 공통 error handler와 metric | 실서버 미검증 |
| Steam News | 공식 패치 기사 조회 | 공개 endpoint | timeout, parse error, cursor 유지 | synthetic payload만 검증 |
| GitHub Pages | 정적 사이트 배포 | 공개 Application ID·상태 URL | 미설정 상태 UI | HTTP 응답 확인 |
| Notion API | Git Markdown 미러 | protected Environment Secrets | 전체 페이지 preflight 후 발행 | Secret 입력 전 |

`/health`는 Discord ready flag를 반환하는 간단한 readiness 신호입니다. Steam,
SQLite 쓰기, 채널 권한까지 종합적으로 확인하는 health check는 아닙니다.

## 9. 데이터 보호와 보안

| 경계 | 정책 | 검증 방법 |
| --- | --- | --- |
| Discord bot token | 환경변수 또는 GitHub Secret에만 저장 | publishable Markdown credential pattern 검사 |
| Notion token·페이지 ID | `notion-production` Environment Secret에만 저장 | 저장소 파일과 문서에서 제외 |
| 공개 사이트 설정 | Application ID, support URL, health URL만 build-time 주입 | `build-site-config.py` 입력 제한 |
| 링크 입력 | HTTP/HTTPS만 허용 | validation 단위 테스트 |
| 길드 데이터 | 길드별 SQLite row, guild remove 시 삭제 | storage 단위 테스트 |
| 문서 발행 | `main`과 승인 플래그가 아니면 `--apply` 거부 | sync runtime branch guard |

문서 자동 검사는 흔한 credential 형태, 사용자별 절대 경로와 placeholder를
차단합니다. 저장소 전체의 과거 운영 데이터·로컬 산출물·Git 이력을 정리하는
검사는 별도 privacy gate로 유지해야 합니다.

## 10. 테스트와 검증 전략

### 현재 테스트 범위

- 최소 권한 Discord OAuth 초대 URL
- Steam payload 정규화, cursor 순서, 오래된 글 필터링, summary 제한
- legacy JSON 이관, 길드 설정·구독·runtime state round-trip
- 네 스레드의 총 100회 metric 원자 증가
- 길드 제거 시 저장 데이터 삭제
- HTTP/HTTPS 링크 검증
- 설정값을 반영한 환영 embed

### 현재 미검증 범위

- `main.py` lifecycle과 Discord gateway
- Cog interaction, 버튼·select·modal의 실제 권한과 응답
- 게임 탐색 UI 전체와 25개 초과 항목
- Steam 실통신, polling loop, Discord 채널 발송
- Docker build·Compose·volume·container health
- Python 3.11과 3.12 전체 배포 매트릭스

### 검증 이력

| 일시 | 기준 | 명령·환경 | 결과 | 미검증 항목 |
| --- | --- | --- | --- | --- |
| 2026-07-27 KST | `d000f83` + 문서 자동화 브랜치 | Python 3.12.13, `python -m unittest discover -s tests -v` | 15개 통과 | Discord·Steam·Docker E2E |
| 2026-07-26 KST | `d000f83` | Node `--check`, JSON parse, 링크·미디어 검사 | JS 2개·JSON 3개 통과, 상대 링크·미디어 누락 0 | 브라우저 상호작용 |
| 2026-07-26T15:05:35Z | 공개 Pages | 랜딩과 세 게임 URL HTTP HEAD | 4개 모두 HTTP 200 | UI 동작·상태 API |
| 2026-07-27 KST | 문서 자동화 브랜치 | project docs validator와 render dry-run | 0 errors·0 warnings, 두 문서 렌더 성공 | Notion 실제 쓰기 |

## 11. 배포·운영·복구

```text
Bot 변경
  → Python 검증
  → container 또는 process 배포
  → /health 관찰
  → SQLite 영속 볼륨 유지

정적 사이트 변경
  → main push
  → site config 생성
  → docs artifact 업로드
  → GitHub Pages 배포

프로젝트 문서 변경
  → pull request 검증
  → main 병합
  → 수동 validate
  → PUBLISH + Environment 승인
  → Notion 전용 페이지 교체
```

- **Bot 배포 조건**: token과 Members intent, 필요한 채널·역할 권한, 영속
  `BOT_DATA_DIR`가 필요합니다.
- **Pages 배포 조건**: `main`의 `docs/**` 또는 관련 workflow 변경이 필요합니다.
- **문서 발행 조건**: `notion-production` Environment, `main` 제한, required
  reviewer, Notion 페이지 공유와 두 Secret이 필요합니다.
- **관찰 항목**: `/health`, command error metric, welcome failure, patch poll·delivery
  failure, Pages workflow summary입니다.
- **백업**: 운영 SQLite 파일과 볼륨을 배포 호스트 정책에 따라 백업해야 합니다.
- **복구**: bot은 이전 image/revision과 동일한 데이터 볼륨으로 재기동하고,
  Notion은 canonical Markdown을 수정한 뒤 같은 revision을 다시 발행합니다.
- **임시 실행 제한**: `temporary-discord-bot.yml`은 시간 제한·비영속 실행이며
  상시 운영이나 복구 경로로 간주하지 않습니다.

## 12. 한계, 기술 부채, 다음 단계

| 우선순위 | 항목 | 사용자·운영 영향 | 다음 행동 |
| --- | --- | --- | --- |
| P0 | 저장소 전체 privacy·artifact gate | 문서 검사 밖의 운영 데이터·로컬 산출물 노출 가능성 | 공개 전 추적 파일과 Git 이력 별도 감사 |
| P0 | Python 테스트 CI 부재 | 변경이 main에 들어가도 bot regression을 자동 차단하지 못함 | 현재 15개 테스트를 PR workflow에 연결 |
| P0 | Discord·Docker E2E 부재 | 실제 권한·gateway·volume 실패를 배포 전에 놓칠 수 있음 | test guild와 container smoke test 구성 |
| P1 | Lethal Company fallback 불일치 | fetch 실패 환경에서 다른 가이드가 표시됨 | JSON에서 fallback 생성 또는 equality test |
| P1 | 공유 JSON schema 부재 | bot과 web 중 한 소비자만 깨질 수 있음 | versioned schema와 양쪽 contract test 추가 |
| P1 | Discord 25개 제한 | 일부 몬스터·레코드가 선택 UI에서 잘림 | 검색 우선 UX와 pagination 추가 |
| P1 | 콘텐츠 provenance 부재 | 게임 수치의 최신성·출처를 판단하기 어려움 | source, gameVersion, updatedAt 도입 |
| P1 | 이미지 권리 메타데이터 부재 | 공개 배포의 라이선스 검토가 어려움 | 출처·라이선스 inventory 작성 |
| P2 | health 범위 제한 | 외부 연동과 DB 장애를 ready 신호가 놓침 | dependency health와 운영 지표 분리 |

다음 단일 작업은 P0 privacy·artifact gate입니다. 프로젝트 문서 자동화는
publishable Markdown만 검사하므로, 저장소 전체 공개 범위를 별도로 정리해야
문서와 소스의 개인정보 경계를 함께 유지할 수 있습니다.

## 13. 관련 문서

- [Project Intro](./Project_Intro.md)
- [Deployment](./deployment.md)
- [Privacy](./privacy.html)
- [Terms](./terms.html)
- [Status](./status.html)
- [Project Docs 운영 준비](./Project_Docs_Operations.md)
