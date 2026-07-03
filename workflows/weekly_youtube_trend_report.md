# Workflow: 주간 유튜브 트렌드 리포트

## 목표

매주 월/수/금/일 오전 7시(한국 시간), "수익성 브랜드 / 콘텐츠 수익화 / 1인 사업 런칭" 분야 유튜브 트렌드를 수집·분석해서:
1. 브랜드 PDF 리포트(인기 주제, 포맷 분석, 이번 주 콘텐츠 주제 추천)를 만들고
2. Gmail로 발송하고
3. 분석 데이터를 구글 시트에 누적 기록한다.

이 Workflow는 클라우드 Routine(`/schedule`)으로 실행되는 것을 전제로 한다. Routine은 매 실행마다 이 저장소를 새로 clone하므로, 로컬 `.env`/`credentials.json`은 존재하지 않는다 — Routine의 실행 프롬프트 안에 이 값들을 직접 넣어서 세션 시작 시 `.env`와 `credentials.json`을 만들도록 지시해야 한다 (claude.ai에 별도로 환경변수를 등록하는 화면이 없기 때문).

**중요 — 왜 노션이 아니라 구글 시트이고, SMTP가 아니라 Gmail API인가:** 클라우드 Routine 실행 환경의 네트워크 정책이 `googleapis.com` 계열 주소만 허용하고, `notion.com`이나 SMTP(raw TCP 소켓) 연결은 차단한다. 그래서 데이터 저장은 노션 대신 구글 시트로, 이메일은 SMTP 대신 Gmail API(OAuth)로 바꿨다. 로컬(사장님 PC)에서 실행할 때는 이 제약이 없어서 노션/SMTP도 원래 잘 됐었다.

## 필요한 값 (Routine 프롬프트에 직접 포함되어 있음)

| 이름 | 용도 |
|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API v3 호출 |
| `EMAIL_ADDRESS` | 발신/수신 기본 Gmail 주소 |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` / `GOOGLE_OAUTH_REFRESH_TOKEN` | Gmail API 발송용 OAuth (최초 1회 `tools/_oauth_setup_gmail.py`로 발급) |
| `REPORT_RECIPIENT_EMAIL` | 수신 이메일 (비워두면 발신자 자신에게 발송) |
| `GOOGLE_SHEET_ID` | 기록할 구글 시트 ID |
| `credentials.json` (파일) | 구글 시트용 서비스 계정 키 |

## 실행 순서

### ⓪ 사전 점검 (Tool)
```
python tools/check_setup.py
```
필요한 키/토큰이 다 준비됐는지 먼저 확인한다. 여기서 실패하면(exit code 1) 바로 중단하고, 뭐가 비어있는지 사장님께 명확히 보고한다 — "PDF가 안 생겼다" 같은 모호한 보고 대신 "NOTION_TOKEN이 비어있어서 실행이 안 됐다"처럼 정확히 말한다.

### ① 데이터 수집 (Tool)
```
python tools/youtube_trends.py --output .tmp/youtube_trends.json
```
`tools/config/youtube_keywords.json`의 키워드로 최근 영상을 검색하고, 조회수/좋아요/영상길이/자막을 모은 원본 JSON을 만든다. 이 단계는 분석하지 않는다 — 순수 데이터 수집.

**실패 시:**
- `YOUTUBE_API_KEY` 관련 401/403 에러 → 키가 잘못됐거나 YouTube Data API v3가 활성화 안 된 것. 사장님께 알리고 중단.
- 쿼터 초과(403 quotaExceeded) → 다음 날 자정(태평양시)까지 기다려야 함. 이번 주는 건너뛰고 사장님께 보고.
- 자막 수집 실패는 개별 영상 단위로 무시하고 계속 진행 (에러 아님, `transcript_snippet`이 `null`로 남을 뿐).

### ② 트렌드 분석 (Agent — 네가 직접 판단)
`.tmp/youtube_trends.json`을 읽고, 다음을 판단해서 `.tmp/analysis.json`을 직접 작성한다 (Tool이 아니라 네 판단으로):

- **인기 주제 Top 5~8개**: 제목과 자막(`transcript_snippet`)을 보고 비슷한 주제끼리 그룹핑, 각 그룹의 총 조회수와 예시 제목 정리
- **포맷 분석**: `is_short`로 Shorts와 롱폼을 나눠서 각각 평균 조회수/영상 수 비교, 어느 쪽이 더 잘 되는지 한두 문장으로 설명
- **이번 주 콘텐츠 주제 추천 3~5개**: 이번 주 뜨는 주제/포맷을 참고해서, "수익성 브랜드/콘텐츠 수익화/1인 사업" 채널이 만들면 좋을 구체적인 콘텐츠 주제와 그 이유
- **전체 요약**: 2~3문장

`generate_report_pdf.py`와 `sheets_logger.py`가 요구하는 정확한 JSON 스키마는 `tools/generate_report_pdf.py` 상단 docstring을 참고할 것. 스키마를 벗어나면 두 Tool 모두 조용히 빈 섹션을 만들거나 에러를 낼 수 있으니 필드명을 정확히 맞춘다.

### ③ PDF 생성 (Tool)
```
python tools/generate_report_pdf.py --input .tmp/analysis.json --output .tmp/report_<YYYY-WW>.pdf
```

### ④ 이메일 발송 (Tool)
```
python tools/send_email.py --pdf .tmp/report_<YYYY-WW>.pdf --subject "주간 유튜브 트렌드 리포트 (<주차>)" --body "<analysis.json의 summary 내용>"
```
**실패 시:** 401/invalid_grant 에러 → refresh_token이 만료됐거나 OAuth 동의 화면이 "테스트 중" 상태에서 7~14일 지난 것. 사장님께 OAuth 동의 화면을 "프로덕션"으로 게시하거나 `tools/_oauth_setup_gmail.py`를 다시 실행해 토큰을 재발급해달라고 요청.

### ⑤ 구글 시트 기록 (Tool)
```
python tools/sheets_logger.py --input .tmp/analysis.json
```
**실패 시:** 403/404 에러 → 시트가 `credentials.json` 안의 `client_email`과 "편집자"로 공유되어 있지 않은 것. 사장님께 구글 시트 공유 설정을 확인해달라고 요청.

## 완료 기준

이메일이 실제로 발송되고 구글 시트에 새 행이 추가된 것을 각 Tool의 출력 메시지로 확인한 뒤 종료. 하나라도 실패하면 어느 단계에서 실패했는지, 원인이 뭔지 사람이 이해할 수 있는 말로 사장님께 보고한다 (에러 메시지 그대로 던지지 말 것).

## 알아둘 점

- 유튜브 채널은 고정 리스트가 아니라 매주 키워드 검색으로 자동 발견된다. 결과가 매주 조금씩 달라지는 게 정상이다.
- 이 파일이나 `tools/config/youtube_keywords.json`은 반복되는 문제를 겪을 때마다 업데이트해서, 같은 실패가 두 번 다시 발생하지 않게 한다.
