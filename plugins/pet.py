import json
import os
import random
import re
import time

from sqlalchemy import Table, Column, PrimaryKeyConstraint, String

from cloudbot import hook
from cloudbot.clients.irc import IrcClient
from cloudbot.util import database

pet_table = Table(
    "pets",
    database.metadata,
    Column('pet_name', String(25)),
    Column('owner_name', String(25)),
    Column('pet_type', String(25)),
    Column('channel', String(25)),
    PrimaryKeyConstraint('pet_name')
)

pets = {}
pet_config = {}  # type: dict
pet_types = {}  # type: dict


class Pet:
    def __init__(self, name, owner, species="pet", channel=None):
        """
        Create a new pet object

        :param name: name of the pet
        :param owner: name of the pet's owner (irc nick)
        :param species: species/type of the pet, if specified allows species-specific actions
        :param channel: channel that the pet lives in
        """
        self.name = name
        self.owner = owner
        self.species = species
        self.channel = channel

        self.hunger = 0
        self.begging = False
        self.beg_delay = 0

        self.last_played_with_nick = None
        self.last_played_with_counter = 0
        self.play_counter = 0

        self.tiredness = 0
        self.sleeping = False
        self.ready_to_sleep = False
        self.sleep_delay = 0
        self.wait_for_owner = False

    @property
    def energy_level(self):
        if self.species in pet_types and "energy" in pet_types[self.species]:
            return pet_types[self.species]['energy']
        else:
            return pet_types['default']['energy']

    @property
    def energy(self):
        if self.species in pet_types and "energy" in pet_types[self.species]:
            return energy_multiplier * pet_types[self.species]['energy']
        else:
            return energy_multiplier * pet_types['default']['energy']

    def get_action(self, action_type, nick=None):
        """
        Get a random entry from the actions list, of the specified type

        :param str action_type: a key in pet_types that specifies the desired action type
        :param str nick: the username to be used in action templates, defaults to the pet owner
        :return: a random action string of the specified type
        :rtype: str
        """
        if nick is None:
            nick = self.owner

        if self.species in pet_types and action_type in pet_types[self.species]:
            return random.choice(pet_types[self.species][action_type]).replace("<nick>", nick)
        elif action_type in pet_types['default']:
            return random.choice(pet_types['default'][action_type]).replace("<nick>", nick)
        else:
            return ""

    def prepare_sleep(self, max_delay=9, wait_for_owner=False):
        """Start the sleep countdown"""
        self.ready_to_sleep = True
        self.wait_for_owner = wait_for_owner
        self.sleep_delay = random.randint(0, max_delay)

    def sleep(self, wait_for_owner=None):
        """
        Put the pet to sleep

        :return: a random sleep action
        :rtype: str
        """
        self.sleeping = True
        self.ready_to_sleep = False
        self.sleep_delay = 0

        if wait_for_owner is not None:
            self.wait_for_owner = wait_for_owner

        return self.get_action("sleep_actions")

    def wakeup(self):
        """
        Wake up the pet

        :return: a random wakeup action
        :rtype: str
        """
        self.sleeping = False
        self.ready_to_sleep = False
        self.tiredness = 0
        self.sleep_delay = 0
        self.wait_for_owner = False
        return self.get_action("wake_actions")

    def update_sleep(self):
        if self.sleeping:
            if self.tiredness > 0:
                self.tiredness -= 1
                return None
            else:
                if not self.wait_for_owner:
                    return self.wakeup()
                else:
                    # only wake on explicit wake
                    return None
        else:
            if self.ready_to_sleep:
                if self.sleep_delay <= 0:
                    # ready to go to sleep
                    return self.sleep()
                else:
                    self.sleep_delay -= 1
                    return None
            elif self.tiredness > self.energy and self.sleep_delay <= 0:
                # get ready to sleep
                self.prepare_sleep()
                return None
            elif not self.ready_to_sleep:
                # not ready to sleep yet
                if self.tiredness < self.energy:
                    self.tiredness += 1
                return None

    def prepare_beg(self, max_delay=9):
        self.begging = True
        self.beg_delay = random.randint(0, max_delay)

    def beg(self):
        self.begging = False
        return self.get_action("beg_actions")

    def update_hunger(self):
        if self.hunger < max_hunger:
            self.hunger += 1

        if not (self.ready_to_sleep or self.sleeping):
            if self.hunger >= max_hunger:
                if not self.begging:
                    # start begging cycle
                    self.prepare_beg()
                    return None
                elif self.beg_delay > 0:
                    # countdown to begging
                    self.beg_delay -= 1
                    return None
                else:
                    # time to beg
                    return self.beg()

    def play(self, nick=None):
        if nick is None:
            return self.get_action("play_actions")
        else:
            return self.get_action("play_with_actions", nick)

    def update_play(self, conn: IrcClient):
        if self.last_played_with_nick is not None:
            self.last_played_with_counter += 1
            if self.last_played_with_counter >= 10:
                # disengage with user
                self.last_played_with_nick = None
                self.last_played_with_counter = 0
                self.play_counter = random.randint(20, 110)
                return None

        if self.sleeping:
            return None

        if self.play_counter <= 0:
            if self.last_played_with_nick is not None:
                # play with last engaged
                self.play_counter = random.randint(4, 10)  # between 4 & 10 min
                return self.play(self.last_played_with_nick)
            else:
                # play randomly
                self.play_counter = random.randint(30, 120)  # between 30 min and 2 hrs
                play_type = random.randint(1, 4)
                if play_type <= 2:
                    # play alone
                    return self.play()
                elif play_type == 3:
                    # play with other pet
                    other_pets = {}
                    for name, pet in pets.items():  # type: str,Pet
                        if pet.channel == self.channel:
                            other_pets[name] = pet

                    if len(other_pets) > 0:
                        other_name = random.choice(list(other_pets))
                        return self.play(other_name)

                    return self.play()
                else:
                    # play with user
                    users = [nick for nick, user in conn.memory['users'].items()
                             if self.channel in user['channels'] and nick != conn.nick]
                    if len(users) > 0:
                        return self.play(random.choice(users))
                    else:
                        return self.play(self.owner)
        else:
            self.play_counter -= 1
            return None


@hook.on_start()
def load_pets(bot, db):
    pets.clear()
    for row in db.execute(pet_table.select()):
        name = row["pet_name"]
        pet = Pet(name, row["owner_name"], row["pet_type"], row["channel"])
        pets[name] = pet

    path = os.path.join(bot.data_dir, "pet.json")

    global pet_config
    global pet_types
    global energy_multiplier
    global max_hunger

    with open(path, encoding="utf-8", mode='r') as f:
        pet_config = json.load(f)
        pet_types = pet_config["pet_types"]
        energy_multiplier = pet_config["energy_multiplier"]
        max_hunger = pet_config["max_hunger"]


@hook.command(permissions=["petconfig"])
def saveconfig(bot, notice):
    path = os.path.join(bot.data_dir, "pet.json")
    with open(path, encoding="utf-8", mode='w') as f:
        json.dump(pet_config, f, indent=4)

    notice("pet config saved successfully")


@hook.irc_raw("004")
def init_pets(conn: IrcClient, message):
    time.sleep(10)
    users = conn.memory['users']  # type: dict

    output = {}
    usermap = {nick.lower(): nick for nick in users.keys()}

    for pet in pets.values():  # type: Pet
        if pet.owner in usermap:
            if pet.channel in users[usermap[pet.owner]]['channels']:
                # owner is here, wakeup silently
                pet.wakeup()
                pet.update_play(conn)
                if pet.channel in output:
                    output[pet.channel] += " " + pet.name
                else:
                    output[pet.channel] = "Woke up pets: " + pet.name
        else:
            # owner not online, sleep silently
            pet.sleep(True)

    for chan, outstr in output.items():  # type: str,str
        message(outstr, chan)

    return


@hook.command("addpet", "apet")
def addpet(event, db, nick, text, chan):
    """<pet name> <pet species> - creates a new pet"""
    args = _parse_args(text)
    if len(args) < 2:
        event.notice_doc()
        return

    if args[0] in pets:
        # already exists
        return "Pet by that name already exists"
    else:
        # add
        newpet = Pet(args[0], nick.lower(), args[1], chan)
        pets[newpet.name] = newpet
        db.execute(pet_table.insert().values(pet_name=newpet.name, owner_name=newpet.owner, pet_type=newpet.species,
                                             channel=newpet.channel))
        db.commit()
        return "Added new " + newpet.species + " " + newpet.name


@hook.command("removepet", "rempet", "rpet")
def removepet(event, db, nick, text, has_permission):
    """<pet name> - removes a pet that belongs to you"""
    args = _parse_args(text)
    if len(args) < 1:
        event.notice_doc()
        return

    if args[0] in pets:
        # pet exists
        delpet = pets[args[0]]
        if nick == delpet.owner or has_permission("botcontrol"):
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
    outstr = "Pets: "
    for name, pet in pets.items():
        outstr += name + " (" + pet.species + "), "

    if outstr.endswith(", "):
        return outstr[:-2]
    else:
        return outstr


beckon_re = re.compile(r'(?:come(?: here)|here|hey|beckons) (\w+)', re.I)


@hook.regex(beckon_re)
def beckon(match, nick, message):
    if match.group(1) in pets:
        cur_pet = pets[match.group(1)]  # type: Pet
        response = cur_pet.get_action('greeting_actions', nick)
        message("\x1D*" + cur_pet.name + " " + response + "*\x0F")


affection_re = re.compile(r'(?:pets|rubs|scratches|boops) (\w+)', re.I)


@hook.regex(affection_re)
def affection_regex(match, nick, message):
    _love_pet(match.group(1), nick, message)


@hook.command("pet", "rub", "scratch", "boop")
def affection(text, nick, message, event):
    """<pet name> - show affection towards a pet"""
    args = _parse_args(text)
    if len(args) < 1:
        event.notice_doc()
    else:
        _love_pet(args[0], nick, message)


def _love_pet(pet_name, nick, message):
    if pet_name in pets:
        cur_pet = pets[pet_name]  # type: Pet
        time.sleep(5)
        response = cur_pet.get_action('happy_actions', nick)
        message("\x1D*" + cur_pet.name + " " + response + "*\x0F")


feed_re = re.compile(r'feeds (\w+)|fills (\w+)(?:\'s)? (?:food|(?:bowl|dish))|gives (\w+) (?:some )?food', re.I)


@hook.regex(feed_re)
def feed_regex(match, nick, message):
    pet_name = ""
    for group in match.groups():
        if group is not None:
            pet_name = group

    if pet_name is not None:
        _feed_pet(pet_name, nick, message)


@hook.command()
def feed(text, nick, message, event):
    """<pet name> - feeds a pet"""
    args = _parse_args(text)
    if len(args) < 1:
        event.notice_doc()
    else:
        _feed_pet(args[0], nick, message)


def _feed_pet(pet_name, nick, message):
    """
    Feed a pet

    :param str pet_name: name of the pet to feed
    :param str nick: nick of command caller
    :param message: message function
    """
    if pet_name in pets:
        cur_pet = pets[pet_name]  # type: Pet
        time.sleep(5)
        if cur_pet.hunger >= max_hunger * 3 / 4:
            # hungry enough to eat
            cur_pet.hunger = 0
            response = cur_pet.get_action('eat_actions', nick)
            message("\x1D*" + cur_pet.name + " " + response + "*\x1D")
            return
        else:
            # not hungry
            message("\x1D*" + cur_pet.name + " sniffs at their food and walks away*\x1D")


@hook.command()
def playwith(text, nick, message, event):
    """<pet name> - plays with a pet"""
    args = _parse_args(text)
    if len(args) < 1:
        event.notice_doc()
    else:
        _play_pet(args[0], nick, message)


play_re = re.compile(r'plays with (\w+)', re.I)


@hook.regex(play_re)
def play_regex(match, nick, message):
    _play_pet(match.group(1), nick, message)


def _play_pet(pet_name, nick, message):
    """
    Play with specified pet

    :param str pet_name: name of the pet to play with
    :param str nick: nick of the calling user
    :param message: message function
    """

    if pet_name in pets:
        cur_pet = pets[pet_name]  # type: Pet
        cur_pet.last_played_with_nick = nick
        cur_pet.last_played_with_counter = 0

        cur_pet.play_counter = random.randint(4, 10)

        time.sleep(5)
        response = cur_pet.play(nick)
        if response is not None:
            message("\x1D*" + cur_pet.name + " " + response + "*\x1D")

    return


@hook.irc_raw("PRIVMSG")
def parse_actions(irc_raw, message):
    i = irc_raw.find(":\x01ACTION")
    if i > -1:
        i += 9
        nick_end = irc_raw.find("!")
        nick = irc_raw[1:nick_end]

        text = irc_raw[i:-1]

        match = beckon_re.match(text)
        if match:
            beckon(match, nick, message)
            return

        match = affection_re.match(text)
        if match:
            affection_regex(match, nick, message)
            return

        match = feed_re.match(text)
        if match:
            feed_regex(match, nick, message)
            return

        match = play_re.match(text)
        if match:
            play_regex(match, nick, message)
            return


@hook.irc_raw(["PART", "QUIT"])
def on_leave(irc_raw, message, conn, nick, chan):
    nick = nick.lower()
    if nick != conn.nick and (irc_raw.lower().find("changing host") == -1):
        for name, pet in pets.items():
            if pet.owner == nick:
                response = pet.sleep(True)
                message("\x1D*" + name + " " + response + " waiting for " + nick + " to return*\x1D", chan)

    return


@hook.irc_raw("JOIN")
def on_join(message, conn, nick, chan):
    nick = nick.lower()
    if nick != conn.nick:
        for name, pet in pets.items():
            if pet.owner == nick and pet.channel == chan:
                if pet.sleeping:
                    response = pet.wakeup()
                    message("\x1D*" + name + " " + response + "*\x1D", chan)
                else:
                    response = pet.get_action("greeting_actions", nick)
                    message("\x1D*" + name + " " + response + "*\x1D", chan)

    return


# run every minute
@hook.periodic(60)
def update_pet_states(bot, logger):
    my_conn = None  # type: IrcClient
    for conn in bot.connections.values():
        if conn.name == "snoonet":
            my_conn = conn

    for name, pet in pets.items():  # type: str,Pet
        # update the pet's hunger status
        response = pet.update_hunger()  # type: str
        if (response is not None) and (pet.channel is not None):
            my_conn.message(pet.channel, "\x1D*" + name + " " + response + "*\x1D")

        response = pet.update_sleep()
        if (response is not None) and (pet.channel is not None):
            my_conn.message(pet.channel, "\x1D*" + name + " " + response + "*\x1D")

        response = pet.update_play(my_conn)

        if (response is not None) and (pet.channel is not None):
            my_conn.message(pet.channel, "\x1D*" + name + " " + response + "*\x1D")

        if pet.sleeping:
            status = "sleeping"
        else:
            status = "awake"

        logger.info("[pet] {} - lpw: {}, lpc: {}, pc: {}, status: {}".format(pet.name, pet.last_played_with_nick,
                                                                             pet.last_played_with_counter,
                                                                             pet.play_counter, status))

    return


@hook.command()
def listspecies(notice):
    """list all species defined in the config"""
    first = True
    outstr = ""
    for species in pet_types:
        if not first:
            outstr += ","
        outstr += " " + species

    notice(outstr)


@hook.command(permissions=["petconfig"])
def addspecies(text, event, bot, notice):
    """<species> - add a new species to the config"""
    args = _parse_args(text)
    if len(args) < 1:
        event.notice_doc()
        return

    if args[0] not in pet_types:
        pet_types[args[0]] = {}
        notice("Added species " + args[0])
        saveconfig(bot, notice)
    else:
        notice("That species already exists in the config")


@hook.command(permissions=["petconfig"])
def remspecies(text, event, bot, notice):
    """<species> - remove a species from the config"""
    args = _parse_args(text)
    if len(args) < 1:
        event.notice_doc()
        return

    if args[0] in pet_types:
        del pet_types[args[0]]
        notice("Removed species " + args[0])
        saveconfig(bot, notice)
    else:
        notice("Species does not exist in config")


@hook.command()
def listactions(text, event, notice):
    """<species> [action type] - list configured actions for a species"""
    args = _parse_args(text)
    if len(args) < 1:
        event.notice_doc()
        return

    if args[0] in pet_types:
        if len(args) < 2:
            # list types
            outstr = "Action types defined for {}:".format(args[0])
            for key, value in pet_types[args[0]].items():
                if type(value) is list:
                    outstr += " " + key
        else:
            # list specific
            if args[1] in pet_types[args[0]]:
                outstr = "{} for {}:".format(args[1], args[0])
                i = 0
                for action in pet_types[args[0]][args[1]]:
                    if i > 0:
                        outstr += ","
                    outstr += " [{}] {}".format(i, action)
                    i += 1
            else:
                outstr = "No actions under that type in the config"
    else:
        outstr = "That species was not found in the config. It can be added with \"|add_species <species>\""

    notice(outstr)


@hook.command(permissions=["petconfig"])
def addaction(text, event, bot, notice):
    """<species> <action type> <action text> - add an action for a species, <nick> is replaced when the action runs"""
    args = _parse_args(text)
    if len(args) < 3:
        event.notice_doc()
        return

    species = args[0]
    a_type = args[1]
    a_text = args[2]

    if species not in pet_types:
        notice("Species not found in config, use |add_species [species]")

    if a_type not in pet_types[species]:
        if a_type in pet_types['default']:
            pet_types[species][a_type] = []
        else:
            outstr = "Action type is not supported. Available types: "
            for k in list(pet_types['default'].keys()):
                outstr += " " + k
            notice(outstr)

    pet_types[species][a_type].append(a_text)
    notice("Action added successfully")
    saveconfig(bot, notice)


@hook.command(permissions=["petconfig"])
def remaction(text, event, bot, notice):
    """<species> <action type> <action #> - remove an action from the config"""
    args = _parse_args(text)
    if len(args) < 3:
        event.notice_doc()
        return

    species = args[0]
    a_type = args[1]
    a_index = int(args[2])

    if species in pet_types and a_type in pet_types[species] and (0 <= a_index < len(pet_types[species][a_type])):
        # valid
        del pet_types[species][a_type][a_index]
        notice("Action removed successfully")
        if len(pet_types[species][a_type]) == 0:
            del pet_types[species][a_type]
        saveconfig(bot, notice)

    else:
        # no such action
        notice("Action not found, use |list_actions to see current config")


def _parse_args(arg_str: str):
    return [p.strip('"') for p in re.split(r"( |\".*?\")", arg_str) if p.strip()]
