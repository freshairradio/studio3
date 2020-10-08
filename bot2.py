import asyncio

import discord
import youtube_dl
import yaml

from discord.ext import commands

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
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

with open('./config.yaml') as file:
  config = yaml.load(file, Loader=yaml.FullLoader)
  print(config)

voice_channel = None
voice_channel_name = config['player_playout']
voice_client = None
voice_controller = None
voice_controller_name = config['player_control']

playqueue = []

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"),
                description='Relatively simple music bot example')

async def setup_voicechans():
  global voice_channel
  global voice_client
  global voice_controller
  print('Setting up playout voice channel...')

  for channel in bot.guilds[0].channels:
    if channel.name == config['player_playout']:
      voice_channel = channel
    if channel.name == config['player_control']:
      voice_controller = channel

  print(voice_channel)

  print(f'Joining {voice_channel_name}')
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
    play_next()

async def play_next():
  next_track = playqueue.pop(0)
  print(f'attempting to play {next_track["song"].title}')
  print(voice_client)
  voice_client.play(next_track['song'], after=track_finished)
  await voice_controller.send(f'Now playing: {next_track["song"].title}')

@commands.check(check_if_in_controller)
@bot.command(name='play')
async def play(ctx, *, url):
    """Plays from a url (almost anything youtube_dl supports)"""

    async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop)
        playqueue.append({
          'user': ctx.author,
          'song': player
        })

    await ctx.send(f'{ctx.author} added {player.title} to queue.')

    print('check if playing')
    print(voice_client.is_playing())
    if not voice_client.is_playing():
      await play_next()

@commands.check(check_if_in_controller)
@bot.command(name='stop')
async def stop(ctx):
    """Stops and disconnects the bot from voice"""

    await ctx.voice_client.stop()

@bot.command(name='ping')
@commands.has_role('admin')
async def ping(ctx):
    await ctx.send('PONG! Yup, I\'m alive :D')

@play.before_invoke
@stop.before_invoke
async def ensure_voice(ctx):
  if ctx.voice_client is None:
    await setup_voicechans()
  elif ctx.voice_client.is_playing():
    ctx.voice_client.stop()

@bot.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(bot.user))
    print('------')
    await setup_voicechans()

@bot.event
async def on_command_error(ctx, error):
  if isinstance(error, commands.errors.CheckFailure):
    await ctx.send('You do not have the correct role for this command.')

bot.run(config['discord_token'])