﻿#Import
import time
startupTime_start = time.time()
import aiohttp
import asyncio
import datetime
import discord
import json
import jsonschema
import os
import platform
import psutil
import re
import sentry_sdk
import signal
import sys
from CustomModules import hercules
from CustomModules import log_handler
from dotenv import load_dotenv
from typing import Optional, Any, Union, Tuple
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile



#Init
discord.VoiceClient.warn_nacl = False
load_dotenv()
APP_FOLDER_NAME = 'Hercules-Bot'
BOT_NAME = 'Hercules'
os.makedirs(f'{APP_FOLDER_NAME}//Logs', exist_ok=True)
os.makedirs(f'{APP_FOLDER_NAME}//Buffer', exist_ok=True)
LOG_FOLDER = f'{APP_FOLDER_NAME}//Logs//'
BUFFER_FOLDER = f'{APP_FOLDER_NAME}//Buffer//'
ACTIVITY_FILE = f'{APP_FOLDER_NAME}//activity.json'
BOT_VERSION = "1.0.0"
sentry_sdk.init(
    dsn=os.getenv('SENTRY_DSN'),
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    environment='Production',
    release=f'{BOT_NAME}@{BOT_VERSION}'
)

#Load env
TOKEN = os.getenv('TOKEN')
OWNERID = os.getenv('OWNER_ID')
LOG_LEVEL = os.getenv('LOG_LEVEL')

#Logger init
log_manager = log_handler.LogManager(LOG_FOLDER, BOT_NAME, LOG_LEVEL)
discord_logger = log_manager.get_logger('discord')
program_logger = log_manager.get_logger('Program')
program_logger.info('Engine powering up...')

obfuscator = hercules.Hercules(program_logger)

#Create activity.json if not exists
class JSONValidator:
    schema = {
        "type" : "object",
        "properties" : {
            "activity_type" : {
                "type" : "string",
                "enum" : ["Playing", "Streaming", "Listening", "Watching", "Competing"]
            },
            "activity_title" : {"type" : "string"},
            "activity_url" : {"type" : "string"},
            "status" : {
                "type" : "string",
                "enum" : ["online", "idle", "dnd", "invisible"]
            },
        },
    }

    default_content = {
        "activity_type": "Playing",
        "activity_title": "Made by Serpensin: https://gitlab.bloodygang.com/Serpensin",
        "activity_url": "",
        "status": "online"
    }

    def __init__(self, file_path):
        self.file_path = file_path

    def validate_and_fix_json(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r') as file:
                try:
                    data = json.load(file)
                    jsonschema.validate(instance=data, schema=self.schema)  # validate the data
                except (jsonschema.exceptions.ValidationError, json.decoder.JSONDecodeError) as e:
                    program_logger.error(f'ValidationError: {e}')
                    self.write_default_content()
        else:
            self.write_default_content()

    def write_default_content(self):
        with open(self.file_path, 'w') as file:
            json.dump(self.default_content, file, indent=4)
validator = JSONValidator(ACTIVITY_FILE)
validator.validate_and_fix_json()


class aclient(discord.AutoShardedClient):
    def __init__(self):

        intents = discord.Intents.default()
        intents.guild_messages = True
        #intents.members = True

        super().__init__(owner_id = OWNERID,
                              intents = intents,
                              status = discord.Status.invisible,
                              auto_reconnect = True
                        )
        self.synced = False
        self.initialized = False


    class Presence():
        @staticmethod
        def get_activity() -> discord.Activity:
            with open(ACTIVITY_FILE) as f:
                data = json.load(f)
                activity_type = data['activity_type']
                activity_title = data['activity_title']
                activity_url = data['activity_url']
            if activity_type == 'Playing':
                return discord.Game(name=activity_title)
            elif activity_type == 'Streaming':
                return discord.Streaming(name=activity_title, url=activity_url)
            elif activity_type == 'Listening':
                return discord.Activity(type=discord.ActivityType.listening, name=activity_title)
            elif activity_type == 'Watching':
                return discord.Activity(type=discord.ActivityType.watching, name=activity_title)
            elif activity_type == 'Competing':
                return discord.Activity(type=discord.ActivityType.competing, name=activity_title)

        @staticmethod
        def get_status() -> discord.Status:
            with open(ACTIVITY_FILE) as f:
                data = json.load(f)
                status = data['status']
            if status == 'online':
                return discord.Status.online
            elif status == 'idle':
                return discord.Status.idle
            elif status == 'dnd':
                return discord.Status.dnd
            elif status == 'invisible':
                return discord.Status.invisible


    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError) -> None:
        options = interaction.data.get("options")
        option_values = ""
        if options:
            for option in options:
                option_values += f"{option['name']}: {option['value']}"
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            await interaction.response.send_message(f'This command is on cooldown.\nTime left: `{str(datetime.timedelta(seconds=int(error.retry_after)))}`', ephemeral=True)
        else:
            try:
                try:
                    await interaction.response.send_message(f"Error! Try again.", ephemeral=True)
                except:
                    try:
                        await interaction.followup.send(f"Error! Try again.", ephemeral=True)
                    except:
                        pass
            except discord.Forbidden:
                try:
                    await interaction.followup.send(f"{error}\n\n{option_values}", ephemeral=True)
                except discord.NotFound:
                    try:
                        await interaction.response.send_message(f"{error}\n\n{option_values}", ephemeral=True)
                    except discord.NotFound:
                        pass
                except Exception as e:
                    discord_logger.warning(f"Unexpected error while sending message: {e}")
            finally:
                try:
                    program_logger.warning(f"{error} -> {option_values} | Invoked by {interaction.user.name} ({interaction.user.id}) @ {interaction.guild.name} ({interaction.guild.id}) with Language {interaction.locale[1]}")
                except AttributeError:
                    program_logger.warning(f"{error} -> {option_values} | Invoked by {interaction.user.name} ({interaction.user.id}) with Language {interaction.locale[1]}")
                sentry_sdk.capture_exception(error)

    async def on_guild_join(self, guild):
        if not self.synced:
            return
        discord_logger.info(f'I joined {guild}. (ID: {guild.id})')

    async def on_message(self, message):
        async def __wrong_selection():
            await message.channel.send('```'
                                       'Commands:\n'
                                       'help - Shows this message\n'
                                       'log - Get the log\n'
                                       'activity - Set the activity of the bot\n'
                                       'status - Set the status of the bot\n'
                                       'shutdown - Shutdown the bot\n'
                                       '```')

        if message.guild is None and message.author.id == int(OWNERID):
            args = message.content.split(' ')
            program_logger.debug(args)
            command, *args = args
            if command == 'help':
                await __wrong_selection()
                return
            elif command == 'log':
                await Owner.log(message, args)
                return
            elif command == 'activity':
                await Owner.activity(message, args)
                return
            elif command == 'status':
                await Owner.status(message, args)
                return
            elif command == 'shutdown':
                await Owner.shutdown(message)
                return
            else:
                await __wrong_selection()

    async def on_guild_remove(self, guild):
        if not self.synced:
            return
        program_logger.info(f'I got kicked from {guild}. (ID: {guild.id})')

    async def setup_hook(self):
        global owner, shutdown
        shutdown = False
        try:
            owner = await self.fetch_user(OWNERID)
            if owner is None:
                program_logger.critical(f"Invalid ownerID: {OWNERID}")
                sys.exit(f"Invalid ownerID: {OWNERID}")
        except discord.HTTPException as e:
            program_logger.critical(f"Error fetching owner user: {e}")
            sys.exit(f"Error fetching owner user: {e}")
        discord_logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
        discord_logger.info('Syncing...')
        await tree.sync()
        discord_logger.info('Synced.')
        self.synced = True

    async def on_ready(self):
        await bot.change_presence(activity = self.Presence.get_activity(), status = self.Presence.get_status())
        if self.initialized:
            return
        global start_time
        start_time = datetime.datetime.now(datetime.UTC)
        program_logger.info(f"Initialization completed in {time.time() - startupTime_start} seconds.")
        self.initialized = True
        
bot = aclient()
tree = discord.app_commands.CommandTree(bot)
tree.on_error = bot.on_app_command_error


class SignalHandler:
    def __init__(self):
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        program_logger.info('Received signal to shutdown...')
        bot.loop.create_task(Owner.shutdown(owner))



#Fix error on windows on shutdown
if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())



#Functions
class Functions():
    def format_seconds(seconds):
        years, remainder = divmod(seconds, 31536000)
        days, remainder = divmod(remainder, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if years:
            parts.append(f"{years}y")
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    async def get_or_fetch(item: str, item_id: int) -> Optional[Any]:
        """
        Attempts to retrieve an object using the 'get_<item>' method of the bot class, and
        if not found, attempts to retrieve it using the 'fetch_<item>' method.

        :param item: Name of the object to retrieve
        :param item_id: ID of the object to retrieve
        :return: Object if found, else None
        :raises AttributeError: If the required methods are not found in the bot class
        """
        get_method_name = f'get_{item}'
        fetch_method_name = f'fetch_{item}'

        get_method = getattr(bot, get_method_name, None)
        fetch_method = getattr(bot, fetch_method_name, None)

        if get_method is None or fetch_method is None:
            raise AttributeError(f"Methods {get_method_name} or {fetch_method_name} not found on bot object.")

        item_object = get_method(item_id)
        if item_object is None:
            try:
                item_object = await fetch_method(item_id)
            except discord.NotFound:
                pass
        return item_object

    async def is_valid_url_and_lua_syntax(url: str) -> Tuple[bool, Union[str, None]]:
        url_pattern = re.compile(
            r'^(http|https):\/\/'  # http:// oder https://
            r'(\w+:{0,1}\w*@)?'  # Userdata (optional)
            r'([a-zA-Z0-9.-]+)'  # Domain-Name
            r'(:[0-9]+)?'  # Port (optional)
            r'(\/.*)?$'  # Path (optional)
        )

        if not url_pattern.match(url):
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status not in [200, 204, 301, 302]:
                        return False, None
                    lua_code = await response.text()
                    if obfuscator.isValidLUASyntax(lua_code):
                        return True, lua_code
                    else:
                        return False, None
        except aiohttp.ClientError as e:
            program_logger.error(f"Error fetching URL: {e}")
            return False, None



##Owner Commands
class Owner():
    async def log(message, args):
        async def __wrong_selection():
            await message.channel.send('```'
                                       'log [current/folder/lines] (Replace lines with a positive number, if you only want lines.) - Get the log\n'
                                       '```')
        if args == []:
            await __wrong_selection()
            return
        if args[0] == 'current':
            try:
                await message.channel.send(file=discord.File(f'{LOG_FOLDER}{BOT_NAME}.log'))
            except discord.HTTPException as err:
                if err.status == 413:
                    with ZipFile(f'{BUFFER_FOLDER}Logs.zip', mode='w', compression=ZIP_DEFLATED, compresslevel=9, allowZip64=True) as f:
                        f.write(f'{LOG_FOLDER}{BOT_NAME}.log')
                    try:
                        await message.channel.send(file=discord.File(f'{BUFFER_FOLDER}Logs.zip'))
                    except discord.HTTPException as err:
                        if err.status == 413:
                            await message.channel.send("The log is too big to be sent directly.\nYou have to look at the log in your server (VPS).")
                    os.remove(f'{BUFFER_FOLDER}Logs.zip')
                    return
        elif args[0] == 'folder':
            if os.path.exists(f'{BUFFER_FOLDER}Logs.zip'):
                os.remove(f'{BUFFER_FOLDER}Logs.zip')
            with ZipFile(f'{BUFFER_FOLDER}Logs.zip', mode='w', compression=ZIP_DEFLATED, compresslevel=9, allowZip64=True) as f:
                for file in os.listdir(LOG_FOLDER):
                    if file.endswith(".zip"):
                        continue
                    f.write(f'{LOG_FOLDER}{file}')
            try:
                await message.channel.send(file=discord.File(f'{BUFFER_FOLDER}Logs.zip'))
            except discord.HTTPException as err:
                if err.status == 413:
                    await message.channel.send("The folder is too big to be sent directly.\nPlease get the current file or the last X lines.")
            os.remove(f'{BUFFER_FOLDER}Logs.zip')
            return
        else:
            try:
                if int(args[0]) < 1:
                    await __wrong_selection()
                    return
                else:
                    lines = int(args[0])
            except ValueError:
                await __wrong_selection()
                return
            with open(f'{LOG_FOLDER}{BOT_NAME}.log', 'r', encoding='utf8') as f:
                with open(f'{BUFFER_FOLDER}log-lines.txt', 'w', encoding='utf8') as f2:
                    count = 0
                    for line in (f.readlines()[-lines:]):
                        f2.write(line)
                        count += 1
            await message.channel.send(content=f'Here are the last {count} lines of the current logfile:', file=discord.File(f'{BUFFER_FOLDER}log-lines.txt'))
            if os.path.exists(f'{BUFFER_FOLDER}log-lines.txt'):
                os.remove(f'{BUFFER_FOLDER}log-lines.txt')
            return

    async def activity(message, args):
        async def __wrong_selection():
            await message.channel.send('```'
                                       'activity [playing/streaming/listening/watching/competing] [title] (url) - Set the activity of the bot\n'
                                       '```')
        def isURL(zeichenkette):
            try:
                ergebnis = urlparse(zeichenkette)
                return all([ergebnis.scheme, ergebnis.netloc])
            except:
                return False

        def remove_and_save(liste):
            if liste and isURL(liste[-1]):
                return liste.pop()
            else:
                return None

        if args == []:
            await __wrong_selection()
            return
        action = args[0].lower()
        url = remove_and_save(args[1:])
        title = ' '.join(args[1:])
        program_logger.debug(title)
        program_logger.debug(url)
        with open(ACTIVITY_FILE, 'r', encoding='utf8') as f:
            data = json.load(f)
        if action == 'playing':
            data['activity_type'] = 'Playing'
            data['activity_title'] = title
            data['activity_url'] = ''
        elif action == 'streaming':
            data['activity_type'] = 'Streaming'
            data['activity_title'] = title
            data['activity_url'] = url
        elif action == 'listening':
            data['activity_type'] = 'Listening'
            data['activity_title'] = title
            data['activity_url'] = ''
        elif action == 'watching':
            data['activity_type'] = 'Watching'
            data['activity_title'] = title
            data['activity_url'] = ''
        elif action == 'competing':
            data['activity_type'] = 'Competing'
            data['activity_title'] = title
            data['activity_url'] = ''
        else:
            await __wrong_selection()
            return
        with open(ACTIVITY_FILE, 'w', encoding='utf8') as f:
            json.dump(data, f, indent=2)
        await bot.change_presence(activity = bot.Presence.get_activity(), status = bot.Presence.get_status())
        await message.channel.send(f'Activity set to {action} {title}{" " + url if url else ""}.')

    async def status(message, args):
        async def __wrong_selection():
            await message.channel.send('```'
                                       'status [online/idle/dnd/invisible] - Set the status of the bot\n'
                                       '```')

        if args == []:
            await __wrong_selection()
            return
        action = args[0].lower()
        with open(ACTIVITY_FILE, 'r', encoding='utf8') as f:
            data = json.load(f)
        if action == 'online':
            data['status'] = 'online'
        elif action == 'idle':
            data['status'] = 'idle'
        elif action == 'dnd':
            data['status'] = 'dnd'
        elif action == 'invisible':
            data['status'] = 'invisible'
        else:
            await __wrong_selection()
            return
        with open(ACTIVITY_FILE, 'w', encoding='utf8') as f:
            json.dump(data, f, indent=2)
        await bot.change_presence(activity = bot.Presence.get_activity(), status = bot.Presence.get_status())
        await message.channel.send(f'Status set to {action}.')

    async def shutdown(message):
        global shutdown
        _message = 'Engine powering down...'
        program_logger.info(_message)
        try:
            await message.channel.send(_message)
        except:
            await owner.send(_message)
        await bot.change_presence(status=discord.Status.invisible)
        shutdown = True

        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        await asyncio.gather(*tasks, return_exceptions=True)

        await bot.close()



##Bot Commands
#Ping
@tree.command(name = 'ping', description = 'Test, if the bot is responding.')
@discord.app_commands.checks.cooldown(1, 30, key=lambda i: (i.user.id))
async def self(interaction: discord.Interaction):
    before = time.monotonic()
    await interaction.response.send_message('Pong!')
    ping = (time.monotonic() - before) * 1000
    await interaction.edit_original_response(content=f'Pong! \nCommand execution time: `{int(ping)}ms`\nPing to gateway: `{int(bot.latency * 1000)}ms`')


#Bot Info
@tree.command(name = 'botinfo', description = 'Get information about the bot.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
async def self(interaction: discord.Interaction):
    member_count = sum(guild.member_count for guild in bot.guilds)

    embed = discord.Embed(
        title=f"Informationen about {bot.user.name}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else '')

    embed.add_field(name="Created at", value=bot.user.created_at.strftime("%d.%m.%Y, %H:%M:%S"), inline=True)
    embed.add_field(name="Bot-Version", value=BOT_VERSION, inline=True)
    embed.add_field(name="Uptime", value=str(datetime.timedelta(seconds=int((datetime.datetime.now(datetime.UTC) - start_time).total_seconds()))), inline=True)

    embed.add_field(name="Bot-Owner", value=f"<@!{OWNERID}>", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(name="Server", value=f"{len(bot.guilds)}", inline=True)
    embed.add_field(name="Member count", value=str(member_count), inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(name="Shards", value=f"{bot.shard_count}", inline=True)
    embed.add_field(name="Shard ID", value=f"{interaction.guild.shard_id if interaction.guild else 'N/A'}", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(name="Python-Version", value=f"{platform.python_version()}", inline=True)
    embed.add_field(name="discord.py-Version", value=f"{discord.__version__}", inline=True)
    embed.add_field(name="Sentry-Version", value=f"{sentry_sdk.consts.VERSION}", inline=True)

    embed.add_field(name="Repo", value=f"[GitLab](https://gitlab.bloodygang.com/Serpensin/Discord-Bot-Base)", inline=True)
    embed.add_field(name="Invite", value=f"[Invite me](https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot)", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    if interaction.user.id == int(OWNERID):
        # Add CPU and RAM usage
        process = psutil.Process(os.getpid())
        cpu_usage = process.cpu_percent()
        ram_usage = round(process.memory_percent(), 2)
        ram_real = round(process.memory_info().rss / (1024 ** 2), 2)

        embed.add_field(name="CPU", value=f"{cpu_usage}%", inline=True)
        embed.add_field(name="RAM", value=f"{ram_usage}%", inline=True)
        embed.add_field(name="RAM", value=f"{ram_real} MB", inline=True)

    await interaction.response.send_message(embed=embed)


#Help
@tree.command(name = 'help', description = 'Explains how to use this obfuscator.')
@discord.app_commands.checks.cooldown(1, 30, key=lambda i: (i.user.id))
async def self(interaction: discord.Interaction):
    embed = discord.Embed(
    title="Hercules Bot - Help",
    description="Your trusty bot for obfuscating Lua files 💪",
    color=discord.Color.blue()
    )    
    embed.add_field(
        name="/obfuscate_url [url]",
        value="Submit a URL (e.g. from pastebin) containing a Lua file. Hercules will process and obfuscate it.",
        inline=False
    )   
    embed.add_field(
        name="/obfuscate_file [file]",
        value="Upload a `.lua` file along with this command. Hercules will add it to the queue and notify you once it's done.",
        inline=False
    ) 
    embed.set_footer(text="Happy obfuscating! 🛡️")
    await interaction.response.send_message(embed=embed)




##Obfucation Commands
#View
class ModeSelectionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.selected_bits = (1 << len(obfuscator.methods)) - 1  # Setzt alle Bits auf 1
        self.create_buttons()

    def toggle_bit(self, bit_position):
        self.selected_bits ^= (1 << bit_position)

    def create_buttons(self):
        for method, bit_position in obfuscator.methods.items():
            is_selected = self.selected_bits & (1 << bit_position) != 0
            button = self.MethodButton(label=method, bit_position=bit_position, selected=is_selected)
            self.add_item(button)

    class MethodButton(discord.ui.Button):
        def __init__(self, label, bit_position, selected=False):
            super().__init__(label=label + (' (Selected)' if selected else ''), style=discord.ButtonStyle.success if selected else discord.ButtonStyle.primary)
            self.bit_position = bit_position

        async def callback(self, interaction: discord.Interaction):
            view = self.view
            if view.selected_bits & (1 << self.bit_position):
                view.toggle_bit(self.bit_position)
                self.label = self.label.replace(' (Selected)', '')
                self.style = discord.ButtonStyle.primary
            else:
                view.toggle_bit(self.bit_position)
                self.label += ' (Selected)'
                self.style = discord.ButtonStyle.success

            await interaction.response.edit_message(view=view)

    @discord.ui.button(label='Submit', style=discord.ButtonStyle.danger)
    async def submit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_bits == 0:
            await interaction.response.send_message("You must select at least one obfuscation method!", ephemeral=True)
        else:
            # Supress "This interaction failed" message
            await interaction.response.edit_message(view=None)
            self.stop()


#Fetch file from URL
@tree.command(name = 'obfuscate_url', description = 'Submit a URL containing a Lua file.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.describe(url = 'The URL of the Lua file.')
async def self(interaction: discord.Interaction, url: str):
    await interaction.response.defer(ephemeral=True)
    valid, lua_code = await Functions.is_valid_url_and_lua_syntax(url)
    if not valid:
        await interaction.edit_original_response(content="The URL is not reachable or does not contain valid Lua syntax.")
        return
    else:
        view = ModeSelectionView()
        await interaction.edit_original_response(content=f"Please select the obfuscation methods you want to use for {url}.", view=view)

        await view.wait()

        selected_bits = view.selected_bits

        file_path = f'{BUFFER_FOLDER}{interaction.user.id}_url.lua'
        with open(file_path, 'w', encoding='utf8') as f:
            f.write(lua_code)

        await interaction.edit_original_response(content=f"Selected bits: {selected_bits:#04b}")

    os.remove(file_path)



#Fetch file from upload
@tree.command(name = 'obfuscate_file', description = 'Upload a Lua file.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.describe(file = 'File to be obfuscated.')
async def self(interaction: discord.Interaction, file: discord.Attachment):
    await interaction.response.defer(ephemeral=True)
    if not file.filename.endswith('.lua'):
        await interaction.edit_original_response(content="Please upload a `.lua` file.")
        return
    if file.size > 1024 * 1024 * 5:
        await interaction.edit_original_response(content="The file is too big. Please upload a file smaller than 5 MB.")
        return

    file_path = f'{BUFFER_FOLDER}{interaction.user.id}_file.lua'
    with open(file_path, 'wb') as f:
        f.write(await file.read())

    with open(file_path, 'r', encoding='utf8') as f:
        lua_code = f.read()

    if not obfuscator.isValidLUASyntax(lua_code):
        await interaction.edit_original_response(content="The uploaded file does not contain valid Lua syntax.")
    else:
        view = ModeSelectionView()
        await interaction.edit_original_response(content=f"Please select the obfuscation methods you want to use for {file.filename}.", view=view)
        await view.wait()

        selected_bits = view.selected_bits
        await interaction.edit_original_response(content=f"Selected bits: {selected_bits:#04b}")

    os.remove(file_path)




if __name__ == '__main__':
    if sys.version_info < (3, 11):
        program_logger.critical('Python 3.11 or higher is required.')
        sys.exit(1)
    if not TOKEN:
        program_logger.critical('Missing token. Please check your .env file.')
        sys.exit()
    else:
        SignalHandler()
        try:
            bot.run(TOKEN, log_handler=None)
        except discord.errors.LoginFailure:
            program_logger.critical('Invalid token. Please check your .env file.')
            sys.exit()
        except asyncio.CancelledError:
            if shutdown:
                pass
