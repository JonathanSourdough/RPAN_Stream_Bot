from typing import Optional, Union, Dict, List
from pathlib import Path
import logging
import json

from selenium.webdriver.chrome.options import Options
from selenium import webdriver
import discord_webhook

logger = logging.getLogger("bot.utils")


def load_json(json_path: Path) -> Dict:
    if not json_path.is_file():
        logger.error(f"json at '{json_path}' is not a file!")
        raise Exception(f"json at '{json_path}' is not a file!")
    try:
        logger.debug(f"Loaded '{json_path}' successfully.")
        return json.loads(json_path.read_text())
    except json.decoder.JSONDecodeError:
        logger.error(f"Failed loading json at '{json_path}'!")
        raise Exception(f"Failed loading json at '{json_path}'!")


def save_json(json_path: Path, save_dict: Union[Dict, List]) -> None:
    Path(json_path).write_text(json.dumps(save_dict, indent=4, sort_keys=True))
    logger.debug(f"Saved '{json_path}' successfully.")


def launch_chrome(chromedriver_path: Path):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--window-size=640x480")
    chrome_options.add_experimental_option(
        "prefs", {"profile.managed_default_content_settings.images": 2, "disk-cache-size": 4096}
    )
    driver = webdriver.Chrome(str(chromedriver_path), chrome_options=chrome_options)
    return driver


def discord_embed_builder(
    embed_title: str = "",
    embed_description: str = "",
    embed_image: str = "",
    embed_thumbnail: str = "",
    author: str = "",
    author_url: str = "",
    author_icon: str = "",
    fields: List[Dict] = [],
) -> discord_webhook.DiscordEmbed:
    embed = discord_webhook.DiscordEmbed(
        title=embed_title,
        description=embed_description,
    )
    if embed_image:
        embed.set_image(url=embed_image)
    if embed_thumbnail:
        embed.set_thumbnail(url=embed_thumbnail)
    if author:
        embed.set_author(name=author, url=author_url)
        if author_icon:
            embed.author["icon_url"] = author_icon
    for field in fields:
        if "name" not in field:
            field["name"] = ""
        if "value" not in field:
            field["value"] = ""
        if "inline" not in field:
            field["inline"] = False
        embed.add_embed_field(name=field["name"], value=field["value"], inline=field["inline"])
    return embed


def webhook_post(
    webhook=discord_webhook.DiscordWebhook,
    plain_text_message: str = "",
    embeds: List[discord_webhook.DiscordEmbed] = [],
):
    webhook.embeds = []

    for embed in embeds:
        webhook.add_embed(embed)
    webhook.set_content(plain_text_message)
    webhook.execute()
