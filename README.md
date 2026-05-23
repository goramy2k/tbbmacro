# 한국·미국 매크로 모니터

한국 8개 + 미국 8개(+CPI/PPI) 거시지표를 매일 자동 수집해
시장 건전성을 점수화하는 대시보드.

## 구성 파일

| 파일 | 역할 |
|------|------|
| `index.html` | 대시보드 앱 (한국/미국/통합 탭) |
| `data.json` | 지표 데이터 (자동 생성·갱신) |
| `scraper.py` | 지표 수집 스크립트 |
| `manual_overrides.json` | 수동 입력 지표값 (한국 BBB-/CP/CDS/반도체수출) |
| `.github/workflows/update.yml` | 매일 자동 실행 설정 |

## 지표 구성

### 한국 (8개)
- 자동 (네이버): VKOSPI, USD/KRW, 외국인 수급, 국고채 10Y-2Y
- 수동 (`manual_overrides.json`): BBB- 스프레드, CP 스프레드, CDS, 반도체 수출 YoY

### 미국 (8개 카드 + CPI/PPI 배너)
- 자동 (FRED API): VIX, HY 스프레드, WTI, 브렌트유, 미국 2Y/10Y/30Y,
  장단기 스프레드, CPI YoY, PPI YoY

## 자동 업데이트 구조

매일 한국시간 17:00 (평일), GitHub Actions가 `scraper.py`를 실행한다.
미국 지표는 FRED API로 거의 전부 자동 수집되며, 한국은 4개만 자동 +
4개는 `manual_overrides.json`에서 읽는다. 결과는 `data.json`에 저장되고
저장소에 자동 커밋된다.

## 설치 (처음 1회)

### 1. 파일 업로드
이 폴더의 모든 파일을 GitHub 저장소(public)에 업로드.
`.github/workflows/update.yml`은 경로째로 올려야 한다.

### 2. FRED API 키를 Secret으로 등록 (중요)
API 키를 코드에 직접 넣으면 노출되므로 반드시 Secret으로 저장한다.

- 저장소 → Settings → Secrets and variables → Actions
- New repository secret 클릭
- Name: `FRED_API_KEY`
- Secret: 본인의 FRED API 키 입력 → Add secret

### 3. Actions 권한 설정
Settings → Actions → General → Workflow permissions
→ "Read and write permissions" 선택 → Save

### 4. GitHub Pages 활성화
Settings → Pages → Branch를 `main` / `(root)`로 지정 → Save
→ `https://<사용자명>.github.io/<저장소명>` 으로 접속

### 5. 첫 실행 테스트
Actions 탭 → "지표 자동 업데이트" → Run workflow
→ 1~2분 후 초록 체크 확인.

## 운영

- 매주 월요일: `manual_overrides.json`의 bbb_spread / cp_spread / cds 갱신
- 매월 1일: `manual_overrides.json`의 semi_export_yoy 갱신
- 미국 지표는 손댈 필요 없음 (FRED 자동)
- 자동 수집 실패 시 대시보드 상단에 경고 표시 → 점검 필요

## AI 해석 기능 (선택)

`index.html` 상단 `ANTHROPIC_API_KEY`에 키를 넣으면 카드별 AI 분석이 작동.
public 저장소에 키를 올리면 노출되므로 본인 로컬에서만 사용 권장.

## 주의

- 스크래핑(네이버)은 대상 사이트 구조에 의존하므로 영구 보장되지 않는다.
- FRED 데이터는 공식 API로 안정적이나 CPI/PPI는 월 1회 갱신, 수일 시차 있음.
- 본 도구는 투자 참고용이며 투자 권유가 아니다.
