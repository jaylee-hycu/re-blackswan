# -*- coding: utf-8 -*-
"""data/data.json + template/page.html -> docs/index.html, data/history/signals.csv 에 판정 한 줄씩 덧붙임"""
import csv, json, os, datetime as dt
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
D = json.load(open(os.path.join(BASE, "data", "data.json"), encoding="utf-8"))
KST = dt.timezone(dt.timedelta(hours=9)); now = dt.datetime.now(KST); today = now.date()
BOK = ["2026-10-22", "2026-11-26"]   # 금통위 통화정책방향 결정회의 (언론 보도, 한국은행 원문 확인 필요)

def ym_add(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) + k
    y += (m - 1) // 12; m = (m - 1) % 12 + 1; return f"{y:04d}-{m:02d}"
def kor(ym): return f"{ym[:4]}년 {int(ym[5:7])}월"
def wk_next(asof):   # 주간: 기준 월요일 + 7일 조사, 그 주 목요일 공표
    d = dt.date.fromisoformat(asof) + dt.timedelta(days=7)
    while d + dt.timedelta(days=3) < today: d += dt.timedelta(days=7)
    return d, d + dt.timedelta(days=3)
WD = "월화수목금토일"
def dfmt(d): return f"{d.isoformat()} ({WD[d.weekday()]})"

g = [D[k]["asof"] for k in ("g_ofr", "g_ust10", "g_jgb10", "g_krw")]
wsurvey, wrel = wk_next(D["sup_seo_wk"]["asof"])
m_sale = D["sale_seo"]["asof"]; m_trd = D["trd_nat"]["asof"]; m_rt = D["trade_seo"]["asof"]
m_k3 = D["ktb3"]["asof"]; m_mo = D["mort"]["asof"]; m_ln = D["hloan"]["asof"]; m_us = D["unsold"]["asof"]
nb = next((x for x in BOK if dt.date.fromisoformat(x) >= today), None)
CAL = [
 ["글로벌", "OFR 스트레스·미국/일본 금리·원달러", f"{min(g)}~{max(g)}", "매 영업일", "—", "일별 공표, 1~7일 시차"],
 ["수급·가격", "부동산원 주간 매매지수·매수우위", f"{D['sup_seo_wk']['asof']} 주", dfmt(wrel), f"{wsurvey.isoformat()} 주", "매주 목요일 14시 공표 (언론 보도)"],
 ["가격", "부동산원 월간 매매·전세지수, 월간 매수우위", kor(m_sale), f"{ym_add(m_sale,2)} 중순", kor(ym_add(m_sale,1)), "통상 다음 달 중순"],
 ["거래", "아파트 매매거래 (부동산원)", kor(m_trd), f"{ym_add(m_trd,2)} 하순", kor(ym_add(m_trd,1)), "통상 다음 달 하순"],
 ["가격", "아파트 실거래가격지수 (명목·실질·달러 환산)", kor(m_rt), f"{ym_add(m_rt,3)} 중순", kor(ym_add(m_rt,1)), "약 2개월 뒤 공표"],
 ["금리", "기준금리 (금통위)", f"{D['base']['last']:.2f}%", dfmt(dt.date.fromisoformat(nb)) if nb else "한국은행 일정 확인", "다음 결정", "금통위 일정 (언론 보도)"],
 ["금리", "국고채 3년 (월평균)", kor(m_k3), f"{ym_add(m_k3,2)} 초", kor(ym_add(m_k3,1)), "월말 후 집계"],
 ["금리", "주택담보대출 금리 (신규취급액)", kor(m_mo), f"{ym_add(m_mo,2)} 하순", kor(ym_add(m_mo,1)), "예금은행 가중평균금리, 통상 다음 달 말"],
 ["취약성", "주택관련·전세자금 대출 잔액", kor(m_ln), f"{ym_add(m_ln,3)}~{ym_add(m_ln,4)[5:]}월", kor(ym_add(m_ln,1)), "ECOS 반영 약 2~3개월 뒤"],
 ["취약성", "미분양 주택", kor(m_us), f"{ym_add(m_us,3)}", kor(ym_add(m_us,1)), "국토교통부 주택통계, ECOS 반영 시차"],
]
obs = sorted(v["asof"] for k, v in D.items() if not k.startswith("_"))
D["_cal"] = CAL
D["_meta"] = dict(built=now.strftime("%Y-%m-%d %H:%M"), obs_range=f"{obs[0]} ~ {obs[-1]}", next=dfmt(wrel), next_what="부동산원 주간 지수")

tpl = open(os.path.join(BASE, "template", "page.html"), encoding="utf-8").read()
html = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta name="robots" content="noindex,nofollow">\n<title>아파트 시장 신호등</title>\n</head>\n<body>\n'
        + tpl.replace("__DATA__", json.dumps(D, ensure_ascii=False)) + "\n</body>\n</html>\n")
os.makedirs(os.path.join(BASE, "docs"), exist_ok=True)
open(os.path.join(BASE, "docs", "index.html"), "w", encoding="utf-8").write(html)

# 판정 기록: 관측 시점이 바뀐 지표만 덧붙임 (기존 줄은 고치지 않음)
H = os.path.join(BASE, "data", "history", "signals.csv"); os.makedirs(os.path.dirname(H), exist_ok=True)
seen = set()
if os.path.exists(H):
    with open(H, encoding="utf-8") as fh: seen = {(r["indicator"], r["obs_date"]) for r in csv.DictReader(fh)}
def stage(p, two):
    if two:
        return "경계·과열" if p >= 90 else "경계·급랭" if p <= 10 else "주의·상승" if p >= 75 else "주의·하락" if p <= 25 else "안정"
    return "경계" if p >= 90 else "주의" if p >= 75 else "안정"
REF = {"base", "usd_trade_seo", "usd_trade_nat"}   # 화면에서 판정 없이 참고로만 보이는 지표
new = [[today.isoformat(), k, v["asof"], v["last"], v["sig"], v["sig_kind"], v["pct"], "참고" if k in REF else stage(v["pct"], v["two"])]
       for k, v in D.items() if not k.startswith("_") and (k, v["asof"]) not in seen]
with open(H, "a", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    if not seen: w.writerow(["run_date", "indicator", "obs_date", "value", "signal", "signal_kind", "percentile", "stage"])
    w.writerows(new)
print("built", D["_meta"], "new signal rows", len(new))
