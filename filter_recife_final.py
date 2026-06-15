import pandas as pd
import os

work_dir = r"C:\Users\gabriel.olima\Desktop\dashboard-git"
os.chdir(work_dir)

print("Loading merged dataset...")
df = pd.read_excel("SG_merged_2013_2025_WITH_DBF.xlsx")
print(f"[OK] Original dataset: {len(df):,} rows, {len(df.columns)} columns")

print("\nFiltering by COD_MUNRES = 261160 (Recife)...")
# Filter by Recife code - keep all NAs in other columns
df_recife = df[df['COD_MUNRES'] == 261160].copy()
print(f"[OK] Filtered dataset: {len(df_recife):,} rows, {len(df_recife.columns)} columns")

print(f"\nRecords removed: {len(df) - len(df_recife):,}")
print(f"Percentage retained: {(len(df_recife) / len(df) * 100):.1f}%")

# Save filtered dataset
output_file = "SG_Recife_2013_2025.xlsx"
print(f"\nSaving filtered dataset to {output_file}...")
df_recife.to_excel(output_file, index=False)
print(f"[OK] Successfully saved!")

print(f"\n{'='*50}")
print(f"RECIFE DATASET SUMMARY:")
print(f"{'='*50}")
print(f"  Total rows: {len(df_recife):,}")
print(f"  Total columns: {len(df_recife.columns)}")
print(f"  Municipality code: 261160")
print(f"  Date range: 2013-2025")

print(f"\nOutput file: {output_file}")
