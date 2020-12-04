from typing import Optional, Dict, List, Set, Tuple
from pathlib import Path
import logging

from prawcore import NotFound
import praw

import utils

logger = logging.getLogger("bot.commands")


class Commands:
    def __init__(self, parent):
        self.parent = parent

    def log(
        self,
        command: str,
        author: str,
        context: str,
        submission_id: Optional[str],
        notices: Optional[List] = None,
        reply: Optional[str] = None,
        log_level: int = logging.INFO,
    ):
        _submission = " at " + submission_id if submission_id is not None else ""
        _notices = " | " + " | ".join(notices) if notices is not None else ""
        _reply = " | " + reply if reply is not None else ""
        logger.log(
            log_level, f"{command} sent by u/{author} in {context}{_submission}{_notices}{_reply}"
        )

    def check_permissions(
        self,
        access: Set,
        command: str,
        author: str,
        context: str,
        submission_id: Optional[str],
        log: bool = True,
    ) -> Tuple[bool, Set[str]]:

        user_permissions = set()
        for permission, user_names in self.parent.users.items():
            if author in user_names:
                user_permissions.add(permission)

        if not "any" in access:
            if not access.intersection(user_permissions):
                if log:
                    notices = [
                        "Insufficent Permission",
                        f"Has: {user_permissions} Needs one of: {access}",
                    ]
                    self.log(command, author, context, submission_id, notices=notices)
                return False, user_permissions

        return True, user_permissions

    def subscribe(self, new_message: Dict) -> Tuple[Optional[str], Optional[str]]:
        message = new_message["message"]
        body = new_message["body"]
        context = new_message["context"]
        author = new_message["author"]
        submission_id = new_message["submission_id"]

        command = "!subscribe"

        access = {"admins", "moderators"}
        allowed, _ = self.check_permissions(access, command, author, context, submission_id)
        if not allowed:
            return None, None

        if author not in self.parent.users["subscribers"]:
            self.parent.users["subscribers"].append(author)

            reply = f"u/{author} has been subscribed. Use !unsubscribe to unsubscribe."
            message.reply(reply)
            self.log(command, author, context, submission_id, reply=reply)
            return "users", "save"
        else:
            reply = f"u/{author} was already subscribed."
            message.reply(reply)
            self.log(command, author, context, submission_id, reply=reply)
            return None, None

    def unsubscribe(self, new_message: Dict) -> Tuple[Optional[str], Optional[str]]:
        message = new_message["message"]
        body = new_message["body"]
        context = new_message["context"]
        author = new_message["author"]
        submission_id = new_message["submission_id"]

        command = "!unsubscribe"

        if author in self.parent.users["subscribers"]:
            self.parent.users["subscribers"].remove(author)

            reply = f"u/{author} has been unsubscribed."
            message.reply(reply)
            self.log(command, author, context, submission_id, reply=reply)
            return "users", "save"
        else:
            message.reply(reply)
            self.log(command, author, context, submission_id, reply=reply)
            return None, None

    def subother(self, new_message: Dict) -> Tuple[Optional[str], Optional[str]]:
        message = new_message["message"]
        body = new_message["body"]
        context = new_message["context"]
        author = new_message["author"]
        submission_id = new_message["submission_id"]

        to_subscribe = body.split(" ")[1]
        if to_subscribe.startswith("u/"):
            to_subscribe = to_subscribe[len("u/") :]

        command = f"!subother {to_subscribe}"

        access = {"admins", "moderators"}
        allowed, _ = self.check_permissions(access, command, author, context, submission_id)
        if not allowed:
            return None, None

        try:
            self.parent.reddit.redditor(to_subscribe).id
            if to_subscribe not in self.parent.users["subscribers"]:
                self.parent.users["subscribers"].append(to_subscribe)

                reply = f"u/{to_subscribe} has been subscribed. Use !unsubscribe to unsubscribe."
                message.reply(reply)
                self.log(command, author, context, submission_id, reply=reply)
                return "users", "save"
            else:
                reply = f"u/{to_subscribe} was already subscribed."
                message.reply(f"u/{to_subscribe} was already subscribed.")
                self.log(command, author, context, submission_id, reply=reply)
                return None, None
        except NotFound:
            reply = f"u/{to_subscribe} not found."
            message.reply(reply)
            self.log(command, author, context, submission_id, reply=reply)
            return None, None

    def unsubother(self, new_message: Dict) -> Tuple[Optional[str], Optional[str]]:
        message = new_message["message"]
        body = new_message["body"]
        context = new_message["context"]
        author = new_message["author"]
        submission_id = new_message["submission_id"]

        to_unsubscribe = body.split(" ")[1]
        if to_unsubscribe.startswith("u/"):
            to_unsubscribe = to_unsubscribe[len("u/") :]

        command = f"!unsubother {to_unsubscribe}"

        access = {"admins", "moderators"}
        allowed, _ = self.check_permissions(access, command, author, context, submission_id)
        if not allowed:
            return None, None

        if to_unsubscribe in self.parent.users["subscribers"]:
            self.parent.users["subscribers"].remove(to_unsubscribe)

            reply = f"u/{to_unsubscribe} has been unsubscribed."
            message.reply(reply)
            self.log(command, author, context, submission_id, reply=reply)
            return "users", "save"
        else:
            reply = f"u/{to_unsubscribe} was not previously subscribed."
            message.reply(reply)
            self.log(command, author, context, submission_id, reply=reply)
            return None, None

    def monitor(self, new_message: Dict) -> Tuple[Optional[str], Optional[str]]:
        message = new_message["message"]
        body = new_message["body"]
        context = new_message["context"]
        author = new_message["author"]
        submission_id = new_message["submission_id"]

        to_monitor = body.split(" ")[1]

        command = f"!monitor {to_monitor}"

        access = {"admins", "moderators"}
        allowed, _ = self.check_permissions(access, command, author, context, submission_id)
        if not allowed:
            return None, None

        submission = self.parent.reddit.submission(to_monitor)

        try:
            submission.allow_live_comments
            if to_monitor not in self.parent.monitored_streams["monitored"]:
                if to_monitor in self.parent.monitored_streams["unmonitored"]:
                    self.parent.monitored_streams["monitored"][
                        to_monitor
                    ] = self.parent.monitored_streams["unmonitored"][to_monitor]
                    self.parent.monitored_streams["unmonitored"].pop(to_monitor)
                else:
                    self.parent.monitored_streams["monitored"][to_monitor] = None

                reply = f"Stream {to_monitor} is now being monitored."
                message.reply(reply)
                self.log(command, author, context, submission_id, reply=reply)
                return "monitored_streams", "save"
            else:
                reply = f"Stream {to_monitor} already being monitored."
                message.reply(reply)
                self.log(command, author, context, submission_id, reply=reply)
                return None, None

        except AttributeError:
            if to_monitor not in self.parent.monitored_posts:
                self.parent.monitored_posts[to_monitor] = len(submission.comments.list())

                reply = f"Post {to_monitor} is now being monitored."
                message.reply(reply)
                self.log(command, author, context, submission_id, reply=reply)
                return "monitored_posts", "save"
            else:
                reply = f"Post {to_monitor} already being monitored."
                message.reply(reply)
                self.log(command, author, context, submission_id, reply=reply)
                return None, None

    def end(self, new_message: Dict) -> Tuple[Optional[str], Optional[str]]:
        message = new_message["message"]
        body = new_message["body"]
        context = new_message["context"]
        author = new_message["author"]
        submission_id = new_message["submission_id"]

        access = {"admins", "moderators"}

        if context in ["stream", "post"]:
            command = "!end"

            allowed, _ = self.check_permissions(access, command, author, context, submission_id)
            if not allowed:
                return None, None

            if submission_id in self.parent.monitored_streams["monitored"]:
                self.parent.monitored_streams["unmonitored"][
                    submission_id
                ] = self.parent.monitored_streams["monitored"][submission_id]
                self.parent.monitored_streams["monitored"].pop(submission_id)

                reply = f"{context.title()} {submission_id} is no longer being monitored."
                message.reply(reply)
                self.log(command, author, context, submission_id, reply=reply)
                return "monitored_streams", "save"
            else:
                reply = f"{context.title()} {submission_id} was not being monitored."
                message.reply(reply)
                self.log(command, author, context, submission_id, reply=reply)
                return None, None

        elif context == "inbox":
            to_unmonitor = body.split(" ")[1]

            command = f"!end {to_unmonitor}"

            allowed, _ = self.check_permissions(access, command, author, context, submission_id)
            if not allowed:
                return None, None

            submission = self.parent.reddit.submission(to_unmonitor)
            try:
                submission.allow_live_comments
                if to_unmonitor in self.parent.monitored_streams["monitored"]:
                    self.parent.monitored_streams["unmonitored"][
                        to_unmonitor
                    ] = self.parent.monitored_streams["monitored"][to_unmonitor]
                    self.parent.monitored_streams["monitored"].pop(to_unmonitor)

                    reply = f"Stream {to_unmonitor} is no longer being monitored."
                    message.reply(reply)
                    self.log(command, author, context, submission_id, reply=reply)
                    return "monitored_streams", "save"
                else:
                    reply = f"Stream {to_unmonitor} was not being monitored."
                    message.reply(reply)
                    self.log(command, author, context, submission_id, reply=reply)
                    return None, None

            except AttributeError:
                if to_unmonitor in self.parent.monitored_posts:
                    self.parent.monitored_posts.pop(to_unmonitor)

                    reply = f"Post {to_unmonitor} is no longer being monitored."
                    message.reply(reply)
                    self.log(command, author, context, submission_id, reply=reply)
                    return "monitored_posts", "save"
                else:
                    reply = f"Post {to_unmonitor} was not being monitored."
                    message.reply(reply)
                    self.log(command, author, context, submission_id, reply=reply)

                    return None, None

        else:
            return None, None

    def reload_commands(self, new_message: Dict) -> Tuple[Optional[str], Optional[str]]:
        context = new_message["context"]
        body = new_message["body"]
        author = new_message["author"]
        submission_id = new_message["submission_id"]

        command = "!reload commands"

        access = {"admins"}
        allowed, _ = self.check_permissions(access, command, author, context, submission_id)
        if not allowed:
            return None, None

        reply = "Commands queued to reload."
        new_message["message"].reply(reply)
        self.log(command, author, context, submission_id, reply=reply)
        return "commands", "load"

    def basic_commands_func(self, this_command: Dict, new_message: Dict):
        message = new_message["message"]
        context = new_message["context"]
        body = new_message["body"]
        author = new_message["author"]
        submission_id = new_message["submission_id"]

        command = body.lower()

        contexts_needed = this_command["context"]
        if not "any" in contexts_needed:
            if not context in contexts_needed:
                notices = [
                    "Disallowed Context",
                    f"Has: '{context}' Needs one of: {contexts_needed}",
                ]
                self.log(command, author, context, submission_id, notices)
                return

        access = set(this_command["permissions"])
        allowed, _ = self.check_permissions(access, command, author, context, submission_id)
        if not allowed:
            return

        reply_message = this_command["message"]
        message.reply(reply_message)
        self.log(command, author, context, submission_id, reply=reply_message)

    def check_message(self, new_message: Dict):
        message = new_message["message"]
        author = new_message["author"]
        context = new_message["context"]
        submission_id = new_message["submission_id"]
        message_body_lower = new_message["body"].lower()

        message_length = len(message_body_lower)
        if message_length > 45:
            notices = [f"Ignored due to message length ({len(message_body_lower)})."]
            self.log(
                message_body_lower, author, context, submission_id, notices, None, logging.DEBUG
            )
            return None, None

        elif message_body_lower in self.parent.basic_commands:
            this_command = self.parent.basic_commands[message_body_lower]
            self.basic_commands_func(this_command, new_message)
            return None, None

        elif message_body_lower == "!subscribe":
            return self.subscribe(new_message)

        elif message_body_lower == "!unsubscribe":
            return self.unsubscribe(new_message)

        elif "!subother" in message_body_lower:
            return self.subother(new_message)

        elif "!unsubother" in message_body_lower:
            return self.unsubother(new_message)

        elif "!monitor" in message_body_lower:
            return self.monitor(new_message)

        elif "!end" in message_body_lower:
            return self.end(new_message)

        elif message_body_lower == "!reload commands":
            return self.reload_commands(new_message)

        notices = ["No command found."]
        self.log(message_body_lower, author, context, submission_id, notices, None, logging.DEBUG)
        return None, None