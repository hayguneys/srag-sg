import pandas as pd
import os
from dbfread import DBF

WORK_DIR = r"C:\Users\gabriel.olima\Desktop\dashboard-git"
OUTPUT_FILE = os.path.join(WORK_DIR, "SG_merged_2013_2025.xlsx")

DATE_COLS = {
    'DT_PREENC', 'DT_NASC', 'DT_PRISINT', 'DT_VACINA', 'DT_ANTIVIR',
    'DT_COLETA', 'IFI_DATA', 'PCR_DATA', 'DT_ENCERRA', 'DT_DIGITA',
    'DT_TRT_COV', 'DOSE_1_COV', 'DOSE_2_COV', 'DOSE_REF', 'DOSE_2REF',
    'DOSE_ADIC', 'DOS_RE_BI', 'VG_DTRES',
}

def clean_header(col):
    return str(col).strip().split(',')[0].strip()

def parse_dates(df):
    for col in df.columns:
        if col in DATE_COLS:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors='coerce')
    return df


# -- 1. Read SG xlsx files ----------------------------------------------------
print("Reading SG xlsx files (2013-2025)...")
frames = []
for year in range(2013, 2026):
    path = os.path.join(WORK_DIR, f"SG {year}.xlsx")
    if not os.path.exists(path):
        print(f"  [SKIP] SG {year}.xlsx not found")
        continue
    df = pd.read_excel(path)
    df.columns = [clean_header(c) for c in df.columns]
    # Use assign() to avoid DataFrame fragmentation warnings
    df = df.assign(source_year=year, data_source='SG')
    frames.append(df)
    print(f"  [OK] SG {year}.xlsx - {len(df):,} rows")


# -- 2. Read and convert DBF --------------------------------------------------
print("\nReading DBF file (SG2772176_00.dbf)...")
dbf_path = os.path.join(WORK_DIR, "SG2772176_00.dbf")
table = DBF(dbf_path, encoding='latin1', ignore_missing_memofile=True)
df_dbf = pd.DataFrame(iter(table))
df_dbf.columns = [clean_header(c) for c in df_dbf.columns]
df_dbf = df_dbf.assign(source_year=2026, data_source='DBF')

dbf_xlsx = os.path.join(WORK_DIR, "SG2772176_00.xlsx")
df_dbf.to_excel(dbf_xlsx, index=False)
print(f"  [OK] DBF converted - {len(df_dbf):,} rows - saved to SG2772176_00.xlsx")
frames.append(df_dbf)


# -- 3. Merge -----------------------------------------------------------------
print(f"\nMerging {len(frames)} dataframes...")
merged = pd.concat(frames, ignore_index=True, sort=False)
print(f"  [OK] Total rows: {len(merged):,} | Total columns: {len(merged.columns)}")


# -- 4. Parse date columns ----------------------------------------------------
print("\nParsing date columns...")
merged = parse_dates(merged)
converted = [c for c in DATE_COLS if c in merged.columns]
print(f"  [OK] Converted {len(converted)} date columns: {converted}")


# -- 5. Save ------------------------------------------------------------------
print(f"\nSaving to {OUTPUT_FILE}...")
merged.to_excel(OUTPUT_FILE, index=False)
size_mb = os.path.getsize(OUTPUT_FILE) / 1_048_576
print(f"  [OK] Saved - {size_mb:.1f} MB")

print("")
print("=" * 55)
print("DONE")
print(f"  Rows    : {len(merged):,}")
print(f"  Columns : {len(merged.columns)}")
print(f"  Output  : SG_merged_2013_2025.xlsx")
print("=" * 55)
