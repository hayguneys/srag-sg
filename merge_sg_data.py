import pandas as pd
import numpy as np
import os
import glob
import re
from pathlib import Path

# Define the working directory
work_dir = r"C:\Users\gabriel.olima\Desktop\dashboard-git"
os.chdir(work_dir)

# Step 1: Read all SG xlsx files (2013-2025)
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

# Step 2: Convert DBF to XLSX and read it
print("\nConverting DBF file...")
dbf_file = "SG2772176_00.dbf"
dbf_xlsx_file = "SG2772176_00_converted.xlsx"

try:
    # Try using simpledbf first
    try:
        from simpledbf import Dbf5
        dbf = Dbf5(dbf_file)
        df_dbf = dbf.to_dataframe()
    except ImportError:
        # Fallback to using pandas with simpledbf installed via pip or direct reading
        print("Installing simpledbf...")
        os.system("pip install simpledbf -q")
        from simpledbf import Dbf5
        dbf = Dbf5(dbf_file)
        df_dbf = dbf.to_dataframe()

    df_dbf.to_excel(dbf_xlsx_file, index=False)
    print(f"[OK] Converted DBF to {dbf_xlsx_file} - {len(df_dbf)} rows")
    dfs.append(df_dbf)
except Exception as e:
    print(f"[WARNING] Trying alternative DBF reader...")
    try:
        # Try pydbf as alternative
        os.system("pip install pydbf -q")
        from pydbf import read
        df_dbf = read(dbf_file)
        df_dbf.to_excel(dbf_xlsx_file, index=False)
        print(f"[OK] Converted DBF to {dbf_xlsx_file} - {len(df_dbf)} rows")
        dfs.append(df_dbf)
    except Exception as e2:
        print(f"[ERROR] Error converting DBF: {e2}")

# Step 3: Merge all dataframes
print("\nMerging all data...")
if dfs:
    merged_df = pd.concat(dfs, ignore_index=True)
    print(f"[OK] Merged {len(dfs)} dataframes - Total rows: {len(merged_df)}")
else:
    print("[ERROR] No data to merge")
    exit(1)

# Step 4: Clean headers - remove commas and everything after
print("\nCleaning headers...")
def clean_header(header):
    if pd.isna(header):
        return "unnamed"
    header = str(header).strip()
    # Remove everything after and including comma
    header = header.split(',')[0].strip()
    return header

original_headers = merged_df.columns.tolist()
merged_df.columns = [clean_header(col) for col in merged_df.columns]
print(f"[OK] Cleaned {len(merged_df.columns)} column headers")

# Show header mapping
print("\nHeader mapping (if changed):")
changes = 0
for orig, new in zip(original_headers, merged_df.columns):
    if orig != new:
        print(f"  {orig} --> {new}")
        changes += 1
if changes == 0:
    print("  (no changes needed)")

# Step 5: Identify and convert date columns
print("\nIdentifying and converting date columns...")
date_columns = []

for col in merged_df.columns:
    # Check if column name suggests it's a date
    col_lower = col.lower()
    if any(date_keyword in col_lower for date_keyword in ['data', 'date', 'data_', '_date', 'nascimento', 'nasc', 'sintoma', 'internacao', 'internação']):
        try:
            # Try to convert to datetime
            merged_df[col] = pd.to_datetime(merged_df[col], errors='coerce')
            date_columns.append(col)
            print(f"[OK] Converted '{col}' to datetime")
        except Exception as e:
            print(f"[WARNING] Could not convert '{col}': {e}")

# Also check columns that look like dates even without date keywords
for col in merged_df.columns:
    if col not in date_columns:
        try:
            # Check if majority of non-null values can be converted to dates
            non_null = merged_df[col].dropna()
            if len(non_null) > 0:
                # Sample to check
                sample = non_null.head(100)
                test_conversion = pd.to_datetime(sample, errors='coerce')
                conversion_rate = test_conversion.notna().sum() / len(sample)

                if conversion_rate > 0.8:  # If 80%+ can be converted
                    merged_df[col] = pd.to_datetime(merged_df[col], errors='coerce')
                    date_columns.append(col)
                    print(f"[OK] Detected and converted '{col}' to datetime (rate: {conversion_rate:.1%})")
        except:
            pass

# Step 6: Save the merged and cleaned data
output_file = "SG_merged_2013_2025.xlsx"
print(f"\nSaving merged data to {output_file}...")

try:
    merged_df.to_excel(output_file, index=False)
    print(f"[OK] Successfully saved {output_file}")
    print(f"\nFinal dataset:")
    print(f"  - Rows: {len(merged_df):,}")
    print(f"  - Columns: {len(merged_df.columns)}")
    print(f"  - Date columns identified: {len(date_columns)}")
    print(f"\nColumn names:")
    for i, col in enumerate(merged_df.columns, 1):
        dtype = str(merged_df[col].dtype)
        print(f"  {i:2d}. {col} ({dtype})")
except Exception as e:
    print(f"[ERROR] Error saving file: {e}")

print("\n" + "="*50)
print("Data wrangling complete!")
