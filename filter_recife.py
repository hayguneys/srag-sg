import pandas as pd
import os

work_dir = r"C:\Users\gabriel.olima\Desktop\dashboard-git"
os.chdir(work_dir)

print("Loading merged dataset...")
df = pd.read_excel("SG_merged_2013_2025_WITH_DBF.xlsx")
print(f"[OK] Loaded {len(df)} rows, {len(df.columns)} columns")

# Find municipality-related columns
print("\nSearching for municipality columns...")
munic_cols = [col for col in df.columns if 'munic' in col.lower() or 'munres' in col.lower()]
print(f"Found columns: {munic_cols}")

# Check what's in these columns
for col in munic_cols:
    print(f"\n{col}:")
    print(f"  - Unique values: {df[col].nunique()}")
    print(f"  - Sample values: {df[col].dropna().unique()[:5]}")

# Look for actual municipality names
print("\n\nSearching for municipality name columns...")
name_cols = [col for col in df.columns if 'nom' in col.lower() and ('munic' in col.lower() or 'res' in col.lower())]
print(f"Found name columns: {name_cols}")

for col in name_cols:
    print(f"\n{col}:")
    print(f"  - Unique values: {df[col].nunique()}")
    print(f"  - Sample values: {df[col].dropna().unique()[:10]}")
