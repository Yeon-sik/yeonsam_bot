# 연삼이 | Project Detail

2026-10-30 (Asia/Seoul) 갱신. Primary source boundary는 [main@f9a7193](https://github.com/Yeon-sik/yeonsam_bot/tree/f9a719374d0911b529266b7a3d8ea0690b474c20)이다. source 설명과 실제 검증 결과를 구분한다. [빠른 소개](./Project_Intro.md)를 참고한다.

## 1. 문서 목적과 범위

연삼이는 Discord 서버의 신규 멤버 온보딩, Git 기반 게임 가이드, Steam 패치·인기 게임과 여러 플랫폼 무료 배포 알림을 운영하는 Python 봇과 정적 사이트다.

2026-08-12 문서 기준 이후 main에는 Windows 로컬 launcher/admin panel, 실행 스크립트와 무료 게임 feed/alert의 multi-platform 보강이 추가됐다. 실제 Discord 실서버·장기 polling은 별도 검증 경계로 유지한다.

## 2. 시스템 아키텍처

```text
Discord user/admin
  -> bot/main.py
  -> cogs: settings / welcome / guides / free games / steam popular / patch alerts
  -> utils: SQLite / game JSON / provider adapters / validation
  -> Discord response

Windows local operator
  -> RUN_YEONSAM_BOT.cmd / start-bot.bat / PowerShell
  -> scripts/local_launcher.py + admin_panel.html
  -> bot process lifecycle / local settings

Web visitor
  -> GitHub Pages
  -> shared docs/games JSON + JS renderer
```

## 3. 데이터 모델과 불변식

- guild setting·subscription·cursor·metric은 길드 범위를 보존한다.
- secret/API token/실제 운영 서버 식별자는 Git·공개 문서에 저장하지 않는다.
- patch subscription 최초 설정은 최신 글을 cursor로 시드하며 과거 글을 한꺼번에 보내지 않는다.
- 무료 배포는 provider payload를 정규화하고 digest가 달라진 변경분만 서버별로 발송한다.
- provider/API 실패는 해당 경로의 실패로 기록하고 다른 기능 전체의 성공으로 숨기지 않는다.
- SQLite는 현재 단일 프로세스 운영 전제이며 다중 writer 안정성을 주장하지 않는다.
- local launcher/admin panel은 process orchestration 편의 도구이며 Discord gateway의 health authority가 아니다.

## 4. 핵심 기술 의사결정

### 결정 1. 게임 JSON을 봇과 웹이 공유
Discord embed와 GitHub Pages가 같은 콘텐츠 원천을 읽어 이중 편집을 줄인다.

### 결정 2. 외부 공급원은 adapter로 격리
Steam/GamerPower payload parsing과 cache/digest를 UI command 밖으로 분리해 공급원 변경과 실패를 좁힌다.

### 결정 3. 서버별 cursor와 idempotent alert
패치·무료 배포는 마지막 처리 상태를 길드별로 저장해 재시작과 polling에서 중복 발송을 줄인다.

### 결정 4. 로컬 launcher는 운영 보조 계층
Windows에서 bot process와 local admin을 쉽게 관리하되 persistence와 Discord 상태의 진실 원천을 launcher 자체에 두지 않는다.

## 5. 테스트와 검증 전략

| 검사 | 결과 | 근거·환경과 한계 |
| --- | --- | --- |
| 최신 main source 감사 | 저장소 검증 | `main@f9a7193`까지 launcher/admin panel, free-game source, tests와 deployment 문서를 확인했다. |
| 2026-08-12 로컬 검증 | 통과 기록 | Python 3.12.13 unit tests 64개, JSON/정적 계약, 브라우저 렌더와 provider read 기록. 최신 HEAD의 독립 재실행은 아니다. |
| Notion/project-docs 이전 발행 | 통과 기록 | source `4199016` 발행·read-back 기록이 있으나 최신 문서 revision과 분리한다. |
| Discord 실서버 E2E | 미검증 | 실제 gateway, guild permission, slash command, channel send, restart recovery와 장기 polling은 별도다. |
| Docker | 미검증 | image/Compose와 persistent volume을 이번 작업에서 실행하지 않았다. |

## 6. 배포·운영·복구

- Python runtime과 의존성은 저장소가 고정한 환경을 따른다.
- local launcher 경로와 Docker/Pages 경로를 혼동하지 않는다. local launcher 성공은 container/remote 배포 성공이 아니다.
- provider 오류·Discord send 실패 시 cursor/digest를 성공한 범위 이상으로 앞당기지 않는다.
- SQLite 파일은 운영 데이터이므로 공개 Git artifact로 취급하지 않는다.

**문서 발행**: Git Markdown이 canonical이다. main 병합 후 저장소의 project-docs 정책에 따라 검증·발행하며 Notion은 read-only mirror다.

## 7. 한계, 기술 부채, 다음 단계

- Discord 실서버와 외부 provider 장기 polling의 신뢰성은 아직 미검증이다.
- SQLite 단일 프로세스 전제와 local launcher Windows 경로는 수평 확장을 목표로 하지 않는다.
- 다음 우선 작업은 테스트용 Discord 서버에서 onboarding·guide·free-game·patch subscription과 bot restart 후 cursor 복구를 종단 검증하는 것이다.

## 8. 근거와 관련 문서

- [기준 source revision](https://github.com/Yeon-sik/yeonsam_bot/tree/f9a719374d0911b529266b7a3d8ea0690b474c20)
- [Project Intro](./Project_Intro.md)
- [Local bot run](./local-bot-run.md)
- [Deployment](./deployment.md)
- [README](../README.md)
