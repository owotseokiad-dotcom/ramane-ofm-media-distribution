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
import io

NOM_AGENCE = "RAMANE OFM - MEDIA DISTRIBUTION"
TOKEN = os.getenv("DISCORD_TOKEN")
FIVESIM_TOKEN = os.getenv("FIVESIM_TOKEN")
GOOGLE_DRIVE_API_KEY = os.getenv("GOOGLE_DRIVE_API_KEY")
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

def extract_folder_id(url):
    m = re.search(r"/folders/([a-zA-Z0-9-_]+)", url)
    return m.group(1) if m else None

async def list_drive_files(folder_id):
    if not GOOGLE_DRIVE_API_KEY or not folder_id:
        return []
    try:
        url = "https://www.googleapis.com/drive/v3/files"
        params = {"q": f"'{folder_id}' in parents and trashed=false", "key": GOOGLE_DRIVE_API_KEY, "fields": "files(id,name,mimeType)", "pageSize": 100}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=15) as r:
                if r.status!= 200:
                    return []
                data = await r.json()
                return data.get("files", [])
    except:
        return []

async def download_drive_file(file_id):
    if not GOOGLE_DRIVE_API_KEY:
        return None
    try:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        params = {"alt": "media", "key": GOOGLE_DRIVE_API_KEY}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=60) as r:
                if r.status!= 200:
                    return None
                return await r.read()
    except:
        return None

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
    @discord.ui.button(label="Generer un numero - 200F", style=discord.ButtonStyle.success)
    async def generate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title=f"PAIEMENT 200F - {NOM_AGENCE}", description=f"**Service:** {self.service_type.upper()}\n\n**1. MoMo:** `{MOMO_NUM}`\n**2. USDT BEP20:** `{CRYPTO_ADDR}`\n\nPaye et envoie capture ICI dans ce salon.", color=0x00ff00)
        await interaction.followup.send(embed=embed, ephemeral=True)

class StockView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.children[0].custom_id = "stock_solde_final"
        self.children[1].custom_id = "stock_tuto_final"
    @discord.ui.button(label="Voir mon solde 5SIM", style=discord.ButtonStyle.primary)
    async def solde(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        solde = await get_solde_5sim()
        if solde == -1: await interaction.followup.send(f"Erreur 5SIM", ephemeral=True)
        else: await interaction.followup.send(f"Solde 5SIM: **{solde}$**", ephemeral=True)
    @discord.ui.button(label="Comment recharger 5SIM?", style=discord.ButtonStyle.secondary)
    async def tuto(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="COMMENT PAYER", description="1. Va sur 5sim.net\n2. Recharge Crypto USDT min 2$\n3. Le bot achete auto", color=0x2b2d31)
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
        await interaction.response.send_message(f"Seul le BOSS peut valider.", ephemeral=True)
        return False
    @discord.ui.button(label="Recu MoMo", style=discord.ButtonStyle.success)
    async def momo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.lancer_achat_infini(interaction)
    @discord.ui.button(label="Recu Crypto", style=discord.ButtonStyle.primary)
    async def crypto(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.lancer_achat_infini(interaction)
    @discord.ui.button(label="Refuse", style=discord.ButtonStyle.danger)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"<@{interaction.user.id}> a refuse <@{self.client_id}>", ephemeral=False)
    async def lancer_achat_infini(self, interaction):
        channel = interaction.channel
        solde = await get_solde_5sim()
        if solde!= -1 and solde < 0.10:
            await channel.send(f"Stock vide doit recharger {solde}$ - <@{self.client_id}>", delete_after=300)
            return
        await channel.send(f"Valide par <@{interaction.user.id}> pour <@{self.client_id}>. Achat en cours...", delete_after=300)
        tentative = 1
        while True:
            try:
                tel, order_id = await acheter_numero(self.service_type)
                if order_id == "STOCK_VIDE":
                    await channel.send(f"Stock vide, recharge sur 5sim.net - <@{self.client_id}>", delete_after=300)
                    break
                if not tel:
                    await channel.send(f"Erreur 5SIM T{tentative} <@{self.client_id}> retente 20s...", delete_after=120)
                    await asyncio.sleep(20); tentative+=1; continue
                await channel.send(f"<@{self.client_id}> NUMERO: `{tel}` ID:{order_id} - Attente code...", delete_after=600)
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
                        await channel.send(f"<@{self.client_id}> CODE: `{code}` - Numero {tel} - Benefice 110F", delete_after=600)
                        break
                    else:
                        async with session.get(f"https://5sim.net/v1/user/cancel/{order_id}", headers=headers):
                            await channel.send(f"<@{self.client_id}> Pas de code T{tentative}. CANCEL + RACHAT...", delete_after=300)
                        tentative+=1; await asyncio.sleep(5); continue
            except Exception as e:
                await channel.send(f"Erreur {e}", delete_after=120); await asyncio.sleep(10); continue

BOSS_PRIVATE_NAME = "mon-stock-5sim"
GRADE_COLORS = {"Manager": 0x3498db, "Team Leader": 0x2ecc71, "VA Pro": 0x9b59b6, "VA DEBUTANT": 0xe91e63, "BOSS": 0xe74c3c}

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
                if "va debutant" in low: await role.edit(color=discord.Color(0xe91e63))
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
        except: await ctx.send(f"Role {keyword} introuvable"); return
    try:
        if guild.me.top_role.position <= role.position: await role.edit(position=guild.me.top_role.position - 1)
    except: pass
    if guild.me.top_role.position <= role.position:
        await ctx.send(f"Monte mon role en haut BOSS"); return
    await member.add_roles(role)
    await ctx.send(f"{member.mention} est maintenant **{role.name}** BOSS")

DRIVE_REGEX = r"https://drive\.google\.com/drive/folders/[a-zA-Z0-9-_]+[^\s]*"
def find_channel(guild, keywords):
    for ch in guild.text_channels:
        if any(k in ch.name.lower() for k in keywords): return ch
    return None

async def get_all_drive_links(guild):
    chan = find_channel(guild, ["drive-reels", "drive-reels", "drive"])
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

class PackGenerateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.children[0].custom_id = "pack_generate_final_same_channel"
    @discord.ui.button(label="Generer mon pack 8 Reels", style=discord.ButtonStyle.success, emoji="🎬")
    async def generate_pack(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        drive_links = await get_all_drive_links(guild)
        if not drive_links:
            await interaction.followup.send("Aucun lien Drive dans #--drive-reels BOSS", ephemeral=True)
            return
        chosen = random.choice(drive_links)
        descs = await get_all_descriptions(guild)
        if len(descs) < 8:
            await interaction.followup.send(f"Pas assez de descriptions dans #description ({len(descs)}/8) BOSS", ephemeral=True)
            return
        selected_descs = random.sample(descs, 8)
        if not GOOGLE_DRIVE_API_KEY:
            await interaction.followup.send("GOOGLE_DRIVE_API_KEY manquante sur Render BOSS", ephemeral=True)
            return
        main_folder_id = extract_folder_id(chosen['url'])
        root_files = await list_drive_files(main_folder_id)
        reels_folder_id = None
        story_folder_id = None
        for f in root_files:
            if "folder" in f.get("mimeType",""):
                lname = f["name"].lower()
                if "reel" in lname: reels_folder_id = f["id"]
                if "story" in lname or "photo" in lname: story_folder_id = f["id"]
        target_reels_id = reels_folder_id if reels_folder_id else main_folder_id
        reels_files = await list_drive_files(target_reels_id)
        video_files = [f for f in reels_files if "video" in f.get("mimeType","") or f["name"].lower().endswith((".mp4",".mov",".mkv"))]
        if len(video_files) == 0:
            video_files = reels_files
        video_files = video_files[:8]
        sent = []
        embed = discord.Embed(title=f"PACK REEL - {chosen['name']} - 8 REELS + 1 STORY", description=f"**BOSS {NOM_AGENCE}**\n\n**Modele:** {chosen['name']}\n**Drive:** {chosen['url']}\n\nVRAIES VIDEOS envoi direct\nAuto-delete dans 20 minutes - Meme salon", color=0xE1306C)
        m = await interaction.channel.send(content=f"PACK pour {interaction.user.mention} - {chosen['name']}", embed=embed)
        sent.append(m)
        for i, vf in enumerate(video_files):
            data = await download_drive_file(vf["id"])
            if not data:
                await interaction.channel.send(f"Impossible de telecharger {vf['name']}")
                continue
            file_obj = discord.File(io.BytesIO(data), filename=vf["name"])
            desc_copiable = f"```\n{selected_descs[i][:1000]}\n```"
            txt = f"REEL {i+1}/8 - {chosen['name']} - {vf['name']}\nDescription copiable (1 clic):\n{desc_copiable}"
            try:
                mm = await interaction.channel.send(content=txt, file=file_obj)
                sent.append(mm)
            except Exception as e:
                direct_link = f"https://www.googleapis.com/drive/v3/files/{vf['id']}?alt=media&key={GOOGLE_DRIVE_API_KEY}"
                await interaction.channel.send(f"Video {vf['name']} trop lourde, lien direct: {direct_link}\n{txt}")
        if story_folder_id:
            story_files = await list_drive_files(story_folder_id)
            story_videos = [f for f in story_files if "video" in f.get("mimeType","") or "image" in f.get("mimeType","")][:1]
            for sf in story_videos:
                sdata = await download_drive_file(sf["id"])
                if sdata:
                    sfile = discord.File(io.BytesIO(sdata), filename=sf["name"])
                    ms = await interaction.channel.send(content=f"STORY 1/1 - {chosen['name']} (meme visage)", file=sfile)
                    sent.append(ms)
        else:
            ms = await interaction.channel.send(content=f"STORY 1/1 - {chosen['name']} - Va dans #story / #photo pour 1 story meme visage")
            sent.append(ms)
        await interaction.followup.send(f"Pack **{chosen['name']}** genere ICI avec VRAIES VIDEOS BOSS! Descriptions copiables - Supprime auto dans 20min", ephemeral=True)
        await asyncio.sleep(1200)
        for msg in sent:
            try: await msg.delete()
            except: pass

@bot.event
async def on_ready():
    print(f"Connecte {bot.user}")
    bot.add_view(GenerateView("google"))
    bot.add_view(GenerateView("instagram"))
    bot.add_view(StockView())
    bot.add_view(PackGenerateView())
    await auto_fix_colors()
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="RAMANE OFM - PACK REELS 8+1"))

@bot.event
async def on_member_join(member):
    role = get_real_role(member.guild, "VA DEBUTANT")
    if role:
        try: await member.add_roles(role)
        except: pass

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.attachments and ("numero-gmail" in message.channel.name or "numero-insta" in message.channel.name):
        service = "google" if "gmail" in message.channel.name else "instagram"
        embed = discord.Embed(title="NOUVELLE PREUVE 200F", description=f"Client: {message.author.mention}\nService: {service}", color=0xffa500)
        embed.set_image(url=message.attachments[0].url)
        try: await message.delete(delay=300)
        except: pass
        await message.channel.send(embed=embed, view=ValidationView(message.author.id, service), delete_after=600)
    await bot.process_commands(message)

@bot.command()
async def ping(ctx): await ctx.send(f"Pong! {NOM_AGENCE}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setupbusiness(ctx): await ctx.send(f"Setup business OK BOSS - {NOM_AGENCE}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setuppack(ctx):
    embed = discord.Embed(title="PACK REELS 8+1 - RAMANE OFM", description="Clique pour generer ton pack 8 Reels + 1 Story dans ce meme salon\n\nAuto-delete 20min - Descriptions qui percent incluses + VRAIES VIDEOS", color=0xE1306C)
    await ctx.send(embed=embed, view=PackGenerateView())

@bot.command()
@commands.has_permissions(administrator=True)
async def manager(ctx, member: discord.Member): await add_grade_logic(ctx, member, "Manager")

@bot.command()
@commands.has_permissions(administrator=True)
async def teamleader(ctx, member: discord.Member): await add_grade_logic(ctx, member, "Team Leader")

@bot.command()
@commands.has_permissions(administrator=True)
async def va(ctx, member: discord.Member): await add_grade_logic(ctx, member, "VA DEBUTANT")

@bot.command()
@commands.has_permissions(administrator=True)
async def pro(ctx, member: discord.Member): await add_grade_logic(ctx, member, "VA Pro")

@bot.command()
@commands.has_permissions(administrator=True)
async def vapro(ctx, member: discord.Member): await add_grade_logic(ctx, member, "VA Pro")

@bot.command()
@commands.has_permissions(administrator=True)
async def vadebutant(ctx, member: discord.Member): await add_grade_logic(ctx, member, "VA DEBUTANT")

@bot.command()
@commands.has_permissions(administrator=True)
async def boss(ctx, member: discord.Member): await add_grade_logic(ctx, member, "BOSS")

@bot.command()
@commands.has_permissions(administrator=True)
async def removegrade(ctx, member: discord.Member, *, grade: str):
    role = get_real_role(ctx.guild, grade)
    if role:
        await member.remove_roles(role)
        await ctx.send(
