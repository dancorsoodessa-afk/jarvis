"""Universal Windows/file tools for JARVIS."""
from __future__ import annotations
import json, os, platform, shutil, subprocess, sys, tarfile, zipfile, tempfile, urllib.request, urllib.error, urllib.parse
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
    try:
        count = int(count)
    except (TypeError, ValueError):
        raise ValueError("count должен быть целым числом")
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
    """Run safe project diagnostics and return actionable output without changing source files."""
    root = _path(path)
    if not root.exists():
        raise ValueError(f"Путь не найден: {root}")

    def run(args, cwd=None, timeout=180):
        workdir = cwd or (root if root.is_dir() else root.parent)
        try:
            r = subprocess.run(
                args, cwd=str(workdir), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout
            )
            out = (r.stdout + "\n" + r.stderr).strip()
            return r.returncode, out[-MAX_TEXT:]
        except FileNotFoundError:
            return None, f"Команда не найдена: {args[0]}"
        except subprocess.TimeoutExpired:
            return None, f"Тайм-аут: {' '.join(args)}"

    if root.is_file():
        if root.suffix.lower() == ".py":
            code, out = run([
                sys.executable, "-c",
                "import ast, pathlib; ast.parse(pathlib.Path(r'%s').read_text(encoding='utf-8'))" % str(root)
            ], cwd=root.parent)
            if code == 0:
                return f"Проект: {root.parent}\n\nOK: Python syntax\n\nПроверка проекта завершена: критических ошибок в выполненной проверке не найдено."
            return f"Проект: {root.parent}\n\nНАЙДЕНЫ ПРОБЛЕМЫ:\n[Python syntax]\n{out}"
        root = root.parent

    results = [f"Проект: {root}"]
    checks = []

    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        py_files = list(root.rglob("*.py"))[:500]
        bad = []
        for p in py_files:
            code, out = run([
                sys.executable, "-c",
                "import ast, pathlib; ast.parse(pathlib.Path(r'%s').read_text(encoding='utf-8'))" % str(p)
            ])
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
    output = (proc.stdout + "\n" + proc.stderr).strip()[-MAX_TEXT:]
    return f"Код возврата: {proc.returncode}\n{output}"

def shutdown(action: str = "shutdown") -> str:
    if sys.platform!="win32": raise RuntimeError("Управление питанием этой функцией реализовано для Windows.")
    action=action.lower().strip()
    commands={"shutdown":["shutdown","/s","/t","0"],"restart":["shutdown","/r","/t","0"],"sleep":["powershell","-NoProfile","-Command","Start-Sleep -Milliseconds 500; Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend',$false,$false)"]}
    if action not in commands: raise ValueError("Доступно: shutdown, restart, sleep")
    subprocess.Popen(commands[action],creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    return {"shutdown":"Выключаю компьютер.","restart":"Перезагружаю компьютер.","sleep":"Перевожу компьютер в сон."}[action]

def app_test_environment() -> str:
    """Проверить доступность инструментов тестирования приложения."""
    tools = {
        "JMeter": shutil.which("jmeter") or shutil.which("jmeter.bat"),
        "ADB": shutil.which("adb"),
        "Flutter": shutil.which("flutter"),
        "Gradle": shutil.which("gradle") or shutil.which("gradle.bat"),
        "Xcode": shutil.which("xcodebuild"),
    }
    data = {
        "JMeter": "доступен" if tools["JMeter"] else "не найден",
        "ADB": "доступен" if tools["ADB"] else "не найден",
        "Flutter": "доступен" if tools["Flutter"] else "не найден",
        "Gradle": "доступен" if tools["Gradle"] else "не найден",
        "Xcode": "доступен" if tools["Xcode"] else "не найден (Xcode работает только на macOS)",
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def android_app_diagnostics(serial: str = "", package: str = "") -> str:
    """Диагностика Android через ADB: устройство, ресурсы и критические ошибки."""
    adb = shutil.which("adb")
    if not adb:
        return "ADB не найден. Нужен Android SDK Platform-Tools."
    code, devices = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=20).returncode, ""
    p = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=20)
    devices = (p.stdout + p.stderr).strip()
    rows = [x for x in devices.splitlines() if "\tdevice" in x]
    if not rows:
        return "Android-устройство не подключено или USB-отладка не разрешена."
    target = serial.strip() or rows[0].split("\t", 1)[0]
    prefix = [adb, "-s", target]
    def sh(*args, timeout=30):
        r = subprocess.run(prefix + list(args), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return (r.stdout + r.stderr).strip()
    log = sh("logcat", "-d", "-v", "time", timeout=45)
    needles = ("FATAL EXCEPTION", "ANR in ", "SecurityException",
               "OutOfMemoryError", "AndroidRuntime", "DeadObjectException")
    if package.strip():
        log = "\n".join(x for x in log.splitlines() if package.strip() in x)
    errors = [x for x in log.splitlines() if any(n in x for n in needles)]
    data = {
        "устройство": target,
        "Android": sh("shell", "getprop", "ro.build.version.release"),
        "модель": sh("shell", "getprop", "ro.product.model"),
        "память": sh("shell", "cat", "/proc/meminfo")[:3000],
        "батарея": sh("shell", "dumpsys", "battery")[:2000],
        "критические_ошибки": errors[-100:],
        "результат": "ОШИБКИ НАЙДЕНЫ" if errors else "критических ошибок в logcat не найдено",
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def jmeter_load_test(jmx_path: str, result_file: str = "") -> str:
    """Запустить JMeter в non-GUI режиме. Запуск нагрузки требует подтверждения."""
    exe = shutil.which("jmeter") or shutil.which("jmeter.bat")
    if not exe:
        return "JMeter не найден. Добавьте Apache JMeter/bin в PATH."
    jmx = _path(jmx_path)
    if not jmx.is_file() or jmx.suffix.lower() != ".jmx":
        raise ValueError(f"JMX-файл не найден: {jmx}")
    result = _path(result_file) if result_file else jmx.with_suffix(".jtl")
    result.parent.mkdir(parents=True, exist_ok=True)
    log = result.with_suffix(".jmeter.log")
    r = subprocess.run([exe, "-n", "-t", str(jmx), "-l", str(result), "-j", str(log)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    return json.dumps({
        "инструмент": "JMeter", "статус": "OK" if r.returncode == 0 else "ОШИБКА",
        "код": r.returncode, "результат": str(result), "лог": str(log),
        "вывод": (r.stdout + "\n" + r.stderr)[-5000:]
    }, ensure_ascii=False, indent=2)


def loaderio_status(action: str = "tests", test_id: str = "") -> str:
    """Loader.io API. Ключ берётся только из JARVIS_LOADERIO_KEY."""
    key = os.environ.get("JARVIS_LOADERIO_KEY", "").strip()
    if not key:
        return "Loader.io не настроен: задайте JARVIS_LOADERIO_KEY."
    base = "https://api.loader.io/v2"
    headers = {"loaderio-auth": key}
    if action == "apps":
        url, method = f"{base}/apps", "GET"
    elif action == "tests":
        url, method = f"{base}/tests", "GET"
    elif action == "results":
        if not test_id: return "Укажите test_id."
        url, method = f"{base}/tests/{test_id}/results", "GET"
    elif action == "run":
        if not test_id: return "Укажите test_id."
        url, method = f"{base}/tests/{test_id}/run", "PUT"
    else:
        return "Доступно: apps, tests, results, run."
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")[:MAX_TEXT]
    except urllib.error.HTTPError as exc:
        return f"Loader.io HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:2000]}"


def cloudflare_analytics(query: str = "") -> str:
    """Cloudflare Analytics GraphQL. Ключ: JARVIS_CLOUDFLARE_TOKEN."""
    token = os.environ.get("JARVIS_CLOUDFLARE_TOKEN", "").strip()
    if not token:
        return "Cloudflare не настроен: задайте JARVIS_CLOUDFLARE_TOKEN."
    query = query.strip() or "query { viewer { accounts { id name } } }"
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/graphql", data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")[:MAX_TEXT]
    except urllib.error.HTTPError as exc:
        return f"Cloudflare HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:2000]}"


def manageengine_monitor(path: str = "") -> str:
    """ManageEngine Applications Manager REST. URL/key хранятся в переменных окружения."""
    base = os.environ.get("JARVIS_MANAGEENGINE_URL", "").strip().rstrip("/")
    key = os.environ.get("JARVIS_MANAGEENGINE_KEY", "").strip()
    if not base or not key:
        return "ManageEngine не настроен: задайте JARVIS_MANAGEENGINE_URL и JARVIS_MANAGEENGINE_KEY."
    sep = "&" if "?" in path else "?"
    url = base + "/" + path.lstrip("/")
    url += f"{sep}apikey={urllib.parse.quote(key)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")[:MAX_TEXT]
    except urllib.error.HTTPError as exc:
        return f"ManageEngine HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:2000]}"
