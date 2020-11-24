from pathlib import Path
from typing import Optional, Union, Dict, List
import json


def load_json(json_path: Path) -> Optional[Dict]:
    if json_path.is_file():
        try:
            return json.loads(json_path.read_text())
        except json.decoder.JSONDecodeError:
            return None
    else:
        return None


def save_json(json_path: Path, save_dict: Union[Dict, List]) -> None:
    Path(json_path).write_text(json.dumps(save_dict, indent=4, sort_keys=True))


def check_permission(users_dict: Dict, user: str, permissions_allowed: List[str]) -> bool:
    if "any" in permissions_allowed:
        return True
    for permission in permissions_allowed:
        if user in users_dict[permission]:
            return True
    else:
        return False
