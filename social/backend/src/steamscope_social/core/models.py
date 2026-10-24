"""Register only tables implemented by the current phase for Alembic metadata."""

from steamscope_social.modules.administration.models import AuditLog
from steamscope_social.modules.auth.models import LoginAttempt, SteamAccount, UserSession
from steamscope_social.modules.chat.models import (
    Conversation,
    ConversationMember,
    Message,
    MessageReport,
)
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.social.models import (
    Connection,
    ConnectionRequest,
    SocialNotification,
    UserBlock,
    UserReport,
)
from steamscope_social.modules.steam.models import (
    AchievementDefinition,
    AchievementSchema,
    AchievementState,
    Game,
    RecentGame,
    RequestBudget,
    SteamFriend,
    SyncJob,
    SyncRun,
    SyncState,
    UserAchievement,
    UserGame,
)
from steamscope_social.modules.users.models import User

__all__ = [
    "Conversation",
    "ConversationMember",
    "Message",
    "MessageReport",
    "Connection",
    "ConnectionRequest",
    "SocialNotification",
    "UserBlock",
    "UserReport",
    "AchievementDefinition",
    "AchievementSchema",
    "AchievementState",
    "UserAchievement",
    "SteamFriend",
    "AuditLog",
    "LoginAttempt",
    "PrivacySettings",
    "SteamAccount",
    "User",
    "UserSession",
    "Game",
    "UserGame",
    "RecentGame",
    "SyncState",
    "SyncJob",
    "SyncRun",
    "RequestBudget",
]
