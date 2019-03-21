# Picturebot

This project was founded out of boredom.

A telegram bot, which is sending a picture from a subreddit to a telegram group.

Based on its configuration, it can randomly select a subreddit from a given list.

It has a history of up to ten sent posts per subreddit, to prevent resending the same picture.

# Installation

- Clone repository
- Install telepot:
`pip install telepot`

# Preparation

Copy `config.sample.json` to `config.json` and edit the parameters to fit your needs.

For details on how to create a Telegram bot, check the [Telegrom Doc](https://core.telegram.org/bots#6-botfather).

# Usage

Execute the script: `python3 pic_bot.py`

___

# Thanks
Thanks to the authors of [telepot](https://telepot.readthedocs.io/en/latest/) for providing such a great and easy to use lib.

