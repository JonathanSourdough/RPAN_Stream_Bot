from typing import Optional, Union, Dict, List
from importlib import reload
from pathlib import Path
import logging
import time
import json

import praw
import websocket
import timeout_decorator
import requests

import utils
import commands


@timeout_decorator.timeout(0.1)
def check_socket(sock):
    return sock.recv()


def main_loop():
    def check_update(update: str):
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

    secrets = utils.load_json(script_dir / "secrets.json")
    users = utils.load_json(script_dir / "users.json")
    basic_commands = utils.load_json(script_dir / "basic_commands.json")

    monitored_streams = utils.load_json(script_dir / "monitored_streams.json")
    monitored_posts = utils.load_json(script_dir / "monitored_posts.json")

    reddit = praw.Reddit(
        username=secrets["user_name"],
        password=secrets["user_password"],
        client_id=secrets["app_id"],
        client_secret=secrets["app_secret"],
        user_agent=secrets["user_agent"],
    )

    u_jcrayz = reddit.redditor("JCrayZ")
    monitored_subreddits = ["RedditSessions"]

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

    while True:
        new_messages = []
        for open_stream in open_streams:
            logging.debug(f"Checking praw stream {open_stream['source']}")
            # Check for new rpan stream
            if type(open_stream["source"]) == praw.models.Redditor:
                for submission in open_stream["stream"]:
                    if submission is None:
                        break
                    if not submission.subreddit in monitored_subreddits:
                        continue

                    if submission.allow_live_comments:
                        monitored_streams[submission.id] = None

                        utils.save_json(script_dir / "monitored_streams.json", monitored_streams)
                        logging.info(
                            f"{open_stream['source']} has gone live on {submission.subreddit} at ({submission.shortlink}) notifing {len(users['subscribers'])} subscribers."
                        )

                        for subscriber in users["subscribers"]:
                            reddit.redditor(subscriber).message(
                                f"Hi {subscriber}, {open_stream['source']} is live on {submission.subreddit}!",
                                f"[{submission.title}]({submission.shortlink})",
                            )
                            logging.debug(f"Sent subscriber {subscriber} gone live message.")

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
            logging.debug(f"Checking post {post_id}")
            post_messages = []
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
            logging.debug(f"{len(new_post_messages)} new comments at {post_id}")

            if new_post_messages:
                monitored_posts[post_id] = len(comment_list)
                save_posts = True

        if save_posts:
            utils.save_json(script_dir / "monitored_posts.json", monitored_posts)

        # add new sockets
        save_streams = False
        for post_id, web_socket_link in monitored_streams.items():
            if post_id not in open_websockets:
                logging.debug(f"Attempting to connect new socket for {post_id}")
                submission = reddit.submission(post_id)
                if web_socket_link is None:
                    response = requests.get(
                        f"https://strapi.reddit.com/videos/{submission.fullname}",
                        headers={
                            "user-agent": secrets["user_agent"],
                            "authorization": f"Bearer {reddit._authorized_core._authorizer.access_token}",
                        },
                    )
                    if not response.ok:
                        logging.warning(f"Failed connecting new socket for {post_id}")
                        continue

                    websocket_address = response.json()["data"]["post"]["liveCommentsWebsocket"]
                    if monitored_streams[post_id] != websocket_address:
                        monitored_streams[post_id] = websocket_address
                        save_streams = True

                open_websockets[post_id] = websocket.create_connection(websocket_address)
                logging.debug(f"Socket for {post_id} connected at {websocket_address}")
                # reddit.submission(post_id).reply("Has joined the chat.")

        if save_streams:
            utils.save_json(script_dir / "monitored_streams.json", monitored_streams)

        # remove old sockets
        for post_id in list(open_websockets.keys()):
            if post_id not in monitored_streams:
                # reddit.submission(post_id).reply("Has left the chat.")
                open_websockets[post_id].close()
                open_websockets.pop(post_id)
                logging.debug(f"Socket for {post_id} disconnected.")

        # check sockets
        for post_id, open_websocket in open_websockets.items():
            logging.debug(f"Checking socket for {post_id}")
            socket_empty = False
            while not socket_empty:
                try:
                    socket_json = check_socket(open_websocket)
                    socket_data = json.loads(socket_json)
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

                except timeout_decorator.timeout_decorator.TimeoutError:
                    logging.debug(f"End of socket messages from {post_id}")
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


if __name__ == "__main__":
    logging.basicConfig(
        filename="bot.log", format="%(levelname)s:[%(levelname)s] > %(message)s", level=logging.INFO
    )
    logging.info("Starting bot")
    while True:
        try:
            main_loop()
        except praw.exceptions.RedditAPIException as e:
            errors = {error.error_type: error.message for error in e.items}
            if "RATELIMIT" in errors:
                logging.error(f"Rate Limit hit! Exception message: {errors['RATELIMIT']}")
                sleep = 0
                if ("minute" in errors["RATELIMIT"]) or ("minutes" in errors["RATELIMIT"]):
                    sleep = int(errors["RATELIMIT"].split(" ")[-2]) * 60 + 5
                elif ("second" in errors["RATELIMIT"]) or ("seconds" in errors["RATELIMIT"]):
                    sleep = int(errors["RATELIMIT"].split(" ")[-2])
                elif ("hour" in errors["RATELIMIT"]) or ("hours" in errors["RATELIMIT"]):
                    sleep = int(int(errors["RATELIMIT"].split(" ")[-2]) * 3600 + 60)

                logging.warning("sleeping for", sleep, "seconds")
                time.sleep(sleep)
