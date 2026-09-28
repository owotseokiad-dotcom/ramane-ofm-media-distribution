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
            await inter.response.defer()
            cid = sel.values[0]
            chosen = next((x for x in self.links if x['id']==cid), None)
            if chosen:
                await self.parent.send_pack_for_link(inter, chosen)
        sel.callback = cb
        self.add_item(sel)

class PackGenerateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Pack Aleatoire", style=discord.ButtonStyle.success, emoji="🎲", custom_id="pack_auto_v4")
    async def auto_pack(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        links = await get_all_drive_links(interaction.guild)
        if not links:
            await interaction.followup.send("Aucun lien dans #drive-reels BOSS", ephemeral=True)
            return
        await self.send_pack_for_link(interaction, random.choice(links))
    @discord.ui.button(label="Choisir un Model", style=discord.ButtonStyle.primary, emoji="📂", custom_id="pack_choose_v4")
    async def choose_pack(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        links = await get_all_drive_links(interaction.guild)
        if not links:
            await interaction.followup.send("Aucun lien", ephemeral=True)
            return
        view = ModelSelectView(links, self)
        await interaction.followup.send(f"📂 **{len(links)} Models dispo** - Choisis ton model :", view=view, ephemeral=True)

    # --- PARTIE CORRIGEE POUR EMAR ---
    async def send_pack_for_link(self, interaction, chosen):
        guild = interaction.guild
        descs = await get_all_descriptions(guild)
        main_folder_id = chosen['id']
        root_files = await list_drive_files(main_folder_id)
        print(f"[PACK] {chosen['name']} root contient {len(root_files)} items")

        reels_files = []
        story_folder_id = None
        subfolders = [f for f in root_files if "folder" in f.get("mimeType","")]

        if not subfolders:
            reels_files = root_files
        else:
            for sub in subfolders:
                lname = sub["name"].lower()
                if any(k in lname for k in ["photo","story","cta","image"]):
                    # On verifie si vide ou pas plus tard
                    story_folder_id = sub["id"]
                    continue
                # TOUT autre dossier = on fouille dedans pour les videos (EMAR, VIDEOS, etc)
                files_in_sub = await list_drive_files(sub["id"])
                print(f"[PACK] Sous-dossier {sub['name']} -> {len(files_in_sub)} fichiers")
                for f in files_in_sub:
                    if "folder" not in f.get("mimeType",""):
                        reels_files.append(f)
            # fallback si rien trouvé
            if len(reels_files) == 0:
                reels_files = [f for f in root_files if "folder" not in f.get("mimeType","")]

        video_files = [f for f in reels_files if "video" in f.get("mimeType","") or f["name"].lower().endswith((".mp4",".mov",".mkv",".avi",".m4v"))]
        if len(video_files) == 0:
            video_files = [f for f in reels_files if "folder" not in f.get("mimeType","")]

        print(f"[PACK] {chosen['name']} -> {len(video_files)} videos detectees")

        if len(video_files) == 0:
            await interaction.followup.send(f"❌ Dossier **{chosen['name']}** vide après fouille de {len(subfolders)} dossiers. Verifie partage 'Toute personne disposant du lien'", ephemeral=True)
            return

        a_envoyer = min(len(video_files), 8)
        # Prend au hasard 8 parmi toutes
        video_files = random.sample(video_files, a_envoyer) if len(video_files) > a_envoyer else video_files
        selected_descs = random.sample(descs, a_envoyer) if len(descs)>=a_envoyer else (descs*a_envoyer)[:a_envoyer] if descs else [""]*a_envoyer

        sent=[]
        embed=discord.Embed(title=f"{chosen['name']} | PACK {a_envoyer}", description=f"Model: {chosen['name']}\nAuto-delete 20min", color=0xE1306C)
        m=await interaction.channel.send(content=f"PACK pour {interaction.user.mention} - **{chosen['name']}** ({a_envoyer} Reels)", embed=embed)
        sent.append(m)

        for i,vf in enumerate(video_files):
            data=await download_drive_file(vf["id"])
            if not data: continue
            file_obj=discord.File(io.BytesIO(data), filename=vf["name"])
            txt=f"**REEL {i+1}/{a_envoyer} - {chosen['name']}**\n```\n{selected_descs[i][:1000]}\n```"
            mm=await interaction.channel.send(content=txt, file=file_obj)
            sent.append(mm)

        if story_folder_id:
            sfiles=await list_drive_files(story_folder_id)
            if sfiles:
                sdata=await download_drive_file(sfiles[0]["id"])
                if sdata:
                    story_channel=find_channel(guild, ["photos-story-cta","photos-story","story","cta"])
                    await (story_channel or interaction.channel).send(content=f"**STORY 1/1 - {chosen['name']}** pour {interaction.user.mention}", file=discord.File(io.BytesIO(sdata), filename=sfiles[0]["name"]))

        await interaction.followup.send(f"✅ Pack **{chosen['name']}** genere! {a_envoyer} Reels", ephemeral=True)
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
    embed = discord.Embed(
        title="🎬 RAMANE OFM - GENERATEUR DE PACK",
        description="**Le bot fait quoi?**\nIl prend TOUS les liens que le BOSS met dans #drive-reels et te livre le pack complet.\n\n**2 options :**\n🎲 **Pack Aleatoire** : Bot choisit un model au hasard\n📂 **Choisir un Model** : Tu choisis ton model (liste des noms)\n\n**3 Avantages :**\n1️⃣ **Rapide** : 8 Reels HD + 1 Story + Captions en 10s\n2️⃣ **Pro** : Descriptions pretes a copier-coller\n3️⃣ **Propre** : Auto-delete 20min, salon propre\n\n👇 **Clique ci-dessous**",
        color=0xE1306C
    )
    embed.set_footer(text="RAMANE OFM - Tous les liens Drive sont accessibles")
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
    r = get_real_role(ctx.guild, grade)
    if r: await member.remove_roles(r); await ctx.send(r.name)
@bot.command()
@commands.has_permissions(administrator=True)
async def fixcolors(ctx): await auto_fix_colors(); await ctx.send("Couleurs fixees")
@bot.command()
@commands.has_permissions(administrator=True)
async def clean(ctx, amount: int = 10):
    await ctx.channel.purge(limit=amount)
    await ctx.send(f"{amount} messages supprimes", delete_after=3)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print("Flask lance")
    if not TOKEN:
        print("DISCORD_TOKEN MANQUANT!")
        while True: time.sleep(60)
    while True:
        try:
            print(f"Lancement {NOM_AGENCE}...")
            bot.run(TOKEN)
        except Exception as e:
            print(f"ERREUR BOT: {e}")
            traceback.print_exc()
            time.sleep(10)
