
from fastapi import APIRouter
from ..models.schemas import UserProfile
from ..core.database import MongoDB, in_memory_users

router = APIRouter()

@router.post("/users/register")
def register_user(profile: UserProfile):
    """Creates or updates a user profile."""
    if MongoDB.users_col is not None:
        MongoDB.users_col.update_one(
            {"user_id": profile.user_id},
            {"$set": profile.dict()},
            upsert=True,
        )
    else:
        in_memory_users[profile.user_id] = profile.dict()
    return {"message": f"User {profile.user_id} registered successfully."}
