# Workflow: 주간 유튜브 트렌드 리포트

## 목표

매주 일요일 저녁 8시(한국 시간), "수익성 브랜드 / 콘텐츠 수익화 / 1인 사업 런칭" 분야 유튜브 트렌드를 수집·분석해서:
1. 브랜드 PDF 리포트(인기 주제, 포맷 분석, 이번 주 콘텐츠 주제 추천)를 만들고
2. Gmail로 발송하고
3. 분석 데이터를 노션 데이터베이스에 누적 기록한다.

이 Workflow는 클라우드 Routine(`/schedule`)으로 실행되는 것을 전제로 한다. Routine은 매 실행마다 이 저장소를 새로 clone하므로, 로컬 `.env`는 존재하지 않는다 — 아래 "필요한 환경변수"는 claude.ai Settings → Environments의 Environment variables에 등록되어 있어야 한다.

## 필요한 환경변수

| 이름 | 용도 |
|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API v3 호출 |
| `EMAIL_ADDRESS` | 발신 Gmail 주소 |
| `EMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 (16자리) |
| `REPORT_RECIPIENT_EMAIL` | 수신 이메일 (비워두면 발신자 자신에게 발송) |
| `NOTION_TOKEN` | Notion Integration 토큰 |
| `NOTION_DATABASE_ID` | 기록할 Notion 데이터베이스 ID |

## 실행 순서

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

`generate_report_pdf.py`와 `notion_logger.py`가 요구하는 정확한 JSON 스키마는 `tools/generate_report_pdf.py` 상단 docstring을 참고할 것. 스키마를 벗어나면 두 Tool 모두 조용히 빈 섹션을 만들거나 에러를 낼 수 있으니 필드명을 정확히 맞춘다.

### ③ PDF 생성 (Tool)
```
python tools/generate_report_pdf.py --input .tmp/analysis.json --output .tmp/report_<YYYY-WW>.pdf
```

### ④ 이메일 발송 (Tool)
```
python tools/send_email.py --pdf .tmp/report_<YYYY-WW>.pdf --subject "주간 유튜브 트렌드 리포트 (<주차>)" --body "<analysis.json의 summary 내용>"
```
**실패 시:** SMTP 인증 실패(535) → 앱 비밀번호가 만료/변경됐을 가능성. 사장님께 재발급 요청 필요, 이번 주는 리포트를 `.tmp/`에 남겨두고 실패를 보고.

### ⑤ 노션 기록 (Tool)
```
python tools/notion_logger.py --input .tmp/analysis.json
```
**실패 시:** "object not found" 에러 → 데이터베이스에 Integration이 연결(공유)되어 있지 않은 것. 사장님께 노션에서 Connections 설정을 확인해달라고 요청.

## 완료 기준

이메일이 실제로 발송되고 노션에 새 행이 추가된 것을 각 Tool의 출력 메시지로 확인한 뒤 종료. 하나라도 실패하면 어느 단계에서 실패했는지, 원인이 뭔지 사람이 이해할 수 있는 말로 사장님께 보고한다 (에러 메시지 그대로 던지지 말 것).

## 알아둘 점

- 유튜브 채널은 고정 리스트가 아니라 매주 키워드 검색으로 자동 발견된다. 결과가 매주 조금씩 달라지는 게 정상이다.
- 이 파일이나 `tools/config/youtube_keywords.json`은 반복되는 문제를 겪을 때마다 업데이트해서, 같은 실패가 두 번 다시 발생하지 않게 한다.
