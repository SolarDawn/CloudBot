import os
import codecs
import json
import random
import re
import requests
from sqlalchemy import Table, Column, PrimaryKeyConstraint, String

from cloudbot import hook
from cloudbot.util import colors, timeformat, database

#MAX_HUNGER = 360
MAX_HUNGER = 2
MAX_TIREDNESS = 2

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
    def __init__(self, name, owner, species):
        self.name = name
        self.owner = owner
        self.species = species
        
        self.hunger = 0
        self.begging = False
        self.beg_delay = 0
        
        self.play_counter = 0
        
        self.tiredness = 0
        self.sleeping = False
        self.sleep_delay = 0
        

    def get_action(self, action_type):
        if self.species in pet_actions and action_type in pet_actions[self.species]:
            return random.choice(pet_actions[self.species][action_type])
        else:
            return random.choice(pet_actions['pet'][action_type])


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


@hook.command("addpet", "apet")
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
        db.execute(pet_table.insert().values(pet_name = newpet.name, owner_name = newpet.owner, pet_type = newpet.species))
        db.commit()
        return "Added new " + newpet.species + " " + newpet.name


@hook.command("removepet", "rempet", "rpet")
def removepet(event, db, nick, text):
    """[pet name] - removes a pet that belongs to you"""
    args = text.split(" ")
    if len(args) < 1:
        event.notice_doc()
        return
    
    if args[0] in pets:
        # pet exists
        delpet = pets[args[0]]
        if nick == delpet.owner:
            db.execute(pet_table.delete().where(pet_table.c.pet_name == args[0]))
            db.commit()
            del pets[args[0]]
            return "Deleted pet " + args[0]
        else:
            return args[0] + " is not one of your pets"
    else:
        return "No pet by that name"


@hook.command("listpets", "lpet", "lpets")
def listpets():
    #"""lists all the pets"""
    outstr = "Pets: "
    for name, pet in pets.items():
        outstr += name + "(" + pet.species + "), "
    
    if outstr.endswith(", "):
        return outstr[:-2]
    else:
        return outstr

beckon_re = re.compile(r'(?:come(?: here)|here|hey|beckons) (\w+)', re.I)
@hook.regex(beckon_re)
def beckon(match, nick, message):
    if match.group(1) in pets:
        cur_pet = pets[match.group(1)]
        response = cur_pet.get_action('greetings').replace("<nick>", nick)
        message("\x1D*" + cur_pet.name + " " + response + "*\x0F")


affection_re = re.compile(r'(?:pets|rubs|scratches|boops) (\w+)', re.I)
@hook.regex(affection_re)
def affection(match, nick, message):
    if match.group(1) in pets:
        cur_pet = pets[match.group(1)]
        response = cur_pet.get_action('happy_actions').replace("<nick>", nick)
        message("\x1D*" + cur_pet.name + " " + response + "*\x0F")


feed_re = re.compile(r'feeds (\w+)|fills (\w+)(?:\'s)? (?:food|(?:bowl|dish))|gives (\w+) (?:some )?food', re.I)
@hook.regex(feed_re)
def feed(match, nick, message):
    pet_name = ""
    for group in match.groups():
        if group != None:
            pet_name = group
    
    if pet_name in pets:
        cur_pet = pets[pet_name]
        if cur_pet.hunger >= MAX_HUNGER * 3/4:
            # hungry enough to eat
            cur_pet.hunger = 0
            response = cur_pet.get_action('eat_actions').replace("<nick>", nick)
            message("\x1D*" + cur_pet.name + " " + response + "*\x1D")
            return
        else:
            # not hungry
            message("\x1D*" + cur_pet.name + " sniffs at their food and walks away*\x1D")


@hook.irc_raw("PRIVMSG")
def parse_actions(irc_raw, message):
    i = irc_raw.find(":\x01ACTION")
    if i > -1:
        i += 9
        nick_end = irc_raw.find("!")
        nick = irc_raw[1:nick_end]
        
        text = irc_raw[i:-1]
        
        match = beckon_re.match(text)
        if (match):
            beckon(match, nick, message)
            return
        
        match = affection_re.match(text)
        if (match):
            affection(match, nick, message)
            return
        
        match = feed_re.match(text)
        if (match):
            feed(match, nick, message)
            return


@hook.periodic(60)
def update_pet_states():
    for name, pet in pets.items():
        if pet.hunger < MAX_HUNGER:
            pet.hunger += 1
        else:
            if not pet.begging:
                pet.begging = True
                pet.beg_delay = random.randint(0, 9)
            elif pet.beg_delay > 0:
                # countdown to begging
                pet.beg_delay -= 1
            else:
                # time to beg
                pet.begging = False
                response = pet.get_action("beg_actions").replace("<nick>", pet.owner)
                message("\x1D*" + name + " " + response + "*\x1D")
        return
        
        if pet.sleeping:
            # sleeping
            if pet.tiredness > 0:
                pet.tiredness -= 1
            else:
                pet.sleeping = False
                pet.tiredness = 0
        
        else:
            # awake
            pet.tiredness += 1
            
    
    return
