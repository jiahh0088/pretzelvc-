import os
import json
import random
import discord
from discord import app_commands
from discord.ext import commands

# Initialize bot with required intents
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

CONFIG_FILE = "config.json"

def load_portal_channel():
    # Priority 1: Check the local JSON config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data.get("portal_channel_id")
        except Exception as e:
            print(f"error loading config file: {e}")
            
    # Priority 2: Fallback to Railway Environment Variable if JSON is wiped
    env_id = os.getenv("PORTAL_CHANNEL_ID")
    if env_id:
        try:
            return int(env_id)
        except ValueError:
            print("error: PORTAL_CHANNEL_ID environment variable must be an integer")
            
    return None

def save_portal_channel(channel_id):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump({"portal_channel_id": channel_id}, f)
    except Exception as e:
        print(f"error saving config file: {e}")

@bot.event
async def on_ready():
    print(f"logged in as {bot.user}")
    try:
        # Sync slash commands globally
        synced = await bot.tree.sync()
        print(f"synced {len(synced)} command(s)")
    except Exception as e:
        print(f"failed to sync commands: {e}")

@bot.tree.command(name="setportal", description="set the random routing voice channel")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="the voice channel to act as the portal")
async def setportal(interaction: discord.Interaction, channel: discord.VoiceChannel):
    save_portal_channel(channel.id)
    await interaction.response.send_message(f"portal channel set to {channel.mention}", ephemeral=True)

@bot.event
async def on_voice_state_update(member, before, after):
    # Ignore bot actions
    if member.bot:
        return

    # Check if a user joined a channel
    if after.channel is None:
        return

    portal_id = load_portal_channel()
    if not portal_id or after.channel.id != portal_id:
        return

    guild = member.guild
    available_channels = []
    
    # Filter valid target voice channels
    for vc in guild.voice_channels:
        if vc.id == portal_id:
            continue
            
        # Check permissions: can the bot connect and move members?
        bot_perms = vc.permissions_for(guild.me)
        if not bot_perms.connect or not bot_perms.move_members:
            continue
            
        # Check if the channel is full (user_limit = 0 means unlimited)
        if vc.user_limit != 0 and len(vc.members) >= vc.user_limit:
            continue
            
        available_channels.append(vc)

    # Handle the "leftover" fallback if no channels are available
    if not available_channels:
        try:
            if member.voice and member.voice.channel:
                await member.move_to(None)
            
            # Ultra-minimalist custom dark embed
            embed = discord.Embed(
                title="/leftover",
                description="disconnected no available channels found",
                color=discord.Color(0x2F3136)
            )
            await member.send(embed=embed)
        except discord.Forbidden:
            print(f"could not send DM to {member.name} or disconnect them (insufficient perms/closed DMs)")
        except Exception as e:
            print(f"error handling disconnect logic: {e}")
        return

    # Weighted random selection (fewer occupants = higher probability)
    # Weights calculated as: 1 / (current_occupants + 1)
    weights = [1 / (len(vc.members) + 1) for vc in available_channels]
    destination = random.choices(available_channels, weights=weights, k=1)[0]

    # Instantly route the user
    try:
        await member.move_to(destination)
    except discord.Forbidden:
        print(f"failed to move {member.name}: missing move_members permission")
    except Exception as e:
        print(f"error routing user: {e}")

# Run bot via environment variable
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("error: DISCORD_TOKEN environment variable not found")
