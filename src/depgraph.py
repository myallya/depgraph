from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

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
    """Выводит все настраиваемые параметры в формате ключ-значение (требование этапа 1)."""
    print("package={}".format(args.package))
    print("repo={}".format(args.repo))
    print("mode={}".format(args.mode))
    print("output={}".format(args.output))
    print("max-depth={}".format(args.max_depth))

def main(argv: Optional[List[str]] = None) -> None:
    """Точка входа в программу."""
    args = parse_args(argv)

    # Этап 1: вывод конфигурации
    print_config(args)


if __name__ == "__main__":
    main()