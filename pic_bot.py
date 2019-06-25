"""Grabs the latest, not yet sent post from a subreddit and sends it to the given telegram group."""

import argparse
from datetime import datetime
import json
import logging
import pickle
import random
import re
import time
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

        # only iterate over max available entries from subreddit
        max_retries = min(len(posts['data']['children']), max_retries)
        self.logger.info('Max retries limited to \'%s\'.', max_retries)
        for i in range(max_retries):
            self.logger.info('Checking post \'%s\' of \'%s\'.', (i + 1), max_retries)
            post = self._get_post_at_position(posts, i)

            if post: # not an empty dict
                post['sub_reddit'] = sub_reddit

                if post['sub_reddit'] in filter_regex:
                    if not self.does_post_match(post['title'], filter_regex[post['sub_reddit']]):
                        continue
                # Post passed regex check
                if RedditCrawler.is_post_in_latest_posts(latest_posts,
                                                         post['sub_reddit'],
                                                         post['post_id']):
                    continue
                else:
                    self.logger.info('Checked: ' + str(i+1) + ' posts.')
                    break
            else:
                self.logger.info('Recieved empty post for entry \'%s\'.', (i + 1))

        if post: # not an empty dict
            latest_posts = self.nvm.update(latest_posts, post['sub_reddit'], post['post_id'])
            self.nvm.store(latest_posts)

        return post

    def _get_post_at_position(self, posts, i):
        """Returns the post and its media type at index i of the given json reddit api data"""
        post = {}

        if posts is not None:
            try:
                data = posts['data']['children'][i]['data']
                if 'preview' in data:
                    is_video = 'reddit_video_preview' in data['preview']
                else:
                    # No media
                    self.logger.info('No parsable media found in post.')
                    return {}

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
        else:
            self.logger.info('Posts are invalid.')

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
        self.logger = Logger.get_instance()

    def send_message(self, chat_id, msg, media=None, is_video=False):
        """Sends a message to the given group."""
        if media is None:
            self.bot.sendMessage(chat_id, msg)
        elif is_video:
            self.bot.sendVideo(chat_id, media, caption=msg)
        else:
            self.bot.sendPhoto(chat_id, media, caption=msg)

    def get_updates(self, update_id=None):
        """Returns all updates for the bot since the last update."""
        updates = []
        if update_id != {}:
            self.logger.info('Last update ID %d', update_id)
            updates = self.bot.getUpdates(update_id)
        else:
            self.logger.info('No update ID found, retrieving all updates')
            updates = self.bot.getUpdates()

        return updates

    def is_admin(self, chat_id, user_id):
        """Checks if the user is admin of the specific group."""
        status = self.bot.getChatMember(chat_id, user_id)['status']
        return status in['creator', 'administrator']


class Configuration:
    """Configuration for the picturebot."""

    def __init__(self, config_file='config.json'):
        self.cfg = {}
        self.cfg = Configuration.get_config(config_file)

    def get_subreddits(self):
        """Returns the subreddits from the config file."""
        return self.cfg.get('subreddits', [])

    def get_chat_id(self, test=False):
        """Returns the chat id from the config file."""
        return self.cfg.get('test_group_id', 0) if test else self.cfg.get('group_id', 0)

    def get_filter_regex(self):
        """Returns the filtering regex from the config file."""
        return self.cfg.get('filter_regex', '.*')

    def get_bot_token(self):
        """Returns the Telegram bot token from the config file."""
        return self.cfg.get('bot_token', '')

    def get_activation_prefix(self):
        """Returns the activation prefix from the config file."""
        return self.cfg.get('activation_prefix', '/picbot')

    def get_triggers(self):
        """Returns the trigger times from the config file."""
        return self.cfg.get('triggers', None)

    @staticmethod
    def get_config(filename='config.json'):
        """Reads a json config, identified by filename."""
        with open(filename) as config_file:
            data = json.load(config_file)
            return data


class Picturebot:
    """"Provides functionality to send pictures to telegram groups"""

    def __init__(self, config_file='config.json'):
        # Setup configuration
        self._cfg = Configuration(config_file)
        # Setup crawler to retrieve reddit posts
        self._crawler = RedditCrawler()
        # Setup bot to post to telegram
        self._telegram_bot = TelegramBot(self._cfg.get_bot_token())
        # Setup logger
        self._logger = Logger.get_instance()
        # Setup NvM Handler
        self._nvm_handler = NvMHandler()
        # Setup command dictionary
        self._commands = \
            [
                {'command_string': 'MakeMeHappy',
                 'command_function': self._make_me_happy,
                 'command_requires_admin': False}
            ]

    def send_picture(self, sub_reddit=None, test=False):
        """
        Pics a picture from the given subreddit and sends it to the telegram group.
        If no subreddit it given, a random one from the config is selected.

        Keyword arguments:
        sub_reddit -- the subreddit if it shall be set fix (default None)
        test -- flag indicating if the message shall be sent to the testgroup
        """
        # if no subreddit is predefined --> get random subreddit from list
        if sub_reddit is None:
            sub_reddit = random.choice(self._cfg.get_subreddits())

        # select group id the message is sent to based on test flag
        chat_id = self._cfg.get_chat_id(test)

        # get images from selected subreddit
        reddit_data = self._crawler.get_subreddit_posts_from_api(sub_reddit)

        # select image and construct post
        post = self._crawler.get_post(reddit_data, sub_reddit, self._cfg.get_filter_regex())

        if post:
            # if an appropriate post was found then send it
            msg = post['sub_reddit'] + ': ' + post['title']
            self._telegram_bot.send_message(chat_id, msg, media=post['media_url'], is_video=post['is_video'])
        else:
            # if no appropriate post was found then send information
            self._telegram_bot.send_message(chat_id, 'Did not find an adequate post. Tired of searching...')

    def process_commands(self, test=False):
        """
        Checks if commands were received and processes them

        Keyword arguments:
        test -- flag indicating if the function shall operate
                on the testgroup
        """
        # load last update id from NvM
        last_update_id = self._nvm_handler.load('update_id.pickle')

        # get updates after the loaded update id
        updates = self._telegram_bot.get_updates(last_update_id)

        # if there are updates store the latest update id
        if len(updates) > 1:
            # discard the first update as it is the one with the provided update id
            updates = updates[1:]
            self._nvm_handler.store(updates[-1]['update_id'], 'update_id.pickle')
        else:
            self._logger.info('No new messages in chat')
            return

        chat_id = self._cfg.get_chat_id(test)

        # process all updates
        for update in updates:
            # check if message was sent in configured group
            if update['message']['chat']['type'] in ['supergroup', 'group'] and update['message']['chat']['id'] == chat_id:
                # check if message was for bot
                if update['message']['text'].startswith(self._cfg.get_activation_prefix()):
                    # check if command is implemented
                    command_split = update['message']['text'].split(' ')
                    command_name = command_split[1]
                    command_param = None
                    if len(command_split) == 3:
                        command_param = update['message']['text'].split(' ')[2]
                    command = next((command for command in self._commands
                                    if command['command_string'].lower() == command_name.lower()), None)
                    if command:
                        # check if admin privileges are needed
                        command_permissions = False
                        if command['command_requires_admin'] is True:
                            # check if sender is admin
                            command_permissions = self._telegram_bot.is_admin(
                                update['message']['chat']['id'],
                                update['message']['from']['id'])
                        else:
                            command_permissions = True

                        # check if command permissions are valid
                        if command_permissions:
                            self._logger.info('Received valid command %s', command_name)
                            command['command_function'](command_param, test)
                        else:
                            first_name = update['message']['from']['first_name']
                            last_name = update['message']['from']['last_name']
                            self._logger.info('User %s %s requested command %s without permission',
                                              first_name, last_name, command_name)
                    else:
                        # command not in list
                        self._logger.info("Unrecognized command %s", command_name)

    def _make_me_happy(self, subreddit, test):
        self.send_picture(subreddit, test)

def main():
    """Main function"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--subreddit")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--process_commands", action="store_true")
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()

    picbot = Picturebot()

    triggers = Configuration().get_triggers()
    if triggers is None:
        print('No triggers configured. Exiting')
        exit(-1)

    if args.loop:
        trigger_executed = [42 for x in triggers]
        while 1:
            picbot.process_commands(args.test)
            time.sleep(1)
            for idx, trigger in enumerate(triggers):
                #check if regular send shall take place
                time_now = datetime.now()
                # configured days
                if time_now.weekday() in trigger['days']:
                    # configured hours
                    if time_now.hour in trigger['hours']:
                        # configured minutes
                        if time_now.minute in trigger['minutes'] and trigger_executed[idx] != time_now.hour:
                            trigger_executed[idx] = time_now.hour
                            subreddit = args.subreddit
                            if trigger.get("subreddit", None) is not None:
                                subreddit = trigger['subreddit']
                            picbot.send_picture(subreddit, args.test)


if __name__ == '__main__':
    main()
