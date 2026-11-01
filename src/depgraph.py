from __future__ import annotations

import argparse
import gzip
import io
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_MAX_DEPTH = 3
DEFAULT_OUTPUT = "graph.png"
VALID_MODES = ("url", "local")

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Разбирает и проверяет аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description=(
            "Инструмент для визуализации графа зависимостей пакетов Alpine Linux (apk). "
            "Не использует менеджеры пакетов и сторонние библиотеки для получения зависимостей."
        )
    )
    parser.add_argument(
        "-p",
        "--package",
        required=True,
        help="Имя анализируемого пакета",
    )
    parser.add_argument(
        "-r",
        "--repo",
        required=True,
        help=(
            "URL репозитория Alpine (каталог, содержащий APKINDEX.tar.gz) "
            "или путь к локальному тестовому файлу/каталогу"
        ),
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=VALID_MODES,
        default="url",
        help="Режим работы с репозиторием: 'url' (скачивание) или 'local' (локальный путь)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Имя файла с изображением графа (по умолчанию: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "-d",
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        help=f"Максимальная глубина анализа зависимостей (по умолчанию: {DEFAULT_MAX_DEPTH})",
    )

    args = parser.parse_args(argv)
    validate_args(args)
    return args

def validate_args(args: argparse.Namespace) -> None:
    """Проверяет корректность переданных аргументов. При ошибке завершает программу."""
    if not args.package.strip():
        print("Ошибка: имя пакета не может быть пустым", file=sys.stderr)
        sys.exit(1)

    if args.max_depth < 0:
        print("Ошибка: max-depth должен быть неотрицательным числом", file=sys.stderr)
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
        if not (
            args.repo.startswith("http://") or args.repo.startswith("https://")
        ):
            print(
                "Ошибка: в режиме 'url' репозиторий должен быть http(s) URL",
                file=sys.stderr,
            )
            sys.exit(1)

def print_config(args: argparse.Namespace) -> None:
    """Выводит все настраиваемые параметры в формате ключ=значение (требование этапа 1)."""
    print("package={}".format(args.package))
    print("repo={}".format(args.repo))
    print("mode={}".format(args.mode))
    print("output={}".format(args.output))
    print("max-depth={}".format(args.max_depth))

def load_apkindex(source: str, mode: str) -> str:
    """Загружает и возвращает текстовое содержимое файла APKINDEX.
    В режиме 'url' source — это базовый URL репозитория, содержащего APKINDEX.tar.gz.
    В режиме 'local' source — путь к APKINDEX.tar.gz, обычному APKINDEX или каталогу с ними.
    """
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
            candidates = [
                path / "APKINDEX.tar.gz",
                path / "APKINDEX",
            ]
            for candidate in candidates:
                if candidate.exists():
                    path = candidate
                    break
            else:
                print(
                    f"Ошибка: в каталоге {source} не найден APKINDEX или APKINDEX.tar.gz",
                    file=sys.stderr,
                )
                sys.exit(1)

        if path.name.endswith(".tar.gz") or path.suffixes[-2:] == [".tar", ".gz"]:
            data = path.read_bytes()
            return _extract_apkindex_from_tar_gz(data)
        else:
            # Обычный текстовый файл APKINDEX
            return path.read_text(encoding="utf-8", errors="replace")

def _extract_apkindex_from_tar_gz(data: bytes) -> str:
    """Извлекает файл APKINDEX из архива tar.gz и возвращает его содержимое."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            member = None
            for m in tar.getmembers():
                if m.name == "APKINDEX" or m.name.endswith("/APKINDEX"):
                    member = m
                    break
            if member is None:
                # Запасной вариант: берём первый обычный файл (не подпись)
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
    """Разбирает текст APKINDEX в словарь: имя_пакета → список зависимостей.

    Используются только поля P: (имя) и D: (зависимости).
    """
    packages: Dict[str, List[str]] = {}
    current_name: Optional[str] = None
    current_deps: List[str] = []

    for raw_line in apkindex_text.splitlines():
        line = raw_line.rstrip("\n")
        if not line:
            # Конец записи о пакете
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
            # Зависимости разделены пробелами
            current_deps = [dep for dep in value.split() if dep]

    # Обработка последней записи, если файл не заканчивается пустой строкой
    if current_name is not None:
        packages[current_name] = current_deps

    return packages

def get_direct_dependencies(
    packages: Dict[str, List[str]], package_name: str
) -> List[str]:
    """Возвращает список прямых зависимостей указанного пакета."""
    if package_name not in packages:
        print(
            f"Ошибка: пакет '{package_name}' не найден в индексе репозитория",
            file=sys.stderr,
        )
        sys.exit(1)
    return packages[package_name]

def main(argv: Optional[List[str]] = None) -> None:
    """Точка входа в программу."""
    args = parse_args(argv)

    # Этап 1: вывод конфигурации
    print_config(args)

    # Этап 2: получение и вывод прямых зависимостей
    apkindex_text = load_apkindex(args.repo, args.mode)
    packages = parse_packages(apkindex_text)
    deps = get_direct_dependencies(packages, args.package)

    print()
    print(f"Прямые зависимости пакета '{args.package}':")
    if not deps:
        print("(нет)")
    else:
        for dep in deps:
            print(dep)

if __name__ == "__main__":
    main()
