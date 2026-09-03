import openpyxl
wb = openpyxl.load_workbook(r"C:\Users\Chad\Estimate_Projects\import\Updated Estimate.xlsm", data_only=True, read_only=True)
print("SHEETS:")
for i, n in enumerate(wb.sheetnames, 1):
    print(f"{i:02d} {n}")
wb.close()
