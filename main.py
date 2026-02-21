import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput, UserSelect, RoleSelect
from discord import app_commands
import os
import json
import psutil
from flask import Flask
from threading import Thread

# ==========================================
# 0. ระบบ Keep Alive
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ บอททำงานปกติบน Render แล้วสัส! (เวอร์ชั่นแก้บัค 100%)"

def run_server():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_server)
    t.start()

# ==========================================
# 1. ระบบฐานข้อมูล
# ==========================================
DB_FILE = "database.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error โหลดไฟล์ DB: {e}")
    return {}

def save_db(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"⚠️ Error เซฟไฟล์ DB: {e}")

server_configs = load_db()
active_channels = server_configs.setdefault("active_channels", {}) 

# ==========================================
# 2. ตั้งค่าบอทพื้นฐาน
# ==========================================
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

async def send_log(guild, message):
    config = server_configs.get(str(guild.id), {})
    log_id = config.get('log_id')
    if log_id:
        channel = guild.get_channel(log_id)
        if channel:
            try:
                embed = discord.Embed(description=message, color=discord.Color.blue())
                await channel.send(embed=embed)
            except: pass

def get_guild_image(guild):
    if guild.banner: return guild.banner.url
    elif guild.icon: return guild.icon.url
    return None

# ==========================================
# 3. ระบบ Modal หน้าต่างกรอกข้อมูล
# ==========================================
class LimitModal(Modal, title='ตั้งค่าจำนวนคนเข้าห้อง'):
    limit_input = TextInput(label='ใส่จำนวนคน (0 = ไม่จำกัด)', style=discord.TextStyle.short, required=True, max_length=2)
    def __init__(self, channel):
        super().__init__()
        self.voice_channel = channel
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.limit_input.value)
            await self.voice_channel.edit(user_limit=limit)
            await interaction.response.send_message(f"👥 จำกัดคนเข้าห้องที่ {limit} คนแล้ว!" if limit > 0 else "👥 เลิกจำกัดคนแล้ว!", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ พิมพ์เป็นตัวเลขดิวะ!", ephemeral=True)

class RenameModal(Modal, title='เปลี่ยนชื่อห้อง'):
    name_input = TextInput(label='ใส่ชื่อห้องใหม่ที่ต้องการ', style=discord.TextStyle.short, required=True, max_length=30)
    def __init__(self, channel):
        super().__init__()
        self.voice_channel = channel
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.voice_channel.edit(name=self.name_input.value)
            await interaction.response.send_message(f"✏️ เปลี่ยนชื่อห้องเป็น **{self.name_input.value}** เรียบร้อย!", ephemeral=True)
        except Exception:
            await interaction.response.send_message("❌ เปลี่ยนชื่อไม่สำเร็จ", ephemeral=True)

# ==========================================
# 4. ระบบหน้าต่างย่อย (Dropdown)
# ==========================================
class WhitelistView(View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60) 
        self.voice_channel = channel

    @discord.ui.select(cls=UserSelect, placeholder="🔑 เลือกเพื่อนที่จะอนุญาตให้เข้าห้อง (ทะลุห้องล็อค)")
    async def select_user(self, interaction: discord.Interaction, select: UserSelect):
        user = select.values[0]
        try:
            await self.voice_channel.set_permissions(user, connect=True)
            await interaction.response.send_message(f"✅ อนุญาตให้ {user.mention} เข้าห้องได้แล้ว!", ephemeral=True)
        except: await interaction.response.send_message("❌ ทำรายการไม่สำเร็จ", ephemeral=True)

class KickView(View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.voice_channel = channel

    @discord.ui.select(cls=UserSelect, placeholder="🥾 เลือกคนที่ต้องการเตะออกจากห้อง")
    async def select_user(self, interaction: discord.Interaction, select: UserSelect):
        user = select.values[0]
        if user in self.voice_channel.members:
            try:
                await user.move_to(None)
                await interaction.response.send_message(f"🥾 เตะ {user.mention} บินออกจากห้องไปละ!", ephemeral=True)
            except: await interaction.response.send_message("❌ เตะไม่ได้ มันของแข็งว่ะ", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ มันไม่ได้อยู่ในห้องนี้เว้ยมึง!", ephemeral=True)

class TransferView(View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.voice_channel = channel

    @discord.ui.select(cls=UserSelect, placeholder="👑 เลือกคนที่จะโอนตำแหน่งหัวหน้าห้องให้")
    async def select_user(self, interaction: discord.Interaction, select: UserSelect):
        new_owner = select.values[0]
        owner_id = active_channels.get(str(self.voice_channel.id))
        
        if new_owner.id == owner_id or new_owner.id == interaction.user.id:
            await interaction.response.send_message("❌ มึงจะโอนให้ตัวเองทำหอกอะไร!", ephemeral=True)
            return
            
        old_owner = interaction.guild.get_member(interaction.user.id)
        try:
            if old_owner: await self.voice_channel.set_permissions(old_owner, overwrite=None) 
            await self.voice_channel.set_permissions(new_owner, connect=True, manage_channels=True, move_members=True)
            active_channels[str(self.voice_channel.id)] = new_owner.id 
            save_db(server_configs)
            await interaction.response.send_message(f"👑 โอนสิทธิ์ห้องให้ {new_owner.mention} แล้ว!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ โอนสิทธิ์ไม่สำเร็จ", ephemeral=True)

class RoleManageSelect(RoleSelect):
    def __init__(self, action: str):
        self.action_type = action
        ph = "➕ เลือกยศที่จะเพิ่ม" if action == "add" else "➖ เลือกยศที่จะลบออก"
        super().__init__(placeholder=ph, min_values=1, max_values=25)

    async def callback(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        if guild_id not in server_configs:
            server_configs[guild_id] = {'hub_id': None, 'cat_id': None, 'role_ids': [], 'log_id': None, 'banned_users': []}
        
        roles_list = server_configs[guild_id].setdefault('role_ids', [])
        processed = []

        if self.action_type == "add":
            for r in self.values:
                if r.id not in roles_list:
                    roles_list.append(r.id)
                    processed.append(r.name)
            msg = f"✅ แอดเพิ่มเรียบร้อย **{len(processed)}** ยศ!" if processed else "⚠️ ยศที่มึงเลือก มันมีอยู่ในระบบหมดแล้ว!"
        else:
            for r in self.values:
                if r.id in roles_list:
                    roles_list.remove(r.id)
                    processed.append(r.name)
            msg = f"✅ ลบออกเรียบร้อย **{len(processed)}** ยศ!" if processed else "⚠️ ยศพวกนี้ไม่ได้อยู่ในระบบอยู่แล้ว!"

        save_db(server_configs)
        await interaction.response.edit_message(content=msg, view=None)

class RoleManageView(View):
    def __init__(self, action: str):
        super().__init__(timeout=120)
        self.add_item(RoleManageSelect(action))

# ==========================================
# 5. แผงควบคุมหลักแบบ "ปุ่มล้วน"
# ==========================================
class RoomControl(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def get_valid_channel(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ มึงต้องเข้าไปนั่งในห้องเสียงของมึงก่อน ถึงจะกดปุ่มได้!", ephemeral=True)
            return None
            
        channel = interaction.user.voice.channel
        
        is_owner = False
        if str(channel.id) in active_channels:
            if active_channels[str(channel.id)] == interaction.user.id:
                is_owner = True
        else:
            user_perms = channel.overwrites_for(interaction.user)
            if user_perms.manage_channels:
                is_owner = True
                active_channels[str(channel.id)] = interaction.user.id
                save_db(server_configs)
        
        config = server_configs.get(str(interaction.guild.id), {})
        cat_id = config.get('cat_id')
        
        if channel.category_id != cat_id or channel.id == config.get('hub_id'):
            await interaction.response.send_message("❌ ห้องที่มึงอยู่ไม่ใช่ห้องส่วนตัวเว้ย!", ephemeral=True)
            return None
            
        if not is_owner:
            await interaction.response.send_message("❌ มึงไม่ใช่เจ้าของห้องนี้ อย่ามามั่วกด!", ephemeral=True)
            return None
            
        return channel

    @discord.ui.button(label="ล็อค", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_lock", row=0)
    async def lock(self, interaction: discord.Interaction, button: Button):
        channel = await self.get_valid_channel(interaction)
        if not channel: return
        try:
            await channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("🔒 ล็อคห้องแล้ว! คนอื่นห้ามเข้า", ephemeral=True)
        except: pass

    @discord.ui.button(label="ปลดล็อค", style=discord.ButtonStyle.success, emoji="🔓", custom_id="btn_unlock", row=0)
    async def unlock(self, interaction: discord.Interaction, button: Button):
        channel = await self.get_valid_channel(interaction)
        if not channel: return
        try:
            await channel.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.response.send_message("🔓 ปลดล็อคห้องแล้ว!", ephemeral=True)
        except: pass

    @discord.ui.button(label="ซ่อน", style=discord.ButtonStyle.secondary, emoji="👻", custom_id="btn_hide", row=0)
    async def hide(self, interaction: discord.Interaction, button: Button):
        channel = await self.get_valid_channel(interaction)
        if not channel: return
        try:
            await channel.set_permissions(interaction.guild.default_role, view_channel=False)
            await interaction.response.send_message("👻 ซ่อนห้องเรียบร้อย!", ephemeral=True)
        except: pass

    @discord.ui.button(label="แสดง", style=discord.ButtonStyle.primary, emoji="👁️", custom_id="btn_unhide", row=0)
    async def unhide(self, interaction: discord.Interaction, button: Button):
        channel = await self.get_valid_channel(interaction)
        if not channel: return
        try:
            await channel.set_permissions(interaction.guild.default_role, view_channel=True)
            await interaction.response.send_message("👁️ แสดงห้องปกติแล้ว!", ephemeral=True)
        except: pass

    @discord.ui.button(label="จำกัดคน", style=discord.ButtonStyle.secondary, emoji="👥", custom_id="btn_limit", row=0)
    async def limit(self, interaction: discord.Interaction, button: Button):
        channel = await self.get_valid_channel(interaction)
        if not channel: return
        await interaction.response.send_modal(LimitModal(channel))

    @discord.ui.button(label="เปลี่ยนชื่อ", style=discord.ButtonStyle.primary, emoji="✏️", custom_id="btn_rename", row=1)
    async def rename(self, interaction: discord.Interaction, button: Button):
        channel = await self.get_valid_channel(interaction)
        if not channel: return
        await interaction.response.send_modal(RenameModal(channel))

    @discord.ui.button(label="อนุญาตเพื่อน", style=discord.ButtonStyle.success, emoji="🔑", custom_id="btn_whitelist", row=1)
    async def whitelist(self, interaction: discord.Interaction, button: Button):
        channel = await self.get_valid_channel(interaction)
        if not channel: return
        await interaction.response.send_message("👇 เลือกชื่อเพื่อนที่ต้องการอนุญาตให้เข้าห้องล็อคได้เลยมึง:", view=WhitelistView(channel), ephemeral=True)

    @discord.ui.button(label="เตะคน", style=discord.ButtonStyle.danger, emoji="🥾", custom_id="btn_kick", row=1)
    async def kick(self, interaction: discord.Interaction, button: Button):
        channel = await self.get_valid_channel(interaction)
        if not channel: return
        await interaction.response.send_message("👇 เลือกชื่อคนที่มึงต้องการเตะออกจากห้องเลย:", view=KickView(channel), ephemeral=True)

    @discord.ui.button(label="โอนหัวหน้า", style=discord.ButtonStyle.secondary, emoji="👑", custom_id="btn_transfer", row=1)
    async def transfer(self, interaction: discord.Interaction, button: Button):
        channel = await self.get_valid_channel(interaction)
        if not channel: return
        await interaction.response.send_message("👇 เลือกชื่อคนที่มึงต้องการโอนตำแหน่งหัวหน้าห้องให้:", view=TransferView(channel), ephemeral=True)

# 🚨 [แก้บัคที่นี่!] รวม Setup Hook ไว้จุดเดียว ไม่ซ้ำซ้อนแล้ว!
async def system_setup_hook():
    bot.add_view(RoomControl())
    try:
        await bot.tree.sync()
        print("✅ ซิงค์คำสั่ง Slash Command อัตโนมัติเรียบร้อย!")
    except Exception as e:
        print(f"⚠️ Error ซิงค์คำสั่ง: {e}")

bot.setup_hook = system_setup_hook

# ==========================================
# 6. คำสั่งแอดมิน 
# ==========================================
@bot.tree.command(name="setup", description="สร้างหมวดหมู่และห้อง")
@app_commands.default_permissions(administrator=True)
async def setup_system(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    
    try:
        category = await interaction.guild.create_category("🌟 • VIP VOICE ROOMS")
        control_channel = await interaction.guild.create_text_channel("🎛️-แผงควบคุมห้อง", category=category)
        hub_channel = await interaction.guild.create_voice_channel("➕ | กดเพื่อสร้างห้องส่วนตัว", category=category)

        if guild_id not in server_configs:
            server_configs[guild_id] = {'role_ids': [], 'log_id': None, 'banned_users': []}
            
        server_configs[guild_id]['hub_id'] = hub_channel.id
        server_configs[guild_id]['cat_id'] = category.id
        save_db(server_configs)

        control_embed = discord.Embed(
            title="🎛️ แผงควบคุมห้องส่วนตัว", 
            description="กดปุ่มด้านล่างนี้เพื่อจัดการห้องได้เลย!\n\n*(ต้องเข้าไปนั่งในห้องเสียงก่อนนะ ถึงจะกดปุ่มใช้งานได้)*",
            color=discord.Color.gold()
        )
        guild_image = get_guild_image(interaction.guild)
        if guild_image: control_embed.set_thumbnail(url=guild_image)
        await control_channel.send(embed=control_embed, view=RoomControl())

        embed = discord.Embed(
            title="🛠️ สร้างระบบสำเร็จ",
            description=f"📂 **หมวดหมู่:** {category.mention}\n🎯 **ห้อง :** {hub_channel.mention}\n📱 **แผงควบคุม:** {control_channel.mention}\n\nใช้ `/set_role` เพื่อแอดรายชื่อยศที่สร้างห้องได้เลย",
            color=discord.Color.brand_green()
        )
        if guild_image: embed.set_image(url=guild_image)
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ เกิดข้อผิดพลาดตอนสร้างห้อง: {e}", ephemeral=True)

@bot.tree.command(name="set_role", description="เพิ่มหรือลบยศ")
@app_commands.choices(action=[app_commands.Choice(name="➕ เพิ่มยศ", value="add"), app_commands.Choice(name="➖ ลบยศ", value="remove")])
@app_commands.default_permissions(administrator=True)
async def set_role(interaction: discord.Interaction, action: app_commands.Choice[str]):
    view = RoleManageView(action.value)
    text = "👇 เลือดยศที่มึงต้องการจากเมนูด้านล่างเลย:"
    await interaction.response.send_message(text, view=view, ephemeral=True)

@bot.tree.command(name="set_log", description="ตั้งค่าห้องแชทสำหรับให้บอทส่งแจ้งเตือน Log")
@app_commands.default_permissions(administrator=True)
async def set_log(interaction: discord.Interaction, text_channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    if guild_id not in server_configs: server_configs[guild_id] = {'hub_id': None, 'cat_id': None, 'role_ids': [], 'log_id': None, 'banned_users': []}
    server_configs[guild_id]['log_id'] = text_channel.id
    save_db(server_configs)
    await interaction.response.send_message(f"✅ บันทึกห้องส่ง Log ไปที่ {text_channel.mention} เรียบร้อย", ephemeral=True)

@bot.tree.command(name="ban_voice", description="แบนสมาชิกไม่ให้สร้างห้องเสียง")
@app_commands.default_permissions(administrator=True)
async def ban_voice(interaction: discord.Interaction, member: discord.Member):
    guild_id = str(interaction.guild.id)
    if guild_id not in server_configs: server_configs[guild_id] = {'hub_id': None, 'cat_id': None, 'role_ids': [], 'log_id': None, 'banned_users': []}
    banned_list = server_configs[guild_id].setdefault('banned_users', [])

    if member.id not in banned_list:
        banned_list.append(member.id)
        save_db(server_configs)
        await interaction.response.send_message(f"🚫 แบนไอ้ {member.mention} เรียบร้อย", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ ไอ้ {member.mention} มันโดนแบนอยู่แล้ว", ephemeral=True)

@bot.tree.command(name="unban_voice", description="ปลดแบนสมาชิก")
@app_commands.default_permissions(administrator=True)
async def unban_voice(interaction: discord.Interaction, member: discord.Member):
    guild_id = str(interaction.guild.id)
    if guild_id not in server_configs: server_configs[guild_id] = {'hub_id': None, 'cat_id': None, 'role_ids': [], 'log_id': None, 'banned_users': []}
    banned_list = server_configs[guild_id].setdefault('banned_users', [])

    if member.id in banned_list:
        banned_list.remove(member.id)
        save_db(server_configs)
        await interaction.response.send_message(f"✅ ปลดแบนไอ้ {member.mention} แล้ว", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ ไอ้ {member.mention} มันไม่ได้โดนแบน", ephemeral=True)

@bot.tree.command(name="help", description="ดูคู่มือและวิธีใช้งานบอททั้งหมด")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 คู่มือการใช้งานระบบห้องเสียง Private",
        description="บอทสร้างห้องเสียงส่วนตัวอัตโนมัติ",
        color=discord.Color.gold()
    )
    guild_image = get_guild_image(interaction.guild)
    if guild_image: embed.set_thumbnail(url=guild_image)

    embed.add_field(
        name="🛠️ คำสั่งสำหรับแอดมิน",
        value=(
            "**`/setup`** - สร้างหมวดหมู่และห้อง Hub อัตโนมัติ\n"
            "**`/set_role`** - เพิ่ม/ลบยศสิทธิพิเศษ\n"
            "**`/set_log`** - ตั้งค่าห้องรับแจ้งเตือน\n"
            "**`/ban_voice`** - แบนคนไม่ให้สร้างห้อง\n"
            "**`/unban_voice`** - ปลดแบน"
        ),
        inline=False
    )
    embed.add_field(
        name="🎛️ ปุ่มในแผงควบคุม",
        value=(
            "🔒 **ล็อค** / 🔓 **ปลดล็อค** - ปิด/เปิดห้อง\n"
            "👻 **ซ่อน** / 👁️ **แสดง** - ทำให้ห้องหายไป/กลับมา\n"
            "👥 **จำกัดคน** - กำหนดจำนวนคน\n"
            "✏️ **เปลี่ยนชื่อ** - เปลี่ยนชื่อห้อง\n"
            "🔑 **อนุญาตเพื่อน** - เด้งหน้าต่างดึงเพื่อนเข้าห้องล็อค\n"
            "🥾 **เตะคน** - เด้งหน้าต่างเตะคน\n"
            "👑 **โอนหัวหน้า** - เด้งหน้าต่างยกห้องให้เพื่อน"
        ),
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==========================================
# 7. ระบบสร้าง/ลบห้องอัตโนมัติ
# ==========================================
@bot.event
async def on_voice_state_update(member, before, after):
    guild_id = str(member.guild.id)
    config = server_configs.get(guild_id)
    if not config: return

    hub_id = config.get('hub_id')
    cat_id = config.get('cat_id')

    if after.channel and after.channel.id == hub_id:
        banned_users = config.get('banned_users', [])
        if member.id in banned_users:
            try: 
                await member.move_to(None) 
                await member.send("🚫 มึงโดนแอดมินแบนจากการสร้างห้องส่วนตัว ไปเคลียร์กันเองนะ")
            except: pass
            return

        allowed_roles = config.get('role_ids', [])
        has_permission = any(role.id in allowed_roles for role in member.roles)
        
        if not has_permission or not allowed_roles:
            try: await member.move_to(None)
            except: pass
            return

        guild = member.guild
        category = guild.get_channel(cat_id)
        
        if not category or len(category.channels) >= 50:
            try: await member.move_to(None)
            except: pass
            return

        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                member: discord.PermissionOverwrite(connect=True, manage_channels=True, move_members=True)
            }

            new_channel = await guild.create_voice_channel(
                name=f"👑 ห้องของ {member.display_name}",
                category=category,
                overwrites=overwrites
            )
            
            try:
                await member.move_to(new_channel)
                active_channels[str(new_channel.id)] = member.id 
                save_db(server_configs)
                await send_log(member.guild, f"🟢 **{member.display_name}** ได้สร้างห้องเสียง: {new_channel.mention}")
            except Exception:
                await new_channel.delete()

        except Exception as e:
            print(f"⚠️ Error สร้างห้อง: {e}")
            try: await member.move_to(None)
            except: pass

    if before.channel and before.channel.category_id == cat_id and before.channel.id != hub_id:
        if len(before.channel.members) == 0:
            try:
                await before.channel.delete()
                if str(before.channel.id) in active_channels:
                    active_channels.pop(str(before.channel.id), None)
                    save_db(server_configs)
                await send_log(member.guild, f"🔴 ห้องถูกลบอัตโนมัติแล้ว")
            except Exception as e:
                print(f"⚠️ Error ลบห้อง: {e}")

# ==========================================
# 8. อัปเดตสถานะอัตโนมัติ
# ==========================================
@tasks.loop(seconds=15)
async def auto_status():
    try:
        ping = round(bot.latency * 1000)
        process = psutil.Process(os.getpid())
        ram_usage = process.memory_info().rss / (1024 * 1024)
        
        room_count = 0
        for guild in bot.guilds:
            config = server_configs.get(str(guild.id), {})
            cat_id = config.get('cat_id')
            if cat_id:
                category = guild.get_channel(cat_id)
                if category:
                    room_count += max(0, len(category.voice_channels) - 1)
        
        status_text = f"🟢 Ping: {ping}ms | 💾 RAM: {ram_usage:.1f}MB | 🎙️ ห้องใช้งาน: {room_count}"
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=status_text))
    except Exception as e:
        print(f"⚠️ Error อัปเดตสถานะ: {e}")

@bot.event
async def on_ready():
    print(f'✅ บอท {bot.user} รันระบบกันบัค 100% พร้อมลุยแล้วสัส!')
    auto_status.start()

keep_alive()
TOKEN = os.environ.get('DISCORD_TOKEN') or 'ใส่_TOKEN_ของบอทตรงนี้'
bot.run(TOKEN)
