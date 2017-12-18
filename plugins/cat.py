import os
import codecs
import random
import re

from cloudbot import hook

@hook.on_start()
def load_actions(bot):
    path = os.path.join(bot.data_dir, "cat_actions.txt")
    global cat_actions
    with codecs.open(path, encoding="utf-8") as f:
        cat_actions = [line.strip() for line in f.readlines() if not line.startswith("//")]

greeting_re = re.compile(r'(hello|hi) (catbot|kitty)(!)?', re.I)
@hook.regex(greeting_re)
def greeting(match):
    return ":3 meow!"

beckon_re = re.compile(r'(?:(come( here)|here|hey) (catbot|kitty))|(?:(hey )?(catbot|kitty),? (come( here)|here))', re.I)
@hook.regex(beckon_re)
def beckon(match, nick, action):
    response = random.choice(cat_actions).replace("<nick>", nick)
    action(response)
