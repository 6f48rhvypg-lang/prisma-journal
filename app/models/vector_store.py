import logging
import os
from datetime import datetime, timedelta
from functools import lru_cache

from config import Config
from database.db import save_embedding

log = logging.getLogger(__name__)

_client = None
_collection = None
_embedder = None


@lru_cache(maxsize=100)
def _cached_query_embedding(query_text):
    """Cache embeddings for repeated search queries.

    Args:
        query_text: The query text to embed (must be hashable/string)

    Returns:
        Tuple of floats (embedding vector) or None if embedding fails
    """
    result = _embed_texts([query_text])
    if result and result[0]:
        return tuple(result[0])
    return None


def _get_embedder():
    """Lazy-load and return the sentence-transformers model.

    Returns None if embeddings service is unavailable.
    """
    global _embedder
    if _embedder is None:
        from utils.services import status, init_sentence_transformer
        if not status.embeddings:
            log.warning("Embeddings unavailable: %s", status.embeddings_message)
            return None
        _embedder = init_sentence_transformer()
    return _embedder


def _embed_texts(texts):
    """Generate embeddings for the given texts.

    Returns a list of embedding vectors or None on failure.
    """
    model = _get_embedder()
    if model is None:
        return None
    try:
        vectors = model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()
    except Exception as e:
        log.warning("Failed to encode texts: %s", e)
        return None


def _get_collection():
    """Lazy-initialize and return the ChromaDB collection.

    Returns None if ChromaDB is not available, allowing the app to
    continue without semantic search.
    """
    global _client, _collection
    if _collection is None:
        from utils.services import status
        if not status.chromadb:
            log.warning("ChromaDB unavailable: %s", status.chromadb_message)
            return None
        try:
            import chromadb
            from chromadb.config import Settings
            os.makedirs(Config.CHROMA_PATH, exist_ok=True)
            _client = chromadb.PersistentClient(
                path=Config.CHROMA_PATH,
                settings=Settings(anonymized_telemetry=False),
            )
            _collection = _client.get_or_create_collection(
                name=Config.CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as e:
            log.error("Failed to initialise ChromaDB: %s", e)
            return None
    return _collection


def add_entry(entry_id, text, metadata=None):
    """Add or update a journal entry embedding.

    Args:
        entry_id: UUID string of the entry
        text: The entry content to embed
        metadata: Optional dict with date, emotions, word_count, tags, summary

    No-op if ChromaDB is down.
    """
    collection = _get_collection()
    if collection is None:
        return
    doc_id = f"entry_{entry_id}"
    meta = metadata or {}
    meta["entry_id"] = entry_id
    # Ensure metadata values are ChromaDB-compatible (str, int, float, bool)
    clean_meta = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            clean_meta[k] = v
        elif isinstance(v, list):
            # Store lists as comma-separated strings
            clean_meta[k] = ",".join(str(x) for x in v)
        else:
            clean_meta[k] = str(v)

    embeddings = _embed_texts([text])
    if embeddings:
        save_embedding(entry_id, embeddings[0], model_version=Config.EMBEDDING_MODEL)
        collection.upsert(
            ids=[doc_id],
            embeddings=embeddings,
            documents=[text],
            metadatas=[clean_meta],
        )
    else:
        collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[clean_meta],
        )


def search_similar(query, n_results=5):
    """Search for entries semantically similar to the query.

    Returns an empty list if ChromaDB is unavailable.
    """
    collection = _get_collection()
    if collection is None or collection.count() == 0:
        return []
    # Use cached embedding for queries
    cached_embedding = _cached_query_embedding(query)
    query_kwargs = {
        "n_results": min(n_results, collection.count()),
    }
    if cached_embedding:
        query_kwargs["query_embeddings"] = [list(cached_embedding)]
    else:
        query_kwargs["query_texts"] = [query]

    results = collection.query(**query_kwargs)
    entries = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            entries.append(
                {
                    "id": doc_id,
                    "entry_id": results["metadatas"][0][i].get("entry_id"),
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "distance": results["distances"][0][i] if results["distances"] else None,
                }
            )
    return entries


def search_semantic(query, n_results=10, include_scores=True):
    """Enhanced semantic search with similarity scores and metadata.

    Args:
        query: The search query text
        n_results: Maximum number of results to return
        include_scores: Whether to include similarity scores

    Returns:
        List of dicts with entry_id, distance, similarity_score, document, metadata
    """
    collection = _get_collection()
    if collection is None or collection.count() == 0:
        return []

    # Use cached embedding for queries
    cached_embedding = _cached_query_embedding(query)
    query_kwargs = {
        "n_results": min(n_results, collection.count()),
        "include": ["documents", "metadatas", "distances"],
    }
    if cached_embedding:
        query_kwargs["query_embeddings"] = [list(cached_embedding)]
    else:
        query_kwargs["query_texts"] = [query]

    results = collection.query(**query_kwargs)

    entries = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results["distances"] else 0
            # Convert cosine distance to similarity score (0-1, higher is better)
            # ChromaDB cosine distance is 0 for identical, 2 for opposite
            similarity = max(0, 1 - (distance / 2))

            entry_data = {
                "entry_id": results["metadatas"][0][i].get("entry_id"),
                "distance": distance,
                "similarity_score": round(similarity, 4),
                "document": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
            }
            entries.append(entry_data)

    return entries


def find_similar_entries(text, n_results=5, exclude_entry_ids=None, exclude_recent_days=0):
    """Find entries similar to the given text.

    Used for the "Past Memories" feature when writing a new entry.

    Args:
        text: The text to find similar entries for
        n_results: Maximum number of results
        exclude_entry_ids: List of entry IDs to exclude from results
        exclude_recent_days: Exclude entries from the last N days

    Returns:
        List of dicts with entry_id, similarity_score, document snippet, metadata
    """
    collection = _get_collection()
    if collection is None or collection.count() == 0:
        return []

    # Request more results to account for filtering
    fetch_count = min(n_results * 3, collection.count())
    if fetch_count == 0:
        return []

    # For shorter texts, use cached embedding; for longer content, compute directly
    if len(text) < 500:
        cached_embedding = _cached_query_embedding(text)
        query_embeddings = [list(cached_embedding)] if cached_embedding else None
    else:
        query_embeddings = _embed_texts([text])

    query_kwargs = {
        "n_results": fetch_count,
        "include": ["documents", "metadatas", "distances"],
    }
    if query_embeddings:
        query_kwargs["query_embeddings"] = query_embeddings
    else:
        query_kwargs["query_texts"] = [text]

    results = collection.query(**query_kwargs)

    exclude_ids = set(exclude_entry_ids or [])
    cutoff_date = None
    if exclude_recent_days > 0:
        cutoff_date = (datetime.now() - timedelta(days=exclude_recent_days)).isoformat()

    entries = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            entry_id = meta.get("entry_id")

            # Skip excluded entries
            if entry_id in exclude_ids:
                continue

            # Skip recent entries if cutoff specified
            if cutoff_date and meta.get("date"):
                entry_date = meta.get("date", "")
                if entry_date > cutoff_date:
                    continue

            distance = results["distances"][0][i] if results["distances"] else 0
            similarity = max(0, 1 - (distance / 2))

            # Skip very low similarity matches
            if similarity < 0.3:
                continue

            doc = results["documents"][0][i] if results["documents"] else ""
            # Create excerpt (first 200 chars)
            excerpt = doc[:200] + "..." if len(doc) > 200 else doc

            entries.append({
                "entry_id": entry_id,
                "similarity_score": round(similarity, 4),
                "excerpt": excerpt,
                "metadata": meta,
            })

            if len(entries) >= n_results:
                break

    return entries


def get_all_entry_embeddings():
    """Get all entry IDs, embeddings, and metadata from the collection.

    Used for analyzing journal patterns and generating personalized prompts.

    Returns:
        List of dicts with entry_id, embedding, document, metadata
    """
    collection = _get_collection()
    if collection is None or collection.count() == 0:
        return []

    # Get all entries (ChromaDB doesn't have a simple "get all" so we use a large limit)
    try:
        results = collection.get(
            include=["metadatas", "embeddings", "documents"],
            limit=10000,
        )
    except Exception as e:
        log.warning("Failed to get all embeddings: %s", e)
        return []

    entries = []
    if results and results["ids"]:
        for i, doc_id in enumerate(results["ids"]):
            meta = results["metadatas"][i] if results["metadatas"] else {}
            embedding = results["embeddings"][i] if results.get("embeddings") is not None else None
            document = results["documents"][i] if results.get("documents") is not None else ""
            entries.append({
                "entry_id": meta.get("entry_id"),
                "embedding": embedding,
                "document": document,
                "metadata": meta,
            })

    return entries


def get_collection_stats():
    """Get statistics about the vector store collection.

    Returns:
        Dict with count, or empty dict if unavailable
    """
    collection = _get_collection()
    if collection is None:
        return {}
    return {"count": collection.count()}


def delete_entry(entry_id):
    """Remove an entry from the vector store.  No-op if ChromaDB is down."""
    collection = _get_collection()
    if collection is None:
        return
    doc_id = f"entry_{entry_id}"
    try:
        collection.delete(ids=[doc_id])
    except Exception:
        pass
