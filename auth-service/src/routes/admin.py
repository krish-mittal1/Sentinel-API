import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..dependencies import require_role
from ..schemas import (
    StartupOverviewResponse,
    TeamMemberCreateRequest,
    TeamMemberCreateResponse,
    TenantCreateRequest,
    TenantResponse,
    UserResponse,
)
from ..services.auth_service import create_team_member, create_tenant, dashboard_snapshot, list_tenants, startup_overview
from ..utils.email import send_email

router = APIRouter(prefix="/admin", tags=["Admin"])

def _dashboard_html(snapshot: dict) -> str:
    metrics = snapshot["metrics"]
    cards = "".join(
        f'<div class="card"><span>{label}</span><strong>{value}</strong></div>'
        for label, value in [
            ("Total Users", metrics["total_users"]),
            ("Verified Users", metrics["verified_users"]),
            ("Admin Users", metrics["admin_users"]),
            ("Active Sessions", metrics["active_sessions"]),
            ("Pending Verifications", metrics["pending_verifications"]),
            ("Pending Resets", metrics["pending_password_resets"]),
        ]
    )
    rows = "".join(
        f"""
        <tr>
          <td>{user.get('tenant_id', '-')}</td>
          <td>{user['name']}</td>
          <td>{user['email']}</td>
          <td>{user['role']}</td>
          <td>{'Yes' if user['email_verified'] else 'No'}</td>
          <td>{user['created_at']}</td>
          <td>{user['last_login_at'] or '-'}</td>
        </tr>
        """
        for user in snapshot["recent_users"]
    )
    audit_rows = "".join(
        f"""
        <tr>
          <td>{event.get('tenant_id', '-')}</td>
          <td>{event['event_type']}</td>
          <td>{event['email'] or '-'}</td>
          <td>{event['status']}</td>
          <td>{event['details'] or '-'}</td>
          <td>{event['created_at']}</td>
        </tr>
        """
        for event in snapshot["recent_audit_events"]
    )
    tenant_rows = "".join(
        f"""
        <tr>
          <td>{tenant['name']}</td>
          <td>{tenant['slug']}</td>
          <td>{'Yes' if tenant['is_active'] else 'No'}</td>
          <td>{tenant['created_at']}</td>
        </tr>
        """
        for tenant in snapshot.get("tenants", [])
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sentinel Admin Dashboard</title>
  <style>
    :root {{
      --bg: #f4efe7;
      --panel: rgba(255,255,255,0.84);
      --ink: #1f2933;
      --muted: #58626b;
      --line: rgba(31,41,51,0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 0% 0%, rgba(15,118,110,0.16), transparent 32%),
        radial-gradient(circle at 100% 100%, rgba(194,120,3,0.14), transparent 28%),
        var(--bg);
    }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 32px 20px 52px; }}
    h1 {{ margin-bottom: 8px; }}
    p {{ color: var(--muted); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 14px;
      margin: 24px 0;
    }}
    .card, .panel {{
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--panel);
      backdrop-filter: blur(8px);
      box-shadow: 0 18px 40px rgba(31,41,51,0.08);
    }}
    .card {{ padding: 18px; }}
    .card span {{ color: var(--muted); display: block; margin-bottom: 6px; }}
    .card strong {{ font-size: 1.9rem; }}
    .panel {{ padding: 20px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 12px 10px; text-align: left; border-bottom: 1px solid var(--line); }}
    th {{ color: var(--muted); text-transform: uppercase; font-size: 0.84rem; letter-spacing: 0.06em; }}
    pre {{
      padding: 14px;
      background: rgba(31,41,51,0.04);
      border-radius: 12px;
      border: 1px solid var(--line);
      white-space: pre-wrap;
      word-break: break-word;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Sentinel Admin Dashboard</h1>
    <p>Protected operational view for auth lifecycle, verification state, and refresh session health.</p>
    <div class="grid">{cards}</div>
    <div class="panel">
      <h2>Recent Users</h2>
      <table>
        <thead>
          <tr>
            <th>Tenant</th>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Verified</th>
            <th>Created</th>
            <th>Last Login</th>
          </tr>
        </thead>
        <tbody>{rows or '<tr><td colspan="7">No users yet.</td></tr>'}</tbody>
      </table>
    </div>
    <div class="panel" style="margin-top: 18px;">
      <h2>Tenants</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Slug</th>
            <th>Active</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>{tenant_rows or '<tr><td colspan="4">No tenants yet.</td></tr>'}</tbody>
      </table>
    </div>
    <div class="panel" style="margin-top: 18px;">
      <h2>Recent Audit Events</h2>
      <table>
        <thead>
          <tr>
            <th>Tenant</th>
            <th>Event</th>
            <th>Email</th>
            <th>Status</th>
            <th>Details</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>{audit_rows or '<tr><td colspan="6">No audit events yet.</td></tr>'}</tbody>
      </table>
    </div>
    <div class="panel" style="margin-top: 18px;">
      <h2>Raw Snapshot</h2>
      <pre>{json.dumps(snapshot, indent=2)}</pre>
    </div>
  </div>
</body>
</html>"""

@router.get("/overview")
async def overview(
    current_user: dict = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_snapshot(db)

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    current_user: dict = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    return HTMLResponse(_dashboard_html(await dashboard_snapshot(db)))


@router.get("/startup-overview", response_model=StartupOverviewResponse)
async def startup_overview_route(
    current_user: dict = Depends(require_role("admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    overview = await startup_overview(current_user, db)
    return StartupOverviewResponse(
        tenant=TenantResponse.model_validate(overview["tenant"]),
        metrics=overview["metrics"],
        recent_users=[UserResponse.model_validate(item) for item in overview["recent_users"]],
    )


@router.get("/tenants", response_model=list[TenantResponse])
async def tenants(
    current_user: dict = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    return [TenantResponse.model_validate(item) for item in await list_tenants(db)]


@router.post("/tenants", response_model=TenantResponse)
async def create_tenant_route(
    data: TenantCreateRequest,
    current_user: dict = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await create_tenant(data.name, data.slug, db)
    return TenantResponse.model_validate(tenant)


@router.post("/members", response_model=TeamMemberCreateResponse)
async def create_member_route(
    data: TeamMemberCreateRequest,
    request: Request,
    current_user: dict = Depends(require_role("admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    user, verification_token = await create_team_member(
        current_user,
        email=data.email,
        password=data.password,
        name=data.name,
        role=data.role,
        db=db,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    await send_email(
        to_email=user.email,
        subject="Verify your Sentinel team account",
        text_body=(
            "A startup admin created your Sentinel account.\n\n"
            f"Use this verification token to activate your account:\n{verification_token}\n"
        ),
    )
    return TeamMemberCreateResponse(
        message="Team member created. Verify the account to activate login.",
        verification_token=verification_token if settings.AUTH_DEBUG_RETURN_TOKENS else None,
        user=UserResponse.model_validate(user),
    )
