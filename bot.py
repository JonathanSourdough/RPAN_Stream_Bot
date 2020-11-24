from typing import Optional, Union, Dict, List
from pathlib import Path
from importlib import reload
import time
import json

import praw
import websocket
import timeout_decorator
import requests

import utils
import advanced_commands


@timeout_decorator.timeout(0.1)
def check_socket(sock):
    return sock.recv()


def main_loop():
    def print_time(print_context):
        if do_print_time:
            print(print_context, time.time() - start_time)

    do_print_time = True

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
        start_time = time.time()
        print("start")
        for open_stream in open_streams:
            # Check for new rpan stream
            if type(open_stream["source"]) == praw.models.Redditor:
                for submission in open_stream["stream"]:
                    print_time("checking streams:")
                    if submission is None:
                        break
                    if not submission.subreddit in monitored_subreddits:
                        continue

                    if submission.allow_live_comments:
                        monitored_streams[submission.id] = None

                        utils.save_json(script_dir / "monitored_streams.json", monitored_streams)

                    for subscriber in users["subscribers"]:
                        reddit.redditor(subscriber).message(
                            f"Hi {subscriber}, {open_stream['source']} is live on {submission.subreddit}!",
                            f"[{submission.title}]({submission.shortlink})",
                        )

                        print_time("subscribers:")
                        time.sleep(1)

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

                print_time("checked inbox:")

        # check posts
        save_posts = False
        for post_id, comment_count in monitored_posts.items():
            post_messages = []
            comment_list = reddit.submission(post_id).comments.list()
            comment_list.sort(key=lambda comment: comment.created)
            post_messages = [
                {
                    "message": comment,
                    "body": comment.body,
                    "author": comment.author.name,
                    "context": "post",
                    "submission_id": comment.submission.id,
                }
                for comment in comment_list[comment_count:]
            ]
            if post_messages:
                save_posts = True
            new_messages += post_messages
            monitored_posts[post_id] = len(comment_list)

        if save_posts:
            utils.save_json(script_dir / "monitored_posts.json", monitored_posts)

        print_time("posts checked:")

        # remove old sockets
        for post_id in list(open_websockets.keys()):
            if post_id not in monitored_streams:
                # reddit.submission(post_id).reply("Has left the chat.")
                open_websockets[post_id].close()
                open_websockets.pop(post_id)

        print_time("sockets removed:")

        # add sockets
        save_streams = False
        for post_id, web_socket_link in monitored_streams.items():
            if post_id not in open_websockets:
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
                        continue
                    monitored_streams[post_id] = response.json()["data"]["post"][
                        "liveCommentsWebsocket"
                    ]

                open_websockets[post_id] = websocket.create_connection(monitored_streams[post_id])
                save_streams = True
                # reddit.submission(post_id).reply("Has joined the chat.")

        if save_streams:
            utils.save_json(script_dir / "monitored_streams.json", monitored_streams)

        print_time("sockets added:")

        # check sockets
        for open_websocket in open_websockets.values():
            socket_empty = False
            while not socket_empty:
                try:
                    socket_json = check_socket(open_websocket)
                    socket_data = json.loads(socket_json)
                    new_messages.append(
                        {
                            "message": reddit.comment(socket_data["payload"]["_id36"]),
                            "body": socket_data["payload"]["body"],
                            "author": socket_data["payload"]["author"],
                            "context": "stream",
                            "submission_id": socket_data["payload"]["link_id"].split("_")[1],
                        }
                    )
                    print_time("socket:")
                except timeout_decorator.timeout_decorator.TimeoutError:
                    socket_empty = True

        print_time("sockets checked:")

        for new_message in new_messages:
            message = new_message["message"]
            body = new_message["body"]
            author = new_message["author"]
            context = new_message["context"]
            message_body_lower = body.lower()

            if author == reddit.user.me().name:
                continue

            elif message_body_lower in basic_commands:
                this_command = basic_commands[message_body_lower]

                if not "any" in this_command["context"]:
                    if not context in this_command["context"]:
                        continue

                for permission in this_command["permissions"]:
                    if permission == "any":
                        break
                    elif author in users[permission]:
                        break
                else:
                    continue

                message.reply(this_command["message"])

            elif message_body_lower == "!reload commands":
                basic_commands = utils.load_json(script_dir / "basic_commands.json")
                global advanced_commands
                advanced_commands = reload(advanced_commands)
                message.reply("Commands successfully reloaded.")

            else:
                update = advanced_commands.advanced_commands(
                    script_dir, users, reddit, monitored_streams, monitored_posts, new_message
                )

                if update == "users":
                    users = utils.load_json(script_dir / "users.json")
                elif update == "monitored_posts":
                    monitored_posts = utils.load_json(script_dir / "monitored_posts.json")
                elif update == "monitored_streams":
                    monitored_streams = utils.load_json(script_dir / "monitored_streams.json")

            print_time("commands:")
            time.sleep(1)


if __name__ == "__main__":
    while True:
        try:
            main_loop()
        except praw.exceptions.RedditAPIException as e:
            errors = {error.error_type: error.message for error in e.items}
            if "RATELIMIT" in errors:
                print()
                print("Error:", errors["RATELIMIT"])
                print()
                if ("minute" in errors["RATELIMIT"]) or ("minutes" in errors["RATELIMIT"]):
                    sleep = int(errors["RATELIMIT"].split(" ")[-2]) * 60 + 5
                    print("sleeping for:", sleep, "seconds")
                    time.sleep(sleep)
                elif ("second" in errors["RATELIMIT"]) or ("seconds" in errors["RATELIMIT"]):
                    sleep = int(errors["RATELIMIT"].split(" ")[-2])
                    print("sleeping for:", sleep, "seconds")
                    time.sleep(sleep)
                elif ("hour" in errors["RATELIMIT"]) or ("hours" in errors["RATELIMIT"]):
                    sleep = int(int(errors["RATELIMIT"].split(" ")[-2]) * 3600 + 60)
                    print("sleeping for:", sleep, "seconds")
                    time.sleep(sleep)
