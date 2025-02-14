import os
import uuid
import discord
from discord.ext import commands, tasks
import aiohttp
import json
from dotenv import load_dotenv
import datetime
import pytz
import threading
from better_profanity import profanity

# -----------------------------
#         Load .env
# -----------------------------
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

# -----------------------------
#        Create the Bot
# -----------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

# -----------------------------
#        User Stats Setup
# -----------------------------
USER_STATS_FILE = "user_stats.json"
user_stats = {}

def load_user_stats():
    """Load the user_stats from a JSON file if it exists."""
    global user_stats
    try:
        with open(USER_STATS_FILE, "r") as f:
            user_stats = json.load(f)
        print("✅ Loaded user statistics from user_stats.json")
    except FileNotFoundError:
        user_stats = {}
        print("ℹ️ No existing user_stats.json found. Starting fresh.")

def save_user_stats():
    """Save the current user_stats dictionary to a JSON file."""
    with open(USER_STATS_FILE, "w") as f:
        json.dump(user_stats, f, indent=4)
    new_timezone = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now().astimezone(new_timezone)
    today = now.strftime("%d-%m-%Y %H:%M:%S")
    print(f"💾 Saved user statistics at {today}")

def initialize_user(user_id, user_name, role):
    """Ensure that the user record exists in user_stats."""
    user_id_str = str(user_id)
    if user_id_str not in user_stats:
        user_stats[user_id_str] = {
            "id": user_id_str,
            "name": user_name,
            "role": role,
            "daily_stats": {}
        }

@bot.event
async def on_message(message: discord.Message):
    """Track messages and (optionally) vulgar language usage."""
    if message.author == bot.user:
        return

    user_id = message.author.id
    user_role = message.author.top_role.name if message.author.roles else "None"

    new_timezone = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now().astimezone(new_timezone)
    today = now.strftime("%d-%m-%Y")

    user_name = message.author.name
    initialize_user(user_id, user_name, user_role)
    user_id_str = str(user_id)

    # Update the user's role
    user_stats[user_id_str]["role"] = user_role

    # Ensure today's stats exist
    if today not in user_stats[user_id_str]["daily_stats"]:
        user_stats[user_id_str]["daily_stats"][today] = {
            "messages_sent": 0,
            "replied": 0,
            "vulgar_sent": 0
        }

    # Check if reply
    is_reply = message.reference is not None

    # Check vulgar language
    is_vulgar = profanity.contains_profanity(message.content)

    # Increment counters
    if is_reply:
        user_stats[user_id_str]["daily_stats"][today]["replied"] += 1
    else:
        user_stats[user_id_str]["daily_stats"][today]["messages_sent"] += 1

    if is_vulgar:
        user_stats[user_id_str]["daily_stats"][today]["vulgar_sent"] += 1

    print(f"Updated stats for user {user_id_str} on {today}: "
          f"{user_stats[user_id_str]['daily_stats'][today]}")

    await bot.process_commands(message)


# -----------------------------
# Criteria Manager
# -----------------------------
CRITERIA_FILE = "criteria.json"

def load_criteria():
    """Load the criteria list from the JSON file if it exists."""
    try:
        with open(CRITERIA_FILE, "r") as f:
            criteria_list = json.load(f)
    except FileNotFoundError:
        criteria_list = []
    return criteria_list

def save_criteria(criteria_list):
    """Save the criteria list to the JSON file."""
    with open(CRITERIA_FILE, "w") as f:
        json.dump(criteria_list, f, indent=4)
    print(f"💾 Saved criteria at {datetime.datetime.utcnow().isoformat()}")

@bot.command(name="addcriteria")
async def add_criteria(ctx, *, criteria_text: str):
    """Command for moderators to add criteria text to criteria.json."""
    criteria_list = load_criteria()
    new_entry = {
        "id": f"criteria_{int(datetime.datetime.utcnow().timestamp())}",
        "original_message": criteria_text,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "enabled": True
    }
    criteria_list.append(new_entry)
    save_criteria(criteria_list)
    await ctx.send("✅ Criteria added successfully.")


@bot.command(name="rolehierarchy")
async def role_hierarchy(ctx):
    """Display the role hierarchy of the current guild."""
    roles = ctx.guild.roles
    sorted_roles = sorted(roles, key=lambda role: role.position, reverse=True)
    roles_info = "\n".join([f"**{role.position}**: {role.name}" for role in sorted_roles])
    await ctx.send(f"**Role Hierarchy for {ctx.guild.name}:**\n{roles_info}")

@bot.command(name="saverolehierarchy")
async def save_role_hierarchy(ctx):
    """Save the current guild's role hierarchy into a JSON file."""
    roles = ctx.guild.roles
    sorted_roles = sorted(roles, key=lambda role: role.position, reverse=True)
    role_list = [role.name for role in sorted_roles]

    filename = f"role_hierarchy.json"
    try:
        with open(filename, "w") as f:
            json.dump(role_list, f, indent=4)
        await ctx.send(f"✅ Role hierarchy saved to `{filename}`")
        print(f"💾 Role hierarchy for guild {ctx.guild.id} saved to {filename}")
    except Exception as e:
        await ctx.send(f"⚠️ Error saving role hierarchy: {e}")
        print(f"Error saving role hierarchy: {e}")


# -----------------------------
# Periodic Saving of Stats
# -----------------------------
@tasks.loop(seconds=60)
async def save_stats_loop():
    """Background task that saves the user_stats to a JSON file every 60 seconds."""
    save_user_stats()


# ----------------------------------------------------
#   PART 2: Automatic Role Changes with JSON
# ----------------------------------------------------
ROLE_REQUESTS_FILE = "role_requests.json"
ROLE_HISTORY_FILE = "role_change_history.json"
requests_lock = threading.Lock()
history_lock = threading.Lock()

# Replace with your real guild ID
GUILD_ID = 1337419131858845794  # Make sure the bot is in this server

@tasks.loop(seconds=30)
async def process_role_requests():
    """
    Background task to read role_requests.json, apply changes, and log them
    in role_change_history.json.
    """
    with requests_lock:
        # Load queued requests
        try:
            with open(ROLE_REQUESTS_FILE, "r") as f:
                requests_data = json.load(f)
        except FileNotFoundError:
            requests_data = []

        if not requests_data:
            return  # No pending requests

        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print(f"⚠️ Could not find guild with ID {GUILD_ID}. Check your settings.")
            return

        remaining_requests = []  # requests we'll keep if unprocessed

        for req in requests_data:
            user_id_str = req.get("user_id")
            action = req.get("action")
            role_name = req.get("role")
            reason = req.get("reason", "No reason")
            human_intervention = req.get("human_intervention", False)

            if not user_id_str or not action:
                print(f"Skipping invalid request: {req}")
                continue

            # Convert user_id
            try:
                user_id = int(user_id_str)
            except ValueError:
                print(f"Invalid user ID: {user_id_str}")
                continue

            member = guild.get_member(user_id)
            if not member:
                print(f"User {user_id} not found in guild {guild.id}.")
                continue

            if human_intervention:
                print(f"Request requires human intervention: {req}")
                remaining_requests.append(req)
                continue

            # Gather old roles for history
            old_roles = [r.name for r in member.roles if r.name != "@everyone"]

            # Perform the action
            if action == "kick":
                success = await handle_kick(member, reason)
                if success:
                    log_role_history(user_id, member.name, old_roles, None, action, reason)
            elif action in ["assign_role", "upgrade_role", "degrade_role"]:
                if role_name:
                    role_obj = discord.utils.get(guild.roles, name=role_name)
                    if not role_obj:
                        print(f"❌ Role '{role_name}' not found in guild {guild.id}.")
                        continue

                    success = await handle_add_role(member, role_obj, reason, action)
                    if success:
                        log_role_history(user_id, member.name, old_roles, role_obj.name, action, reason)
                else:
                    print(f"No role specified for action '{action}', skipping.")
            elif action == "no_change":
                print(f"No change for user {user_id}, skipping.")
            else:
                print(f"Unrecognized action '{action}' for user {user_id}, skipping.")

        # Rewrite only the unprocessed or intervention-needed requests
        with open(ROLE_REQUESTS_FILE, "w") as f:
            json.dump(remaining_requests, f, indent=2)

async def handle_kick(member: discord.Member, reason: str) -> bool:
    """Try to kick the user."""
    try:
        await member.kick(reason=reason)
        print(f"✅ Kicked user {member.id}. Reason: {reason}")
        return True
    except discord.Forbidden:
        print(f"❌ Missing permissions to kick {member.id}")
    except discord.HTTPException as e:
        print(f"❌ HTTP error kicking {member.id}: {e}")
    return False

async def handle_add_role(member: discord.Member, role: discord.Role, reason: str, action: str) -> bool:
    """Add a role to the member, return True if success."""
    try:
        await member.add_roles(role, reason=reason)
        print(f"✅ {action}: Added role '{role.name}' to {member.id}. Reason: {reason}")
        return True
    except discord.Forbidden:
        print(f"❌ Missing permissions to assign role '{role.name}' to {member.id}")
    except discord.HTTPException as e:
        print(f"❌ HTTP error while adding role '{role.name}' to {member.id}: {e}")
    return False

def log_role_history(user_id: int, user_name: str, old_roles: list, new_role: str, action: str, reason: str):
    """
    Log a completed role action to role_change_history.json, capturing old/new roles.
    """
    new_timezone = pytz.timezone("Asia/Kolkata")
    now = datetime.datetime.now().astimezone(new_timezone)
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

    entry = {
        "timestamp": timestamp_str,
        "user_id": str(user_id),
        "user_name": user_name,
        "old_roles": old_roles,
        "new_role": new_role,
        "action": action,
        "reason": reason
    }

    with history_lock:
        try:
            with open(ROLE_HISTORY_FILE, "r") as f:
                history_data = json.load(f)
        except FileNotFoundError:
            history_data = []

        history_data.append(entry)

        with open(ROLE_HISTORY_FILE, "w") as f:
            json.dump(history_data, f, indent=2)

    print(f"📝 Logged role change: {entry}")


# -----------------------------
#   BOT EVENTS
# -----------------------------
@bot.event
async def on_ready():
    print(f"✅ Bot is online and logged in as {bot.user}")
    load_user_stats()
    save_stats_loop.start()       # Start the periodic user_stats saving
    process_role_requests.start() # Start the periodic role request processing


# -----------------------------
#   RUN THE BOT
# -----------------------------
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ No BOT_TOKEN found. Set DISCORD_TOKEN in your .env file.")
    else:
        bot.run(BOT_TOKEN)
