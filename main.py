import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import math
import asyncio
import logging
import traceback
import shutil
from datetime import datetime
import io
import aiohttp
import time
import uuid
import random
import psutil
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('discord_bot')

# --------- Config -----------
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("Error: DISCORD_BOT_TOKEN environment variable not set!")
    print("Please set your Discord bot token in the Secrets tab.")
    exit(1)

# Validate token format
if not TOKEN.startswith(('Bot ', 'Bearer ')) and len(TOKEN) < 50:
    print("Warning: Token format appears invalid. Make sure you're using the bot token, not client secret.")
    print("Bot tokens are typically 59+ characters long.")

GUILD_ID = 1362531923586453678  # Your guild ID here - only changeable in code

# Bot configuration that can be changed via commands
BOT_CONFIG = {
    "tier_channel_id": 1362836497060855959,
    "auction_forum_channel_id": 1362896002981433354,
    "premium_auction_forum_channel_id": 1377669568146833480,
    "bidder_role_id": 1362851306330652842,
    "buyer_role_id": 1362851277222056108,
    "staff_roles": [1362545929038594118, 1362546172429996323],
    "default_embed_color": 0x680da8,
    "tier_colors": {
        "s": 0xFFD700,
        "a": 0xC0C0C0,
        "b": 0xCD7F32,
        "c": 0x3498DB,
        "d": 0x95A5A6,
    },
    "slot_roles": {
        1334277888249303161: {"name": "2 boosts", "slots": 1},
        1334277824210800681: {"name": "3-5 boosts", "slots": 2},
        1334277764173271123: {"name": "6+ boosts", "slots": 4},
        1334276381969874995: {"name": "level30", "slots": 1},
        1344029633607372883: {"name": "level40", "slots": 2},
        1344029863845302272: {"name": "level50", "slots": 4},
    },
    "currency_symbol": "$",
    "levelup_channel_id": None,
    "suggestions_channel_id": None,
    "reports_channel_id": None
}

# Intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# --------- Data loading & saving -----------

def load_json(file_name):
    if os.path.isfile(file_name):
        with open(file_name, "r") as f:
            return json.load(f)
    return {}

# Load bot configuration
bot_config = load_json("bot_config.json")
if bot_config:
    BOT_CONFIG.update(bot_config)

tier_data = load_json("tierlist.json")
member_stats = load_json("member_stats.json")
shops_data = load_json("shops.json")
user_balances = load_json("balances.json")
user_inventories = load_json("inventories.json")
reaction_roles = load_json("reaction_roles.json")
sticky_messages = load_json("sticky_messages.json")
server_settings = load_json("server_settings.json")
verification_data = load_json("verification.json")
user_profiles = load_json("user_profiles.json")
giveaways_data = load_json("giveaways.json")
auction_data = load_json("auctions.json")
premium_slots = load_json("premium_slots.json")
logging_settings = load_json("logging_settings.json")
member_warnings = load_json("member_warnings.json")
autoresponders = load_json("autoresponders.json")
profile_presets = load_json("profile_presets.json")

def save_json(file_name, data):
    with open(file_name, "w") as f:
        json.dump(data, f, indent=2)

def save_all():
    save_json("bot_config.json", BOT_CONFIG)
    save_json("tierlist.json", tier_data)
    save_json("member_stats.json", member_stats)
    save_json("shops.json", shops_data)
    save_json("balances.json", user_balances)
    save_json("inventories.json", user_inventories)
    save_json("reaction_roles.json", reaction_roles)
    save_json("sticky_messages.json", sticky_messages)
    save_json("server_settings.json", server_settings)
    save_json("verification.json", verification_data)
    save_json("auctions.json", auction_data)
    save_json("user_profiles.json", user_profiles)
    save_json("giveaways.json", giveaways_data)
    save_json("premium_slots.json", premium_slots)
    save_json("logging_settings.json", logging_settings)
    save_json("member_warnings.json", member_warnings)
    save_json("autoresponders.json", autoresponders)
    save_json("profile_presets.json", profile_presets)

# --------- Helper Functions -----------

def has_staff_role(interaction: discord.Interaction):
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(role_id in BOT_CONFIG["staff_roles"] for role_id in user_role_ids)

def has_admin_permissions(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator or interaction.user.id == interaction.guild.owner_id

def get_currency_symbol():
    return BOT_CONFIG.get("currency_symbol", "$")

def get_color_for_tier(tier: str):
    return BOT_CONFIG["tier_colors"].get(tier.lower(), BOT_CONFIG["default_embed_color"])

def calculate_level(xp: int):
    return int(math.sqrt(xp / 100)) if xp >= 0 else 0

def calculate_xp_for_level(level: int):
    return level * level * 100

def ensure_user_in_stats(user_id: str):
    if user_id not in member_stats:
        member_stats[user_id] = {
            "xp": 0,
            "daily_messages": 0,
            "weekly_messages": 0,
            "monthly_messages": 0,
            "all_time_messages": 0,
        }
    if user_id not in user_balances:
        user_balances[user_id] = 0
    if user_id not in user_inventories:
        user_inventories[user_id] = {}

# --------- Image Upload Function -----------

async def upload_image_to_thread(thread, image_url):
    """Download and upload an image to a Discord thread"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    file_extension = image_url.split('.')[-1].lower()
                    if file_extension not in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                        file_extension = 'png'

                    file = discord.File(
                        io.BytesIO(image_data),
                        filename=f"image.{file_extension}"
                    )
                    await thread.send(file=file)
                    return True
    except Exception as e:
        logger.error(f"Failed to upload image {image_url}: {e}")
        return False
    return False

# --------- Guild Restriction Check -----------

def guild_only():
    def predicate(interaction: discord.Interaction):
        return interaction.guild and interaction.guild.id == GUILD_ID
    return app_commands.check(predicate)

# --------- Enhanced Help System -----------

class HelpNavigationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.current_page = 0
        self.pages = self.create_help_pages()

    def create_help_pages(self):
        return [
            {
                "title": "🏠 Main Menu",
                "description": "Welcome to the comprehensive help system! Use the navigation buttons or select a category below to explore all available commands.",
                "fields": [
                    {"name": "🎮 Quick Start", "value": "• `/profile create` - Set up your profile\n• `/level` - Check your XP and level\n• `/balance` - View your currency\n• `/shop list` - Browse available items", "inline": False},
                    {"name": "👥 User Commands", "value": "Commands available to all members", "inline": True},
                    {"name": "⚡ Staff Commands", "value": "Commands for staff members only", "inline": True},
                    {"name": "🔧 Admin Commands", "value": "Commands for administrators", "inline": True}
                ]
            },
            {
                "title": "👥 User Commands - Social & Economy",
                "description": "Commands available to all server members",
                "fields": [
                    {"name": "💰 Economy Commands", "value": "`/balance` - Check your currency balance\n`/shop list [shop_name]` - Browse shops and items\n`/shop buy` - Purchase items\n`/inventory` - View your items\n`/gift` - Give items to others\n`/trade` - Trade items with others", "inline": False},
                    {"name": "📊 Level & Stats", "value": "`/level [user]` - View level and XP\n`/level leaderboard` - Server rankings\n`/messages` - View message statistics", "inline": False},
                    {"name": "👤 Profile System", "value": "`/profile create` - Create your profile\n`/profile view [user]` - View profiles\n`/profile edit` - Edit your profile\n`/profile list_presets` - Available presets", "inline": False}
                ]
            },
            {
                "title": "👥 User Commands - Utility & Fun",
                "description": "Additional commands for member interaction",
                "fields": [
                    {"name": "📝 Utility Commands", "value": "`/suggest` - Submit suggestions to staff\n`/report` - Report issues or users\n`/afk [reason]` - Set yourself as AFK\n`/remindme` - Set personal reminders", "inline": False},
                    {"name": "🎰 Premium Slots", "value": "`/viewslots` - Check your premium auction slots\n`/auction list` - View active auctions", "inline": False},
                    {"name": "🎉 Giveaways", "value": "`/giveaway_claim` - Mark prizes as claimed (if winner)\n`/giveaway_unclaimed` - View unclaimed prizes", "inline": False}
                ]
            },
            {
                "title": "⚡ Staff Commands - Content Management",
                "description": "Commands available to staff members only",
                "fields": [
                    {"name": "🏆 Tier List Management", "value": "`/tierlist` - Interactive tier list posting\n`/tierlist_move` - Move items between tiers", "inline": False},
                    {"name": "🛍️ Shop Management", "value": "`/shop` - Interactive shop management\n• Create, edit, and manage shops\n• Add/remove items and discounts\n• Full inventory control", "inline": False},
                    {"name": "🎭 Reaction Roles", "value": "`/reaction_role` - Set up reaction role systems\n• Role assignment on reactions\n• XP and currency rewards\n• Custom responses", "inline": False}
                ]
            },
            {
                "title": "⚡ Staff Commands - Events & Automation",
                "description": "Advanced staff management tools",
                "fields": [
                    {"name": "🎉 Giveaway System", "value": "`/giveaway` - Create interactive giveaways\n• Role restrictions and requirements\n• Extra entry systems\n• Automatic winner selection", "inline": False},
                    {"name": "🏺 Auction System", "value": "`/auction` - Create auction posts\n• Regular and premium auctions\n• Image upload support\n• Automatic thread creation", "inline": False},
                    {"name": "🤖 Automation Tools", "value": "`/autoresponder` - Set up auto-responses\n`/sticky` - Create sticky messages\n`/verification` - Set up verification systems", "inline": False}
                ]
            },
            {
                "title": "⚡ Staff Commands - Moderation",
                "description": "Tools for maintaining server order",
                "fields": [
                    {"name": "🔨 Basic Moderation", "value": "`/ban` - Ban members with logging\n`/kick` - Kick members\n`/warn` - Issue warnings\n`/quarantine` - Isolate members temporarily\n`/purge` - Mass delete messages", "inline": False},
                    {"name": "📋 Warning System", "value": "`/warnings` - View member warnings\n`/remove_warning` - Remove specific warnings\n• Full warning history tracking\n• Warning ID system", "inline": False},
                    {"name": "💰 Economy Management", "value": "`/balance_give` - Give currency to users\n`/balance_remove` - Remove currency\n`/addslots` / `/removeslots` - Manage premium slots", "inline": False}
                ]
            },
            {
                "title": "🔧 Admin Commands - Configuration",
                "description": "Commands for server administrators only",
                "fields": [
                    {"name": "⚙️ Bot Configuration", "value": "`/config` - Interactive configuration panel\n• Channel settings\n• Role management\n• Color customization\n• Currency setup", "inline": False},
                    {"name": "📊 Logging System", "value": "`/logging_setup` - Configure action logging\n`/logging_disable` - Disable specific logging\n• Moderation logs\n• Member activity\n• Message events", "inline": False},
                    {"name": "🎭 Profile Presets", "value": "`/profile create_preset` - Create new presets\n`/profile delete_preset` - Remove presets\n• Custom field creation\n• Template management", "inline": False}
                ]
            },
            {
                "title": "🔧 Admin Commands - Management",
                "description": "Advanced administrative tools",
                "fields": [
                    {"name": "🧹 Data Management", "value": "`/cleanup_data` - Remove old/invalid data\n`/export_data` - Backup data files\n• Automated cleanup systems\n• Data integrity maintenance", "inline": False},
                    {"name": "🔍 Debug Tools", "value": "`/debug_info` - Bot performance metrics\n`/debug_user` - User data inspection\n`/debug_performance` - System statistics", "inline": False},
                    {"name": "🏪 Role Menu System", "value": "`/role_menu` - Create self-role systems\n• Interactive role selection\n• Category organization\n• Automatic role management", "inline": False}
                ]
            },
            {
                "title": "📚 Command Usage Examples",
                "description": "Detailed examples of complex commands",
                "fields": [
                    {"name": "🏺 Auction Creation", "value": "Use `/auction` to open the interactive auction creator:\n1. Set item details (name, starting bid, payment methods)\n2. Add up to 5 images (URLs)\n3. Configure seller information\n4. Create the auction thread", "inline": False},
                    {"name": "🎉 Giveaway Setup", "value": "Use `/giveaway` for comprehensive giveaway creation:\n1. Set basic info (name, prizes, duration)\n2. Add requirements (roles, levels, messages)\n3. Configure extra entries and bypass roles\n4. Launch the giveaway", "inline": False},
                    {"name": "👤 Profile System", "value": "Complete profile workflow:\n1. Staff create presets with `/profile create_preset`\n2. Users create profiles with `/profile create`\n3. Edit anytime with `/profile edit`\n4. View with `/profile view`", "inline": False}
                ]
            }
        ]

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_page(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.primary)
    async def home_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        await self.update_page(interaction)

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await self.update_page(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.select(
        placeholder="Jump to a specific section...",
        options=[
            discord.SelectOption(label="🏠 Main Menu", value="0", description="Overview and quick start"),
            discord.SelectOption(label="👥 User: Social & Economy", value="1", description="Profile, balance, trading"),
            discord.SelectOption(label="👥 User: Utility & Fun", value="2", description="AFK, reminders, reports"),
            discord.SelectOption(label="⚡ Staff: Content", value="3", description="Tier lists, shops, roles"),
            discord.SelectOption(label="⚡ Staff: Events", value="4", description="Giveaways, auctions, automation"),
            discord.SelectOption(label="⚡ Staff: Moderation", value="5", description="Bans, warnings, purges"),
            discord.SelectOption(label="🔧 Admin: Configuration", value="6", description="Bot setup, logging"),
            discord.SelectOption(label="🔧 Admin: Management", value="7", description="Data, debug, role menus"),
            discord.SelectOption(label="📚 Examples", value="8", description="Detailed usage examples"),
        ]
    )
    async def page_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.current_page = int(select.values[0])
        await self.update_page(interaction)

    async def update_page(self, interaction: discord.Interaction):
        page = self.pages[self.current_page]
        embed = discord.Embed(
            title=page["title"],
            description=page["description"],
            color=BOT_CONFIG["default_embed_color"]
        )

        for field in page["fields"]:
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", False)
            )

        embed.set_footer(text=f"Page {self.current_page + 1} of {len(self.pages)} • Use buttons or dropdown to navigate")
        await interaction.response.edit_message(embed=embed, view=self)

@tree.command(name="help", description="Comprehensive help system with all bot commands", guild=discord.Object(id=GUILD_ID))
@guild_only()
async def help_command(interaction: discord.Interaction):
    view = HelpNavigationView()
    page = view.pages[0]

    embed = discord.Embed(
        title=page["title"],
        description=page["description"],
        color=BOT_CONFIG["default_embed_color"]
    )

    for field in page["fields"]:
        embed.add_field(
            name=field["name"],
            value=field["value"],
            inline=field.get("inline", False)
        )

    embed.set_footer(text=f"Page 1 of {len(view.pages)} • Use buttons or dropdown to navigate")
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# --------- Enhanced Auction System with Image Upload -----------

class AuctionSetupView(discord.ui.View):
    def __init__(self, is_premium=False):
        super().__init__(timeout=600)
        self.is_premium = is_premium
        self.auction_data = {"is_premium": is_premium, "images": []}

    @discord.ui.button(label="📝 Item Details", style=discord.ButtonStyle.primary)
    async def set_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AuctionDetailsModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🖼️ Add Images", style=discord.ButtonStyle.secondary)
    async def add_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "name" not in self.auction_data:
            await interaction.response.send_message("Please set item details first.", ephemeral=True)
            return
        modal = AuctionImagesModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="👤 Set Seller", style=discord.ButtonStyle.secondary)
    async def set_seller(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AuctionSellerModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="⚙️ Advanced Options", style=discord.ButtonStyle.secondary)
    async def advanced_options(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AuctionAdvancedView(self)
        embed = discord.Embed(
            title="Advanced Auction Options",
            description="Configure additional auction settings:",
            color=BOT_CONFIG["default_embed_color"]
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="✅ Create Auction", style=discord.ButtonStyle.green)
    async def create_auction(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not all(key in self.auction_data for key in ["name", "seller_id", "starting_bid"]):
            await interaction.response.send_message("Please fill out all required fields first.", ephemeral=True)
            return

        await self.create_auction_thread(interaction)

    async def update_display(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"Creating {'Premium ' if self.is_premium else ''}Auction",
            color=BOT_CONFIG["default_embed_color"]
        )

        # Show current progress
        progress = []
        if "name" in self.auction_data:
            progress.append(f"✅ Item: {self.auction_data['name']}")
        else:
            progress.append("❌ Item details not set")

        if "seller_id" in self.auction_data:
            seller = interaction.guild.get_member(self.auction_data["seller_id"])
            progress.append(f"✅ Seller: {seller.mention if seller else 'Unknown'}")
        else:
            progress.append("❌ Seller not set")

        if self.auction_data.get("images"):
            progress.append(f"✅ Images: {len(self.auction_data['images'])} added")
        else:
            progress.append("❌ No images added")

        embed.description = "\n".join(progress)

        if "starting_bid" in self.auction_data:
            embed.add_field(
                name="Auction Details",
                value=f"Starting Bid: ${self.auction_data['starting_bid']}\n"
                      f"Payment Methods: {self.auction_data.get('payment_methods', 'Not set')}\n"
                      f"Instant Accept: {self.auction_data.get('instant_accept', 'N/A')}",
                inline=False
            )

        await interaction.response.edit_message(embed=embed, view=self)

    async def create_auction_thread(self, interaction):
        if not has_staff_role(interaction):
            await interaction.response.send_message("You don't have permission to create auctions.", ephemeral=True)
            return

        # Check premium slots if needed
        if self.auction_data.get("is_premium"):
            seller_id = str(self.auction_data["seller_id"])
            user_slots = premium_slots.get(seller_id, {"total_slots": 0, "used_slots": 0})
            if user_slots["used_slots"] >= user_slots["total_slots"]:
                await interaction.response.send_message("Seller doesn't have available premium slots.", ephemeral=True)
                return

        # Build auction text
        auction_text = f"# {self.auction_data['name']}"

        if self.auction_data.get("server", "N/A") != "N/A":
            auction_text += f" ({self.auction_data['server']})"

        auction_text += " <:cutesy_star:1364222257349525506>\n"

        # Add rarity and type
        rarity_line = "ᯓ★ "
        if self.auction_data.get("rarity", "NA") != "NA":
            rarity_line += self.auction_data["rarity"]
        if self.auction_data.get("type_category", "NA") != "NA":
            if self.auction_data.get("rarity", "NA") != "NA":
                rarity_line += " ‧ "
            rarity_line += self.auction_data["type_category"]
        auction_text += rarity_line + "\n"

        seller = interaction.guild.get_member(self.auction_data["seller_id"])
        auction_text += f"<:neonstars:1364582630363758685> ── .✦ Seller: {seller.mention}\n\n"

        # Payment methods
        if self.auction_data.get("payment_methods"):
            methods_formatted = " ‧ ".join([method.strip() for method in self.auction_data["payment_methods"].split(",")])
            auction_text += f"      ✶⋆.˚ Payment Methods:\n                 {methods_formatted}\n\n"

        # Bidding info
        auction_text += f"╰┈➤ Starting: ${self.auction_data['starting_bid']}\n"
        auction_text += f"╰┈➤ Increase: {self.auction_data.get('increase', '$1')}\n"
        auction_text += f"╰┈➤ IA: {self.auction_data.get('instant_accept', 'N/A')}\n\n"

        # Extra info
        if self.auction_data.get("extra_info"):
            auction_text += f"༘⋆ Extra Info: {self.auction_data['extra_info']}\n"

        # Holds
        if self.auction_data.get("holds"):
            auction_text += f"𓂃 𓈒𓏸 Holds: {self.auction_data['holds']}"
            if self.auction_data.get("hold_days"):
                auction_text += f"  ‧  {self.auction_data['hold_days']} Days"
            auction_text += "\n\n"

        # End timestamp
        if self.auction_data.get("end_timestamp"):
            auction_text += f"     Ends: {self.auction_data['end_timestamp']}\n\n"

        # Role mentions
        bidder_role = interaction.guild.get_role(BOT_CONFIG["bidder_role_id"])
        buyer_role = interaction.guild.get_role(BOT_CONFIG["buyer_role_id"])

        if bidder_role and buyer_role:
            auction_text += f"{bidder_role.mention} {buyer_role.mention}"

        # Get forum channel
        channel_key = "premium_auction_forum_channel_id" if self.auction_data.get("is_premium") else "auction_forum_channel_id"
        forum_channel = bot.get_channel(BOT_CONFIG[channel_key])

        if not forum_channel:
            await interaction.response.send_message("Auction forum channel not found.", ephemeral=True)
            return

        try:
            await interaction.response.send_message("Creating auction thread and uploading images...", ephemeral=True)

            # Create forum thread
            thread = await forum_channel.create_thread(
                name=self.auction_data["name"],
                content=auction_text
            )

            # Upload images as attachments to ensure they display properly
            images_uploaded = 0
            for img_url in self.auction_data.get("images", []):
                if img_url and img_url.strip():
                    success = await upload_image_to_thread(thread, img_url)
                    if success:
                        images_uploaded += 1

            # Use premium slot if needed
            if self.auction_data.get("is_premium"):
                seller_id = str(self.auction_data["seller_id"])
                if seller_id not in premium_slots:
                    premium_slots[seller_id] = {"total_slots": 0, "used_slots": 0}
                premium_slots[seller_id]["used_slots"] += 1

            # Save auction data
            auction_id = str(thread.id)
            auction_data[auction_id] = {
                "name": self.auction_data["name"],
                "seller_id": self.auction_data["seller_id"],
                "starting_bid": self.auction_data["starting_bid"],
                "thread_id": thread.id,
                "status": "active",
                "is_premium": self.auction_data.get("is_premium", False)
            }
            save_all()

            embed = discord.Embed(
                title="✅ Auction Created!",
                description=f"Auction for **{self.auction_data['name']}** has been posted in {thread.mention}!",
                color=0x00FF00
            )

            if images_uploaded > 0:
                embed.add_field(name="Images", value=f"{images_uploaded} images uploaded successfully", inline=True)

            await interaction.edit_original_response(embed=embed)

        except Exception as e:
            await interaction.edit_original_response(content=f"Failed to create auction: {str(e)}")

class AuctionDetailsModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Auction Item Details")
        self.view = view

        self.name = discord.ui.TextInput(
            label="Item Name",
            placeholder="Enter the item name",
            required=True,
            max_length=100
        )

        self.starting_bid = discord.ui.TextInput(
            label="Starting Bid (1-10)",
            placeholder="Enter starting bid ($1-$10)",
            required=True,
            max_length=2
        )

        self.payment_methods = discord.ui.TextInput(
            label="Payment Methods",
            placeholder="Separate with commas (e.g., PayPal, Venmo, Cash)",
            required=True,
            max_length=200,
            style=discord.TextStyle.paragraph
        )

        self.instant_accept = discord.ui.TextInput(
            label="Instant Accept",
            placeholder="Enter instant accept amount (e.g., $50)",
            required=False,
            max_length=20
        )

        self.add_item(self.name)
        self.add_item(self.starting_bid)
        self.add_item(self.payment_methods)
        self.add_item(self.instant_accept)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            starting_bid = int(self.starting_bid.value)
            if starting_bid < 1 or starting_bid > 10:
                await interaction.response.send_message("Starting bid must be between $1 and $10.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("Invalid starting bid. Please enter a number.", ephemeral=True)
            return

        self.view.auction_data.update({
            "name": self.name.value,
            "starting_bid": starting_bid,
            "payment_methods": self.payment_methods.value,
            "instant_accept": self.instant_accept.value or "N/A"
        })

        await self.view.update_display(interaction)

class AuctionImagesModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Add Auction Images")
        self.view = view

        self.images = discord.ui.TextInput(
            label="Image URLs",
            placeholder="Enter image URLs (one per line, max 5)",
            required=True,
            max_length=2000,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.images)

    async def on_submit(self, interaction: discord.Interaction):
        image_urls = [url.strip() for url in self.images.value.split('\n') if url.strip()]
        self.view.auction_data["images"] = image_urls[:5]  # Limit to 5 images

        await self.view.update_display(interaction)

class AuctionSellerModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Set Seller")
        self.view = view

        self.seller = discord.ui.TextInput(
            label="Seller User ID",
            placeholder="Enter the seller's Discord user ID",
            required=True,
            max_length=20
        )
        self.add_item(self.seller)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            seller_id = int(self.seller.value)
            seller = interaction.guild.get_member(seller_id)

            if not seller:
                await interaction.response.send_message("User not found in this server.", ephemeral=True)
                return

            self.view.auction_data["seller_id"] = seller_id
            await self.view.update_display(interaction)

        except ValueError:
            await interaction.response.send_message("Invalid user ID. Please enter numbers only.", ephemeral=True)

class AuctionAdvancedView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__(timeout=300)
        self.parent_view = parent_view

    @discord.ui.select(
        placeholder="Select server location...",
        options=[
            discord.SelectOption(label="US", value="US"),
            discord.SelectOption(label="UK", value="UK"),
            discord.SelectOption(label="CA", value="CA"),
            discord.SelectOption(label="TR", value="TR"),
            discord.SelectOption(label="N/A", value="N/A"),
        ]
    )
    async def server_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.parent_view.auction_data["server"] = select.values[0]
        await interaction.response.send_message(f"Set server location to: {select.values[0]}", ephemeral=True)

    @discord.ui.select(
        placeholder="Select item rarity...",
        options=[
            discord.SelectOption(label="S", value="S"),
            discord.SelectOption(label="NS", value="NS"),
            discord.SelectOption(label="NA", value="NA"),
        ]
    )
    async def rarity_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.parent_view.auction_data["rarity"] = select.values[0]
        await interaction.response.send_message(f"Set rarity to: {select.values[0]}", ephemeral=True)

    @discord.ui.select(
        placeholder="Select item type...",
        options=[
            discord.SelectOption(label="EXO", value="EXO"),
            discord.SelectOption(label="OG", value="OG"),
            discord.SelectOption(label="NA", value="NA"),
        ]
    )
    async def type_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.parent_view.auction_data["type_category"] = select.values[0]
        await interaction.response.send_message(f"Set type to: {select.values[0]}", ephemeral=True)

    @discord.ui.button(label="Set Extra Info", style=discord.ButtonStyle.secondary)
    async def set_extra_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AuctionExtraInfoModal(self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Back to Main", style=discord.ButtonStyle.primary)
    async def back_to_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.parent_view.update_display(interaction)

class AuctionExtraInfoModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Additional Auction Info")
        self.view = view

        self.extra_info = discord.ui.TextInput(
            label="Extra Information",
            placeholder="Any additional details about the item",
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph
        )

        self.holds = discord.ui.TextInput(
            label="Holds Accepted",
            placeholder="Yes, No, or Ask",
            required=False,
            max_length=10
        )

        self.hold_days = discord.ui.TextInput(
            label="Hold Days",
            placeholder="Number of days for holds",
            required=False,
            max_length=3
        )

        self.end_timestamp = discord.ui.TextInput(
            label="End Timestamp",
            placeholder="Discord timestamp for auction end",
            required=False,
            max_length=50
        )

        self.add_item(self.extra_info)
        self.add_item(self.holds)
        self.add_item(self.hold_days)
        self.add_item(self.end_timestamp)

    async def on_submit(self, interaction: discord.Interaction):
        if self.extra_info.value:
            self.view.auction_data["extra_info"] = self.extra_info.value
        if self.holds.value:
            self.view.auction_data["holds"] = self.holds.value
        if self.hold_days.value:
            try:
                self.view.auction_data["hold_days"] = int(self.hold_days.value)
            except ValueError:
                pass
        if self.end_timestamp.value:
            self.view.auction_data["end_timestamp"] = self.end_timestamp.value

        await interaction.response.send_message("Advanced settings updated!", ephemeral=True)

@tree.command(name="sync", description="Manually sync slash commands", guild=discord.Object(id=GUILD_ID))
@guild_only()
async def sync_commands(interaction: discord.Interaction):
    if not has_admin_permissions(interaction):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    try:
        synced = await tree.sync(guild=discord.Object(id=GUILD_ID))
        await interaction.response.send_message(f"✅ Synced {len(synced)} command(s) to this server.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to sync: {e}", ephemeral=True)

@tree.command(name="auction", description="Create auctions with interactive setup", guild=discord.Object(id=GUILD_ID))
@guild_only()
@app_commands.describe(
    auction_type="Type of auction to create"
)
@app_commands.choices(auction_type=[
    app_commands.Choice(name="Regular Auction", value="regular"),
    app_commands.Choice(name="Premium Auction", value="premium"),
])
async def auction(interaction: discord.Interaction, auction_type: app_commands.Choice[str]):
    if not has_staff_role(interaction):
        await interaction.response.send_message("You don't have permission to create auctions.", ephemeral=True)
        return

    is_premium = auction_type.value == "premium"
    view = AuctionSetupView(is_premium)

    embed = discord.Embed(
        title=f"Creating {'Premium ' if is_premium else ''}Auction",
        description="❌ Item details not set\n❌ Seller not set\n❌ No images added",
        color=BOT_CONFIG["default_embed_color"]
    )

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# --------- Enhanced Giveaway System -----------

class GiveawaySetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.giveaway_data = {
            "participants": {},
            "status": "creating",
            "required_roles": [],
            "extra_entry_roles": [],
            "bypass_roles": []
        }

    @discord.ui.button(label="📝 Basic Info", style=discord.ButtonStyle.primary)
    async def set_basic_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = GiveawayBasicModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="⚙️ Requirements", style=discord.ButtonStyle.secondary)
    async def set_requirements(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "name" not in self.giveaway_data:
            await interaction.response.send_message("Please set basic info first.", ephemeral=True)
            return
        view = GiveawayRequirementsView(self)
        embed = discord.Embed(
            title="Set Giveaway Requirements",
            description="Configure who can join your giveaway:",
            color=BOT_CONFIG["default_embed_color"]
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🎨 Appearance", style=discord.ButtonStyle.secondary)
    async def set_appearance(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = GiveawayAppearanceModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="✅ Create Giveaway", style=discord.ButtonStyle.green)
    async def create_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not all(key in self.giveaway_data for key in ["name", "prizes", "duration_hours", "winners", "host_id"]):
            await interaction.response.send_message("Please fill out all required fields first.", ephemeral=True)
            return

        await self.create_giveaway_message(interaction)

    async def update_display(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Creating Giveaway",
            color=BOT_CONFIG["default_embed_color"]
        )

        # Show current progress
        progress = []
        if "name" in self.giveaway_data:
            progress.append(f"✅ Name: {self.giveaway_data['name']}")
        else:
            progress.append("❌ Basic info not set")

        if self.giveaway_data.get("required_roles"):
            progress.append(f"✅ Role requirements: {len(self.giveaway_data['required_roles'])} roles")

        if self.giveaway_data.get("extra_entry_roles"):
            progress.append(f"✅ Extra entries: {len(self.giveaway_data['extra_entry_roles'])} configured")

        embed.description = "\n".join(progress) if progress else "No configuration set yet"

        if "duration_hours" in self.giveaway_data:
            embed.add_field(
                name="Giveaway Details",
                value=f"Duration: {self.giveaway_data['duration_hours']} hours\n"
                      f"Winners: {self.giveaway_data.get('winners', 'Not set')}\n"
                      f"Prizes: {self.giveaway_data.get('prizes', 'Not set')[:100]}...",
                inline=False
            )

        await interaction.response.edit_message(embed=embed, view=self)

    async def create_giveaway_message(self, interaction):
        giveaway_id = str(uuid.uuid4())
        end_time = int(time.time()) + (self.giveaway_data["duration_hours"] * 3600)

        self.giveaway_data.update({
            "id": giveaway_id,
            "end_time": end_time,
            "status": "active",
            "channel_id": interaction.channel.id
        })

        # Create giveaway embed
        embed = discord.Embed(
            title=f"🎉 {self.giveaway_data['name']}",
            description=f"**Prizes:** {self.giveaway_data['prizes']}",
            color=self.giveaway_data.get("embed_color", BOT_CONFIG["default_embed_color"])
        )

        host = interaction.guild.get_member(self.giveaway_data["host_id"])
        embed.add_field(name="Host", value=host.mention if host else "Unknown", inline=True)
        embed.add_field(name="Winners", value=str(self.giveaway_data["winners"]), inline=True)
        embed.add_field(name="Ends", value=f"<t:{end_time}:R>", inline=True)

        if self.giveaway_data.get("required_level"):
            embed.add_field(name="Required Level", value=str(self.giveaway_data["required_level"]), inline=True)

        if self.giveaway_data.get("thumbnail_url"):
            embed.set_thumbnail(url=self.giveaway_data["thumbnail_url"])
        if self.giveaway_data.get("image_url"):
            embed.set_image(url=self.giveaway_data["image_url"])

        embed.set_footer(text="Click the button below to join!")

        view = GiveawayJoinView(giveaway_id)
        giveaway_message = await interaction.followup.send(embed=embed, view=view)

        self.giveaway_data["message_id"] = giveaway_message.id
        giveaways_data[giveaway_id] = self.giveaway_data
        save_json("giveaways.json", giveaways_data)

        success_embed = discord.Embed(
            title="✅ Giveaway Created!",
            description=f"Giveaway '{self.giveaway_data['name']}' has been created!",
            color=0x00FF00
        )

        await interaction.edit_original_response(embed=success_embed)

class GiveawayBasicModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Giveaway Basic Information")
        self.view = view

        self.name = discord.ui.TextInput(
            label="Giveaway Name",
            placeholder="Enter the giveaway name",
            required=True,
            max_length=100
        )

        self.prizes = discord.ui.TextInput(
            label="Prizes",
            placeholder="What are you giving away?",
            required=True,
            max_length=500,
            style=discord.TextStyle.paragraph
        )

        self.duration = discord.ui.TextInput(
            label="Duration (hours)",
            placeholder="How long should the giveaway run?",
            required=True,
            max_length=3
        )

        self.winners = discord.ui.TextInput(
            label="Number of Winners",
            placeholder="How many winners?",
            required=True,
            max_length=2
        )

        self.add_item(self.name)
        self.add_item(self.prizes)
        self.add_item(self.duration)
        self.add_item(self.winners)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            duration_hours = int(self.duration.value)
            winners = int(self.winners.value)

            if duration_hours <= 0 or winners <= 0:
                await interaction.response.send_message("Duration and winners must be positive numbers.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("Invalid duration or winners. Please enter numbers only.", ephemeral=True)
            return

        self.view.giveaway_data.update({
            "name": self.name.value,
            "prizes": self.prizes.value,
            "duration_hours": duration_hours,
            "winners": winners,
            "host_id": interaction.user.id
        })

        await self.view.update_display(interaction)

class GiveawayRequirementsView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__(timeout=300)
        self.parent_view = parent_view

    @discord.ui.button(label="Add Required Role", style=discord.ButtonStyle.secondary)
    async def add_required_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = GiveawayRoleModal(self.parent_view, "required")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Add Extra Entry Role", style=discord.ButtonStyle.secondary)
    async def add_extra_entry_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = GiveawayExtraEntryModal(self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Add Bypass Role", style=discord.ButtonStyle.secondary)
    async def add_bypass_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = GiveawayRoleModal(self.parent_view, "bypass")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Set Level Requirement", style=discord.ButtonStyle.secondary)
    async def set_level_requirement(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = GiveawayLevelModal(self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Back to Main", style=discord.ButtonStyle.primary)
    async def back_to_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.parent_view.update_display(interaction)

class GiveawayAppearanceModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Giveaway Appearance")
        self.view = view

        self.embed_color = discord.ui.TextInput(
            label="Embed Color (hex)",
            placeholder="e.g., #FF5733 or FF5733",
            required=False,
            max_length=7
        )

        self.thumbnail_url = discord.ui.TextInput(
            label="Thumbnail URL",
            placeholder="Image URL for thumbnail",
            required=False,
            max_length=500
        )

        self.image_url = discord.ui.TextInput(
            label="Main Image URL",
            placeholder="Image URL for main image",
            required=False,
            max_length=500
        )

        self.add_item(self.embed_color)
        self.add_item(self.thumbnail_url)
        self.add_item(self.image_url)

    async def on_submit(self, interaction: discord.Interaction):
        if self.embed_color.value:
            try:
                hex_color = self.embed_color.value.lstrip('#')
                color = int(hex_color, 16)
                self.view.giveaway_data["embed_color"] = color
            except ValueError:
                await interaction.response.send_message("Invalid hex color format.", ephemeral=True)
                return

        if self.thumbnail_url.value:
            self.view.giveaway_data["thumbnail_url"] = self.thumbnail_url.value
        if self.image_url.value:
            self.view.giveaway_data["image_url"] = self.image_url.value

        await interaction.response.send_message("Appearance settings updated!", ephemeral=True)

class GiveawayRoleModal(discord.ui.Modal):
    def __init__(self, view, role_type):
        super().__init__(title=f"Add {role_type.title()} Role")
        self.view = view
        self.role_type = role_type

        self.role_input = discord.ui.TextInput(
            label="Role ID",
            placeholder="Enter the role ID",
            required=True,
            max_length=20
        )
        self.add_item(self.role_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_input.value)
            role = interaction.guild.get_role(role_id)

            if not role:
                await interaction.response.send_message("Role not found.", ephemeral=True)
                return

            key = f"{self.role_type}_roles"
            if role_id not in self.view.giveaway_data[key]:
                self.view.giveaway_data[key].append(role_id)
                await interaction.response.send_message(f"✅ Added {role.name} as a {self.role_type} role", ephemeral=True)
            else:
                await interaction.response.send_message("Role already added.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid role ID.", ephemeral=True)

class GiveawayExtraEntryModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Add Extra Entry Role")
        self.view = view

        self.role_input = discord.ui.TextInput(
            label="Role ID",
            placeholder="Enter the role ID",
            required=True,
            max_length=20
        )

        self.entries_input = discord.ui.TextInput(
            label="Number of Entries",
            placeholder="How many entries should this role get?",
            required=True,
            max_length=2
        )

        self.add_item(self.role_input)
        self.add_item(self.entries_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_input.value)
            entries = int(self.entries_input.value)

            if entries <= 0:
                await interaction.response.send_message("Entries must be positive.", ephemeral=True)
                return

            role = interaction.guild.get_role(role_id)
            if not role:
                await interaction.response.send_message("Role not found.", ephemeral=True)
                return

            # Remove existing entry for this role
            self.view.giveaway_data["extra_entry_roles"] = [
                r for r in self.view.giveaway_data["extra_entry_roles"] 
                if r["role_id"] != role_id
            ]

            self.view.giveaway_data["extra_entry_roles"].append({
                "role_id": role_id,
                "entries": entries
            })

            await interaction.response.send_message(f"✅ Added {role.name} for {entries} entries", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid role ID or entries number.", ephemeral=True)

class GiveawayLevelModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Set Level Requirement")
        self.view = view

        self.level_input = discord.ui.TextInput(
            label="Required Level",
            placeholder="Enter minimum level required",
            required=True,
            max_length=3
        )
        self.add_item(self.level_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            level = int(self.level_input.value)
            if level < 0:
                await interaction.response.send_message("Level must be 0 or higher.", ephemeral=True)
                return

            self.view.giveaway_data["required_level"] = level
            await interaction.response.send_message(f"✅ Set required level to {level}", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid level. Please enter a number.", ephemeral=True)

class GiveawayJoinView(discord.ui.View):
    def __init__(self, giveaway_id: str):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🎉 Join Giveaway", style=discord.ButtonStyle.primary)
    async def join_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = giveaways_data.get(self.giveaway_id)
        if not giveaway or giveaway["status"] != "active":
            await interaction.response.send_message("This giveaway is no longer active.", ephemeral=True)
            return

        user_id = str(interaction.user.id)

        # Check role restrictions
        if giveaway.get("required_roles"):
            user_role_ids = [role.id for role in interaction.user.roles]
            if not any(role_id in user_role_ids for role_id in giveaway["required_roles"]):
                await interaction.response.send_message("You don't have the required roles to join this giveaway.", ephemeral=True)
                return

        # Check level requirement
        if giveaway.get("required_level", 0) > 0:
            ensure_user_in_stats(user_id)
            user_level = calculate_level(member_stats.get(user_id, {}).get("xp", 0))
            if user_level < giveaway["required_level"]:
                # Check bypass roles
                if giveaway.get("bypass_roles"):
                    user_role_ids = [role.id for role in interaction.user.roles]
                    has_bypass = any(role_id in user_role_ids for role_id in giveaway["bypass_roles"])
                    if not has_bypass:
                        await interaction.response.send_message(f"You need to be Level {giveaway['required_level']} or higher to join this giveaway.", ephemeral=True)
                        return
                else:
                    await interaction.response.send_message(f"You need to be Level {giveaway['required_level']} or higher to join this giveaway.", ephemeral=True)
                    return

        # Add user to participants
        if user_id not in giveaway["participants"]:
            giveaway["participants"][user_id] = {"entries": 1}

        # Check for extra entries
        if giveaway.get("extra_entry_roles"):
            user_role_ids = [role.id for role in interaction.user.roles]
            for role_config in giveaway["extra_entry_roles"]:
                if role_config["role_id"] in user_role_ids:
                    giveaway["participants"][user_id]["entries"] = role_config["entries"]
                    break

        save_json("giveaways.json", giveaways_data)

        entries = giveaway["participants"][user_id]["entries"]
        entry_text = "entry" if entries == 1 else "entries"
        await interaction.response.send_message(f"You've joined the giveaway with {entries} {entry_text}!", ephemeral=True)

    @discord.ui.button(label="📊 View Info", style=discord.ButtonStyle.secondary)
    async def view_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = giveaways_data.get(self.giveaway_id)
        if not giveaway:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Giveaway Information",
            color=BOT_CONFIG["default_embed_color"]
        )

        embed.add_field(name="Participants", value=str(len(giveaway["participants"])), inline=True)
        total_entries = sum(data["entries"] for data in giveaway["participants"].values())
        embed.add_field(name="Total Entries", value=str(total_entries), inline=True)
        embed.add_field(name="Time Left", value=f"<t:{giveaway['end_time']}:R>", inline=True)

        if giveaway.get("required_level"):
            embed.add_field(name="Required Level", value=str(giveaway["required_level"]), inline=True)

        if giveaway.get("required_roles"):
            roles = [interaction.guild.get_role(rid).name for rid in giveaway["required_roles"] if interaction.guild.get_role(rid)]
            if roles:
                embed.add_field(name="Required Roles", value=", ".join(roles[:3]), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="giveaway", description="Create giveaways with interactive setup", guild=discord.Object(id=GUILD_ID))
@guild_only()
async def giveaway(interaction: discord.Interaction):
    if not has_staff_role(interaction):
        await interaction.response.send_message("You don't have permission to create giveaways.", ephemeral=True)
        return

    view = GiveawaySetupView()
    embed = discord.Embed(
        title="Creating Giveaway",
        description="❌ Basic Info | ⚙️ Requirements | 🎨 Appearance",
        color=BOT_CONFIG["default_embed_color"]
    )

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# --------- Additional Commands and Features -----------

# Simple user commands
@tree.command(name="balance", description="Check your currency balance", guild=discord.Object(id=GUILD_ID))
@guild_only()
async def balance(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    ensure_user_in_stats(uid)
    bal = user_balances.get(uid, 0)
    currency_symbol = get_currency_symbol()

    embed = discord.Embed(
        title=f"{interaction.user.display_name}'s Balance",
        description=f"{currency_symbol}{bal}",
        color=BOT_CONFIG["default_embed_color"]
    )
    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)

    await interaction.response.send_message(embed=embed)

@tree.command(name="level", description="Check level and XP", guild=discord.Object(id=GUILD_ID))
@guild_only()
@app_commands.describe(user="User to check (optional)")
async def level(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user
    uid = str(target_user.id)
    ensure_user_in_stats(uid)

    data = member_stats.get(uid, {})
    level = calculate_level(data.get("xp", 0))
    xp = data.get("xp", 0)

    current_level_xp = calculate_xp_for_level(level)
    next_level_xp = calculate_xp_for_level(level + 1)

    if level == 0:
        progress = xp / next_level_xp
        current_progress = xp
        needed_for_next = next_level_xp
    else:
        progress = (xp - current_level_xp) / (next_level_xp - current_level_xp)
        current_progress = xp - current_level_xp
        needed_for_next = next_level_xp - current_level_xp

    bar_length = 10
    filled_length = int(bar_length * progress)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)

    embed = discord.Embed(
        title=f"{target_user.display_name}'s Level",
        color=BOT_CONFIG["default_embed_color"]
    )
    embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)
    embed.add_field(name="Level", value=f"Level {level}", inline=True)
    embed.add_field(name="XP", value=str(xp), inline=True)
    embed.add_field(name="Progress", value=f"{bar} {current_progress}/{needed_for_next} XP", inline=False)

    await interaction.response.send_message(embed=embed)

@tree.command(name="viewslots", description="View your premium auction slots", guild=discord.Object(id=GUILD_ID))
@guild_only()
async def viewslots(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user_slots = premium_slots.get(user_id, {"total_slots": 0, "used_slots": 0})

    embed = discord.Embed(
        title=f"{interaction.user.display_name}'s Premium Slots",
        color=BOT_CONFIG["default_embed_color"]
    )
    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)

    total_slots = user_slots["total_slots"]
    used_slots = user_slots["used_slots"]
    available_slots = total_slots - used_slots

    embed.add_field(name="Total Slots", value=str(total_slots), inline=True)
    embed.add_field(name="Used Slots", value=str(used_slots), inline=True)
    embed.add_field(name="Available Slots", value=str(available_slots), inline=True)

    await interaction.response.send_message(embed=embed)

# Simple staff commands for slot management
@tree.command(name="addslots", description="Add premium auction slots to a member", guild=discord.Object(id=GUILD_ID))
@guild_only()
@app_commands.describe(member="Member to add slots to", amount="Number of slots to add")
async def addslots(interaction:discord.Interaction, member: discord.Member, amount: int):
    if not has_staff_role(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("Amount must be positive.", ephemeral=True)
        return

    user_id = str(member.id)
    if user_id not in premium_slots:
        premium_slots[user_id] = {"total_slots": 0, "used_slots": 0, "manual_slots": 0}

    premium_slots[user_id]["manual_slots"] = premium_slots[user_id].get("manual_slots", 0) + amount
    premium_slots[user_id]["total_slots"] += amount
    save_json("premium_slots.json", premium_slots)

    await interaction.response.send_message(f"✅ Added {amount} premium auction slots to {member.mention}. They now have {premium_slots[user_id]['total_slots']} total slots.")

# Background tasks and event handlers
@tasks.loop(hours=24)
async def reset_daily():
    for uid in member_stats:
        member_stats[uid]["daily_messages"] = 0
    save_json("member_stats.json", member_stats)

@tasks.loop(minutes=1)
async def check_giveaways():
    current_time = int(time.time())

    for giveaway_id, giveaway in list(giveaways_data.items()):
        if giveaway["status"] == "active" and current_time >= giveaway["end_time"]:
            guild = bot.get_guild(GUILD_ID)
            if guild:
                await end_giveaway(giveaway_id, guild)

async def end_giveaway(giveaway_id: str, guild: discord.Guild):
    giveaway = giveaways_data.get(giveaway_id)
    if not giveaway or giveaway["status"] != "active":
        return

    # Mark as ended immediately to prevent duplicate endings
    giveaway["status"] = "ended"
    save_json("giveaways.json", giveaways_data)

    channel = guild.get_channel(giveaway["channel_id"])
    if not channel:
        return

    # Handle no participants
    if not giveaway["participants"]:
        embed = discord.Embed(
            title="🎉 Giveaway Ended",
            description=f"**{giveaway['name']}**\n\nNo participants joined this giveaway!",
            color=0xFF0000
        )
        await channel.send(embed=embed)
        return

    # Select winners
    weighted_participants = []
    for user_id, data in giveaway["participants"].items():
        weighted_participants.extend([user_id] * data["entries"])

    winner_count = min(giveaway["winners"], len(giveaway["participants"]))
    winners = random.sample(weighted_participants, winner_count)

    # Remove duplicates
    unique_winners = []
    seen = set()
    for winner in winners:
        if winner not in seen:
            unique_winners.append(winner)
            seen.add(winner)

    giveaway["winners_list"] = unique_winners

    # Create winner announcement
    host = guild.get_member(giveaway["host_id"])
    embed = discord.Embed(
        title="🎉 Giveaway Ended!",
        description=f"**{giveaway['name']}**\n\n**Prizes:** {giveaway['prizes']}",
        color=0x00FF00
    )

    winner_mentions = [f"<@{winner_id}>" for winner_id in unique_winners]
    embed.add_field(name="Winners", value="\n".join(winner_mentions), inline=False)

    if host:
        embed.add_field(name="Host", value=host.mention, inline=True)

    winner_pings = " ".join(winner_mentions)
    if host:
        winner_pings += f" {host.mention}"

    await channel.send(content=winner_pings, embed=embed)
    save_json("giveaways.json", giveaways_data)

@tasks.loop(hours=6)
async def automated_backup():
    """Create automated backups every 6 hours"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"backups/backup_{timestamp}"
        os.makedirs(backup_dir, exist_ok=True)

        data_files = [
            "bot_config.json", "tierlist.json", "member_stats.json", "shops.json", 
            "balances.json", "inventories.json", "reaction_roles.json", 
            "sticky_messages.json", "server_settings.json", "verification.json", 
            "auctions.json", "user_profiles.json", "giveaways.json", 
            "premium_slots.json", "logging_settings.json", "member_warnings.json", 
            "autoresponders.json", "profile_presets.json"
        ]

        for file in data_files:
            if os.path.exists(file):
                shutil.copy2(file, backup_dir)

        logger.info(f"Backup created: {backup_dir}")
    except Exception as e:
        logger.error(f"Backup failed: {e}")

@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None or message.guild.id != GUILD_ID:
        return

    # Track member stats
    uid = str(message.author.id)
    ensure_user_in_stats(uid)

    # Check for level up
    old_level = calculate_level(member_stats[uid].get("xp", 0))

    member_stats[uid]["daily_messages"] += 1
    member_stats[uid]["weekly_messages"] += 1
    member_stats[uid]["monthly_messages"] += 1
    member_stats[uid]["all_time_messages"] += 1
    member_stats[uid]["xp"] += 5

    new_level = calculate_level(member_stats[uid]["xp"])

    # Send level up notification
    if new_level > old_level and BOT_CONFIG.get("levelup_channel_id"):
        levelup_channel = bot.get_channel(BOT_CONFIG["levelup_channel_id"])
        if levelup_channel:
            await levelup_channel.send(f"🎉 {message.author.mention} leveled up to Level {new_level}!")

    save_all()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Bot started successfully as {bot.user}")

    try:
        await tree.sync(guild=discord.Object(id=GUILD_ID))
        logger.info("Command tree synced successfully")
    except Exception as e:
        logger.error(f"Failed to sync command tree: {e}")

    reset_daily.start()
    check_giveaways.start()
    automated_backup.start()

bot.run(TOKEN)
