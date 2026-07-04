# Workflow: 일일 집밥 트렌드 리포트

## 목표

매일 아침 8시(한국 시간), **"집밥"** 주제로 좁혀서 요리 쇼츠 트렌드를 수집·분석해서:
1. 오늘의 인기 키워드, 주목할 채널을 정리하고
2. 오늘의 콘텐츠 주제 추천(트렌드 기반) + 예시 대본 5개를 만들고
3. 시청자에게 실질적으로 도움되는 주제 5개 + 대본 5개를 만들고
4. 브랜드 PDF 리포트로 만들어 Gmail로 발송하고
5. 채널 데이터를 구글 시트에 매일 누적 기록한다.

이 Workflow는 `workflows/daily_cooking_trend_report.md`(매일 오전 7시, 전체 요리 주제)와 **완전히 별개로 병행 운영**된다. 같은 Tool들을 재사용하지만, 키워드 설정 파일과 Routine이 다르다. 시크릿 처리 방식과 네트워크 제약, 데이터 한계(검색 수요 추정치, 사운드 트렌드 미포함, 초기 성장률 없음)는 `daily_cooking_trend_report.md`와 동일하다.

## 다른 점 (7시 자동화와 비교)

| | 매일 7시 (전체 요리) | 매일 8시 (집밥 전용) |
|---|---|---|
| 키워드 설정 | `tools/config/cooking_keywords.json` | `tools/config/home_cooking_keywords.json` |
| 데이터 출력 | `.tmp/cooking_daily_trends.json` | `.tmp/home_cooking_daily_trends.json` |
| 채널 성장 기록 | 구글 시트 "채널성장추적" 탭 (공유) | 구글 시트 "채널성장추적" 탭 (공유 — 같은 탭을 그대로 씀, 채널이 겹쳐도 문제 없음) |

## 필요한 값

`daily_cooking_trend_report.md`와 완전히 동일한 값을 그대로 쓴다. 추가 시크릿 없음.

## 실행 순서

### ⓪ 사전 점검 (Tool)
```
python tools/check_setup.py
```

### ① 데이터 수집 (Tool)
```
python tools/cooking_daily_trends.py --keywords tools/config/home_cooking_keywords.json --output .tmp/home_cooking_daily_trends.json
```

### ② 채널 성장 기록 + 성장 리포트 (Tool, 두 번 호출)
```
python tools/channel_growth_tracker.py --log --input .tmp/home_cooking_daily_trends.json
python tools/channel_growth_tracker.py --report --input .tmp/home_cooking_daily_trends.json --output .tmp/home_cooking_channel_growth.json
```

### ③ 트렌드 분석 (Agent — 네가 직접 판단)
`.tmp/home_cooking_daily_trends.json`과 `.tmp/home_cooking_channel_growth.json`을 읽고, `.tmp/home_cooking_analysis.json`을 작성한다. 스키마와 판단 기준은 `daily_cooking_trend_report.md`의 ③단계와 동일하다 (`recommendations`/`scripts` = 트렌드·후킹 기반, `helpful_topics`/`helpful_scripts` = 실제 도움되는 요리 지식 기반).

집밥 주제 특성상 다음 패턴이 자주 나올 수 있다 — 발견되면 반영한다:
- **"K-집밥 해외반응" 콘텐츠**: 외국인이 한국 집밥을 접하는 반응 영상이 따로 하나의 카테고리로 자주 등장한다
- **연예인/유명인 + 집밥 결합 포맷**: 연예뉴스와 집밥을 섞은 콘텐츠

### ④ PDF 생성 (Tool, 기존 것 재사용)
```
python tools/generate_daily_cooking_report_pdf.py --input .tmp/home_cooking_analysis.json --output .tmp/home_cooking_report_<YYYY-MM-DD>.pdf
```

### ⑤ 이메일 발송 (Tool)
```
python tools/send_email.py --pdf .tmp/home_cooking_report_<YYYY-MM-DD>.pdf --subject "일일 집밥 트렌드 리포트 (<날짜>)" --body "<analysis.json의 summary 내용>"
```

## 완료 기준

이메일이 실제로 발송된 것을 Tool 출력 메시지로 확인한 뒤 종료. 하나라도 실패하면 어느 단계에서 실패했는지 사람이 이해할 수 있는 말로 사장님께 보고한다.
