# The Barbarous Relic Exchange 🪙₿

A Streamlit app that computes and plots the **real exchange rate (RER)** between any two IMF economies (or the Euro area) from monthly IMF CPI and exchange-rate data. The skin is a satire of gold bugs and crypto bros. The arithmetic is not.

## What it does

- Pick Country 1 and Country 2 (IMF countries plus the Euro area, `G163`).
- Pick a start and end month (data from January 1976 where available).
- See the **Real Index**, the nominal exchange rate **S(t)**, or **Both** (dual axes) in interactive Plotly charts.
- Download a CSV of every observation and calculation in the sample, including dropped months flagged as invalid.

## Formulas

- `S(t)` = units of Country 2 currency per one unit of Country 1 currency. The IMF reports local currency per USD, so `S = (C2 per USD) / (C1 per USD)`.
- `P1(t)`, `P2(t)` = monthly CPI index levels.
- `RER(t) = S(t) × P1(t) / P2(t)`
- `RER*` = average of `RER(t)` over **valid months** in the selected sample (a month is valid only if S, P1 and P2 all exist and are positive). Recomputed whenever countries or dates change.
- `Real Index(t) = 100 × RER(t) / RER*`
- Nominal S(t) is plotted in actual currency units, never normalized.

Real Index above 100 means Country 1's goods are relatively expensive versus the sample average (real appreciation of Country 1's currency); below 100 means real depreciation. CPI base years differ across countries, which is why the index is normalized to `RER*`.

## Data sources

IMF SDMX 3.0 API: `https://api.imf.org/external/sdmx/3.0`

| Series | Key pattern |
|---|---|
| Monthly CPI index | `{ISO3}.CPI._T.IX.M` (dataflow `IMF.STA/CPI`) |
| Exchange rate, local currency per USD | `{ISO3}.XDC_USD.PA_RT.M` (dataflow `IMF.STA/ER`) |

The Euro area code is `G163`. The United States has `XDC_USD = 1` by construction; the app fills this in if the API returns nothing for it. No data is interpolated or invented.

## Install and run (Python 3.12)

```bash
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Run the built-in checks (S(t) direction, Real Index averaging to 100, SDMX parsing):

```bash
python app.py --selftest
```

Tip: Streamlit follows your system light/dark mode. For the intended look, create `.streamlit/config.toml` with:

```toml
[theme]
base = "dark"
```

## Changing the theme

All colors are in the `TH` dictionary and all jokes, titles, headings, loading messages and chart titles are in the `TXT` dictionary near the top of `app.py`. Edit them freely. Fonts are loaded in `inject_theme()`.

## Assumptions about the IMF API

The app was written without a guarantee of the live API's exact shape, so it is tolerant: it tries two URL variants, accepts SDMX-JSON 1.0 and 2.0, series-based and flat observation layouts, and `1976-M01` / `1976-01` period formats. If the IMF changes paths or dataflow IDs, edit the constants at the top of `app.py` (`IMF_BASE`, `AGENCY`, `CPI_FLOW`, `ER_FLOW`, `CPI_KEY`, `ER_KEY`, `CODELIST_URLS`).

## Known limitations

- IMF coverage varies: some countries lack monthly CPI or exchange rates, or start late. The app says which series is missing.
- Rows span only the months in your sample where at least one input exists. Interior gaps are listed as dropped months.
- If the IMF country codelist cannot be fetched, a built-in list of about 80 economies is used. A fetched list may include entities with no data.
- Euro-area transitions: before adoption, a country's exchange rate may be in a legacy currency (or absent). The app shows a note and the axis label may say EUR anyway.
- CPI levels from different countries have different base years; only the normalized Real Index is comparable across pairs.
- API rate limits, outages or format changes may produce warnings. Results are cached for 6 hours; failures are not cached.
- RER* is a sample average, not a theoretical equilibrium. PPP holds in the long run, apparently.

## Prompt used / model / date

- Prompt: _(fill in)_
- Model: _(fill in)_
- Date: _(fill in)_
