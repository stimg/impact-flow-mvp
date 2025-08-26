def get_recommendation(self, user_message, tags):
    """Queries the PostgreSQL Q&A database for the given tag(s)"""

    if not user_message:
        return {"User message is not defined"}

    # print(f"--------> User message: {user_message}")
    vec_query = self.generate_embedding(user_message)

    # Get recommendation
    sql = """
        SET hnsw.ef_search = 40;
        
        WITH
        q AS (
          SELECT
            %s::vector AS qvec,
            websearch_to_tsquery('german', %s) AS qtext,
            normalize_csv(%s) AS qtags
        ),
        
        -- 1) Exact tag short-circuit
        exact_tag AS (
          SELECT p.id, 1.0 AS score
          FROM product_recommendations p, q
          WHERE p.tags_arr && q.qtags
        ),
        has_exact AS (
          SELECT EXISTS(SELECT 1 FROM exact_tag) AS found
        ),
        
        -- 2) Score all rows
        scored_all AS (
          SELECT
            p.id,
            COALESCE(1 - (p.vec_info <=> (SELECT qvec FROM q)), 0) AS s_info_dense,
            ts_rank_cd(p.info_tsv, (SELECT qtext FROM q))           AS s_info_bm25,
            (
              SELECT MAX(similarity(t, qt))
              FROM unnest(p.tags_arr) t
              CROSS JOIN LATERAL unnest((SELECT qtags FROM q)) qt
            )                                                       AS s_tags_trgm
          FROM product_recommendations p
        ),
        
        -- 3) Normalize (NULL-safe for channels that might be missing)
        norm AS (
          SELECT
            id,
            COALESCE(
              (s_info_dense - MIN(s_info_dense) OVER())
              / NULLIF(MAX(s_info_dense) OVER() - MIN(s_info_dense) OVER(), 0), 0
            ) AS n_info_dense,
            COALESCE(
              (s_info_bm25 - MIN(s_info_bm25) OVER())
              / NULLIF(MAX(s_info_bm25) OVER() - MIN(s_info_bm25) OVER(), 0), 0
            ) AS n_info_bm25,
            COALESCE(
              (s_tags_trgm - MIN(s_tags_trgm) OVER())
              / NULLIF(MAX(s_tags_trgm) OVER() - MIN(s_tags_trgm) OVER(), 0), 0
            ) AS n_tags_trgm
          FROM scored_all
        ),
        
        -- 4) Weighted hybrid
        hybrid AS (
          SELECT id, 0.5*n_info_dense + 0.35*n_info_bm25 + 0.15*n_tags_trgm AS score
          FROM norm
        ),
        
        -- 5) Final selection
        final_ids AS (
          SELECT id, score FROM exact_tag
          UNION ALL
          SELECT h.id, h.score
          FROM hybrid h, has_exact hx
          WHERE NOT hx.found
            AND h.score >= 0.9
        )
        SELECT p.id, p.tags, p.recommended, p.suitable, p.info, f.score
        FROM final_ids f
        JOIN product_recommendations p ON p.id = f.id
        WHERE f.score > 0.8
        ORDER BY f.score DESC
        LIMIT 1;
    """
    result = self.query_db(sql, (vec_query, user_message, tags))

    # Get product links for recommended products
    sql = """
        SELECT jsonb_object_agg(
            regexp_replace(pc.vmetadata ->> 'name', '^\\s*Produktname:\\s*', ''),
            regexp_replace(pc.chunk_text, '^\\s*Produkwebseite:\\s*', '')
        ) AS links
        FROM product_chunks pc
        WHERE pc.section = 'reference_link'
            AND EXISTS (SELECT 1
                FROM unnest(normalize_csv(%s)) AS pat
                WHERE lower(regexp_replace(pc.vmetadata ->> 'name', '^\s*Produktname:\s*', '')) ILIKE pat || '%%') \
    """

    if not result:
        return None

    res = self.query_db(sql, (f"{result['recommended']}, {result['suitable']}",))
    links = res["links"] if res else None

    # print(f"-----> Links: {links}")
    # print(f"-----> Result: {result}")

    return {**result, "links": links}

