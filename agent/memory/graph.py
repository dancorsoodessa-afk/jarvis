"""Knowledge Graph memory store for Jarvis.

Stores entities (nodes) and relations (edges / triples) in a persistent JSON
file. Supports querying entities and relations, finding connection paths (BFS),
generating Mermaid diagrams, and calculating graph statistics.
All stdlib, cross-platform, atomic persistence.
"""

from collections import deque
import datetime as _dt
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

MAX_ENTITIES = 2000
MAX_RELATIONS = 10000


def _slug(text: str) -> str:
    """Normalize identifier for lookup (case-insensitive, trimmed)."""
    return " ".join(text.strip().lower().split())


def _escape_mermaid_label(text: str) -> str:
    """Escape quotes and brackets for Mermaid labels."""
    return text.replace('"', "'").replace("[", "(").replace("]", ")")


class KnowledgeGraph:
    """Persistent Knowledge Graph with entity-relation storage and traversal."""

    def __init__(self, path: str | Path = "jarvis_kg.json"):
        self.path = Path(path)

    # -- Persistence ---------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"entities": {}, "relations": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"entities": {}, "relations": []}
            data.setdefault("entities", {})
            data.setdefault("relations", [])
            return data
        except (json.JSONDecodeError, OSError):
            return {"entities": {}, "relations": []}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Cap limits
        if len(data.get("relations", [])) > MAX_RELATIONS:
            data["relations"] = data["relations"][-MAX_RELATIONS:]

        fd, tmp = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=self.path.name + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False, indent=2))
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- Entity & Relation Manipulation ---------------------------------------

    def add_fact(
        self,
        source: str,
        relation: str = "",
        target: str = "",
        source_type: str = "",
        target_type: str = "",
    ) -> str:
        """Add a triple (source -> relation -> target) with optional entity types.
        Also accepts a single string in format 'source; relation; target'."""
        if not relation and not target and (";" in source or "—" in source or "->" in source):
            if ";" in source:
                parts = [p.strip() for p in source.split(";")]
            elif "->" in source:
                parts = [p.strip() for p in source.split("->")]
            elif "—" in source:
                parts = [p.strip() for p in source.split("—")]
            else:
                parts = []
            if len(parts) >= 3:
                source, relation, target = parts[0], parts[1], parts[2]

        source = " ".join(source.split()).strip()
        relation = " ".join(relation.split()).strip()
        target = " ".join(target.split()).strip()

        if not source or not relation or not target:
            raise ValueError("Субъект, отношение и объект не могут быть пустыми")

        data = self._load()
        entities = data["entities"]
        relations = data["relations"]

        now_iso = _dt.datetime.now().isoformat(timespec="seconds")
        src_slug = _slug(source)
        tgt_slug = _slug(target)

        # Update / register entities
        if src_slug not in entities:
            if len(entities) < MAX_ENTITIES:
                entities[src_slug] = {
                    "name": source,
                    "type": source_type.strip(),
                    "properties": {},
                    "created": now_iso,
                    "updated": now_iso,
                }
        else:
            if source_type.strip():
                entities[src_slug]["type"] = source_type.strip()
            entities[src_slug]["updated"] = now_iso

        if tgt_slug not in entities:
            if len(entities) < MAX_ENTITIES:
                entities[tgt_slug] = {
                    "name": target,
                    "type": target_type.strip(),
                    "properties": {},
                    "created": now_iso,
                    "updated": now_iso,
                }
        else:
            if target_type.strip():
                entities[tgt_slug]["type"] = target_type.strip()
            entities[tgt_slug]["updated"] = now_iso

        # Check for existing relation
        rel_slug = _slug(relation)
        exists = any(
            _slug(r["source"]) == src_slug
            and _slug(r["relation"]) == rel_slug
            and _slug(r["target"]) == tgt_slug
            for r in relations
        )

        if not exists:
            relations.append({
                "source": entities[src_slug]["name"] if src_slug in entities else source,
                "relation": relation,
                "target": entities[tgt_slug]["name"] if tgt_slug in entities else target,
                "created": now_iso,
            })
            self._save(data)
            return f"Запомнил факт: [{source}] —({relation})→ [{target}]"

        self._save(data)
        return f"Факт уже известен: [{source}] —({relation})→ [{target}]"

    def remove_fact(self, source: str, relation: str, target: str) -> str:
        """Remove a specific relation triple."""
        src_slug = _slug(source)
        rel_slug = _slug(relation)
        tgt_slug = _slug(target)

        data = self._load()
        orig_count = len(data["relations"])
        data["relations"] = [
            r for r in data["relations"]
            if not (
                _slug(r["source"]) == src_slug
                and _slug(r["relation"]) == rel_slug
                and _slug(r["target"]) == tgt_slug
            )
        ]

        if len(data["relations"]) < orig_count:
            self._save(data)
            return f"Удалена связь: [{source}] —({relation})→ [{target}]"
        return f"Связь [{source}] —({relation})→ [{target}] не найдена."

    def remove_entity(self, name: str) -> str:
        """Remove an entity and all its incident edges."""
        name_slug = _slug(name)
        data = self._load()

        found = name_slug in data["entities"]
        if found:
            disp_name = data["entities"][name_slug]["name"]
            del data["entities"][name_slug]
        else:
            disp_name = name

        orig_rel_count = len(data["relations"])
        data["relations"] = [
            r for r in data["relations"]
            if _slug(r["source"]) != name_slug and _slug(r["target"]) != name_slug
        ]
        removed_edges = orig_rel_count - len(data["relations"])

        if found or removed_edges > 0:
            self._save(data)
            return f"Сущность [{disp_name}] удалена из графа (удалено связей: {removed_edges})."
        return f"Сущность [{name}] не найдена в графе."

    def delete(self, target: str) -> str:
        """Convenient delete: accepts entity name or 'source; relation; target'."""
        target = target.strip()
        if not target:
            raise ValueError("Укажите сущность или факт для удаления")

        parts = [p.strip() for p in target.split(";")]
        if len(parts) == 3:
            return self.remove_fact(parts[0], parts[1], parts[2])

        # If contains '->' or '—'
        arrow_match = re.split(r"\s*[-—]+(?:\((.*?)\))?[-—]*>\s*", target)
        if len(arrow_match) == 3 and arrow_match[1]:
            return self.remove_fact(arrow_match[0], arrow_match[1], arrow_match[2])

        return self.remove_entity(target)

    # -- Query & Search -------------------------------------------------------

    def query(self, search_term: str = "") -> str:
        """Search entities and relations or summarize the graph."""
        data = self._load()
        entities = data["entities"]
        relations = data["relations"]

        if not entities and not relations:
            return "Граф знаний пока пуст. Добавьте факты командой /kg_add."

        search = _slug(search_term)
        if not search:
            return self.stats()

        # Find matching entities
        matched_slugs = set()
        for slug, ent in entities.items():
            if (
                search in slug
                or search in _slug(ent.get("type", ""))
                or any(search in _slug(str(v)) for v in ent.get("properties", {}).values())
            ):
                matched_slugs.add(slug)

        # Also find entities involved in matching relations
        for r in relations:
            s_slug = _slug(r["source"])
            t_slug = _slug(r["target"])
            rel_slug = _slug(r["relation"])
            if search in rel_slug or search in s_slug or search in t_slug:
                matched_slugs.add(s_slug)
                matched_slugs.add(t_slug)

        if not matched_slugs:
            return f"В графе знаний ничего не нашлось по запросу «{search_term}»."

        output_blocks = []
        for slug in sorted(matched_slugs):
            ent = entities.get(slug, {"name": slug, "type": ""})
            name = ent["name"]
            ent_type = f" [{ent['type']}]" if ent.get("type") else ""

            # Outgoing & incoming relations
            out_rels = [r for r in relations if _slug(r["source"]) == slug]
            in_rels = [r for r in relations if _slug(r["target"]) == slug]

            lines = [f"● {name}{ent_type}:"]
            for r in out_rels:
                lines.append(f"   → {r['relation']} → {r['target']}")
            for r in in_rels:
                lines.append(f"   ← {r['relation']} ← {r['source']}")

            if not out_rels and not in_rels:
                lines.append("   (нет прямых связей)")

            output_blocks.append("\n".join(lines))

        return "\n\n".join(output_blocks)

    # -- Graph Traversal / Path Finding ---------------------------------------

    def find_path(self, source: str, target: str, max_depth: int = 4) -> str:
        """Find the shortest path connecting two entities using BFS."""
        src_slug = _slug(source)
        tgt_slug = _slug(target)

        if not src_slug or not tgt_slug:
            raise ValueError("Укажите начальную и конечную сущность")

        if src_slug == tgt_slug:
            return f"[{source}] и [{target}] — это одна и та же сущность."

        data = self._load()
        relations = data["relations"]
        entities = data["entities"]

        # Adjacency list: node -> list of (neighbor, relation, direction)
        adj: dict[str, list[tuple[str, str, str]]] = {}
        for r in relations:
            u = _slug(r["source"])
            v = _slug(r["target"])
            rel = r["relation"]
            adj.setdefault(u, []).append((v, rel, "out"))
            adj.setdefault(v, []).append((u, rel, "in"))

        if src_slug not in adj:
            return f"Сущность [{source}] не связана с другими узлами графа."
        if tgt_slug not in adj:
            return f"Сущность [{target}] не связана с другими узлами графа."

        # BFS
        queue = deque([(src_slug, [(src_slug, "", "")])])
        visited = {src_slug}

        found_path: list[tuple[str, str, str]] | None = None
        while queue:
            curr, path = queue.popleft()
            if len(path) - 1 >= max_depth:
                continue

            for neighbor, rel, direction in adj.get(curr, []):
                if neighbor == tgt_slug:
                    found_path = path + [(neighbor, rel, direction)]
                    break
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [(neighbor, rel, direction)]))

            if found_path:
                break

        if not found_path:
            return f"Связь между [{source}] и [{target}] не найдена в пределах {max_depth} шагов."

        # Format path nicely
        parts = []
        def get_name(slug: str) -> str:
            return entities.get(slug, {}).get("name", slug)

        start_name = get_name(found_path[0][0])
        parts.append(f"[{start_name}]")

        for i in range(1, len(found_path)):
            node, rel, direction = found_path[i]
            node_name = get_name(node)
            if direction == "out":
                parts.append(f"—({rel})→ [{node_name}]")
            else:
                parts.append(f"←({rel})— [{node_name}]")

        return "Путь связей: " + " ".join(parts)

    # -- Visualization & Summary ----------------------------------------------

    def visualize(self, focus: str = "") -> str:
        """Generate a Mermaid flowchart diagram and summary."""
        data = self._load()
        entities = data["entities"]
        relations = data["relations"]

        if not relations and not entities:
            return "Граф знаний пуст. Нечего отображать."

        focus_slug = _slug(focus) if focus else ""
        if focus_slug:
            # Filter to 1-hop subgraph around focus
            relevant_slugs = {focus_slug}
            for r in relations:
                s = _slug(r["source"])
                t = _slug(r["target"])
                if s == focus_slug:
                    relevant_slugs.add(t)
                elif t == focus_slug:
                    relevant_slugs.add(s)

            filtered_relations = [
                r for r in relations
                if _slug(r["source"]) in relevant_slugs and _slug(r["target"]) in relevant_slugs
            ]
        else:
            relevant_slugs = set(entities.keys())
            filtered_relations = relations[:60]  # Cap diagram size for readability

        # Node index map
        node_ids: dict[str, str] = {}
        idx = 1
        for slug in relevant_slugs:
            node_ids[slug] = f"N{idx}"
            idx += 1

        mermaid_lines = ["graph TD"]
        # Declare nodes with labels
        for slug, node_id in node_ids.items():
            ent = entities.get(slug, {})
            name = _escape_mermaid_label(ent.get("name", slug))
            ent_type = ent.get("type", "")
            if ent_type:
                label = f"{name} ({ent_type})"
            else:
                label = name
            mermaid_lines.append(f'  {node_id}["{label}"]')

        # Declare edges
        for r in filtered_relations:
            s_slug = _slug(r["source"])
            t_slug = _slug(r["target"])
            s_id = node_ids.get(s_slug)
            t_id = node_ids.get(t_slug)
            if s_id and t_id:
                rel = _escape_mermaid_label(r["relation"])
                mermaid_lines.append(f'  {s_id} -->|"{rel}"| {t_id}')

        chart = "```mermaid\n" + "\n".join(mermaid_lines) + "\n```"
        stats_line = (
            f"Узлов: {len(entities)}, связей: {len(relations)}"
            + (f" (показан подграф для «{focus}»)" if focus else "")
        )
        return f"{stats_line}\n\n{chart}"

    def stats(self) -> str:
        """Return statistics and top connected nodes in the graph."""
        data = self._load()
        entities = data["entities"]
        relations = data["relations"]

        if not entities and not relations:
            return "Граф знаний пока пуст."

        # Count degrees
        degrees: dict[str, int] = {}
        for r in relations:
            s = _slug(r["source"])
            t = _slug(r["target"])
            degrees[s] = degrees.get(s, 0) + 1
            degrees[t] = degrees.get(t, 0) + 1

        top_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:5]
        top_str = ", ".join(
            f"{entities.get(s, {}).get('name', s)} ({deg})"
            for s, deg in top_nodes
        ) or "—"

        lines = [
            f"📊 Граф знаний Jarvis:",
            f"• Сущностей: {len(entities)}",
            f"• Связей (фактов): {len(relations)}",
            f"• Ключевые узлы: {top_str}",
        ]
        if relations:
            recent = relations[-3:]
            lines.append("• Последние факты:")
            for r in reversed(recent):
                lines.append(f"   - [{r['source']}] —({r['relation']})→ [{r['target']}]")

        return "\n".join(lines)
