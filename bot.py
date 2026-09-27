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
import random
import traceback

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
                if r.status!= 200: return -1
                data = json.loads(text)
                balance = float(data.get("balance", 0))
                solde_cache = balance
                dernier_check = time.time()
                return balance
    except: return -1

async def acheter_numero(service):
    solde = await get_solde_5sim()
    if solde!= -1 and solde < 0.10: return None, "STOCK_VIDE"
    try:
        headers = {"Authorization": f"Bearer {FIVESIM_TOKEN}", "Accept": "application/json"}
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://5sim.net/v1/user/buy/activation/any/any/{service}", headers=headers) as r:
                text = await r.text()
                if r.status!= 200: return None, "STOCK_VIDE"
                data = json.loads(text)
                if "phone" not in data or "id" not in data: return None, "STOCK_VIDE"
                return str(data["phone"]).replace("+",""), str(data["id"])
    except: return None, "STOCK_VIDE"

class GenerateView(discord.ui.View):
    def __init__(self, service_type):
        super().__init__(timeout=None)
        self.service_type = service_type
        self.children[0].custom_id = f"gen_{service_type}"
    @discord.ui.button(label="🎲 Générer un numéro - 200F", style=discord.ButtonStyle.success)
    async def generate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title=f"💳 PAIEMENT 200F - {NOM_AGENCE}", description=f"**Service:** {self.service_type.upper()}\n\n**1. MoMo:** `{MOMO_NUM}`\n**2. USDT BEP20:** `{CRYPTO_ADDR}`\n\nPaye et envoie capture **ICI dans ce salon** avec 📎.", color=0x00ff00)
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
        if solde == -1: await interaction.followup.send(f"❌ Erreur 5SIM", ephemeral=True)
        else: await interaction.followup.send(f"✅ Solde 5SIM: **{solde}$**", ephemeral=True)
    @discord.ui.button(label="📚 Comment recharger 5SIM?", style=discord.ButtonStyle.secondary)
    async def tuto(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="📚 COMMENT PAYER", description="1. Va sur 5sim.net\n2. Recharge Crypto USDT min 2$\n3. Le bot achète auto", color=0x2b2d31)
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
        if interaction.user.guild_permissions.administrator: return True
        for r in interaction.guild.roles:
            if "boss" in r.name.lower() and r in interaction.user.roles: return True
        await interaction.response.send_message(f"❌ Seul le BOSS peut valider.", ephemeral=True)
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
        await interaction.response.send_message(f"❌ <@{interaction.user.id}> a refusé <@{self.client_id}>", ephemeral=False)
    async def lancer_achat_infini(self, interaction):
        channel = interaction.channel
        solde = await get_solde_5sim()
        if solde!= -1 and solde < 0.10:
            await channel.send(f"❌ **Stock vide doit recharger {solde}$ - <@{self.client_id}>**", delete_after=300)
            return
        await channel.send(f"✅ Validé par <@{interaction.user.id}> pour <@{self.client_id}>. Achat en cours...", delete_after=300)
        tentative = 1
        while True:
            try:
                tel, order_id = await acheter_numero(self.service_type)
                if order_id == "STOCK_VIDE":
                    await channel.send(f"❌ **Stock vide, recharge sur 5sim.net - <@{self.client_id}>**", delete_after=300)
                    break
                if not tel:
                    await channel.send(f"❌ Erreur 5SIM T{tentative} <@{self.client_id}> retente 20s...", delete_after=120)
                    await asyncio.sleep(20); tentative+=1; continue
                await channel.send(f"✅ **<@{self.client_id}> NUMÉRO: `{tel}` ID:{order_id} - Attente code...**", delete_after=600)
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
                        await channel.send(f"📩 **<@{self.client_id}> CODE: `{code}` - Numéro {tel} - Bénéfice 110F ✅**", delete_after=600)
                        break
                    else:
                        async with session.get(f"https://5sim.net/v1/user/cancel/{order_id}", headers=headers):
                            await channel.send(f"⚠️ <@{self.client_id}> Pas de code T{tentative}. CANCEL + RACHAT...", delete_after=300)
                        tentative+=1; await asyncio.sleep(5); continue
            except Exception as e:
                await channel.send(f"Erreur {e}", delete_after=120); await asyncio.sleep(10); continue

BOSS_PRIVATE_NAME = "mon-stock-5sim"
GRADE_COLORS = {"Manager": 0x3498db, "Team Leader": 0x2ecc71, "VA Pro": 0x9b59b6, "VA DÉBUTANT": 0xe91e63, "BOSS": 0xe74c3c}

def get_real_role(guild, keyword):
    keyword = keyword.lower()
    for r in guild.roles:
        if keyword in r.name.lower() and ("🔰" in r.name or "📚" in r.name or "📖" in r.name): return r
    for r in guild.roles:
        if keyword in r.name.lower(): return r
    return None

async def auto_fix_colors():
    for guild in bot.guilds:
        for role in guild.roles:
            low = role.name.lower()
            try:
                if "va débutant" in low or "va debutant" in low: await role.edit(color=discord.Color(0xe91e63))
                elif "va pro" in low: await role.edit(color=discord.Color(0x9b59b6))
                elif "team leader" in low: await role.edit(color=discord.Color(0x2ecc71))
                elif "manager" in low: await role.edit(color=discord.Color(0x3498db))
                elif "boss" in low: await role.edit(color=discord.Color(0xe74c3c))
            except: pass

async def add_grade_logic(ctx, member: discord.Member, keyword: str):
    guild = ctx.guild
    role = get_real_role(guild, keyword)
    if not role: role = discord.utils.get(guild.roles, name=keyword)
    if not role:
        try: role = await guild.create_role(name=keyword, color=discord.Color(GRADE_COLORS.get(keyword, 0x3498db)))
        except: await ctx.send(f"❌ Rôle {keyword} introuvable"); return
    try:
        if guild.me.top_role.position <= role.position: await role.edit(position=guild.me.top_role.position - 1)
    except: pass
    if guild.me.top_role.position <= role.position:
        await ctx.send(f"❌ Monte mon rôle en haut BOSS"); return
    await member.add_roles(role)
    await ctx.send(f"✅ {member.mention} est maintenant **{role.name}** BOSS")

DRIVE_REGEX = r"https://drive\.google\.com/drive/folders/[a-zA-Z0-9-_]+[^\s]*"
def find_channel(guild, keywords):
    for ch in guild.text_channels:
        if any(k in ch.name.lower() for k in keywords): return ch
    return None
async def get_all_drive_links(guild):
    chan = find_channel(guild, ["drive-réels", "drive-reels", "drive"])
    if not chan: return []
    links = []
    async for msg in chan.history(limit=500):
        found = re.findall(DRIVE_REGEX, msg.content)
        for f in found:
            clean = f.split("?")[0]
            name_match = re.search(r"REELS\s+([A-Z0-9_]+)", msg.content.upper())
            model_name = name_match.group(1) if name_match else "MODEL"
            links.append({"url": clean, "name": model_name})
    uniq = {}
    for l in links: uniq[l["url"]] = l
    return list(uniq.values())
async def get_all_descriptions(guild):
    chan = find_channel(guild, ["description"])
    if not chan: return []
    descs = []
    async for msg in chan.history(limit=500):
        if len(msg.content) > 10: descs.append(msg.content)
    return descs

class FinishPackView(discord.ui.View):
    def __init__(self, thread_id):
        super().__init__(timeout=1200)
        self.thread_id = thread_id
        self.children[0].custom_id = f"finish_pack_{thread_id}"
    @discord.ui.button(label="✅ J'ai fini de poster", style=discord.ButtonStyle.success)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ Pack supprimé BOSS, bien joué!", ephemeral=True)
        try:
            thread = interaction.guild.get_thread(self.thread_id) or await interaction.guild.fetch_channel(self.thread_id)
            await thread.delete()
        except: pass

class PackGenerateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.children[0].custom_id = "pack_generate_v9"
    @discord.ui.button(label="📦 Générer mon pack 8 Reels", style=discord.ButtonStyle.success, emoji="🎬")
    async def generate_pack(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        drive_links = await get_all_drive_links(guild)
        if not drive_links:
            await interaction.followup.send("❌ Aucun lien Drive trouvé dans #--drive-réels BOSS", ephemeral=True)
            return
        chosen = random.choice(drive_links)
        descs = await get_all_descriptions(guild)
        if len(descs) < 8:
            await interaction.followup.send(f"⚠️ Pas assez de descriptions (trouvé {len(descs)}), il en faut 8 min BOSS", ephemeral=True)
            return
        selected_descs = random.sample(descs, 8)
        packs_chan = find_channel(guild, ["packs-reels", "pack-reels", "packs"])
        if not packs_chan: packs_chan = interaction.channel
        model_name = chosen["name"]
        thread_name = f"PACK-{model_name}-{interaction.user.display_name}"
        try:
            thread = await packs_chan.create_thread(name=thread_name, type=discord.ChannelType.private_thread, auto_archive_duration=60)
        except:
            thread = await packs_chan.create_thread(name=thread_name, auto_archive_duration=60)
        try: await thread.add_user(interaction.user)
        except: pass
        embed = discord.Embed(title=f"🎬 PACK REEL - {model_name} - 8 REELS + 1 STORY", description=f"**BOSS {NOM_AGENCE}**\n\n**Modèle:** {model_name}\n**Drive:** {chosen['url']}\n\n⏰ Auto-delete dans **20 minutes**", color=0xE1306C)
        pack_text = f"**🔥 PACK REEL - {model_name}** - {chosen['url']}\n\n"
        for i, d in enumerate(selected_descs, 1):
            pack_text += f"**REEL {i}:**\n{d[:800]}\n\n"
        view_finish = FinishPackView(thread.id)
        await thread.send(embed=embed, view=view_finish)
        await thread.send(content=pack_text[:1900])
        if len(pack_text) > 1900: await thread.send(content=pack_text[1900:3800])
        await interaction.followup.send(f"✅ Ton pack **{model_name}** est prêt dans {thread.mention} BOSS!", ephemeral=True)
        await asyncio.sleep(1200)
        try: await thread.delete()
        except: pass

@bot.event
async def on_ready():
    print(f"Connecté {bot.user}")
    bot.add_view(GenerateView("google"))
    bot.add_view(GenerateView("instagram"))
    bot.add_view(StockView())
    bot.add_view(PackGenerateView())
    await auto_fix_colors()
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="RAMANE OFM - PACK REELS 8+1"))

@bot.event
async def on_member_join(member):
    role = get_real_role(member.guild, "VA DÉBUTANT")
    if not role: role = get_real_role(member.guild, "VA DEBUTANT")
    if role:
        try: await member.add_roles(role)
        except: pass

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.attachments and ("numéro-gmail" in message.channel.name or "numéro-insta" in message.channel.name):
        service = "google" if "gmail" in message.channel.name else "instagram"
        embed = discord.Embed(title="💰 NOUVELLE PREUVE 200F", description=f"Client: {message.author.mention}\nService: {service}", color=0xffa500)
        embed.set_image(url=message.attachments[0].url)
        try: await message.delete(delay=300)
        except: pass
        await message.channel.send(embed=embed, view=ValidationView(message.author.id, service), delete_after=600)
    await bot.process_commands(message)

@bot.command()
async def ping(ctx): await ctx.send(f"Pong! {NOM_AGENCE} ✅")

@bot.command()
@commands.has_permissions(administrator=True)
async def setupbusiness(ctx): await ctx.send(f"✅ Setup business OK BOSS - {NOM_AGENCE}")

# === AJOUT SEULEMENT POUR PACK - NE TOUCHE PAS TES ANCIENS ===
@bot.command()
@commands.has_permissions(administrator=True)
async def setuppack(ctx):
    embed = discord.Embed(title="🎬 PACK REELS 8+1 - RAMANE OFM", description="Clique sur le bouton pour générer ton pack 8 Reels + 1 Story\n\n⏰ Le pack s'auto-supprime après 20min", color=0xE1306C)
    await ctx.send(embed=embed, view=PackGenerateView())

@bot.command()
@commands.has_permissions(administrator=True)
async def manager(ctx, member: discord.Member): await add_grade_logic(ctx, member, "Manager")
@bot.command()
@commands.has_permissions(administrator=True)
async def teamleader(ctx, member: discord.Member): await add_grade_logic(ctx, member, "Team Leader")
@bot.command()
@commands.has_permissions(administrator=True)
async def va(ctx, member: discord.Member): await add_grade_logic(ctx, member, "VA DÉBUTANT")
@bot.command()
@commands.has_permissions(administrator=True)
async def pro(ctx, member: discord.Member): await add_grade_logic(ctx, member, "VA Pro")
@bot.command()
@commands.has_permissions(administrator=True)
async def vapro(ctx, member: discord.Member): await add_grade_logic(ctx, member, "VA Pro")
@bot.command()
@commands.has_permissions(administrator=True)
async def vadebutant(ctx, member: discord.Member): await add_grade_logic(ctx, member, "VA DÉBUTANT")
@bot.command()
@commands.has_permissions(administrator=True)
async def boss(ctx, member: discord.Member): await add_grade_logic(ctx, member, "BOSS")
@bot.command()
@commands.has_permissions(administrator=True)
async def removegrade(ctx, member: discord.Member, *, grade: str):
    role = get_real_role(ctx.guild, grade)
    if role: await member.remove_roles(role); await ctx.send(f"✅ {grade} retiré à {member.mention}")
@bot.command()
@commands.has_permissions(administrator=True)
async def fixcolors(ctx): await auto_fix_colors(); await ctx.send("✅ Couleurs fixées")
@bot.command()
@commands.has_permissions(administrator=True)
async def clean(ctx, amount: int = 10): await ctx.channel.purge(limit=amount); await ctx.send(f"✅ {amount} messages supprimés", delete_after=3)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print("✅ Flask lancé")
    if not TOKEN:
        print("❌ DISCORD_TOKEN MANQUANT!")
        while True:
            time.sleep(60)
    while True:
        try:
            print(f"🚀 Lancement {NOM_AGENCE}...")
            bot.run(TOKEN)
        except Exception as e:
            print(f"❌ ERREUR BOT: {e}")
            traceback.print_exc()
            print("⏳ Redémarrage dans 10s...")
            time.sleep(10)
