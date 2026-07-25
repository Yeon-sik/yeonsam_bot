# 연삼이 운영 배포

## 1. 봇 24시간 실행

저장소 루트에서 `.env.example`을 `.env`로 복사하고 `TOKEN`을 입력합니다.

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8080/health
```

`docker-compose.yml`은 다음 운영 조건을 고정합니다.

- 프로세스 종료 시 자동 재시작
- `data/`를 `/app/data`에 연결해 SQLite 설정과 알림 상태 영속 보관
- `/health` 기반 컨테이너 헬스체크
- Steam 공식 업데이트를 기본 30분 간격으로 확인

실제 공개 운영에서는 동일한 Docker 이미지를 상시 실행 가능한 VPS, NAS 또는 컨테이너 호스팅에 배포하고 `/app/data`에 영속 볼륨을 연결해야 합니다.

## 2. 공개 사이트 설정

GitHub 저장소의 `Settings > Secrets and variables > Actions > Variables`에 다음 변수를 등록합니다.

- `DISCORD_APPLICATION_ID`: Discord Developer Portal의 Application ID
- `BOT_HEALTH_URL`: 공개 배포된 봇의 `https://.../health` 주소
- `SUPPORT_SERVER_URL`: 지원 서버 또는 문의 페이지 주소

`Deploy public site` Actions가 이 값을 `docs/assets/site-config.js`에 주입합니다. Application ID는 비밀 값이 아니지만 임의의 ID를 추측해 넣으면 잘못된 봇 설치 화면으로 연결되므로 반드시 Developer Portal 값과 대조합니다.

## 3. Discord 권한

설치 링크는 다음 최소 권한만 요청합니다.

- View Channel
- Send Messages
- Embed Links
- Attach Files
- Manage Nicknames

서버에서는 봇 역할을 닉네임을 변경할 대상 역할보다 위에 배치해야 합니다.

## 4. 첫 설정과 패치 알림

1. `/설정`에서 환영 채널, 문구, 안내 링크를 입력합니다.
2. `권한 진단`을 실행하고 테스트 메시지를 발송합니다.
3. `/패치알림설정`에서 게임과 알림 채널을 선택합니다.
4. `/패치알림테스트`로 현재 최신 공식 업데이트를 확인합니다.

현재 자동 알림 지원 게임은 Lethal Company와 R.E.P.O.입니다. 공급원은 Steamworks의 공개 `ISteamNews/GetNewsForApp/v2` API입니다.
