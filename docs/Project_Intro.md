# 연삼이 | Discord 서버 온보딩과 게임 운영을 연결하는 봇

연삼이는 Discord 서버 관리자가 신규 멤버 안내, 게임 가이드 탐색, Steam 패치·인기 게임·기간 한정 무료 배포 알림을 한곳에서 운영하도록 돕는 Python 봇과 정적 GitHub Pages 사이트다. 게임 JSON은 Discord와 웹이 공유하고 길드별 운영 상태는 SQLite에 저장한다.

| 항목 | 내용 |
| --- | --- |
| 문서 갱신 | 2026-10-30 (Asia/Seoul) |
| 기준 소스 | [main@f9a7193](https://github.com/Yeon-sik/yeonsam_bot/tree/f9a719374d0911b529266b7a3d8ea0690b474c20) |
| 프로젝트 형태 | Python Discord 봇 + 정적 GitHub Pages 사이트 |
| 저장소 | [Yeon-sik/yeonsam_bot](https://github.com/Yeon-sik/yeonsam_bot) |
| 공개 사이트 | [연삼이 GitHub Pages](https://yeon-sik.github.io/yeonsam_bot/) |
| 범위 | 병합된 main source와 저장소 검증 근거. 실제 길드 식별자·운영 메시지·secret은 제외. |

## 1. 30초 요약

- 신규 멤버 안내, 게임 가이드, Steam 패치·인기 게임·무료 배포 공지를 하나의 Discord 봇과 정적 사이트로 연결한다.
- 2026-08-12 문서 기준 이후 Windows 로컬 launcher/admin panel이 추가됐고, 무료 게임 feed의 여러 플랫폼 처리·필터·알림 로직이 보강됐다.
- 저장소와 과거 단위 테스트 기록은 확인했지만 실제 Discord gateway·장기 polling·provider rate limit은 이번 갱신에서 재검증하지 않았다.

## 2. 문제와 해결

**문제**: Discord 서버 관리자는 신규 멤버 안내, 게임 정보 공유, 패치·무료 배포 공지를 서로 다른 채널과 도구에서 반복 관리해야 한다.

**해결**: Discord command/event, Git에서 관리하는 공유 게임 JSON, SQLite guild state와 외부 feed adapter를 한 봇에 묶고, 같은 콘텐츠를 Discord와 GitHub Pages가 함께 소비하도록 구성한다.

## 3. 핵심 기능과 결과

| 영역 | 현재 source에서 확인한 범위 |
| --- | --- |
| 서버 온보딩 | 관리자 채널 선택, 환영 문구·링크, 권한 진단과 테스트 흐름. |
| 게임 가이드 | Git JSON을 Discord 검색/선택 UI와 정적 웹이 공유. |
| 무료 배포 | 여러 플랫폼의 무료 배포 조회, 서버별 구독·digest 비교와 변경분 알림. |
| Steam | 인기 게임 조회와 서버별 공식 뉴스 cursor 기반 패치 알림. |
| 운영 데이터 | guild settings, subscription, cursor, runtime state와 일별 metric을 SQLite로 관리. |
| 로컬 운영 | Windows launcher와 admin panel, PowerShell/BAT 시작 경로로 로컬 bot lifecycle을 관리. |
| 공개 문서 | GitHub Pages로 랜딩·게임 가이드를 배포. |

## 4. 데이터·운영 불변식

- secret과 Discord 실제 서버 식별자를 Git에 저장하지 않는다.
- 길드별 설정·구독·cursor를 다른 길드와 섞지 않는다.
- 최초 패치 subscription은 최신 글을 cursor로 시드해 과거 글 일괄 발송을 피한다.
- 무료 배포 digest가 같으면 중복 알림을 보내지 않는다.
- 외부 provider 실패가 다른 길드·기능 전체를 조용히 성공 처리하게 하지 않는다.
- 로컬 launcher는 편의 도구이며 실제 Discord 연결·장기 운영 성공의 증거가 아니다.

## 5. 검증 현황

| 항목 | 상태 | 근거와 한계 |
| --- | --- | --- |
| 최신 main source | 저장소 검증 | `main@f9a7193`까지 launcher, admin panel, free-game adapter와 관련 tests를 확인했다. |
| 2026-08-12 로컬 검증 | 통과 기록 | Python unit tests 64개, 공유 JSON/정적 계약, 브라우저 렌더와 GamerPower 읽기 확인 기록이 있다. 최신 HEAD 전체를 재실행한 증거로 확대하지 않는다. |
| Discord 실서버 E2E | 미검증 | 실제 gateway, guild permission, command response, 채널 발송과 장기 polling은 이번 갱신에서 실행하지 않았다. |
| Docker 운영 | 미검증 | image/Compose 기동과 persistent volume은 별도 검증 대상이다. |

## 6. 현재 한계와 다음 단계

- 외부 Steam/GamerPower 응답과 rate limit은 장기 실행 환경에서 재확인이 필요하다.
- local launcher/admin panel은 운영 편의성을 높이지만 daemon reliability를 자동으로 보장하지 않는다.
- 다음 우선 검증은 폐기 가능한 Discord 서버에서 onboarding→guide→free-game/patch subscription→restart recovery를 종단 확인하는 것이다.

## 7. 관련 문서

- [프로젝트 상세](./Project_Detail.md)
- [로컬 봇 실행](./local-bot-run.md)
- [배포](./deployment.md)

Git Markdown이 원본이며 Notion은 생성 미러다.
