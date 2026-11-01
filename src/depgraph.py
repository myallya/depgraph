from __future__ import annotations

import argparse
import gzip
import io
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Set

DEFAULT_MAX_DEPTH = 3
DEFAULT_OUTPUT = "graph.png"
VALID_MODES = ("url", "local")

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Инструмент для визуализации графа зависимостей пакетов Alpine Linux."
    )
    parser.add_argument("-p", "--package", required=True, help="Имя анализируемого пакета")
    parser.add_argument(
        "-r", "--repo", required=True,
        help="URL репозитория, путь к локальному файлу или каталогу с тестом"
    )
    parser.add_argument(
        "-m", "--mode", choices=VALID_MODES, default="url",
        help="Режим работы: 'url' или 'local' (тестовый файл)"
    )
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT, help="Имя файла графа")
    parser.add_argument(
        "-d", "--max-depth", type=int, default=DEFAULT_MAX_DEPTH,
        help="Максимальная глубина анализа"
    )
    args = parser.parse_args(argv)
    validate_args(args)
    return args

def validate_args(args: argparse.Namespace) -> None:
    if not args.package.strip():
        print("Ошибка: имя пакета не может быть пустым", file=sys.stderr)
        sys.exit(1)
    if args.max_depth < 0:
        print("Ошибка: max-depth должен быть >= 0", file=sys.stderr)
        sys.exit(1)
    if not args.output.strip():
        print("Ошибка: имя выходного файла не может быть пустым", file=sys.stderr)
        sys.exit(1)
        
    if args.mode == "local":
        path = Path(args.repo)
        if not path.exists():
            print(f"Ошибка: локальный путь не существует: {args.repo}", file=sys.stderr)
            sys.exit(1)
    elif args.mode == "url":
        if not (args.repo.startswith("http://") or args.repo.startswith("https://")):
            print("Ошибка: в режиме 'url' репозиторий должен быть http(s) URL", file=sys.stderr)
            sys.exit(1)

def print_config(args: argparse.Namespace) -> None:
    print("package={}".format(args.package))
    print("repo={}".format(args.repo))
    print("mode={}".format(args.mode))
    print("output={}".format(args.output))
    print("max-depth={}".format(args.max_depth))

def load_apkindex(source: str, mode: str) -> str:
    if mode == "url":
        url = source.rstrip("/") + "/APKINDEX.tar.gz"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
        except urllib.error.URLError as exc:
            print(f"Ошибка: не удалось скачать APKINDEX с {url}: {exc}", file=sys.stderr)
            sys.exit(1)
        return _extract_apkindex_from_tar_gz(data)
    else:
        path = Path(source)
        if path.is_dir():
            for candidate in [path / "APKINDEX.tar.gz", path / "APKINDEX"]:
                if candidate.exists():
                    path = candidate
                    break
            else:
                print(f"Ошибка: в каталоге {source} не найден APKINDEX", file=sys.stderr)
                sys.exit(1)

        if path.name.endswith(".tar.gz") or path.suffixes[-2:] == [".tar", ".gz"]:
            return _extract_apkindex_from_tar_gz(path.read_bytes())
        else:
            return path.read_text(encoding="utf-8", errors="replace")

def _extract_apkindex_from_tar_gz(data: bytes) -> str:
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            member = None
            for m in tar.getmembers():
                if m.name == "APKINDEX" or m.name.endswith("/APKINDEX"):
                    member = m
                    break
            if member is None:
                for m in tar.getmembers():
                    if "SIGN" not in m.name.upper() and m.isfile():
                        member = m
                        break
            if member is None:
                print("Ошибка: внутри архива не найден файл APKINDEX", file=sys.stderr)
                sys.exit(1)
            extracted = tar.extractfile(member)
            if extracted is None:
                print("Ошибка: не удалось прочитать файл APKINDEX", file=sys.stderr)
                sys.exit(1)
            return extracted.read().decode("utf-8", errors="replace")
    except (tarfile.TarError, OSError, gzip.BadGzipFile) as exc:
        print(f"Ошибка: не удалось извлечь APKINDEX: {exc}", file=sys.stderr)
        sys.exit(1)

def parse_packages(apkindex_text: str) -> Dict[str, List[str]]:
    packages: Dict[str, List[str]] = {}
    current_name: Optional[str] = None
    current_deps: List[str] = []

    for raw_line in apkindex_text.splitlines():
        line = raw_line.rstrip("\n")
        if not line:
            if current_name is not None:
                packages[current_name] = current_deps
            current_name = None
            current_deps = []
            continue

        if len(line) < 2 or line[1] != ":":
            continue

        key = line[0]
        value = line[2:]

        if key == "P":
            current_name = value
            current_deps = []
        elif key == "D" and current_name is not None:
            current_deps = [dep for dep in value.split() if dep]

    if current_name is not None:
        packages[current_name] = current_deps

    return packages

# --- НОВЫЕ ФУНКЦИИ ДЛЯ ЭТАПА 3 ---

def load_local_graph(file_path: str) -> Dict[str, List[str]]:
    """Читает тестовый файл формата 'A: B C' и возвращает словарь."""
    packages = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                pkg, deps_str = line.split(":", 1)
                pkg = pkg.strip()
                deps = deps_str.strip().split()
                packages[pkg] = deps
    except Exception as e:
        print(f"Ошибка при чтении файла {file_path}: {e}", file=sys.stderr)
        sys.exit(1)
    return packages

def build_graph_bfs(
    packages: Dict[str, List[str]], 
    start_pkg: str, 
    max_depth: int
) -> Dict[str, List[str]]:
    """Строит граф зависимостей в ширину (BFS) с помощью рекурсии.
    Корректно обрабатывает циклы и ограничивает глубину.
    """
    graph: Dict[str, List[str]] = {}

    # Защита от ситуаций, когда пакет вообще не найден в базе
    if start_pkg not in packages:
        print(f"Ошибка: пакет '{start_pkg}' не найден в индексе репозитория", file=sys.stderr)
        sys.exit(1)

    # visited хранит пары (имя_пакета, глубина), чтобы не зациклиться
    visited: Set[tuple[str, int]] = set()

    def recursive_bfs(current_pkg: str, current_depth: int, path: Set[str]):
        """Внутренняя рекурсивная функция."""
        # Базовый случай 1: достигли максимальной глубины
        if current_depth > max_depth:
            return
        
        # Базовый случай 2: мы уже обрабатывали этот пакет на этой же глубине
        if (current_pkg, current_depth) in visited:
            return
        
        visited.add((current_pkg, current_depth))

        # Получаем прямые зависимости (или пустой список, если их нет)
        deps = packages.get(current_pkg, [])
        
        if current_pkg not in graph:
            graph[current_pkg] = []
        
        # Обход зависимостей (в ширину на текущем уровне)
        for dep in deps:
            # Обработка цикла: если зависимость уже есть в текущем пути
            if dep in path:
                # Добавляем ребро, но не идем глубже, чтобы не зациклиться
                graph[current_pkg].append(dep)
                continue
                
            graph[current_pkg].append(dep)
            
            # Рекурсивный вызов для следующего уровня (глубина + 1)
            recursive_bfs(dep, current_depth + 1, path | {dep})

    # Запускаем алгоритм
    recursive_bfs(start_pkg, 0, {start_pkg})
    return graph


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    print_config(args)

    packages: Dict[str, List[str]] = {}

    if args.mode == "url":
        apkindex_text = load_apkindex(args.repo, "url")
        packages = parse_packages(apkindex_text)
    else:
        # Если передан путь к txt-файлу, используем его как тестовый граф
        if Path(args.repo).is_file() and args.repo.endswith(".txt"):
            packages = load_local_graph(args.repo)
        else:
            apkindex_text = load_apkindex(args.repo, "local")
            packages = parse_packages(apkindex_text)

    # Строим граф (Этап 3)
    print(f"\nПостроение графа для пакета '{args.package}' (глубина: {args.max_depth})...")
    graph = build_graph_bfs(packages, args.package, args.max_depth)

    print("\nРезультаты обхода (BFS с рекурсией):")
    for pkg, deps in graph.items():
        print(f"{pkg} -> {', '.join(deps) if deps else '(нет зависимостей)'}")


if __name__ == "__main__":
    main()