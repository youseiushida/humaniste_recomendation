# FastAPI + microCMS 関連記事 自動更新

パイプライン:
1. Webhook（microCMS）→ FastAPI `/webhook/microcms`
2. microCMS から記事を取得
3. 正規化（GPT-5）→ 日本語の標準化テキストを生成
4. 埋め込み（text-embedding-3-large）
5. pgvector で近傍上位4件を検索
6. microCMS に関連記事（4件）を PATCH 更新
7. その4件についても再検索 → 各自の関連記事を再設定（伝播更新）

## セットアップ

1) 依存関係インストール（pyproject.toml を使用）
```bash
pip install -e .
```

2) .env（環境変数）
```
OPENAI_API_KEY=...
MICROCMS_API_KEY=...
MICROCMS_SERVICE_ID=...
MICROCMS_WEBHOOK_SECRET=... # 任意。設定すると署名検証を有効化
MICROCMS_ENDPOINT=blog
MICROCMS_RELATION_FIELD=related_blog_post
DATABASE_URL=postgresql+psycopg://app:app@localhost:9002/app
OPENAI_NORMALIZE_MODEL=gpt-5
OPENAI_EMBED_MODEL=text-embedding-3-large
```

3) pgvector（Docker）
```bash
docker compose up -d db
```

4) API を起動
```bash
uvicorn app.main:app --host 0.0.0.0 --port 9001 --reload
```

5) 初期バッチ（⓪）
```bash
python -m app.initial_batch
```

## microCMS Webhook（カスタム通知）
- URL: `<あなたの公開URL>/webhook/microcms`
- シークレットを設定すると `x-microcms-signature`（HMAC-SHA256 / raw body）で署名検証

## メモ
- 関連記事フィールドは `relationList` 型を想定。PATCH ボディにはコンテンツID配列を送ります。
- DBテーブル: `article_embeddings(id, title, normalized_text, embedding vector(3072), updated_at)` を使用。IVFFlat（cosine）インデックスはデータ投入後の再作成/調整を推奨。
