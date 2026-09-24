"""Knowledge skills: persistent notes, safe calculator, date/time.

All stdlib, cross-platform. Notes live in the memory JSON store under
"notes": [{"id", "text", "tags", "created"}].
"""

import ast
import datetime as _dt
import json
import operator
import re

MAX_NOTES = 500


# -- Notes (long-term knowledge) --------------------------------------------

class NoteStore:
    """Tiny persistent knowledge base with keyword search."""

    def __init__(self, path):
        from pathlib import Path
        self.path = Path(path)

    def _load(self) -> list:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("notes", []) if isinstance(data, dict) else []
        except (json.JSONDecodeError, OSError):
            return []

    def all(self) -> list:
        return self._load()

    def _save(self, notes: list):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if self.path.exists():
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(existing, dict):
                    existing = {}
            except (json.JSONDecodeError, OSError):
                existing = {}
        existing["notes"] = notes[-MAX_NOTES:]
        self.path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def add(self, text: str, tags: str = "") -> str:
        text = " ".join(text.split()).strip()
        if not text:
            raise ValueError("Пустая заметка")
        notes = self._load()
        next_id = max((n["id"] for n in notes), default=0) + 1
        notes.append({
            "id": next_id,
            "text": text[:2000],
            "tags": " ".join(tags.split())[:200],
            "created": _dt.datetime.now().isoformat(timespec="seconds"),
        })
        self._save(notes)
        return f"Запомнил: {text[:100]}"

    def recall(self, query: str = "") -> str:
        notes = self._load()
        if not notes:
            return "Заметок пока нет."
        if query:
            words = query.lower().split()
            notes = [n for n in notes
                     if any(w in (n["text"] + " " + n["tags"]).lower()
                            for w in words)]
            if not notes:
                return "Ничего не нашлось по запросу."
        shown = notes[-10:]
        lines = [f"#{n['id']} [{n['tags']}] {n['text']}" if n["tags"]
                 else f"#{n['id']} {n['text']}" for n in shown]
        if len(notes) > len(shown):
            lines.append(f"...и ещё {len(notes) - len(shown)}")
        return "\n".join(lines)

    def forget(self, note_id) -> str:
        notes = self._load()
        try:
            note_id = int(note_id)
        except (TypeError, ValueError):
            raise ValueError("Укажите номер заметки, например: /forget 3")
        remaining = [n for n in notes if n["id"] != note_id]
        if len(remaining) == len(notes):
            return f"Заметка #{note_id} не найдена."
        self._save(remaining)
        return f"Забыл заметку #{note_id}."


# -- Calculator (safe, no eval) ----------------------------------------------

_CALC_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _calc_node(node):
    if isinstance(node, ast.Expression):
        return _calc_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _CALC_OPS:
        return _CALC_OPS[type(node.op)](_calc_node(node.left),
                                        _calc_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _CALC_OPS:
        return _CALC_OPS[type(node.op)](_calc_node(node.operand))
    raise ValueError("Разрешены только числа и + - * / // % ** ( )")


def calculate(expression: str) -> str:
    """Evaluate arithmetic safely via ast (no eval)."""
    expr = expression.strip().replace(",", ".")
    expr = re.sub(r"[хx×*](?=\s*\d)", "*", expr)  # "2 x 3" / "2 х 3"
    if not expr:
        raise ValueError("Пустое выражение")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Не удалось разобрать выражение: {expression!r}") from exc
    result = _calc_node(tree)
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return f"{expression.strip()} = {result}"


# -- Date / time --------------------------------------------------------------

def now() -> str:
    d = _dt.datetime.now()
    days = ["понедельник", "вторник", "среда", "четверг",
            "пятница", "суббота", "воскресенье"]
    months = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    return (f"Сейчас {d.strftime('%H:%M:%S')}, "
            f"{d.day} {months[d.month]} {d.year} года, {days[d.weekday()]}.")

# -- Legacy J.A.R.V.I.S-compatible utility skills ----------------------------

def wikipedia_search(query: str) -> str:
    """Search Wikipedia without requiring the wikipedia package."""
    import requests
    q = " ".join(str(query).split()).strip()
    if not q:
        raise ValueError("Укажите запрос для Wikipedia.")
    r = requests.get("https://ru.wikipedia.org/w/api.php", params={"action":"query","list":"search","srsearch":q,"format":"json","utf8":1,"srlimit":5}, timeout=15, headers={"User-Agent":"JARVIS/1.0"})
    r.raise_for_status()
    items = r.json().get("query", {}).get("search", [])
    if not items:
        return "В Wikipedia ничего не найдено."
    return "\n".join(f"{i+1}. {x['title']}" for i, x in enumerate(items))


def dictionary_lookup(word: str) -> str:
    import requests
    q = str(word).strip()
    if not q:
        raise ValueError("Укажите слово.")
    try:
        r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{q}", timeout=10)
        if r.ok:
            lines=[]
            for m in r.json()[0].get("meanings",[])[:3]:
                for d in m.get("definitions",[])[:2]:
                    lines.append(f"{m.get('partOfSpeech','')}: {d.get('definition','')}")
            if lines: return "\n".join(lines)
    except Exception: pass
    return f"Определение для «{q}» не найдено."


def news_search(query: str = "Украина") -> str:
    import urllib.parse
    q = str(query).strip() or "Украина"
    return "https://news.google.com/search?q=" + urllib.parse.quote(q)


def youtube_search(query: str) -> str:
    import urllib.parse
    q = str(query).strip()
    if not q: raise ValueError("Укажите, что искать на YouTube.")
    return "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q)


def youtube_download(url: str, output_dir: str = "") -> str:
    import shutil, subprocess
    from pathlib import Path
    target = Path(output_dir).expanduser() if output_dir else Path.home()/"Downloads"/"JARVIS"
    target.mkdir(parents=True, exist_ok=True)
    exe=shutil.which("yt-dlp")
    if not exe: raise RuntimeError("yt-dlp не установлен. Установите: pip install yt-dlp")
    u=str(url).strip()
    if not u.startswith(("http://","https://")): raise ValueError("Нужен полный URL видео.")
    p=subprocess.run([exe,"-P",str(target),"-o","%(title)s.%(ext)s",u],capture_output=True,text=True,timeout=600)
    if p.returncode: raise RuntimeError((p.stderr or p.stdout or "yt-dlp завершился с ошибкой")[-2000:])
    return f"Видео сохранено в: {target}"


def google_maps_search(location: str) -> str:
    import urllib.parse
    q=str(location).strip()
    if not q: raise ValueError("Укажите место.")
    return "https://www.google.com/maps/search/?api=1&query="+urllib.parse.quote_plus(q)


def open_website(url: str) -> str:
    import webbrowser
    u=str(url).strip()
    if not u.startswith(("http://","https://")): u="https://"+u
    webbrowser.open_new_tab(u)
    return f"Открываю: {u}"


def play_music(path: str) -> str:
    import os
    from pathlib import Path
    p=Path(path).expanduser()
    if not p.exists(): raise FileNotFoundError(f"Музыкальный файл не найден: {p}")
    if os.name=="nt": os.startfile(str(p))
    else:
        import subprocess; subprocess.Popen(["xdg-open",str(p)])
    return f"Открываю музыку: {p}"


def location_lookup() -> str:
    import requests
    r=requests.get("https://ipapi.co/json/",timeout=10); r.raise_for_status(); d=r.json()
    return f"Город: {d.get('city') or '—'}; страна: {d.get('country_name') or '—'}; широта: {d.get('latitude') or '—'}; долгота: {d.get('longitude') or '—'}; IP: {d.get('ip') or '—'}"


def face_recognition_check(image_path: str, reference_path: str = "") -> str:
    try: import cv2
    except ImportError as exc: raise RuntimeError("OpenCV не установлен; модуль лица необязателен.") from exc
    from pathlib import Path
    p=Path(image_path).expanduser()
    if not p.exists(): raise FileNotFoundError(str(p))
    img=cv2.imread(str(p))
    if img is None: raise ValueError("Не удалось прочитать изображение.")
    cascade=cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY); faces=cascade.detectMultiScale(gray,1.1,5)
    if not reference_path: return f"Найдено лиц: {len(faces)}"
    rp=Path(reference_path).expanduser(); ref=cv2.imread(str(rp))
    if ref is None: raise ValueError("Не удалось прочитать эталонное изображение.")
    rg=cv2.cvtColor(ref,cv2.COLOR_BGR2GRAY); refs=cascade.detectMultiScale(rg,1.1,5)
    return "Лицо обнаружено на обоих изображениях." if faces and refs else "Лицо на одном из изображений не найдено."


def todo_add(text: str, path: str = "") -> str:
    from pathlib import Path
    import json
    p=Path(path).expanduser() if path else Path.home()/"JARVIS"/"todo.json"; p.parent.mkdir(parents=True,exist_ok=True)
    data=json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    nid=max((int(x.get("id",0)) for x in data),default=0)+1
    data.append({"id":nid,"text":str(text).strip(),"done":False})
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    return f"Добавил задачу #{nid}: {text}"


def todo_list(path: str = "") -> str:
    from pathlib import Path
    import json
    p=Path(path).expanduser() if path else Path.home()/"JARVIS"/"todo.json"
    if not p.exists(): return "Список задач пуст."
    data=json.loads(p.read_text(encoding="utf-8")); pending=[x for x in data if not x.get("done")]
    return "\n".join(f"#{x['id']} □ {x['text']}" for x in pending) or "Активных задач нет."


def todo_done(task_id: int, path: str = "") -> str:
    from pathlib import Path
    import json
    p=Path(path).expanduser() if path else Path.home()/"JARVIS"/"todo.json"
    if not p.exists(): return f"Задача #{task_id} не найдена."
    data=json.loads(p.read_text(encoding="utf-8"))
    for x in data:
        if int(x.get("id",-1))==int(task_id):
            x["done"]=True; p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); return f"Задача #{task_id} выполнена."
    return f"Задача #{task_id} не найдена."
