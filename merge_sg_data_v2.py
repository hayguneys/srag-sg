import pandas as pd
import numpy as np
import os
from pathlib import Path

work_dir = r"C:\Users\gabriel.olima\Desktop\dashboard-git"
os.chdir(work_dir)

print("Reading SG data files...")
sg_files = [f"SG {year}.xlsx" for year in range(2013, 2026)]
dfs = []

for file in sg_files:
    if os.path.exists(file):
        try:
            df = pd.read_excel(file)
            year = int(file.split()[1].split('.')[0])
            df['source_year'] = year
            dfs.append(df)
            print(f"[OK] Loaded {file} - {len(df)} rows")
        except Exception as e:
            print(f"[ERROR] Error loading {file}: {e}")

print(f"\nMerging {len(dfs)} dataframes...")
merged_df = pd.concat(dfs, ignore_index=True)
print(f"[OK] Merged - Total rows: {len(merged_df)}")

print("\nCleaning headers...")
def clean_header(header):
    if pd.isna(header):
        return "unnamed"
    header = str(header).strip()
    header = header.split(',')[0].strip()
    return header

original_headers = merged_df.columns.tolist()
merged_df.columns = [clean_header(col) for col in merged_df.columns]
print(f"[OK] Cleaned {len(merged_df.columns)} column headers")

changes = 0
for orig, new in zip(original_headers, merged_df.columns):
    if orig != new:
        changes += 1
print(f"[OK] {changes} headers modified")

print("\nIdentifying and converting date columns...")

# Whitelist of columns that are definitely dates
date_keywords = [
    'DT_', '_DATA', '_DATA_', '_DIGITA',
    'DT_NASC', 'DT_PREENC', 'DT_PRISINT', 'DT_VACINA', 'DT_ANTIVIR',
    'DT_COLETA', 'IFI_DATA', 'PCR_DATA', 'DT_ENCERRA', 'DT_DIGITA',
    'DT_TRT_COV', 'DOSE_1_COV', 'DOSE_2_COV', 'DOSE_REF', 'DOSE_2REF',
    'DOSE_ADIC', 'DOS_RE_BI', 'VG_DTRES'
]

date_columns = []

for col in merged_df.columns:
    col_lower = col.lower()

    # Check if column name matches date keywords
    is_date_col = any(keyword.lower() in col_lower for keyword in date_keywords)

    if is_date_col:
        try:
            merged_df[col] = pd.to_datetime(merged_df[col], errors='coerce', format='%d/%m/%Y')
            date_columns.append(col)
            print(f"[OK] Converted '{col}' to datetime")
        except Exception as e:
            try:
                # Try without specific format
                merged_df[col] = pd.to_datetime(merged_df[col], errors='coerce')
                date_columns.append(col)
                print(f"[OK] Converted '{col}' to datetime (auto-format)")
            except Exception as e2:
                print(f"[WARNING] Could not convert '{col}': {e2}")

print(f"\n[OK] Identified and converted {len(date_columns)} date columns")

print(f"\nSaving merged data to SG_merged_2013_2025_CLEAN.xlsx...")
try:
    merged_df.to_excel("SG_merged_2013_2025_CLEAN.xlsx", index=False)
    print(f"[OK] Successfully saved")
    print(f"\nFinal dataset:")
    print(f"  - Rows: {len(merged_df):,}")
    print(f"  - Columns: {len(merged_df.columns)}")
    print(f"  - Date columns: {len(date_columns)}")
    print(f"\nDate columns:")
    for col in date_columns:
        print(f"  - {col}")
except Exception as e:
    print(f"[ERROR] Error saving file: {e}")

print("\nData wrangling complete!")
