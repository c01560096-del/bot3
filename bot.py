import discord
from discord.ext import commands, tasks
import json
import os
import random
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Database
DATA_FILE = "bot_data.json"

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({
            "users": {},
            "reaction_roles": {},
            "settings": {"xp_rate": 10, "voice_xp": 5}
        }, f, indent=4)

def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Rank Card
async def create_rank_card(member, level, xp, max_xp):
    try:
        bg = Image.new("RGB", (800, 300), color="#2c2f33")
        draw = ImageDraw.Draw(bg)
        
        # Background
        draw.rectangle([0, 0, 800, 300], fill="#23272a")
        
        # Avatar
        avatar_url = str(member.display_avatar.url).replace("?size=1024", "?size=256")
        response = requests.get(avatar_url)
        avatar = Image.open(BytesIO(response.content)).resize((150, 150)).convert("RGBA")
        bg.paste(avatar, (50, 75), avatar)
        
        # Text
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
        
        draw.text((230, 70), f"{member.display_name}", fill="white", font=font_large)
        draw.text((230, 120), f"Level {level}", fill="#00ff00", font=font_large)
        draw.text((230, 160), f"XP: {xp} / {max_xp}", fill="white", font=font_small)
        
        # Progress Bar
        progress = min(xp / max_xp, 1)
        draw.rectangle([230, 200, 730, 230], fill="#444444")
        draw.rectangle([230, 200, 230 + int(500 * progress), 230], fill="#00ff00")
        
        filename = f"rank_{member.id}.png"
        bg.save(filename)
        return filename
    except Exception as e:
        print(f"Rank card error: {e}")
        return None

@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online!")
    await bot.change_presence(activity=discord.Game("Leveling Up!"))

# Message + Reaction XP
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    data = load_data()
    gid = str(message.guild.id)
    uid = str(message.author.id)

    if gid not in data["users"]:
        data["users"][gid] = {}
    if uid not in data["users"][gid]:
        data["users"][gid][uid] = {"xp": 0, "level": 1, "last_daily": None}

    # Message XP
    data["users"][gid][uid]["xp"] += data["settings"]["xp_rate"] + random.randint(1, 5)

    # Level Up
    user = data["users"][gid][uid]
    xp_needed = user["level"] * 100

    if user["xp"] >= xp_needed:
        old_level = user["level"]
        user["level"] += 1
        await message.channel.send(f"🎉 **LEVEL UP!** {message.author.mention} → **Level {user['level']}**!")

    save_data(data)
    await bot.process_commands(message)

# Reaction XP
@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    data = load_data()
    gid = str(reaction.message.guild.id)
    uid = str(user.id)
    if gid in data["users"] and uid in data["users"][gid]:
        data["users"][gid][uid]["xp"] += 5
        save_data(data)

# Rank Command
@bot.command()
async def rank(ctx):
    data = load_data()
    gid = str(ctx.guild.id)
    uid = str(ctx.author.id)

    if gid in data["users"] and uid in data["users"][gid]:
        user = data["users"][gid][uid]
        level = user["level"]
        xp = user["xp"]
        max_xp = level * 100

        card = await create_rank_card(ctx.author, level, xp, max_xp)
        if card:
            await ctx.send(file=discord.File(card))
            os.remove(card)
        else:
            await ctx.send(f"**{ctx.author.name}** | Level: **{level}** | XP: **{xp}/{max_xp}**")
    else:
        await ctx.send("ඔබට තවම XP නැහැ! මැසේජ් ටයිප් කරන්න.")

# Leaderboard
@bot.command()
async def leaderboard(ctx):
    data = load_data()
    gid = str(ctx.guild.id)
    if gid not in data["users"]:
        return await ctx.send("No data yet!")

    users = sorted(data["users"][gid].items(), key=lambda x: x[1]["level"], reverse=True)[:10]
    
    embed = discord.Embed(title="🏆 Server Leaderboard", color=0x7289da)
    for i, (uid, info) in enumerate(users, 1):
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else "Unknown"
        embed.add_field(name=f"#{i} {name}", value=f"Level {info['level']} | XP {info['xp']}", inline=False)
    await ctx.send(embed=embed)

# Welcomer
@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name="welcome")
    if channel:
        embed = discord.Embed(
            title="Welcome to the Server! 🎉",
            description=f"{member.mention}\nWe're glad you're here!",
            color=0x00ff00
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

# Daily Reward
@bot.command()
async def daily(ctx):
    data = load_data()
    gid = str(ctx.guild.id)
    uid = str(ctx.author.id)
    user = data["users"].get(gid, {}).get(uid)

    if not user:
        return await ctx.send("ඔබේ data නැහැ.")

    now = datetime.now()
    last = user.get("last_daily")
    
    if last and (now - datetime.fromisoformat(last)).total_seconds() < 86400:  # 24 hours
        return await ctx.send("ඔබ දැනටමත් Daily Reward ගත්තා. 24 පැයකට පස්සේ උත්සාහ කරන්න.")
    
    user["xp"] += 100
    user["last_daily"] = now.isoformat()
    save_data(data)
    await ctx.send(f"✅ {ctx.author.mention} ඔබට **Daily Reward** ලැබුණා! +100 XP")

# Admin Commands
@bot.command()
@commands.has_permissions(administrator=True)
async def setxprate(ctx, amount: int):
    data = load_data()
    data["settings"]["xp_rate"] = amount
    save_data(data)
    await ctx.send(f"Message XP rate සකසා ඇත: **{amount}**")

@bot.command()
@commands.has_permissions(administrator=True)
async def setvoicexp(ctx, amount: int):
    data = load_data()
    data["settings"]["voice_xp"] = amount
    save_data(data)
    await ctx.send(f"Voice XP rate සකසා ඇත: **{amount}**")

# Run Bot
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ BOT_TOKEN Environment Variable එක හමුවේ නැහැ!")
else:
    bot.run(TOKEN)
