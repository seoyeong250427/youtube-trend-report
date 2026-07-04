# Workflow: 일일 요리 쇼츠 트렌드 리포트

## 목표

매일 아침 7시(한국 시간), 요리 쇼츠 분야 트렌드를 수집·분석해서:
1. 오늘의 인기 키워드, 주목할 채널을 정리하고
2. 오늘의 콘텐츠 주제 추천 + 예시 대본 5개를 만들고
3. 브랜드 PDF 리포트로 만들어 Gmail로 발송하고
4. 채널 데이터를 구글 시트에 매일 누적 기록한다 (며칠 후부터 실제 성장률 계산 가능해짐).

이 Workflow는 클라우드 Routine(`/schedule`)으로 실행되는 것을 전제로 한다. 시크릿 처리 방식과 네트워크 제약은 `workflows/weekly_youtube_trend_report.md`와 동일하다 (Notion 대신 구글 시트, SMTP 대신 Gmail API).

## 데이터 한계 (있는 척 하지 않을 것)

- **"검색 수요"는 실제 검색량이 아니다** — 유튜브 조회수를 대신 쓰는 추정치. 리포트에 반드시 이 사실을 명시한다.
- **사운드/음악 트렌드는 수집하지 않는다** — 유튜브 공식 API가 이 데이터를 제공하지 않는다. 지어내지 말고 생략한다.
- **"주목할 채널"의 정확한 성장률(%)은 초기에 없다** — `channel_growth_tracker.py`가 최소 하루 이상 지난 기록이 있어야 계산 가능하다. 그전까지는 "구독자 대비 조회수 비율이 이례적으로 높은 채널"을 대체 신호로 쓴다 (이 경우도 "추정 신호"라고 리포트에 명시).

## 필요한 값 (Routine 프롬프트에 직접 포함)

`workflows/weekly_youtube_trend_report.md`와 동일한 값을 그대로 쓴다: `YOUTUBE_API_KEY`, `EMAIL_ADDRESS`, `GOOGLE_OAUTH_CLIENT_ID`/`SECRET`/`REFRESH_TOKEN`, `REPORT_RECIPIENT_EMAIL`, `GOOGLE_SHEET_ID`, `credentials.json`. 별도로 추가할 시크릿은 없다.

## 실행 순서

### ⓪ 사전 점검 (Tool)
```
python tools/check_setup.py
```

### ① 데이터 수집 (Tool)
```
python tools/cooking_daily_trends.py --output .tmp/cooking_daily_trends.json
```
`tools/config/cooking_keywords.json`의 키워드로 최근 3일(기본값) 요리 영상을 검색하고, 영상 원본 데이터 + 채널별 집계를 만든다. 분석하지 않는다 — 순수 데이터 수집.

### ② 채널 성장 기록 + 성장 리포트 (Tool, 두 번 호출)
```
python tools/channel_growth_tracker.py --log --input .tmp/cooking_daily_trends.json
python tools/channel_growth_tracker.py --report --input .tmp/cooking_daily_trends.json --output .tmp/channel_growth.json
```
첫 번째 명령으로 오늘 데이터를 구글 시트 "채널성장추적" 탭에 기록하고, 두 번째 명령으로 과거 기록과 비교해 실제 성장률을 계산한다. `has_historical_data`가 `false`면 아직 비교할 과거 데이터가 없다는 뜻 — 이 경우 ③단계에서 "구독자 대비 조회수 비율" 방식으로 대체한다.

### ③ 트렌드 분석 (Agent — 네가 직접 판단)
`.tmp/cooking_daily_trends.json`과 `.tmp/channel_growth.json`을 읽고, 다음을 판단해서 `.tmp/analysis.json`을 직접 작성한다:

- **오늘의 인기 키워드**: `matched_keywords` 빈도 집계 (상위 5~8개)
- **주목할 채널**: `channel_growth.json`에 실제 성장 채널이 있으면 그걸 우선 쓰고, 없으면(`has_historical_data: false`) `channels_ranked_by_window_views`에서 "구독자 대비 기간내조회수 비율"이 높은 채널 2~3개를 골라 대체 신호로 제시 — 반드시 "실제 성장률 아님, 추정 신호"라고 명시
- **오늘의 콘텐츠 주제 추천 3~5개**: 오늘 데이터에서 실제로 반복되는 패턴(키워드, 제목 후킹 방식, 포맷)을 근거로
- **예시 대본 5개**: 60초 기준 4단 구조(0-3초 훅 → 3-10초 상황 → 10-50초 과정 → 50-60초 반응). 추천 주제와 연결되게 작성
- **전체 요약**: 2~3문장, 데이터 한계 caveat 포함

`generate_daily_cooking_report_pdf.py`가 요구하는 정확한 JSON 스키마는 그 파일 상단 docstring과 `.tmp/cooking_daily_analysis.json`(예시)을 참고한다.

### ④ PDF 생성 (Tool)
```
python tools/generate_daily_cooking_report_pdf.py --input .tmp/analysis.json --output .tmp/report_<YYYY-MM-DD>.pdf
```

### ⑤ 이메일 발송 (Tool)
```
python tools/send_email.py --pdf .tmp/report_<YYYY-MM-DD>.pdf --subject "일일 요리 쇼츠 트렌드 리포트 (<날짜>)" --body "<analysis.json의 summary 내용>"
```

## 완료 기준

이메일이 실제로 발송된 것을 Tool 출력 메시지로 확인한 뒤 종료. 하나라도 실패하면 어느 단계에서 실패했는지, 원인이 뭔지 사람이 이해할 수 있는 말로 사장님께 보고한다.

## 알아둘 점

- 매일 실행되므로 `lookback_days`(기본 3일)와 겹치는 기간의 데이터가 매일 조금씩 중복될 수 있다 — 정상이다.
- `tools/config/cooking_keywords.json`은 반복되는 문제나 새로 뜨는 트렌드 카테고리를 발견할 때마다 업데이트한다.
- 채널 성장 기록이 몇 주 쌓이면, `channel_growth_tracker.py`의 `GROWTH_THRESHOLD_PCT` 기준을 사장님과 상의해서 조정할 수 있다.
