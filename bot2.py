import asyncio

import discord
import youtube_dl
import yaml
import glob
import random

from discord.ext import commands

with open('./config.yaml') as file:
  config = yaml.load(file, Loader=yaml.FullLoader)
  print(config)

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0', # bind to ipv4 since ipv6 addresses cause issues sometimes
    'outtmpl': config['ytdl_archive_path']+'/%(title)s.%(ext)s'
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

voice_channel = None
voice_channel_name = config['player_playout']
voice_client = None
voice_controller = None
voice_controller_name = config['player_control']

playqueue = []

played_since_jingle = 0
jingle_every_n_tracks = config['jingle_every_n_tracks']
jingles = []

class YTDLSource():
    def __init__(self, source, *, data):
        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')
        self.source = source

    @classmethod
    async def from_url(cls, url, *, stream=False):
        data = ytdl.extract_info(url, download=not stream)

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

def setup_jingles():
  global jingles
  print(f'Looking for jingles in {config["jingle_search_path"]}...')
  jingles = glob.glob(config['jingle_search_path'])
  print(f'Found {len(jingles)} jingles.')
  pass

bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"),
                description='freshair radio Discord scheduler')

async def setup_voicechans():
  global voice_channel
  global voice_controller
  print('Setting up playout voice channel...')

  for channel in bot.guilds[0].channels:
    if channel.name == config['player_playout']:
      voice_channel = channel
    if channel.name == config['player_control']:
      voice_controller = channel

  print(voice_channel)

async def connect_voice_client():
  global voice_client
  print('Connecting to voice...')
  voice_client = await voice_channel.connect()
  print(voice_client)

async def check_if_in_controller(ctx):
  if ctx.channel.name != voice_controller_name:
    await ctx.send(f'You can\'t do that from here! You need to be in {voice_controller_name} to manage our playlist!')
    return False
  return True

def track_finished(e=None):
  if e:
    print('Player error: %s' % e)
    return
  
  if len(playqueue):
    coro = play_next()
    asyncio.run_coroutine_threadsafe(coro, voice_client.loop)
  else:
    coro = voice_controller.send("No more tracks in the queue... :(")
    asyncio.run_coroutine_threadsafe(coro, voice_client.loop)
    print('Disconnecting from voice...')
    asyncio.run_coroutine_threadsafe(voice_client.disconnect(), voice_client.loop)

async def play_next():
  global played_since_jingle

  if jingle_every_n_tracks <= played_since_jingle:
    print('playing a jingle!')
    played_since_jingle = 0
    if len(jingles) == 0:
      print('No jingles loaded... :(')
    else:
      jingle = random.choice(jingles)
      player = discord.FFmpegPCMAudio(random.choice(jingles), **ffmpeg_options)
      voice_client.play(player, after=track_finished)
      return

  next_track = playqueue.pop(0)
  print(f'attempting to play {next_track["song"].title}')
  voice_client.play(next_track['song'].source, after=track_finished)
  played_since_jingle += 1
  await voice_controller.send(f'Now playing: {next_track["song"].title}')

@commands.check(check_if_in_controller)
@bot.command(name='play')
async def play(ctx, *, url):
    """Plays from a url (almost anything youtube_dl supports)"""

    async with ctx.typing():
        player = await YTDLSource.from_url(url)
        playqueue.append({
          'user': ctx.author,
          'song': player
        })

    await ctx.send(f'{ctx.author} added {player.title} to queue.')

    if not ctx.voice_client.is_playing():
      await play_next()

@commands.check(check_if_in_controller)
@commands.has_role('admin')
@bot.command(name='stop')
async def stop(ctx):
    """Stops current playout and disconnects from voice"""

    await ctx.voice_client.stop()
    await voice_client.disconnect()

@commands.check(check_if_in_controller)
@commands.has_role('committee')
@bot.command(name='skip')
async def skip(ctx):
    """Skips current track"""

    await ctx.voice_client.stop()
    await play_next()
    await ctx.send(f'{ctx.author} has skipped the current track.')

@commands.check(check_if_in_controller)
@commands.has_role('committee')
@bot.command(name='clear')
async def clear(ctx):
    """Stops playout and clears playlist"""

    await ctx.voice_client.stop()
    playqueue = []
    await ctx.send(f'{ctx.author} has cleared the play queue.')

@bot.command(name='ping')
@commands.has_role('admin')
async def ping(ctx):
  """Check the bot is responding..."""
  await ctx.send('PONG! Yup, I\'m alive :D')

@play.before_invoke
@stop.before_invoke
async def ensure_voice(ctx):
  if ctx.voice_client is None:
    await connect_voice_client()

@bot.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(bot.user))
    print('------')
    await setup_voicechans()

@bot.event
async def on_command_error(ctx, error):
  if isinstance(error, commands.errors.CheckFailure):
    await ctx.send('You do not have the correct role for this command.')

setup_jingles()

bot.run(config['discord_token'])