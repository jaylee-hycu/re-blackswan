"""부동산 Black Swan 지표 계산 (공개판, GitHub Actions용). 입력 data/raw/ -> 출력 data/data.json, data/series.csv
입력:       data/raw/global.csv (OFR·FRED·일본 재무성 일별), ecos_raw.json (한국은행), rone_*.csv (한국부동산원)
- 부동산원 아파트 매매·전세: R-ONE 원값(2026.06=100, 2003.11~ 공식 연결 시계열) 사용 → v0.1의 ECOS 수작업 연결 대체
- 실거래가격지수·금리·대출·미분양: ECOS
- 판정값/백분위 규칙은 v0.1과 같음. 분포는 2006-01(또는 시계열 시작) 이후
"""
import json, os, sys, pandas as pd, numpy as np
BASE=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
RAW=os.path.join(BASE,"data","raw")
R=json.load(open(os.path.join(RAW,"ecos_raw.json")))
def ecos(k): return pd.Series({f"{t[:4]}-{t[4:6]}":v for t,v in R[k]}).sort_index()
def rd(f): return pd.read_csv(os.path.join(RAW,f),dtype={"t":str})
def rmon(f,cls,itm=None):
    d=rd(f); d=d[d.cls==cls]
    if itm: d=d[d.itm==itm]
    return pd.Series(d.val.values,index=[f"{t[:4]}-{t[4:6]}" for t in d.t]).sort_index()
def rwk(f,cls):
    d=rd(f); d=d[d.cls==cls]; return pd.Series(d.val.values,index=d.desc.values).sort_index()
# 확산도: 최하위 지역(시군구) 중 1년 상승률 > 0 인 비율
s=rd("rone_sale_all.csv").dropna(subset=["cls"])
cl=list(s.cls.unique()); AGG={"전국","수도권","지방권","5대광역시","4대광역시","8개도","7개도"}
leaves=[c for c in cl if c not in AGG and not any(o!=c and o.startswith(c+">") for o in cl)]
P=s[s.cls.isin(leaves)].pivot_table(index="t",columns="cls",values="val"); P.index=[f"{t[:4]}-{t[4:6]}" for t in P.index]
Y=(P/P.shift(12)-1)*100; ok=Y.notna().sum(axis=1)
diff=((Y>0).sum(axis=1)/ok*100)[ok>=50]
J=rd("rone_jeon_all.csv").dropna(subset=["cls"])
PJ=J[J.cls.isin(leaves)].pivot_table(index="t",columns="cls",values="val"); PJ.index=[f"{t[:4]}-{t[4:6]}" for t in PJ.index]
C24=(PJ/PJ.shift(24)-1)*100; okj=C24.notna().sum(axis=1)
revj=((C24<0).sum(axis=1)/okj*100)[okj>=50]
S={ "rev_jeon":revj, "sale_nat":rmon("rone_sale_all.csv","전국"), "sale_seo":rmon("rone_sale_all.csv","서울"),
    "jeon_nat":rmon("rone_jeon_all.csv","전국"), "jeon_seo":rmon("rone_jeon_all.csv","서울"),
    "sup_seo_m":rmon("rone_supply_m.csv","서울"), "trd_nat":rmon("rone_trade.csv","전국","동(호)수"), "trd_seo":rmon("rone_trade.csv","서울","동(호)수"),
    "diff":diff,
    **{k:ecos(k) for k in ["trade_nat","trade_seo","mort","ktb3","base","unsold","unsold_metro","hloan","jloan","cpi"]}}
pd.DataFrame(S).sort_index().to_csv(os.path.join(BASE,"data","series.csv"))
W={"sup_seo_wk":rwk("rone_supply_wk.csv","서울"),"sup_nat_wk":rwk("rone_supply_wk.csv","전국"),"wk_seo":rwk("rone_sale_wk.csv","서울")}
yoy=lambda x:(x/x.shift(12)-1)*100
yoy3=lambda x:(x.rolling(3).sum()/x.rolling(3).sum().shift(12)-1)*100
SIG={ # key:(시계열, 판정값 함수, 설명, 양방향, 주간)
 "ktb3":(S["ktb3"],lambda x:x.diff(3),"3개월 변화 %p",False,False),
 "mort":(S["mort"],lambda x:x.diff(3),"3개월 변화 %p",False,False),
 "base":(S["base"],lambda x:x.diff(3),"3개월 변화 %p",False,False),
 "hloan":(S["hloan"],yoy,"전년동월비 %",False,False),
 "jloan":(S["jloan"],yoy,"전년동월비 %",False,False),
 "jeon_fall":(S["jeon_nat"],lambda x:-yoy(x),"전세 하락률 %",False,False),
 "rev_jeon":(S["rev_jeon"],lambda x:x,"2년 전보다 전세가 낮은 지역 비율 %",False,False),
 "unsold":(S["unsold"],lambda x:x,"수준(호)",False,False),
 "unsold_metro":(S["unsold_metro"],lambda x:x,"수준(호)",False,False),
 "sup_seo_wk":(W["sup_seo_wk"],lambda x:x,"수준(100=균형)",True,True),
 "sup_nat_wk":(W["sup_nat_wk"],lambda x:x,"수준(100=균형)",True,True),
 "wk_seo":(W["wk_seo"],lambda x:(x/x.shift(4)-1)*100,"4주 변화 %",True,True),
 "trd_nat":(S["trd_nat"],yoy3,"3개월 합 전년동기비 %",True,False),
 "trd_seo":(S["trd_seo"],yoy3,"3개월 합 전년동기비 %",True,False),
 "diff":(S["diff"],lambda x:x,"상승 지역 비율 %",True,False),
 "sale_nat":(S["sale_nat"],yoy,"전년동월비 %",True,False),
 "sale_seo":(S["sale_seo"],yoy,"전년동월비 %",True,False),
 "trade_seo":(S["trade_seo"],yoy,"전년동월비 %",True,False),
 "jeon_seo":(S["jeon_seo"],yoy,"전년동월비 %",True,False),
}
out={}
for k,(x,f,kind,two,wk) in SIG.items():
    x=x.dropna(); g=f(x).dropna()
    if not wk: g=g[g.index>="2006-01"]
    cur=g.iloc[-1]; pct=round(float((g<=cur).mean()*100),1)
    out[k]=dict(d=list(x.index),v=[round(float(v),4) for v in x.values],last=round(float(x.iloc[-1]),4),asof=x.index[-1],
        sig=round(float(cur),3),sig_kind=kind,pct=pct,two=two,wk=wk,sig_start=g.index[0],n=len(x),
        sd=list(g.index),sv=[round(float(v),3) for v in g.values],q={str(p):round(float(np.percentile(g,p)),3) for p in (10,25,75,90)})
out["_diff_n"]=int(ok.iloc[-1]); out["_revj_n"]=int(okj.iloc[-1])
G=pd.read_csv(os.path.join(RAW,"global.csv"),parse_dates=["date"]); G=G.pivot_table(index="date",columns="series",values="value")
def gpack(x,kind=None):
    x=x.dropna(); x=x[x.index>="2000-01-01"]
    g=x if kind is None else (x.diff(21) if kind=="diff" else x.pct_change(21)*100)
    g=g.dropna(); cur=float(g.iloc[-1]); w=x.resample("W-FRI").last().dropna(); gw=g.resample("W-FRI").last().dropna()
    return dict(d=[t.strftime("%Y-%m-%d") for t in w.index],v=[round(float(v),4) for v in w.values],last=round(float(x.iloc[-1]),4),
        asof=x.index[-1].strftime("%Y-%m-%d"),sig=round(cur,3),sig_kind=kind or "수준",pct=round(float((g<=cur).mean()*100),1),two=False,wk=True,
        sig_start=g.index[0].strftime("%Y-%m-%d"),n=len(x),sd=[t.strftime("%Y-%m-%d") for t in gw.index],sv=[round(float(v),3) for v in gw.values],
        q={str(p):round(float(np.percentile(g,p)),3) for p in (10,25,75,90)})
fxm=G["DEXKOUS"].dropna().resample("ME").mean(); fxm.index=fxm.index.strftime("%Y-%m")
cpi=S["cpi"].dropna()
def mk(k,x,kind):
    g=yoy(x).dropna(); g=g[g.index>="2006-01"]; cur=g.iloc[-1]
    out[k]=dict(d=list(x.index),v=[round(float(v),4) for v in x.values],last=round(float(x.iloc[-1]),4),asof=x.index[-1],
        sig=round(float(cur),3),sig_kind=kind,pct=round(float((g<=cur).mean()*100),1),two=True,wk=False,sig_start=g.index[0],n=len(x),
        sd=list(g.index),sv=[round(float(v),3) for v in g.values],q={str(p):round(float(np.percentile(g,p)),3) for p in (10,25,75,90)})
for k,src in [("real_trade_seo","trade_seo"),("real_trade_nat","trade_nat")]:   # 실질 = 실거래가지수 / 소비자물가, 2026.06=100
    x=S[src].dropna(); c=cpi.reindex(x.index); r=(x/c*c["2026-06"]).dropna(); mk(k,r,"실질 전년동월비 %")
    nom=float(yoy(S[src].dropna()).loc[out[k]["asof"]]); out[k]["nom"]=round(nom,3)
    out[k]["cpipart"]=round(((1+nom/100)/(1+out[k]["sig"]/100)-1)*100,2)   # 명목 상승률 중 물가 몫
for k,src in [("usd_trade_seo","trade_seo"),("usd_trade_nat","trade_nat")]:     # 달러 환산 = 실거래가지수 / 원달러 월평균, 2026.06=100
    x=S[src].dropna(); f=fxm.reindex(x.index); u=(x/f*f["2026-06"]).dropna(); mk(k,u,"달러 기준 전년동월비 %")
    nom=float(yoy(S[src].dropna()).loc[out[k]["asof"]]); out[k]["nom"]=round(nom,3)
    out[k]["fxpart"]=round(((1+nom/100)/(1+out[k]["sig"]/100)-1)*100,2)    # 원화 상승률 중 환율 몫
out["g_ofr"]=gpack(G["OFR_OFRFSI"]); out["g_ust10"]=gpack(G["DGS10"],"diff"); out["g_jgb10"]=gpack(G["JGB10"],"diff"); out["g_krw"]=gpack(G["DEXKOUS"],"pct")
json.dump(out,open(os.path.join(BASE,"data","data.json"),"w"),ensure_ascii=False)
for k,v in out.items():
    if not k.startswith("_"): print(f"{k:13s} {v['asof']:10s} last={v['last']:<12} sig={v['sig']:<9} pct={v['pct']:<5} from {v['sig_start']}")
print("diff regions",out["_diff_n"],"revj regions",out["_revj_n"])
