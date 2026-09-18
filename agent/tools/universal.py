"""Universal Windows/file tools for JARVIS."""
from __future__ import annotations
import json, os, platform, shutil, subprocess, sys, tarfile, zipfile, tempfile
from pathlib import Path

MAX_TEXT = 120_000
MAX_FILES = 500

TEXT_EXTS = {".txt",".md",".log",".csv",".json",".xml",".yaml",".yml",".toml",".ini",".cfg",".py",".ps1",".bat",".cmd",".js",".ts",".tsx",".jsx",".html",".css",".sql",".dart",".java",".kt",".c",".cpp",".h",".hpp",".rs",".go",".sh"}
ARCHIVE_EXTS = {".zip",".tar",".gz",".tgz",".bz2",".xz",".7z",".rar"}

def _path(value: str) -> Path:
    p = Path(str(value).strip().strip('"')).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()

def read_text(path: str) -> str:
    p = _path(path)
    if not p.is_file(): raise ValueError(f"Файл не найден: {p}")
    try: data = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e: raise RuntimeError(f"Не удалось прочитать файл: {e}") from e
    return data[:MAX_TEXT]

def inspect_file(path: str) -> str:
    p = _path(path)
    if not p.exists(): raise ValueError(f"Путь не найден: {p}")
    if p.is_dir():
        items=[]
        for x in list(p.iterdir())[:MAX_FILES]:
            items.append(("DIR " if x.is_dir() else "FILE")+f" {x.name}")
        return f"Папка: {p}\n" + "\n".join(items)
    suffix=p.suffix.lower()
    if suffix in TEXT_EXTS:
        return f"Файл: {p}\nРазмер: {p.stat().st_size} байт\n\n{read_text(str(p))}"
    if suffix==".pdf":
        try:
            from pypdf import PdfReader
            reader=PdfReader(str(p))
            parts=[]
            for page in reader.pages[:50]:
                parts.append(page.extract_text() or "")
            return f"PDF: {p}\nСтраниц: {len(reader.pages)}\n\n" + "\n".join(parts)[:MAX_TEXT]
        except ImportError:
            return "Для чтения PDF установите pypdf."
    if suffix==".docx":
        try:
            from docx import Document
            doc=Document(str(p))
            return f"DOCX: {p}\n\n" + "\n".join(x.text for x in doc.paragraphs)[:MAX_TEXT]
        except ImportError:
            return "Для чтения DOCX установите python-docx."
    if suffix in {".xlsx",".xlsm"}:
        try:
            from openpyxl import load_workbook
            wb=load_workbook(str(p), read_only=True, data_only=True)
            out=[]
            for ws in wb.worksheets:
                out.append(f"[Лист: {ws.title}]")
                for row in ws.iter_rows(max_row=100, values_only=True):
                    out.append(" | ".join("" if v is None else str(v) for v in row))
            return f"Таблица: {p}\n\n" + "\n".join(out)[:MAX_TEXT]
        except ImportError:
            return "Для чтения XLSX установите openpyxl."
    if suffix in ARCHIVE_EXTS:
        return inspect_archive(str(p))
    return f"Файл: {p}\nРазмер: {p.stat().st_size} байт\nТип: {p.suffix or 'без расширения'}"

def inspect_archive(path: str) -> str:
    p=_path(path)
    if not p.is_file(): raise ValueError(f"Архив не найден: {p}")
    s=p.suffix.lower()
    if s==".zip":
        with zipfile.ZipFile(p) as z:
            names=z.namelist()[:MAX_FILES]
            return f"ZIP: {p}\nФайлов: {len(z.namelist())}\n\n" + "\n".join(names)
    if s in {".tar",".gz",".tgz",".bz2",".xz"}:
        try:
            with tarfile.open(p) as t:
                names=[m.name for m in t.getmembers()[:MAX_FILES]]
            return f"TAR-архив: {p}\n\n" + "\n".join(names)
        except tarfile.TarError as e: raise RuntimeError(f"Ошибка TAR: {e}") from e
    seven=shutil.which("7z") or shutil.which("7zz")
    if seven and s in {".7z",".rar"}:
        r=subprocess.run([seven,"l",str(p)],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=60)
        if r.returncode!=0: raise RuntimeError(r.stderr.strip() or "7-Zip не смог прочитать архив")
        return r.stdout[-MAX_TEXT:]
    return f"Архив {p.name} распознан, но для {s} нужен 7-Zip (7z/7zz) в PATH."

def extract_archive(path: str, destination: str = "") -> str:
    p=_path(path)
    if not p.is_file(): raise ValueError(f"Архив не найден: {p}")
    dest=_path(destination) if destination else p.with_name(p.stem+"_extracted")
    dest.mkdir(parents=True,exist_ok=True)
    if p.suffix.lower()==".zip":
        with zipfile.ZipFile(p) as z:
            root=dest.resolve()
            for member in z.infolist():
                target=(dest/member.filename).resolve()
                target.relative_to(root)
            z.extractall(dest)
    elif p.suffix.lower() in {".tar",".gz",".tgz",".bz2",".xz"}:
        with tarfile.open(p) as t:
            root=dest.resolve()
            for m in t.getmembers():
                (dest/m.name).resolve().relative_to(root)
            t.extractall(dest)
    else:
        seven=shutil.which("7z") or shutil.which("7zz")
        if not seven: raise RuntimeError("Для этого архива нужен 7-Zip. Установите 7-Zip и добавьте 7z.exe в PATH.")
        r=subprocess.run([seven,"x",str(p),f"-o{dest}","-y"],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=300)
        if r.returncode!=0: raise RuntimeError(r.stderr.strip() or r.stdout[-1000:])
    return f"Архив распакован: {dest}"

def edit_file(path: str, old: str, new: str, count: int = 1) -> str:
    """Safely replace text in a local UTF-8 text file, keeping a backup."""
    p = _path(path)
    if not p.is_file():
        raise ValueError(f"Файл не найден: {p}")
    if not old:
        raise ValueError("Старый текст для замены не указан")
    text = p.read_text(encoding="utf-8", errors="replace")
    occurrences = text.count(old)
    if occurrences == 0:
        raise ValueError("Искомый фрагмент не найден")
    if count == 0:
        raise ValueError("count должен быть не равен 0")
    if count < 0:
        count = occurrences
    backup = p.with_suffix(p.suffix + ".jarvis.bak")
    shutil.copy2(p, backup)
    updated = text.replace(old, new, count)
    p.write_text(updated, encoding="utf-8")
    return f"Файл изменён: {p}. Заменено: {min(occurrences, count)}. Резервная копия: {backup}"


def project_check(path: str = ".") -> str:
    """Run safe, read-only project diagnostics and return actionable output."""
    root = _path(path)
    if not root.exists():
        raise ValueError(f"Путь не найден: {root}")
    if root.is_file():
        root = root.parent
    results = [f"Проект: {root}"]
    def run(args, cwd=root, timeout=180):
        try:
            r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout)
            out = (r.stdout + "\n" + r.stderr).strip()
            return r.returncode, out[-MAX_TEXT:]
        except FileNotFoundError:
            return None, f"Команда не найдена: {args[0]}"
        except subprocess.TimeoutExpired:
            return None, f"Тайм-аут: {' '.join(args)}"

    checks = []
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        py_files = list(root.rglob("*.py"))[:500]
        bad = []
        for p in py_files:
            code, out = run([sys.executable, "-m", "py_compile", str(p)])
            if code not in (0, None):
                bad.append(f"{p}: {out}")
        checks.append(("Python syntax", bad))
        if (root / "pyproject.toml").exists():
            code, out = run([sys.executable, "-m", "pip", "check"], timeout=120)
            checks.append(("pip check", [] if code == 0 else [out]))
    if (root / "package.json").exists():
        code, out = run(["npm", "test", "--", "--runInBand"], timeout=180)
        checks.append(("npm test", [] if code == 0 else [out]))
        if code != 0:
            code2, out2 = run(["npm", "run", "build"], timeout=180)
            checks.append(("npm build", [] if code2 == 0 else [out2]))
    if (root / "pubspec.yaml").exists():
        code, out = run(["flutter", "analyze"], timeout=180)
        checks.append(("flutter analyze", [] if code == 0 else [out]))
    if not checks:
        checks.append(("project type", ["Не распознан поддерживаемый Python/Node/Flutter проект."]))
    failed = []
    for name, errors in checks:
        if errors:
            failed.append(f"[{name}]\n" + "\n".join(errors))
        else:
            results.append(f"OK: {name}")
    if failed:
        results.append("НАЙДЕНЫ ПРОБЛЕМЫ:\n" + "\n\n".join(failed))
    else:
        results.append("Проверка проекта завершена: критических ошибок в выполненных проверках не найдено.")
    return "\n\n".join(results)[-MAX_TEXT:]

def find_errors(path: str = ".") -> str:
    root=_path(path)
    if not root.exists(): raise ValueError(f"Путь не найден: {root}")
    errors=[]
    files=[]
    if root.is_file(): files=[root]
    else:
        for p in root.rglob("*"):
            if p.is_file() and len(files)<300 and p.suffix.lower() in TEXT_EXTS: files.append(p)
    markers=("traceback","exception","error:","syntaxerror","modulenotfounderror","filenotfounderror","failed","fatal error","build failed")
    for p in files:
        try: txt=p.read_text(encoding="utf-8",errors="replace")
        except OSError: continue
        hits=[line.strip() for line in txt.splitlines() if any(m in line.lower() for m in markers)]
        if hits: errors.append(f"\n[{p}]\n" + "\n".join(hits[:20]))
    return ("Ошибки/подозрительные строки найдены:" + "".join(errors))[:MAX_TEXT] if errors else "Явных строк ошибок в доступных текстовых файлах не найдено."

def run_command(command: str) -> str:
    command=str(command).strip()
    if not command: raise ValueError("Команда не указана")
    if sys.platform=="win32":
        proc=subprocess.run(["cmd","/c",command],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=120)
    else:
        proc=subprocess.run(command,shell=True,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=120)
    return f"Код возврата: {proc.returncode}\n{(proc.stdout+'\n'+proc.stderr).strip()[-MAX_TEXT:]}"

def shutdown(action: str = "shutdown") -> str:
    if sys.platform!="win32": raise RuntimeError("Управление питанием этой функцией реализовано для Windows.")
    action=action.lower().strip()
    commands={"shutdown":["shutdown","/s","/t","0"],"restart":["shutdown","/r","/t","0"],"sleep":["powershell","-NoProfile","-Command","Start-Sleep -Milliseconds 500; Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend',$false,$false)"]}
    if action not in commands: raise ValueError("Доступно: shutdown, restart, sleep")
    subprocess.Popen(commands[action],creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    return {"shutdown":"Выключаю компьютер.","restart":"Перезагружаю компьютер.","sleep":"Перевожу компьютер в сон."}[action]
