# -*- coding: utf-8 -*-
"""수집: 글로벌(OFR·FRED·일본 재무성), 한국은행 ECOS, 한국부동산원 R-ONE -> data/raw/
환경 변수: REB_API_KEY(필수), ECOS_API_KEY(없으면 공개 sample 키, 느림)"""
import csv, io, json, os, sys, time, zipfile, urllib.parse
import pandas as pd, requests
RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw"); os.makedirs(RAW, exist_ok=True)
S_ = requests.Session()

def get(url, tries=5):
    for k in range(tries):
        try:
            r = S_.get(url, timeout=90); r.raise_for_status(); return r.content
        except Exception as e:
            if k == tries - 1: raise
            time.sleep(3 * (k + 1))

# ---------- 글로벌 ----------
def fred(ids, cosd="2000-01-01"):
    b = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={','.join(ids)}&cosd={cosd}")
    if b[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(b)); b = z.read([n for n in z.namelist() if n.endswith(".csv") and "README" not in n][0])
    return pd.read_csv(io.BytesIO(b), parse_dates=["observation_date"]).set_index("observation_date").apply(pd.to_numeric, errors="coerce")

def ofr():
    j = json.loads(get("https://www.financialresearch.gov/financial-stress-index/data/fsi.json"))
    return pd.Series({pd.to_datetime(t, unit="ms"): v for t, v in j["OFRFSI"]["data"]}).sort_index()

def mof():
    out = []
    for u in ["https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv",
              "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"]:
        t = get(u).decode("latin-1").splitlines(); rows = [l for l in t if l[:2].isdigit()]
        df = pd.read_csv(io.StringIO("\n".join(rows)), header=None)[[0, 10]]; df.columns = ["d", "y"]
        df["d"] = pd.to_datetime(df["d"], format="%Y/%m/%d"); df["y"] = pd.to_numeric(df["y"], errors="coerce"); out.append(df.set_index("d")["y"])
    s = pd.concat(out); return s[~s.index.duplicated(keep="last")].sort_index()

def global_():
    f = fred(["DGS10", "DEXKOUS"])
    S = {"OFR_OFRFSI": ofr(), "DGS10": f["DGS10"], "DEXKOUS": f["DEXKOUS"], "JGB10": mof()}
    rows = [(d.strftime("%Y-%m-%d"), k, v) for k, s in S.items() for d, v in s.dropna().items()]
    pd.DataFrame(rows, columns=["date", "series", "value"]).to_csv(os.path.join(RAW, "global.csv"), index=False)
    print("global", {k: s.dropna().index[-1].date() for k, s in S.items()}, flush=True)

# ---------- ECOS ----------
ECOS = {
 "trade_nat": ("901Y089", ["100"]), "trade_seo": ("901Y089", ["200"]),
 "mort": ("121Y006", ["BECBLA0302"]), "ktb3": ("721Y001", ["5020000"]), "base": ("722Y001", ["0101000"]),
 "unsold": ("901Y074", ["I410A"]), "unsold_metro": ("901Y074", ["I410R"]),
 "hloan": ("151Y005", ["11100A0"]), "jloan": ("151Y005", ["1120094"]),
 "cpi": ("901Y009", ["0"]),
}
def ecos_one(key, code, items, start="200001", end="209912"):
    step = 10 if key == "sample" else 10000; out = []; s = 1
    while True:
        u = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/{s}/{s+step-1}/{code}/M/{start}/{end}/{'/'.join(items)}"
        j = json.loads(get(u)); x = j.get("StatisticSearch")
        if not x: break
        out += [(r["TIME"], float(r["DATA_VALUE"])) for r in x["row"] if r["DATA_VALUE"] not in (None, "")]
        s += step
        if s > x["list_total_count"]: break
    return out
def ecos():
    key = os.environ.get("ECOS_API_KEY") or "sample"; res = {}
    for k, (c, it) in ECOS.items():
        res[k] = ecos_one(key, c, it)
        if not res[k]: raise RuntimeError(f"ECOS 빈 응답: {k}")
    json.dump(res, open(os.path.join(RAW, "ecos_raw.json"), "w"))
    print("ecos", {k: v[-1][0] for k, v in res.items()}, flush=True)

# ---------- R-ONE ----------
RONE = [ # 파일, 표ID, 주기, 시작, 지역ID(None=전체)
 ("rone_sale_all.csv", "A_2024_00045", "MM", "200001", None),
 ("rone_jeon_all.csv", "A_2024_00050", "MM", "200001", None),
 ("rone_supply_m.csv", "A_2024_00076", "MM", "200001", ["500001", "500002", "500008"]),
 ("rone_trade.csv", "A_2024_00554", "MM", "200001", ["500001", "500002"]),
 ("rone_sale_wk.csv", "T244183132827305", "WK", "201201", ["50001", "50002", "50008"]),
 ("rone_supply_wk.csv", "T248163133074619", "WK", "201201", ["50001", "50002", "50008"]),
]
def rone_rows(key, **p):
    out = []; i = 1
    while True:
        q = dict(p, KEY=key, Type="json", pIndex=i, pSize=1000)
        j = json.loads(get("https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do?" + urllib.parse.urlencode(q)))
        b = j.get("SttsApiTblData")
        if not b: raise RuntimeError("R-ONE 오류: " + str(j)[:200])
        out += b[1]["row"]
        if len(out) >= b[0]["head"][0]["list_total_count"]: return out
        i += 1
def rone():
    key = os.environ["REB_API_KEY"]
    for f, tid, cyc, start, cls in RONE:
        R = []
        for c in (cls or [None]):
            p = dict(STATBL_ID=tid, DTACYCLE_CD=cyc, START_WRTTIME=start, END_WRTTIME="209953" if cyc == "WK" else "209912")
            if c: p["CLS_ID"] = c
            R += rone_rows(key, **p)
        with open(os.path.join(RAW, f), "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["t", "desc", "cls_id", "cls", "itm", "val"])
            for x in R: w.writerow([x["WRTTIME_IDTFR_ID"], x["WRTTIME_DESC"], x["CLS_ID"], x["CLS_FULLNM"], x["ITM_NM"], x["DTA_VAL"]])
        print("rone", f, len(R), flush=True)

if __name__ == "__main__":
    parts = sys.argv[1:] or ["global", "ecos", "rone"]
    for p in parts: {"global": global_, "ecos": ecos, "rone": rone}[p]()
