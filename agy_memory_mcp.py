#!/usr/bin/env python3
"""
AGY Memory Engine - MCP Server Layer (FastMCP)
Allows AGY to explicitly query, store, link entities, and manage multi-layer memories (Facts, Episodes, Learnings).
"""

import json
from mcp.server.fastmcp import FastMCP

from schema import db_session

mcp = FastMCP("memory")


@mcp.tool()
def search_memory(query: str, limit: int = 5) -> str:
    """Search personal persistent memories, facts, narrative chronicles, learnings, and linked relations by keyword.
    
    Args:
        query: Search terms or keywords to query the memory store.
        limit: Maximum number of results to return per category (default: 5).
    """
    words = [w for w in query.split() if len(w) > 2]
    if not words:
        return json.dumps([], ensure_ascii=False)
    fts_query = " OR ".join(words)
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            
            # Facts via JOIN (ranked by relevance)
            cursor.execute("""
                SELECT m.id, m.category, m.fact 
                FROM memories m
                JOIN memories_fts f ON m.id = f.id
                WHERE memories_fts MATCH ?
                ORDER BY f.rank
                LIMIT ?
            """, (fts_query, limit))
            facts = [{"type": "fact", "id": r[0], "category": r[1], "content": r[2]} for r in cursor.fetchall()]

            # Episodes via JOIN (ranked with status weighting: active > cooling > historic/resolved)
            cursor.execute("""
                SELECT e.id, e.topic, e.title, e.period, e.status, e.narrative, e.stance
                FROM episodes e
                JOIN episodes_fts f ON e.id = f.id
                WHERE episodes_fts MATCH ?
                ORDER BY 
                    CASE e.status 
                        WHEN 'active' THEN 1 
                        WHEN 'cooling' THEN 2 
                        ELSE 3 
                    END ASC,
                    f.rank ASC
                LIMIT ?
            """, (fts_query, limit))
            episodes = [{
                "type": "episode",
                "id": r[0],
                "topic": r[1],
                "title": r[2],
                "period": r[3],
                "status": r[4],
                "narrative": r[5],
                "stance": r[6]
            } for r in cursor.fetchall()]

            # Learnings via JOIN (ranked by relevance)
            cursor.execute("""
                SELECT l.id, l.category, l.insight, l.context
                FROM learnings l
                JOIN learnings_fts f ON l.id = f.id
                WHERE learnings_fts MATCH ?
                ORDER BY f.rank
                LIMIT ?
            """, (fts_query, limit))
            learnings = [{
                "type": "learning",
                "id": r[0],
                "category": r[1],
                "insight": r[2],
                "context": r[3]
            } for r in cursor.fetchall()]

            # Entity links
            cursor.execute("""
                SELECT l.source_id, l.target_id, l.relation
                FROM entity_links l
                JOIN entity_links_fts f ON l.source_id = f.source_id AND l.target_id = f.target_id AND l.relation = f.relation
                WHERE entity_links_fts MATCH ?
                LIMIT ?
            """, (fts_query, limit))
            entity_links = [{"source": r[0], "target": r[1], "relation": r[2]} for r in cursor.fetchall()]

            return json.dumps({
                "facts": facts,
                "episodes": episodes,
                "learnings": learnings,
                "entity_links": entity_links
            }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@mcp.tool()
def store_memory(id: str, fact: str, category: str = "general", keywords: str = "") -> str:
    """Store or update an atomic persistent fact or configuration parameter.
    
    Args:
        id: Unique identifier / key for this memory (e.g. 'infra.server.ip').
        fact: Fact content or description.
        category: Category classification (default: general).
        keywords: Optional search keywords or synonyms.
    """
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memories (id, category, fact, keywords, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    category = excluded.category,
                    fact = excluded.fact,
                    keywords = excluded.keywords,
                    updated_at = CURRENT_TIMESTAMP;
            """, (id, category, fact, keywords))
            conn.commit()
        return f"Successfully stored fact '{id}'"
    except Exception as e:
        return f"Error storing memory: {e}"

@mcp.tool()
def record_episode(id: str, topic: str, title: str, narrative: str, period: str = "", status: str = "active", entities: str = "", stance: str = "", keywords: str = "") -> str:
    """Record or update a narrative chronicle, background story, relationship context, or ongoing topic dossier.
    
    Args:
        id: Unique identifier (e.g. 'stweg.hoehenweg15.nachbarschaft', 'health.abbie.epilepsie').
        topic: Topic domain (e.g. 'stweg', 'health', 'travel', 'finance', 'dev').
        title: Human-readable title of this chronicle.
        narrative: Rich multi-sentence narrative summary of history, events, and background context.
        period: Time period (e.g. '2020 - laufend', 'Sommer 2024').
        status: Current status ('active', 'cooling', 'historic', 'resolved').
        entities: Involved people, organizations, or places.
        stance: User's stance, attitude, sentiments, or approach to this subject.
        keywords: Multilingual search terms and synonyms.
    """
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO episodes (id, topic, title, period, status, narrative, entities, stance, keywords, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    topic = excluded.topic,
                    title = excluded.title,
                    period = excluded.period,
                    status = excluded.status,
                    narrative = excluded.narrative,
                    entities = excluded.entities,
                    stance = excluded.stance,
                    keywords = excluded.keywords,
                    updated_at = CURRENT_TIMESTAMP;
            """, (id, topic, title, period, status, narrative, entities, stance, keywords))
            conn.commit()
        return f"Successfully recorded narrative episode '{id}'"
    except Exception as e:
        return f"Error recording episode: {e}"

@mcp.tool()
def record_learning(id: str, category: str, insight: str, context: str = "", keywords: str = "") -> str:
    """Record a practical learning, rule of thumb, heuristic, or tested opinion.
    
    Args:
        id: Unique key (e.g. 'travel.fewo_dog', 'coding.fastapi_patterns').
        category: Category (e.g. 'travel', 'health', 'dev', 'finance').
        insight: The lesson learned or heuristic.
        context: Context of how/when this was learned.
        keywords: Search terms and synonyms.
    """
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO learnings (id, category, insight, context, keywords, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    category = excluded.category,
                    insight = excluded.insight,
                    context = excluded.context,
                    keywords = excluded.keywords,
                    updated_at = CURRENT_TIMESTAMP;
            """, (id, category, insight, context, keywords))
            conn.commit()
        return f"Successfully recorded learning '{id}'"
    except Exception as e:
        return f"Error recording learning: {e}"

@mcp.tool()
def link_entities_mcp(source_id: str, target_id: str, relation: str) -> str:
    """Link two memory entities with a semantic relationship (e.g. 'infra.beelink' hosts 'service.immich').
    
    Args:
        source_id: Source ID (e.g. 'infra.beelink').
        target_id: Target ID (e.g. 'service.immich').
        relation: Relationship description (e.g. 'hosts', 'member_of', 'depends_on', 'owns').
    """
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO entity_links (source_id, target_id, relation)
                VALUES (?, ?, ?)
                ON CONFLICT(source_id, target_id, relation) DO NOTHING;
            """, (source_id.strip(), target_id.strip(), relation.strip()))
            conn.commit()
        return f"Successfully linked '{source_id}' --[{relation}]--> '{target_id}'"
    except Exception as e:
        return f"Error linking entities: {e}"

@mcp.tool()
def list_memories() -> str:
    """List all stored semantic facts, narrative chronicles, learnings, and entity links."""
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, category, fact FROM memories ORDER BY category, id")
            facts = [{"id": r[0], "category": r[1], "fact": r[2]} for r in cursor.fetchall()]
            
            cursor.execute("SELECT id, topic, title, period, status, narrative, stance FROM episodes ORDER BY topic, id")
            episodes = [{
                "id": r[0],
                "topic": r[1],
                "title": r[2],
                "period": r[3],
                "status": r[4],
                "narrative": r[5],
                "stance": r[6]
            } for r in cursor.fetchall()]

            cursor.execute("SELECT id, category, insight, context FROM learnings ORDER BY category, id")
            learnings = [{"id": r[0], "category": r[1], "insight": r[2], "context": r[3]} for r in cursor.fetchall()]

            cursor.execute("SELECT source_id, target_id, relation FROM entity_links ORDER BY source_id, target_id")
            links = [{"source": r[0], "target": r[1], "relation": r[2]} for r in cursor.fetchall()]

            return json.dumps({
                "facts": facts,
                "episodes": episodes,
                "learnings": learnings,
                "entity_links": links
            }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
