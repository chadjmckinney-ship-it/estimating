import openpyxl, csv
from pathlib import Path
wb = openpyxl.load_workbook(r"C:\Users\Chad\Estimate_Projects\import\Updated Estimate.xlsm", data_only=True, read_only=True)
out = Path(r"C:\Users\Chad\Estimate_Projects\import")
for name in [
    "Mono Slab on Grade Garden Style",
    "Mono Slab on Grade Building 1",
    "Mono Slab on Grade Building 2",
    "SLAB ON GRADE",
    "Information",
    "Gd Beams",
]:
    ws = wb[name]
    safe = "".join(c if c.isalnum() else "_" for c in name)[:50] + ".csv"
    path = out / safe
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for row in ws.iter_rows(max_row=130, max_col=40, values_only=True):
            w.writerow(list(row))
    print("WROTE", path.name, "max_row_dumped=130")
wb.close()
