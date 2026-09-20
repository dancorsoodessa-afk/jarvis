"""Persistent task tracker for multi-step JARVIS work."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

class TaskStore:
    def __init__(self, path: str):
        self.path = Path(path)
    def _load(self):
        try:
            data=json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data,list) else []
        except Exception:
            return []
    def _save(self,data):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.path.write_text(json.dumps(data[-100:],ensure_ascii=False,indent=2),encoding="utf-8")
    def add(self,title:str)->str:
        data=self._load(); tid=f"T{len(data)+1:05d}"
        item={"id":tid,"title":title,"status":"active","steps":[],"created":datetime.now(timezone.utc).isoformat()}
        data.append(item); self._save(data); return f"Задача {tid} создана: {title}"
    def list(self)->str:
        data=[x for x in self._load() if x.get("status")=="active"]
        if not data: return "Активных задач нет."
        return "\n".join(f"{x['id']} — {x['title']} ({len(x.get('steps',[]))} шагов)" for x in data)
    def update(self,task_id:str,status:str,step:str="")->str:
        data=self._load()
        for x in data:
            if x.get("id")==task_id:
                if step: x.setdefault("steps",[]).append({"text":step,"time":datetime.now(timezone.utc).isoformat()})
                if status in ("active","done","failed","cancelled"): x["status"]=status
                self._save(data); return f"{task_id}: {x['status']}"
        return f"Задача {task_id} не найдена."
