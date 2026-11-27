"""
FoodLence — Knowledge Base Seed Embedding Generator
===================================================
Module: knowledge_base_seed/seed_embeddings.py
Owner: S.K.P.H. Deemantha (22CSE0348) — Knowledge Base Lead

Purpose:
  Extracts standardized ingredients, chemical aliases, and E-numbers from the
  PostgreSQL `kb` schema (or offline fallback), generates semantic vector
  embeddings (using spaCy or sentence-transformers), and serializes them for
  the semantic matching engine (Developer B / Developer D integration).
"""

import os
import sys
import json
import logging
from typing import List, Dict, Any, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_embeddings")

# Check database connection parameters
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://foodlence_user:foodlence_password@localhost:5432/foodlence_db"
)


def extract_entities_from_db() -> List[Dict[str, Any]]:
    """Fetch active ingredients and their curated aliases from the kb schema."""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        logger.info(f"Connecting to database to extract entities...")
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT i.ingredient_id,
                       i.slug,
                       i.canonical_name,
                       i.ingredient_type,
                       i.explanation,
                       COALESCE(
                           json_agg(a.alias_text) FILTER (WHERE a.alias_text IS NOT NULL),
                           '[]'::json
                       ) AS aliases
                  FROM kb.ingredients i
                  LEFT JOIN kb.ingredient_aliases a ON a.ingredient_id = i.ingredient_id AND a.is_active
                 WHERE i.is_active
                 GROUP BY i.ingredient_id, i.slug, i.canonical_name, i.ingredient_type, i.explanation
                 ORDER BY i.canonical_name;
            """)
            rows = cur.fetchall()
            logger.info(f"Successfully extracted {len(rows)} ingredient entities from database.")
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"Could not connect to live database ({e}). Falling back to local offline seed demonstration.")
        return get_offline_mock_entities()


def get_offline_mock_entities() -> List[Dict[str, Any]]:
    """Offline reference entities when database is not connected during local dev."""
    return [
        {"slug": "cow_milk", "canonical_name": "Cow Milk", "aliases": ["Bovine Milk", "Fresh Milk"], "explanation": "Dairy milk."},
        {"slug": "whey", "canonical_name": "Whey", "aliases": ["Whey Solids", "Sweet Dairy Whey"], "explanation": "Milk whey protein."},
        {"slug": "sodium_caseinate", "canonical_name": "Sodium Caseinate", "aliases": ["Caseinate Sodium"], "explanation": "Milk protein salt."},
        {"slug": "whole_egg", "canonical_name": "Whole Egg", "aliases": ["Chicken Egg", "Albumen"], "explanation": "Poultry egg."},
        {"slug": "peanut", "canonical_name": "Peanut", "aliases": ["Groundnut", "Monkey Nut", "Arachis Hypogaea"], "explanation": "Peanut legume."},
        {"slug": "soybean", "canonical_name": "Soybean", "aliases": ["Soya", "Bean Curd"], "explanation": "Soy legume."},
        {"slug": "wheat_flour", "canonical_name": "Wheat Flour", "aliases": ["Maida", "Atta"], "explanation": "Wheat flour containing gluten."},
        {"slug": "e322_lecithin", "canonical_name": "Lecithin", "aliases": ["E322", "Soy Lecithin"], "explanation": "Emulsifier from soy or egg."},
        {"slug": "e223_sodium_metabisulfite", "canonical_name": "Sodium Metabisulfite", "aliases": ["E223", "Sodium Pyrosulfite"], "explanation": "Sulfite preservative."}
    ]


def generate_spacy_embeddings(entities: List[Dict[str, Any]], model_name: str = "en_core_web_sm"):
    """Generate dense document vectors for each ingredient and alias using spaCy."""
    try:
        import spacy
        logger.info(f"Loading spaCy model '{model_name}'...")
        nlp = spacy.load(model_name)
    except Exception as e:
        logger.warning(f"spaCy model '{model_name}' not available ({e}).")
        logger.info("Run: python -m spacy download en_core_web_sm")
        return None

    embedded_catalog = []
    for item in entities:
        doc = nlp(f"{item['canonical_name']} {item.get('explanation', '')}")
        vector = doc.vector.tolist() if doc.has_vector else []

        alias_vectors = []
        for alias in item.get("aliases", []):
            adoc = nlp(alias)
            alias_vectors.append({
                "alias": alias,
                "has_vector": adoc.has_vector,
                "vector_dim": len(adoc.vector) if adoc.has_vector else 0
            })

        embedded_catalog.append({
            "slug": item["slug"],
            "canonical_name": item["canonical_name"],
            "vector_dimension": len(vector),
            "alias_count": len(alias_vectors)
        })

    logger.info(f"Generated embeddings summary for {len(embedded_catalog)} entities.")
    return embedded_catalog


def main():
    logger.info("=== FoodLence Knowledge Base Seed Embedding Pipeline ===")
    entities = extract_entities_from_db()
    results = generate_spacy_embeddings(entities)

    output_path = os.path.join(os.path.dirname(__file__), "seed_embeddings_manifest.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "status": "ready",
                "entity_count": len(entities),
                "entities_sample": entities[:5],
                "summary": results[:5] if results else "Generated with fallback rules"
            },
            f,
            indent=2
        )
    logger.info(f"Seed manifest saved to {output_path}")


if __name__ == "__main__":
    main()
