import marimo

__generated_with = "0.23.6"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    mo.md(
        """
        # CSV readability check

        Quick validation for Telegram export CSVs (`merged.csv`, single-chat exports, etc.).
        """
    )
    return (mo,)


@app.cell
def _(mo):
    from pathlib import Path

    csv_path = mo.ui.text(
        value="merged.csv",
        label="CSV path (relative to `research/telegram_scrapper/` or absolute)",
        full_width=True,
    )
    csv_path
    return Path, csv_path


@app.cell
def _(Path, csv_path, mo):
    import pandas as pd

    path = Path(csv_path.value)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path

    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")

    df = pd.read_csv(path)
    expected = {"text_or_caption", "msg_id", "reply_to", "chat_id", "date_created"}
    missing = expected - set(df.columns)
    extra = set(df.columns) - expected

    mo.md(
        f"""
        **File:** `{path}`  
        **Rows:** {len(df):,} · **Columns:** {len(df.columns)}

        | Check | Result |
        |-------|--------|
        | Expected columns present | {"yes" if not missing else f"missing {sorted(missing)}"} |
        | Extra columns | {", ".join(sorted(extra)) or "none"} |
        """
    )
    return df, expected, extra, missing, path, pd


@app.cell
def _(df, mo):
    mo.ui.table(df.dtypes.reset_index().rename(columns={"index": "column", 0: "dtype"}))
    return


@app.cell
def _(df, mo):
    nulls = df.isna().sum().sort_values(ascending=False)
    mo.ui.table(nulls.reset_index().rename(columns={"index": "column", 0: "null_count"}))
    return


@app.cell
def _(df, mo):
    preview = df.head(10)
    mo.ui.table(preview)
    return


if __name__ == "__main__":
    app.run()
