import asyncio
import discord
import secrets
import voice

from discord.ext import commands
from voice import Music, VoiceEntry, VoiceState, ChatBot

if not discord.opus.is_loaded():
    # the 'opus' library here is opus.dll on windows
    # or libopus.so on linux in the current directory
    # you should replace this with the location the
    # opus library is located in and with the proper filename.
    # note that on windows this DLL is automatically provided for you
    discord.opus.load_opus('opus')

bot = commands.Bot(command_prefix=commands.when_mentioned_or('!'), description='A music and chat bot made by Killdu')
bot.add_cog(Music(bot))
bot.add_cog(ChatBot(bot))
    
@bot.event
async def on_ready():
    print('Logged in as:\n{0} (ID: {0.id})'.format(bot.user))

bot.run(secrets.BOT_TOKEN)