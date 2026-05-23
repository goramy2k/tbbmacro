#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국 + 미국 매크로 모니터링 - 지표 자동 수집 스크립트
매일 GitHub Actions 로 실행되어 data.json 을 생성한다.

한국 (8개)
  - 자동 (네이버): VKOSPI, USD/KRW, 외국인 수급, 국고채 금리
  - 수동 (manual_overrides.json): BBB-, CP 스프레드, CDS, 반도체 수출

미국 (8개 카드 + CPI/PPI 별도)
  - 자동 (FRED API): 2Y, 10Y, 30Y, 장단기 스프레드, HY 스프레드, VIX, WTI, 브렌트, CPI, PPI

FRED API 키는 환경변수 FRED_API_KEY 로 받는다 (GitHub Secrets).
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

# GitHub Secrets 에서 주입 (절대 코드에 키를 직접 쓰지 않는다)
FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()


def fetch(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[fetch 실패] {url[:80]} -> {e}", file=sys.stderr)
        return None


def fetch_json(url, timeout=20):
    raw = fetch(url, timeout)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"[json 파싱 실패] -> {e}", file=sys.stderr)
        return None


# ===========================================================================
# FRED - 미국 지표 공통 수집기
# ===========================================================================
def fred_latest(series_id):
    """FRED 시리즈의 최근 유효 관측치 1개를 반환."""
    if not FRED_KEY:
        print("[FRED] API 키 없음 - 미국 자동수집 건너뜀", file=sys.stderr)
        return None, None
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_KEY}&file_type=json"
           f"&sort_order=desc&limit=8")
    j = fetch_json(url)
    if not j:
        return None, None
    for o in j.get("observations", []):
        if o.get("value") not in (".", "", None):
            try:
                return float(o["value"]), o["date"]
            except ValueError:
                continue
    return None, None


def fred_yoy(series_id):
    """월간 지수의 전년동월비(%)를 계산. CPI, PPI 용."""
    if not FRED_KEY:
        return None, None
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_KEY}&file_type=json"
           f"&sort_order=desc&limit=14")
    j = fetch_json(url)
    if not j:
        return None, None
    vals = []
    for o in j.get("observations", []):
        if o.get("value") not in (".", "", None):
            try:
                vals.append((o["date"], float(o["value"])))
            except ValueError:
                continue
    if len(vals) >= 13:
        latest_date, latest = vals[0]
        year_ago = vals[12][1]
        if year_ago:
            return round((latest / year_ago - 1) * 100, 1), latest_date
    return None, None


# ===========================================================================
# 한국 지표 수집기
# ===========================================================================
def get_usdkrw():
    j = fetch_json("https://api.stock.naver.com/marketindex/exchange/FX_USDKRW")
    try:
        return float(str(j["closePrice"]).replace(",", ""))
    except Exception:
        pass
    raw = fetch("https://m.stock.naver.com/marketindex/exchange/FX_USDKRW")
    if raw:
        m = re.search(r'"closePrice"\s*:\s*"([\d,\.]+)"', raw)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def get_vkospi():
    j = fetch_json("https://api.stock.naver.com/index/VKOSPI/basic")
    try:
        return float(str(j["closePrice"]).replace(",", ""))
    except Exception:
        return None


def get_kospi_and_foreign():
    j = fetch_json("https://api.stock.naver.com/index/KOSPI/basic")
    kospi = None
    try:
        kospi = float(str(j["closePrice"]).replace(",", ""))
    except Exception:
        pass
    foreign = None
    inv = fetch_json("https://api.stock.naver.com/index/KOSPI/investorTrend")
    try:
        row = inv["investorTrends"][0]
        foreign = float(row["foreignerPureBuyQuant"]) / 1e8
    except Exception:
        pass
    return kospi, foreign


def get_treasury_kr():
    raw = fetch("https://finance.naver.com/marketindex/bondList.naver")
    y10 = y2 = None
    if raw:
        m10 = re.search(r'국고채\(10년\).*?([\d]\.[\d]{2,3})', raw, re.S)
        m2 = re.search(r'국고채\(2년\).*?([\d]\.[\d]{2,3})', raw, re.S)
        if m10:
            y10 = float(m10.group(1))
        if m2:
            y2 = float(m2.group(1))
    if y10 is not None and y2 is not None:
        return round((y10 - y2) * 100)
    return None


def get_us_market_naver():
    """네이버 해외 시장지표에서 VIX, WTI, 브렌트 보조 수집."""
    out = {"vix": None, "wti": None, "brent": None}
    mapping = {
        "vix": "https://api.stock.naver.com/index/.VIX/basic",
        "wti": "https://api.stock.naver.com/marketindex/oil/CLcv1",
        "brent": "https://api.stock.naver.com/marketindex/oil/LCOcv1",
    }
    for k, url in mapping.items():
        j = fetch_json(url)
        try:
            out[k] = float(str(j["closePrice"]).replace(",", ""))
        except Exception:
            pass
    return out


# ===========================================================================
# 상태 판정
# ===========================================================================
def status_of(metric, v):
    if v is None:
        return "warn"
    t = {
        "vkospi":   lambda x: "ok" if x < 15 else "warn" if x < 20 else "danger",
        "usdkrw":   lambda x: "ok" if x < 1350 else "warn" if x < 1400 else "danger",
        "foreigner":lambda x: "ok" if x > 0 else "warn" if x > -5000 else "danger",
        "bbb":      lambda x: "ok" if x < 200 else "warn" if x < 300 else "danger",
        "spread":   lambda x: "ok" if x > 30 else "warn" if x > 0 else "danger",
        "cp":       lambda x: "ok" if x < 50 else "warn" if x < 100 else "danger",
        "semi":     lambda x: "ok" if x > 10 else "warn" if x > 0 else "danger",
        "cds":      lambda x: "ok" if x < 50 else "warn" if x < 80 else "danger",
        "vix":      lambda x: "ok" if x < 20 else "warn" if x < 30 else "danger",
        "hy":       lambda x: "ok" if x < 4 else "warn" if x < 6 else "danger",
        "wti":      lambda x: "ok" if x < 85 else "warn" if x < 100 else "danger",
        "brent":    lambda x: "ok" if x < 90 else "warn" if x < 105 else "danger",
        "us2y":     lambda x: "ok" if x < 4 else "warn" if x < 4.8 else "danger",
        "us10y":    lambda x: "ok" if x < 4.5 else "warn" if x < 5 else "danger",
        "us30y":    lambda x: "ok" if x < 5 else "warn" if x < 5.5 else "danger",
        "usspread": lambda x: "ok" if x > 0.3 else "warn" if x > 0 else "danger",
        "cpi":      lambda x: "ok" if x < 3 else "warn" if x < 4 else "danger",
        "ppi":      lambda x: "ok" if x < 3 else "warn" if x < 5 else "danger",
    }
    fn = t.get(metric)
    return fn(v) if fn else "warn"


def score_of(indicators):
    if not indicators:
        return 0
    per = 100.0 / len(indicators)
    s = 0.0
    for ind in indicators:
        if ind["status"] == "ok":
            s += per
        elif ind["status"] == "warn":
            s += per / 2
    return round(s)


def main():
    manual = {}
    if os.path.exists(MANUAL_PATH):
        try:
            with open(MANUAL_PATH, encoding="utf-8") as f:
                manual = json.load(f)
        except Exception as e:
            print(f"[manual 로드 실패] {e}", file=sys.stderr)

    prev = {}
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            pass

    prev_kr = {i["id"]: i for i in prev.get("kr", {}).get("indicators", [])}
    prev_us = {i["id"]: i for i in prev.get("us", {}).get("indicators", [])}

    # ---------------- 한국 ----------------
    usdkrw = get_usdkrw()
    vkospi = get_vkospi()
    kospi, foreign = get_kospi_and_foreign()
    kr_spread = get_treasury_kr()

    def kr_auto(mid, val, fmt, unit, label, cat):
        if val is None:
            p = prev_kr.get(mid, {})
            return {"id": mid, "label": label, "cat": cat,
                    "value": p.get("value"), "raw": p.get("raw"),
                    "unit": unit, "status": p.get("status", "warn"),
                    "source": "fallback"}
        return {"id": mid, "label": label, "cat": cat,
                "value": fmt(val), "raw": val, "unit": unit,
                "status": status_of(mid, val), "source": "naver"}

    kr_inds = []
    kr_inds.append(kr_auto("vkospi", vkospi, lambda v: f"{v:.1f}", "",
                           "VKOSPI", "변동성"))
    kr_inds.append(kr_auto("usdkrw", usdkrw, lambda v: f"{v:,.1f}", "원",
                           "USD/KRW", "환율·수급"))
    if foreign is None:
        p = prev_kr.get("foreigner", {})
        kr_inds.append({"id": "foreigner", "label": "외국인 순매수",
                        "cat": "환율·수급", "value": p.get("value"),
                        "raw": p.get("raw"), "unit": "",
                        "status": p.get("status", "warn"), "source": "fallback"})
    else:
        fval = (f"{foreign/10000:+.1f}조" if abs(foreign) >= 10000
                else f"{foreign:+,.0f}억")
        kr_inds.append({"id": "foreigner", "label": "외국인 순매수",
                        "cat": "환율·수급", "value": fval, "raw": foreign,
                        "unit": "", "status": status_of("foreigner", foreign),
                        "source": "naver"})
    bbb = manual.get("bbb_spread")
    kr_inds.append({"id": "bbb", "label": "BBB- 스프레드", "cat": "크레딧",
                    "value": f"~{bbb:.0f}" if bbb is not None else None,
                    "raw": bbb, "unit": "bp",
                    "status": status_of("bbb", bbb), "source": "manual"})
    kr_inds.append(kr_auto("spread", kr_spread, lambda v: f"{v:+.0f}", "bp",
                           "국고채 10Y-2Y", "금리곡선"))
    cp = manual.get("cp_spread")
    kr_inds.append({"id": "cp", "label": "CP 스프레드", "cat": "크레딧",
                    "value": f"~{cp:.0f}" if cp is not None else None,
                    "raw": cp, "unit": "bp",
                    "status": status_of("cp", cp), "source": "manual"})
    semi = manual.get("semi_export_yoy")
    kr_inds.append({"id": "semi", "label": "반도체 수출 YoY", "cat": "경기선행",
                    "value": f"{semi:+.1f}" if semi is not None else None,
                    "raw": semi, "unit": "%",
                    "status": status_of("semi", semi), "source": "manual"})
    cds = manual.get("cds")
    kr_inds.append({"id": "cds", "label": "한국 CDS 5Y", "cat": "국가신용",
                    "value": f"~{cds:.0f}" if cds is not None else None,
                    "raw": cds, "unit": "bp",
                    "status": status_of("cds", cds), "source": "manual"})

    # ---------------- 미국 ----------------
    us2y, _ = fred_latest("DGS2")
    us10y, _ = fred_latest("DGS10")
    us30y, _ = fred_latest("DGS30")
    usspread, _ = fred_latest("T10Y2Y")
    hy, _ = fred_latest("BAMLH0A0HYM2")
    vix_f, _ = fred_latest("VIXCLS")
    wti_f, _ = fred_latest("DCOILWTICO")
    brent_f, _ = fred_latest("DCOILBRENTEU")
    cpi_yoy, cpi_date = fred_yoy("CPIAUCSL")
    ppi_yoy, ppi_date = fred_yoy("PPIFIS")

    nv = get_us_market_naver()
    vix = vix_f if vix_f is not None else nv["vix"]
    wti = wti_f if wti_f is not None else nv["wti"]
    brent = brent_f if brent_f is not None else nv["brent"]

    def us_card(mid, val, fmt, unit, label, cat):
        if val is None:
            p = prev_us.get(mid, {})
            return {"id": mid, "label": label, "cat": cat,
                    "value": p.get("value"), "raw": p.get("raw"),
                    "unit": unit, "status": p.get("status", "warn"),
                    "source": "fallback"}
        return {"id": mid, "label": label, "cat": cat,
                "value": fmt(val), "raw": val, "unit": unit,
                "status": status_of(mid, val), "source": "fred"}

    us_inds = []
    us_inds.append(us_card("vix", vix, lambda v: f"{v:.1f}", "", "VIX", "변동성"))
    us_inds.append(us_card("hy", hy, lambda v: f"{v:.2f}", "%",
                           "HY 스프레드", "크레딧"))
    us_inds.append(us_card("wti", wti, lambda v: f"{v:.1f}", "$",
                           "WTI 유가", "원자재"))
    us_inds.append(us_card("brent", brent, lambda v: f"{v:.1f}", "$",
                           "브렌트유", "원자재"))
    us_inds.append(us_card("us2y", us2y, lambda v: f"{v:.2f}", "%",
                           "미국 2Y", "금리"))
    us_inds.append(us_card("us10y", us10y, lambda v: f"{v:.2f}", "%",
                           "미국 10Y", "금리"))
    us_inds.append(us_card("us30y", us30y, lambda v: f"{v:.2f}", "%",
                           "미국 30Y", "금리"))
    us_inds.append(us_card("usspread", usspread, lambda v: f"{v:+.2f}", "%p",
                           "장단기 10Y-2Y", "금리곡선"))

    pm = prev.get("us", {}).get("macro", {})
    macro = {
        "cpi": {"label": "미국 CPI YoY",
                "value": f"{cpi_yoy:+.1f}%" if cpi_yoy is not None
                else pm.get("cpi", {}).get("value"),
                "raw": cpi_yoy if cpi_yoy is not None
                else pm.get("cpi", {}).get("raw"),
                "date": cpi_date or pm.get("cpi", {}).get("date"),
                "status": status_of("cpi", cpi_yoy if cpi_yoy is not None
                                     else pm.get("cpi", {}).get("raw"))},
        "ppi": {"label": "미국 PPI YoY",
                "value": f"{ppi_yoy:+.1f}%" if ppi_yoy is not None
                else pm.get("ppi", {}).get("value"),
                "raw": ppi_yoy if ppi_yoy is not None
                else pm.get("ppi", {}).get("raw"),
                "date": ppi_date or pm.get("ppi", {}).get("date"),
                "status": status_of("ppi", ppi_yoy if ppi_yoy is not None
                                     else pm.get("ppi", {}).get("raw"))},
    }

    kr_score = score_of(kr_inds)
    us_score = score_of(us_inds)
    total_score = round((kr_score + us_score) / 2)

    history = prev.get("history", [])
    history = [h for h in history if h.get("date") != DATESTR]
    history.append({"date": DATESTR, "kr": kr_score,
                    "us": us_score, "total": total_score})
    history = history[-30:]

    out = {
        "updated": ISO,
        "updated_kst": TODAY.strftime("%Y-%m-%d %H:%M KST"),
        "total_score": total_score,
        "history": history,
        "kr": {"score": kr_score, "kospi": kospi, "indicators": kr_inds},
        "us": {"score": us_score, "indicators": us_inds, "macro": macro},
    }

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    kr_ok = sum(1 for i in kr_inds if i["source"] in ("naver", "manual"))
    us_ok = sum(1 for i in us_inds if i["source"] == "fred")
    print(f"[완료] {ISO} | 통합 {total_score} "
          f"(한국 {kr_score}/미국 {us_score}) | "
          f"한국 {kr_ok}/8, 미국 {us_ok}/8 수집")


if __name__ == "__main__":
    main()
