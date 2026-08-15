import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

IST = ZoneInfo("Asia/Kolkata")


def now_ist():
    return datetime.now(IST)

# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="Nifty50 Pre-Market Dashboard",
    layout="wide"
)

UP_COLOR = "#2ecc71"
DOWN_COLOR = "#e74c3c"
BG_COLOR = "#ffffff"
TEXT_COLOR = "#1a1a1a"

# ============================================================
# NSE PAGES
# ============================================================

NSE_HOME = "https://www.nseindia.com/"

MOST_ACTIVE_PAGE = (
    "https://www.nseindia.com/market-data/"
    "most-active-contracts"
)

EQUITY_PAGE = (
    "https://www.nseindia.com/market-data/"
    "top-gainers-losers"
)

# IMPORTANT:
# This is the normal EQUITY pre-open page.
# DO NOT CHANGE THIS.
PREOPEN_PAGE = (
    "https://www.nseindia.com/market-data/"
    "pre-open-market-cotation"
)

# Separate F&O pre-open page
DERIVATIVE_PREOPEN_PAGE = (
    "https://www.nseindia.com/market-data/"
    "pre-open-market-fno"
)

# ============================================================
# NSE API URLS
# ============================================================

DERIV_URLS = {
    "futures":
        "https://www.nseindia.com/api/"
        "snapshot-derivatives-equity?index=futures",

    "options":
        "https://www.nseindia.com/api/"
        "snapshot-derivatives-equity?index=options&limit=20",

    "calls":
        "https://www.nseindia.com/api/"
        "snapshot-derivatives-equity?index=calls-stocks-vol",

    "puts":
        "https://www.nseindia.com/api/"
        "snapshot-derivatives-equity?index=puts-stocks-vol",
}

EQUITY_URL = (
    "https://www.nseindia.com/api/"
    "live-analysis-variations"
)

# ============================================================
# EQUITY PRE-MARKET API
# ============================================================

# IMPORTANT:
# This remains the ORIGINAL equity pre-market API.
PREOPEN_URL_TEMPLATE = (
    "https://www.nseindia.com/api/"
    "market-data-pre-open?key={key}"
)

# ============================================================
# DERIVATIVE PRE-OPEN API
# ============================================================

# NSE F&O pre-open API
DERIVATIVE_PREOPEN_URL = (
    "https://www.nseindia.com/api/"
    "market-data-pre-open?key=FO"
)

# ============================================================
# SETTINGS
# ============================================================

KEY_OPTIONS = [
    "NIFTY",
    "BANKNIFTY",
    "NIFTYNEXT50",
    "FNO",
    "ALL",
    "SME",
    "OTHERS"
]

INDEX_UNDERLYINGS = {
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "NIFTYIT",
    "MIDCPNIFTY",
    "NIFTYNXT50",
    "NIFTYMIDCAPSELECT"
}

# ============================================================
# NSE SESSION
# ============================================================

@st.cache_resource(ttl=300, show_spinner=False)
def get_nse_session():

    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": MOST_ACTIVE_PAGE,
        "Connection": "keep-alive",
    })

    try:
        session.get(NSE_HOME, timeout=10)
        session.get(MOST_ACTIVE_PAGE, timeout=10)
    except requests.RequestException:
        pass

    return session


def fetch_json(session, url, referer=None):

    old_referer = session.headers.get("Referer")

    if referer:
        session.headers["Referer"] = referer

    try:

        response = session.get(url, timeout=20)

        if response.status_code in (401, 403):

            session.cookies.clear()
            get_nse_session.clear()

            session.get(NSE_HOME, timeout=10)

            if referer:
                session.get(referer, timeout=10)

            response = session.get(url, timeout=20)

        response.raise_for_status()

        return response.json()

    finally:

        if old_referer:
            session.headers["Referer"] = old_referer
        else:
            session.headers.pop("Referer", None)


# ============================================================
# HELPERS
# ============================================================

def get_field(record, *keys, default=None):

    if not isinstance(record, dict):
        return default

    for key in keys:

        if key in record and record[key] not in (None, ""):
            return record[key]

    lower = {
        str(k).lower(): v
        for k, v in record.items()
    }

    for key in keys:

        value = lower.get(str(key).lower())

        if value not in (None, ""):
            return value

    return default


def to_num(value):

    try:

        if value in (None, "", "-"):
            return None

        return float(
            str(value).replace(",", "")
        )

    except (TypeError, ValueError):

        return None


def option_type(value):

    value = str(value or "").strip().upper()

    if value in ("CALL", "CE"):
        return "CE"

    if value in ("PUT", "PE"):
        return "PE"

    return value or "-"


# ============================================================
# "FIRST SEEN" TRACKING
# ============================================================
#
# Adds a "First Seen" column right next to Symbol that records
# the clock time a symbol FIRST appeared in a given list.
#
# - It does NOT keep updating on every refresh while the symbol
#   stays in the list, so you can glance at it and immediately
#   see which stocks are new vs. ones that have been sitting
#   there for a while.
# - If a symbol drops out of the list and later comes back, it
#   is treated as "new" again and gets a fresh timestamp.
#
# This relies on st.session_state, which only persists across
# Streamlit *reruns* (not full browser page reloads). That's why
# auto-refresh below uses streamlit-autorefresh (a proper
# Streamlit rerun) instead of a JavaScript window.location.reload().
# ============================================================

def track_first_seen(
    df,
    list_key,
    symbol_col="Symbol"
):

    if df is None or df.empty or symbol_col not in df.columns:
        return df

    store_key = f"first_seen__{list_key}"

    if store_key not in st.session_state:
        st.session_state[store_key] = {}

    seen = st.session_state[store_key]

    now = now_ist()

    current_symbols = set(df[symbol_col])

    # Record a timestamp the first time we see a symbol
    for symbol in current_symbols:
        if symbol not in seen:
            seen[symbol] = now

    # Forget symbols that fell out of the list, so that if they
    # reappear later they're flagged as new again
    for symbol in list(seen.keys()):
        if symbol not in current_symbols:
            del seen[symbol]

    df = df.copy()

    df.insert(
        df.columns.get_loc(symbol_col) + 1,
        "First Seen",
        df[symbol_col].map(
            lambda s: seen.get(s, now).strftime("%H:%M:%S")
        )
    )

    return df


# ============================================================
# EQUITY PRE-MARKET
# ============================================================

def fetch_preopen(session, key):

    url = PREOPEN_URL_TEMPLATE.format(key=key)

    return fetch_json(
        session,
        url,
        PREOPEN_PAGE
    )


def make_preopen_df(raw, limit=None):

    rows = []

    if not isinstance(raw, dict):
        return pd.DataFrame()

    for item in raw.get("data", []):

        metadata = item.get("metadata", {})

        symbol = metadata.get("symbol")

        if not symbol:
            continue

        rows.append({
            "symbol": symbol,
            "price": to_num(
                metadata.get("lastPrice")
            ),
            "change": to_num(
                metadata.get("pChange")
            ),
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df = (
        df
        .dropna(subset=["change"])
        .sort_values(
            "change",
            ascending=True
        )
        .reset_index(drop=True)
    )

    if limit:

        half = limit // 2

        df = pd.concat([
            df.head(half),
            df.tail(half)
        ]).drop_duplicates(
            subset="symbol"
        ).sort_values(
            "change"
        ).reset_index(drop=True)

    return df


# ============================================================
# DERIVATIVES PRE-OPEN
# ============================================================

def fetch_derivative_preopen(session):

    return fetch_json(
        session,
        DERIVATIVE_PREOPEN_URL,
        DERIVATIVE_PREOPEN_PAGE
    )


def extract_derivative_preopen_records(raw):

    records = []

    if not isinstance(raw, dict):
        return records

    # Try common NSE structures
    for key in (
        "data",
        "FUTSTK",
        "futures",
        "FO"
    ):

        block = raw.get(key)

        if isinstance(block, list):

            records.extend(block)

        elif isinstance(block, dict):

            data = block.get("data")

            if isinstance(data, list):
                records.extend(data)

    # Search nested dictionaries
    if not records:

        for value in raw.values():

            if isinstance(value, dict):

                data = value.get("data")

                if isinstance(data, list):
                    records.extend(data)

    return records


def make_derivative_preopen_df(raw):

    records = extract_derivative_preopen_records(raw)

    rows = []

    for record in records:

        if not isinstance(record, dict):
            continue

        # NSE F&O pre-open can have metadata nested inside
        metadata = record.get(
            "metadata",
            record
        )

        if not isinstance(metadata, dict):
            metadata = record

        symbol = get_field(
            metadata,
            "symbol",
            "underlying",
            "underlyingSymbol"
        )

        if not symbol:
            continue

        instrument = str(
            get_field(
                metadata,
                "instrumentType",
                "instrument_type",
                "instrument",
                default=""
            )
        ).upper()

        # We only want STOCK FUTURES
        if instrument and instrument not in (
            "FUTSTK",
            "STOCK FUTURES",
            "FUTURE"
        ):
            continue

        expiry = get_field(
            metadata,
            "expiryDate",
            "expiry_date",
            "expiry"
        )

        ltp = to_num(
            get_field(
                metadata,
                "lastPrice",
                "ltp"
            )
        )

        change = to_num(
            get_field(
                metadata,
                "change",
                "netChange",
                "chng"
            )
        )

        pchange = to_num(
            get_field(
                metadata,
                "pChange",
                "perChange",
                "percentChange"
            )
        )

        open_price = to_num(
            get_field(
                metadata,
                "open",
                "openPrice",
                "open_price"
            )
        )

        high = to_num(
            get_field(
                metadata,
                "high",
                "highPrice",
                "high_price"
            )
        )

        low = to_num(
            get_field(
                metadata,
                "low",
                "lowPrice",
                "low_price"
            )
        )

        volume = to_num(
            get_field(
                metadata,
                "totalTradedVolume",
                "tradedVolume",
                "volume",
                "numberOfContractsTraded"
            )
        )

        value = to_num(
            get_field(
                metadata,
                "totalTurnover",
                "turnover",
                "value"
            )
        )

        oi = to_num(
            get_field(
                metadata,
                "openInterest",
                "oi"
            )
        )

        rows.append({
            "Symbol": str(symbol).strip(),
            "Expiry": expiry,
            "LTP": ltp,
            "Chng": change,
            "% Chng": pchange,
            "Open": open_price,
            "High": high,
            "Low": low,
            "Volume": volume,
            "Value": value,
            "Open Interest": oi,
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    if "% Chng" in df.columns:

        df = df.sort_values(
            "% Chng",
            ascending=False,
            na_position="last"
        )

    return (
        df
        .drop_duplicates(
            subset=["Symbol", "Expiry"]
        )
        .head(20)
        .reset_index(drop=True)
    )


# ============================================================
# DERIVATIVE RESPONSE PARSING
# ============================================================

def extract_records(raw, kind):

    if not isinstance(raw, dict):
        return []

    if kind in ("calls", "puts"):

        optstk = raw.get("OPTSTK")

        if isinstance(optstk, dict):

            data = optstk.get("data")

            if isinstance(data, list):
                return data

    volume = raw.get("volume")

    if isinstance(volume, dict):

        data = volume.get("data")

        if isinstance(data, list):
            return data

    for key in (
        "FUTSTK",
        "OPTSTK",
        "data"
    ):

        block = raw.get(key)

        if isinstance(block, dict):

            data = block.get("data")

            if isinstance(data, list):
                return data

        if isinstance(block, list):
            return block

    for value in raw.values():

        if isinstance(value, dict):

            data = value.get("data")

            if isinstance(data, list):
                return data

    return []


# ============================================================
# NORMALIZE DERIVATIVES
# ============================================================

def normalize_derivatives(records, kind):

    rows = []

    for record in records:

        if not isinstance(record, dict):
            continue

        instrument = str(
            get_field(
                record,
                "instrumentType",
                "instrument_type",
                default=""
            )
        ).upper()

        if kind == "futures" and instrument:

            if instrument != "FUTSTK":
                continue

        if kind in (
            "options",
            "calls",
            "puts"
        ) and instrument:

            if instrument != "OPTSTK":
                continue

        symbol = get_field(
            record,
            "symbol",
            "underlying",
            "underlyingSymbol"
        )

        if not symbol:
            continue

        symbol = str(symbol).strip()

        if symbol.upper() in INDEX_UNDERLYINGS:
            continue

        volume = to_num(
            get_field(
                record,
                "numberOfContractsTraded",
                "tradedVolume",
                "volume",
                "totalTradedVolume"
            )
        )

        turnover = to_num(
            get_field(
                record,
                "totalTurnover",
                "value",
                "turnover"
            )
        )

        row = {
            "Symbol": symbol,

            "Expiry": get_field(
                record,
                "expiryDate",
                "expiry_date",
                "expiry"
            ),

            "LTP": to_num(
                get_field(
                    record,
                    "lastPrice",
                    "ltp"
                )
            ),

            "Chng": to_num(
                get_field(
                    record,
                    "change",
                    "netChange",
                    "chng"
                )
            ),

            "% Chng": to_num(
                get_field(
                    record,
                    "pChange",
                    "perChange",
                    "percentChange"
                )
            ),

            "Volume (Contracts)": volume,

            "Value (₹ Cr)": turnover,

            "OI": to_num(
                get_field(
                    record,
                    "openInterest",
                    "oi"
                )
            ),

            "Chg in OI": to_num(
                get_field(
                    record,
                    "changeInOpenInterest",
                    "changeinOpenInterest",
                    "changeInOI"
                )
            ),
        }

        if kind in (
            "options",
            "calls",
            "puts"
        ):

            row["Type"] = option_type(
                get_field(
                    record,
                    "optionType",
                    "option_type",
                    "type"
                )
            )

            row["Strike"] = to_num(
                get_field(
                    record,
                    "strikePrice",
                    "strike"
                )
            )

        rows.append(row)

    return rows


def make_derivative_df(
    records,
    kind,
    top_n=20
):

    rows = normalize_derivatives(
        records,
        kind
    )

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    if "Volume (Contracts)" in df.columns:

        df = df.sort_values(
            "Volume (Contracts)",
            ascending=False,
            na_position="last"
        )

    if kind in (
        "options",
        "calls",
        "puts"
    ):

        columns = [
            "Symbol",
            "Type",
            "Strike",
            "Expiry",
            "LTP",
            "Chng",
            "% Chng",
            "Volume (Contracts)",
            "Value (₹ Cr)",
            "OI",
            "Chg in OI",
        ]

    else:

        columns = [
            "Symbol",
            "Expiry",
            "LTP",
            "Chng",
            "% Chng",
            "Volume (Contracts)",
            "Value (₹ Cr)",
            "OI",
            "Chg in OI",
        ]

    columns = [
        c for c in columns
        if c in df.columns
    ]

    return (
        df[columns]
        .head(top_n)
        .reset_index(drop=True)
    )


# ============================================================
# STYLING
# ============================================================

def _change_color(value):

    try:

        value = float(value)

        if value > 0:
            return (
                f"color: {UP_COLOR}; "
                "font-weight: 600;"
            )

        if value < 0:
            return (
                f"color: {DOWN_COLOR}; "
                "font-weight: 600;"
            )

    except Exception:
        pass

    return ""


# ============================================================
# DERIVATIVE PRE-OPEN TABLE
# ============================================================

def style_derivative_preopen_table(df):

    if df.empty:
        return df

    styler = df.style

    for column in (
        "Chng",
        "% Chng"
    ):

        if column in df.columns:

            styler = styler.map(
                _change_color,
                subset=[column]
            )

    formats = {}

    for column in (
        "LTP",
        "Chng",
        "% Chng",
        "Open",
        "High",
        "Low"
    ):

        if column in df.columns:
            formats[column] = "{:,.2f}"

    for column in (
        "Volume",
        "Open Interest"
    ):

        if column in df.columns:
            formats[column] = "{:,.0f}"

    if "Value" in df.columns:
        formats["Value"] = "{:,.2f}"

    return styler.format(
        formats,
        na_rep="-"
    )


def render_derivative_preopen_table(df):

    st.subheader(
        "📋 Derivatives Pre-Open Market — Stock Futures"
    )

    if df.empty:

        st.info(
            "No stock futures pre-open data "
            "returned by NSE."
        )

        return

    df = track_first_seen(
        df,
        "deriv_preopen_futures"
    )

    st.dataframe(
        style_derivative_preopen_table(df),
        use_container_width=True,
        hide_index=True,
        height=600
    )


# ============================================================
# LOAD STOCK OPTIONS
# ============================================================

def load_stock_options(session):

    first_df = pd.DataFrame()
    first_raw = None

    try:

        first_raw = fetch_json(
            session,
            DERIV_URLS["options"],
            MOST_ACTIVE_PAGE
        )

        first_records = extract_records(
            first_raw,
            "options"
        )

        first_df = make_derivative_df(
            first_records,
            "options",
            20
        )

        if len(first_df) > 0:

            return {
                "df": first_df,
                "raw": first_raw,
                "source":
                    "NSE options snapshot",
                "error": None,
            }

    except Exception:
        pass

    combined = []
    raw_parts = {}

    for kind in (
        "calls",
        "puts"
    ):

        try:

            raw = fetch_json(
                session,
                DERIV_URLS[kind],
                MOST_ACTIVE_PAGE
            )

            raw_parts[kind] = raw

            combined.extend(
                extract_records(
                    raw,
                    kind
                )
            )

        except Exception:
            continue

    fallback_df = make_derivative_df(
        combined,
        "options",
        20
    )

    if not fallback_df.empty:

        return {
            "df": fallback_df,
            "raw": raw_parts,
            "source":
                "NSE stock calls + puts fallback",
            "error": None,
        }

    return {
        "df": first_df,
        "raw": first_raw,
        "source":
            "NSE options snapshot",
        "error": None,
    }


# ============================================================
# LOAD DERIVATIVES
# ============================================================

def load_derivatives():

    session = get_nse_session()

    result = {}

    try:

        raw = fetch_json(
            session,
            DERIV_URLS["futures"],
            MOST_ACTIVE_PAGE
        )

        result["futures"] = {
            "df":
                make_derivative_df(
                    extract_records(
                        raw,
                        "futures"
                    ),
                    "futures",
                    20
                ),
            "raw": raw,
            "error": None,
        }

    except Exception as e:

        result["futures"] = {
            "df": pd.DataFrame(),
            "raw": None,
            "error": str(e)
        }

    try:

        result["options"] = load_stock_options(
            session
        )

    except Exception as e:

        result["options"] = {
            "df": pd.DataFrame(),
            "raw": None,
            "source": None,
            "error": str(e)
        }

    for kind in (
        "calls",
        "puts"
    ):

        try:

            raw = fetch_json(
                session,
                DERIV_URLS[kind],
                MOST_ACTIVE_PAGE
            )

            result[kind] = {
                "df":
                    make_derivative_df(
                        extract_records(
                            raw,
                            kind
                        ),
                        kind,
                        20
                    ),
                "raw": raw,
                "error": None,
            }

        except Exception as e:

            result[kind] = {
                "df": pd.DataFrame(),
                "raw": None,
                "error": str(e)
            }

    return result


# ============================================================
# RENDER DERIVATIVE TABLE
# ============================================================

def style_derivative_table(df):

    if df.empty:
        return df

    styler = df.style

    for column in (
        "Chng",
        "% Chng",
        "Chg in OI"
    ):

        if column in df.columns:

            styler = styler.map(
                _change_color,
                subset=[column]
            )

    formats = {}

    for column in (
        "LTP",
        "Chng",
        "% Chng",
        "Strike"
    ):

        if column in df.columns:
            formats[column] = "{:,.2f}"

    for column in (
        "Volume (Contracts)",
        "OI",
        "Chg in OI"
    ):

        if column in df.columns:
            formats[column] = "{:,.0f}"

    if "Value (₹ Cr)" in df.columns:

        formats[
            "Value (₹ Cr)"
        ] = "{:,.2f}"

    return styler.format(
        formats,
        na_rep="-"
    )


def render_derivative_table(
    title,
    section
):

    st.subheader(title)

    if section.get("error"):

        st.warning(
            f"Could not load this table: "
            f"{section['error']}"
        )

        return

    df = section.get(
        "df",
        pd.DataFrame()
    )

    if df.empty:

        st.info(
            "No stock derivative records "
            "were returned by NSE."
        )

        return

    df = track_first_seen(
        df,
        f"deriv__{title}"
    )

    st.dataframe(
        style_derivative_table(df),
        use_container_width=True,
        hide_index=True,
        height=500
    )


# ============================================================
# EQUITY MARKET
# ============================================================

def extract_equity_group(
    raw,
    group
):

    if not isinstance(raw, dict):
        return pd.DataFrame()

    block = raw.get(group, {})

    if not isinstance(block, dict):
        return pd.DataFrame()

    records = block.get(
        "data",
        []
    )

    if not isinstance(records, list):
        return pd.DataFrame()

    rows = []

    for record in records:

        if not isinstance(record, dict):
            continue

        symbol = record.get("symbol")

        if not symbol:
            continue

        turnover = to_num(
            record.get(
                "turnover",
                record.get(
                    "totalTradedValue"
                )
            )
        )

        rows.append({

            "Symbol":
                symbol,

            "Prev Close":
                to_num(
                    record.get(
                        "prev_price",
                        record.get(
                            "previousClose"
                        )
                    )
                ),

            "LTP":
                to_num(
                    record.get(
                        "ltp",
                        record.get(
                            "lastPrice"
                        )
                    )
                ),

            "Chng":
                to_num(
                    record.get(
                        "net_price",
                        record.get(
                            "change"
                        )
                    )
                ),

            "% Chng":
                to_num(
                    record.get(
                        "perChange",
                        record.get(
                            "pChange"
                        )
                    )
                ),

            "Open":
                to_num(
                    record.get(
                        "open_price",
                        record.get(
                            "open"
                        )
                    )
                ),

            "High":
                to_num(
                    record.get(
                        "high_price",
                        record.get(
                            "high"
                        )
                    )
                ),

            "Low":
                to_num(
                    record.get(
                        "low_price",
                        record.get(
                            "low"
                        )
                    )
                ),

            "Volume":
                to_num(
                    record.get(
                        "trade_quantity",
                        record.get(
                            "totalTradedVolume"
                        )
                    )
                ),

            "Value (₹ Cr)":
                (
                    turnover / 100
                    if turnover is not None
                    else None
                )
        })

    return pd.DataFrame(rows)


def load_equity_variations():

    session = get_nse_session()

    result = {}

    for direction in (
        "gainers",
        "loosers"
    ):

        result[direction] = fetch_json(
            session,
            f"{EQUITY_URL}?index={direction}",
            EQUITY_PAGE
        )

    return result


# ============================================================
# EQUITY TABLE STYLING
# ============================================================

def style_equity_table(df):

    if df.empty:
        return df

    styler = df.style

    for column in (
        "Chng",
        "% Chng"
    ):

        if column in df.columns:

            styler = styler.map(
                _change_color,
                subset=[column]
            )

    formats = {}

    for column in (
        "Prev Close",
        "LTP",
        "Chng",
        "Open",
        "High",
        "Low"
    ):

        if column in df.columns:
            formats[column] = "{:,.2f}"

    if "% Chng" in df.columns:

        formats[
            "% Chng"
        ] = "{:+.2f}%"

    if "Volume" in df.columns:

        formats[
            "Volume"
        ] = "{:,.0f}"

    if "Value (₹ Cr)" in df.columns:

        formats[
            "Value (₹ Cr)"
        ] = "{:,.2f}"

    return styler.format(
        formats,
        na_rep="-"
    )


def prepare_equity_df(
    df,
    descending
):

    if (
        df.empty
        or "% Chng" not in df.columns
    ):
        return df

    return (
        df
        .dropna(
            subset=["% Chng"]
        )
        .sort_values(
            "% Chng",
            ascending=not descending
        )
        .head(20)
        .reset_index(drop=True)
    )


def render_equity_table(
    title,
    df,
    list_key
):

    st.subheader(title)

    if df.empty:

        st.info(
            "No data returned by NSE "
            "for this table."
        )

        return

    df = track_first_seen(
        df,
        list_key
    )

    columns = [
        "Symbol",
        "First Seen",
        "Prev Close",
        "LTP",
        "Chng",
        "% Chng",
        "Open",
        "High",
        "Low",
        "Volume",
        "Value (₹ Cr)"
    ]

    columns = [
        c for c in columns
        if c in df.columns
    ]

    st.dataframe(
        style_equity_table(
            df[columns]
        ),
        use_container_width=True,
        hide_index=True,
        height=500
    )


# ============================================================
# MOST ACTIVE EQUITIES
# ============================================================

def make_most_active_equities(
    df,
    top_n=20
):

    if df.empty:
        return df

    if "Volume" not in df.columns:
        return df

    return (
        df
        .dropna(
            subset=["Volume"]
        )
        .sort_values(
            "Volume",
            ascending=False
        )
        .head(top_n)
        .reset_index(drop=True)
    )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "### Settings"
    )

    segment_key = st.selectbox(
        "Pre-market segment",
        KEY_OPTIONS,
        index=0,
        help=(
            "Which NSE pre-open universe "
            "to chart. NIFTY = Nifty 50."
        )
    )

    auto_refresh = st.checkbox(
        "Auto-refresh",
        value=False
    )

    refresh_time = st.selectbox(
        "Refresh interval",
        [
            "30 seconds",
            "1 minute",
            "2 minutes",
            "3 minutes"
        ],
        index=0
    )

    refresh_seconds = {
        "30 seconds": 30,
        "1 minute": 60,
        "2 minutes": 120,
        "3 minutes": 180
    }[refresh_time]

    if auto_refresh:

        st_autorefresh(
            interval=refresh_seconds * 1000,
            key="auto_refresh_tick"
        )

        st.caption(
            f"🔄 Auto-refreshing every "
            f"{refresh_time}"
        )

    if st.button(
        "🔄 Refresh now",
        use_container_width=True
    ):

        st.cache_data.clear()
        get_nse_session.clear()
        st.rerun()


# ============================================================
# TITLE
# ============================================================

st.title(
    "Nifty50 Pre-Market Dashboard"
)

show_debug = st.checkbox(
    "Show raw response (debug)",
    value=False
)


# ============================================================
# LOAD DERIVATIVES
# ============================================================
# Loaded once up front since Stock Futures, Stock Options,
# Calls, and Puts are now split across two different groups
# below.
# ============================================================

try:

    derivatives = load_derivatives()

except Exception as e:

    derivatives = None

    st.error(
        f"Could not load derivatives data: {e}"
    )


# ============================================================
# ============================================================
# GROUP 1 — PRE-MARKET SNAPSHOT
# ============================================================
# ============================================================

st.header("📈 Equity Market")

st.subheader(
    f"Equity Pre-Market — {segment_key}"
)

try:

    pm_session = get_nse_session()

    # IMPORTANT:
    # This remains the ORIGINAL equity pre-market.
    preopen_raw = fetch_preopen(
        pm_session,
        segment_key
    )

    market_df = make_preopen_df(
        preopen_raw,
        limit=50
    )

except Exception as e:

    market_df = pd.DataFrame()

    st.error(
        f"Equity Pre-market data failed: {e}"
    )


if not market_df.empty:

    top_loser = market_df.iloc[0]

    top_gainer = market_df.iloc[-1]

    st.caption(
        f"NSE Equity Pre-Market "
        f"({segment_key}) — "
        + now_ist().strftime(
            "%d-%b-%Y %H:%M:%S"
        )
        + " IST"
    )

    st.write(
        f"**Top Gainer:** "
        f"{top_gainer['symbol']} "
        f"(+{top_gainer['change']:.2f}%)"
        f"  |  "
        f"**Top Loser:** "
        f"{top_loser['symbol']} "
        f"({top_loser['change']:.2f}%)"
    )

    col1, col2 = st.columns(
        [3, 1]
    )

    with col1:

        fig, ax = plt.subplots(
            figsize=(10, 10)
        )

        colors = [
            UP_COLOR
            if value >= 0
            else DOWN_COLOR
            for value
            in market_df["change"]
        ]

        ax.barh(
            market_df["symbol"],
            market_df["change"],
            color=colors,
            height=0.6
        )

        ax.axvline(
            0,
            color=TEXT_COLOR,
            linewidth=0.8
        )

        ax.set_title(
            f"{segment_key} Equity Premarket Movement"
        )

        for index, value in enumerate(
            market_df["change"]
        ):

            ax.text(
                value,
                index,
                f" {value:+.2f}%",
                va="center",
                ha=(
                    "left"
                    if value >= 0
                    else "right"
                ),
                fontsize=8
            )

        st.pyplot(fig)

        plt.close(fig)

    with col2:

        up = int(
            (
                market_df["change"]
                >= 0
            ).sum()
        )

        down = int(
            (
                market_df["change"]
                < 0
            ).sum()
        )

        fig, ax = plt.subplots(
            figsize=(5, 5)
        )

        ax.pie(
            [up, down],
            labels=[
                f"Up ({up})",
                f"Down ({down})"
            ],
            colors=[
                UP_COLOR,
                DOWN_COLOR
            ],
            wedgeprops={
                "width": 0.4
            },
            autopct="%1.0f%%",
            startangle=90
        )

        ax.set_title(
            "Market Breadth"
        )

        ratio = (
            up / down
            if down > 0
            else float("inf")
        )

        ax.text(
            0,
            -1.3,
            f"A/D Ratio: {ratio:.2f}",
            ha="center"
        )

        st.pyplot(fig)

        plt.close(fig)

else:

    st.info(
        f"No equity pre-market rows "
        f"returned for segment "
        f"'{segment_key}'."
    )


st.divider()

try:

    derivative_preopen_session = (
        get_nse_session()
    )

    derivative_preopen_raw = (
        fetch_derivative_preopen(
            derivative_preopen_session
        )
    )

    derivative_preopen_df = (
        make_derivative_preopen_df(
            derivative_preopen_raw
        )
    )

    render_derivative_preopen_table(
        derivative_preopen_df
    )

except Exception as e:

    derivative_preopen_df = pd.DataFrame()

    st.error(
        "Could not load "
        "Derivatives Pre-Open Market — "
        f"Stock Futures: {e}"
    )


st.divider()

if derivatives:

    render_derivative_table(
        "Stock Futures — Top 20 Contracts",
        derivatives["futures"]
    )


# ============================================================
# ============================================================
# GROUP 2 — GAINERS, LOSERS & OPTIONS ACTIVITY
# ============================================================
# ============================================================

st.divider()

st.subheader(
    "Equity Gainers / Losers"
)

try:

    equity_raw = load_equity_variations()

    nifty_gainers = prepare_equity_df(
        extract_equity_group(
            equity_raw.get("gainers"),
            "NIFTY"
        ),
        descending=True
    )

    nifty_losers = prepare_equity_df(
        extract_equity_group(
            equity_raw.get("loosers"),
            "NIFTY"
        ),
        descending=False
    )

    fno_gainers = prepare_equity_df(
        extract_equity_group(
            equity_raw.get("gainers"),
            "FOSec"
        ),
        descending=True
    )

    fno_losers = prepare_equity_df(
        extract_equity_group(
            equity_raw.get("loosers"),
            "FOSec"
        ),
        descending=False
    )

except Exception as e:

    nifty_gainers = pd.DataFrame()
    nifty_losers = pd.DataFrame()
    fno_gainers = pd.DataFrame()
    fno_losers = pd.DataFrame()

    st.error(
        f"Could not load equity data: {e}"
    )


col1, col2 = st.columns(2)

with col1:

    render_equity_table(
        "🟢 NIFTY 50 — Top 20 Gainers",
        nifty_gainers,
        "nifty_gainers"
    )

with col2:

    render_equity_table(
        "🔴 NIFTY 50 — Top 20 Losers",
        nifty_losers,
        "nifty_losers"
    )


col3, col4 = st.columns(2)

with col3:

    render_equity_table(
        "🟢 F&O Securities — Top 20 Gainers",
        fno_gainers,
        "fno_gainers"
    )

with col4:

    render_equity_table(
        "🔴 F&O Securities — Top 20 Losers",
        fno_losers,
        "fno_losers"
    )


st.divider()

if derivatives:

    render_derivative_table(
        "Stock Options — Top 20 Contracts",
        derivatives["options"]
    )

    col5, col6 = st.columns(2)

    with col5:

        render_derivative_table(
            "🟢 Most Active Stock Calls",
            derivatives["calls"]
        )

    with col6:

        render_derivative_table(
            "🔴 Most Active Stock Puts",
            derivatives["puts"]
        )


# ============================================================
# MOST ACTIVE EQUITIES
# ============================================================

st.divider()

st.subheader(
    "🔥 Most Active Equities"
)

# Combine NIFTY + F&O securities
active_equities = pd.concat(
    [
        extract_equity_group(
            equity_raw.get("gainers"),
            "NIFTY"
        ),
        extract_equity_group(
            equity_raw.get("loosers"),
            "NIFTY"
        ),
        extract_equity_group(
            equity_raw.get("gainers"),
            "FOSec"
        ),
        extract_equity_group(
            equity_raw.get("loosers"),
            "FOSec"
        )
    ],
    ignore_index=True
)

if not active_equities.empty:

    active_equities = (
        active_equities
        .drop_duplicates(
            subset=["Symbol"]
        )
    )

    active_equities = make_most_active_equities(
        active_equities,
        20
    )

    render_equity_table(
        "🔥 Most Active Equities — Top 20",
        active_equities,
        "most_active_equities"
    )

else:

    st.info(
        "No most active equity data "
        "returned by NSE."
    )


# ============================================================
# DEBUG
# ============================================================

if show_debug:

    st.divider()

    st.subheader(
        "NSE Raw Responses"
    )

    with st.expander(
        "Debug — Equity Pre-Market"
    ):

        st.write(
            "Endpoint:",
            PREOPEN_URL_TEMPLATE.format(
                key=segment_key
            )
        )

        st.write(
            "Rows:",
            len(market_df)
        )

        if "preopen_raw" in locals():
            st.json(preopen_raw)

    with st.expander(
        "Debug — Derivatives Pre-Open"
    ):

        st.write(
            "Endpoint:",
            DERIVATIVE_PREOPEN_URL
        )

        st.write(
            "Page:",
            DERIVATIVE_PREOPEN_PAGE
        )

        st.write(
            "Rows:",
            len(derivative_preopen_df)
        )

        if "derivative_preopen_raw" in locals():
            st.json(
                derivative_preopen_raw
            )

    if derivatives:

        for name in (
            "futures",
            "options",
            "calls",
            "puts"
        ):

            section = derivatives[name]

            with st.expander(
                f"Debug — {name}"
            ):

                st.write(
                    "Rows:",
                    len(section["df"])
                )

                st.write(
                    "Source:",
                    section.get(
                        "source",
                        "-"
                    )
                )

                st.write(
                    "Error:",
                    section.get(
                        "error"
                    )
                )

                if section.get("raw") is not None:
                    st.json(
                        section["raw"]
                    )


# ============================================================
# FOOTER
# ============================================================

st.caption(
    "Equity and derivatives data refresh "
    "according to the selected auto-refresh interval."
)
