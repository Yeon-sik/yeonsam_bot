# 연삼이 프로젝트 문서의 Notion 발행 준비

이 저장소는 Git Markdown을 원본으로 유지하고, 검토된 `main` 문서만 전용
Notion 페이지에 미러링합니다. 현재 설정은 수동 승인 방식입니다.

| 설정 | 값 |
| --- | --- |
| 기준 브랜치 | `main` |
| 발행 모드 | `manual` |
| GitHub Environment | `notion-production` |
| 소개 문서 키 | `intro` |
| 상세 문서 키 | `detail` |

## 1. 사용자에게 남은 최초 1회 설정

1. Notion internal integration을 만들고 콘텐츠 읽기·수정 권한을 부여합니다.
2. `프로젝트 소개`, `프로젝트 상세` 전용 빈 페이지를 각각 만듭니다.
3. 두 페이지를 integration에 공유합니다.
4. GitHub 저장소의 Settings → Environments에서 `notion-production`을 만듭니다.
5. 배포 브랜치를 `main`으로 제한하고 required reviewer를 설정합니다.
6. Environment Secrets에 다음 값을 추가합니다.

| Secret 이름 | 값 |
| --- | --- |
| `NOTION_TOKEN` | Notion internal integration token |
| `NOTION_PAGE_IDS_JSON` | `intro`, `detail` 키와 페이지 ID의 JSON 매핑 |

페이지 매핑 형식은 다음과 같습니다.

```json
{"intro":"소개 페이지의 32자리 ID","detail":"상세 페이지의 32자리 ID"}
```

실제 token과 page ID는 저장소 파일, Markdown, 이슈, 채팅에 붙여 넣지 않습니다.

## 2. 키 입력 전 로컬 검증

```powershell
node .github/project-docs/validate-project-docs.mjs `
  --config project-docs.config.json `
  --require-tracked

node .github/project-docs/sync-project-docs-to-notion.mjs `
  --config project-docs.config.json
```

두 번째 명령은 render-only dry-run입니다. 로컬에서 `--apply`를 추가하지 않습니다.

## 3. 최초 발행

기능 브랜치의 전체 변경을 검토하고 `main`에 병합한 다음 진행합니다.

### GitHub Actions 화면

1. `Validate and publish project docs` workflow를 엽니다.
2. `operation=validate`로 실행하고 성공을 확인합니다.
3. 다시 실행해 `operation=publish`를 선택합니다.
4. confirmation에 대문자 `PUBLISH`를 입력합니다.
5. `notion-production` Environment 승인을 완료합니다.

### GitHub CLI

CLI를 사용할 경우 먼저 인증 상태를 확인합니다.

```powershell
gh auth status
gh workflow run project-docs-notion.yml --ref main -f operation=validate
gh run watch
gh workflow run project-docs-notion.yml --ref main `
  -f operation=publish `
  -f confirmation=PUBLISH
gh run watch
```

인증이 만료됐다면 `gh auth login -h github.com`으로 다시 연결하거나 GitHub
Actions 화면을 사용합니다.

## 4. 성공 확인

- Actions validation과 publish job이 모두 성공했는지 확인합니다.
- 소개·상세 페이지 상단의 source revision 링크와 fingerprint를 확인합니다.
- 두 페이지 내용이 Git Markdown과 일치하는지 확인합니다.
- 전용 미러 페이지에는 수동 메모, child page, database를 두지 않습니다.

## 5. 실패 시 복구

- **페이지 접근 실패**: integration 공유와 page ID 매핑을 수정한 뒤 재실행합니다.
- **사전 점검 실패**: 아무 페이지도 쓰지 않은 상태이므로 원인을 수정합니다.
- **일부 발행 실패**: Notion에서 직접 고치지 말고 같은 Git revision을 재실행합니다.
- **잘못된 내용**: Git Markdown을 수정·검토한 뒤 새 revision을 발행합니다.
- **token 노출**: 즉시 폐기하고 새 token으로 Environment Secret을 교체합니다.
