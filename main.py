#    Bulletin Board Bot - Pin Management Made Easier
#    Copyright(c) OblivionCreator - 2022

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

import errno
import glob
import json
import os
import warnings

import aiohttp
import disnake
from disnake.ext import commands
from configparser import ConfigParser
import requests

intents = disnake.Intents.default()
intents.guilds = True
bot = commands.Bot(command_prefix='unused',
                   allowed_mentions=disnake.AllowedMentions(users=False, everyone=False, roles=False,
                                                            replied_user=False), intents=intents) # Creates Bot Object, disallows bot from pinging any users and gets .guild() intent.
bot.remove_command('help')
guilds = None # Allowed Guilds. Set to 'None' to make commands Global, or set to [<guild_id>] to set on a per-server basis. Commands may take 1-2 hours to register Globally.


def loadConfig(guild):
    config = ConfigParser()
    try:
        with open(f'guild_configs/{guild}_config.ini', 'x') as file:
            config['DEFAULT'] = {'defaultbulletinchannel': 0, 'logging': 0}
            config['MONITORED_CHANNELS'] = {}
            config['WEBHOOKS'] = {}
            config['MONITORED_MESSAGES'] = {}
            config.write(file) # If no config exists, creates a new config for that guild when it is first loaded. DefaultBulletinChannel and Logging set to 0 by default.
    except:
        pass
    config.read(f'guild_configs/{guild}_config.ini')
    return config

def removeConfigItem(section, item, guild):
    config = loadConfig(guild)
    with open(f'guild_configs/{guild}_config.ini', 'w') as file:
        config.remove_option(section, item)
        config.write(file) # Removes an item from the guild's config.ini file.

def getConfigItem(section, item, guild):
    config = loadConfig(guild)
    return config.get(section, item)
    # Returns item from guild's config.ini

def getAllConfigItems(section, guild):
    config = loadConfig(guild)
    filtered_items = [x for x in config.items(section) if x[0] not in config.defaults()] # Filters out items from [DEFAULT] when returning all items under a section.
    return filtered_items


def setConfigItem(section, item, value, guild):
    config = loadConfig(guild)
    config.set(section, item, value)
    config.write(open(f'guild_configs/{guild}_config.ini', 'w'))
    return True # Sets a config item and then returns True if successful.


async def log(item, guild):
    logChannel = bot.get_channel(int(getConfigItem('DEFAULT', 'logging', guild)))
    if logChannel is not None:
        try:
            await logChannel.send(item)
        except Exception as e:
            guildObj = bot.get_guild(guild)
            warnings.warn(f"Tried logging a message in Server {guildObj.name}, however the bot encountered an error:\n{e}\nData to be logged: {item}")
            return False
# Tries to get a Logging Channel for the guild. If there is no logging channel or it is unable to find one (i.e it has been deleted), returns gives a warning and returns false.

async def getBulletinChannel(guild):
    bulletinChannel = await bot.get_channel(int(getConfigItem('DEFAULT', 'defaultbulletinchannel')), guild)
    return bulletinChannel
# Gets the bulletinChannel of a server. Returns 'None' if channel is not found.

async def webhookManager(channelID: int, author, embed, files, guild):
    webhooks = getAllConfigItems('WEBHOOKS', guild) # Gets all stored webhook URLs for a guild.
    webhook_url = None
    for w, x in webhooks:
        if int(w) == channelID: # Checks if the channel ID has a webhook, if so sets the webhook_url.
            webhook_url = x

    async with aiohttp.ClientSession() as session: # Opens a session to create a webhook.
        if webhook_url:
            webhook = disnake.Webhook.from_url(webhook_url, session=session) # Gets the existing webhook if it already exists.
            try:
                await webhook.send(embed=embed, files=files, username=author.name, avatar_url=author.display_avatar)
                return
            except disnake.NotFound as nf:
                webhook_url = False
        if not webhook_url:
            channel = bot.get_channel(channelID)
            webhook = await channel.create_webhook(name="Bulletin-Board-Generated Webhook") # Generates the webhook and stores the webhook item if no webhook is found.
            setConfigItem('WEBHOOKS', str(channelID), webhook.url, guild)
            await webhook.send(embed=embed, files=files, username=author.name, avatar_url=author.display_avatar)
            return


@bot.slash_command(description="Registers a Channel as the default Bulletin Channel", name='SetDefaultBulletin',
                   guild_ids=guilds)
@commands.has_permissions(manage_messages=True)
async def defaultchannel(inter, bulletin_channel: disnake.abc.GuildChannel):
    guild = inter.guild_id
    setConfigItem('DEFAULT', 'defaultbulletinchannel', str(bulletin_channel.id), guild)
    await inter.response.send_message(
        f"Channel {bulletin_channel.mention} has been registered as the default Bulletin Board channel.",
        ephemeral=True)
    await log(f"{inter.author} has set {bulletin_channel.mention} as the default Bulletin Board Channel.", guild)


@bot.slash_command(description="Sets the channel where changes are logged.", name='setLoggingChannel', guild_ids=guilds)
@commands.has_permissions(manage_messages=True)
async def logger(inter, logging_channel: disnake.abc.GuildChannel):
    guild = inter.guild_id
    try:
        await logging_channel.send(f"{inter.author} has set this channel as the default bot logging channel.")
    except Exception as e:
        await inter.response.send_message(
            "Unable to set this channel as the Logging Channel! This bot does not have permissions to send messages there. Check your permissions and try again.",
            ephemeral=True)
        return
    await log(f"{inter.author} has set {logging_channel.mention} for all future bot logs.", guild)
    setConfigItem('DEFAULT', 'logging', str(logging_channel.id), guild)
    await inter.response.send_message(
        f"Channel {logging_channel.mention} has been set as the default channel for all bot logs.", ephemeral=True)


@bot.slash_command(description="Sets a command to be monitored for Bulletin Board Pins", name='register',
                   guild_ids=guilds)
@commands.has_permissions(manage_messages=True)
async def register(inter, channel: disnake.abc.GuildChannel, to_bulletin_channel: disnake.abc.GuildChannel = None):
    guild = inter.guild_id
    defaultbulletin = getConfigItem("DEFAULT", "defaultbulletinchannel", guild)

    chID = channel.id
    remove = False
    listChannels = getAllConfigItems("MONITORED_CHANNELS", guild=guild)
    for i, unused in listChannels:
        if int(i) == chID:
            remove = True

    if remove:
        removeConfigItem("MONITORED_CHANNELS", str(chID), guild=guild)
        await inter.response.send_message(f"Channel {channel.mention} has been removed from pin monitoring.", ephemeral=True)
        await log(f'{inter.author.name} has removed {channel.mention} from pin monitoring.', guild)
        return

    try:
        testcase = await channel.pins()
    except Exception as e:
        await inter.response.send_message("The bot does not appear to have access to that channel to monitor its pins! Please check the permissions and try again.", ephemeral=True)
        return

    if not to_bulletin_channel:

        if int(defaultbulletin) == 0:
            await inter.response.send_message("This server does not have a default bulletin channel setup! Please set a channel as default by doing `/setdefaultbulletin <channel>` or by specifying what channel you want to divert overflow pins to!", ephemeral=True)
            return

        await log(
            f"{inter.author} registered channel {channel.mention}'s overflow pins to be posted to the Default Bulletin Board.", guild)
        line = 'the Default Bulletin Board'
        to_bulletin_channel = ''
    else:
        await log(
            f"{inter.author} registered channel {channel.mention}'s overflow pins to be posted to {to_bulletin_channel.mention}", guild)
        line = f'{to_bulletin_channel.mention}'
        to_bulletin_channel = str(to_bulletin_channel.id)
    setConfigItem('MONITORED_CHANNELS', str(channel.id), to_bulletin_channel, guild=guild)
    await inter.response.send_message(f"Overflow Pins in {channel.mention} will now be sent to {line}", ephemeral=True)


@bot.slash_command(description="Lists all of the locked pins in a channel.", name='list', guild_ids=guilds)
@commands.has_permissions(manage_messages=True)
async def listItems(inter, channel:disnake.abc.GuildChannel):
    guild = inter.guild_id
    allMessages = getAllConfigItems('MONITORED_MESSAGES', guild)
    msgList = []
    for msg, ch in allMessages:
        if int(ch) == channel.id:
            msgList.append(int(msg))

    if len(msgList) == 0:
        inter.response("There are no locked pins in this channel!")

    messageListURL = []
    for m in msgList:
        message = await channel.fetch_message(m)
        if message is None:
            removeConfigItem('MONITORED_MESSAGES', str(m), guild)
            continue
        url = message.jump_url
        messageListURL.append(url)

    urlString = ''
    for mu in messageListURL:
        urlString = f'{urlString}{mu}\n'
    urlString.rstrip()
    await inter.response.send_message(f"Here are all the Locked Pins in {channel.mention}:\n{urlString}")


@bot.slash_command(description='Adds or removes a message from the Locked Pins.', name='lock', guild_ids=guilds)
@commands.has_permissions(manage_messages=True)
async def padlock(inter, message: disnake.Message):
    guild = inter.guild_id
    channel = message.channel
    monitored_messages = getAllConfigItems('MONITORED_MESSAGES', guild)
    monitoredMSGs = []
    for msg, bu in monitored_messages:
        monitoredMSGs.append(int(msg))

    if message.id not in monitoredMSGs:
        curChannelItems = []
        for msg, ch in monitored_messages:
            if int(ch) == message.channel.id:
                curChannelItems.append(int(ch))
        if len(curChannelItems) >= 10:
            await inter.send("You can only have 10 locked messages in a channel! You must unlock a pinned message before you can lock any more!", ephemeral=True)
            return

        setConfigItem('MONITORED_MESSAGES', str(message.id), str(channel.id), guild)
        await inter.send("Message added to the Locked Pins list.", ephemeral=True)
        await log(f"{inter.author.name} added a message to the Locked Pins in {message.channel.mention}", guild=guild)
        await message.unpin()
        await message.pin()
    else:
        removeConfigItem("MONITORED_MESSAGES", str(message.id), guild)
        await inter.send("Message removed from the Locked Pins list.", ephemeral=True)
        await log(f"{inter.author.name} removed a message from the Locked Pins in {message.channel.mention}", guild=guild)


@bot.listen()
async def on_slash_command_error(ctx, error):
    if isinstance(error.original, disnake.ext.commands.MessageNotFound):
        await ctx.send("That isn't a valid message!", ephemeral=True)
        return
    if isinstance(error.original, disnake.ext.commands.ChannelNotReadable):
        await ctx.send("The bot can't read the specified channel! Please check the permissions and try again!", ephemeral=True)
        return
    await ctx.send(error, ephemeral=True)


def JsonHandler(channelid, action, data=None, guild=None):

    if not os.path.exists(f'tracked_pins/{guild}'):
        try:
            os.makedirs(f'tracked_pins/{guild}')
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    if action == 'set':
        with open(f'tracked_pins/{guild}/{channelid}.json', 'w+') as file:
            file.write(json.dumps(data))
    elif action == 'get':
        try:
            with open(f'tracked_pins/{guild}/{channelid}.json', 'r') as file:
                data = json.loads(file.read())
                return data
        except FileNotFoundError:
            return []


@bot.listen()
async def on_guild_channel_pins_update(channel, last_pin):
    guild = channel.guild.id
    storedPins = JsonHandler(channel.id, 'get', guild=guild)
    currentPins = await channel.pins()
    cPinIDs = []
    for p in currentPins:
        cPinIDs.append(p.id)

    if len(storedPins) > len(currentPins):
        JsonHandler(channel.id, 'set', cPinIDs, guild=guild)
    elif len(currentPins) > len(storedPins):
        allMonitored = getAllConfigItems('MONITORED_MESSAGES', guild)
        channelMonitored = []
        for m, c in allMonitored:
            if int(c) == channel.id:
                channelMonitored.append(m)

        if len(channelMonitored) == 0 or str(cPinIDs[0]) in channelMonitored:
            return

        for i in channelMonitored:
            msgID = int(i)
            message = await channel.fetch_message(msgID)
            if message is None:
                removeConfigItem('MONITORED_MESSAGES', str(m), guild=guild)
                continue
            await message.unpin()
            await message.pin()
    else:
        pass

    JsonHandler(channel.id, 'set', cPinIDs, guild)

    monitorList = getAllConfigItems('MONITORED_CHANNELS', guild=guild)
    monitoredChannels = []
    for ch, bu in monitorList:
        monitoredChannels.append(int(ch))

    if channel.id in monitoredChannels:
        pinList = await channel.pins()
        if len(pinList) >= 50:
            oldest_pin = pinList[len(pinList) - 1] # Gets the last pin (oldest) Message.
            author = oldest_pin.author
            channel = oldest_pin.channel
            pbChannel = getConfigItem('MONITORED_CHANNELS', str(channel.id), guild=guild) # Returns the Bulletin Board channel. If

            attachments = oldest_pin.attachments
            if pbChannel == '':
                pbChannel = bot.get_channel(int(getConfigItem("DEFAULT", "defaultbulletinchannel", guild=guild)))
            else:
                pbChannel = bot.get_channel(int(pbChannel))

            if pbChannel is None:
                await log("The Bulletin Board Channel has been deleted or cannot be accessed by the bot! Please verify the channel exists and the Bot has permissions to access it. The bot will not function correctly.\nIf the channel does not exist, please set one using `/setdefaultbulletin`", guild)
                return

            embed = disnake.Embed(color=0xe100e1, title=f'{author}:', description=f'{oldest_pin.content}',
                                  url=oldest_pin.jump_url)
            old_time = oldest_pin.created_at
            strf_old = old_time.strftime("%B %d, %Y")
            embed.set_thumbnail(author.display_avatar)
            embed.set_footer(text=f"Sent by {author} on {strf_old}")

            # Attachments - Downloads attachments to tempfiles, uploads them then deletes them.

            dFiles = None

            if len(attachments) > 0:
                dFiles = []
                for f in attachments:
                    url = f.url
                    filename = f.filename
                    r = requests.get(url, allow_redirects=False)
                    with open(f'tempfiles/{filename}', 'wb') as file:
                        file.write(r.content)
                    with open(f'tempfiles/{filename}', 'rb') as file:
                        convFile = disnake.File(file)
                        dFiles.append(convFile)

            await webhookManager(pbChannel.id, author, embed=embed, files=dFiles, guild=guild)
            await oldest_pin.unpin()
            files = glob.glob('/tempfiles/*')
            for f in files:
                os.remove(f)

    files = glob.glob('/tempfiles/*')
    for f in files:
        os.remove(f)

with open('token.txt', 'r') as file:
    token = file.read()
bot.run(token)
