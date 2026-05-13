import json
from pathlib import Path


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def save_json(path, payload):
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_text(path, payload):
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(payload, encoding="utf-8")


def load_json(path, default=None):
    path_obj = Path(path)
    if not path_obj.exists():
        return {} if default is None else default
    return json.loads(path_obj.read_text(encoding="utf-8"))
