import pandas as pd

# ✅ Load Excel file
file_path = "march_update_2025_ibw_dynasty_top_1000.xlsx"  # Ensure correct filename
xls = pd.ExcelFile(file_path)

# ✅ Print column names for each sheet
for sheet_name in xls.sheet_names:
    df = pd.read_excel(xls, sheet_name)
    print(f"\n🔍 Sheet: {sheet_name}")
    print(df.columns.tolist())  # ✅ Print actual column names
