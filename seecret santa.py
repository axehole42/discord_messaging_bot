import os
import csv
import asyncio
import discord
from dotenv import load_dotenv

# =========================
# CONFIG
# =========================

load_dotenv()
TOKEN = os.getenv("SECRET_KEY")

SLEEP_SECONDS = 1.2     # Delay between DMs (safe)
DRY_RUN = False         # True = no DMs sent, just prints
GUILD_ID = 1412819198702387343  # paste your server ID here


MESSAGE_TEMPLATE = """🎁 Secret Santa 🎁

❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️

Hey **{username}**!

The Guild Christmas event is near! 🎄🎄🎄

You are the Secret Santa for:
🎅❄️🎄 **{target}** 🎅❄️🎄

Make sure to wrap the item using gift wrap, which is sold by any general goods vendor.
You can also use festive paper from Winter's Veil!

There are no restrictions on what you can give, but please keep it appropriate and within budget (if you are poor like me).
You CANNOT wrap certain items, such as stackable items (e.g., potions, food, or Ice Cold Milk).

**The event is planned for the 21st of December at 21:30 CET (3:30 PM EST/NYC).**

Location Coordinates: Alterac Mountains, Chillwind Point 80.00 / 52.5
(Across the Warrior Quest Place)

Do not send your gift before then — everyone will trade each other their gifts at the same time!

If you won’t be able to attend, please inform Jumpscare as soon as possible.

Enjoy the Christmas spirit! ☃️🧣

Much love,
Jumpscare

-------------------------------------------------
**CAUTION!!!!!**
*This is an automated message, please do not reply to this DM.*
**If you have any questions, please contact Jumpscare personally.**
***Should you not be able to attend, please inform Jumpscare as soon as possible.***
"""

# =========================
# PATHS
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "secret_santa_test.csv")
LOG_PATH = os.path.join(BASE_DIR, "dm_log.txt")

# =========================
# DISCORD SETUP
# =========================

intents = discord.Intents.default()
intents.members = True  # REQUIRED for member lookup

client = discord.Client(intents=intents)

# =========================
# HELPERS
# =========================

def norm(s: str | None) -> str | None:
    """Normalize strings for matching."""
    if not s:
        return None
    return s.strip().lower().lstrip("@")

def chunk_message(text: str, limit: int = 1900) -> list[str]:
    """Split long messages into Discord-safe chunks (<= 2000)."""
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks

def build_member_lookup(guild: discord.Guild) -> dict[str, discord.Member]:
    """
    Build lookup from multiple member identifiers:
    - username (m.name)
    - global display name (m.global_name)
    - display name (m.display_name)
    - nickname (m.nick)
    """
    lookup: dict[str, discord.Member] = {}

    for m in guild.members:
        candidates = [
            m.name,
            getattr(m, "global_name", None),
            m.display_name,
            m.nick,
        ]
        for c in candidates:
            key = norm(c)
            if key:
                lookup[key] = m

    return lookup

async def send_dm(member: discord.Member, target: str) -> tuple[bool, str]:
    try:
        if DRY_RUN:
            return True, f"DRY_RUN would DM {member.display_name} -> {target}"

        full_text = MESSAGE_TEMPLATE.format(
            username=member.display_name,
            target=target
        )

        # Send in chunks if too long
        for part in chunk_message(full_text):
            await member.send(part)
            await asyncio.sleep(0.6)

        return True, f"Sent to {member.display_name} ({member.id})"

    except discord.Forbidden:
        return False, f"DM blocked for {member.display_name} ({member.id})"
    except discord.NotFound:
        return False, f"User not found ({member.display_name}, id={member.id})"
    except Exception as e:
        return False, f"Error for {member.display_name} ({member.id}): {type(e).__name__}: {e}"

# =========================
# MAIN BOT LOGIC
# =========================

@client.event
async def on_ready():
    print(f"Logged in as {client.user} (id={client.user.id})")

    if not client.guilds:
        print("ERROR: Bot is not in any server.")
        await client.close()
        return

    guild = client.get_guild(GUILD_ID)
    if guild is None:
        print(f"ERROR: Bot is not in your server (GUILD_ID={GUILD_ID}).")
        print("Bot is currently in:", [(g.name, g.id) for g in client.guilds])
        await client.close()
        return
    print(f"Using guild: {guild.name}")

    # IMPORTANT: ensure full member list is available
    print("Fetching members from Discord...")
    member_lookup = {}

    def add_key(key, member):
        if key:
            member_lookup[key.strip().lower().lstrip("@")] = member

    count = 0
    async for m in guild.fetch_members(limit=None):
        count += 1
        add_key(m.name, m)
        add_key(getattr(m, "global_name", None), m)
        add_key(m.display_name, m)
        add_key(m.nick, m)

    print(f"Fetched {count} members. Indexed {len(member_lookup)} name keys.")

    # Read CSV
    rows: list[tuple[discord.Member, str]] = []

    if not os.path.exists(CSV_PATH):
        print(f"ERROR: CSV not found at {CSV_PATH}")
        await client.close()
        return

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = [h.strip().lower() for h in (reader.fieldnames or [])]
        print("Detected headers:", headers)

        if not {"username", "target"}.issubset(headers):
            print("ERROR: CSV must have headers: username,target")
            await client.close()
            return

        for r in reader:
            raw_user = r.get("username", "")
            raw_target = r.get("target", "")

            u = norm(raw_user)
            t = (raw_target or "").strip()

            if not u or not t:
                continue

            member = member_lookup.get(u)
            if not member:
                print(f"User not found in server: {u}")
                continue

            rows.append((member, t))

    print(f"Loaded {len(rows)} rows from CSV")
    print("Starting DMs...")

    success = 0
    fail = 0
    log_lines: list[str] = []

    for member, target in rows:
        ok, msg = await send_dm(member, target)
        print(msg)
        log_lines.append(msg)

        if ok:
            success += 1
        else:
            fail += 1

        await asyncio.sleep(SLEEP_SECONDS)

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    print(f"Done. Success={success}, Fail={fail}. Log saved to dm_log.txt")
    await client.close()

# =========================
# RUN
# =========================

client.run(TOKEN)
