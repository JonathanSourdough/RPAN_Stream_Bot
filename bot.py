from typing import Optional, Union, Dict, List, Tuple
from importlib import reload
from pathlib import Path
import logging
import time
import json

import praw
import websocket
import requests
import discord_webhook

import utils
import commands


class Bot:
    def __init__(self):
        self.script_dir = Path(__file__).resolve().parent
        self.config_dir = self.script_dir / "config"

        self.secrets = utils.load_json(self.config_dir / "secrets.json")
        self.users = utils.load_json(self.config_dir / "users.json")
        self.basic_commands = utils.load_json(self.config_dir / "basic_commands.json")
        self.monitored_streams = utils.load_json(self.config_dir / "monitored_streams.json")
        self.monitored_posts = utils.load_json(self.config_dir / "monitored_posts.json")

        self.commands = commands.Commands(self)

        self.webhook = discord_webhook.DiscordWebhook(url=self.secrets["webhooks"])

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
                self.commands = commands.Commands
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
                logger.warning(f"Failed retrieving new socket address. for {post_id}")
                return False

            websocket_address = response.json()["data"]["post"]["liveCommentsWebsocket"]
            if self.monitored_streams["monitored"][post_id] != websocket_address:
                self.monitored_streams["monitored"][post_id] = websocket_address
                logger.info(f"Retrieved new socket address for {post_id}: {websocket_address}")
                return True

            logger.debug(
                f"Retrieved new socket address for {post_id}: {websocket_address} but is the same as saved."
            )
            return False

        save_streams = False
        for post_id, websocket_address in self.monitored_streams["monitored"].items():
            if post_id not in self.websockets_dict:
                if websocket_address is None:
                    success = get_websocket_address(post_id)
                    if success:
                        save_streams = True
            else:
                this_websocket = self.websockets_dict[post_id]

                if this_websocket["socket"] is None:
                    if this_websocket["timeout_length"] >= 60:
                        if self.webdriver_connected is None:
                            logger.info(f"Loading webdriver to {post_id}")
                            self.webdriver.get(f"http://redd.it/{post_id}")
                            logger.info(f"Webdriver loaded to {post_id}")
                            self.webdriver_connected = post_id
                    if (
                        this_websocket["last_tried"] + this_websocket["timeout_length"]
                        < time.time()
                    ):
                        success = get_websocket_address(post_id)
                        if not success:
                            this_websocket["last_tried"] = time.time()
                            if this_websocket["timeout_length"] < 60:
                                this_websocket["timeout_length"] += 30
                            logger.warning(
                                f"Could not obtain new socket address for {post_id}. Timing out for {this_websocket['timeout_length']}"
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
                }

            websocket_address = self.monitored_streams["monitored"][post_id]
            try:
                if (this_websocket["socket"] is not None) or websocket_address is None:
                    continue

                this_websocket["socket"] = websocket.create_connection(websocket_address)
                this_websocket["socket"].settimeout(0.1)
                this_websocket["timeout_length"] = 0
                this_websocket["last_tried"] = time.time()

                logger.info(f"Socket for {post_id} connected at {websocket_address}")

            except websocket.WebSocketBadStatusException as bad_status:
                this_websocket["socket"] = None
                this_websocket["timeout_length"] = 30
                this_websocket["last_tried"] = time.time()

                logger.warning(
                    f"Socket for {post_id} at {websocket_address} could not connect, error {bad_status.status_code}. Increasing timeout to {this_websocket['timeout_length']}"
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

                    new_message = {
                        "message": self.reddit.comment(socket_data["payload"]["_id36"]),
                        "body": socket_data["payload"]["body"],
                        "author": author,
                        "context": "stream",
                        "submission_id": socket_data["payload"]["link_id"].split("_")[1],
                    }

                    update, mode = self.commands.check_message(new_message)
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
                if type(open_stream["source"]) == praw.models.Redditor:
                    for submission in open_stream["stream"]:
                        if submission is None:
                            break
                        if not submission.subreddit in self.monitored_subreddits:
                            continue

                        if submission.allow_live_comments:
                            self.monitored_streams["monitored"][submission.id] = None

                            utils.save_json(
                                self.config_dir / "monitored_streams.json", self.monitored_streams
                            )
                            logger.info(
                                f"{open_stream['source']} has gone live on {submission.subreddit} at ({submission.shortlink}) notifing {len(self.users['subscribers'])} subscribers."
                            )

                            embed = discord_webhook.DiscordEmbed(
                                title=f"u/{open_stream['source']} has gone live on {submission.subreddit}!",
                                description=f"[{submission.title}]({submission.shortlink})",
                            )
                            embed.set_author(
                                name=open_stream["source"],
                                url=f"https://www.reddit.com/u/{open_stream['source']}",
                            )
                            embed.author[
                                "icon_url"
                            ] = "https://cdn.discordapp.com/attachments/247673665624342529/783533920951074846/unknown.png"
                            embed.set_image(
                                url="https://cdn.discordapp.com/attachments/247673665624342529/783525595174141962/qgcqva8epe551.png"
                            )

                            self.webhook.set_content("@here")
                            self.webhook.add_embed(embed)
                            self.webhook.execute()
                            self.webhook.embeds = []
                            self.webhook.set_content("")

                            for subscriber in self.users["subscribers"]:
                                self.reddit.redditor(subscriber).message(
                                    f"Hi {subscriber}, u/{open_stream['source']} is live on {submission.subreddit}!",
                                    f"[{submission.title}]({submission.shortlink})",
                                )
                                logger.debug(f"Sent subscriber u/{subscriber} gone live message.")

                # Check for new inbox messages
                elif type(open_stream["source"]) == praw.models.inbox.Inbox:
                    for message in open_stream["stream"]:
                        if message is None:
                            break
                        new_messages.append(
                            {
                                "message": message,
                                "body": message.body,
                                "author": message.author.name,
                                "context": "inbox",
                                "submission_id": None,
                            }
                        )

            # check posts
            save_posts = False
            for post_id, comment_count in self.monitored_posts.items():
                logger.debug(f"Checking post {post_id}")
                new_post_messages = []
                comment_list = self.reddit.submission(post_id).comments.list()
                comment_list.sort(key=lambda comment: comment.created)

                for comment in comment_list[comment_count:]:
                    author = comment.author.name

                    if author == self.reddit.user.me().name:
                        continue

                    new_post_messages.append(
                        {
                            "message": comment,
                            "body": comment.body,
                            "author": author,
                            "context": "post",
                            "submission_id": comment.submission.id,
                        }
                    )

                new_messages += new_post_messages
                logger.debug(f"{len(new_post_messages)} new comments at {post_id}")

                if new_post_messages:
                    self.monitored_posts[post_id] = len(comment_list)
                    save_posts = True

            if save_posts:
                utils.save_json(self.config_dir / "monitored_posts.json", self.monitored_posts)

            self.add_new_sockets()
            self.remove_old_sockets()
            self.check_sockets()

            for new_message in new_messages:
                update, mode = self.commands.check_message(new_message)
                self.check_update(update, mode)

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


if __name__ == "__main__":
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

    logger.info("Initializing bot")
    bot = Bot()
    try:
        bot.run_with_respawn()
    except Exception as e:
        bot.webdriver.quit()
        logger.critical(f"Program crashing out with '{e}' as exception")
