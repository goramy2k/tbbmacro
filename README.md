# 한국·미국 매크로 모니터

한국 8개 + 미국 8개(+CPI/PPI) 거시지표를 자동 수집하고
Claude AI가 시장을 분석하는 대시보드.

## 화면 구성

- 🇰🇷 한국 탭: 대시보드 / 시나리오 / 체크리스트
- 🇺🇸 미국 탭: 대시보드 / 시나리오 / 체크리스트
- 종합 탭: 한국 AI 해석 + 미국 AI 해석 + 글로벌 종합 요약

## 자동 업데이트 (2개 워크플로)

| 워크플로 | 실행 시각 | 담당 |
|----------|-----------|------|
| update-kr.yml | 평일 17:00 KST | 한국 지표 수집 + AI 분석 |
| update-us.yml | 평일 08:00 KST | 미국 지표 수집 + AI 분석 |

각 워크플로는 자기 시장만 갱신하고 상대 시장 데이터는 보존한다.
양쪽 AI 분석이 모두 준비되면 종합 요약이 자동 생성된다.

## 구성 파일

| 파일 | 역할 |
|------|------|
| `index.html` | 대시보드 앱 |
| `data.json` | 지표 + AI 분석 데이터 (자동 갱신) |
| `scraper.py` | 수집·분석 스크립트 (kr/us 인자) |
| `manual_overrides.json` | 한국 수동 입력 지표 |
| `.github/workflows/update-kr.yml` | 한국 자동 실행 |
| `.github/workflows/update-us.yml` | 미국 자동 실행 |

## 설치 (처음 1회)

### 1. 파일 업로드
모든 파일을 GitHub 저장소(public)에 업로드.

### 2. Secret 2개 등록
Settings → Secrets and variables → Actions → New repository secret
- `FRED_API_KEY` : FRED API 키
- `ANTHROPIC_API_KEY` : Anthropic API 키

### 3. Actions 권한
Settings → Actions → General → Workflow permissions
→ "Read and write permissions" → Save

### 4. GitHub Pages
Settings → Pages → Branch `main` / `(root)` → Save

### 5. 첫 실행 테스트
Actions 탭에서 "한국 지표 업데이트", "미국 지표 업데이트"를
각각 Run workflow로 한 번씩 실행.

## scraper.py 사용법

```
python scraper.py kr    # 한국만
python scraper.py us    # 미국만
python scraper.py       # 둘 다 (수동)
```

## 수동 갱신 (한국 지표 일부)

- 매주 월요일: manual_overrides.json 의 bbb_spread/cp_spread/cds
- 매월 1일: semi_export_yoy

## 비용

AI 분석은 하루 한국 1회 + 미국 1회 호출. 월 2달러 미만 수준.
Anthropic Console에서 월 지출 한도 설정 권장.

## 주의

- 스크래핑(네이버)은 사이트 구조 변경 시 깨질 수 있다.
- 본 도구는 투자 참고용이며 투자 권유가 아니다.
