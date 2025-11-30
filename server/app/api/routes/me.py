from fastapi import APIRouter, Depends

from server.app.core.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api")


@router.get("/me")
def get_me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return current_user
