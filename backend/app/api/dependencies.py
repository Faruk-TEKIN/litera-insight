from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from database.models.User import User


def get_current_user(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> User:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-Id header")
    try:
        user_id = int(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid X-User-Id header") from exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user
