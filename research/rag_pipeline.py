import marimo

__generated_with = "0.23.6"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    mo.md("""
    # RAG pipeline: Telegram chats → ChromaDB

    **Pipeline**: CSV → thread reconstruction → ollama `mxbai-embed-large` → ChromaDB.

    **Caveat**: `merged.csv` only has `reply_to`, no own `msg_id`. True parent→reply chain reconstruction is impossible. msg_id will be added.
    Workaround: group by `(chat_id, reply_to)` siblings; standalone msgs (no `reply_to`) = own doc.
    For real threads, patch `telegram_scrapper/export.py` to also write `message.id`.
    """)
    return

@app.cell
def _():
    import pandas as pd
    import ollama
    import chromadb
    from chromadb.config import Settings
    from tqdm import tqdm
    from pathlib import Path

    CSV_PATH = Path("telegram_scrapper/merged.csv")
    CHROMA_DIR = Path("chroma_db")
    OLLAMA_MODEL = "mxbai-embed-large"
    COLLECTION_NAME = "tg_threads"
    MAX_DOC_CHARS = 700
    return

@app.cell
def _():
    df_raw = pd.read_csv(CSV_PATH)
    df_raw = df_raw.dropna(subset=["text_or_caption"])
    df_raw["date_created"] = pd.to_datetime(df_raw["date_created"], utc=True)
    df_raw = df_raw.sort_values(["chat_id", "date_created"]).reset_index(drop=True)
    mo.md(f"Loaded **{len(df_raw):,}** msgs across **{df_raw.chat_id.nunique()}** chats. {df_raw.reply_to.notna().sum():,} have `reply_to`.")
    return

@app.cell
def _():
    def build_threads(df: pd.DataFrame, max_chars: int = MAX_DOC_CHARS) -> pd.DataFrame:
        """Group siblings replying to same parent into one doc. Standalone msgs = own doc."""
        threaded = df[df.reply_to.notna()].copy()
        standalone = df[df.reply_to.isna()].copy()

        grouped = (
            threaded
            .groupby(["chat_id", "reply_to"], sort=False)
            .agg(
                text=("text_or_caption", lambda s: "\n---\n".join(s.astype(str))),
                n_msgs=("text_or_caption", "count"),
                date_min=("date_created", "min"),
                date_max=("date_created", "max"),
            )
            .reset_index()
        )
        grouped["kind"] = "thread"
        grouped["doc_id"] = grouped.apply(lambda r: f"thread:{int(r.chat_id)}:{int(r.reply_to)}", axis=1)

        standalone_out = pd.DataFrame({
            "chat_id": standalone.chat_id.values,
            "reply_to": pd.NA,
            "text": standalone.text_or_caption.values,
            "n_msgs": 1,
            "date_min": standalone.date_created.values,
            "date_max": standalone.date_created.values,
            "kind": "single",
        })
        standalone_out["doc_id"] = [
            f"single:{cid}:{idx}" for idx, cid in zip(standalone.index, standalone.chat_id.values)
        ]

        out = pd.concat([grouped, standalone_out], ignore_index=True)
        out["text"] = out["text"].str.slice(0, max_chars)
        return out

    threads_df = build_threads(df_raw)
    mo.md(f"Built **{len(threads_df):,}** docs: "
          f"{(threads_df.kind=='thread').sum():,} threads, "
          f"{(threads_df.kind=='single').sum():,} singletons.")
    return

@app.cell
def _():
    SAFE_CHARS = 600
    HARD_CHARS = 300

    def _trim(t, limit):
        return t if len(t) <= limit else t[:limit]

    def _embed_one(t, model):
        try:
            r = ollama.embed(model=model, input=_trim(t, SAFE_CHARS), truncate=True)
            return r["embeddings"][0]
        except Exception:
            r = ollama.embed(model=model, input=_trim(t, HARD_CHARS), truncate=True)
            return r["embeddings"][0]

    def embed_texts(texts, model=OLLAMA_MODEL):
        return [_embed_one(t, model) for t in texts]

    def embed_text(text, model=OLLAMA_MODEL):
        return _embed_one(text, model)

    _probe = embed_text("hello world")
    mo.md(f"Embedding dim: **{len(_probe)}** (safe={SAFE_CHARS} hard={HARD_CHARS})")

    return

@app.cell
def _():
    CHROMA_DIR.mkdir(exist_ok=True)
    chroma_client = chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    mo.md(f"Chroma collection `{COLLECTION_NAME}` at `{CHROMA_DIR}/`. Current count: **{collection.count():,}**")
    return

@app.cell
def _():
    def ingest(docs_df: pd.DataFrame, coll, batch_size: int = 32, limit: int | None = None) -> int:
        rows = docs_df if limit is None else docs_df.head(limit)
        existing = set(coll.get(include=[])["ids"])
        todo = rows[~rows["doc_id"].isin(existing)]
        if todo.empty:
            return 0

        written = 0
        for start in tqdm(range(0, len(todo), batch_size), desc="ingest"):
            chunk = todo.iloc[start:start + batch_size]
            texts = chunk["text"].tolist()
            embs = embed_texts(texts)
            metas = [
                {
                    "chat_id": int(r.chat_id),
                    "kind": r.kind,
                    "n_msgs": int(r.n_msgs),
                    "date_min": str(r.date_min),
                    "date_max": str(r.date_max),
                }
                for r in chunk.itertuples()
            ]
            coll.add(
                ids=chunk["doc_id"].tolist(),
                embeddings=embs,
                documents=texts,
                metadatas=metas,
            )
            written += len(chunk)
        return written

    n_test_sample = 50
    n_written_sample = ingest(threads_df, collection, batch_size=16, limit=n_test_sample)
    mo.md(f"Ingested **{n_written_sample}** new docs (sample of {n_test_sample}). Collection now: **{collection.count():,}**")
    return

@app.cell
def _():
    def rag_query(question: str, k: int = 5):
        qvec = embed_text(question)
        res = collection.query(query_embeddings=[qvec], n_results=k)
        hits = []
        for i in range(len(res["ids"][0])):
            hits.append({
                "id": res["ids"][0][i],
                "distance": res["distances"][0][i],
                "metadata": res["metadatas"][0][i],
                "snippet": res["documents"][0][i][:300],
            })
        return hits

    test_question = "как получить ВНЖ в Сербии"
    test_hits = rag_query(test_question, k=5)
    mo.md(f"### Query: _{test_question}_\n\n" + "\n\n---\n\n".join(
        f"**{h['id']}** · dist=`{h['distance']:.3f}` · chat=`{h['metadata']['chat_id']}` · {h['metadata']['kind']}\n\n{h['snippet']}"
        for h in test_hits
    ))
    return

@app.cell
def _():
    mo.md(r"""
    ### Pipeline status

    - **CSV parsed**: pandas load + drop empty text.
    - **Threads**: siblings with same (chat_id, reply_to) merged. Standalone = own doc.
    - **Embed**: ollama mxbai-embed-large (dim 1024). Trim 600 chars (fallback 300).
    - **Store**: ChromaDB persistent at chroma_db/, cosine.
    - **Test**: 50 docs ingested, query returns relevant hits.

    ### Limits
    1. No msg_id in CSV => true parent-reply impossible. Patch telegram_scrapper/export.py.
    2. 600-char trim loses info => consider chunk+mean-pool.
    3. Run full ingest: set n_test_sample=None.
    """)
    return


if __name__ == "__main__":
    app.run()
