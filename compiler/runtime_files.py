"""Resolve the same runtime resources in a checkout and an installed wheel."""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent


def resource_directory(packaged, source):
    installed = PACKAGE / packaged
    if installed.is_dir():
        return installed
    # An installed compiler must not pick up an unrelated application's files.
    root = PACKAGE.parent
    if (root / "pyproject.toml").is_file() and (root / source).is_dir():
        return root / source
    raise RuntimeError(f"Sudograph runtime resource is missing: {packaged}")


def renderer_directory():
    return resource_directory("_assets", "app")


def nexus_directory():
    return resource_directory("_nexus", "nexus-client")


def implementation_files():
    """Canonical logical paths keep publisher hashes independent of installation."""
    for label, root in (("compiler", PACKAGE), ("app", renderer_directory())):
        # Path ordering folds case on Windows. Logical wire paths must use the
        # same byte ordering when this exact wheel runs on another platform.
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root)
            if (path.is_file() and "__pycache__" not in relative.parts
                    and relative.parts[0] not in {"_assets", "_nexus"}
                    and path.suffix != ".pyc"):
                yield f"{label}/{relative.as_posix()}", path
