import asyncio
import discord
import random
import scrims
from discord.ext import commands

class VoiceEntry:
    def __init__(self, message, player):
        self.requester = message.author
        self.channel = message.channel
        self.player = player

    def __str__(self):
        fmt = '*{0.title}* uploaded by {0.uploader} and requested by {1.display_name}'
        duration = self.player.duration
        if duration:
            fmt = fmt + ' [length: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))
        return fmt.format(self.player, self.requester)

class VoiceState:
    def __init__(self, bot):
        self.current = None
        self.voice = None
        self.bot = bot
        self.play_next_song = asyncio.Event()
        self.songs = asyncio.Queue()
        self.skip_votes = set() # a set of user_ids that voted
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())

    def is_playing(self):
        if self.voice is None or self.current is None:
            return False

        player = self.current.player
        return not player.is_done()

    @property
    def player(self):
        return self.current.player

    def skip(self):
        self.skip_votes.clear()
        if self.is_playing():
            self.player.stop()

    def toggle_next(self):
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)

    async def audio_player_task(self):
        while True:
            self.play_next_song.clear()
            self.current = await self.songs.get()
            await self.bot.send_message(self.current.channel, 'Now playing ' + str(self.current))
            self.current.player.start()
            await self.play_next_song.wait()

class Music:
    """Voice related commands.
    Works in multiple servers at once.
    """
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, server):
        state = self.voice_states.get(server.id)
        if state is None:
            state = VoiceState(self.bot)
            self.voice_states[server.id] = state

        return state

    async def create_voice_client(self, channel):
        voice = await self.bot.join_voice_channel(channel)
        state = self.get_voice_state(channel.server)
        state.voice = voice

    def __unload(self):
        for state in self.voice_states.values():
            try:
                state.audio_player.cancel()
                if state.voice:
                    self.bot.loop.create_task(state.voice.disconnect())
            except:
                pass

    @commands.command(pass_context=True, no_pm=True)
    async def join(self, ctx, *, channel : discord.Channel):
        """Joins a voice channel."""
        try:
            await self.create_voice_client(channel)
        except discord.ClientException:
            await self.bot.say('Already in a voice channel...')
        except discord.InvalidArgument:
            await self.bot.say('This is not a voice channel...')
        else:
            await self.bot.say('Ready to play audio in ' + channel.name)
    
    @commands.command(pass_context=True, no_pm=True)
    async def summon(self, ctx):
        """Summons the bot to join your voice channel."""
        summoned_channel = ctx.message.author.voice_channel
        if summoned_channel is None:
            await self.bot.say('You are not in a voice channel.')
            return False

        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            state.voice = await self.bot.join_voice_channel(summoned_channel)
        else:
            await state.voice.move_to(summoned_channel)

        return True

    @commands.command(pass_context=True, no_pm=True)
    async def play(self, ctx, *, song : str):
        """Plays a song.
        If there is a song currently in the queue, then it is
        queued until the next song is done playing.
        This command automatically searches as well from YouTube.
        The list of supported sites can be found here:
        https://rg3.github.io/youtube-dl/supportedsites.html
        """
        state = self.get_voice_state(ctx.message.server)
        opts = {
            'default_search': 'auto',
            'quiet': True,
        }

        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return

        try:
            player = await state.voice.create_ytdl_player(song, ytdl_options=opts, after=state.toggle_next)
        except Exception as e:
            fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
            await self.bot.send_message(ctx.message.channel, fmt.format(type(e).__name__, e))
        else:
            player.volume = 0.6
            entry = VoiceEntry(ctx.message, player)
            await self.bot.say('Enqueued ' + str(entry))
            await state.songs.put(entry)

    @commands.command(pass_context=True, no_pm=True)
    async def volume(self, ctx, value : int):
        """Sets the volume of the currently playing song."""

        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.volume = value / 100
            await self.bot.say('Set the volume to {:.0%}'.format(player.volume))

    @commands.command(pass_context=True, no_pm=True)
    async def pause(self, ctx):
        """Pauses the currently played song."""
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.pause()

    @commands.command(pass_context=True, no_pm=True)
    async def resume(self, ctx):
        """Resumes the currently played song."""
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.resume()

    @commands.command(pass_context=True, no_pm=True)
    async def stop(self, ctx):
        """Stops playing audio and leaves the voice channel.
        This also clears the queue.
        """
        server = ctx.message.server
        state = self.get_voice_state(server)

        if state.is_playing():
            player = state.player
            player.stop()

        try:
            state.audio_player.cancel()
            del self.voice_states[server.id]
            await state.voice.disconnect()
        except:
            pass

    @commands.command(pass_context=True, no_pm=True)
    async def skip(self, ctx):
        """Vote to skip a song. The song requester can automatically skip.
        3 skip votes are needed for the song to be skipped.
        """

        state = self.get_voice_state(ctx.message.server)
        if not state.is_playing():
            await self.bot.say('Not playing any music right now...')
            return

        voter = ctx.message.author
        if voter == state.current.requester:
            await self.bot.say('Requester requested skipping song...')
            state.skip()
        elif voter.id not in state.skip_votes:
            state.skip_votes.add(voter.id)
            total_votes = len(state.skip_votes)
            if total_votes >= 3:
                await self.bot.say('Skip vote passed, skipping song...')
                state.skip()
            else:
                await self.bot.say('Skip vote added, currently at [{}/3]'.format(total_votes))
        else:
            await self.bot.say('You have already voted to skip this song.')

    @commands.command(pass_context=True, no_pm=True)
    async def playing(self, ctx):
        """Shows info about the currently played song."""

        state = self.get_voice_state(ctx.message.server)
        if state.current is None:
            await self.bot.say('Not playing anything.')
        else:
            skip_count = len(state.skip_votes)
            await self.bot.say('Now playing {} [skips: {}/3]'.format(state.current, skip_count))

    @commands.command(pass_context=True, no_pm=True)
    async def fart(self, ctx, channel: discord.Channel):
        """Under Construction"""
        player = voice.create_ffmpeg_player('fart.mp3') #play mp3
        player.start()

class ChatBot:
    """Chat commands"""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, no_pm=False)
    async def hello(self, ctx):
        """Greet your favorite bot"""
        name = ctx.message.author.name
        return await self.bot.say("Hello {}!".format(name))

    @commands.command(pass_context=True, no_pm=True)
    async def flipcoin(self, ctx):
        """Totally unbiased coin flip"""
        return await self.bot.say("Killdu Wins!")

    @commands.command(pass_context=True, no_pm=True)
    async def rolldice(self, ctx):
        """Returns random int from 1-6"""
        roll = random.randint(1, 6)
        return await self.bot.say('You rolled a {}'.format(roll))

    @commands.command(pass_context=True, no_pm=True)
    async def choose(self, ctx, choices : str):
        """Picks random option !choose opt1 opt2 ..."""
        return await self.bot.say(random.choice(choices))

    @commands.command(pass_context=True, no_pm=True)
    async def memeME(self, ctx, *args):
        """Posts a random meme from the meme library"""
        lines = open('memeLib.txt').read().splitlines()
        myline = random.choice(lines)
        return await self.bot.say(myline)

    @commands.command(pass_context=True, no_pm=True)
    async def addmeme(self, ctx):
        """Add a URL to the meme library"""
        with open('memeLib.txt', 'a') as file:
            s = list(ctx.message.content) #converts message into a l-i-s-t of chars
            while (s[0] != ' '): #deletes characters up till the first space to remove command form context
                s.pop(0)
            s.pop(0)
            newS = ''.join(s)
            file.write('\n')
            file.write(newS)
        return await self.bot.say('Your meme was successfully added')

    @commands.command(pass_context=True, no_pm=True)
    async def delmsgs(self, ctx, *args):
        """deletes the last (ammount) of messages"""
        try:
            ammount = int(args[0]) + 1 if len(args) > 0 else 2
        except:
            await self.bot.send_message(ctx.message.channel, embed=discord.Embed(color=discord.Color.red(), descrition="Please enter a valid value for message ammount!"))
            return

        cleared = 0
        failed = 0

        async for m in self.bot.logs_from(ctx.message.channel, limit=ammount):
            try:
                await self.bot.delete_message(m)
                cleared += 1
            except:
                failed += 1
                pass

        failed_str = "\n\nFailed to clear %s message(s)." % failed if failed > 0 else ""
        returnmsg = await self.bot.send_message(ctx.message.channel, embed=discord.Embed(color=discord.Color.blue(), description="Cleared %s message(s).%s" % (cleared, failed_str)))
        await asyncio.sleep(4)
        await self.bot.delete_message(returnmsg)

    @commands.command(pass_context=True, no_pm=True)
    async def esportsready(self, ctx, *args):
        """Posts oversized "esports ready" emote"""
        async for m in self.bot.logs_from(ctx.message.channel, limit=1):
            await self.bot.delete_message(m)
        return await self.bot.say("https://cdn.discordapp.com/attachments/364645055841173505/368252323044261888/eSportsReady.png")

    @commands.command(pass_context=True, no_pm=True)
    async def parkour(self, ctx):
        """Parkour"""
        del1(ctx)
        return await self.bot.say("Hardcore Parkour! https://www.youtube.com/watch?v=0Kvw2BPKjz0")

    @commands.command(pass_context=True, no_pm=False)
    async def LFS(self, ctx, start="", end="", dayofweek=""):
        name = ctx.message.author
        await insert-scrim(name, start, end, dayofweek)