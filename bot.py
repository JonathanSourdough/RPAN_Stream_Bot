from typing import Optional, Union, Dict, List, Tuple, Iterator
from importlib import reload
from pathlib import Path
import logging
import time
import json

import praw
import prawcore
import websocket
import requests
import discord_webhook

import utils
import commands


class Bot:
    def __init__(self, script_dir: Path, config_dir: Path, secrets):
        self.script_dir = script_dir
        self.config_dir = config_dir

        self.secrets = secrets
        self.users = utils.load_json(self.config_dir / "users.json")
        self.basic_commands = utils.load_json(self.config_dir / "basic_commands.json")
        self.monitored_streams = utils.load_json(self.config_dir / "monitored_streams.json")
        self.monitored_posts = utils.load_json(self.config_dir / "monitored_posts.json")

        self.commands = commands.Commands(self)

        self.webhook = discord_webhook.DiscordWebhook(url=self.secrets["webhooks"]["announcements"])

        logger.debug("Starting chrome webdriver")
        self.webdriver = utils.launch_chrome(self.script_dir / "other" / "chromedriver")
        self.webdriver_connected = None

        logger.debug(f"Initializing praw")
        self.reddit = praw.Reddit(
            username=self.secrets["user_name"],
            password=self.secrets["user_password"],
            client_id=self.secrets["app_id"],
            client_secret=self.secrets["app_secret"],
            user_agent=self.secrets["user_agent"],
        )

        u_jcrayz = self.reddit.redditor("JCrayZ")
        self.monitored_subreddits = ("RedditSessions",)

        logger.debug(f"Adding submission/inbox streams")
        self.open_feed_streams = []
        self.open_feed_streams.append(
            {
                "stream": u_jcrayz.stream.submissions(pause_after=0, skip_existing=True),
                "source": u_jcrayz,
            }
        )
        self.open_feed_streams.append(
            {
                "stream": self.reddit.inbox.stream(pause_after=0, skip_existing=True),
                "source": self.reddit.inbox,
            }
        )
        self.websockets_dict = {}

    def check_update(self, update: Optional[str], mode=Optional[str]) -> None:
        if update == None or mode == None:
            return

        if mode == "load":
            logger.info(f"Loading {update}")
            if update == "commands":
                basic_commands = utils.load_json(self.config_dir / "basic_commands.json")
                global commands
                commands = reload(commands)
                self.commands = commands.Commands(self)
            elif update == "users":
                self.users = utils.load_json(self.config_dir / "users.json")
            elif update == "monitored_posts":
                self.monitored_posts = utils.load_json(self.config_dir / "monitored_posts.json")
            elif update == "monitored_streams":
                self.monitored_streams = utils.load_json(self.config_dir / "monitored_streams.json")
        elif mode == "save":
            logger.info(f"Saving {update}")
            if update == "users":
                utils.save_json(self.config_dir / "users.json", self.users)
            elif update == "monitored_posts":
                utils.save_json(self.config_dir / "monitored_posts.json", self.monitored_posts)
            elif update == "monitored_streams":
                utils.save_json(self.config_dir / "monitored_streams.json", self.monitored_streams)

    def check_redditor(self, open_stream: Dict):
        for submission in open_stream["stream"]:
            if submission is None:
                break
            if not submission.subreddit in self.monitored_subreddits:
                continue

            if submission.allow_live_comments:
                self.monitored_streams["monitored"][submission.id] = None

                utils.save_json(self.config_dir / "monitored_streams.json", self.monitored_streams)
                redditor_name = str(open_stream["source"])
                logger.info(
                    f"{redditor_name} has gone live on {submission.subreddit} at ({submission.shortlink}) notifing {len(self.users['subscribers'])} subscribers, and posting to discord.",
                )

                utils.webhook_post(
                    webhook=self.webhook,
                    plain_text_message="@here",
                    embeds=[
                        utils.discord_embed_builder(
                            embed_title=f"u/{redditor_name} has gone live on {submission.subreddit}!",
                            embed_description=f"[{submission.title}]({submission.shortlink})",
                            embed_image="https://cdn.discordapp.com/attachments/247673665624342529/783525595174141962/qgcqva8epe551.png",
                            author=open_stream["source"],
                            author_url=f"https://www.reddit.com/u/{redditor_name}",
                            author_icon="https://cdn.discordapp.com/attachments/247673665624342529/783533920951074846/unknown.png",
                        )
                    ],
                )

                for subscriber in self.users["subscribers"]:
                    self.reddit.redditor(subscriber).message(
                        subject=f"Hi {subscriber}, u/{redditor_name} is live on {submission.subreddit}!",
                        message=f"[{submission.title}]({submission.shortlink})",
                    )
                    logger.debug(f"Sent subscriber u/{subscriber} gone live message.")

    def check_inbox(self, inbox: Dict):
        for message in inbox["stream"]:
            if message is None:
                return
            update, mode = self.commands.check_message(
                {
                    "message": message,
                    "body": message.body,
                    "author": message.author.name,
                    "context": "inbox",
                    "submission_id": None,
                }
            )
            self.check_update(update, mode)

    def check_posts(self):
        for post_id, comment_count in self.monitored_posts.items():
            logger.debug(f"Checking post {post_id}")
            comment_list = self.reddit.submission(post_id).comments.list()
            comment_list.sort(key=lambda comment: comment.created)

            new_post_messages = 0
            for comment in comment_list[comment_count:]:
                if not post_id in self.monitored_posts:
                    logger.debug(f"{post_id} unmonitored mid-loop breaking loop.")
                    break
                author = comment.author.name
                if author == self.reddit.user.me().name:
                    continue

                update, mode = self.commands.check_message(
                    {
                        "message": comment,
                        "body": comment.body,
                        "author": author,
                        "context": "post",
                        "submission_id": comment.submission.id,
                    }
                )
                self.check_update(update, mode)
                new_post_messages += 1

            if new_post_messages and post_id in self.monitored_posts:
                self.monitored_posts[post_id] = len(comment_list)
                utils.save_json(self.config_dir / "monitored_posts.json", self.monitored_posts)

    def remove_old_sockets(self):
        for post_id in list(self.websockets_dict.keys()):
            if post_id not in self.monitored_streams["monitored"]:
                self.websockets_dict[post_id]["socket"].close()
                self.websockets_dict.pop(post_id)
                logger.info(f"Socket for {post_id} disconnected.")

    def add_new_sockets(self):
        def get_websocket_address(post_id: str) -> bool:
            logger.debug(f"Attempting to retrieving new socket address for {post_id}")
            submission = self.reddit.submission(post_id)
            response = requests.get(
                f"https://strapi.reddit.com/videos/{submission.fullname}",
                headers={
                    "user-agent": self.secrets["user_agent"],
                    "authorization": f"Bearer {self.reddit._authorized_core._authorizer.access_token}",
                    "Sec-Fetch-Mode": "no-cors",
                },
            )
            if not response.ok:
                return False

            websocket_address = response.json()["data"]["post"]["liveCommentsWebsocket"]
            if self.monitored_streams["monitored"][post_id] != websocket_address:
                self.monitored_streams["monitored"][post_id] = websocket_address
                return True

            logger.debug(
                f"Retrieved new socket address for {post_id}: {websocket_address} but is the same as saved.",
            )
            return False

        save_streams = False
        for post_id, websocket_address in self.monitored_streams["monitored"].items():
            if post_id not in self.websockets_dict:
                if websocket_address is None:
                    success = get_websocket_address(post_id)
                    if success:
                        logger.info(
                            f"Retrieved new socket address for {post_id}: {websocket_address}"
                        )
                        save_streams = True
                    else:
                        logger.warning(f"Failed retrieving new socket address. for {post_id}")
            else:
                this_websocket = self.websockets_dict[post_id]

                if this_websocket["socket"] is None:
                    if self.webdriver_connected is None:
                        if (
                            this_websocket["last_tried"] + this_websocket["timeout_length"]
                            < time.time()
                        ):
                            success = get_websocket_address(post_id)
                            if not success:
                                this_websocket["last_tried"] = time.time()
                                this_websocket["retry_count"] += 1
                                if this_websocket["retry_count"] == 2:
                                    logger.warning(
                                        f"Could not obtain new socket address for {post_id} after {this_websocket['retry_count']} retries. Timing out for {this_websocket['timeout_length']} seconds. Loading webdriver to page."
                                    )
                                    self.webdriver.get(f"http://redd.it/{post_id}")
                                    logger.info(f"Webdriver loaded to {post_id}")
                                elif this_websocket["retry_count"] in (6, 12, 20):
                                    logger.warning(
                                        f"Could not obtain new socket address for {post_id} after {this_websocket['retry_count']} retries. Timing out for {this_websocket['timeout_length']} seconds. Refreshing page."
                                    )
                                    self.webdriver.refresh()
                                    logger.info("Webdriver reloaded.")
                                elif this_websocket["retry_count"] == 30:
                                    self.parent.monitored_streams["unmonitored"][
                                        post_id
                                    ] = self.parent.monitored_streams["monitored"][post_id]
                                    self.parent.monitored_streams["monitored"].pop(post_id)
                                    self.webdriver.get("https://www.google.com")
                                    self.webdriver_connected = None
                                    logger.error(
                                        f"Could not obtain new socket address for {post_id} after {this_websocket['retry_count']} retries. Unmonitoring stream."
                                    )
                                else:
                                    logger.warning(
                                        f"Could not obtain new socket address for {post_id} after {this_websocket['retry_count']} retries. Timing out for {this_websocket['timeout_length']} seconds."
                                    )
                                continue
                            if self.webdriver_connected == post_id:
                                self.webdriver.get("https://www.google.com")
                                self.webdriver_connected = None
                            save_streams = True
                        else:
                            continue

            if post_id not in self.websockets_dict:
                this_websocket = {
                    "socket": None,
                    "timeout_length": 0,
                    "last_tried": time.time(),
                    "retry_count": 0,
                }

            websocket_address = self.monitored_streams["monitored"][post_id]
            try:
                if (this_websocket["socket"] is not None) or websocket_address is None:
                    continue

                this_websocket["socket"] = websocket.create_connection(websocket_address)
                this_websocket["socket"].settimeout(0.1)
                this_websocket["timeout_length"] = 0
                this_websocket["last_tried"] = time.time()
                this_websocket["retry_count"] = 0

                logger.info(f"Socket for {post_id} connected at {websocket_address}")

            except websocket.WebSocketBadStatusException as bad_status:
                this_websocket["socket"] = None
                this_websocket["timeout_length"] = 30
                this_websocket["last_tried"] = time.time()
                this_websocket["retry_count"] = 0

                logger.warning(
                    f"Socket for {post_id} at {websocket_address} could not connect, error {bad_status.status_code}. Timing out for {this_websocket['timeout_length']} seconds."
                )

            self.websockets_dict[post_id] = this_websocket

        if save_streams:
            utils.save_json(self.config_dir / "monitored_streams.json", self.monitored_streams)

    def check_sockets(self):
        for post_id, this_websocket in self.websockets_dict.items():
            if this_websocket["socket"] is None:
                continue

            logger.debug(f"Checking socket for {post_id}")
            socket_empty = False
            while not socket_empty:
                try:
                    socket_json = this_websocket["socket"].recv()
                    socket_data = json.loads(socket_json)
                    if not socket_data["type"] == "new_comment":
                        continue

                    author = socket_data["payload"]["author"]

                    if author == self.reddit.user.me().name:
                        continue

                    update, mode = self.commands.check_message(
                        {
                            "message": self.reddit.comment(socket_data["payload"]["_id36"]),
                            "body": socket_data["payload"]["body"],
                            "author": author,
                            "context": "stream",
                            "submission_id": socket_data["payload"]["link_id"].split("_")[1],
                        }
                    )
                    self.check_update(update, mode)

                except websocket.WebSocketTimeoutException:
                    logger.debug(f"End of socket messages from {post_id}")
                    socket_empty = True
                except Exception as e:
                    # TODO figure out how exactly reddit disconnects the socket
                    logger.error(f"Socket for post {post_id} excepted {e}")
                    socket_empty = True

    def run(self):
        logger.info(f"Starting bot loop")
        while True:
            new_messages = []

            for open_stream in self.open_feed_streams:
                logger.debug(f"Checking praw stream {open_stream['source']}")
                # Check for new rpan stream
                try:
                    if type(open_stream["source"]) == praw.models.Redditor:
                        self.check_redditor(open_stream)

                    # Check for new inbox messages
                    elif type(open_stream["source"]) == praw.models.inbox.Inbox:
                        self.check_inbox(open_stream)
                except prawcore.exceptions.ServerError:
                    logger.error(
                        f"Reddit feed stream for {open_stream['source']} excepted {e}, skipping and continuing."
                    )

            self.check_posts()

            self.add_new_sockets()
            self.remove_old_sockets()
            self.check_sockets()

    def run_with_respawn(self):
        while True:
            try:
                self.run()
            except praw.exceptions.RedditAPIException as api_exception:
                errors = {error.error_type: error.message for error in api_exception.items}
                if "RATELIMIT" in errors:
                    logger.error(f"Rate Limit hit! Exception message: {errors['RATELIMIT']}")
                    sleep = 0
                    if ("minute" in errors["RATELIMIT"]) or ("minutes" in errors["RATELIMIT"]):
                        sleep = int(errors["RATELIMIT"].split(" ")[-2]) * 60 + 5
                    elif ("second" in errors["RATELIMIT"]) or ("seconds" in errors["RATELIMIT"]):
                        sleep = int(errors["RATELIMIT"].split(" ")[-2])
                    elif ("hour" in errors["RATELIMIT"]) or ("hours" in errors["RATELIMIT"]):
                        sleep = int(int(errors["RATELIMIT"].split(" ")[-2]) * 3600 + 60)

                    logger.warning(f"sleeping for {sleep} seconds")
                    time.sleep(sleep)


class UTC_Formatter(logging.Formatter):
    converter = time.gmtime


class DiscordHandler(logging.Handler):
    def __init__(self, webhooks):
        logging.Handler.__init__(self)
        self.webhook = discord_webhook.DiscordWebhook(webhooks)

    def emit(self, record):
        try:
            msg = self.format(record)
            if record.levelno in (logging.WARN, logging.INFO):
                utils.webhook_post(self.webhook, f"`{msg}`")
            if record.levelno in (logging.ERROR, logging.CRITICAL):
                utils.webhook_post(self.webhook, f"<@122165502847090698> `{msg}`")
        except Exception:
            self.handleError(record)


if __name__ == "__main__":
    script_dir = Path(__file__).resolve().parent
    config_dir = script_dir / "config"
    secrets = utils.load_json(config_dir / "secrets.json")

    # setup logging
    logger = logging.getLogger("bot")
    logger.setLevel(logging.INFO)
    formatter = UTC_Formatter(
        fmt="%(levelname)s:[%(asctime)s] > %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z"
    )

    filehandler = logging.FileHandler("bot.log")
    # filehandler.setLevel(logging.INFO)
    filehandler.setFormatter(formatter)
    logger.addHandler(filehandler)

    consolehandler = logging.StreamHandler()
    # consolehandler.setLevel(logging.INFO)
    consolehandler.setFormatter(formatter)
    logger.addHandler(consolehandler)

    discord_handler = DiscordHandler(secrets["webhooks"]["errors"])
    # discord_handler.setLevel(logging.INFO)
    discord_handler.setFormatter(formatter)
    logger.addHandler(discord_handler)

    logger.info("Initializing bot")
    bot = Bot(script_dir, config_dir, secrets)
    try:
        bot.run_with_respawn()
    except Exception as e:
        bot.webdriver.close()
        bot.webdriver.quit()
        logger.critical(f"Program crashing out with '{e}' as exception")
