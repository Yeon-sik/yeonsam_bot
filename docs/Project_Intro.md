# 연삼이 | Discord 서버 온보딩과 협동 게임 가이드를 연결하는 운영 봇

> 연삼이는 Discord 서버 관리자가 신규 멤버 안내, 게임 가이드 탐색, 공식 패치 알림을
> 한곳에서 운영하도록 돕는 Python 봇과 정적 문서 사이트입니다. Git으로 관리되는 게임
> JSON을 Discord와 웹이 함께 사용하고, 서버별 운영 상태는 SQLite에 분리해 저장합니다.

| 항목 | 내용 |
| --- | --- |
| 개발 기간 | 2026-05 ~ 진행 중 |
| 프로젝트 형태 | Python Discord 봇 + 정적 GitHub Pages 사이트 |
| 현재 상태 | MVP, 공개 문서 사이트 운영 확인 / Discord 실운영 상태 미검증 |
| 문서 기준 | 제품 기능 `d000f83`, 문서 자동화 `feat/project-docs-notion`, 2026-07-27 |
| 주요 기술 | Python, discord.py 2.7.1, SQLite, HTML/CSS/JavaScript, GitHub Actions, Docker |
| 공개 사이트 | [연삼이 GitHub Pages](https://yeon-sik.github.io/yeonsam_bot/) |
| 저장소 | [Yeon-sik/yeonsam_bot](https://github.com/Yeon-sik/yeonsam_bot) |
| 상세 문서 | [Project_Detail.md](./Project_Detail.md) |

---

## 1. 30초 요약

- **문제**: Discord 서버 관리자는 신규 멤버 안내, 게임 정보 공유, 업데이트 공지를
  서로 다른 채널과 도구에서 반복해서 관리해야 합니다.
- **해결**: 관리자용 설정 UI, 신규 멤버 환영 흐름, JSON 기반 게임 가이드, 서버별
  Steam 패치 알림을 하나의 Discord 봇으로 연결했습니다.
- **핵심 결과**: 저장소 기준 단위 테스트 15개가 통과했고, 세 게임 가이드 페이지를
  포함한 공개 GitHub Pages가 HTTP 200으로 응답했습니다.
- **기술적 차별점**: 같은 게임 JSON을 Discord와 정적 사이트가 함께 사용하며,
  길드별 설정·구독·운영 지표는 SQLite로 분리했습니다.

## 2. 문제와 해결

| 사용자 문제 | 해결 방식 | 사용자에게 주는 가치 |
| --- | --- | --- |
| 신규 멤버 안내가 서버 기본 채널과 수작업에 의존함 | `/설정`에서 환영 채널·문구·링크를 저장하고 권한 진단과 테스트 발송 제공 | 서버마다 필요한 온보딩 흐름을 관리자가 직접 구성 |
| 긴 게임 정보를 Discord 메시지로 반복 작성해야 함 | 공용 JSON을 검색·선택형 Discord UI와 웹 페이지로 렌더링 | 채팅 안에서 빠르게 찾고, 상세 내용은 링크로 공유 |
| 공식 업데이트를 관리자가 직접 확인해 전달해야 함 | Lethal Company와 R.E.P.O.의 Steam 공식 뉴스 cursor를 서버별로 추적 | 이미 본 글을 반복 발송하지 않고 지정 채널에 새 글 전달 |
| 운영 설정과 상태가 단일 JSON에 섞이기 쉬움 | SQLite에 설정·구독·runtime state·일별 지표를 분리 | 서버별 데이터 수명주기와 원자적 지표 집계를 명시적으로 관리 |

## 3. 핵심 기능과 결과

| 영역 | 구현 결과 | 근거 |
| --- | --- | --- |
| 서버 온보딩 | 관리자 채널 선택, 문구·링크 입력, 권한 진단, 테스트 발송 | [settings.py](../bot/cogs/settings.py), [welcome.py](../bot/cogs/welcome.py) |
| 게임 가이드 | Lethal Company, R.E.P.O., Thunderstore 콘텐츠를 Discord와 웹에 제공 | [game_content.py](../bot/utils/game_content.py), [game-page.js](./assets/game-page.js) |
| 항목 검색 | 게임·주제·몬스터·레코드를 검색하고 선택형 UI로 탐색 | [yeonsam.py](../bot/cogs/yeonsam.py) |
| 패치 알림 | 서버별 게임·채널 구독과 Steam 새 글 cursor 처리 | [patch_alerts.py](../bot/cogs/patch_alerts.py), [patch_feed.py](../bot/utils/patch_feed.py) |
| 데이터 저장 | 길드 설정, 일별 지표, 패치 구독, runtime state를 SQLite로 관리 | [storage.py](../bot/utils/storage.py) |
| 공개 문서 | 랜딩·정책·상태·세 게임 가이드를 GitHub Pages로 배포 | [deploy-pages.yml](../.github/workflows/deploy-pages.yml) |
| 운영 경로 | Docker 영속 볼륨과 `/health`, 수동 임시 Actions 실행 경로 선언 | [Dockerfile](../Dockerfile), [deployment.md](./deployment.md) |

게임 콘텐츠의 저장소 기준 규모는 Lethal Company 몬스터 33개, R.E.P.O.
몬스터 29개, Thunderstore 단계 카드 10개입니다. 이 수치는 데이터 파일 구조를
센 결과이며 실제 사용자 이용량이나 콘텐츠 정확성 지표가 아닙니다.

## 4. 구현 범위

- **Discord 애플리케이션**: slash command 등록, persistent view, 길드 이벤트,
  오류·완료 지표 수집을 구현했습니다.
- **서버 설정**: 관리자가 환영 채널·문구·링크를 구성하고 실제 발송 전 권한을
  확인할 수 있습니다.
- **가이드 탐색**: `docs/games` 아래 JSON을 읽어 Discord embed와 정적 웹
  카드로 변환합니다.
- **패치 알림**: 공개 Steam News API를 읽고 길드별 마지막 글 cursor 이후의
  새 항목만 전달하도록 구성했습니다.
- **저장소**: 기존 JSON 설정을 SQLite로 한 번 이관하고, 길드 제거 시 해당
  길드의 설정·구독·지표를 삭제합니다.
- **배포 기반**: GitHub Pages, Docker/Compose, 시간 제한 수동 Actions 경로를
  제공합니다.

개인별 메시지 내용이나 실제 서버 식별자는 이 공개 문서의 근거와 결과에서
제외했습니다.

## 5. 핵심 사용자 흐름

```text
관리자
  → /설정
  → 환영 채널·문구·링크 저장
  → 권한 진단
  → 테스트 발송
  → 신규 멤버 환영 흐름 사용

서버 사용자
  → /도움 또는 항목검색
  → 게임·주제·항목 선택
  → Discord 요약 확인
  → 공개 웹 가이드로 상세 내용 확인

관리자
  → 패치 알림 게임·채널 설정
  → Steam 공식 뉴스 확인
  → 새 글만 지정 채널로 전달
```

## 6. 핵심 기술 판단

### Git JSON을 봇과 웹의 공용 콘텐츠 원천으로 사용

- **상황**: 동일한 게임 가이드를 Discord와 웹에서 각각 관리하면 내용이 쉽게
  어긋납니다.
- **선택**: 게임별 JSON을 Git에서 관리하고 Python과 JavaScript가 함께 읽도록
  구성했습니다.
- **결과**: 한 번의 콘텐츠 변경으로 두 UI를 갱신할 수 있습니다.
- **비용**: 정식 JSON schema가 없고 일부 HTML fallback이 복제되어 있어,
  schema 변경 시 봇·웹·fallback을 함께 검증해야 합니다.

## 7. 검증 현황

| 검증 항목 | 상태 | 확인 시각 | 근거와 경계 |
| --- | --- | --- | --- |
| Python 단위 테스트 | 통과 | 2026-07-27 KST | Python 3.12.13, `python -m unittest discover -s tests -v`, 15개 |
| JavaScript 문법 | 통과 | 2026-07-27 KST | `site.js`, `game-page.js`에 `node --check` |
| 게임 JSON 파싱 | 통과 | 2026-07-27 KST | 게임 JSON 3개와 project-docs JSON 2개 파싱 |
| 정적 링크·미디어 | 통과 | 2026-07-26 KST | HTML 상대 링크 누락 0, JSON 참조 미디어 75개 누락 0 |
| 공개 사이트 | 응답 확인 | 2026-07-26T15:05:35Z | 랜딩과 세 게임 페이지 HTTP 200 |
| 프로젝트 문서 | 통과 | 2026-07-27 KST | validator 0 errors·0 warnings, Notion render-only dry-run 성공 |
| Discord 실서버 E2E | 미검증 | 2026-07-27 KST | 실제 gateway, 명령 동기화, 메시지 발송을 실행하지 않음 |
| Steam 실통신 | 미검증 | 2026-07-27 KST | synthetic payload 테스트만 수행 |
| Docker 실행 | 미검증 | 2026-07-27 KST | 현재 환경에서 Docker image/Compose를 실행하지 못함 |

위 검증은 기능 구현과 로컬 계약을 확인한 결과입니다. 실제 Discord 운영 서버 수,
사용자 수, 알림 발송량, 성능이나 장애율을 증명하지 않습니다.

## 8. 현재 한계와 다음 단계

- Discord select 제한 때문에 25개를 넘는 몬스터·레코드는 선택 UI 한 화면에
  모두 노출되지 않습니다. 검색과 pagination 경계를 보강해야 합니다.
- Lethal Company HTML의 inline fallback과 외부 JSON 일부가 일치하지 않습니다.
  fallback 자동 생성 또는 동등성 테스트가 필요합니다.
- 공유 게임 JSON에 정식 schema, 출처, 게임 버전, 갱신일 필드가 없습니다.
- Python 단위 테스트를 자동 실행하는 CI와 Discord test guild E2E가 없습니다.
- Docker build, persistent volume, health check를 실제 컨테이너에서 확인해야 합니다.
- 게임 이미지의 라이선스·출처 메타데이터를 별도로 정리해야 합니다.
- 시간 제한 GitHub Actions 실행은 상시 운영 경로가 아니며, 운영 환경에는
  영속 데이터 볼륨과 별도 관찰 체계가 필요합니다.

## 9. 관련 문서

- [Project Detail](./Project_Detail.md): 아키텍처, 데이터 경계, 기술 판단과 검증
- [Deployment](./deployment.md): Docker, 공개 사이트 설정과 운영 절차
- [Privacy](./privacy.html): 저장 데이터와 삭제 정책
- [Terms](./terms.html): 서비스 범위와 책임 제한
