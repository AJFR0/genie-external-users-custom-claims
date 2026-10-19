from fastapi import APIRouter


def build_admin_router(settings, services, templates):
    return APIRouter(prefix="/admin")
