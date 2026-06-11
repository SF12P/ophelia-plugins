"""
plugins/conversation_insights.py — Ophelia Conversation Insights
=================================================================
Generates summaries and stats about your conversation history
with Ophelia using actual stored memories.

Commands:
  conversation insights      — full monthly summary
  what have we talked about  — same
  memory summary             — same
  how long have we talked    — relationship stats
  what do you know about me  — Ophelia summarizes what she knows
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

NAME        = "conversation_insights"
VERSION     = "1.0"
DESCRIPTION = "Generates summaries and stats about your conversation history with Ophelia."
MANUAL_ONLY = False
AUTHOR      = "SF12P"
TAGS        = ["utility", "memory", "insights"]
REQUIRES    = []

TRIGGERS = [
    "conversation insights", "what have we talked about",
    "memory summary", "how long have we talked",
    "what do you know about me", "our conversation history",
    "what do you remember about me", "talking stats",
    "how long have we known each other",
]

COMMANDS = {
    "conversation insights":     "Full summary of recent conversation topics",
    "what have we talked about": "Summary of recent topics",
    "what do you know about me": "Ophelia summarizes her memories about you",
    "how long have we talked":   "Relationship stats — time, message count",
}


def _get_memory_dir(context: dict) -> Path:
    return Path(context.get("memory_dir", "trm_memory"))


_memory_cache = {"data": [], "time": 0}

def _load_all_memories(mem_dir: Path) -> list:
    """Load memories from ChromaDB — cached for 60 seconds to avoid slow repeated queries."""
    import time
    now = time.time()
    if _memory_cache["data"] and now - _memory_cache["time"] < 60:
        return _memory_cache["data"]
    try:
        import sys
        sys.path.insert(0, str(mem_dir.parent))
        from memory.store import MemoryStore
        from utils.config import Config
        store = MemoryStore(Config())
        results = store.search("user life interests preferences", top_k=30)
        _memory_cache["data"] = results
        _memory_cache["time"] = now
        return results
    except Exception:
        return []


def _load_chat_history(mem_dir: Path) -> list:
    """Load all chat JSON files."""
    chats_dir = mem_dir / "chats"
    all_messages = []
    if not chats_dir.exists():
        return []
    for f in chats_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("is_private") or data.get("is_roleplay"):
                continue
            for msg in data.get("messages", []):
                msg["chat_name"] = data.get("name", f.stem)
                msg["chat_id"]   = f.stem
                all_messages.append(msg)
        except Exception:
            continue
    return all_messages


def _count_stats(messages: list) -> dict:
    """Count basic conversation stats."""
    user_msgs     = [m for m in messages if m.get("role") == "user"]
    ai_msgs       = [m for m in messages if m.get("role") in ("assistant","ai","ophelia")]
    total_words   = sum(len(m.get("content", m.get("text","")).split())
                        for m in messages)

    # Find oldest message timestamp
    oldest = None
    for m in messages:
        ts = m.get("timestamp","")
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                if oldest is None or dt < oldest:
                    oldest = dt
            except Exception:
                pass

    days_known = 0
    if oldest:
        days_known = (datetime.now() - oldest).days

    return {
        "total_messages": len(messages),
        "user_messages":  len(user_msgs),
        "ai_messages":    len(ai_msgs),
        "total_words":    total_words,
        "days_known":     days_known,
        "oldest":         oldest,
    }


def _extract_topics(memories: list) -> list:
    """Extract rough topic keywords from memories."""
    import re
    stop_words = {"the","a","an","is","was","are","were","have","has","had",
                  "i","you","he","she","they","we","it","this","that","and",
                  "or","but","in","on","at","to","for","of","with","about",
                  "user","ophelia","said","told","mentioned","asked","chat"}
    word_counts = Counter()
    for m in memories:
        text = m.get("text","").lower()
        words = re.findall(r'\b[a-z]{4,}\b', text)
        for w in words:
            if w not in stop_words:
                word_counts[w] += 1
    return [w for w, _ in word_counts.most_common(12)]


def _recent_chats(mem_dir: Path, days: int = 30) -> list:
    """Get chat names active in the last N days."""
    chats_dir = mem_dir / "chats"
    recent = []
    cutoff = datetime.now() - timedelta(days=days)
    if not chats_dir.exists():
        return []
    for f in sorted(chats_dir.glob("*.json"),
                    key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("is_private") or data.get("is_roleplay"):
                continue
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime >= cutoff:
                recent.append(data.get("name", f.stem))
        except Exception:
            continue
    return recent[:5]


def run(query: str, context: dict) -> str:
    text    = context["user_input"].lower()
    mem_dir = _get_memory_dir(context)

    # ── Relationship stats ────────────────────────────────────────────
    if any(k in text for k in ["how long", "known each other", "talking stats"]):
        messages = _load_chat_history(mem_dir)
        stats    = _count_stats(messages)
        days     = stats["days_known"]

        if days == 0 and stats["total_messages"] == 0:
            return "We haven't talked much yet — but we're getting started."

        if days >= 365:
            time_str = f"{days // 365} year(s) and {(days % 365)} days"
        elif days >= 30:
            time_str = f"{days // 30} month(s)"
        elif days > 1:
            time_str = f"{days} days"
        else:
            time_str = "just getting started"

        return (
            f"We've been talking for {time_str}.\n"
            f"Total messages: {stats['total_messages']} "
            f"({stats['user_messages']} from you, {stats['ai_messages']} from me)\n"
            f"Total words exchanged: {stats['total_words']:,}"
        )

    # ── What do I know about you ──────────────────────────────────────
    if any(k in text for k in ["what do you know", "what do you remember",
                                "know about me", "remember about me"]):
        memories = _load_all_memories(mem_dir)
        if not memories:
            return ("I don't have many specific memories about you yet. "
                    "The more we talk the more I'll remember.")

        # Use LLM to summarize memories naturally
        mem_texts = "\n".join(f"- {m.get('text','')[:150]}"
                               for m in memories[:20])
        user_name = context.get("shared_state",{}).get("user_name","") or "you"

        try:
            import requests
            from utils.config import Config
            model = Config().llm_model
            prompt = (
                f"Based on these memory notes about {user_name}, "
                f"write a natural 3-4 sentence summary of what you know about them. "
                f"Write in first person as Ophelia. Be specific, not generic.\n\n"
                f"Memories:\n{mem_texts}"
            )
            r = requests.post("http://localhost:11434/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=30)
            return r.json().get("response","").strip() or \
                   f"I have {len(memories)} memories about you stored."
        except Exception:
            topics = _extract_topics(memories)
            return (f"I have {len(memories)} memories stored about you. "
                    f"Topics that come up: {', '.join(topics[:8])}.")

    # ── Full conversation insights ────────────────────────────────────
    messages = _load_chat_history(mem_dir)
    memories = _load_all_memories(mem_dir)
    stats    = _count_stats(messages)
    topics   = _extract_topics(memories)
    recent   = _recent_chats(mem_dir, days=30)

    if stats["total_messages"] == 0:
        return ("We haven't had many conversations yet. "
                "Start chatting and I'll build up a picture of what we talk about.")

    days = stats["days_known"]
    if days >= 30:
        time_str = f"{days // 30} month(s)"
    elif days > 1:
        time_str = f"{days} days"
    else:
        time_str = "less than a day"

    lines = [f"We've been talking for {time_str} — "
             f"{stats['total_messages']} messages total."]

    if topics:
        lines.append(f"Topics that come up most: {', '.join(topics[:8])}.")

    if recent:
        lines.append(f"Recent active chats: {', '.join(recent)}.")

    if memories:
        lines.append(f"I have {len(memories)} memories stored about you and our conversations.")

    return "\n".join(lines)
