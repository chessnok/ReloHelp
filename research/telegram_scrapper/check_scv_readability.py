import pandas as pd

df = pd.read_csv("my_export.csv")
print(df.columns, len(df))
