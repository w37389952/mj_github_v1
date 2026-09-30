# 작업 현황판

MJ의 모든 작업(코드·수익화)을 한 화면에 모아 보는 페이지다.

- 주소: https://w37389952.github.io/mj_github_v1/dashboard/
- **공개 페이지다.** 주소를 아는 사람은 누구나 볼 수 있다(검색엔진에는 안 뜬다).
  계정 이메일, 기기 이름, 키, 비밀번호, 개인 블로그 주소, 수익 금액은 **적지 않는다.**
- 내용은 전부 `dashboard/data.json` 하나에 있다. `index.html`은 그리는 일만 한다.
- `main`에 올라가면 `deploy.yml`이 1분 안에 배포한다. JSON이 깨져 있으면 배포가 멈추고 이전 화면이 그대로 남는다.

## data.json 구조

```jsonc
{
  "updated": "2026-09-30T15:10:00+09:00",   // 고칠 때마다 지금 시각(한국 시간)으로
  "projects": [
    {
      "id": "tistory",                  // 영문 소문자. tasks·log가 이 값으로 가리킨다
      "name": "티스토리 유용팁 생활노트",
      "group": "수익화",                // "코드" 또는 "수익화"
      "status": "운영 중",              // 운영 중 | 진행 중 | 확인 대기 | 확인 필요 | 막힘 | 기획
      "summary": "한두 문장",
      "link": "https://...",            // 선택
      "progress": 40,                   // 0~100, 또는 아래 goal 중 하나
      "goal": { "label": "애드센스 신청까지 글 수", "current": 7, "target": 20 }
    }
  ],
  "tasks": [
    { "project": "tistory", "title": "할 일", "owner": "MJ",      // "MJ" 또는 "Claude"
      "status": "할 일",                                          // 할 일 | 진행 중 | 막힘 | 완료
      "due": "2026-10-05",                                        // 선택
      "done": "2026-09-30" }                                      // 완료일 때만
  ],
  "log": [
    { "date": "2026-09-30", "project": "tistory", "text": "오늘 한 일 한 문장" }
  ]
}
```

## 다른 창에 붙여 넣을 안내문

아래를 그대로 복사해서 각 Claude 창에 보내면 된다.

```
앞으로 작업을 마칠 때마다(하루 여러 번이어도 됨) 작업 현황판에 오늘 한 일을 올려줘.

- 파일: GitHub w37389952/mj_github_v1 저장소, main 브랜치의 dashboard/data.json
  (규칙은 같은 폴더 README.md에 있음. 처음 한 번 읽어줘.)
- 올리는 법: main에서 파일을 새로 받아서 고친 뒤 main에 바로 커밋해줘.
  PR은 만들지 마. 커밋 메시지는 "현황판: <프로젝트> 갱신".
  GitHub 도구(create_or_update_file)로 해도 되고, 로컬 저장소면 git pull 후 push.
  push가 거절되면 다시 받아서 내 변경만 얹어 다시 올려.
- 고칠 것:
  1) log 맨 앞에 {"date": 오늘 날짜, "project": 이 작업의 id, "text": 한 일 한 문장} 추가
  2) 이 작업의 tasks에서 끝난 건 status를 "완료"로 바꾸고 done 날짜 적기, 새로 생긴 할 일은 추가
     (내가 해야 하는 건 owner "MJ", 네가 할 건 "Claude")
  3) projects에서 이 작업의 status, summary, progress(또는 goal.current)를 지금 상태로
  4) 맨 위 updated를 지금 한국 시각으로
- 이 작업이 projects에 없으면 새로 추가해. id는 영문 소문자, group은 "코드" 또는 "수익화".
- 다른 프로젝트 항목은 건드리지 마.
- 공개 페이지라서 이메일, 기기 이름, 키, 비밀번호, 개인 블로그 주소, 수익 금액은 절대 쓰지 마.
- 저장 전에 JSON이 올바른지 확인해줘.
```
