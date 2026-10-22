#!/usr/bin/env python3
"""Embed every product (title | brand | category) once with text-embedding-3-small (256-d) and cache to disk.
Resumable: writes chunk files to emb_cache/ and merges into product_emb.f16.npy + product_emb_ids.json.

Does not run on import. Needs BOXAPI_API_KEY. Outputs stay under DATA_DIR and are gitignored.

  python backend/app/engine/embed_products.py
"""
import json, os, sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from openai import OpenAI

HERE = os.path.dirname(os.path.abspath(__file__))
DIM, BATCH = 256, 1000


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def data_dir():
    return os.environ.get('DATA_DIR') or os.path.join(_repo_root(), 'data')


def main():
    cache = os.path.join(data_dir(), 'emb_cache')
    os.makedirs(cache, exist_ok=True)
    key = os.environ.get('BOXAPI_API_KEY') or ''
    if not key:
        print('BOXAPI_API_KEY is not set; refusing to call the embeddings API.', file=sys.stderr)
        return 1
    base = os.environ.get('BOXAPI_BASE_URL') or 'https://ai.boxapi.ir/ai/v1'
    db = os.environ.get('DATABASE_PATH') or os.path.join(data_dir(), 'torob.sqlite')
    if not os.path.exists(db):
        print(f'database not found: {db}', file=sys.stderr)
        return 1
    cli = OpenAI(api_key=key, base_url=base)
    con = sqlite3.connect(db)
    rows = con.execute('SELECT product_id, persian_title, brand_name, category_name FROM products ORDER BY rowid').fetchall()
    ids = [r[0] for r in rows]
    texts = [f"{r[1] or ''} | {r[2] or ''} | {r[3] or ''}"[:300] for r in rows]
    chunks = [(i, texts[i:i + BATCH]) for i in range(0, len(texts), BATCH)]
    cost = [0.0]

    def work(c):
        i, tx = c
        fn = os.path.join(cache, f'{i:07d}.npy')
        if os.path.exists(fn):
            return
        for att in range(5):
            try:
                r = cli.embeddings.create(model='text-embedding-3-small', input=tx, dimensions=DIM)
                break
            except Exception:
                time.sleep(3 * (att + 1))
        else:
            raise RuntimeError(f'chunk {i} failed')
        cost[0] += float((r.model_extra or {}).get('cost', 0) or 0)
        np.save(fn, np.array([d.embedding for d in r.data], dtype=np.float16))

    t0 = time.time()
    with ThreadPoolExecutor(6) as ex:
        for n, _ in enumerate(ex.map(work, chunks), 1):
            if n % 20 == 0:
                print(f'{n}/{len(chunks)} chunks {time.time()-t0:.0f}s cost=${cost[0]:.4f}', flush=True)
    mat = np.concatenate([np.load(os.path.join(cache, f'{i:07d}.npy')) for i, _ in chunks])
    mat = mat.astype(np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8
    np.save(os.path.join(data_dir(), 'product_emb.f16.npy'), mat.astype(np.float16))
    json.dump(ids, open(os.path.join(data_dir(), 'product_emb_ids.json'), 'w'))
    print('done', mat.shape, f'cost this session ${cost[0]:.4f}', f'{time.time()-t0:.0f}s')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
