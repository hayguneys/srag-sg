import pandas as pd
import os
import sys

work_dir = r"C:\Users\gabriel.olima\Desktop\dashboard-git"
os.chdir(work_dir)

print("Installing dbfread library...")
os.system("pip install dbfread -q")

print("\nConverting DBF file...")
try:
    from dbfread import DBF

    dbf_file = "SG2772176_00.dbf"
    print(f"Reading {dbf_file}...")

    # Read DBF file - try different encodings
    encodings_to_try = ['latin1', 'iso-8859-1', 'cp1252', 'utf-8']
    dbf = None
    for enc in encodings_to_try:
        try:
            dbf = DBF(dbf_file, encoding=enc)
            print(f"[OK] Using encoding: {enc}")
            break
        except Exception as e:
            print(f"[WARNING] Encoding {enc} failed, trying next...")
            continue

    if dbf is None:
        raise Exception("Could not read DBF file with any encoding")
    records = [dict(record) for record in dbf]

    df_dbf = pd.DataFrame(records)
    print(f"[OK] Converted DBF - {len(df_dbf)} rows, {len(df_dbf.columns)} columns")

    # Clean headers for DBF data
    def clean_header(header):
        if pd.isna(header):
            return "unnamed"
        header = str(header).strip()
        header = header.split(',')[0].strip()
        return header

    original_headers = df_dbf.columns.tolist()
    df_dbf.columns = [clean_header(col) for col in df_dbf.columns]

    # Save DBF as xlsx
    dbf_xlsx_file = "SG2772176_00.xlsx"
    df_dbf.to_excel(dbf_xlsx_file, index=False)
    print(f"[OK] Saved DBF to {dbf_xlsx_file}")

    # Now merge with the main dataset
    print("\nLoading cleaned SG merged data...")
    df_main = pd.read_excel("SG_merged_2013_2025_CLEAN.xlsx")
    print(f"[OK] Loaded main dataset - {len(df_main)} rows, {len(df_main.columns)} columns")

    print("\nMerging datasets...")
    # Add source indicator for DBF data
    df_dbf['source_year'] = 0  # or use a special marker
    df_dbf['data_source'] = 'DBF'
    df_main['data_source'] = 'SG'

    # Identify common columns (case-insensitive)
    main_cols_lower = {col.lower(): col for col in df_main.columns}
    dbf_cols_lower = {col.lower(): col for col in df_dbf.columns}

    common_cols_lower = set(main_cols_lower.keys()) & set(dbf_cols_lower.keys())
    print(f"[OK] Found {len(common_cols_lower)} common columns")

    # Reorder DBF columns to match main dataset where possible
    reorder_cols = []
    for col in df_main.columns:
        col_lower = col.lower()
        if col_lower in dbf_cols_lower:
            reorder_cols.append(dbf_cols_lower[col_lower])

    # Add remaining DBF columns
    for col in df_dbf.columns:
        if col not in reorder_cols:
            reorder_cols.append(col)

    df_dbf = df_dbf[reorder_cols]

    # Add missing columns to DBF dataframe (with NaN)
    for col in df_main.columns:
        if col not in df_dbf.columns:
            df_dbf[col] = None

    # Reorder DBF columns to match main dataset
    df_dbf = df_dbf[df_main.columns]

    # Merge
    merged = pd.concat([df_main, df_dbf], ignore_index=True)
    print(f"[OK] Merged - Total rows: {len(merged)}")
    print(f"[OK] Total columns: {len(merged.columns)}")

    # Save merged file
    output_file = "SG_merged_2013_2025_WITH_DBF.xlsx"
    print(f"\nSaving final merged file to {output_file}...")
    merged.to_excel(output_file, index=False)
    print(f"[OK] Successfully saved!")

    print(f"\nFinal dataset summary:")
    print(f"  - Total rows: {len(merged):,}")
    print(f"  - Total columns: {len(merged.columns)}")
    print(f"  - Rows from SG files: {len(df_main):,}")
    print(f"  - Rows from DBF: {len(df_dbf):,}")
    print(f"  - Data sources: SG (2013-2025), DBF")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
