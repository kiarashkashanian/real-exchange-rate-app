"""The Sound Money Exchange: a Real Exchange Rate explorer on IMF data.

Satire: a sincere gold-bug / crypto-maximalist persona over standard textbook arithmetic.

Definitions (all monthly):
    S(t)      = units of Country 2 currency per ONE unit of Country 1 currency
    P1, P2    = CPI index levels of Country 1 and Country 2
    RER(t)    = S(t) * P1(t) / P2(t)
    RER*      = mean of RER(t) over valid months in the selected sample
    RealIndex = 100 * RER(t) / RER*

Run:        streamlit run app.py
Self-test:  python app.py --selftest

Assumptions about the IMF SDMX 3.0 API (verify if something breaks; all are
constants or small functions near the top):
  1. Data URL pattern: {BASE}/data/dataflow/IMF.STA/{CPI|ER}/+/{key}
  2. JSON is either SDMX-JSON 1.0 (top-level "structure" + "dataSets") or 2.0
     (everything under "data", with "structures"[0]). Both are handled.
  3. Observations are either series-based (series -> observations) or flat.
  4. Time periods look like "1976-M01" or "1976-01".
  5. XDC_USD is local-currency units per USD (so USD itself = 1).
"""
from __future__ import annotations

import random
import re
import sys
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------------------------------------------------------------
# Constants: fix these first if the IMF changes anything
# --------------------------------------------------------------------------
IMF_BASE = "https://api.imf.org/external/sdmx/3.0"
AGENCY = "IMF.STA"
CPI_FLOW, ER_FLOW = "CPI", "ER"
CPI_KEY = "{iso}.CPI._T.IX.M"
ER_KEY = "{iso}.XDC_USD.PA_RT.M"
CODELIST_URLS = [
    f"{IMF_BASE}/structure/codelist/IMF/CL_COUNTRY/+",
    f"{IMF_BASE}/structure/codelist/IMF/CL_COUNTRY/latest",
]
EURO_AREA = "G163"
START_DATE = date(1976, 1, 1)
TIMEOUT = (5, 25)  # connect, read (seconds)
ACCEPT_HEADERS = ["application/json", "application/vnd.sdmx.data+json;version=2.0.0"]

# Euro adoption year by ISO3 (for the pre-euro warning).
EURO_ADOPTION = {
    EURO_AREA: 1999, "AUT": 1999, "BEL": 1999, "FIN": 1999, "FRA": 1999,
    "DEU": 1999, "IRL": 1999, "ITA": 1999, "LUX": 1999, "NLD": 1999,
    "PRT": 1999, "ESP": 1999, "GRC": 2001, "SVN": 2007, "CYP": 2008,
    "MLT": 2008, "SVK": 2009, "EST": 2011, "LVA": 2014, "LTU": 2015,
    "HRV": 2023,
}

# ISO3 | name | currency code (fallback list, also used for axis labels)
_COUNTRY_TABLE = """
USA|United States|USD
G163|Euro area|EUR
JPN|Japan|JPY
GBR|United Kingdom|GBP
CAN|Canada|CAD
AUS|Australia|AUD
NZL|New Zealand|NZD
CHE|Switzerland|CHF
SWE|Sweden|SEK
NOR|Norway|NOK
DNK|Denmark|DKK
ISL|Iceland|ISK
CHN|China, P.R.: Mainland|CNY
HKG|Hong Kong SAR|HKD
KOR|Korea, Republic of|KRW
IND|India|INR
IDN|Indonesia|IDR
THA|Thailand|THB
MYS|Malaysia|MYR
PHL|Philippines|PHP
SGP|Singapore|SGD
VNM|Vietnam|VND
PAK|Pakistan|PKR
BGD|Bangladesh|BDT
LKA|Sri Lanka|LKR
ISR|Israel|ILS
TUR|Türkiye|TRY
SAU|Saudi Arabia|SAR
ARE|United Arab Emirates|AED
QAT|Qatar|QAR
KWT|Kuwait|KWD
JOR|Jordan|JOD
IRN|Iran|IRR
EGY|Egypt|EGP
ZAF|South Africa|ZAR
NGA|Nigeria|NGN
KEN|Kenya|KES
GHA|Ghana|GHS
MAR|Morocco|MAD
TUN|Tunisia|TND
DZA|Algeria|DZD
ETH|Ethiopia|ETB
BRA|Brazil|BRL
ARG|Argentina|ARS
CHL|Chile|CLP
COL|Colombia|COP
PER|Peru|PEN
MEX|Mexico|MXN
URY|Uruguay|UYU
BOL|Bolivia|BOB
CRI|Costa Rica|CRC
DOM|Dominican Republic|DOP
JAM|Jamaica|JMD
RUS|Russian Federation|RUB
UKR|Ukraine|UAH
POL|Poland|PLN
CZE|Czech Republic|CZK
HUN|Hungary|HUF
ROU|Romania|RON
BGR|Bulgaria|BGN
KAZ|Kazakhstan|KZT
DEU|Germany|EUR
FRA|France|EUR
ITA|Italy|EUR
ESP|Spain|EUR
NLD|Netherlands|EUR
BEL|Belgium|EUR
AUT|Austria|EUR
FIN|Finland|EUR
IRL|Ireland|EUR
PRT|Portugal|EUR
GRC|Greece|EUR
LUX|Luxembourg|EUR
SVN|Slovenia|EUR
SVK|Slovak Republic|EUR
EST|Estonia|EUR
LVA|Latvia|EUR
LTU|Lithuania|EUR
CYP|Cyprus|EUR
MLT|Malta|EUR
HRV|Croatia|EUR
"""
FALLBACK_COUNTRIES: dict[str, str] = {}
CURRENCY: dict[str, str] = {}
for _line in _COUNTRY_TABLE.strip().splitlines():
    _iso, _name, _ccy = _line.split("|")
    FALLBACK_COUNTRIES[_iso] = _name
    CURRENCY[_iso] = _ccy

# --------------------------------------------------------------------------
# Theme and humor: edit here to re-skin the app
# --------------------------------------------------------------------------
TH = {
    "bg": "#0D0B14", "panel": "#17131F", "text": "#F3E7C3",
    "gold": "#F5C542", "orange": "#F7931A", "purple": "#9945FF", "red": "#FF5C5C",
    "page_title": "The Sound Money Exchange",
    "icon": "🪙",
}
# Persona: a sincere gold-bug / crypto maximalist. The jokes are in the confidence.
TXT = {
    "title": "🪙 The Sound Money Exchange ₿",
    "tagline": "The only real exchange rate calculator for people who know that gold and Bitcoin "
               "are the future, and that every currency below is a government IOU in slow "
               "motion collapse. We use their data only to document the crime scene.",
    "h_countries": "Step 1: Pick two doomed fiat currencies (we're documenting the collapse)",
    "h_dates": "Step 2: Choose your sample period (how long you've been robbed)",
    "h_view": "Step 3: Real (the truth), Nominal (the lies), or Both (the whole scam)",
    "h_chart": "Exhibit A: The Fiat Crime Scene",
    "h_download": "Download the evidence (for your case against the central bank)",
    "ticker": [
        "GOLD: 5,000 years undefeated (zero yield, zero problems)",
        "BTC: hard cap of 21 million. Fiat: cap decided at Tuesday's meeting",
        "FIAT: down 99 percent since 1913 (ignore the wages, ignore the GDP)",
        "THE GOLD STANDARD: worked great (do not look up 1929)",
        "NOT YOUR KEYS, NOT YOUR COINS",
        "STABLECOIN: 100 percent backed by trust me bro",
        "TETHER AUDIT: coming soon",
        "CENTRAL BANKERS: seething",
        "VOLATILITY: not a bug, it is price discovery",
        "HAVE FUN STAYING POOR",
    ],
    "loading": [
        "Running a full node on the IMF (and on your last nerve)...",
        "Checking the Fed's homework. It is not gold-backed, so it is wrong...",
        "Mining data (the electricity is worth it, trust me bro)...",
        "Converting your fiat into something real... just kidding, it is still fiat. Loading...",
        "Asking a laser-eyed influencer to verify the data. He says buy...",
    ],
    "empty": "No data. The central bankers are hiding it. (Realistically, the IMF's "
             "coverage is patchy for this series.)",
    "error_prefix": "FUD detected.",
    "same_country": "Same fiat currency twice? That's a double-spend of one IOU. "
                    "Pick two different economies so we can compare two failures.",
    "bad_dates": "Start month is after end month. You cannot go back in time, "
                 "not even with a hardware wallet.",
    "chart_titles": {
        "Real": "Real Index: fiat's purchasing power, exposed (100 = RER*, the sample average)",
        "Nominal": "Nominal S(t): two failing IOUs in a race to the bottom",
        "Both": "Real vs. Nominal: the number goes up, the number goes down, gold stays gold",
    },
    "hline": "100 = RER*, the 'long-run PPP' fiat economists cope with. Gold needs no PPP.",
    "spinner_done": "Data fetched. Satoshi-approved. (Satoshi has not approved this.)",
    "disclosure": "**Not financial advice, but you should absolutely sell your pension and buy "
                  "the dip.** (Please don't. This is satire. The economics in the explainer "
                  "is standard textbook RER, and the arithmetic is real.)",
}


# --------------------------------------------------------------------------
# Parsing and fetching
# --------------------------------------------------------------------------
class IMFError(Exception):
    """Transient problem reaching or reading the IMF API (never cached)."""


_PERIOD_RE = re.compile(r"^(\d{4})[-_]?M?(\d{1,2})$", re.I)


def parse_period(token: object) -> pd.Timestamp:
    """Parse '1976-M01', '1976-01', '197601', or a date string to a month-start Timestamp."""
    t = str(token).strip()
    m = _PERIOD_RE.match(t)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return pd.Timestamp(year=y, month=mo, day=1) if 1 <= mo <= 12 else pd.NaT
    ts = pd.to_datetime(t, errors="coerce")
    return pd.NaT if pd.isna(ts) else ts.to_period("M").to_timestamp()


def _label(v: dict) -> str:
    return str(v.get("id") or v.get("value") or v.get("name") or "")


def _num(v: object) -> float:
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    if isinstance(v, dict):
        v = v.get("value")
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("nan")


def parse_sdmx_json(payload: dict) -> pd.Series:
    """Parse SDMX-JSON 1.0 or 2.0 into a month-start-indexed float Series (may be empty)."""
    empty = pd.Series(dtype=float)
    if not isinstance(payload, dict):
        return empty
    root = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    datasets = root.get("dataSets") or payload.get("dataSets") or []
    structs = root.get("structures") or payload.get("structures") or []
    struct = structs[0] if structs else (root.get("structure") or payload.get("structure") or {})
    obs_dims = (struct.get("dimensions") or {}).get("observation") or []
    if not datasets or not obs_dims:
        return empty
    time_pos = next(
        (i for i, d in enumerate(obs_dims) if str(d.get("id", "")).upper() in ("TIME_PERIOD", "TIME")),
        len(obs_dims) - 1,
    )
    times = [_label(v) for v in obs_dims[time_pos].get("values", [])]
    ds = datasets[0]
    raw: dict[int, float] = {}
    series = ds.get("series") or {}
    if series:  # series-based layout: pick the series with the most observations
        best = max(series.values(), key=lambda s: len(s.get("observations", {})))
        for k, v in best.get("observations", {}).items():
            raw[int(k)] = _num(v)
    else:  # flat layout: keys like "0:5"; keep one consistent non-time signature
        sig0 = None
        for k, v in (ds.get("observations") or {}).items():
            parts = k.split(":")
            idx = int(parts[time_pos]) if len(parts) > 1 else int(parts[0])
            sig = tuple(p for i, p in enumerate(parts) if i != time_pos) if len(parts) > 1 else ()
            sig0 = sig if sig0 is None else sig0
            if sig == sig0:
                raw[idx] = _num(v)
    out = {}
    for idx, val in raw.items():
        if 0 <= idx < len(times):
            ts = parse_period(times[idx])
            if not pd.isna(ts):
                out[ts] = val
    if not out:
        return empty
    s = pd.Series(out, dtype=float).sort_index()
    return s[~s.index.duplicated(keep="last")]


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.8, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def fetch_series(flow: str, key: str) -> tuple[pd.Series, str]:
    """Fetch one IMF series. Returns (series, note). Raises IMFError if the API is unreachable."""
    urls = [f"{IMF_BASE}/data/dataflow/{AGENCY}/{flow}/+/{key}",
            f"{IMF_BASE}/data/dataflow/{AGENCY}/{flow}/latest/{key}"]
    sess, answered, last = _session(), False, "no response"
    for url in urls:
        for accept in ACCEPT_HEADERS:
            try:
                r = sess.get(url, headers={"Accept": accept}, timeout=TIMEOUT)
            except requests.RequestException as e:
                last = f"network problem ({type(e).__name__})"
                continue
            if r.status_code == 404:
                answered = True
                break
            if r.status_code != 200:
                last = f"HTTP {r.status_code}"
                continue
            answered = True
            try:
                s = parse_sdmx_json(r.json())
            except ValueError:
                last = "response was not valid JSON"
                continue
            s = s[s.index >= pd.Timestamp(START_DATE)]
            if not s.empty:
                return s, ""
    if answered:
        return pd.Series(dtype=float), "the IMF has no monthly observations for this series"
    raise IMFError(last)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_series(flow: str, key: str) -> tuple[pd.Series, str]:
    """Cached wrapper. Exceptions (transient failures) are deliberately not cached."""
    return fetch_series(flow, key)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_country_list() -> dict[str, str]:
    """IMF country codelist if reachable and plausible, else the built-in fallback list."""
    sess = _session()
    for url in CODELIST_URLS:
        try:
            r = sess.get(url, headers={"Accept": "application/json"}, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            js = r.json()
            root = js.get("data", js)
            codes = (root.get("codelists") or [{}])[0].get("codes") or []
            found = {}
            for c in codes:
                cid = str(c.get("id", ""))
                names = c.get("names") or {}
                name = names.get("en") if isinstance(names, dict) else None
                name = name or c.get("name") or cid
                if re.fullmatch(r"[A-Z]{3}", cid):
                    found[cid] = str(name)
            if len(found) >= 100:
                found.setdefault("USA", FALLBACK_COUNTRIES["USA"])
                found[EURO_AREA] = "Euro area"
                return found
        except (requests.RequestException, ValueError, AttributeError, IndexError):
            continue
    return dict(FALLBACK_COUNTRIES)


# --------------------------------------------------------------------------
# Pure calculations (no Streamlit): unit-testable
# --------------------------------------------------------------------------
def compute_s(xdc1: pd.Series, xdc2: pd.Series) -> pd.Series:
    """S(t) = units of C2 currency per ONE unit of C1 currency.

    IMF gives local units per USD. C2 per USD / C1 per USD cancels the USD:
        (C2/USD) / (C1/USD) = C2/C1.
    """
    ok = (xdc1 > 0) & (xdc2 > 0)
    return (xdc2 / xdc1).where(ok)


def build_frame(xdc1: pd.Series, xdc2: pd.Series, p1: pd.Series, p2: pd.Series,
                start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Align series over [start, end], compute S, RER, RER* and the Real Index.

    Rows run from the first to the last month in the sample where ANY input exists,
    so months the IMF has not yet published are not counted as 'dropped'. Interior
    gaps are kept as rows and flagged invalid. Nothing is interpolated.
    """
    idx = pd.date_range(start, end, freq="MS")
    df = pd.DataFrame({"xdc_per_usd_c1": xdc1.reindex(idx), "xdc_per_usd_c2": xdc2.reindex(idx),
                       "P1": p1.reindex(idx), "P2": p2.reindex(idx)}, index=idx)
    has_any = df.notna().any(axis=1)
    if not has_any.any():
        return df.iloc[0:0].assign(S=[], RER=[], RER_star=[], real_index=[], valid=[])
    df = df.loc[has_any.idxmax(): has_any[::-1].idxmax()].copy()
    df["S"] = compute_s(df["xdc_per_usd_c1"], df["xdc_per_usd_c2"])
    df["valid"] = df["S"].notna() & (df["P1"] > 0) & (df["P2"] > 0)
    # RER(t) = S(t) * P1(t) / P2(t)
    df["RER"] = (df["S"] * df["P1"] / df["P2"]).where(df["valid"])
    # RER* = sample mean over valid months only; recomputed on every call
    rer_star = df["RER"].mean() if df["valid"].any() else float("nan")
    df["RER_star"] = rer_star
    df["real_index"] = 100.0 * df["RER"] / rer_star
    return df


def euro_notes(iso: str, name: str, start: pd.Timestamp) -> list[str]:
    adopt = EURO_ADOPTION.get(iso)
    if adopt and start.year < adopt:
        return [f"{name}: euro adopted/created in {adopt}, but your sample starts in {start.year}. "
                "Earlier values may reflect a legacy currency (or be missing), so the axis "
                "label 'EUR' may not apply to the early months."]
    return []


def currency_label(iso: str, countries: dict[str, str]) -> str:
    return CURRENCY.get(iso) or f"{countries.get(iso, iso)} currency"


# --------------------------------------------------------------------------
# Plotting
# --------------------------------------------------------------------------
def make_figure(df: pd.DataFrame, mode: str, s_label: str) -> go.Figure:
    """Real, Nominal, or Both (dual axes: Real left, Nominal right)."""
    real_c, nom_c = TH["gold"], TH["orange"]
    both = mode == "Both"
    fig = make_subplots(specs=[[{"secondary_y": True}]]) if both else go.Figure()
    kw = {"secondary_y": False} if both else {}
    if mode in ("Real", "Both"):
        fig.add_trace(go.Scatter(x=df.index, y=df["real_index"], name="Real Index (100 = RER*)",
                                 mode="lines", line=dict(color=real_c, width=2.5),
                                 hovertemplate="%{y:.2f}"), **kw)
        fig.add_trace(go.Scatter(x=[df.index.min(), df.index.max()], y=[100, 100], mode="lines",
                                 line=dict(color=TH["purple"], dash="dash", width=1.5),
                                 showlegend=False, hoverinfo="skip"), **kw)
        fig.add_annotation(xref="paper", yref="y", x=0.0, y=100, text=TXT["hline"],
                           showarrow=False, xanchor="left", yanchor="bottom",
                           font=dict(color=TH["purple"], size=11))
    if mode in ("Nominal", "Both"):
        extra = {"secondary_y": True} if both else {}
        fig.add_trace(go.Scatter(x=df.index, y=df["S"], name=f"Nominal S(t): {s_label}",
                                 mode="lines", line=dict(color=nom_c, width=2.2),
                                 hovertemplate="%{y:,.4f}"), **extra)
    fig.update_layout(
        title=TXT["chart_titles"][mode], template="plotly_dark", hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=TH["panel"], font=dict(color=TH["text"]),
        xaxis=dict(rangeslider=dict(visible=True), title="Month"),
        legend=dict(orientation="h", y=1.12), height=560, margin=dict(t=100),
    )
    if mode == "Real":
        fig.update_yaxes(title_text="Real Index (100 = sample-average RER*)",
                         title_font_color=real_c, tickfont_color=real_c)
    elif mode == "Nominal":
        fig.update_yaxes(title_text=s_label, title_font_color=nom_c, tickfont_color=nom_c)
    else:
        fig.update_yaxes(title_text="Real Index (100 = RER*)", title_font_color=real_c,
                         tickfont_color=real_c, secondary_y=False)
        fig.update_yaxes(title_text=s_label, title_font_color=nom_c, tickfont_color=nom_c,
                         secondary_y=True, showgrid=False)
    return fig


# --------------------------------------------------------------------------
# Theme injection and UI
# --------------------------------------------------------------------------
def inject_theme() -> None:
    css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Space+Mono&display=swap');
    .stApp { background: radial-gradient(circle at 20% 0%, #2a1d05 0%, __BG__ 45%),
                         linear-gradient(135deg, __BG__, #120a24); color: __TEXT__;
             font-family: 'Space Mono', monospace; }
    h1, h2, h3 { font-family: 'Playfair Display', Georgia, serif !important; color: __GOLD__ !important; }
    h1 { text-shadow: 0 0 18px rgba(247,147,26,.55); }
    .stApp p, .stApp label, [data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] { color: __TEXT__; }
    [data-testid="stSidebar"] { background: __PANEL__; border-right: 2px solid __GOLD__; }
    [data-testid="stMetricValue"] { color: __GOLD__; font-family: 'Space Mono', monospace; }
    [data-testid="stMetricLabel"] p { color: __ORANGE__; }
    .ticker { overflow: hidden; white-space: nowrap; background: #000; border: 1px solid __GOLD__;
              border-radius: 6px; padding: 6px 0; margin-bottom: 14px; }
    .ticker span { display: inline-block; padding-left: 100%; animation: tick 60s linear infinite;
                   color: __ORANGE__; font-family: 'Space Mono', monospace; font-size: .85rem; }
    @keyframes tick { 0% { transform: translateX(0); } 100% { transform: translateX(-100%); } }
    .tagline { color: __PURPLE__; font-style: italic; margin-top: -10px; }
    </style>"""
    for k in ("BG", "TEXT", "GOLD", "PANEL", "ORANGE", "PURPLE"):
        css = css.replace(f"__{k}__", TH[k.lower()])
    st.markdown(css, unsafe_allow_html=True)


def render_header() -> None:
    items = "  \u2022  ".join(TXT["ticker"])
    st.markdown(f'<div class="ticker"><span>{items}</span></div>', unsafe_allow_html=True)
    st.title(TXT["title"])
    st.markdown(f'<p class="tagline">{TXT["tagline"]}</p>', unsafe_allow_html=True)


def safe_load(flow: str, key: str, what: str, warnings: list[str]) -> pd.Series:
    """Load a series; on any failure record a plain-language reason and return empty."""
    try:
        s, note = load_series(flow, key)
        if s.empty:
            warnings.append(f"{what}: {note or 'no data returned'}.")
        return s
    except IMFError as e:
        warnings.append(f"{what}: could not reach/read the IMF API ({e}). Try again shortly.")
    except Exception as e:  # never crash the app
        warnings.append(f"{what}: unexpected problem ({type(e).__name__}).")
    return pd.Series(dtype=float)


def main() -> None:
    st.set_page_config(page_title=TH["page_title"], page_icon=TH["icon"], layout="wide")
    inject_theme()
    render_header()

    countries = load_country_list()
    ids = sorted(countries, key=lambda k: countries[k])

    with st.sidebar:
        st.header("📜 How to read this (sound money edition)")
        st.markdown(
            "- **Real Index > 100:** Country 1's goods are relatively *expensive* vs. Country 2's, "
            "compared with the sample average (real appreciation of Country 1's currency). "
            "Gold bugs read this as 'one IOU is rotting slower than the other.'\n"
            "- **Real Index < 100:** real depreciation of Country 1's currency. Gold bugs read "
            "this as 'told you so.' (They read everything that way.)\n"
            "- CPI base years differ across countries, so the index is normalized to the "
            "sample-average RER*. We use fiat CPI only to document the crime scene.\n"
            "- **S(t)** = Country 2 currency units per 1 Country 1 currency unit.\n"
            "- PPP holds in the long run. Gold bugs: 'the long run is now.' "
            "Economists: 'the long run is long.'"
        )
        with st.expander("Why gold and Bitcoin are better (an incomplete list)"):
            st.markdown(
                "- **Gold:** 5,000 years of price stability.* (*Not measured. Please do not measure.)\n"
                "- **Bitcoin:** hard cap of 21 million, so deflation is not a problem, "
                "it is called 'appreciation.'\n"
                "- **Volatility:** not a bug, price discovery.\n"
                "- **Real exchange rates:** unnecessary if everyone just used gold. "
                "This app would not exist. Please enjoy it while it lasts."
            )
        st.divider()
        st.markdown(TXT["disclosure"])

    st.subheader(TXT["h_countries"])
    fmt = lambda k: f"{countries[k]} ({k})"  # noqa: E731
    col1, col2 = st.columns(2)
    iso1 = col1.selectbox("Country 1 (the 'base' currency)", ids, format_func=fmt,
                          index=ids.index("USA") if "USA" in ids else 0)
    iso2 = col2.selectbox("Country 2 (the 'quote' currency)", ids, format_func=fmt,
                          index=ids.index("JPN") if "JPN" in ids else 1)

    st.subheader(TXT["h_dates"])
    today = date.today()
    dcol1, dcol2 = st.columns(2)
    start_d = dcol1.date_input("Start month (any day in the month)", value=date(2000, 1, 1),
                               min_value=START_DATE, max_value=today)
    end_d = dcol2.date_input("End month (any day in the month)", value=today.replace(day=1),
                             min_value=START_DATE, max_value=today)

    st.subheader(TXT["h_view"])
    mode = st.radio("Chart", ["Real", "Nominal", "Both"], horizontal=True, label_visibility="collapsed")

    if iso1 == iso2:
        st.error(TXT["same_country"])
        st.stop()
    start = pd.Timestamp(start_d).to_period("M").to_timestamp()
    end = pd.Timestamp(end_d).to_period("M").to_timestamp()
    if start > end:
        st.error(TXT["bad_dates"])
        st.stop()

    name1, name2 = countries[iso1], countries[iso2]
    warnings: list[str] = []
    with st.spinner(random.choice(TXT["loading"])):
        p1 = safe_load(CPI_FLOW, CPI_KEY.format(iso=iso1), f"CPI for {name1}", warnings)
        p2 = safe_load(CPI_FLOW, CPI_KEY.format(iso=iso2), f"CPI for {name2}", warnings)
        x1 = safe_load(ER_FLOW, ER_KEY.format(iso=iso1), f"Exchange rate for {name1}", warnings)
        x2 = safe_load(ER_FLOW, ER_KEY.format(iso=iso2), f"Exchange rate for {name2}", warnings)

    # USD per USD is 1 by construction; handle explicitly if the API returns nothing.
    if iso1 == "USA" and x1.empty and not p1.empty:
        x1 = pd.Series(1.0, index=p1.index)
        warnings = [w for w in warnings if not w.startswith(f"Exchange rate for {name1}")]
    if iso2 == "USA" and x2.empty and not p2.empty:
        x2 = pd.Series(1.0, index=p2.index)
        warnings = [w for w in warnings if not w.startswith(f"Exchange rate for {name2}")]

    for w in warnings:
        st.warning(w)
    if any(s.empty for s in (p1, p2, x1, x2)):
        st.error(f"{TXT['error_prefix']} {TXT['empty']} At least one required series is missing "
                 "(see warnings above), so RER cannot be computed for this pair.")
        st.stop()

    for note in euro_notes(iso1, name1, start) + euro_notes(iso2, name2, start):
        st.info(note)

    df = build_frame(x1, x2, p1, p2, start, end)
    n_valid = int(df["valid"].sum()) if not df.empty else 0
    if n_valid == 0:
        st.error(f"{TXT['empty']} The four series have no overlapping valid months in "
                 f"{start:%b %Y} to {end:%b %Y}. Try a different window or pair.")
        st.stop()

    s_label = f"{currency_label(iso2, countries)} per 1 {currency_label(iso1, countries)}"
    rer_star = float(df["RER_star"].iloc[0])
    n_drop = int((~df["valid"]).sum())

    st.subheader(TXT["h_chart"])
    m = st.columns(5)
    m[0].metric("RER* (sample mean)", f"{rer_star:,.4f}")
    m[1].metric("Valid months", f"{n_valid}")
    m[2].metric("Dropped months", f"{n_drop}", help="Months the central bank deleted (or the IMF did not report).")
    last = df["real_index"].dropna()
    m[3].metric("Latest Real Index", f"{last.iloc[-1]:.2f}")
    m[4].metric("Fiat volatility range (max - min)", f"{last.max() - last.min():.1f} pts", help="Gold bugs call this the scam. Economists call it variation.")
    st.caption(f"Rows span {df.index.min():%b %Y} to {df.index.max():%b %Y} (where any data exists). "
               f"Dropped months are missing at least one of S, P1, P2; nothing is interpolated. "
               f"{TXT['spinner_done']}")
    st.plotly_chart(make_figure(df, mode, s_label), use_container_width=True)

    st.subheader(TXT["h_download"])
    out = df.copy()
    out.index.name = "date"
    out = out.reset_index()
    out.insert(1, "country1_iso3", iso1)
    out.insert(2, "country2_iso3", iso2)
    out = out.rename(columns={"xdc_per_usd_c1": "C1_XDC_per_USD", "xdc_per_usd_c2": "C2_XDC_per_USD",
                              "S": "S_C2_per_1_C1", "valid": "valid_month"})
    out = out[["date", "country1_iso3", "country2_iso3", "C1_XDC_per_USD", "C2_XDC_per_USD",
               "S_C2_per_1_C1", "P1", "P2", "RER", "RER_star", "real_index", "valid_month"]]
    st.download_button("⬇️ Download CSV (every observation and calculation)",
                       out.to_csv(index=False).encode("utf-8"),
                       file_name=f"rer_{iso1}_{iso2}_{start:%Y%m}_{end:%Y%m}.csv", mime="text/csv")
    with st.expander("Peek at the ledger (it is basically the blockchain, but a CSV)"):
        st.dataframe(out.tail(24), use_container_width=True)


# --------------------------------------------------------------------------
# Self-tests: python app.py --selftest
# --------------------------------------------------------------------------
def run_self_tests() -> None:
    idx = pd.date_range("2000-01-01", periods=6, freq="MS")
    usd = pd.Series(1.0, index=idx)
    jpy = pd.Series([100, 110, 120, 130, 140, 150.0], index=idx)
    p1 = pd.Series([100, 101, 102, 103, 104, 105.0], index=idx)
    p2 = pd.Series([100, 100, 100, 100, 100, 100.0], index=idx)
    # Direction: C1 = USA, C2 = JPN -> S = JPY per USD
    assert (compute_s(usd, jpy) == jpy).all()
    # Swapped: S = USD per JPY
    assert abs(compute_s(jpy, usd).iloc[0] - 0.01) < 1e-12
    # Real index averages exactly 100 over valid months, with a gap dropped
    p2g = p2.copy()
    p2g.iloc[2] = float("nan")
    df = build_frame(usd, jpy, p1, p2g, idx[0], idx[-1])
    assert int(df["valid"].sum()) == 5 and int((~df["valid"]).sum()) == 1
    assert abs(df.loc[df["valid"], "real_index"].mean() - 100) < 1e-9
    # RER* changes when the window changes
    df2 = build_frame(usd, jpy, p1, p2, idx[2], idx[-1])
    df3 = build_frame(usd, jpy, p1, p2, idx[0], idx[-1])
    assert df2["RER_star"].iloc[0] != df3["RER_star"].iloc[0]
    # Period parsing
    assert parse_period("1976-M01") == pd.Timestamp(1976, 1, 1)
    assert parse_period("1976-12") == pd.Timestamp(1976, 12, 1)
    # SDMX-JSON 2.0 (series layout) and 1.0 (flat layout)
    times = [{"id": "1976-M01"}, {"id": "1976-M02"}]
    v2 = {"data": {"dataSets": [{"series": {"0:0": {"observations": {"0": [1.5], "1": [2.5]}}}}],
                   "structures": [{"dimensions": {"observation": [{"id": "TIME_PERIOD", "values": times}]}}]}}
    v1 = {"dataSets": [{"observations": {"0:0": [1.5], "0:1": [2.5]}}],
          "structure": {"dimensions": {"observation": [{"id": "COUNTRY", "values": [{"id": "USA"}]},
                                                       {"id": "TIME_PERIOD", "values": times}]}}}
    for payload in (v2, v1):
        s = parse_sdmx_json(payload)
        assert list(s.values) == [1.5, 2.5] and s.index[0] == pd.Timestamp(1976, 1, 1)
    print("All self-tests passed.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        run_self_tests()
    else:
        main()
