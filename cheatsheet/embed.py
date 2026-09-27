"""Tạo embedding cho các văn bản chưa có vector (incremental, chạy lại an toàn).

    uv run -m cheatsheet.embed            # chỉ embed văn bản mới / đã đổi nội dung / model đổi digest
    uv run -m cheatsheet.embed --prune    # đồng thời xoá vector không còn entry nào dùng

Mỗi entry có tối đa 2 văn bản: embed_text (tiếng Anh) và embed_text_vi (bản dịch tiếng Việt).
Vector ghi kèm digest của model trong Ollama: `ollama pull` ra bản mới (cùng tên) thì lần chạy
sau tự embed lại, tránh trộn vector của 2 phiên bản model.
"""

import sys
import time

import psycopg

from cheatsheet.config import DATABASE_URL, EMBED_MODEL
from cheatsheet.embedder import embed, model_digest, to_pgvector

BATCH = 32

TEXTS = """
    SELECT content_hash AS h, embed_text AS t FROM entries
    UNION SELECT content_hash_vi, embed_text_vi FROM entries WHERE content_hash_vi IS NOT NULL
"""


def main():
    prune = "--prune" in sys.argv
    digest = model_digest()
    with psycopg.connect(DATABASE_URL) as conn:
        todo = conn.execute(f"""
            SELECT x.h, x.t FROM ({TEXTS}) x
            WHERE NOT EXISTS (SELECT 1 FROM embeddings v WHERE v.content_hash = x.h AND v.model = %s
                                AND v.model_digest IS NOT DISTINCT FROM %s)
        """, (EMBED_MODEL, digest)).fetchall()
        print(f"{EMBED_MODEL} ({(digest or '?')[:12]}): {len(todo)} văn bản cần embed")
        t0 = time.time()
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            vecs = embed([text for _, text in chunk])
            with conn.cursor() as cur:
                cur.executemany("""
                    INSERT INTO embeddings (content_hash, model, model_digest, embedding)
                    VALUES (%s, %s, %s, %s::vector)
                    ON CONFLICT (content_hash, model) DO UPDATE
                      SET embedding = EXCLUDED.embedding, model_digest = EXCLUDED.model_digest,
                          created_at = now()
                """, [(h, EMBED_MODEL, digest, to_pgvector(v)) for (h, _), v in zip(chunk, vecs)])
            conn.commit()
            print(f"  {min(i + BATCH, len(todo))}/{len(todo)}  ({time.time() - t0:.1f}s)")
        if prune:
            n = conn.execute(f"""
                DELETE FROM embeddings v
                WHERE NOT EXISTS (SELECT 1 FROM ({TEXTS}) x WHERE x.h = v.content_hash)
            """).rowcount
            print(f"pruned {n} vector mồ côi")


if __name__ == "__main__":
    main()
