import pandas as pd
import os

work_dir = r"C:\Users\gabriel.olima\Desktop\dashboard-git"
os.chdir(work_dir)

print("Loading merged dataset...")
df = pd.read_excel("SG_merged_2013_2025_WITH_DBF.xlsx")

# List all columns
print("\nAll columns:")
for i, col in enumerate(df.columns, 1):
    print(f"{i:3d}. {col}")

# Look for text columns that might have Recife
print("\n\nSearching for 'Recife' in text columns...")
for col in df.columns:
    if df[col].dtype == 'object':  # String columns
        if df[col].astype(str).str.contains('Recife', case=False, na=False).any():
            print(f"\nFound 'Recife' in column: {col}")
            recife_count = df[col].astype(str).str.contains('Recife', case=False, na=False).sum()
            print(f"  - Count: {recife_count}")
            print(f"  - Unique values with 'Recife': {df[df[col].astype(str).str.contains('Recife', case=False, na=False)][col].unique()[:5]}")

# Check if COD_MUNRES 260960 might be Recife
print("\n\nChecking municipality codes...")
print("\nCOD_MUNRES unique values (top 20):")
print(df['COD_MUNRES'].value_counts().head(20))

print("\n\nCOD_MUNIC unique values:")
print(df['COD_MUNIC'].value_counts())
