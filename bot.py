from flask import Flask
import discord
from discord.ext import commands
import os
import threading

# --- CONFIG ---
NOM_AGENCE = "RAMANE OFM - MEDIA DISTRIBUTION"
TOKEN = os.getenv("DISCORD_TOKEN")

# --- FLASK POUR RESTER EN LIGNE H24 SUR RENDER ---
app = Flask(__name__)

@app.route('/')
def home():
    return f"{NOM_AGENCE} - Bot en ligne !"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# --- BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user} - {NOM_AGENCE}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="MEDIA DISTRIBUTION"))

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong ! {NOM_AGENCE} est en ligne ✅")

@bot.command()
async def media(ctx, *, lien=""):
    if not lien:
        await ctx.send("Envoie un lien YouTube / Drive boss !")
        return
    await ctx.send(f"📥 **{NOM_AGENCE}** a reçu ton média : {lien}\nDistribution en cours...")

# --- LANCEMENT ---
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("ERREUR: DISCORD_TOKEN non défini sur Render !")
