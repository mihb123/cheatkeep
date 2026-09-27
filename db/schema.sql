-- Cheatsheet schema v3 — thiết kế cho tìm kiếm ngữ nghĩa (pgvector), song ngữ Anh–Việt.
--
--   sheets      1 dòng / cheatsheet; `layout` giữ cấu trúc hiển thị (card, section)
--   entries     1 dòng / lệnh, phím tắt, snippet, ghi chú — ĐƠN VỊ TÌM KIẾM; mỗi entry có tối đa
--               2 văn bản embed: embed_text (gốc tiếng Anh) và embed_text_vi (bản dịch + cụm từ tìm kiếm)
--   embeddings  cache vector, khoá (content_hash, model) — không phụ thuộc id của entries
--
-- sheets/entries là dữ liệu sinh ra từ HTML nên được tạo lại mỗi lần nạp seed; embeddings giữ
-- nguyên, văn bản không đổi sẽ tự khớp lại vector cũ qua content_hash (không phải embed lại).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

DROP FUNCTION IF EXISTS search_entries(text, vector, text, text, int);
DROP FUNCTION IF EXISTS search_entries(text, vector, text, text, int, float8);
DROP FUNCTION IF EXISTS search_entries(text, vector, text, text, int, float8, text[], float8);
DROP FUNCTION IF EXISTS sheet_json(text);
DROP VIEW     IF EXISTS sheet_list;
DROP TABLE    IF EXISTS entries, sheets CASCADE;

-- unaccent() chỉ STABLE (phụ thuộc search_path) → bọc lại IMMUTABLE để dùng trong cột generated.
-- Bỏ dấu để "xoa dong" khớp "xoá dòng"/"xóa dòng" (unaccent cũng đổi đ → d).
CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$;

CREATE TABLE sheets (
  id          serial PRIMARY KEY,
  slug        text NOT NULL UNIQUE,
  title       text NOT NULL,
  aliases     text[] NOT NULL DEFAULT '{}',  -- từ khoá nhận diện sheet trong câu hỏi: {mysql}, {neovim,nvim,vim}
  subtitle    text,
  badge       text,
  description text,
  logo        text,
  source_url  text,
  links       jsonb NOT NULL DEFAULT '[]',   -- [{label, url}]
  meta        jsonb NOT NULL DEFAULT '{}',   -- dữ liệu riêng từng trang (legend, ...)
  -- [{title, icon, color, tip, title_accent, title_note, layout, body_cols,
  --   sections: [{label, kind, lang, columns, copy_lines}]}]
  layout      jsonb NOT NULL DEFAULT '[]',
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE entries (
  id           serial PRIMARY KEY,
  sheet_id     int  NOT NULL REFERENCES sheets(id) ON DELETE CASCADE,
  card_pos     int  NOT NULL,                -- vị trí trong sheets.layout (1-based)
  section_pos  int  NOT NULL,                -- vị trí trong layout[card].sections (1-based)
  position     int  NOT NULL,
  card         text NOT NULL,                -- ngữ cảnh dạng chữ, vd "Create / Delete / Modify Table"
  section      text,                         -- vd "Create"
  kind         text NOT NULL CHECK (kind IN ('command', 'shortcut', 'option', 'snippet', 'note')),
  command      text,                         -- thứ để gõ / copy (NULL với note)
  description  text,
  details      text,                         -- giải thích dài (tooltip)
  example      text,
  danger       text,                         -- cảnh báo lệnh nguy hiểm
  lang         text,                         -- bash | sql | toml | ...
  display      jsonb NOT NULL DEFAULT '{}',  -- chỉ phục vụ render web: key_style, variant, note, raw, tags
  embed_text   text NOT NULL,                -- văn bản đem đi embed (sheet › card › section + nội dung)
  content_hash text NOT NULL,                -- sha256(embed_text) → khoá sang embeddings
  description_vi  text,                      -- mô tả tiếng Việt (data/translations.vi.json)
  embed_text_vi   text,                      -- ngữ cảnh + command + mô tả Việt + cụm từ tìm kiếm Việt
  content_hash_vi text,                      -- sha256(embed_text_vi); NULL khi chưa dịch
  search_tsv   tsvector GENERATED ALWAYS AS (
                 to_tsvector('simple', f_unaccent(embed_text || E'\n' || COALESCE(embed_text_vi, '')))) STORED,
  UNIQUE (sheet_id, card_pos, section_pos, position)
);

CREATE INDEX ON entries (sheet_id);
CREATE INDEX ON entries (content_hash);
CREATE INDEX ON entries (content_hash_vi);
CREATE INDEX ON entries USING gin (search_tsv);

-- Chỉ dùng bge-m3 nên cố định vector(1024). Thêm model khác chiều → bảng/cột riêng, không trộn vào
-- chung một HNSW index. model_digest (digest Ollama) để tự embed lại khi model được pull bản mới
-- nhưng vẫn giữ tên.
CREATE TABLE IF NOT EXISTS embeddings (
  content_hash text NOT NULL,
  model        text NOT NULL,
  embedding    vector(1024) NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (content_hash, model)
);
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS model_digest text;
CREATE INDEX IF NOT EXISTS embeddings_hnsw ON embeddings USING hnsw (embedding vector_cosine_ops);


-- ------------------------------------------------------------------ web
-- Dựng lại cấu trúc card → section → item cho frontend từ layout + entries.
CREATE FUNCTION sheet_json(p_slug text) RETURNS jsonb
LANGUAGE sql STABLE AS $$
  SELECT jsonb_build_object(
    'slug', sh.slug, 'title', sh.title, 'subtitle', sh.subtitle, 'badge', sh.badge,
    'description', sh.description, 'logo', sh.logo, 'source_url', sh.source_url,
    'links', sh.links, 'meta', sh.meta,
    'cards', COALESCE((
      SELECT jsonb_agg((c.card - 'sections') || jsonb_build_object('sections', COALESCE((
        SELECT jsonb_agg(s.sec || CASE s.sec->>'kind'
          WHEN 'code' THEN jsonb_build_object('items', '[]'::jsonb, 'content', (
            SELECT string_agg(e.display->>'raw', E'\n' ORDER BY e.position) FROM entries e
            WHERE e.sheet_id = sh.id AND e.card_pos = c.ord AND e.section_pos = s.ord))
          WHEN 'text' THEN jsonb_build_object('items', '[]'::jsonb, 'content', (
            SELECT string_agg(e.description, E'\n' ORDER BY e.position) FROM entries e
            WHERE e.sheet_id = sh.id AND e.card_pos = c.ord AND e.section_pos = s.ord))
          WHEN 'tags' THEN jsonb_build_object('items', COALESCE((
            SELECT jsonb_agg(jsonb_build_object('key', t.tag) ORDER BY e.position, t.n) FROM entries e,
                   jsonb_array_elements_text(e.display->'tags') WITH ORDINALITY t(tag, n)
            WHERE e.sheet_id = sh.id AND e.card_pos = c.ord AND e.section_pos = s.ord), '[]'))
          ELSE jsonb_build_object('items', COALESCE((
            SELECT jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                     'key', e.command, 'key_style', e.display->>'key_style',
                     'description', e.description, 'note', e.display->>'note',
                     'tip', e.details, 'example', e.example, 'danger', e.danger,
                     'variant', e.display->>'variant')) ORDER BY e.position)
            FROM entries e
            WHERE e.sheet_id = sh.id AND e.card_pos = c.ord AND e.section_pos = s.ord), '[]'))
        END ORDER BY s.ord)
        FROM jsonb_array_elements(c.card->'sections') WITH ORDINALITY s(sec, ord)), '[]'))
      ORDER BY c.ord)
      FROM jsonb_array_elements(sh.layout) WITH ORDINALITY c(card, ord)), '[]')
  )
  FROM sheets sh WHERE sh.slug = p_slug
$$;

CREATE VIEW sheet_list AS
SELECT sh.slug, sh.title, sh.subtitle,
       jsonb_array_length(sh.layout) AS cards,
       (SELECT count(*) FROM entries e WHERE e.sheet_id = sh.id) AS entries
FROM sheets sh ORDER BY sh.title;


-- ------------------------------------------------------------------ search
-- Hybrid search: score = cosine similarity + p_kw_weight × (tỷ lệ từ trong câu hỏi xuất hiện ở entry).
--   Không dùng RRF: câu hỏi tiếng Việt lẫn vài từ tiếng Anh ("file", "server") khiến nhánh keyword
--   xếp hạng nhiễu; cộng điểm thưởng theo tỷ lệ khớp giữ vector làm chủ, keyword chỉ để phân định
--   khi câu hỏi chứa đúng token của lệnh (mysqldump, --cwd, :wq ...) hoặc từ tiếng Việt gõ không dấu.
--   Phạm vi sheet do cheatsheet.search.parse_query() quyết định:
--   p_sheet  lọc cứng — người dùng chỉ rõ (-s hoặc tiền tố "mysql: ...").
--   p_boost  sheet có tên trong câu hỏi → chỉ cộng p_boost_weight, không lọc: tên tool trong câu có
--            thể là đối tượng chứ không phải tool cần tìm ("import history from bash" → atuin,
--            "find and replace in vim" → neovim). Tên tool vẫn giữ trong keyword vì "bash" giúp khớp
--            đúng `atuin import bash`; bản thân vector câu hỏi cũng đã nghiêng về sheet đó.
--
-- Hai bước, viết để planner dùng được index:
--   1. Lấy ứng viên: nhánh vector ORDER BY khoảng cách trực tiếp trên embeddings (HNSW, iterative
--      scan để lọc theo sheet/model mà vẫn đủ LIMIT) + nhánh keyword @@ trực tiếp trên entries (GIN).
--   2. Chấm điểm lại chính xác: similarity = max(cosine với vector tiếng Anh, vector tiếng Việt).
-- Với vài trăm entry planner vẫn có thể chọn seq scan vì rẻ hơn — shape query chỉ đảm bảo khi dữ
-- liệu lớn lên thì index được dùng.
CREATE FUNCTION search_entries(
  p_query     text,
  p_embedding vector,
  p_model     text,
  p_sheet     text   DEFAULT NULL,
  p_limit     int    DEFAULT 10,
  p_kw_weight float8 DEFAULT 0.15,
  p_boost     text[] DEFAULT '{}',
  p_boost_weight float8 DEFAULT 0.05  -- 0.1 bắt đầu kéo entry sheet bash lên trên atuin ở ví dụ trên
) RETURNS TABLE (
  id int, sheet text, card text, section text, kind text, command text,
  description text, description_vi text, details text, example text, danger text, lang text,
  score float8, similarity float8, kw_ratio float8
)
LANGUAGE sql STABLE
SET hnsw.iterative_scan = 'relaxed_order'
AS $$
  WITH target AS (
    SELECT p_sheet AS slug, (SELECT sh.id FROM sheets sh WHERE sh.slug = p_sheet) AS sheet_id,
           ARRAY(SELECT sh.id FROM sheets sh WHERE sh.slug = ANY (p_boost)) AS boost_ids, t.terms,
           CASE WHEN cardinality(t.terms) > 0 THEN
             array_to_string(ARRAY(SELECT quote_literal(x) FROM unnest(t.terms) x), ' | ')::tsquery
           END AS tsq
    FROM (SELECT ARRAY(SELECT x FROM unnest(tsvector_to_array(to_tsvector('simple', f_unaccent(lower(p_query))))) x
                       -- hư từ tiếng Việt (đã bỏ dấu) xuất hiện ở hầu hết câu hỏi, không giúp phân định
                       WHERE x <> ALL ('{la,gi,cua,cac,nhung,cho,trong,mot,va,voi,de,thi,nao,cach,
                                        the,nay,do,duoc,co,cau,lenh,muon,toi,minh,hay}'::text[])) AS terms) t
  ),
  vec AS (  -- mỗi entry có ≤ 2 vector → lấy dư gấp đôi rồi gộp
    SELECT DISTINCT x.id FROM (
      SELECT e.id
      FROM embeddings v
      JOIN (SELECT e.id, e.sheet_id, e.content_hash AS h FROM entries e
            UNION ALL
            SELECT e.id, e.sheet_id, e.content_hash_vi FROM entries e WHERE e.content_hash_vi IS NOT NULL
           ) e ON e.h = v.content_hash
      WHERE v.model = p_model
        AND ((SELECT slug FROM target) IS NULL OR e.sheet_id = (SELECT sheet_id FROM target))
      ORDER BY v.embedding <=> p_embedding
      LIMIT 2 * GREATEST(p_limit * 5, 50)
    ) x
  ),
  kw AS (
    SELECT e.id FROM entries e
    WHERE e.search_tsv @@ (SELECT tsq FROM target)
      AND ((SELECT slug FROM target) IS NULL OR e.sheet_id = (SELECT sheet_id FROM target))
  ),
  scored AS (
    SELECT e.*,
           (SELECT max(1 - (v.embedding <=> p_embedding)) FROM embeddings v
            WHERE v.model = p_model AND v.content_hash IN (e.content_hash, e.content_hash_vi)) AS sim,
           (SELECT count(*) FROM unnest(tsvector_to_array(e.search_tsv)) l WHERE l = ANY (t.terms))::float8
             / NULLIF(cardinality(t.terms), 0) AS ratio,
           CASE WHEN e.sheet_id = ANY (t.boost_ids) THEN p_boost_weight ELSE 0 END AS bonus
    FROM (SELECT id FROM vec UNION SELECT id FROM kw) c
    JOIN entries e ON e.id = c.id
    CROSS JOIN target t
  )
  SELECT s.id, sh.slug, s.card, s.section, s.kind, s.command,
         s.description, s.description_vi, s.details, s.example, s.danger, s.lang,
         COALESCE(s.sim, 0) + p_kw_weight * COALESCE(s.ratio, 0) + s.bonus, s.sim, s.ratio
  FROM scored s JOIN sheets sh ON sh.id = s.sheet_id
  ORDER BY 13 DESC
  LIMIT p_limit
$$;
