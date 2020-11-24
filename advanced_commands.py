from pathlib import Path
from typing import Optional, Dict, List

from prawcore import NotFound
import praw

import utils


def subscribe(script_dir: Path, users: Dict, new_message: Dict) -> Optional[str]:
    message = new_message["message"]
    author = new_message["author"]

    if not utils.check_permission(users, author, ["admins", "moderators"]):
        return None

    if author not in users["subscribers"]:
        users["subscribers"].append(author)
        utils.save_json((script_dir / "users.json"), users)
        message.reply(f"u/{author} has been subscribed. Use !unsubscribe to unsubscribe")
        return "users"
    else:
        message.reply(f"u/{author} was already subscribed.")
        return None


def unsubscribe(script_dir: Path, users: Dict, new_message: Dict) -> Optional[str]:
    message = new_message["message"]
    author = new_message["author"]

    if author in users["subscribers"]:
        users["subscribers"].remove(author)
        utils.save_json((script_dir / "users.json"), users)
        message.reply(f"u/{author} has been unsubscribed.")
        return "users"
    else:
        message.reply(f"u/{author} was not subscribed.")
        return None


def subother(
    script_dir: Path, users: Dict, reddit: praw.Reddit, new_message: Dict
) -> Optional[str]:
    message = new_message["message"]
    body = new_message["body"]
    author = new_message["author"]

    if not utils.check_permission(users, author, ["admins", "moderators"]):
        return None

    to_subscribe = body.split(" ")[1]

    if to_subscribe.startswith("u/"):
        to_subscribe = to_subscribe[len("u/") :]

    try:
        reddit.redditor(to_subscribe).id
        users["subscribers"].append(to_subscribe)
        utils.save_json((script_dir / "users.json"), users)
        message.reply(f"u/{to_subscribe} has been subscribed. Use !unsubscribe to unsubscribe")
        return "users"
    except NotFound:
        message.reply(f"u/{to_subscribe} not found.")
        return None


def unsubother(script_dir: Path, users: Dict, new_message: Dict) -> Optional[str]:
    message = new_message["message"]
    body = new_message["body"]
    author = new_message["author"]

    if not utils.check_permission(users, author, ["admins", "moderators"]):
        return None

    to_unsubscribe = body.split(" ")[1]

    if to_unsubscribe.startswith("u/"):
        to_unsubscribe = to_unsubscribe[len("u/") :]

    if to_unsubscribe in users["subscribers"]:
        users["subscribers"].remove(to_unsubscribe)
        utils.save_json((script_dir / "users.json"), users)
        message.reply(f"u/{to_unsubscribe} has been unsubscribed.")
        return "users"
    else:
        message.reply(f"u/{to_unsubscribe} was not previously subscribed.")
        return None


def monitor(
    script_dir: Path,
    users: Dict,
    reddit: praw.Reddit,
    monitored_streams: Dict,
    monitored_posts: Dict,
    new_message: Dict,
) -> Optional[str]:
    message = new_message["message"]
    body = new_message["body"]

    if not utils.check_permission(users, message.author.name, ["admins", "moderators"]):
        return None

    to_monitor = body.split(" ")[1]

    submission_to_monitor = reddit.submission(to_monitor)

    try:
        submission_to_monitor.allow_live_comments
        if to_monitor not in monitored_streams:
            monitored_streams[to_monitor] = None
            utils.save_json(script_dir / "monitored_streams.json", monitored_streams)

            message.reply(f"{to_monitor} is now being monitored")
            return "monitored_streams"
        else:
            message.reply(f"{to_monitor} already being monitored")
            return None
    except AttributeError:
        if to_monitor not in monitored_posts:
            monitored_posts[to_monitor] = len(submission_to_monitor.comments.list())
            utils.save_json(script_dir / "monitored_posts.json", monitored_posts)

            message.reply(f"{to_monitor} is now being monitored")
            return "monitored_posts"
        else:
            message.reply(f"{to_monitor} already being monitored")
            return None


def end(
    script_dir: Path,
    users: Dict,
    reddit: praw.Reddit,
    monitored_streams: Dict,
    monitored_posts: Dict,
    new_message: Dict,
) -> Optional[str]:
    message = new_message["message"]
    body = new_message["body"]
    context = new_message["context"]
    author = new_message["author"]
    submission_id = new_message["submission_id"]

    if not utils.check_permission(users, author, ["admins", "moderators"]):
        return None

    if context == "stream":
        if submission_id in monitored_streams:
            monitored_streams.pop(submission_id)
            utils.save_json(script_dir / "monitored_streams.json", monitored_streams)
            message.reply(f"{submission_id} is no longer being monitored")
            return "monitored_streams"
        else:
            message.reply(f"{submission_id} was not being monitored")
            return None

    elif context == "inbox":
        to_remove = body.split(" ")[1]

        submission_to_monitor = reddit.submission(to_remove)

        try:
            submission_to_monitor.allow_live_comments
            if to_remove in monitored_streams:
                monitored_streams.pop(to_remove)
                utils.save_json(script_dir / "monitored_streams.json", monitored_streams)
                message.reply(f"{to_remove} is no longer being monitored")
                return "monitored_streams"
            else:
                message.reply(f"{to_remove} was not being monitored")
                return None
        except AttributeError:
            if to_remove in monitored_posts:
                monitored_posts.pop(to_remove)
                utils.save_json(script_dir / "monitored_posts.json", monitored_posts)
                message.reply(f"{to_remove} is no longer being monitored")
                return "monitored_posts"
            else:
                message.reply(f"{to_remove} was not being monitored")
                return None

    else:
        return None


def advanced_commands(
    script_dir: Path,
    users: Dict,
    reddit: praw.Reddit,
    monitored_streams: Dict,
    monitored_posts: Dict,
    new_message: Dict,
) -> Optional[str]:
    message_body_lower = new_message["body"].lower()

    if message_body_lower == "!subscribe":
        return subscribe(script_dir, users, new_message)

    elif message_body_lower == "!unsubscribe":
        return unsubscribe(script_dir, users, new_message)

    elif "!subother" in message_body_lower:
        return subother(script_dir, users, reddit, new_message)

    elif "!unsubother" in message_body_lower:
        return unsubother(script_dir, users, new_message)

    elif "!monitor" in message_body_lower:
        return monitor(script_dir, users, reddit, monitored_streams, monitored_posts, new_message)

    elif "!end" in message_body_lower:
        return end(script_dir, users, reddit, monitored_streams, monitored_posts, new_message)

    return None
