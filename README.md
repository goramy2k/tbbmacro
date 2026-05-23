# 한국 매크로 모니터

8대 거시지표를 매일 자동 수집해 시장 건전성을 점수화하는 대시보드.

## 구성 파일

| 파일 | 역할 |
|------|------|
| `index.html` | 대시보드 앱 (브라우저에서 실행) |
| `data.json` | 지표 데이터 (자동 생성·갱신) |
| `scraper.py` | 지표 수집 스크립트 |
| `manual_overrides.json` | 수동 입력 지표값 (BBB-/CP/CDS/반도체수출) |
| `.github/workflows/update.yml` | 매일 자동 실행 설정 |

## 자동 업데이트 구조

매일 한국시간 17:00 (장 마감 후), GitHub Actions가 `scraper.py`를 실행한다.

- 자동 수집 (네이버 증권): VKOSPI, USD/KRW, 외국인 수급, 국고채 금리
- 수동 관리 (`manual_overrides.json`): BBB- 스프레드, CP 스프레드, CDS, 반도체 수출 YoY

수집 결과는 `data.json`에 저장되고 저장소에 자동 커밋된다. 앱은 `data.json`을 읽어 표시한다.

## 설치 (처음 1회)

1. GitHub 계정 생성 후 새 저장소(public) 생성
2. 이 폴더의 모든 파일을 업로드
3. 저장소 Settings → Pages → Branch를 `main`으로 지정 → Save
4. Settings → Actions → General → Workflow permissions를
   "Read and write permissions"로 설정
5. `https://<사용자명>.github.io/<저장소명>` 으로 접속

## 운영

- 매주 1회: `manual_overrides.json`을 열어 BBB-/CP/CDS 값을 갱신
  (KOFIA kofiabond.or.kr, Investing.com 등에서 확인)
- 자동 수집이 실패하면 대시보드 상단에 경고가 표시됨
  → 네이버 페이지 구조 변경 가능성, `scraper.py` 점검 필요
- Actions 탭에서 "지표 자동 업데이트" → "Run workflow"로 즉시 실행 가능

## AI 해석 기능 (선택)

`index.html` 상단 `ANTHROPIC_API_KEY`에 키를 입력하면 카드별 AI 분석이 작동한다.
공개 저장소에 키를 올리면 노출되므로, AI 기능은 본인 로컬에서만 쓰거나
별도 백엔드를 두는 것을 권장한다.

## 주의

- 스크래핑은 대상 사이트의 HTML 구조에 의존하므로 영구 보장되지 않는다.
- 네이버 등은 스크래핑을 공식 지원하지 않는다. 과도한 호출은 피한다.
- 본 도구는 투자 참고용이며 투자 권유가 아니다.
