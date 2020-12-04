from typing import Optional, Union, Dict, List
from pathlib import Path
import logging
import json

from selenium.webdriver.chrome.options import Options
from selenium import webdriver

logger = logging.getLogger("bot.utils")


def launch_chrome(chromedriver_path: Path):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--window-size=640x480")
    chrome_options.add_experimental_option(
        "prefs", {"profile.managed_default_content_settings.images": 2, "disk-cache-size": 4096}
    )
    driver = webdriver.Chrome(str(chromedriver_path), chrome_options=chrome_options)
    return driver


def load_json(json_path: Path) -> Optional[Dict]:
    if not json_path.is_file():
        logger.error(f"json at '{json_path}' is not a file!")
    try:
        logger.debug(f"Loaded '{json_path}' successfully.")
        return json.loads(json_path.read_text())
    except json.decoder.JSONDecodeError:
        logger.error(f"Failed loading json at '{json_path}'!")
        return None


def save_json(json_path: Path, save_dict: Union[Dict, List]) -> None:
    Path(json_path).write_text(json.dumps(save_dict, indent=4, sort_keys=True))
    logger.debug(f"Saved '{json_path}' successfully.")