import asyncio
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, GetFullChatRequest
from telethon.errors import InviteHashExpiredError, InviteHashInvalidError, ChannelPrivateError, UsernameNotOccupiedError, UserBannedInChannelError, ChatAdminRequiredError
from telethon.tl.types import ChannelParticipantCreator
import config

client = TelegramClient('session_name', config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

async def join_group(invite_link):
    try:
        if not client.is_connected():
            await client.connect()
        if 'joinchat' in invite_link or '+' in invite_link:
            # Private group
            hash_part = invite_link.split('/')[-1].lstrip('+')
            await client(ImportChatInviteRequest(hash_part))
            return True, None
        else:
            # Public group/channel
            username = invite_link.split('/')[-1]
            await client(JoinChannelRequest(username))
            return True, None
    except InviteHashExpiredError:
        print("Private invite expired")
        return False, "private_expired"
    except InviteHashInvalidError:
        print("Private invite invalid")
        return False, "private_invalid"
    except ChannelPrivateError:
        print("Channel is private")
        return False, "public_private"
    except UsernameNotOccupiedError:
        print("Username not found")
        return False, "invalid_username"
    except (UserBannedInChannelError, ChatAdminRequiredError):
        print("Cannot join due to restrictions")
        return False, "not_joinable"
    except Exception as e:
        print(f"Unexpected error joining: {e}")
        return False, "join_error"

async def get_creation_year(chat_id):
    try:
        if not client.is_connected():
            await client.connect()
        # Always use full channel/chat request for accurate creation date
        try:
            if chat_id < 0:  # Group
                full_chat = await client(GetFullChatRequest(chat_id))
                if hasattr(full_chat, 'chats') and full_chat.chats:
                    creation_date = full_chat.chats[0].date
                    year = creation_date.year
                    print(f"Debug: Full chat creation date: {creation_date}, Year: {year}")
                    return year
            else:  # Channel
                chat = await client.get_entity(chat_id)
                full_channel = await client(GetFullChannelRequest(chat))
                if hasattr(full_channel, 'chats') and full_channel.chats:
                    creation_date = full_channel.chats[0].date
                    year = creation_date.year
                    print(f"Debug: Full channel creation date: {creation_date}, Year: {year}")
                    return year
        except Exception as e2:
            print(f"Error getting full chat/channel info: {e2}")
            return None
    except Exception as e:
        print(f"Error getting creation year: {e}")
        return None
async def check_ownership(chat_id, username=config.OWNER_USERNAME):
    try:
        if not client.is_connected():
            await client.connect()
        chat = await client.get_entity(chat_id)
        print(f"Debug: Checking ownership for chat {chat_id}, username {username}")
        # First, check if the bot is the creator (ownership transferred)
        participants = await client.get_participants(chat_id, limit=100)
        print(f"Debug: Found {len(participants)} participants")
        for p in participants:
            print(f"Debug: Participant {p.username}, role {type(p.participant)}")
            if p.username == username and isinstance(p.participant, ChannelParticipantCreator):
                print(f"Debug: Ownership confirmed for {username}")
                return True
        print(f"Debug: Ownership not found for {username}")
        return False
    except Exception as e:
        print(f"Error checking ownership: {e}")
        return False

async def leave_group(chat_id):
    try:
        if not client.is_connected():
            await client.connect()
        await client.delete_dialog(chat_id)
    except Exception as e:
        print(f"Error leaving group: {e}")

# Note: User needs to run this once to create session
async def main():
    await client.start(phone=config.PHONE)
    print("Telethon client started. Session saved.")

if __name__ == '__main__':
    asyncio.run(main())
