import pandas as pd
import os
import sys

work_dir = r"C:\Users\gabriel.olima\Desktop\dashboard-git"
os.chdir(work_dir)

print("Installing dbfread library...")
os.system("pip install dbfread -q 2>nul")

print("\nConverting DBF file with encoding detection...")
try:
    from dbfread import DBF

    dbf_file = "SG2772176_00.dbf"
    print(f"Reading {dbf_file}...")

    # Try different encodings
    encodings_to_try = ['latin1', 'iso-8859-1', 'cp1252', 'utf-8']
    dbf = None
    used_encoding = None

    for enc in encodings_to_try:
        try:
            print(f"  Trying encoding: {enc}...")
            dbf = DBF(dbf_file, encoding=enc, ignore_missing_memofile=True)
            records = [dict(record) for record in dbf]
            used_encoding = enc
            print(f"[OK] Successfully read with encoding: {enc}")
            break
        except UnicodeDecodeError as e:
            print(f"  {enc} - UnicodeDecodeError, trying next...")
            continue
        except Exception as e:
            print(f"  {enc} - {type(e).__name__}, trying next...")
            continue

    if dbf is None or used_encoding is None:
        print("[ERROR] Could not read DBF file with any encoding")
        sys.exit(1)

    df_dbf = pd.DataFrame(records)
    print(f"[OK] Converted DBF - {len(df_dbf)} rows, {len(df_dbf.columns)} columns")
    print(f"[OK] Used encoding: {used_encoding}")

    # Clean headers for DBF data
    def clean_header(header):
        if pd.isna(header):
            return "unnamed"
        header = str(header).strip()
        # Remove everything after comma
        header = header.split(',')[0].strip()
        return header

    original_headers = df_dbf.columns.tolist()
    df_dbf.columns = [clean_header(col) for col in df_dbf.columns]
    print(f"[OK] Cleaned DBF headers")

    # Convert date columns in DBF
    date_keywords = ['DT_', '_DATA', '_DATA_', '_DIGITA']
    for col in df_dbf.columns:
        col_lower = col.lower()
        if any(keyword.lower() in col_lower for keyword in date_keywords):
            try:
                df_dbf[col] = pd.to_datetime(df_dbf[col], errors='coerce', format='%d/%m/%Y')
            except:
                try:
                    df_dbf[col] = pd.to_datetime(df_dbf[col], errors='coerce')
                except:
                    pass

    # Save DBF as xlsx
    dbf_xlsx_file = "SG2772176_00.xlsx"
    df_dbf.to_excel(dbf_xlsx_file, index=False)
    print(f"[OK] Saved DBF to {dbf_xlsx_file}")

    # Load the main dataset
    print("\nLoading cleaned SG merged data...")
    df_main = pd.read_excel("SG_merged_2013_2025_CLEAN.xlsx")
    print(f"[OK] Loaded main dataset - {len(df_main)} rows, {len(df_main.columns)} columns")

    # Prepare for merge
    print("\nPreparing for merge...")
    df_dbf['data_source'] = 'DBF'
    df_main['data_source'] = 'SG'

    # Get common columns
    main_cols_lower = {col.lower(): col for col in df_main.columns if col != 'data_source'}
    dbf_cols_lower = {col.lower(): col for col in df_dbf.columns if col != 'data_source'}

    common = set(main_cols_lower.keys()) & set(dbf_cols_lower.keys())
    print(f"[OK] Found {len(common)} common columns")

    # Align columns - add missing columns to DBF
    for col in df_main.columns:
        if col not in df_dbf.columns:
            df_dbf[col] = None

    # Reorder DBF to match main
    df_dbf = df_dbf[df_main.columns]

    # Merge
    print("\nMerging datasets...")
    merged = pd.concat([df_main, df_dbf], ignore_index=True, sort=False)
    print(f"[OK] Merged - Total rows: {len(merged):,}")
    print(f"[OK] Total columns: {len(merged.columns)}")

    # Save
    output_file = "SG_merged_2013_2025_WITH_DBF.xlsx"
    print(f"\nSaving to {output_file}...")
    merged.to_excel(output_file, index=False)
    print(f"[OK] Successfully saved!")

    print(f"\n{'='*50}")
    print(f"FINAL DATASET SUMMARY:")
    print(f"{'='*50}")
    print(f"  Total rows: {len(merged):,}")
    print(f"  Total columns: {len(merged.columns)}")
    print(f"  From SG files (2013-2025): {len(df_main):,} rows")
    print(f"  From DBF: {len(df_dbf):,} rows")
    print(f"\nOutput file: {output_file}")

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
