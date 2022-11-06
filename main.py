import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get
import os
from dotenv import load_dotenv
from paypal_api import PayPalApi
from verify_bot import VerifyBot, AlreadyVerifiedPurchases, AlreadyVerifiedEmail, VerificationFailed

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = [int(os.environ.get("GUILD_ID"))]
REPORT_CHANNEL_ID = int(os.environ.get("REPORT_CHANNEL_ID"))
VERIFY_CHANNEL_ID = int(os.environ.get("VERIFY_CHANNEL_ID"))
ADMIN_ROLE_ID = int(os.environ.get("ADMIN_ROLE_ID"))
ADMIN_ID_LIST = []
if bool(os.environ.get("ADMIN_ID_LIST") and os.environ.get("ADMIN_ID_LIST").strip()):
    ADMIN_ID_LIST = [int(i) for i in os.environ.get("ADMIN_ID_LIST").split(" ")]
APPEAR_OFFLINE = os.getenv("APPEAR_OFFLINE").lower() == "true"
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())
paypal_api = PayPalApi()
verify_bot = VerifyBot(paypal_api)


@bot.event
async def on_message(message):
    if message.author.id == bot.user.id:
        return
    role = discord.utils.get(message.guild.roles, id=ADMIN_ROLE_ID)
    if not hasattr(message.author, "roles"):
        return
    if message.channel.id == VERIFY_CHANNEL_ID and role not in message.author.roles:
        await message.delete()


# discord bot command to add a role to a user
async def add_role(ctx, role_id):
    member = ctx.author
    role = get(member.guild.roles, id=int(role_id))
    await member.add_roles(role)


# send a direct message to a list of admins
async def dm_admins(ctx, email, username, roles_given, verified):
    if verified:
        message = "{} successfully verified a purchase with email: ".format(
            ctx.author.mention) + f"{email} and username: {username}. Given roles: "
        roles = [(get(ctx.guild.roles, id=int(role_id))).name for role_id in roles_given]
        message = message + str(roles)
    else:
        message = "{} failed to verify a purchase with email: ".format(
            ctx.author.mention) + f"{email} and username: {username}"
    for user_id in ADMIN_ID_LIST:
        user = ctx.author.guild.get_member(user_id)
        await user.send(message)


# send a report message into a channel
async def channel_message(author, email, username, roles, verified):
    channel = bot.get_channel(REPORT_CHANNEL_ID)
    roles_message = ""
    if verified:
        embed = discord.Embed(title="Purchase verify of premium plugins",
                              description="Purchase verification completed for {}!".format(author.name),
                              color=0x2ecc71)
        for role_id in roles:
            roles_message = roles_message + f"<@&{role_id}> "
    else:
        embed = discord.Embed(title="Purchase verify of premium plugins",
                              description="Purchase verification failed for {}!".format(author.name),
                              color=0xe74c3c)
    embed.add_field(name="Email", value=email, inline=True)
    embed.add_field(name="Username", value=username, inline=True)
    if verified:
        embed.add_field(name="Roles", value=roles_message, inline=False)
    await channel.send(embed=embed)

# discord event that fires when the bot is ready and listening
@bot.event
async def on_ready():
    logging.basicConfig(handlers=[logging.FileHandler('data/verifybot.log', 'a+', 'utf-8')], level=logging.INFO,
                       format='%(asctime)s: %(message)s')

    if APPEAR_OFFLINE:
        await bot.change_presence(status=discord.Status.offline)

    print("Syncing slash commands...")
    await bot.tree.sync()

    print("The bot is ready!")


# defines a new 'slash command' in discord and what options to show to user for params
@bot.hybrid_command(name="verify", description="Verify your plugins purchase.")
@app_commands.describe(email="Your PayPal email", username="Your SpigotMC or BitByBit username.")
async def _verifypurchase(ctx, email: str, username: str):
    if not (ctx.channel.id == VERIFY_CHANNEL_ID):
        await ctx.reply(f"This command is available only in channel dedicated for verification.", ephemeral=True)
        return

    try:
        roles_to_give = await verify_bot.verify(ctx, email, username)
        if roles_to_give:
            for role in roles_to_give:
                await add_role(ctx, role)
                logging.info(f"{ctx.author.name} given role: " + role)

            await ctx.reply(f"Successfully verified plugin purchase!", ephemeral=True)
            await channel_message(ctx.author, email, username, roles_to_give, True)
            await dm_admins(ctx, email, username, roles_to_give, True)
            logging.info(f"{ctx.author.name} successfully verified their purchase")
            asyncio.create_task(verify_bot.write_out_emails())
    except AlreadyVerifiedPurchases:
        await ctx.reply(f"You have already verified your purchase(s)!", ephemeral=True)
        logging.info(f"{ctx.author.name} already had all verified roles.")
        return
    except AlreadyVerifiedEmail:
        await ctx.reply(f"Purchase already verified with this email!", ephemeral=True)
        logging.info(f"{ctx.author.name} already verified email.")
    except VerificationFailed:
        await ctx.reply("Failed to verify plugin purchase, open a ticket.", ephemeral=True)
        await channel_message(ctx.author, email, username, [], False)
        await dm_admins(ctx, email, username, [], False)
        logging.info(f"{ctx.author.name} failed to verify their purchase")


# run the discord client with the discord token
bot.run(DISCORD_TOKEN)
