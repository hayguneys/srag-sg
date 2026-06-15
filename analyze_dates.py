import pandas as pd

df = pd.read_excel("SG_merged_2013_2025.xlsx")

print(f"Total rows: {len(df):,}")
print(f"Total columns: {len(df.columns)}")
print(f"source_year range: {df['source_year'].min()} to {df['source_year'].max()}")
print(f"source_year counts:\n{df['source_year'].value_counts().sort_index()}")
print()

date_cols = [
    'DT_PREENC', 'DT_NASC', 'DT_PRISINT', 'DT_VACINA', 'DT_ANTIVIR',
    'DT_COLETA', 'IFI_DATA', 'PCR_DATA', 'DT_ENCERRA', 'DT_DIGITA',
    'DOSE_1_COV', 'DOSE_2_COV', 'DOSE_REF', 'DOSE_2REF', 'DOSE_ADIC', 'DOS_RE_BI',
]

print("Date column ranges:")
print("-" * 70)
for col in date_cols:
    if col in df.columns:
        s = df[col].dropna()
        if len(s):
            print(f"  {col:<15} {str(s.min().date())} to {str(s.max().date())}  ({s.notna().sum():,} non-null)")
        else:
            print(f"  {col:<15} (all null)")
