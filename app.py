import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

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

NIFTY50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM",
    "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "ITC", "INDUSINDBK", "INFY", "JSWSTEEL",
    "JIOFIN", "KOTAKBANK", "LT", "M&M", "MARUTI", "MAXHEALTH", "NESTLEIND",
    "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN",
    "SBIN", "SUNPHARMA", "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO", "INDIGO"
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

NSE_HOME = "https://www.nseindia.com/"

MOST_ACTIVE_PAGE = (
    "https://www.nseindia.com/market-data/"
    "most-active-contracts"
)

EQUITY_PAGE = (
    "https://www.nseindia.com/market-data/"
    "top-gainers-losers"
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

# NSE Most Active Contracts
DERIVATIVE_CONTRACTS_URL = (
    "https://www.nseindia.com/api/"
    "snapshot-derivatives-equity?index=contracts"
)

EQUITY_URL = (
    "https://www.nseindia.com/api/"
    "live-analysis-variations"
)

# ============================================================
# NSE SESSION
# ============================================================

def new_nse_session():

    session = requests.Session()

    session.headers.update({

        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),

        "Accept": (
            "application/json, text/plain, */*"
        ),

        "Accept-Language":
            "en-IN,en;q=0.9",

        "Referer":
            MOST_ACTIVE_PAGE,

        "Connection":
            "keep-alive",
    })

    try:

        session.get(
            NSE_HOME,
            timeout=10
        )

        session.get(
            MOST_ACTIVE_PAGE,
            timeout=10
        )

    except requests.RequestException:
        pass

    return session


def fetch_json(
    session,
    url,
    referer=None
):

    old_referer = session.headers.get(
        "Referer"
    )

    if referer:
        session.headers["Referer"] = referer

    try:

        response = session.get(
            url,
            timeout=20
        )

        if response.status_code in (
            401,
            403
        ):

            session.cookies.clear()

            session.get(
                NSE_HOME,
                timeout=10
            )

            if referer:

                session.get(
                    referer,
                    timeout=10
                )

            response = session.get(
                url,
                timeout=20
            )

        response.raise_for_status()

        return response.json()

    finally:

        if old_referer:

            session.headers[
                "Referer"
            ] = old_referer

        else:

            session.headers.pop(
                "Referer",
                None
            )


# ============================================================
# HELPERS
# ============================================================

def get_field(
    record,
    *keys,
    default=None
):

    if not isinstance(
        record,
        dict
    ):
        return default

    for key in keys:

        if (
            key in record
            and record[key] not in (
                None,
                ""
            )
        ):

            return record[key]

    lower = {
        str(k).lower(): v
        for k, v in record.items()
    }

    for key in keys:

        value = lower.get(
            str(key).lower()
        )

        if value not in (
            None,
            ""
        ):

            return value

    return default


def to_num(value):

    try:

        if value in (
            None,
            "",
            "-"
        ):

            return None

        return float(
            str(value)
            .replace(",", "")
        )

    except (
        TypeError,
        ValueError
    ):

        return None


def option_type(value):

    value = str(
        value or ""
    ).strip().upper()

    if value in (
        "CALL",
        "CE"
    ):

        return "CE"

    if value in (
        "PUT",
        "PE"
    ):

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
# the auto-refresh below uses streamlit-autorefresh (a proper
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

    now = datetime.now()

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
# PRE-MARKET
# ============================================================

def fetch_preopen(session):

    return fetch_json(

        session,

        "https://www.nseindia.com/api/"
        "market-data-pre-open?key=ALL",

        NSE_HOME
    )


def make_preopen_df(raw):

    rows = []

    for item in raw.get(
        "data",
        []
    ):

        metadata = item.get(
            "metadata",
            {}
        )

        symbol = metadata.get(
            "symbol"
        )

        if symbol in NIFTY50:

            rows.append({

                "symbol":
                    symbol,

                "price":
                    to_num(
                        metadata.get(
                            "lastPrice"
                        )
                    ),

                "change":
                    to_num(
                        metadata.get(
                            "pChange"
                        )
                    ),
            })

    df = pd.DataFrame(
        rows
    )

    if df.empty:
        return df

    return (
        df
        .sort_values(
            "change",
            ascending=True
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# DERIVATIVE RESPONSE PARSING
# ============================================================

def extract_records(
    raw,
    kind
):

    if not isinstance(
        raw,
        dict
    ):
        return []

    if kind in (
        "calls",
        "puts"
    ):

        optstk = raw.get(
            "OPTSTK"
        )

        if isinstance(
            optstk,
            dict
        ):

            data = optstk.get(
                "data"
            )

            if isinstance(
                data,
                list
            ):

                return data

    volume = raw.get(
        "volume"
    )

    if isinstance(
        volume,
        dict
    ):

        data = volume.get(
            "data"
        )

        if isinstance(
            data,
            list
        ):

            return data

    for key in (
        "FUTSTK",
        "OPTSTK",
        "data"
    ):

        block = raw.get(
            key
        )

        if isinstance(
            block,
            dict
        ):

            data = block.get(
                "data"
            )

            if isinstance(
                data,
                list
            ):

                return data

        if isinstance(
            block,
            list
        ):

            return block

    for value in raw.values():

        if isinstance(
            value,
            dict
        ):

            data = value.get(
                "data"
            )

            if isinstance(
                data,
                list
            ):

                return data

    return []


# ============================================================
# NORMALIZE DERIVATIVES
# ============================================================

def normalize_derivatives(
    records,
    kind
):

    rows = []

    for record in records:

        if not isinstance(
            record,
            dict
        ):
            continue

        instrument = str(

            get_field(
                record,

                "instrumentType",
                "instrument_type",

                default=""
            )

        ).upper()

        if (
            kind == "futures"
            and instrument
        ):

            if instrument != "FUTSTK":
                continue

        if (
            kind in (
                "options",
                "calls",
                "puts"
            )
            and instrument
        ):

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

        symbol = str(
            symbol
        ).strip()

        if (
            symbol.upper()
            in INDEX_UNDERLYINGS
        ):
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

            "Symbol":
                symbol,

            "Expiry":
                get_field(
                    record,
                    "expiryDate",
                    "expiry_date",
                    "expiry"
                ),

            "LTP":
                to_num(
                    get_field(
                        record,
                        "lastPrice",
                        "ltp"
                    )
                ),

            "Chng":
                to_num(
                    get_field(
                        record,
                        "change",
                        "netChange",
                        "chng"
                    )
                ),

            "% Chng":
                to_num(
                    get_field(
                        record,
                        "pChange",
                        "perChange",
                        "percentChange"
                    )
                ),

            "Volume (Contracts)":
                volume,

            "Value (₹ Cr)":
                turnover,

            "OI":
                to_num(
                    get_field(
                        record,
                        "openInterest",
                        "oi"
                    )
                ),

            "Chg in OI":
                to_num(
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

        rows.append(
            row
        )

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

    df = pd.DataFrame(
        rows
    )

    if df.empty:
        return df

    if (
        "Volume (Contracts)"
        in df.columns
    ):

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

        column

        for column in columns

        if column in df.columns
    ]

    return (
        df[columns]
        .head(top_n)
        .reset_index(drop=True)
    )


# ============================================================
# NSE DERIVATIVES MARKET
# ============================================================

def fetch_derivative_market_contracts(
    session
):

    raw = fetch_json(

        session,

        DERIVATIVE_CONTRACTS_URL,

        MOST_ACTIVE_PAGE
    )

    records = []

    if isinstance(
        raw,
        dict
    ):

        volume_block = raw.get(
            "volume"
        )

        if isinstance(
            volume_block,
            dict
        ):

            data = volume_block.get(
                "data"
            )

            if isinstance(
                data,
                list
            ):

                records = data

    return records


def make_derivative_market_df(
    records,
    top_n=20
):

    rows = []

    for record in records:

        if not isinstance(
            record,
            dict
        ):
            continue

        instrument_type = get_field(

            record,

            "instrumentType",
            "instrument_type",
            "instrument"
        )

        symbol = get_field(

            record,

            "symbol",
            "underlying",
            "underlyingSymbol"
        )

        expiry = get_field(

            record,

            "expiryDate",
            "expiry_date",
            "expiry"
        )

        opt_type = option_type(

            get_field(

                record,

                "optionType",
                "option_type",
                "type"
            )
        )

        strike = to_num(

            get_field(

                record,

                "strikePrice",
                "strike"
            )
        )

        ltp = to_num(

            get_field(

                record,

                "lastPrice",
                "ltp"
            )
        )

        change = to_num(

            get_field(

                record,

                "change",
                "netChange",
                "chng"
            )
        )

        percent_change = to_num(

            get_field(

                record,

                "pChange",
                "perChange",
                "percentChange"
            )
        )

        open_price = to_num(

            get_field(

                record,

                "open",
                "openPrice",
                "open_price"
            )
        )

        high = to_num(

            get_field(

                record,

                "high",
                "highPrice",
                "high_price"
            )
        )

        low = to_num(

            get_field(

                record,

                "low",
                "lowPrice",
                "low_price"
            )
        )

        volume = to_num(

            get_field(

                record,

                "numberOfContractsTraded",
                "tradedVolume",
                "volume",
                "totalTradedVolume"
            )
        )

        value = to_num(

            get_field(

                record,

                "totalTurnover",
                "value",
                "turnover"
            )
        )

        open_interest = to_num(

            get_field(

                record,

                "openInterest",
                "oi"
            )
        )

        underlying_value = to_num(

            get_field(

                record,

                "underlyingValue",
                "underlying_value",
                "underlyingValueOfSecurity"
            )
        )

        rows.append({

            "Instrument Type":
                instrument_type,

            "Symbol":
                symbol,

            "Expiry Date":
                expiry,

            "Option Type":
                opt_type,

            "Strike":
                strike,

            "LTP":
                ltp,

            "Chng":
                change,

            "% Chng":
                percent_change,

            "Open":
                open_price,

            "High":
                high,

            "Low":
                low,

            "Volume (Contracts)":
                volume,

            "Value (₹ Crores)":
                value,

            "Open Interest":
                open_interest,

            "Underlying Value":
                underlying_value
        })

    df = pd.DataFrame(
        rows
    )

    if df.empty:
        return df

    if (
        "Volume (Contracts)"
        in df.columns
    ):

        df = df.sort_values(

            "Volume (Contracts)",

            ascending=False,

            na_position="last"
        )

    return (
        df
        .head(top_n)
        .reset_index(drop=True)
    )


# ============================================================
# STYLE DERIVATIVE MARKET TABLE
# ============================================================

def style_derivative_market_table(
    df
):

    if df.empty:
        return df

    def change_color(
        value
    ):

        try:

            value = float(
                value
            )

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

    styler = df.style

    for column in (
        "Chng",
        "% Chng"
    ):

        if column in df.columns:

            styler = styler.map(

                change_color,

                subset=[column]
            )

    formats = {}

    for column in (

        "Strike",
        "LTP",
        "Chng",
        "% Chng",
        "Open",
        "High",
        "Low",
        "Underlying Value"
    ):

        if column in df.columns:

            formats[column] = "{:,.2f}"

    for column in (

        "Volume (Contracts)",
        "Open Interest"
    ):

        if column in df.columns:

            formats[column] = "{:,.0f}"

    if "Value (₹ Crores)" in df.columns:

        formats[
            "Value (₹ Crores)"
        ] = "{:,.2f}"

    return styler.format(

        formats,

        na_rep="-"
    )


def render_derivative_market_table(
    df
):

    st.subheader(
        "📊 Derivatives Market — Top 20 Contracts"
    )

    if df.empty:

        st.info(
            "No derivatives market "
            "contracts returned by NSE."
        )

        return

    df = track_first_seen(
        df,
        "deriv_market"
    )

    st.dataframe(

        style_derivative_market_table(
            df
        ),

        use_container_width=True,

        hide_index=True,

        height=600
    )


# ============================================================
# STOCK OPTIONS
# ============================================================

def load_stock_options(
    session
):

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

                "df":
                    first_df,

                "raw":
                    first_raw,

                "source":
                    "NSE options snapshot",

                "error":
                    None,
            }

    except Exception:

        first_df = pd.DataFrame()

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

            "df":
                fallback_df,

            "raw":
                raw_parts,

            "source":
                "NSE stock calls + puts fallback",

            "error":
                None,
        }

    return {

        "df":
            first_df
            if "first_df" in locals()
            else pd.DataFrame(),

        "raw":
            first_raw,

        "source":
            "NSE options snapshot",

        "error":
            None,
    }


# ============================================================
# DERIVATIVES LOADER
# ============================================================

def load_derivatives():

    session = new_nse_session()

    result = {}

    # Futures
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

            "raw":
                raw,

            "error":
                None,
        }

    except Exception as e:

        result["futures"] = {

            "df":
                pd.DataFrame(),

            "raw":
                None,

            "error":
                str(e),
        }

    # Stock Options
    try:

        result["options"] = (
            load_stock_options(
                session
            )
        )

    except Exception as e:

        result["options"] = {

            "df":
                pd.DataFrame(),

            "raw":
                None,

            "source":
                None,

            "error":
                str(e),
        }

    # Calls and Puts
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

                "raw":
                    raw,

                "error":
                    None,
            }

        except Exception as e:

            result[kind] = {

                "df":
                    pd.DataFrame(),

                "raw":
                    None,

                "error":
                    str(e),
            }

    return result


# ============================================================
# EQUITY MOVERS
# ============================================================

def extract_equity_group(
    raw,
    group
):

    if not isinstance(
        raw,
        dict
    ):
        return pd.DataFrame()

    block = raw.get(
        group,
        {}
    )

    if not isinstance(
        block,
        dict
    ):
        return pd.DataFrame()

    records = block.get(
        "data",
        []
    )

    if not isinstance(
        records,
        list
    ):
        return pd.DataFrame()

    rows = []

    for record in records:

        if not isinstance(
            record,
            dict
        ):
            continue

        symbol = record.get(
            "symbol"
        )

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
                ),
        })

    return pd.DataFrame(
        rows
    )


def load_equity_variations():

    session = new_nse_session()

    result = {}

    for direction in (
        "gainers",
        "loosers"
    ):

        result[direction] = fetch_json(

            session,

            f"{EQUITY_URL}"
            f"?index={direction}",

            EQUITY_PAGE
        )

    return result


# ============================================================
# TABLE STYLING
# ============================================================

def style_derivative_table(
    df
):

    if df.empty:
        return df

    def change_color(
        value
    ):

        try:

            value = float(
                value
            )

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

    styler = df.style

    for column in (
        "Chng",
        "% Chng",
        "Chg in OI"
    ):

        if column in df.columns:

            styler = styler.map(

                change_color,

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

    st.subheader(
        title
    )

    if section.get(
        "error"
    ):

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

        style_derivative_table(
            df
        ),

        use_container_width=True,

        hide_index=True,

        height=500
    )


def style_equity_table(
    df
):

    if df.empty:
        return df

    def color_change(
        value
    ):

        try:

            value = float(
                value
            )

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

    styler = df.style

    for column in (
        "Chng",
        "% Chng"
    ):

        if column in df.columns:

            styler = styler.map(

                color_change,

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

    if df.empty:
        return df

    if "% Chng" not in df.columns:
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

        .reset_index(
            drop=True
        )
    )


def render_equity_table(
    title,
    df,
    list_key
):

    st.subheader(
        title
    )

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

        column

        for column in columns

        if column in df.columns
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
# AUTO REFRESH
# ============================================================

with st.sidebar:

    # Only refresh settings
    st.markdown("### Settings")

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

        st.markdown(
            f"""
            <div style="
                font-size:14px;
                margin-top:8px;
                margin-bottom:8px;
            ">
                🔄 Auto-refresh every {refresh_time}
            </div>
            """,
            unsafe_allow_html=True
        )

        # Uses a real Streamlit rerun (not a browser page reload),
        # so st.session_state — and therefore the "First Seen"
        # timestamps — survive every refresh.
        st_autorefresh(
            interval=refresh_seconds * 1000,
            key="dashboard_autorefresh"
        )

    if st.button(
        "🔄 Refresh now",
        use_container_width=True
    ):

        st.cache_data.clear()
        st.rerun()


# ============================================================
# TITLE
# ============================================================

st.title(
    "Nifty50 Pre-Market Dashboard"
)

refresh_col, debug_col = st.columns(
    [1, 3]
)

with refresh_col:

    if st.button(
        "🔄 Refresh Now",
        use_container_width=True
    ):

        st.cache_data.clear()
        st.rerun()

with debug_col:

    show_debug = st.checkbox(

        "Show raw response (debug)",

        value=False
    )


# ============================================================
# PRE-MARKET
# ============================================================

try:

    session = new_nse_session()

    preopen_raw = fetch_preopen(
        session
    )

    market_df = make_preopen_df(
        preopen_raw
    )

except Exception as e:

    market_df = pd.DataFrame()

    st.error(
        f"Pre-market data failed: {e}"
    )


if not market_df.empty:

    top_loser = market_df.iloc[0]

    top_gainer = market_df.iloc[-1]

    st.caption(

        "NSE Pre-Market — "

        + datetime.now().strftime(
            "%d-%b-%Y %H:%M:%S"
        )
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
            "Nifty50 Premarket Movement"
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

        st.pyplot(
            fig
        )

        plt.close(
            fig
        )

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

        st.pyplot(
            fig
        )

        plt.close(
            fig
        )


# ============================================================
# DERIVATIVES MARKET
# ============================================================

st.divider()

st.header(
    "📊 Derivatives Market"
)


# ============================================================
# NSE DERIVATIVES MARKET TABLE
# ============================================================

try:

    derivative_market_session = (
        new_nse_session()
    )

    derivative_market_records = (
        fetch_derivative_market_contracts(
            derivative_market_session
        )
    )

    derivative_market_df = (
        make_derivative_market_df(

            derivative_market_records,

            top_n=20
        )
    )

    render_derivative_market_table(
        derivative_market_df
    )

except Exception as e:

    derivative_market_df = pd.DataFrame()

    st.error(

        "Could not load NSE "
        "Derivatives Market: "
        f"{e}"
    )


st.divider()


# ============================================================
# EXISTING DERIVATIVE TABLES
# ============================================================

try:

    derivatives = load_derivatives()

except Exception as e:

    derivatives = None

    st.error(

        f"Could not load derivatives data: "
        f"{e}"
    )


if derivatives:

    col1, col2 = st.columns(
        2
    )

    with col1:

        render_derivative_table(

            "Stock Futures — Top 20 Contracts",

            derivatives["futures"]
        )

    with col2:

        render_derivative_table(

            "Stock Options — Top 20 Contracts",

            derivatives["options"]
        )

    col3, col4 = st.columns(
        2
    )

    with col3:

        render_derivative_table(

            "🟢 Most Active Stock Calls",

            derivatives["calls"]
        )

    with col4:

        render_derivative_table(

            "🔴 Most Active Stock Puts",

            derivatives["puts"]
        )

    if show_debug:

        st.divider()

        st.subheader(
            "NSE Raw Responses"
        )

        with st.expander(
            "Debug — Derivatives Market"
        ):

            st.write(
                "Rows:",
                len(
                    derivative_market_df
                )
            )

            st.write(
                "Endpoint:",
                DERIVATIVE_CONTRACTS_URL
            )

            st.json(
                derivative_market_records
            )

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

                    len(
                        section["df"]
                    )
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

                if section.get(
                    "raw"
                ) is not None:

                    st.json(
                        section["raw"]
                    )


st.caption(

    "Derivatives data refreshes according "
    "to the selected auto-refresh interval."
)


# ============================================================
# EQUITY MARKET
# ============================================================

st.divider()

st.header(
    "📈 Equity Market"
)

st.caption(
    "NIFTY 50 and F&O Securities "
    "Top Gainers / Top Losers"
)


try:

    equity_raw = (
        load_equity_variations()
    )

    nifty_gainers = (
        prepare_equity_df(

            extract_equity_group(

                equity_raw.get(
                    "gainers"
                ),

                "NIFTY"
            ),

            descending=True
        )
    )

    nifty_losers = (
        prepare_equity_df(

            extract_equity_group(

                equity_raw.get(
                    "loosers"
                ),

                "NIFTY"
            ),

            descending=False
        )
    )

    fno_gainers = (
        prepare_equity_df(

            extract_equity_group(

                equity_raw.get(
                    "gainers"
                ),

                "FOSec"
            ),

            descending=True
        )
    )

    fno_losers = (
        prepare_equity_df(

            extract_equity_group(

                equity_raw.get(
                    "loosers"
                ),

                "FOSec"
            ),

            descending=False
        )
    )

except Exception as e:

    nifty_gainers = pd.DataFrame()

    nifty_losers = pd.DataFrame()

    fno_gainers = pd.DataFrame()

    fno_losers = pd.DataFrame()

    st.error(
        f"Could not load equity data: {e}"
    )


col1, col2 = st.columns(
    2
)

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


col3, col4 = st.columns(
    2
)

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


st.caption(

    "Equity data refreshes according "
    "to the selected auto-refresh interval."
)
