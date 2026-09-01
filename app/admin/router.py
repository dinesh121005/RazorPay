"""
Admin REST router for customer mandate lifecycle management and credential provisioning.

IMPORTANT SAFEGUARD:
These endpoints are strictly for human administrator and operations tooling.
They must NEVER be exposed as MCP tools or reachable by AI shopping agents.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from app.admin.models import CreateCustomerRequest, UpdateMandateLimitRequest
from app.auth import verify_admin_key
from app.oauth.store import customer_auth_store
from app.policy.mandate import Mandate
from app.policy.store import mandate_store

router = APIRouter(
    prefix="/admin/customers",
    tags=["admin"],
    dependencies=[Depends(verify_admin_key)]
)


@router.post(
    "",
    response_model=Mandate,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a new customer mandate and OAuth credentials",
    description="Creates a new customer spending mandate and registers OAuth login credentials in the persisted store. Admin-only."
)
def create_customer_mandate(payload: CreateCustomerRequest) -> Mandate:
    """
    Admin endpoint to provision a new customer spending mandate and OAuth credentials.
    Enforces customer_id and username uniqueness across both stores with atomic rollback.
    """
    clean_cust_id = payload.customer_id.strip()
    username = (payload.username or clean_cust_id).strip().lower()
    password = payload.password or "password123"
    email = payload.email or f"{username}@example.com"

    # 1. Uniqueness check across Mandate store
    if mandate_store.get_mandate(clean_cust_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Mandate for customer '{clean_cust_id}' already exists."
        )

    # 2. Uniqueness check across OAuth credentials store
    if customer_auth_store.get_user_by_username(username) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{username}' is already registered."
        )

    # 3. Provision OAuth credentials in persisted SQLite table
    try:
        customer_auth_store.register_user(
            customer_id=clean_cust_id,
            username=username,
            email=email,
            password=password,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    # 4. Create Mandate in MandateStore (with rollback on error)
    try:
        mandate = mandate_store.create_mandate(
            customer_id=clean_cust_id,
            display_name=payload.display_name,
            mandate_limit=payload.mandate_limit,
            allowed_categories=payload.allowed_categories,
            allowed_merchants=payload.allowed_merchants,
            email=email,
            expires_at=payload.expires_at,
        )
        return mandate
    except Exception as e:
        # Atomic rollback: remove newly registered OAuth credentials if mandate creation fails
        customer_auth_store.delete_user(clean_cust_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT if isinstance(e, ValueError) else status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "",
    response_model=List[Mandate],
    status_code=status.HTTP_200_OK,
    summary="List all customer mandates",
    description="Lists all customer mandates currently active in the policy store. Admin-only."
)
def list_customer_mandates() -> List[Mandate]:
    """
    Admin endpoint listing all customer mandates.
    """
    return list(mandate_store.list_mandates().values())


@router.get(
    "/{customer_id}",
    response_model=Mandate,
    status_code=status.HTTP_200_OK,
    summary="Get customer mandate by ID",
    description="Retrieves the current spending mandate for a specific customer ID. Admin-only."
)
def get_customer_mandate(customer_id: str) -> Mandate:
    """
    Admin endpoint fetching a single customer mandate by customer_id.
    """
    mandate = mandate_store.get_mandate(customer_id)
    if mandate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer mandate for '{customer_id}' not found"
        )
    return mandate


@router.patch(
    "/{customer_id}/mandate",
    response_model=Mandate,
    status_code=status.HTTP_200_OK,
    summary="Update customer mandate spending limit",
    description="Updates the maximum transaction amount limit for an existing customer mandate. Admin-only."
)
def update_customer_mandate_limit(
    customer_id: str,
    payload: UpdateMandateLimitRequest
) -> Mandate:
    """
    Admin endpoint updating a customer's spending limit.
    """
    try:
        return mandate_store.update_mandate_limit(
            customer_id=customer_id,
            new_limit=payload.mandate_limit
        )
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
