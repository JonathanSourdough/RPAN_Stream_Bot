from typing import Optional, Dict, List, Set
from pathlib import Path
import logging

from prawcore import NotFound
import praw

import utils


def get_permissions(users_dict: Dict, user: str) -> Set[str]:
    user_permissions = set()
    for permission, user_names in users_dict.items():
        if user in user_names:
            user_permissions.add(permission)
    return user_permissions


def subscribe(script_dir: Path, users: Dict, new_message: Dict) -> Optional[str]:
    message = new_message["message"]
    body = new_message["body"]
    context = new_message["context"]
    author = new_message["author"]
    submission_id = new_message["submission_id"]

    permissions_needed = {"admins", "moderators"}
    user_permissions = get_permissions(users, author)

    if not permissions_needed.intersection(user_permissions):
        logging.info(
            f"!subscribe used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Insufficent Permission | Has: {user_permissions} Needs one of: {permissions_needed}"
        )
        return None

    if author not in users["subscribers"]:
        users["subscribers"].append(author)
        utils.save_json((script_dir / "users.json"), users)
        message.reply(f"u/{author} has been subscribed. Use !unsubscribe to unsubscribe")
        logging.info(
            f"!subscribe used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | u/{author} now subscribed."
        )
        return "users"
    else:
        message.reply(f"u/{author} was already subscribed.")
        logging.info(
            f"!subscribe used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | u/{author} was already subscribed."
        )
        return None


def unsubscribe(script_dir: Path, users: Dict, new_message: Dict) -> Optional[str]:
    message = new_message["message"]
    body = new_message["body"]
    context = new_message["context"]
    author = new_message["author"]
    submission_id = new_message["submission_id"]

    if author in users["subscribers"]:
        users["subscribers"].remove(author)
        utils.save_json((script_dir / "users.json"), users)
        message.reply(f"u/{author} has been unsubscribed.")
        return "users"
        logging.info(
            f"!unsubscribe used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | u/{author} has been unsubscribed."
        )
    else:
        message.reply(f"u/{author} was not subscribed.")
        logging.info(
            f"!unsubscribe used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | u/{author} was not subscribed."
        )
        return None


def subother(
    script_dir: Path, users: Dict, reddit: praw.Reddit, new_message: Dict
) -> Optional[str]:
    message = new_message["message"]
    body = new_message["body"]
    context = new_message["context"]
    author = new_message["author"]
    submission_id = new_message["submission_id"]

    permissions_needed = {"admins", "moderators"}
    user_permissions = get_permissions(users, author)

    to_subscribe = body.split(" ")[1]
    if to_subscribe.startswith("u/"):
        to_subscribe = to_subscribe[len("u/") :]

    if not permissions_needed.intersection(user_permissions):
        logging.info(
            f"!subother {to_subscribe} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Insufficent Permission | Has: {user_permissions} Needs one of: {permissions_needed}"
        )
        return None

    try:
        reddit.redditor(to_subscribe).id
        users["subscribers"].append(to_subscribe)
        utils.save_json((script_dir / "users.json"), users)
        message.reply(f"u/{to_subscribe} has been subscribed. Use !unsubscribe to unsubscribe")
        logging.info(
            f"!subother {to_subscribe} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | u/{to_subscribe} has been subscribed."
        )
        return "users"
    except NotFound:
        message.reply(f"u/{to_subscribe} not found.")
        logging.info(
            f"!subother {to_subscribe} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | u/{to_subscribe} not found."
        )
        return None


def unsubother(script_dir: Path, users: Dict, new_message: Dict) -> Optional[str]:
    message = new_message["message"]
    body = new_message["body"]
    context = new_message["context"]
    author = new_message["author"]
    submission_id = new_message["submission_id"]

    permissions_needed = {"admins", "moderators"}
    user_permissions = get_permissions(users, author)

    to_unsubscribe = body.split(" ")[1]

    if to_unsubscribe.startswith("u/"):
        to_unsubscribe = to_unsubscribe[len("u/") :]

    if not permissions_needed.intersection(user_permissions):
        logging.info(
            f"!unsubother {to_unsubscribe} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Insufficent Permission | Has: {user_permissions} Needs one of: {permissions_needed}"
        )
        return None

    if to_unsubscribe in users["subscribers"]:
        users["subscribers"].remove(to_unsubscribe)
        utils.save_json((script_dir / "users.json"), users)
        message.reply(f"u/{to_unsubscribe} has been unsubscribed.")
        logging.info(
            f"!unsubother {to_unsubscribe} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | u/{to_unsubscribe} has been unsubscribed."
        )
        return "users"
    else:
        message.reply(f"u/{to_unsubscribe} was not previously subscribed.")
        logging.info(
            f"!unsubother {to_unsubscribe} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | u/{to_unsubscribe} was not subscribed."
        )
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
    context = new_message["context"]
    author = new_message["author"]
    submission_id = new_message["submission_id"]

    permissions_needed = {"admins", "moderators"}
    user_permissions = get_permissions(users, author)

    to_monitor = body.split(" ")[1]

    if not permissions_needed.intersection(user_permissions):
        logging.info(
            f"!monitor {to_monitor} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Insufficent Permission | Has: {user_permissions} Needs one of: {permissions_needed}"
        )
        return None

    submission_to_monitor = reddit.submission(to_monitor)

    try:
        submission_to_monitor.allow_live_comments
        if to_monitor not in monitored_streams:
            monitored_streams[to_monitor] = None
            utils.save_json(script_dir / "monitored_streams.json", monitored_streams)

            message.reply(f"{to_monitor} is now being monitored")
            logging.info(
                f"!monitor {to_monitor} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Stream {to_monitor} is now being monitored."
            )
            return "monitored_streams"
        else:
            message.reply(f"{to_monitor} already being monitored")
            logging.info(
                f"!monitor {to_monitor} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Stream {to_monitor} was already being monitored."
            )
            return None
    except AttributeError:
        if to_monitor not in monitored_posts:
            monitored_posts[to_monitor] = len(submission_to_monitor.comments.list())
            utils.save_json(script_dir / "monitored_posts.json", monitored_posts)

            message.reply(f"{to_monitor} is now being monitored")
            logging.info(
                f"!monitor {to_monitor} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Post {to_monitor} is now being monitored."
            )
            return "monitored_posts"
        else:
            message.reply(f"{to_monitor} already being monitored")
            logging.info(
                f"!monitor {to_monitor} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Post {to_monitor} was already being monitored."
            )
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

    permissions_needed = {"admins", "moderators"}
    user_permissions = get_permissions(users, author)

    if not permissions_needed.intersection(user_permissions):
        logging.info(
            f"!end used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Insufficent Permission | Has: {user_permissions} Needs one of: {permissions_needed}"
        )
        return None

    if context == "stream":
        if submission_id in monitored_streams:
            monitored_streams.pop(submission_id)
            utils.save_json(script_dir / "monitored_streams.json", monitored_streams)

            message.reply(f"{submission_id} is no longer being monitored")
            logging.info(
                f"!end used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Stream has been unmonitored."
            )
            return "monitored_streams"
        else:
            message.reply(f"{submission_id} was not being monitored")
            logging.info(
                f"!monitor used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Stream was not monitored."
            )
            return None

    elif context == "inbox":
        to_unmonitor = body.split(" ")[1]

        submission_to_unmonitor = reddit.submission(to_unmonitor)

        try:
            submission_to_unmonitor.allow_live_comments
            if to_unmonitor in monitored_streams:
                monitored_streams.pop(to_unmonitor)
                utils.save_json(script_dir / "monitored_streams.json", monitored_streams)

                message.reply(f"{to_unmonitor} is no longer being monitored")
                logging.info(
                    f"!end {to_unmonitor} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Stream {to_unmonitor} has been unmonitored."
                )
                return "monitored_streams"
            else:
                message.reply(f"{to_unmonitor} was not being monitored")
                logging.info(
                    f"!end {to_unmonitor} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Stream {to_unmonitor} was not monitored."
                )
                return None
        except AttributeError:
            if to_unmonitor in monitored_posts:
                monitored_posts.pop(to_unmonitor)
                utils.save_json(script_dir / "monitored_posts.json", monitored_posts)
                message.reply(f"{to_unmonitor} is no longer being monitored")
                logging.info(
                    f"!end {to_unmonitor} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Post {to_unmonitor} has been unmonitored."
                )
                return "monitored_posts"
            else:
                message.reply(f"{to_unmonitor} was not being monitored")
                logging.info(
                    f"!end {to_unmonitor} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Post {to_unmonitor} was not monitored."
                )
                return None

    else:
        return None


def reload_commands(users: Dict, new_message: Dict):
    context = new_message["context"]
    body = new_message["body"]
    author = new_message["author"]
    submission_id = new_message["submission_id"]

    permissions_needed = {"admins"}
    user_permissions = get_permissions(users, author)

    if not permissions_needed.intersection(user_permissions):
        logging.info(
            f"!reload_commands used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Insufficent Permission | Has: {user_permissions} Needs one of: {permissions_needed}"
        )
        return None

    new_message["message"].reply("Commands queued to reload.")

    logging.info(
        f"!reload commands used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Queuing reload commands."
    )
    return "commands"


def basic_commands_func(user_dict: Dict, this_command: Dict, new_message: Dict):
    message = new_message["message"]
    context = new_message["context"]
    body = new_message["body"]
    author = new_message["author"]
    submission_id = new_message["submission_id"]

    contexts_needed = this_command["context"]
    if not "any" in contexts_needed:
        if not context in contexts_needed:
            logging.info(
                f"{body.lower()} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Disallowed Context | Has: {context} Needs one of: {contexts_needed}"
            )
            return

    permissions_needed = this_command["permissions"]
    if not "any" in permissions_needed:
        user_permissions = get_permissions(user_dict, author)
        if not permissions_needed.intersection(user_permissions):
            logging.info(
                f"{body.lower()} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Insufficent Permission | Has: {user_permissions} Needs one of: {permissions_needed}"
            )
            return

    reply_message = this_command["message"]
    message.reply(reply_message)
    logging.info(
        f"{body.lower()} used by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Replied: {reply_message}"
    )


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

    elif message_body_lower == "!reload commands":
        return reload_commands(users, new_message)

    return None


def check_message(
    script_dir: Path,
    basic_commands: Dict,
    users: Dict,
    reddit: praw.Reddit,
    monitored_streams: Dict,
    monitored_posts: Dict,
    new_message: Dict,
):
    message = new_message["message"]
    body = new_message["body"]
    author = new_message["author"]
    context = new_message["context"]
    submission_id = new_message["submission_id"]
    message_body_lower = body.lower()

    message_length = len(message_body_lower)
    if message_length > 30:
        logging.info(
            f"Long message ({message_length} characters) sent by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | Ignored due to message length."
        )
        return None

    elif message_body_lower in basic_commands:
        this_command = basic_commands[message_body_lower]
        basic_commands_func(users, this_command, new_message)
        return None

    else:
        return advanced_commands(
            script_dir, users, reddit, monitored_streams, monitored_posts, new_message
        )

    logging.info(
        f"{body} sent by u/{author} in {context}{' at' + submission_id if submission_id is not None else ''} | No command found."
    )
    return None