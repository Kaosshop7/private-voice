import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput, UserSelect
from discord import app_commands
import os
import json
import psutil
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ บอททำงานปกติบน Render แล้วสัส!"

def run_server():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_server)
    t.start()

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
active_channels = {} 

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

async def setup_hook():
    try:
        await bot.tree.sync()
        print("✅ ซิงค์คำสั่ง Slash Command อัตโนมัติเรียบร้อย!")
    except Exception as e:
        print(f"⚠️ Error ซิงค์คำสั่ง: {e}")

bot.setup_hook = setup_hook

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
        except Exception:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดตอนแก้ห้องว่ะ", ephemeral=True)

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

class RoomControl(View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=None)
        self.voice_channel = channel

    async def check_owner(self, interaction: discord.Interaction):
        owner_id = active_channels.get(self.voice_channel.id)
        if interaction.user.id != owner_id:
            await interaction.response.send_message("❌ มึงไม่ใช่เจ้าของห้อง อย่ามากด!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="ล็อค", style=discord.ButtonStyle.danger, emoji="🔒", row=0)
    async def lock(self, interaction: discord.Interaction, button: Button):
        if not await self.check_owner(interaction): return
        try:
            await self.voice_channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("🔒 ล็อคห้องแล้ว!", ephemeral=True)
        except: await interaction.response.send_message("❌ ล็อคห้องไม่ได้ เช็คสิทธิ์บอทด้วย", ephemeral=True)

    @discord.ui.button(label="ปลดล็อค", style=discord.ButtonStyle.success, emoji="🔓", row=0)
    async def unlock(self, interaction: discord.Interaction, button: Button):
        if not await self.check_owner(interaction): return
        try:
            await self.voice_channel.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.response.send_message("🔓 ปลดล็อคห้องแล้ว!", ephemeral=True)
        except: pass

    @discord.ui.button(label="ซ่อน", style=discord.ButtonStyle.secondary, emoji="👻", row=0)
    async def hide(self, interaction: discord.Interaction, button: Button):
        if not await self.check_owner(interaction): return
        try:
            await self.voice_channel.set_permissions(interaction.guild.default_role, view_channel=False)
            await interaction.response.send_message("👻 ซ่อนห้องเรียบร้อย!", ephemeral=True)
        except: pass

    @discord.ui.button(label="แสดง", style=discord.ButtonStyle.primary, emoji="👁️", row=0)
    async def unhide(self, interaction: discord.Interaction, button: Button):
        if not await self.check_owner(interaction): return
        try:
            await self.voice_channel.set_permissions(interaction.guild.default_role, view_channel=True)
            await interaction.response.send_message("👁️ แสดงห้องปกติแล้ว!", ephemeral=True)
        except: pass

    @discord.ui.button(label="จำกัดคน", style=discord.ButtonStyle.secondary, emoji="👥", row=0)
    async def limit(self, interaction: discord.Interaction, button: Button):
        if not await self.check_owner(interaction): return
        await interaction.response.send_modal(LimitModal(self.voice_channel))

    @discord.ui.button(label="เปลี่ยนชื่อ", style=discord.ButtonStyle.primary, emoji="✏️", row=1)
    async def rename(self, interaction: discord.Interaction, button: Button):
        if not await self.check_owner(interaction): return
        await interaction.response.send_modal(RenameModal(self.voice_channel))

    @discord.ui.select(cls=UserSelect, placeholder="🔑 เลือกเพื่อนที่จะอนุญาตให้เข้าห้อง (ทะลุห้องล็อค)", row=2)
    async def whitelist_user(self, interaction: discord.Interaction, select: UserSelect):
        if not await self.check_owner(interaction): return
        user = select.values[0]
        try:
            await self.voice_channel.set_permissions(user, connect=True)
            await interaction.response.send_message(f"✅ อนุญาตให้ {user.mention} เข้าห้องได้แล้ว!", ephemeral=True)
        except: await interaction.response.send_message("❌ ทำรายการไม่สำเร็จ", ephemeral=True)

    @discord.ui.select(cls=UserSelect, placeholder="🥾 เลือกคนที่ต้องการเตะออกจากห้อง", row=3)
    async def kick_user(self, interaction: discord.Interaction, select: UserSelect):
        if not await self.check_owner(interaction): return
        user = select.values[0]
        if user in self.voice_channel.members:
            try:
                await user.move_to(None)
                await interaction.response.send_message(f"🥾 เตะ {user.mention} บินออกจากห้องไปละ!", ephemeral=True)
            except: await interaction.response.send_message("❌ เตะไม่ได้ มันของแข็งว่ะ", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ มันไม่ได้อยู่ในห้องนี้เว้ยมึง!", ephemeral=True)

    @discord.ui.select(cls=UserSelect, placeholder="👑 เลือกคนที่จะโอนตำแหน่งหัวหน้าห้องให้", row=4)
    async def transfer_owner(self, interaction: discord.Interaction, select: UserSelect):
        if not await self.check_owner(interaction): return
        new_owner = select.values[0]
        old_owner_id = active_channels.get(self.voice_channel.id)
        
        if new_owner.id == old_owner_id:
            await interaction.response.send_message("❌ มึงจะโอนให้ตัวเองทำหอกอะไร!", ephemeral=True)
            return
            
        old_owner = interaction.guild.get_member(old_owner_id)
        try:
            if old_owner: await self.voice_channel.set_permissions(old_owner, overwrite=None) 
            await self.voice_channel.set_permissions(new_owner, connect=True, manage_channels=True, move_members=True, send_messages=True)
            active_channels[self.voice_channel.id] = new_owner.id 
            await interaction.response.send_message(f"👑 โอนสิทธิ์ห้องให้ {new_owner.mention} แล้ว!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ โอนสิทธิ์ไม่สำเร็จ", ephemeral=True)

@bot.tree.command(name="setup", description="สร้างหมวดหมู่และห้อง")
@app_commands.default_permissions(administrator=True)
async def setup_system(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    
    try:
        default_overwrites = {}
        for role in interaction.guild.roles:
            default_overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, connect=True, send_messages=False,
                create_public_threads=False, create_private_threads=False, read_message_history=True
            )
        default_overwrites[interaction.guild.me] = discord.PermissionOverwrite(
            view_channel=True, connect=True, send_messages=True, manage_channels=True, manage_permissions=True
        )

        category = await interaction.guild.create_category("🌟 | VIP VOICE ROOMS", overwrites=default_overwrites)
        hub_channel = await interaction.guild.create_voice_channel("➕ | กดเพื่อสร้างห้องส่วนตัว", category=category)

        if guild_id not in server_configs:
            server_configs[guild_id] = {'role_ids': [], 'log_id': None, 'banned_users': []}
            
        server_configs[guild_id]['hub_id'] = hub_channel.id
        server_configs[guild_id]['cat_id'] = category.id
        save_db(server_configs)

        embed = discord.Embed(
            title="🛠️ สร้างระบบสำเร็จ!",
            description=f"📂 **หมวดหมู่:** {category.mention}\n🎯 **ห้อง Hub:** {hub_channel.mention}\n\nใช้ `/set_role` เพื่อแอดรายชื่อยศที่สร้างห้องได้เลย",
            color=discord.Color.brand_green()
        )
        guild_image = get_guild_image(interaction.guild)
        if guild_image: embed.set_image(url=guild_image)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ เกิดข้อผิดพลาดตอนสร้างห้องว่ะ: {e}", ephemeral=True)

@bot.tree.command(name="set_role", description="เพิ่มหรือลบยศที่สร้างห้องได้")
@app_commands.choices(action=[app_commands.Choice(name="➕ เพิ่มยศ", value="add"), app_commands.Choice(name="➖ ลบยศ", value="remove")])
@app_commands.default_permissions(administrator=True)
async def set_role(interaction: discord.Interaction, action: app_commands.Choice[str], role: discord.Role):
    guild_id = str(interaction.guild.id)
    if guild_id not in server_configs: server_configs[guild_id] = {'hub_id': None, 'cat_id': None, 'role_ids': [], 'log_id': None, 'banned_users': []}
    roles_list = server_configs[guild_id].setdefault('role_ids', [])
    
    if action.value == "add" and role.id not in roles_list:
        roles_list.append(role.id)
        msg = f"✅ เพิ่มยศ {role.mention} เข้าสู่ระบบ!"
    elif action.value == "remove" and role.id in roles_list:
        roles_list.remove(role.id)
        msg = f"✅ ลบยศ {role.mention} ออกจากระบบแล้ว!"
    else:
        msg = "⚠️ ข้อมูลยศนี้มี/หรือไม่มีอยู่ในระบบอยู่แล้ว!"
    save_db(server_configs)
    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="set_log", description="ตั้งค่าห้องแชทสำหรับให้บอทส่งแจ้งเตือน Log")
@app_commands.default_permissions(administrator=True)
async def set_log(interaction: discord.Interaction, text_channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    if guild_id not in server_configs: server_configs[guild_id] = {'hub_id': None, 'cat_id': None, 'role_ids': [], 'log_id': None, 'banned_users': []}
    server_configs[guild_id]['log_id'] = text_channel.id
    save_db(server_configs)
    await interaction.response.send_message(f"✅ บันทึกห้องส่ง Log ไปที่ {text_channel.mention} เรียบร้อยมึง!", ephemeral=True)

@bot.tree.command(name="ban_voice", description="แบนสมาชิกไม่ให้สร้างห้องเสียง")
@app_commands.default_permissions(administrator=True)
async def ban_voice(interaction: discord.Interaction, member: discord.Member):
    guild_id = str(interaction.guild.id)
    if guild_id not in server_configs: server_configs[guild_id] = {'hub_id': None, 'cat_id': None, 'role_ids': [], 'log_id': None, 'banned_users': []}
    banned_list = server_configs[guild_id].setdefault('banned_users', [])

    if member.id not in banned_list:
        banned_list.append(member.id)
        save_db(server_configs)
        await interaction.response.send_message(f"🚫 แบนไอ้ {member.mention} เรียบร้อย!", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ ไอ้ {member.mention} มันโดนแบนอยู่แล้วมึง!", ephemeral=True)

@bot.tree.command(name="unban_voice", description="ปลดแบนสมาชิกให้กลับมาสร้างห้องได้")
@app_commands.default_permissions(administrator=True)
async def unban_voice(interaction: discord.Interaction, member: discord.Member):
    guild_id = str(interaction.guild.id)
    if guild_id not in server_configs: server_configs[guild_id] = {'hub_id': None, 'cat_id': None, 'role_ids': [], 'log_id': None, 'banned_users': []}
    banned_list = server_configs[guild_id].setdefault('banned_users', [])

    if member.id in banned_list:
        banned_list.remove(member.id)
        save_db(server_configs)
        await interaction.response.send_message(f"✅ ปลดแบนไอ้ {member.mention} แล้ว!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ ไอ้ {member.mention} มันไม่ได้โดนแบน!", ephemeral=True)

@bot.tree.command(name="help", description="ดูคู่มือและวิธีใช้งานบอททั้งหมด")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 คู่มือการใช้งานระบบห้องเสียง",
        description="บอทสร้างห้องเสียงส่วนตัวอัตโนมัติ",
        color=discord.Color.gold()
    )
    
    guild_image = get_guild_image(interaction.guild)
    if guild_image: embed.set_thumbnail(url=guild_image)

    embed.add_field(
        name="🛠️ คำสั่งสำหรับแอดมิน",
        value=(
            "**`/setup`** - สร้างหมวดหมู่และห้อง Hub อัตโนมัติ\n"
            "**`/set_role`** - เพิ่ม/ลบยศสิทธิพิเศษในการสร้างห้อง\n"
            "**`/set_log`** - ตั้งค่าห้องรับแจ้งเตือนการสร้าง/ลบห้อง\n"
            "**`/ban_voice`** - แบนคนไม่ให้สร้างห้อง\n"
            "**`/unban_voice`** - ปลดแบนให้คนกลับมาสร้างห้องได้"
        ),
        inline=False
    )
    embed.add_field(
        name="🎛️ ปุ่มในแผงควบคุม (สำหรับเจ้าของห้อง)",
        value=(
            "🔒 **ล็อค** / 🔓 **ปลดล็อค** - ปิด/เปิดไม่ให้คนอื่นเข้า\n"
            "👻 **ซ่อน** / 👁️ **แสดง** - ทำให้ห้องหายไปจากสายตาคนอื่น\n"
            "👥 **จำกัดคน** - กำหนดจำนวนคนเข้าห้องได้\n"
            "✏️ **เปลี่ยนชื่อ** - พิมพ์ชื่อห้องใหม่ได้ตามใจชอบ\n"
            "🔑 **เมนูอนุญาตเพื่อน** - ดึงเพื่อนทะลุเข้าห้องล็อคได้\n"
            "🥾 **เมนูเตะคน** - เตะคนกวนตีนออกจากห้อง\n"
            "👑 **เมนูโอนสิทธิ์** - ยกตำแหน่งหัวหน้าห้องให้คนอื่น"
        ),
        inline=False
    )
    embed.set_footer(text=f"ร้องขอโดย {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_voice_state_update(member, before, after):
    guild_id = str(member.guild.id)
    config = server_configs.get(guild_id)
    if not config or not config.get('hub_id'): return

    if after.channel and after.channel.id == config['hub_id']:
        
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
        category = guild.get_channel(config.get('cat_id'))
        
        if not category or len(category.channels) >= 50:
            try: await member.move_to(None)
            except: pass
            return

        try:
            overwrites = {}
            for role in guild.roles:
                overwrites[role] = discord.PermissionOverwrite(
                    connect=True, view_channel=True, send_messages=False,
                    create_public_threads=False, create_private_threads=False, read_message_history=True
                )
            overwrites[member] = discord.PermissionOverwrite(
                connect=True, manage_channels=True, move_members=True, send_messages=True, read_message_history=True
            )
            overwrites[guild.me] = discord.PermissionOverwrite(
                connect=True, view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True
            )

            new_channel = await guild.create_voice_channel(
                name=f"👑 ห้องของ {member.display_name}",
                category=category,
                overwrites=overwrites
            )
            
            await member.move_to(new_channel)
            active_channels[new_channel.id] = member.id 

            embed = discord.Embed(
                title="🎛️ แผงควบคุมห้องส่วนตัว", 
                description="กดปุ่มหรือเลือกเมนูด้านล่างเพื่อจัดการห้องได้เลย!\n",
                color=discord.Color.gold()
            )
            guild_image = get_guild_image(guild)
            if guild_image: embed.set_thumbnail(url=guild_image)

            view = RoomControl(channel=new_channel)
            await new_channel.send(content=member.mention, embed=embed, view=view)
            
            await send_log(member.guild, f"🟢 **{member.display_name}** ได้สร้างห้องเสียง: {new_channel.mention}")

        except Exception as e:
            print(f"⚠️ Error สร้างห้อง: {e}")
            try: await member.move_to(None)
            except: pass

    if before.channel and before.channel.id in active_channels:
        if len(before.channel.members) == 0:
            try:
                await before.channel.delete()
                active_channels.pop(before.channel.id, None)
                await send_log(member.guild, f"🔴 ห้องถูกลบอัตโนมัติแล้ว")
            except Exception as e:
                print(f"⚠️ Error ลบห้อง: {e}")
                active_channels.pop(before.channel.id, None)

@tasks.loop(seconds=15)
async def auto_status():
    try:
        ping = round(bot.latency * 1000)
        
        process = psutil.Process(os.getpid())
        ram_usage = process.memory_info().rss / (1024 * 1024)
        
        room_count = len(active_channels)
        
        status_text = f"🟢 Ping: {ping}ms | 💾 RAM: {ram_usage:.1f}MB | 🎙️ ห้องใช้งาน: {room_count}"
        
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=status_text))
    except Exception as e:
        print(f"⚠️ Error อัปเดตสถานะ: {e}")

@bot.event
async def on_ready():
    print(f'✅ บอท {bot.user} รันระบบเต็มสูบ พร้อมลุยแล้วสัส!')
    auto_status.start()

keep_alive()
TOKEN = os.environ.get('DISCORD_TOKEN') or 'ใส่_TOKEN_ของบอทตรงนี้'
bot.run(TOKEN)
