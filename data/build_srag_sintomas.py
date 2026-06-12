"""Build the SRAG parquet datasets from the SIVEP-GRIPE historical Excel export.

Source: data/SRAG_Série Histórica_2019 a 2026.xlsx (sheet "Plan1"), a DBF export
whose header cells carry the field metadata ("NU_NOTIFIC,C,14"); we keep only the
field name before the first comma.

Scope:
  * município de RESIDÊNCIA = Recife (ID_MN_RESI == "RECIFE").
  * analytic date = DT_SIN_PRI (data dos primeiros sintomas), NOT DT_NOTIFIC.

Output:
  * srag_sintomas.parquet — DT_SIN_PRI as the analytic date. Empty DT_SIN_PRI is
    filled from DT_NOTIFIC, though in the current Recife-residência extract every
    record already has a symptom date so no row actually needs filling.

Schema is kept compatible with the previous SRAG dataset (sragmain_withna.csv):
same field names, DT_DIGITA / DT_SIN_PRI as datetime, and every other column
coerced to the same dtype pandas.read_csv would have inferred (numeric where all
non-empty values are numeric, otherwise string) so the dashboard's comparisons
(e.g. EVOLUCAO == 2) keep working.
"""
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent
SRC = DATA_DIR / "SRAG_Série Histórica_2019 a 2026.xlsx"
OUT = DATA_DIR / "srag_sintomas.parquet"

# Date columns the dashboard parses as datetime via the loader.
DATETIME_COLS = ["DT_DIGITA", "DT_SIN_PRI"]


def _clean_columns(cols) -> list[str]:
    return [str(c).split(",")[0].strip() for c in cols]


def _read_excel() -> pd.DataFrame:
    df = pd.read_excel(SRC, sheet_name="Plan1", dtype=str)
    df.columns = _clean_columns(df.columns)
    # Drop trailing empty / unnamed columns produced by the DBF export.
    keep = [c for c in df.columns if c and c != "None" and not c.lower().startswith("unnamed")]
    df = df.loc[:, keep]
    # Normalise whitespace-only cells to NA (works for object and Arrow-string dtypes).
    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col]):
            df[col] = df[col].str.strip().replace({"": pd.NA})
    return df


def _coerce_like_read_csv(df: pd.DataFrame) -> pd.DataFrame:
    """Make string columns numeric where every non-null value parses as a number,
    mirroring pandas.read_csv type inference so downstream `== <int>` comparisons work.
    """
    for col in df.columns:
        if col in DATETIME_COLS:
            continue
        s = df[col]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        coerced = pd.to_numeric(s, errors="coerce")
        # Numeric only if nothing that had data failed to parse.
        if (coerced.isna() & s.notna()).sum() == 0 and s.notna().any():
            df[col] = coerced
    return df


def main() -> None:
    df = _read_excel()
    print(f"Loaded {len(df):,} rows × {df.shape[1]} cols")

    # --- município de residência == Recife --------------------------------
    df = df[df["ID_MN_RESI"] == "RECIFE"].copy()
    print(f"After residência==RECIFE: {len(df):,} rows")

    # --- analytic date = primeiros sintomas -------------------------------
    sin_pri = pd.to_datetime(df["DT_SIN_PRI"], format="%d/%m/%Y", errors="coerce")
    notific = pd.to_datetime(df["DT_NOTIFIC"], format="%d/%m/%Y", errors="coerce")
    print(f"DT_SIN_PRI empty/unparsed: {sin_pri.isna().sum()}  (these would be filled from DT_NOTIFIC)")

    df["DT_DIGITA"] = pd.to_datetime(df["DT_DIGITA"], errors="coerce")

    df = _coerce_like_read_csv(df)

    # Analytic date = DT_SIN_PRI, falling back to DT_NOTIFIC where the symptom
    # date is missing (no rows in the current extract).
    df["DT_SIN_PRI"] = sin_pri.fillna(notific)
    df.to_parquet(OUT, index=False)

    n_filled = int(sin_pri.isna().sum())
    print(f"Wrote {OUT.name} ({len(df):,} rows, filled {n_filled} from DT_NOTIFIC)")
    print(f"  DT_SIN_PRI year range: {int(df['DT_SIN_PRI'].dt.year.min())}"
          f"–{int(df['DT_SIN_PRI'].dt.year.max())}")


if __name__ == "__main__":
    main()
