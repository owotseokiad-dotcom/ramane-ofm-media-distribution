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
    if not m: m = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", url)
    if not m: m = re.search(r"/file/d/([a-zA-Z0-9-_]+)", url)
    return m.group(1) if m else url

async def list_drive_files(folder_id):
    if not GOOGLE_DRIVE_API_KEY or not folder_id: return []
    try:
        url = "https://www.googleapis.com/drive/v3/files"
        params = {"q": f"'{folder_id}' in parents and trashed=false", "key": GOOGLE_DRIVE_API_KEY, "fields": "files(id,name,mimeType)", "pageSize": 100}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=15) as r:
                if r.status!= 200:
                    txt = await r.text()
                    print(f"[DRIVE ERR] {folder_id} status {r.status} {txt[:200]}")
                    return []
                data = await r.json()
                return data.get("files", [])
    except Exception as e:
        print(f"[DRIVE EX] {e}")
        return []

async def download_drive_file(file_id):
    if not GOOGLE_DRIVE_API_KEY: return None
    try:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        params = {"alt": "media", "key": GOOGLE_DRIVE_API_KEY}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=90) as r:
                if r.status!= 200: return None
                return await r.read()
    except: return None

async def get_solde_5sim():
    global solde_cache, dernier_check
    if time.time() - dernier_check < 120 and solde_cache!= 0: return solde_cache
    try:
        headers = {"Authorization": "Bearer " + FIVESIM_TOKEN, "Accept": "application/json"}
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
        headers = {"Authorization": "Bearer " + FIVESIM_TOKEN, "Accept": "application/json"}
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
        self.children[0].custom_id = "gen_" + service_type
    @discord.ui.button(label="Generer un numero - 200F", style=discord.ButtonStyle.success)
    async def generate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="PAIEMENT 200F - " + NOM_AGENCE, description=f"**Service:** {self.service_type.upper()}\n\n**1. MoMo:** {MOMO_NUM}\n**2. USDT BEP20:** {CRYPTO_ADDR}\n\nPaye et envoie capture ICI.", color=0x00ff00)
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
        if solde == -1: await interaction.followup.send("Erreur 5SIM", ephemeral=True)
        else: await interaction.followup.send(f"Solde 5SIM: {solde}$", ephemeral=True)
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
        await interaction.response.send_message("Seul le BOSS peut valider.", ephemeral=True)
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
                await channel.send(f"<@{self.client_id}> NUMERO: {tel} ID:{order_id} - Attente code...", delete_after=600)
                code=None
                async with aiohttp.ClientSession() as session:
                    headers = {"Authorization": "Bearer " + FIVESIM_TOKEN, "Accept": "application/json"}
                    for _ in range(16):
                        await asyncio.sleep(30)
                        async with session.get(f"https://5sim.net/v1/user/check/{order_id}", headers=headers) as check_resp:
                            try:
                                check_data = await check_resp.json()
                                if check_data.get("sms") and len(check_data["sms"])>0:
                                    code=check_data["sms"][0]["code"]; break
                            except: continue
                    if code:
                        await channel.send(f"<@{self.client_id}> CODE: {code} - Numero {tel} - Benefice 110F", delete_after=600)
                        break
                    else:
                        async with session.get(f"https://5sim.net/v1/user/cancel/{order_id}", headers=headers):
                            await channel.send(f"<@{self.client_id}> Pas de code T{tentative}. CANCEL + RACHAT...", delete_after=300)
                        tentative+=1; await asyncio.sleep(5); continue
            except Exception as e:
                await channel.send(f"Erreur {e}", delete_after=120); await asyncio.sleep(10); continue

def get_real_role(guild, keyword):
    keyword = keyword.lower()
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
        try: role = await guild.create_role(name=keyword, color=discord.Color(0x3498db))
        except: await ctx.send(f"Role {keyword} introuvable"); return
    await member.add_roles(role)
    await ctx.send(f"{member.mention} est maintenant {role.name} BOSS")

def find_channel(guild, keywords):
    for ch in guild.text_channels:
        if any(k in ch.name.lower() for k in keywords): return ch
    return None

DRIVE_REGEX = r"https://drive\.google\.com/(?:drive/folders/|file/d/|open\?id=)([a-zA-Z0-9-_]{15,})"

async def get_all_drive_links(guild):
    chan = find_channel(guild, ["drive-reels", "drive"])
    if not chan: return []
    links = []
    async for msg in chan.history(limit=None):
        ids = re.findall(DRIVE_REGEX, msg.content)
        for fid in ids:
            clean_url = f"https://drive.google.com/drive/folders/{fid}"
            first_line = msg.content.split('\n')[0]
            first_line = re.sub(r'https?://\S+', '', first_line).strip()
            if len(first_line) < 2: first_line = f"MODEL {len(links)+1}"
            links.append({"url": clean_url, "id": fid, "name": first_line.upper()[:80]})
    uniq = {}
    for l in links: uniq[l['id']] = l
    print(f"[DRIVE] {len(uniq)} liens trouves")
    return list(uniq.values())

async def get_all_descriptions(guild):
    chan = find_channel(guild, ["description"])
    if not chan: return []
    descs = []
    async for msg in chan.history(limit=500):
        if len(msg.content) > 10: descs.append(msg.content)
    return descs

class ModelSelectView(discord.ui.View):
    def __init__(self, links, parent):
        super().__init__(timeout=180)
        self.links = links
        self.parent = parent
        options = [discord.SelectOption(label=l['name'][:90], value=l['id']) for l in links[:25]]
        sel = discord.ui.Select(placeholder=f"{len(links)} Models - Choisis", options=options)
        async def cb(inter: discord.Interaction):
            await inter.response.defer(ephemeral=True)
            cid = sel.values[0]
            chosen = next((x for x in self.links if x['id']==cid), None)
            if chosen:
                await self.parent.send_pack_for_link(inter, chosen)
        sel.callback = cb
        self.add_item(sel)

class PackGenerateView(discord.ui.View):
    def __
