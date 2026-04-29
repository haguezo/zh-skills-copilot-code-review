"""
Announcements endpoints for the High School Management System API
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional, List
from datetime import datetime
from bson.objectid import ObjectId

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def _is_announcement_active(announcement: Dict[str, Any]) -> bool:
    """Check if an announcement is currently active based on start and expiration dates"""
    now = datetime.now().isoformat()
    
    # Check if announcement has started
    if "start_date" in announcement and announcement["start_date"]:
        if announcement["start_date"] > now:
            return False
    
    # Check if announcement has expired
    if "expiration_date" in announcement:
        if announcement["expiration_date"] <= now:
            return False
    
    return True


def _verify_admin_access(username: Optional[str]) -> bool:
    """Verify that a user has admin access to manage announcements"""
    if not username:
        return False
    
    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        return False
    
    return teacher.get("role") in ["admin", "teacher"]


def _format_announcement(announcement: Dict[str, Any]) -> Dict[str, Any]:
    """Format announcement for API response"""
    formatted = {
        "id": str(announcement["_id"]),
        "message": announcement.get("message", ""),
        "start_date": announcement.get("start_date"),
        "expiration_date": announcement.get("expiration_date"),
        "created_at": announcement.get("created_at"),
        "created_by": announcement.get("created_by")
    }
    return formatted


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """
    Get all currently active announcements
    
    Returns announcements that:
    - Have passed their start_date (if set)
    - Have not yet reached their expiration_date
    """
    announcements = []
    for announcement in announcements_collection.find():
        if _is_announcement_active(announcement):
            announcements.append(_format_announcement(announcement))
    
    return announcements


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """
    Get all announcements (admin only)
    
    Requires teacher/admin authentication via username query parameter
    """
    if not _verify_admin_access(username):
        raise HTTPException(
            status_code=403, 
            detail="Only authenticated teachers can manage announcements"
        )
    
    announcements = []
    for announcement in announcements_collection.find().sort("created_at", -1):
        announcements.append(_format_announcement(announcement))
    
    return announcements


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    message: str,
    expiration_date: str,
    start_date: Optional[str] = None,
    username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Create a new announcement (admin only)
    
    Required fields:
    - message: The announcement text
    - expiration_date: ISO format datetime string (e.g., "2024-05-15T23:59:59")
    
    Optional fields:
    - start_date: ISO format datetime string when announcement becomes active
    - username: Required for authentication
    """
    if not _verify_admin_access(username):
        raise HTTPException(
            status_code=403, 
            detail="Only authenticated teachers can create announcements"
        )
    
    # Validate expiration_date format
    try:
        datetime.fromisoformat(expiration_date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="expiration_date must be in ISO format (e.g., 2024-05-15T23:59:59)"
        )
    
    # Validate start_date format if provided
    if start_date:
        try:
            datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="start_date must be in ISO format (e.g., 2024-05-15T23:59:59)"
            )
    
    announcement = {
        "message": message,
        "start_date": start_date,
        "expiration_date": expiration_date,
        "created_at": datetime.now().isoformat(),
        "created_by": username
    }
    
    result = announcements_collection.insert_one(announcement)
    announcement["_id"] = result.inserted_id
    
    return _format_announcement(announcement)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    message: Optional[str] = None,
    expiration_date: Optional[str] = None,
    start_date: Optional[str] = None,
    username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Update an announcement (admin only)
    
    At least one field must be provided to update
    """
    if not _verify_admin_access(username):
        raise HTTPException(
            status_code=403,
            detail="Only authenticated teachers can update announcements"
        )
    
    # Validate announcement exists
    try:
        announcement = announcements_collection.find_one({"_id": ObjectId(announcement_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid announcement ID")
    
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    # Validate date formats if provided
    if expiration_date:
        try:
            datetime.fromisoformat(expiration_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="expiration_date must be in ISO format"
            )
    
    if start_date is not None:  # Allow empty string to clear start_date
        if start_date:  # Only validate if non-empty
            try:
                datetime.fromisoformat(start_date)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="start_date must be in ISO format"
                )
    
    # Build update dict
    update_data = {}
    if message is not None:
        update_data["message"] = message
    if expiration_date is not None:
        update_data["expiration_date"] = expiration_date
    if start_date is not None:
        update_data["start_date"] = start_date if start_date else None
    
    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="At least one field must be provided to update"
        )
    
    result = announcements_collection.update_one(
        {"_id": ObjectId(announcement_id)},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update announcement")
    
    # Fetch updated announcement
    updated = announcements_collection.find_one({"_id": ObjectId(announcement_id)})
    return _format_announcement(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """
    Delete an announcement (admin only)
    """
    if not _verify_admin_access(username):
        raise HTTPException(
            status_code=403,
            detail="Only authenticated teachers can delete announcements"
        )
    
    # Validate announcement exists
    try:
        announcement = announcements_collection.find_one({"_id": ObjectId(announcement_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid announcement ID")
    
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    result = announcements_collection.delete_one({"_id": ObjectId(announcement_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=500, detail="Failed to delete announcement")
    
    return {"message": "Announcement deleted successfully"}
