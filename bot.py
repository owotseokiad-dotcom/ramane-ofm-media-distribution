from flask import Flask
import discord
from discord.ext import commands
import os
import threading
import asyncio
import aiohttp

# --- CONFIG ---
NOM_AGENCE = "RAMANE OFM - MEDIA DISTRIBUTION"
TOKEN = os.getenv("DISCORD_TOKEN")
FIVESIM_TOKEN = os.getenv("FIVESIM_TOKEN")
MOMO_NUM = "0151824797"
CRYPTO_ADDR = "0x1A93A940fc7C721052001b0f04e1450a9e27E95c"

# --- FLASK POUR RESTER EN LIGNE H24 SUR RENDER ---
app = Flask(__name__)

@app.route('/')
def home():
    return f"{NOM_AGENCE} - Bot en ligne!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== PARTIE QUE TU AS DEMANDÉE - BUSINESS NUMÉROS 200F ==========

# --- VUES / BOUTONS ---
class GenerateView(discord.ui.View):
    def __init__(self, service_type):
        super().__init__(timeout=None)
        self.service_type = service_type

    @discord.ui.button(label="🎲 Générer un numéro", style=discord.ButtonStyle.success, custom_id="generate_num")
    async def generate(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"💳 PAIEMENT 200F - {NOM_AGENCE}",
            description=f"**1. MoMo :** `{MOMO_NUM}`\n**2. Crypto USDT BEP20 :** `{CRYPTO_ADDR}`\n\nEnvoie ta capture de paiement **ICI dans ce salon** après paiement.",
            color=0x00ff00
        )
        embed.set_footer(text=f"Service: {self.service_type} | 200F = Numéro garanti")
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
        await interaction.response.send_message(f"❌ Paiement refusé pour <@{self.client_id}>. Preuve invalide.", ephemeral=False)

    async def lancer_achat_infini(self, interaction):
        if not FIVESIM_TOKEN:
            await interaction.followup.send("ERREUR BOSS: FIVESIM_TOKEN non défini dans Render!", ephemeral=True)
            return

        channel = interaction.channel
        await channel.send(f"✅ Paiement validé par {interaction.user.mention} pour <@{self.client_id}>. Achat en cours sur 5sim... Boucle infinie activée jusqu'à livraison.")

        tentative = 1
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {"Authorization": f"Bearer {FIVESIM_TOKEN}", "Accept": "application/json"}
                    async with session.get(f"https://5sim.net/v1/user/buy/activation/any/any/{self.service_type}", headers=headers) as resp:
                        data = await resp.json()
                        if resp.status!= 200 or "id" not in data:
                            await channel.send(f"❌ Erreur achat 5sim (Tentative {tentative}): {data}. Vérifie ton solde 5sim BOSS. Nouvelle tentative dans 20s...")
                            await asyncio.sleep(20)
                            tentative += 1
                            continue
                        order_id = data["id"]
                        phone = data["phone"]
                        await channel.send(f"✅ **NUMÉRO LIVRÉ (Tentative {tentative}) pour <@{self.client_id}>** : `{phone}` (ID: {order_id}) - J'attends le code...")

                    code = None
                    for _ in range(16):
                        await asyncio.sleep(30)
                        async with session.get(f"https://5sim.net/v1/user/check/{order_id}", headers=headers) as check_resp:
                            check_data = await check_resp.json()
                            if check_data.get("sms") and len(check_data["sms"]) > 0:
                                code = check_data["sms"][0]["code"]
                                break

                    if code:
                        await channel.send(f"📩 **CODE POUR <@{self.client_id}>** : `{code}` - Numéro {phone} - Livraison réussie ✅ BOSS bénéfice 110F")
                        break
                    else:
                        async with session.get(f"https://5sim.net/v1/user/cancel/{order_id}", headers=headers) as cancel_resp:
                            await channel.send(f"⚠️ Pas de code pour ID {order_id} (Tentative {tentative}). CANCEL AUTO fait -> Remboursement 5sim OK. Je rachète un nouveau numéro tout de suite (Tentative {tentative+1})...")
                        tentative += 1
                        await asyncio.sleep(5)
                        continue

            except Exception as e:
                await channel.send(f"Erreur boucle: {e}. Nouvelle tentative dans 10s...")
                await asyncio.sleep(10)
                continue

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user} - {NOM_AGENCE}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="MEDIA DISTRIBUTION"))

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.attachments and ("numéro-gmail" in message.channel.name or "numéro-insta" in message.channel.name):
        service = "google" if "gmail" in message.channel.name else "instagram"
        embed = discord.Embed(
            title="💰 NOUVELLE PREUVE DE PAIEMENT 200F",
            description=f"Client: {message.author.mention}\nSalon: {message.channel.mention}\nService: {service}\n\nBOSS RAMANE, vérifie MoMo {MOMO_NUM} ou Crypto et valide.",
            color=0xffa500
        )
        embed.set_image(url=message.attachments[0].url)
        view = ValidationView(message.author.id, service)
        await message.channel.send(content=f"BOSS RAMANE OFM - Validation requise", embed=embed, view=view)
    await bot.process_commands(message)

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! {NOM_AGENCE} est en ligne ✅")

@bot.command()
async def media(ctx, *, lien=""):
    if not lien:
        await ctx.send("Envoie un lien YouTube / Drive boss!")
        return
    await ctx.send(f"📥 **{NOM_AGENCE}** a reçu ton média : {lien}\nDistribution en cours...")

@bot.command()
async def setupgmail(ctx):
    embed = discord.Embed(
        title="📧 SALON NUMÉROS GMAIL USA - RAMANE OFM",
        description="Ici tu achètes un numéro virtuel USA pour créer ton compte Gmail.\n**Prix : 200F**\n**Comment faire?**\n1. Clique sur 🎲 Générer un numéro ci-dessous\n2. Paye sur MoMo ou Crypto\n3. Envoie ta capture de paiement ICI dans ce salon\n4. Dès que le BOSS RAMANE valide, tu reçois ton numéro + le code SMS ici même automatiquement.\nNe paye pas 2 fois. Un seul paiement = un numéro garanti.",
        color=0x00ff00
    )
    await ctx.send(embed=embed, view=GenerateView("google"))

@bot.command()
async def setupinsta(ctx):
    embed = discord.Embed(
        title="📸 SALON NUMÉROS INSTA USA - RAMANE OFM",
        description="Ici tu achètes un numéro virtuel USA pour créer ton compte Instagram.\n**Prix : 200F**\n**Comment faire?**\n1. Clique sur 🎲 Générer un numéro ci-dessous\n2. Paye sur MoMo ou Crypto\n3. Envoie ta capture de paiement ICI dans ce salon\n4. Dès que le BOSS RAMANE valide, tu reçois ton numéro + le code SMS ici même automatiquement.\nNe paye pas 2 fois. Un seul paiement = un numéro garanti.",
        color=0xE1306C
    )
    await ctx.send(embed=embed, view=GenerateView("instagram"))

@bot.command()
async def code(ctx, order_id: int):
    if not FIVESIM_TOKEN:
        await ctx.send("FIVESIM_TOKEN manquant")
        return
    headers = {"Authorization": f"Bearer {FIVESIM_TOKEN}", "Accept": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://5sim.net/v1/user/check/{order_id}", headers=headers) as resp:
            data = await resp.json()
            await ctx.send(f"Check ID {order_id}: {data}")

# ========== AJOUT DEMANDÉ PAR TOI BOSS - CRÉATION CATÉGORIE AUTO ==========
@bot.command()
@commands.has_permissions(administrator=True)
async def setupbusiness(ctx):
    guild = ctx.guild
    # Crée la catégorie
    category = await guild.create_category("💰 RAMANE OFM - BUSINESS")

    # Overwrites
    overwrites_stock = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True),
        ctx.author: discord.PermissionOverwrite(view_channel=True)
    }
    overwrites_public = {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }

    # 4 Salons dedans comme tu veux
    await guild.create_text_channel("🔒-mon-stock-5sim", category=category, overwrites=overwrites_stock, topic="TON STOCK 5SIM")
    infos = await guild.create_text_channel("📢-infos-paiement", category=category, overwrites=overwrites_public, topic="Paiement 200F")
    await infos.send(f"**💰 RAMANE OFM BUSINESS - 200F / NUMÉRO**\n\n📧 Gmail = 200F\n📸 Insta = 200F\n💳 MoMo: {MOMO_NUM}\nCrypto: {CRYPTO_ADDR}")

    gmail = await guild.create_text_channel("📧-numéro-gmail", category=category, overwrites=overwrites_public)
    await gmail.send(embed=discord.Embed(title="📧 SALON NUMÉROS GMAIL USA - RAMANE OFM", description="Prix 200F - Clique 🎲 - Paye - Envoie preuve ici", color=0x00ff00), view=GenerateView("google"))

    insta = await guild.create_text_channel("📸-numéro-insta", category=category, overwrites=overwrites_public)
    await insta.send(embed=discord.Embed(title="📸 SALON NUMÉROS INSTA USA - RAMANE OFM", description="Prix 200F - Clique 🎲 - Paye - Envoie preuve ici", color=0xE1306C), view=GenerateView("instagram"))

    await ctx.send(f"✅ BOSS C'EST FAIT! Catégorie {category.name} créée avec tout ton business dedans. Nikel.")

# --- LANCEMENT ---
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("ERREUR: DISCORD_TOKEN non défini sur Render!")
