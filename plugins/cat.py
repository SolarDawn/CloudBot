import os
import codecs
import random
import re
import json

from cloudbot import hook

@hook.on_start()
def load_actions(bot):
    path = os.path.join(bot.data_dir, "cat.json")
    global cat_actions
    with codecs.open(path, encoding="utf-8") as f:
        cat_actions = json.load(f)

@hook.regex(r':3')
def catface(match, nick, action):
    action("boops " + nick + " :3")

@hook.regex(r'(?i)(hello|hi) (catbot|kitty)(!)?')
def greeting(match):
    return ":3 meow!"

#beckon_re = re.compile(r'(?:(come( here)|here|hey) (catbot|kitty))|(?:(hey )?(catbot|kitty),? (come( here)|here))', re.I)
@hook.regex(r'(?i)(?:(come( here)|here|hey) (catbot|kitty))|(?:(hey )?(catbot|kitty),? (come( here)|here))')
def beckon(match, nick, action):
    response = random.choice(cat_actions['greetings']).replace("<nick>", nick)
    action(response)

@hook.regex(r'(?i)(?:pets|rubs|scratches) (?:catbot|kitty)')
def affection(match, action):
    action(random.choice(cat_actions['happy_actions']) + " happily")
