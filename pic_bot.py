"""Grabs the latest, not yet sent post from a subreddit and sends it to the given telegram group."""

import argparse
import json
import logging
import pickle
import random
import re
import urllib.request

import telepot


class Logger:
    """ Logging singleton to provide a single logger for all classes"""
    __instance = None

    @staticmethod
    def get_instance():
        """ Static access method. """
        if Logger.__instance is None:
            Logger()
        return Logger.__instance

    def __init__(self):
        """ Virtually private constructor. """
        if Logger.__instance is not None:
            raise Exception("This class is a singleton!")
        Logger.__instance = self

        # set up logging to file - see previous section for more details
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                            datefmt='%m-%d %H:%M',
                            filename='picturebot.log',
                            filemode='w')
        # define a Handler which writes INFO messages or higher to the sys.stderr
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        # set a format which is simpler for console use
        formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
        # tell the handler to use this format
        console.setFormatter(formatter)
        # add the handler to the root logger

        self.log = logging.getLogger('picturebot')
        self.log.addHandler(console)

    def info(self, msg, *args, **kwargs):
        """Log to log level INFO."""
        self.log.info(msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        """Log to log level DEBUG."""
        self.log.debug(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """Log to log level ERROR."""
        self.log.error(msg, *args, **kwargs)


class NvMHandler:
    """Handles read and write request, as well as a ring buffer for the data."""

    def __init__(self):
        self.logger = Logger.get_instance()

    def store(self, data, filename='posts.pickle'):
        """Stores the given data as dump in the file identified by filename."""
        self.logger.info('Storing data in %s', filename)
        with open(filename, 'wb') as handle:
            pickle.dump(data, handle)

    def load(self, filename='posts.pickle'):
        """Loads and returns a stored dump identified by filename."""
        self.logger.info('Loading data from %s', filename)
        try:
            with open(filename, 'rb') as handle:
                data = pickle.load(handle)
                return data
        except FileNotFoundError:
            self.logger.debug('Could not find %s', filename)
            return {}

    def update(self, data, subreddit, post_id):
        """Updates the given dictionary with the key subreddit and the value post_id."""
        self.logger.info('Updating data with %s - %s', subreddit, post_id)
        if subreddit in data:
            data[subreddit].append(post_id)
        else:
            data[subreddit] = [post_id]
        return self._crop_data(data)

    def _crop_data(self, data, max_length=10):
        """Reduces the length of the latest posts to the given max_length."""
        self.logger.info('Cropping data to max %s length', max_length)
        for key in data:
            data[key] = data[key][-max_length:]
        return data


class RedditCrawler:
    """Crawler for the reddit API to retrieve posts."""

    def __init__(self):
        self.logger = Logger.get_instance()
        self.nvm = NvMHandler()

    def get_subreddit_posts_from_api(self, subreddit):
        """Returns the latest posts of the given subreddit"""
        data = None

        try:
            req = urllib.request.Request(
                'https://www.reddit.com/r/' + str(subreddit) + '/new.json?sort=new',
                data=None,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) \
                    AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'
                })
            data = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
        except urllib.error.HTTPError as err:
            self.logger.debug('HTTPError: %s', err)
        return data

    def does_post_match(self, title, regex='.*'):
        """Checks given post whether its title matches the given regex."""
        pre_compiled = re.compile(regex)
        if pre_compiled.match(title) is None:
            self.logger.info('Title: \'%s\' does not match regex \'%s\'', title, regex)
            return False
        return True

    def get_post(self, posts, sub_reddit, filter_regex, max_retries=10):
        """Get the latest not yet sent reddit post, applying a regex filter for gonewild."""
        latest_posts = self.nvm.load()

        post = None
        for i in range(max_retries):
            post = self._get_post_at_position(posts, i)

            post['sub_reddit'] = sub_reddit

            if post['sub_reddit'] == 'gonewild':
                if not self.does_post_match(post['title'], filter_regex):
                    continue
            # Post passed regex check
            if RedditCrawler.is_post_in_latest_posts(latest_posts,
                                                     post['sub_reddit'],
                                                     post['post_id']):
                continue
            else:
                self.logger.info('Checked: ' + str(i+1) + ' posts.')
                break

        latest_posts = self.nvm.update(latest_posts, post['sub_reddit'], post['post_id'])
        self.nvm.store(latest_posts)

        return post

    def _get_post_at_position(self, posts, i):
        """Returns the post and its media type at index i of the given json reddit api data"""
        post = {}
        try:
            data = posts['data']['children'][i]['data']
            is_video = 'reddit_video_preview' in data['preview']

            if is_video:
                media_url = data['preview']['reddit_video_preview']['fallback_url']
            else:
                media_url = data['url']

            title = data['title']
            post_id = data['id']

            if title is not None and media_url is not None and post_id is not None:
                post['title'] = title
                post['media_url'] = media_url
                post['post_id'] = post_id
                post['is_video'] = is_video
        except KeyError as err:
            self.logger.debug('Error accessing key: %s', err)

        return post

    @staticmethod
    def is_post_in_latest_posts(latest_posts, subreddit, post_id):
        """Checks if the given value is in the given key of the given dictionary."""
        if subreddit in latest_posts:
            return post_id in latest_posts[subreddit]
        return False


class TelegramBot:  # pylint: disable=too-few-public-methods
    """Telegram Bot instance."""
    def __init__(self, token):
        self.bot = telepot.Bot(token)

    def send_message(self, chat_id, msg, media=None, is_video=False):
        """Sends a message to the given group."""
        if media is None:
            self.bot.sendMessage(chat_id, msg)
        elif is_video:
            self.bot.sendVideo(chat_id, media, caption=msg)
        else:
            self.bot.sendPhoto(chat_id, media, caption=msg)


class Configuration:
    """Configuration for the picturebot."""
    def __init__(self, config_file='config.json'):
        self.cfg = {}
        self.cfg = Configuration.get_config(config_file)

    def get_subreddits(self):
        """Returns the subreddits from the config file."""
        return self.cfg.get('subreddits', [])

    def get_chat_id(self):
        """Returns the chat id from the config file."""
        return self.cfg.get('group_id', 0)

    def get_test_chat_id(self):
        """Returns the test chat id from the config file."""
        return self.cfg.get('test_group_id', 0)

    def get_filter_regex(self):
        """Returns the filtering regex from the config file."""
        return self.cfg.get('filter_regex', '.*')

    def get_bot_token(self):
        """Returns the Telegram bot token from the config file."""
        return self.cfg.get('bot_token', '')

    @staticmethod
    def get_config(filename='config.json'):
        """Reads a json config, identified by filename."""
        with open(filename) as config_file:
            data = json.load(config_file)
            return data


def main(sub_reddit=None, test=False):
    """Main function"""

    # Setup configuration
    cfg = Configuration()

    # If no subreddit is predefined --> get random subreddit from list
    if sub_reddit is None:
        sub_reddit = random.choice(cfg.get_subreddits())

    if test:
        chat_id = cfg.get_test_chat_id()
    else:
        chat_id = cfg.get_chat_id()

    crawler = RedditCrawler()

    reddit_data = crawler.get_subreddit_posts_from_api(sub_reddit)

    post = crawler.get_post(reddit_data, sub_reddit, cfg.get_filter_regex())

    bot = TelegramBot(cfg.get_bot_token())

    if post:
        msg = post['sub_reddit'] + ': ' + post['title']
        bot.send_message(chat_id, msg, media=post['media_url'], is_video=post['is_video'])
    else:
        bot.send_message(chat_id, 'Did not find an adequate post. Tired of searching...')


if __name__ == '__main__':
    PARSER = argparse.ArgumentParser()
    PARSER.add_argument("--subreddit")
    PARSER.add_argument("--test", action="store_true")
    ARGS = PARSER.parse_args()
    main(ARGS.subreddit, ARGS.test)
