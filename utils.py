from typing import Optional, Union, Dict, List
from pathlib import Path
import logging
import json


def load_json(json_path: Path) -> Optional[Dict]:
    if not json_path.is_file():
        logging.error(f"json at '{json_path}' is not a file!")
    try:
        return json.loads(json_path.read_text())
    except json.decoder.JSONDecodeError:
        logging.error(f"Failed loading json at '{json_path}'!")
        return None


def save_json(json_path: Path, save_dict: Union[Dict, List]) -> None:
    Path(json_path).write_text(json.dumps(save_dict, indent=4, sort_keys=True))
    logging.info(f"Loaded '{json_path}' successfully.")
