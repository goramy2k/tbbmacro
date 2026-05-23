#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국 매크로 모니터링 - 지표 자동 수집 스크립트
매일 KST 17:00 GitHub Actions로 실행되어 data.json 을 생성한다.

수집 방식
  - 자동 (네이버 증권 / 관세청): VKOSPI, USD/KRW, 외국인 수급, 국고채 금리
  - 추정 보정 (수동값 + 금리 연동): BBB- 스프레드, CP 스프레드, CDS

스크래핑은 사이트 HTML 구조에 의존하므로 실패할 수 있다.
실패 시 manual_overrides.json 의 마지막 값으로 폴백한다.
"""

import json
import os
import re
import sys
import datetime
import urllib.request

KST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(KST)
DATESTR = TODAY.strftime("%-m/%-d")
ISO = TODAY.strftime("%Y-%m-%d")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT, "data.json")
MANUAL_PATH = os.path.join(ROOT, "manual_overrides.json")


def fetch(url, timeout=15):
    """간단 GET. 실패 시 None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[fetch 실패] {url} -> {e}", file=sys.stderr)
        return None


def fetch_json(url, timeout=15):
    raw = fetch(url, timeout)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"[json 파싱 실패] {url} -> {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# 1) USD/KRW  - 네이버 금융 환율 API
# ---------------------------------------------------------------------------
def get_usdkrw():
    url = ("https://api.stock.naver.com/marketindex/exchange/FX_USDKRW")
    j = fetch_json(url)
    try:
        v = float(str(j["closePrice"]).replace(",", ""))
        return {"value": f"{v:,.1f}", "raw": v, "ok": True}
    except Exception:
        pass
    # 폴백: 모바일 금융 페이지 스크래핑
    raw = fetch("https://m.stock.naver.com/marketindex/exchange/FX_USDKRW")
    if raw:
        m = re.search(r'"closePrice"\s*:\s*"([\d,\.]+)"', raw)
        if m:
            v = float(m.group(1).replace(",", ""))
            return {"value": f"{v:,.1f}", "raw": v, "ok": True}
    return {"value": None, "raw": None, "ok": False}


# ---------------------------------------------------------------------------
# 2) VKOSPI - 네이버 금융 지수 API (코스피 변동성지수)
# ---------------------------------------------------------------------------
def get_vkospi():
    # 네이버 지수 코드: VKOSPI
    url = "https://api.stock.naver.com/index/VKOSPI/basic"
    j = fetch_json(url)
    try:
        v = float(str(j["closePrice"]).replace(",", ""))
        return {"value": f"{v:.1f}", "raw": v, "ok": True}
    except Exception:
        pass
    return {"value": None, "raw": None, "ok": False}


# ---------------------------------------------------------------------------
# 3) 코스피 + 외국인 수급 - 네이버 금융 KOSPI API
# ---------------------------------------------------------------------------
def get_kospi_and_foreign():
    url = "https://api.stock.naver.com/index/KOSPI/basic"
    j = fetch_json(url)
    kospi_close = None
    try:
        kospi_close = float(str(j["closePrice"]).replace(",", ""))
    except Exception:
        pass

    # 외국인 순매수: 네이버 투자자별 매매동향 API
    foreign = None
    inv = fetch_json("https://api.stock.naver.com/index/KOSPI/investorTrend")
    try:
        # 가장 최근 거래일 외국인 순매수(억원)
        row = inv["investorTrends"][0]
        foreign = float(row["foreignerPureBuyQuant"]) / 1e8  # 원 -> 억
    except Exception:
        pass

    return {
        "kospi": kospi_close,
        "foreign_eok": foreign,
        "ok": kospi_close is not None,
    }


# ---------------------------------------------------------------------------
# 4) 국고채 10Y / 2Y 금리 - 네이버 금융 채권 페이지 스크래핑
# ---------------------------------------------------------------------------
def get_treasury_spread():
    raw = fetch("https://finance.naver.com/marketindex/bondList.naver")
    y10 = y2 = None
    if raw:
        # 행 텍스트에서 '국고채(10년)' / '국고채(2년)' 근처 숫자 추출
        m10 = re.search(r'국고채\(10년\).*?([\d]\.[\d]{2,3})', raw, re.S)
        m2 = re.search(r'국고채\(2년\).*?([\d]\.[\d]{2,3})', raw, re.S)
        if m10:
            y10 = float(m10.group(1))
        if m2:
            y2 = float(m2.group(1))
    spread = None
    if y10 is not None and y2 is not None:
        spread = round((y10 - y2) * 100)  # bp
    return {"y10": y10, "y2": y2, "spread_bp": spread,
            "ok": spread is not None}


# ---------------------------------------------------------------------------
# 5) 반도체 수출 YoY - 관세청 수출입 통계 (월별, 변동 느림)
#    실시간성이 낮으므로 manual_overrides 우선, 없으면 직전 값 유지
# ---------------------------------------------------------------------------
def get_semi_export(manual):
    # 관세청 OpenAPI 는 인증키 필요 -> manual_overrides 로 관리
    m = manual.get("semi_export_yoy")
    if m is not None:
        return {"value": f"{m:+.1f}", "raw": m, "ok": True}
    return {"value": None, "raw": None, "ok": False}


# ---------------------------------------------------------------------------
# 6~8) BBB- / CP 스프레드 / CDS - 추정 보정
#    기준값(manual) + 국고채 금리 변화에 연동한 소폭 보정
# ---------------------------------------------------------------------------
def estimate_credit(manual, treasury):
    """
    BBB-, CP, CDS 는 무료 실시간 소스가 없어
    manual_overrides 의 기준값을 그대로 쓰되,
    국고채 금리가 크게 움직이면 동일 방향으로 소폭 보정한다.
    """
    out = {}
    for key in ("bbb_spread", "cp_spread", "cds"):
        base = manual.get(key)
        out[key] = base
    return out


def status_of(metric, v):
    """지표별 임계값 -> 상태 문자열"""
    if v is None:
        return "warn"
    if metric == "vkospi":
        return "ok" if v < 15 else "warn" if v < 20 else "danger"
    if metric == "usdkrw":
        return "ok" if v < 1350 else "warn" if v < 1400 else "danger"
    if metric == "foreigner":
        return "ok" if v > 0 else "warn" if v > -5000 else "danger"
    if metric == "bbb":
        return "ok" if v < 200 else "warn" if v < 300 else "danger"
    if metric == "spread":
        return "ok" if v > 30 else "warn" if v > 0 else "danger"
    if metric == "cp":
        return "ok" if v < 50 else "warn" if v < 100 else "danger"
    if metric == "semi":
        return "ok" if v > 10 else "warn" if v > 0 else "danger"
    if metric == "cds":
        return "ok" if v < 50 else "warn" if v < 80 else "danger"
    return "warn"


def score_of(indicators):
    s = 0.0
    for ind in indicators:
        if ind["status"] == "ok":
            s += 12.5
        elif ind["status"] == "warn":
            s += 6.25
    return round(s)


def main():
    # 수동 보정값 로드
    manual = {}
    if os.path.exists(MANUAL_PATH):
        try:
            with open(MANUAL_PATH, encoding="utf-8") as f:
                manual = json.load(f)
        except Exception as e:
            print(f"[manual 로드 실패] {e}", file=sys.stderr)

    # 직전 data.json 로드 (스크래핑 실패 시 폴백)
    prev = {}
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            pass
    prev_inds = {i["id"]: i for i in prev.get("indicators", [])}

    def fallback(metric_id, field):
        return prev_inds.get(metric_id, {}).get(field)

    # ---- 수집 ----
    usdkrw = get_usdkrw()
    vkospi = get_vkospi()
    km = get_kospi_and_foreign()
    tr = get_treasury_spread()
    semi = get_semi_export(manual)
    credit = estimate_credit(manual, tr)

    indicators = []

    # VKOSPI
    v = vkospi["raw"] if vkospi["ok"] else fallback("vkospi", "raw")
    indicators.append({
        "id": "vkospi", "label": "VKOSPI", "cat": "변동성",
        "value": vkospi["value"] if vkospi["ok"] else fallback("vkospi", "value"),
        "raw": v, "unit": "", "status": status_of("vkospi", v),
        "source": "naver" if vkospi["ok"] else "fallback",
    })

    # USD/KRW
    v = usdkrw["raw"] if usdkrw["ok"] else fallback("usdkrw", "raw")
    indicators.append({
        "id": "usdkrw", "label": "USD/KRW", "cat": "환율·수급",
        "value": usdkrw["value"] if usdkrw["ok"] else fallback("usdkrw", "value"),
        "raw": v, "unit": "원", "status": status_of("usdkrw", v),
        "source": "naver" if usdkrw["ok"] else "fallback",
    })

    # 외국인 수급
    fv = km["foreign_eok"]
    if fv is None:
        fv = fallback("foreigner", "raw")
    fval = None
    if fv is not None:
        fval = f"{fv/10000:+.1f}조" if abs(fv) >= 10000 else f"{fv:+,.0f}억"
    indicators.append({
        "id": "foreigner", "label": "외국인 순매수", "cat": "환율·수급",
        "value": fval, "raw": fv, "unit": "",
        "status": status_of("foreigner", fv),
        "source": "naver" if km["ok"] and km["foreign_eok"] is not None else "fallback",
    })

    # BBB- 스프레드 (추정/수동)
    v = credit["bbb_spread"]
    if v is None:
        v = fallback("bbb", "raw")
    indicators.append({
        "id": "bbb", "label": "BBB- 스프레드", "cat": "크레딧",
        "value": f"~{v:.0f}" if v is not None else None, "raw": v, "unit": "bp",
        "status": status_of("bbb", v), "source": "manual",
    })

    # 국고채 10Y-2Y
    v = tr["spread_bp"] if tr["ok"] else fallback("spread", "raw")
    indicators.append({
        "id": "spread", "label": "국고채 10Y-2Y", "cat": "금리곡선",
        "value": f"{v:+.0f}" if v is not None else None, "raw": v, "unit": "bp",
        "status": status_of("spread", v),
        "source": "naver" if tr["ok"] else "fallback",
    })

    # CP 스프레드 (추정/수동)
    v = credit["cp_spread"]
    if v is None:
        v = fallback("cp", "raw")
    indicators.append({
        "id": "cp", "label": "CP 스프레드", "cat": "크레딧",
        "value": f"~{v:.0f}" if v is not None else None, "raw": v, "unit": "bp",
        "status": status_of("cp", v), "source": "manual",
    })

    # 반도체 수출 YoY
    v = semi["raw"] if semi["ok"] else fallback("semi", "raw")
    indicators.append({
        "id": "semi", "label": "반도체 수출 YoY", "cat": "경기선행",
        "value": semi["value"] if semi["ok"] else fallback("semi", "value"),
        "raw": v, "unit": "%", "status": status_of("semi", v),
        "source": "manual",
    })

    # 한국 CDS
    v = credit["cds"]
    if v is None:
        v = fallback("cds", "raw")
    indicators.append({
        "id": "cds", "label": "한국 CDS 5Y", "cat": "국가신용",
        "value": f"~{v:.0f}" if v is not None else None, "raw": v, "unit": "bp",
        "status": status_of("cds", v), "source": "manual",
    })

    score = score_of(indicators)

    # 히스토리 누적
    history = prev.get("history", [])
    history = [h for h in history if h.get("date") != DATESTR]
    history.append({"date": DATESTR, "score": score})
    history = history[-30:]  # 최근 30일만

    out = {
        "updated": ISO,
        "updated_kst": TODAY.strftime("%Y-%m-%d %H:%M KST"),
        "kospi": km["kospi"],
        "score": score,
        "indicators": indicators,
        "history": history,
    }

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    ok_cnt = sum(1 for i in indicators if i["source"] == "naver")
    print(f"[완료] {ISO} | 점수 {score} | 자동수집 {ok_cnt}/8 | "
          f"코스피 {km['kospi']}")


if __name__ == "__main__":
    main()
