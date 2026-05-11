# 무료 운영 임시안

Oracle Cloud Free Tier 승인이 안 나는 동안에는 아래 순서로 운영하는 편이 가장 현실적입니다.

## 1순위: 내 PC / NAS / 미니PC에서 상시 실행

- 장점: 완전 무료, Discord 봇에 필요한 상시 연결 유지가 가장 안정적임
- 장점: 현재 JSON 저장 구조를 그대로 써도 됨
- 단점: 내 장비가 켜져 있어야 함
- 전제: Python 3.11 이상이 설치되어 있어야 함

실행:

```powershell
$env:TOKEN="디스코드_봇_토큰"
powershell -ExecutionPolicy Bypass -File .\scripts\run-bot.ps1
```

데이터는 기본적으로 `data/guild_config.json` 에 저장됩니다.

## 2순위: GitHub Actions로 임시 실행

- 파일: `.github/workflows/temporary-discord-bot.yml`
- 용도: 데모, 테스트, 짧은 기간 임시 운영
- 주의: GitHub Hosted Runner는 한 번에 최대 6시간까지만 실행 가능
- 주의: 저장소가 비공개면 GitHub Actions 무료 분 한도를 빨리 소모할 수 있음

사용 방법:

1. GitHub 저장소 `Settings > Secrets and variables > Actions` 로 이동
2. `TOKEN` 시크릿 추가
3. `Actions > Temporary Discord Bot > Run workflow` 실행
4. `duration_minutes` 는 보통 `350` 유지

## 왜 이 방향을 골랐는가

- Koyeb 무료 인스턴스는 웹 서비스 중심이고, 유휴 시 scale-to-zero 제약이 있어 Discord 봇 상시 연결용으로는 불리함
- Railway 무료 크레딧은 아주 작은 실험용에 가깝고 상시 봇에는 여유가 적음
- 지금 코드 구조는 웹 요청형 서버가 아니라 장시간 연결되는 워커형 프로세스에 가깝기 때문에, 임시로는 로컬 실행이 가장 적합함
