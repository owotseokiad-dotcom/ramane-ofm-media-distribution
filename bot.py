from flask import Flask
import discord
from discord.ext import commands
import os
import threading
import asyncio
import aiohttp

NOM_AGENCE = "RAMANE OFM - MEDIA DISTRIBUTION"
TOKEN = os.getenv("DISCORD_TOKEN")
FIVESIM_TOKEN = os.getenv("FIVESIM_TOKEN")
MOMO_NUM = "0151824797"
CRYPTO_ADDR = "0x1A93A940fc7C721052001b0f04e1450a9e27E95c"

app = Flask(__name__)
@app.route('/')
def home(): return f"{NOM_AGENCE} - Bot en ligne!"
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- VUES CORRIGÉES BOSS - ANTI BUG ---
class GenerateView(discord.ui.View):
    def __init__(self, service_type):
        super().__init__(timeout=None)
        self.service_type = service_type

    @discord.ui.button(label="🎲 Générer un numéro - 200F", style=discord.ButtonStyle.success)
    async def generate(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"💳 PAIEMENT 200F - {NOM_AGENCE}",
            description=f"**Service:** {self.service_type.upper()}\n\n**1. MoMo:** `{MOMO_NUM}`\n**2. USDT BEP20:** `{CRYPTO_ADDR}`\n\nPaye et envoie capture ICI dans ce salon.",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class StockView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="💰 Voir mon solde 5SIM", style=discord.ButtonStyle.primary)
    async def solde(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        headers = {"Authorization": f"Bearer {FIVESIM_TOKEN}", "Accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            async with session.get("https://5sim.net/v1/user/profile", headers=headers) as resp:
                data = await resp.json()
                await interaction.followup.send(f"✅ Solde 5SIM: **{data.get('balance', '0')}$** | 1 numéro = ~0.15$ | Tu revends 200F = 110F bénef", ephemeral=True)
    @discord.ui.button(label="📚 Comment recharger 5SIM?", style=discord.ButtonStyle.secondary)
    async def tuto(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="📚 COMMENT PAYER TES NUMÉROS - BOSS", description="**1.** Va sur 5sim.net\n**2.** Recharge avec Crypto (USDT) min 2$\n**3.** Tu n'as PAS besoin de stock BOSS\nLe bot achète tout seul quand tu valides un client. Boucle infinie jusqu'à livraison du code.", color=0x2b2d31)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ValidationView(discord.ui.View):
    def __init__(self, client_id, service_type):
        super().__init__(timeout=None)
        self.client_id = client_id
        self.service_type = service_type
    @discord.ui.button(label="✅ Reçu MoMo", style=discord.ButtonStyle.success)
    async def momo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.lancer_achat_infini(interaction)
    @discord.ui.button(label="✅ Reçu Crypto", style=discord.ButtonStyle.primary)
    async def crypto(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.lancer_achat_infini(interaction)
    @discord.ui.button(label="❌ Refusé", style=discord.ButtonStyle.danger)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"❌ Paiement refusé pour <@{self.client_id}>", ephemeral=False)

    async def lancer_achat_infini(self, interaction):
        channel = interaction.channel
        await channel.send(f"✅ Validé par {interaction.user.mention} pour <@{self.client_id}>. Achat 5SIM en cours...")
        tentative = 1
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {"Authorization": f"Bearer {FIVESIM_TOKEN}", "Accept": "application/json"}
                    async with session.get(f"https://5sim.net/v1/user/buy/activation/any/any/{self.service_type}", headers=headers) as resp:
                        data = await resp.json()
                        if resp.status!=200 or "id" not in data:
                            await channel.send(f"❌ Erreur 5SIM T{tentative}: {data}. Retente 20s..."); await asyncio.sleep(20); tentative+=1; continue
                        order_id = data["id"]; phone = data["phone"]
                        await channel.send(f"✅ **NUMÉRO LIVRÉ T{tentative} pour <@{self.client_id}>: `{phone}` ID:{order_id} - Attente code...**")
                    code=None
                    for _ in range(16):
                        await asyncio.sleep(30)
                        async with session.get(f"https://5sim.net/v1/user/check/{order_id}", headers=headers) as check_resp:
                            check_data = await check_resp.json()
                            if check_data.get("sms") and len(check_data["sms"])>0:
                                code=check_data["sms"][0]["code"]; break
                    if code:
                        await channel.send(f"📩 **CODE POUR <@{self.client_id}>: `{code}` - Numéro {phone} - Bénéfice 110F ✅**"); break
                    else:
                        async with session.get(f"https://5sim.net/v1/user/cancel/{order_id}", headers=headers):
                            await channel.send(f"⚠️ Pas de code ID {order_id} T{tentative}. CANCEL + RACHAT T{tentative+1}...");
                        tentative+=1; await asyncio.sleep(5); continue
            except Exception as e:
                await channel.send(f"Erreur: {e}"); await asyncio.sleep(10); continue

@bot.event
async def on_ready():
    print(f"Connecté {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="MEDIA DISTRIBUTION"))

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.attachments and ("numéro-gmail" in message.channel.name or "numéro-insta" in message.channel.name):
        service = "google" if "gmail" in message.channel.name else "instagram"
        embed = discord.Embed(title="💰 NOUVELLE PREUVE 200F", description=f"Client: {message.author.mention}\nService: {service}", color=0xffa500)
        embed.set_image(url=message.attachments[0].url)
        await message.channel.send(embed=embed, view=ValidationView(message.author.id, service))
    await bot.process_commands(message)

@bot.command()
async def ping(ctx): await ctx.send(f"Pong! {NOM_AGENCE} ✅")

@bot.command()
@commands.has_permissions(administrator=True)
async def setupbusiness(ctx):
    guild = ctx.guild
    # Supprime ancienne si existe
    for cat in guild.categories:
        if "RAMANE" in cat.name:
            for ch in cat.channels: await ch.delete()
            await cat.delete()

    category = await guild.create_category("💰 RAMANE OFM - BUSINESS")
    overwrites_stock = {guild.default_role: discord.PermissionOverwrite(view_channel=False), guild.me: discord.PermissionOverwrite(view_channel=True), ctx.author: discord.PermissionOverwrite(view_channel=True)}
    overwrites_public = {guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False), guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True), ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True)}

    # 1. TON STOCK PRIVÉ - AVEC BOT DEDANS COMME TU VEUX BOSS
    stock = await guild.create_text_channel("🔒-mon-stock-5sim", category=category, overwrites=overwrites_stock)
    embed_stock = discord.Embed(title="🔒 TON QG PERSO - BOSS RAMANE", description=f"**Ici tu gères ton business 5SIM.**\n\n**Comment ça marche?**\nTu n'as pas besoin de stocker de numéros. Tu recharges juste ton solde sur 5sim.net.\nQuand un client paye 200F, le bot achète 1 numéro (~90F) et te reste 110F de bénef.\n\n**Tuto:** Clique en bas pour voir ton solde et comment recharger.", color=0x2b2d31)
    await stock.send(embed=embed_stock, view=StockView())

    # 2. INFOS PAIEMENT
    infos = await guild.create_text_channel("📢-infos-paiement", category=category, overwrites=overwrites_public)
    await infos.send(embed=discord.Embed(title="💳 PAIEMENT - 200F / NUMÉRO", description=f"**MoMo:** `{MOMO_NUM}`\n**USDT BEP20:** `{CRYPTO_ADDR}`\n\nPaye -> Envoie preuve dans 📧 ou 📸", color=0x00ff00))

    # 3. GMAIL - DESCRIPTION ARRANGÉE
    gmail = await guild.create_text_channel("📧-numéro-gmail", category=category, overwrites=overwrites_public)
    embed_gmail = discord.Embed(
        title="📧 NUMÉRO GMAIL USA - 200F",
        description="**C'est quoi?** Numéro USA pour créer ton Gmail sans ton perso.\n\n**Avantage:**\n✅ Compte USA = + confiance, débloque tout\n✅ 100% anonyme\n✅ Livraison < 5min avec code\n\n**Comment utiliser?**\n1. Clique sur 🎲 en bas\n2. Paye 200F\n3. Envoie capture ICI\n4. Tu reçois numéro + code auto",
        color=0x00ff00
    )
    await gmail.send(embed=embed_gmail, view=GenerateView("google"))

    # 4. INSTA - DESCRIPTION ARRANGÉE
    insta = await guild.create_text_channel("📸-numéro-insta", category=category, overwrites=overwrites_public)
    embed_insta = discord.Embed(
        title="📸 NUMÉRO INSTA USA - 200F",
        description="**C'est quoi?** Numéro USA pour créer ton Insta sans ton perso.\n\n**Avantage:**\n✅ Compte USA = + de portée, pas de blocage\n✅ Parfait pour OFM / Modèle\n✅ Livraison < 5min avec code\n\n**Comment utiliser?**\n1. Clique sur 🎲 en bas\n2. Paye 200F\n3. Envoie capture ICI\n4. Tu reçois numéro + code auto",
        color=0xE1306C
    )
    await insta.send(embed=embed_insta, view=GenerateView("instagram"))
    await ctx.send("✅ C'est fait BOSS. Tout arrangé nikel. Teste 🎲 maintenant.")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    if TOKEN: bot.run(TOKEN)
