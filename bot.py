from flask import Flask
import discord
from discord.ext import commands
import os
import threading
import asyncio
import aiohttp
import time
import json
import re

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

# --- FIX ANTI-SPAM 5SIM ---
solde_cache = 0
dernier_check = 0

async def get_solde_5sim():
    global solde_cache, dernier_check
    if time.time() - dernier_check < 120 and solde_cache!= 0:
        return solde_cache
    try:
        headers = {"Authorization": f"Bearer {FIVESIM_TOKEN}", "Accept": "application/json"}
        async with aiohttp.ClientSession() as s:
            async with s.get("https://5sim.net/v1/user/profile", headers=headers, timeout=10) as r:
                text = await r.text()
                if r.status!= 200:
                    print(f"SOLDE ERREUR {r.status}: {text}")
                    return -1
                data = json.loads(text)
                balance = float(data.get("balance", 0))
                solde_cache = balance
                dernier_check = time.time()
                print(f"Solde 5SIM: {balance}$")
                return balance
    except Exception as e:
        print(f"Erreur solde: {e}")
        return -1

async def acheter_numero(service):
    solde = await get_solde_5sim()
    if solde!= -1 and solde < 0.10:
        return None, "STOCK_VIDE"
    try:
        headers = {"Authorization": f"Bearer {FIVESIM_TOKEN}", "Accept": "application/json"}
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://5sim.net/v1/user/buy/activation/any/any/{service}", headers=headers) as r:
                text = await r.text()
                if r.status!= 200:
                    if "balance" in text.lower() or "insufficient" in text.lower() or "money" in text.lower():
                        return None, "STOCK_VIDE"
                    print(f"5SIM BUY ERREUR {r.status}: {text}")
                    return None, "STOCK_VIDE"
                data = json.loads(text)
                if "phone" not in data or "id" not in data:
                    return None, "STOCK_VIDE"
                return str(data["phone"]).replace("+",""), str(data["id"])
    except Exception as e:
        print(f"EXCEPTION BUY: {e}")
        return None, "STOCK_VIDE"

# --- VUES FIX BUG "PAS REPONDU" ---
class GenerateView(discord.ui.View):
    def __init__(self, service_type):
        super().__init__(timeout=None)
        self.service_type = service_type
        self.children[0].custom_id = f"gen_{service_type}"

    @discord.ui.button(label="🎲 Générer un numéro - 200F", style=discord.ButtonStyle.success)
    async def generate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title=f"💳 PAIEMENT 200F - {NOM_AGENCE}",
            description=f"**Service:** {self.service_type.upper()}\n\n**1. MoMo:** `{MOMO_NUM}`\n**2. USDT BEP20:** `{CRYPTO_ADDR}`\n\nPaye et envoie capture **ICI dans ce salon** avec 📎.",
            color=0x00ff00
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

class StockView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.children[0].custom_id = "stock_solde_final"
        self.children[1].custom_id = "stock_tuto_final"

    @discord.ui.button(label="💰 Voir mon solde 5SIM", style=discord.ButtonStyle.primary)
    async def solde(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        solde = await get_solde_5sim()
        if solde == -1:
            await interaction.followup.send(f"❌ Erreur 5SIM, vérifie FIVESIM_TOKEN sur Render", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Solde 5SIM: **{solde}$** | 1 num = ~0.15$ | Bénef 110F", ephemeral=True)

    @discord.ui.button(label="📚 Comment recharger 5SIM?", style=discord.ButtonStyle.secondary)
    async def tuto(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="📚 COMMENT PAYER TES NUMÉROS - BOSS", description="**1.** Va sur 5sim.net\n**2.** Recharge avec Crypto (USDT) min 2$\n**3.** Tu n'as PAS besoin de stock BOSS\nLe bot achète tout seul quand tu valides un client. Boucle infinie jusqu'à livraison du code.", color=0x2b2d31)
        await interaction.followup.send(embed=embed, ephemeral=True)

class ValidationView(discord.ui.View):
    def __init__(self, client_id, service_type):
        super().__init__(timeout=None)
        self.client_id = client_id
        self.service_type = service_type
        self.children[0].custom_id = f"val_momo_{client_id}"
        self.children[1].custom_id = f"val_crypto_{client_id}"
        self.children[2].custom_id = f"val_refuse_{client_id}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        boss_role = discord.utils.get(interaction.guild.roles, name="BOSS")
        if boss_role and boss_role in interaction.user.roles:
            return True
        await interaction.response.send_message(f"❌ <@{interaction.user.id}> Seul le BOSS peut valider.", ephemeral=True)
        return False

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
        await interaction.response.send_message(f"❌ <@{interaction.user.id}> a refusé le paiement de <@{self.client_id}>", ephemeral=False)

    async def lancer_achat_infini(self, interaction):
        channel = interaction.channel
        solde = await get_solde_5sim()
        if solde!= -1 and solde < 0.10:
            await channel.send(f"❌ **Stock vide <@{interaction.user.id}> doit recharger** - Solde 5SIM: {solde}$ - <@{self.client_id}> reviens plus tard.")
            return
        await channel.send(f"✅ Validé par <@{interaction.user.id}> pour <@{self.client_id}>. Achat 5SIM en cours... <@{self.client_id}> reste ici dans ce salon.")
        tentative = 1
        while True:
            try:
                tel, order_id = await acheter_numero(self.service_type)
                if order_id == "STOCK_VIDE":
                    await channel.send(f"❌ **Stock vide, <@{interaction.user.id}> doit recharger sur 5sim.net** - Stop achat pour <@{self.client_id}>.")
                    break
                if not tel:
                    await channel.send(f"❌ Erreur 5SIM T{tentative} pour <@{self.client_id}>, retente 20s..."); await asyncio.sleep(20); tentative+=1; continue
                await channel.send(f"✅ **<@{self.client_id}> NUMÉRO LIVRÉ T{tentative}: `{tel}` ID:{order_id} - Attente code... Validé par <@{interaction.user.id}>**")
                code=None
                async with aiohttp.ClientSession() as session:
                    headers = {"Authorization": f"Bearer {FIVESIM_TOKEN}", "Accept": "application/json"}
                    for _ in range(16):
                        await asyncio.sleep(30)
                        async with session.get(f"https://5sim.net/v1/user/check/{order_id}", headers=headers) as check_resp:
                            try:
                                check_data = await check_resp.json()
                                if check_data.get("sms") and len(check_data["sms"])>0:
                                    code=check_data["sms"][0]["code"]; break
                            except: continue
                    if code:
                        await channel.send(f"📩 **<@{self.client_id}> CODE: `{code}` - Numéro {tel} - Bénéfice 110F ✅ Validé par <@{interaction.user.id}>**")
                        break
                    else:
                        async with session.get(f"https://5sim.net/v1/user/cancel/{order_id}", headers=headers):
                            await channel.send(f"⚠️ <@{self.client_id}> Pas de code ID {order_id} T{tentative}. CANCEL + RACHAT T{tentative+1}... Commandé par <@{interaction.user.id}>")
                        tentative+=1; await asyncio.sleep(5); continue
            except Exception as e:
                await channel.send(f"Erreur pour <@{self.client_id}>: {e} - <@{interaction.user.id}>"); await asyncio.sleep(10); continue

@bot.event
async def on_ready():
    print(f"Connecté {bot.user}")
    bot.add_view(GenerateView("google"))
    bot.add_view(GenerateView("instagram"))
    bot.add_view(StockView())
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
    for cat in guild.categories:
        if "RAMANE" in cat.name:
            for ch in cat.channels: await ch.delete()
            await cat.delete()
    category = await guild.create_category("💰 RAMANE OFM - BUSINESS")
    overwrites_stock = {guild.default_role: discord.PermissionOverwrite(view_channel=False), guild.me: discord.PermissionOverwrite(view_channel=True), ctx.author: discord.PermissionOverwrite(view_channel=True)}
    overwrites_public = {guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False), guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True), ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
    overwrites_number = {guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True), guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True), ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
    stock = await guild.create_text_channel("🔒-mon-stock-5sim", category=category, overwrites=overwrites_stock)
    embed_stock = discord.Embed(title="🔒 TON QG PERSO - BOSS RAMANE", description=f"**Ici tu gères ton business 5SIM.**\n\n**Comment ça marche?**\nTu n'as pas besoin de stocker de numéros. Tu recharges juste ton solde sur 5sim.net.\nQuand un client paye 200F, le bot achète 1 numéro (~90F) et te reste 110F de bénef.\n\n**Tuto:** Clique en bas pour voir ton solde et comment recharger.", color=0x2b2d31)
    await stock.send(embed=embed_stock, view=StockView())
    infos = await guild.create_text_channel("📢-infos-paiement", category=category, overwrites=overwrites_public)
    await infos.send(embed=discord.Embed(title="💳 PAIEMENT - 200F / NUMÉRO", description=f"**MoMo:** `{MOMO_NUM}`\n**USDT BEP20:** `{CRYPTO_ADDR}`\n\nPaye -> Envoie preuve dans 📧 ou 📸", color=0x00ff00))
    gmail = await guild.create_text_channel("📧-numéro-gmail", category=category, overwrites=overwrites_number)
    embed_gmail = discord.Embed(title="📧 NUMÉRO GMAIL USA - 200F", description="**C'est quoi?** Numéro USA pour créer ton Gmail sans ton perso.\n\n**Avantage:**\n✅ Compte USA = + confiance, débloque tout\n✅ 100% anonyme\n✅ Livraison < 5min avec code\n\n**Comment utiliser?**\n1. Clique sur 🎲 en bas\n2. Paye 200F\n3. Envoie capture **ICI dans ce salon** avec 📎\n4. Tu reçois numéro + code auto ici même", color=0x00ff00)
    await gmail.send(embed=embed_gmail, view=GenerateView("google"))
    insta = await guild.create_text_channel("📸-numéro-insta", category=category, overwrites=overwrites_number)
    embed_insta = discord.Embed(title="📸 NUMÉRO INSTA USA - 200F", description="**C'est quoi?** Numéro USA pour créer ton Insta sans ton perso.\n\n**Avantage:**\n✅ Compte USA = + de portée, pas de blocage\n✅ Parfait pour OFM / Modèle\n✅ Livraison < 5min avec code\n\n**Comment utiliser?**\n1. Clique sur 🎲 en bas\n2. Paye 200F\n3. Envoie capture **ICI dans ce salon** avec 📎\n4. Tu reçois numéro + code auto ici même", color=0xE1306C)
    await insta.send(embed=embed_insta, view=GenerateView("instagram"))
    await ctx.send("✅ C'est fait BOSS. Tout arrangé nikel. Teste 🎲 maintenant.")

# --- GRADES FIX 403 ---
BOSS_PRIVATE_NAME = "mon-stock-5sim"
GRADE_COLORS = {"Manager": 0x3498db, "Team Leader": 0xf1c40f, "VA": 0x2ecc71, "PRO": 0x9b59b6}

async def add_grade_logic(ctx, member: discord.Member, grade_name: str):
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=grade_name)
    if not role:
        role = await guild.create_role(name=grade_name, color=discord.Color(GRADE_COLORS[grade_name]))
    try:
        if guild.me.top_role.position <= role.position:
            await role.edit(position=guild.me.top_role.position - 1)
    except: pass
    if guild.me.top_role.position <= role.position:
        await ctx.send(f"❌ BOSS monte le rôle **{guild.me.top_role.name}** tout en haut dans Paramètres > Rôles. Il est sous {grade_name} donc je peux pas le donner.")
        return
    await member.add_roles(role)

    # --- FIX PSEUDO GRADE SANS CHIFFRE BOSS ---
    try:
        base_name = member.display_name
        for g in ["Manager", "Team Leader", "VA", "PRO", "BOSS"]:
            base_name = base_name.replace(g, "")
        base_name = re.sub(r'[0-9]+', '', base_name)
        base_name = base_name.strip(" |[]-_@").strip()
        base_name = re.sub(r'\s+', ' ', base_name)
        if not base_name:
            base_name = re.sub(r'[0-9]+', '', member.name).strip()
        new_nick = f"{grade_name} {base_name}"
        if len(new_nick) > 32:
            new_nick = new_nick[:32]
        await member.edit(nick=new_nick)
    except Exception as e:
        print(f"Erreur pseudo: {e}")

    if grade_name in ["Manager", "Team Leader"]:
        count=0
        for channel in guild.channels:
            if BOSS_PRIVATE_NAME in channel.name.lower(): continue
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                if channel.overwrites_for(guild.default_role).view_channel == False:
                    try:
                        await channel.set_permissions(role, view_channel=True, send_messages=True, read_message_history=True, connect=True)
                        count+=1
                    except: pass
        await ctx.send(f"✅ {member.mention} est maintenant **{grade_name}** + pseudo: **{member.display_name}** + {count} salons BOSS")
    else:
        await ctx.send(f"✅ {member.mention} est maintenant **{grade_name}** + pseudo: **{member.display_name}** BOSS")

@bot.command()
@commands.has_permissions(administrator=True)
async def manager(ctx, member: discord.Member):
    await add_grade_logic(ctx, member, "Manager")

@bot.command()
@commands.has_permissions(administrator=True)
async def teamleader(ctx, member: discord.Member):
    await add_grade_logic(ctx, member, "Team Leader")

@bot.command()
@commands.has_permissions(administrator=True)
async def va(ctx, member: discord.Member):
    await add_grade_logic(ctx, member, "VA")

@bot.command()
@commands.has_permissions(administrator=True)
async def pro(ctx, member: discord.Member):
    await add_grade_logic(ctx, member, "PRO")

@bot.command()
@commands.has_permissions(administrator=True)
async def removegrade(ctx, member: discord.Member, *, grade_name: str):
    role = discord.utils.get(ctx.guild.roles, name=grade_name)
    if role and role in member.roles:
        await member.remove_roles(role)
        await ctx.send(f"✅ Grade {grade_name} retiré à {member.mention} BOSS")
    else:
        await ctx.send(f"❌ {member.mention} n'a pas {grade_name}")

@bot.command()
@commands.has_permissions(administrator=True)
async def clearerrors(ctx):
    await ctx.send("🧹 Nettoyage des erreurs en cours BOSS...")
    mots_erreur = ["Erreur 5SIM", "STOCK_VIDE", "Attempt to decode", "mimetype", "text/plain", "https://5sim.net"]
    total = 0
    for channel in ctx.guild.text_channels:
        if "numéro" in channel.name or "gmail" in channel.name or "insta" in channel.name:
            try:
                async for msg in channel.history(limit=200):
                    if msg.author == bot.user and any(m in msg.content for m in mots_erreur):
                        try:
                            await msg.delete()
                            total+=1
                            await asyncio.sleep(0.4)
                        except: pass
            except: pass
    await ctx.send(f"✅ C'est propre BOSS - {total} messages d'erreur supprimés.")

@bot.command()
@commands.has_permissions(administrator=True)
async def clean(ctx, nombre: int = 50):
    deleted = await ctx.channel.purge(limit=nombre, check=lambda m: not m.pinned)
    await ctx.send(f"✅ {len(deleted)} messages supprimés BOSS", delete_after=5)

@bot.event
async def on_command_error(ctx, error):
    print(f"ERREUR: {error}")
    await ctx.send(f"❌ Erreur: {error}")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    if TOKEN: bot.run(TOKEN)
