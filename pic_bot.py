"""Grabs the latest, not yet sent post from a subreddit and sends it to the given telegram group."""

import argparse
import json
import pickle
import random
import re
import urllib.request

import telepot

# configuration
def get_config(filename='config.json'):
    """Reads a json config, identified by filename."""
    with open(filename) as config_file:
        data = json.load(config_file)
        return data

# maintain and store already sent posts
def store_latest_posts(data, filename='posts.pickle'):
    """Stores the given data as dump in the file identified by filename."""
    with open(filename, 'wb') as handle:
        pickle.dump(data, handle)

def get_latest_posts(filename='posts.pickle'):
    """Loads and returns a stored dump identified by filename."""
    try:
        with open(filename, 'rb') as handle:
            data = pickle.load(handle)
            return data
    except FileNotFoundError:
        return {}

def update_latest_posts(latest_posts, subreddit, post_id):
    """Updates the given dictionary with the key subreddit and the value post_id."""
    if subreddit in latest_posts:
        latest_posts[subreddit].append(post_id)
    else:
        latest_posts[subreddit] = [post_id]
    return latest_posts

def crop_latest_posts(latest_posts, max_length=10):
    """Reduces the length of the latest posts to the given max_length."""
    for key in latest_posts:
        latest_posts[key] = latest_posts[key][-max_length:]
    return latest_posts

def is_post_in_latest_posts(latest_posts, subreddit, post_id):
    """Checks if the given value is in the given key of the given dictionary."""
    if subreddit in latest_posts:
        return post_id in latest_posts[subreddit]
    return False

# convenience getter methods
def get_bot(token):
    """Returns a telepot Bot object, identified by parameter token"""
    return telepot.Bot(token)

def get_subreddit_posts(subreddit):
    """Returns the latest posts of the given subreddit"""
    url = None

    try:
        req = urllib.request.Request(
            'https://www.reddit.com/r/' + str(subreddit) + '/new.json?sort=new',
            data=None,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36' # pylint: disable=line-too-long
                })
        url = urllib.request.urlopen(req).read().decode('utf-8')
    except urllib.error.HTTPError as err:
        print(err)
    return url

def get_post(posts_json, i):
    """Returns the post and its media type at index i of the given json reddit api data"""
    data = json.loads(posts_json)['data']['children'][i]['data']
    is_video = 'reddit_video_preview' in data['preview']
    media_url = None

    if is_video:
        media_url = data['preview']['reddit_video_preview']['fallback_url']
    else:
        media_url = data['url']

    title = data['title']
    post_id = data['id']

    return media_url, title, post_id, is_video

def does_post_match(title, regex=None):
    """Checks given post whether its title matches the given regex."""
    pre_compiled = re.compile(regex)
    return bool(pre_compiled.match(title) is not None)

def main(sub_reddit=None, test=False):
    """Main function"""
    # Setupo environment and configuration
    config = get_config()
    if test is True:
        group_id = config['test_group_id']
    else:
        group_id = config['group_id']
    token = config['bot_token']
    regex = config['filter_regex']
    subreddits = config['subreddits']

    latest_posts = get_latest_posts()

    # Get Bot
    bot = get_bot(token)

    # If no subreddit is predefined --> get random subreddit from list
    if sub_reddit is None:
        sub_reddit = random.choice(subreddits)

    # get newest posts from sub reddit
    newest_posts = get_subreddit_posts(sub_reddit)

    # Get latest reddit post, filter gonewild
    media_url = None
    title = None
    post_id = None
    is_video = None

    for i in range(10):
        media_url, title, post_id, is_video = get_post(newest_posts, i)
        if sub_reddit == 'gonewild':
            if not does_post_match(title, regex):
                continue
        # Post passed regex check
        if is_post_in_latest_posts(latest_posts, sub_reddit, post_id):
            continue
        else:
            print('Checked: ' + str(i) + ' posts.')
            break

    if media_url is not None and title is not None and post_id is not None and is_video is not None:
        # Create the message
        msg = sub_reddit + ': ' + title

        if is_video:
            bot.sendVideo(group_id, media_url, caption=msg)
        else:
            bot.sendPhoto(group_id, media_url, caption=msg)

        # Update already sent posts
        latest_posts = update_latest_posts(latest_posts, sub_reddit, post_id)
        crop_latest_posts(latest_posts)
        store_latest_posts(data=latest_posts)
    else:
        bot.sendMessage(group_id, 'Did not find an adequate post. Tired of searching...')


if __name__ == '__main__':
    PARSER = argparse.ArgumentParser()
    PARSER.add_argument("--subreddit")
    PARSER.add_argument("--test", action="store_true")
    ARGS = PARSER.parse_args()
    main(ARGS.subreddit, ARGS.test)
