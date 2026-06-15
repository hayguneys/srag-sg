"""Reconstruct data/sg_srag_linked.parquet — SG cases that progressed to SRAG.

Matches SG and SRAG records belonging to the same person and keeps the pairs
where the SG symptom onset precedes (or coincides with) the SRAG symptom onset,
i.e. a Sindrome Gripal case that later progressed to a Sindrome Respiratoria
Aguda Grave.

Match key (identity combo): CPF + data de nascimento + sexo.
  - CPF is the primary identity field.
  - DT_NASC and SEXO corroborate the same individual (in this data every CPF
    match also agrees on date of birth, so the combo is robust).
  - CNES (COD_UNID / CO_UNI_NOT) is NOT used as an equality key: the two banks
    use different unit-code registries (SG has 7 local codes, SRAG 139 on a
    different scale), so requiring CNES equality would discard true matches.

Both banks are filtered to symptom-onset years 2022-2026 before matching
(DT_PRISINT for SG, DT_SIN_PRI for SRAG). Progression direction and the gap
between cases are both measured on the symptom-onset dates, and only pairs
whose onsets fall within MAX_GAP_DAYS (30) of each other are kept.

Output columns consumed by pages/1_SG.py (Progressao para SRAG tab):
  sg_SEXO, sg_IDADE, sg_NOM_BAIRRO, sg_DT_DIGITA, sg_DT_PRISINT, sg_classi_label,
  srag_DT_DIGITA, srag_DT_SIN_PRI, srag_classi_label, srag_evolucao_label,
  srag_NM_UN_INTE, gap_dias, gap_faixa
"""
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent
SG_PATH   = DATA_DIR / "sg_main.parquet"
SRAG_PATH = DATA_DIR / "srag_sintomas.parquet"
OUT_PATH  = DATA_DIR / "sg_srag_linked.parquet"

YEAR_MIN, YEAR_MAX = 2022, 2026

# A true SG->SRAG progression is a single clinical episode: the SRAG symptom
# onset must fall within this many days of the SG symptom onset. Longer gaps are
# treated as separate episodes (e.g. reinfections), not progressions.
MAX_GAP_DAYS = 30

SG_CLASSI = {
    1: "SG por influenza",
    2: "SG por outro vírus respiratório",
    3: "SG por outro agente etiológico",
    4: "SG não especificado",
    5: "SG por covid-19",
}
SRAG_CLASSI = {
    1: "SRAG por Influenza",
    2: "SRAG por outro vírus resp.",
    3: "SRAG por outro agente",
    4: "SRAG não especificado",
    5: "SRAG por COVID-19",
}
SRAG_EVOLUCAO = {
    1: "Cura",
    2: "Obito",
    3: "Obito por outras causas",
    9: "Ignorado",
}
GAP_BINS = [
    (0, 7, "0-7d"), (8, 14, "8-14d"), (15, 30, "15-30d"), (31, 60, "31-60d"),
    (61, 90, "61-90d"), (91, 180, "91-180d"), (181, 365, "181-365d"),
]


def _norm_cpf(s: pd.Series) -> pd.Series:
    cpf = pd.to_numeric(s, errors="coerce")
    out = cpf.dropna().astype("int64").astype(str).str.zfill(11)
    return out.reindex(s.index)


def _gap_faixa(days: float) -> str | None:
    if pd.isna(days):
        return None
    d = int(days)
    for lo, hi, lbl in GAP_BINS:
        if lo <= d <= hi:
            return lbl
    return ">365d" if d > 365 else None


def main() -> None:
    # ---- SG ----------------------------------------------------------------
    sg = pd.read_parquet(SG_PATH)
    sg["DT_DIGITA"]  = pd.to_datetime(sg["DT_DIGITA"], errors="coerce")
    sg["DT_PRISINT"] = pd.to_datetime(sg.get("DT_PRISINT"), errors="coerce")
    sg = sg[sg["DT_PRISINT"].dt.year.between(YEAR_MIN, YEAR_MAX)].copy()
    sg["cpf"] = _norm_cpf(sg["NU_CPF"])
    sg["dob"] = pd.to_datetime(sg["DT_NASC"], format="%d/%m/%Y", errors="coerce")
    sg["sex"] = pd.to_numeric(sg["SEXO"], errors="coerce").map({1: "M", 2: "F"})
    sg = sg.dropna(subset=["cpf", "dob", "sex"])

    sg_keep = sg[[
        "cpf", "dob", "sex", "SEXO", "IDADE", "NOM_BAIRRO",
        "DT_DIGITA", "DT_PRISINT", "CLASSI_FIN",
    ]].rename(columns={
        "SEXO": "sg_SEXO", "IDADE": "sg_IDADE", "NOM_BAIRRO": "sg_NOM_BAIRRO",
        "DT_DIGITA": "sg_DT_DIGITA", "DT_PRISINT": "sg_DT_PRISINT",
    })
    sg_keep["sg_classi_label"] = (
        pd.to_numeric(sg["CLASSI_FIN"], errors="coerce").map(SG_CLASSI).values
    )
    sg_keep = sg_keep.drop(columns=["CLASSI_FIN"])

    # ---- SRAG --------------------------------------------------------------
    sr = pd.read_parquet(SRAG_PATH)
    sr["DT_DIGITA"]  = pd.to_datetime(sr["DT_DIGITA"], errors="coerce")
    sr["DT_SIN_PRI"] = pd.to_datetime(sr.get("DT_SIN_PRI"), errors="coerce")
    sr = sr[sr["DT_SIN_PRI"].dt.year.between(YEAR_MIN, YEAR_MAX)].copy()
    sr["cpf"] = _norm_cpf(sr["NU_CPF"])
    sr["dob"] = pd.to_datetime(sr["DT_NASC"], format="%d/%m/%Y", errors="coerce")
    sr["sex"] = sr["CS_SEXO"].map({"M": "M", "F": "F"})
    sr = sr.dropna(subset=["cpf", "dob", "sex"])

    sr_keep = sr[[
        "cpf", "dob", "sex", "DT_DIGITA", "DT_SIN_PRI",
        "CLASSI_FIN", "EVOLUCAO", "NM_UN_INTE",
    ]].rename(columns={
        "DT_DIGITA": "srag_DT_DIGITA", "DT_SIN_PRI": "srag_DT_SIN_PRI",
        "NM_UN_INTE": "srag_NM_UN_INTE",
    })
    sr_keep["srag_classi_label"] = (
        pd.to_numeric(sr["CLASSI_FIN"], errors="coerce").map(SRAG_CLASSI).values
    )
    sr_keep["srag_evolucao_label"] = (
        pd.to_numeric(sr["EVOLUCAO"], errors="coerce").map(SRAG_EVOLUCAO).values
    )
    sr_keep = sr_keep.drop(columns=["CLASSI_FIN", "EVOLUCAO"])

    # ---- match on identity combo ------------------------------------------
    linked = sg_keep.merge(sr_keep, on=["cpf", "dob", "sex"], how="inner")

    # progression = SG symptom onset on/before the SRAG symptom onset
    linked = linked[linked["sg_DT_PRISINT"] <= linked["srag_DT_SIN_PRI"]].copy()

    linked["gap_dias"] = (
        linked["srag_DT_SIN_PRI"] - linked["sg_DT_PRISINT"]
    ).dt.days

    # keep only pairs within the progression window (same clinical episode)
    linked = linked[linked["gap_dias"] <= MAX_GAP_DAYS].copy()

    linked["gap_faixa"] = linked["gap_dias"].apply(_gap_faixa)

    # one SRAG pairing per SG record: keep the earliest SRAG onset after the SG
    linked = linked.sort_values("srag_DT_SIN_PRI").drop_duplicates(
        subset=["cpf", "dob", "sex", "sg_DT_PRISINT"], keep="first"
    )

    linked = linked.drop(columns=["cpf", "dob", "sex"]).reset_index(drop=True)
    linked.to_parquet(OUT_PATH, index=False)

    print(f"Wrote {OUT_PATH} — {len(linked)} progressions")
    print(f"  distinct desfechos: {linked['srag_evolucao_label'].value_counts().to_dict()}")
    print(f"  obitos: {(linked['srag_evolucao_label'] == 'Obito').sum()}")
    print(f"  gap_faixa: {linked['gap_faixa'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
