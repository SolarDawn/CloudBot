import os
import codecs
import json
import random
import requests
from sqlalchemy import Table, Column, PrimaryKeyConstraint, String

from cloudbot import hook
from cloudbot.util import colors, timeformat, database

pet_table = Table(
    "pets",
    database.metadata,
    Column('pet_name', String(25)),
    Column('owner_name', String(25)),
    Column('pet_type', String(25)),
    PrimaryKeyConstraint('pet_name')
)

pets = {}

class Pet:
    def __init__(self, name, owner, pet_type):
        self.name = name
        self.owner = owner
        self.pet_type = pet_type

@hook.on_start()
def load_pets(bot, db):
    pets.clear()
    for row in db.execute(pet_table.select()):
        name = row["pet_name"]
        pet = Pet(name, row["owner_name"], row["pet_type"])
        pets[name] = pet

    path = os.path.join(bot.data_dir, "pet.json")
    global pet_actions
    with codecs.open(path, encoding="utf-8") as f:
        pet_actions = json.load(f)


@hook.command()
def addpet(event, db, nick, text):
    """[pet name] [pet species] - creates a new pet"""
    args = text.split(" ")
    if len(args) < 2:
        event.notice_doc()
        return

    if args[0] in pets:
        # already exists
        return "Pet by that name already exists"
    else:
        # add
        newpet = Pet(args[0], nick, args[1])
        pets[newpet.name] = newpet
        db.execute(pet_table.insert().values(pet_name = newpet.name, owner_name = newpet.owner, pet_type = newpet.pet_type))
        db.commit()
        return "Added new " + newpet.pet_type + " " + newpet.name


@hook.regex(r'(?i)(?:come( here)|here|hey) (\w+)')
def beckon(match, nick, message):
    if match.group(2) in pets:

        cur_pet = pets[match.group(2)]
        if cur_pet.pet_type in pet_actions:
            response = random.choice(pet_actions[cur_pet.pet_type]['greetings']).replace("<nick>", nick)
        else:
            response = random.choice(pet_actions['pet']['greetings']).replace("<nick>", nick)

        message("\x1D*" + cur_pet.name + " " + response + colors.parse("*$(clear)") + chr(0x1D))


@hook.regex(r'(?i)(?:pets|rubs|scratches) (\w+)')
def affection(match, action):
    return ""
