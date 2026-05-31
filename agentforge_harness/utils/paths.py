import os
from pathlib import Path

EXCLUDED_DIRS = {"node_modules", "__pycache__", ".git", ".venv", "venv"}

def find_source_files(search_path: Path, max_files: int = 500) -> list[Path]:
    files: list[Path] = []
    for root, dirs, filenames in os.walk(search_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for filename in filenames:
            if filename.startswith("."):
                continue
            file_path = Path(root) / filename
            if not is_binary_file(file_path):
                files.append(file_path)
                if len(files) >= max_files:
                    return files
    return files

def resolve_path(base : str | Path , path : str | Path):
    path = Path(path)
    if path.is_absolute():
        return path.resolve()
    
    return Path(base).resolve() / path


def is_binary_file(path : str | Path) -> bool  :
    try :
       with open(path , "rb") as f:
        chunk = f.read(8192)
        return b"\x00" in chunk
    except (OSError , IOError):
        return False

def display_path_rel_to_cwd(path: str, cwd: Path | None) -> str:
    try:
        p = Path(path)
    except Exception:
        return path

    if cwd:
        try:
            return str(p.relative_to(cwd))
        except ValueError:
            pass

    return str(p)

def ensure_parent_directory(path : Path) -> Path:
    path = Path(path)

    path.parent.mkdir(parents=True , exist_ok = True)
    return path

