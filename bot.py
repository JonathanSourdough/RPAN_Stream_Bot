from typing import Optional, Union, Dict, List
from importlib import reload
from pathlib import Path
import logging
import time
import json

import praw
import websocket
import requests

import utils
import commands


def get_websocket_address(
    script_dir: Path, secrets: Dict, monitored_streams: Dict, reddit: praw.Reddit, post_id: str
) -> bool:
    logger.debug(f"Attempting to retrieving new socket address for {post_id}")
    submission = reddit.submission(post_id)
    response = requests.get(
        f"https://strapi.reddit.com/videos/{submission.fullname}",
        headers={
            "user-agent": secrets["user_agent"],
            "authorization": f"Bearer {reddit._authorized_core._authorizer.access_token}",
            "Sec-Fetch-Mode": "no-cors",
        },
    )
    if not response.ok:
        logger.warning(f"Failed retrieving new socket address. for {post_id}")
        return False
    websocket_address = response.json()["data"]["post"]["liveCommentsWebsocket"]
    if monitored_streams["monitored"][post_id] != websocket_address:
        monitored_streams["monitored"][post_id] = websocket_address
        utils.save_json(script_dir / "monitored_streams.json", monitored_streams)
        logger.debug(f"Retrieved new socket address for {post_id}: {websocket_address}")
        return True

    logger.debug(
        f"Retrieved new socket address for {post_id}: {websocket_address} but is the same as saved."
    )
    return False


def main_loop():
    def check_update(update: str) -> None:
        if update == None:
            return

        logger.info(f"Updating {update}")
        if update == "commands":
            basic_commands = utils.load_json(script_dir / "basic_commands.json")
            global commands
            commands = reload(commands)
        elif update == "users":
            users = utils.load_json(script_dir / "users.json")
        elif update == "monitored_posts":
            monitored_posts = utils.load_json(script_dir / "monitored_posts.json")
        elif update == "monitored_streams":
            monitored_streams = utils.load_json(script_dir / "monitored_streams.json")

    script_dir = Path(__file__).resolve().parent

    logger.debug(f"Loading secrets/users/commands")
    secrets = utils.load_json(script_dir / "secrets.json")
    users = utils.load_json(script_dir / "users.json")
    basic_commands = utils.load_json(script_dir / "basic_commands.json")

    logger.debug(f"Loading monitored posts/streams")
    monitored_streams = utils.load_json(script_dir / "monitored_streams.json")
    monitored_posts = utils.load_json(script_dir / "monitored_posts.json")

    logger.debug(f"Initializing praw")
    reddit = praw.Reddit(
        username=secrets["user_name"],
        password=secrets["user_password"],
        client_id=secrets["app_id"],
        client_secret=secrets["app_secret"],
        user_agent=secrets["user_agent"],
    )

    u_jcrayz = reddit.redditor("JCrayZ")
    monitored_subreddits = ["RedditSessions"]

    logger.debug(f"Adding submission/inbox streams")
    open_streams = []
    open_streams.append(
        {
            "stream": u_jcrayz.stream.submissions(pause_after=0, skip_existing=True),
            "source": u_jcrayz,
        }
    )
    open_streams.append(
        {
            "stream": reddit.inbox.stream(pause_after=0, skip_existing=True),
            "source": reddit.inbox,
        }
    )
    open_websockets = {}

    logger.info(f"Starting bot loop")
    while True:
        new_messages = []
        for open_stream in open_streams:
            logger.debug(f"Checking praw stream {open_stream['source']}")
            # Check for new rpan stream
            if type(open_stream["source"]) == praw.models.Redditor:
                for submission in open_stream["stream"]:
                    if submission is None:
                        break
                    if not submission.subreddit in monitored_subreddits:
                        continue

                    if submission.allow_live_comments:
                        monitored_streams["monitored"][submission.id] = None

                        utils.save_json(script_dir / "monitored_streams.json", monitored_streams)
                        logger.info(
                            f"{open_stream['source']} has gone live on {submission.subreddit} at ({submission.shortlink}) notifing {len(users['subscribers'])} subscribers."
                        )

                        for subscriber in users["subscribers"]:
                            reddit.redditor(subscriber).message(
                                f"Hi {subscriber}, {open_stream['source']} is live on {submission.subreddit}!",
                                f"[{submission.title}]({submission.shortlink})",
                            )
                            logger.debug(f"Sent subscriber {subscriber} gone live message.")

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
        for post_id, comment_count in monitored_posts.items():
            logger.debug(f"Checking post {post_id}")
            new_post_messages = []
            comment_list = reddit.submission(post_id).comments.list()
            comment_list.sort(key=lambda comment: comment.created)

            for comment in comment_list[comment_count:]:
                author = comment.author.name

                if author == reddit.user.me().name:
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
                monitored_posts[post_id] = len(comment_list)
                save_posts = True

        if save_posts:
            utils.save_json(script_dir / "monitored_posts.json", monitored_posts)

        # add new sockets
        save_streams = False
        for post_id, websocket_address in monitored_streams["monitored"].items():
            if post_id not in open_websockets:
                if websocket_address is None:
                    if get_websocket_address(
                        script_dir, secrets, monitored_streams, reddit, post_id
                    ):
                        monitored_streams = utils.load_json(script_dir / "monitored_streams.json")
                    else:
                        continue
            else:
                if open_websockets[post_id]["socket"] is None:
                    if (
                        open_websockets[post_id]["last_tried"]
                        + open_websockets[post_id]["timeout_length"]
                        < time.time()
                    ):
                        if get_websocket_address(
                            script_dir, secrets, monitored_streams, reddit, post_id
                        ):
                            monitored_streams = utils.load_json(
                                script_dir / "monitored_streams.json"
                            )
                        else:
                            open_websockets[post_id]["last_tried"] = time.time()
                            open_websockets[post_id]["timeout_length"] *= 2
                            logger.warning(
                                f"Socket for {post_id} at {monitored_streams['monitored'][post_id]} could not connect, error 403. Increasing timeout to {open_websockets[post_id]['timeout_length']}"
                            )
                            continue
                    else:
                        continue
            try:
                if post_id not in open_websockets:
                    open_websockets[post_id] = {
                        "socket": None,
                        "timeout_length": 0,
                        "last_tried": time.time(),
                    }
                elif open_websockets[post_id]["socket"] is not None:
                    continue
                open_websockets[post_id]["socket"] = websocket.create_connection(
                    monitored_streams["monitored"][post_id]
                )
                logger.info(
                    f"Socket for {post_id} connected at {monitored_streams['monitored'][post_id]}"
                )
            except websocket.WebSocketBadStatusException as bad_status:
                if post_id not in open_websockets:
                    open_websockets[post_id] = {
                        "socket": None,
                        "timeout_length": 0,
                        "last_tried": time.time(),
                    }
                status_code = bad_status.status_code
                if status_code == "403":
                    open_websockets[post_id]["socket"] = None
                    if open_websockets[post_id]["timeout_length"] == 0:
                        open_websockets[post_id]["timeout_length"] = 30
                    else:
                        open_websockets[post_id]["timeout_length"] *= 2
                    open_websockets[post_id]["last_tried"] = time.time()
                    logger.warning(
                        f"Socket for {post_id} at {monitored_streams['monitored'][post_id]} could not connect, error 403. Increasing timeout to {open_websockets[post_id]['timeout_length']}"
                    )
                else:
                    open_websockets[post_id]["socket"] = None
                    if open_websockets[post_id]["timeout_length"] == 0:
                        open_websockets[post_id]["timeout_length"] = 30
                    else:
                        open_websockets[post_id]["timeout_length"] *= 2
                    open_websockets[post_id]["last_tried"] = time.time()
                    logger.warning(
                        f"Socket for {post_id} at {monitored_streams['monitored'][post_id]} could not connect, error {status_code}. Increasing timeout to {open_websockets[post_id]['timeout_length']}"
                    )
            # reddit.submission(post_id).reply("Has joined the chat.")

        if save_streams:
            utils.save_json(script_dir / "monitored_streams.json", monitored_streams)

        # remove old sockets
        for post_id in list(open_websockets.keys()):
            if (post_id not in monitored_streams["monitored"]) or (
                post_id in monitored_streams["unmonitored"]
            ):
                # reddit.submission(post_id).reply("Has left the chat.")
                open_websockets[post_id]["socket"].close()
                open_websockets.pop(post_id)
                logger.info(f"Socket for {post_id} disconnected.")

        # check sockets
        for post_id, open_websocket in open_websockets.items():
            if open_websocket["socket"] is None:
                continue

            logger.debug(f"Checking socket for {post_id}")
            socket_empty = False
            while not socket_empty:
                try:
                    socket_json = open_websocket["socket"].recv()
                    socket_data = json.loads(socket_json)
                    if not socket_data["type"] == "new_comment":
                        continue

                    author = socket_data["payload"]["author"]

                    if author == reddit.user.me().name:
                        continue

                    new_message = {
                        "message": reddit.comment(socket_data["payload"]["_id36"]),
                        "body": socket_data["payload"]["body"],
                        "author": author,
                        "context": "stream",
                        "submission_id": socket_data["payload"]["link_id"].split("_")[1],
                    }
                    update = None
                    update = commands.check_message(
                        script_dir,
                        basic_commands,
                        users,
                        reddit,
                        monitored_streams,
                        monitored_posts,
                        new_message,
                    )
                    if update is not None:
                        check_update(update)

                except websocket.WebSocketTimeoutException:
                    logger.debug(f"End of socket messages from {post_id}")
                    socket_empty = True
                except Exception as e:
                    logger.error(f"Socket for post {post_id} excepted {e}")
                    socket_empty = True

        for new_message in new_messages:
            update = None
            update = commands.check_message(
                script_dir,
                basic_commands,
                users,
                reddit,
                monitored_streams,
                monitored_posts,
                new_message,
            )
            if update is not None:
                check_update(update)


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
    while True:
        try:
            main_loop()
        except praw.exceptions.RedditAPIException as e:
            errors = {error.error_type: error.message for error in e.items}
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
