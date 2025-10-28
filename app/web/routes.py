"""FastAPI routes for the travel assistant."""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings, Settings
from app.deps import get_db, get_admin_user, hash_ip
from app.orchestration.llm_orchestrator import LLMOrchestrator
from app.repositories.sessions import SessionRepository
from app.repositories.messages import MessageRepository
from app.repositories.itineraries import ItineraryRepository
from app.repositories.ledger import LedgerRepository
from app.repositories.cache import CacheRepository
from app.web.forms import ChatForm

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with chat interface."""
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "title": "Travel Assistant",
            "messages": [],
            "session_id": None,
        }
    )


@router.post("/chat", response_class=HTMLResponse)
async def chat(
    request: Request,
    message: str = Form(...),
    destination: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    budget_tier: Optional[str] = Form("mid"),
    session_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Handle chat form submission."""
    
    try:
        # Validate form data
        form_data = {
            "message": message,
            "destination": destination,
            "budget_tier": budget_tier,
        }
        
        # Parse dates if provided
        parsed_start_date = None
        parsed_end_date = None
        if start_date:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
                form_data["start_date"] = parsed_start_date
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start date format")
        
        if end_date:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
                form_data["end_date"] = parsed_end_date
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end date format")
        
        # Validate using Pydantic
        try:
            form = ChatForm(**form_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Get or create session
        session_repo = SessionRepository(db)
        if session_id:
            try:
                session_uuid = uuid.UUID(session_id)
                session = session_repo.get_session(str(session_uuid))
                if not session:
                    # Create new session if not found
                    client_ip = request.client.host
                    session = session_repo.create_session(client_ip, settings.ip_hash_salt)
            except ValueError:
                # Invalid UUID, create new session
                client_ip = request.client.host
                session = session_repo.create_session(client_ip, settings.ip_hash_salt)
        else:
            # Create new session
            client_ip = request.client.host
            session = session_repo.create_session(client_ip, settings.ip_hash_salt)
        
        # Process chat message
        orchestrator = LLMOrchestrator(settings, db)
        try:
            result = await orchestrator.process_chat_message(
                session_id=str(session.id),
                user_message=form.message,
                destination=form.destination,
                start_date=start_date,
                end_date=end_date,
                budget_tier=form.budget_tier,
            )
        finally:
            orchestrator.close()
        
        # Get conversation history
        message_repo = MessageRepository(db)
        messages = message_repo.get_messages_by_session(str(session.id))
        
        # Prepare template context
        context = {
            "request": request,
            "title": "Travel Assistant",
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.created_at.strftime("%H:%M"),
                }
                for msg in messages
            ],
            "session_id": str(session.id),
            "itinerary_id": result.get("itinerary_id"),
            "spend_capped": result.get("spend_capped", False),
            "success": result.get("success", True),
        }
        
        return templates.TemplateResponse("chat.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/v1/itineraries/{itinerary_id}")
async def export_itinerary(
    itinerary_id: str,
    db: Session = Depends(get_db),
):
    """Export itinerary as JSON."""
    
    try:
        itinerary_repo = ItineraryRepository(db)
        itinerary = itinerary_repo.get_itinerary(itinerary_id)
        
        if not itinerary:
            raise HTTPException(status_code=404, detail="Itinerary not found")
        
        # Build export data
        export_data = {
            "id": str(itinerary.id),
            "city": itinerary.city,
            "country": itinerary.country,
            "start_date": itinerary.start_date.isoformat(),
            "end_date": itinerary.end_date.isoformat(),
            "budget_tier": itinerary.budget_tier,
            "created_at": itinerary.created_at.isoformat(),
            "days": []
        }
        
        # Add days and items
        for day in sorted(itinerary.days, key=lambda d: d.day_index):
            day_data = {
                "day_index": day.day_index,
                "date": day.date.isoformat(),
                "items": []
            }
            
            for item in day.items:
                item_data = {
                    "type": item.item_type,
                    "start_time": item.start_time.strftime("%H:%M") if item.start_time else None,
                    "end_time": item.end_time.strftime("%H:%M") if item.end_time else None,
                    "notes": item.notes,
                }
                
                # Add place or hotel info if available
                if item.place:
                    item_data["place"] = {
                        "name": item.place.name,
                        "lat": item.place.lat,
                        "lon": item.place.lon,
                        "address": item.place.address,
                        "categories": item.place.categories,
                        "rating": item.place.rating,
                    }
                
                if item.hotel:
                    item_data["hotel"] = {
                        "name": item.hotel.name,
                        "lat": item.hotel.lat,
                        "lon": item.hotel.lon,
                        "address": item.hotel.address,
                        "rating": item.hotel.rating,
                        "price_eur_per_night": item.hotel.price_eur_per_night,
                        "url": item.hotel.url,
                    }
                
                day_data["items"].append(item_data)
            
            export_data["days"].append(day_data)
        
        return JSONResponse(content=export_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting itinerary {itinerary_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    admin_user: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Admin dashboard."""
    
    try:
        # Get various stats
        ledger_repo = LedgerRepository(db)
        cache_repo = CacheRepository(db)
        
        # Spend cap info
        current_month = datetime.utcnow().strftime("%Y-%m")
        monthly_stats = ledger_repo.get_monthly_stats(current_month)
        daily_costs = ledger_repo.get_daily_costs(30)
        recent_usage = ledger_repo.get_recent_usage(20)
        
        # Cache stats
        cache_stats = cache_repo.get_cache_stats()
        
        # System info
        system_info = {
            "monthly_cap_usd": settings.monthly_spend_cap_usd,
            "openai_model": settings.openai_model,
            "rapidapi_enabled": settings.rapidapi_hotels_enabled,
            "cache_ttl_hours": settings.api_cache_ttl_seconds / 3600,
        }
        
        context = {
            "request": request,
            "title": "Admin Dashboard",
            "monthly_stats": monthly_stats,
            "daily_costs": daily_costs,
            "recent_usage": [
                {
                    "timestamp": usage.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "model": usage.model,
                    "tokens_in": usage.prompt_tokens,
                    "tokens_out": usage.completion_tokens,
                    "cost_usd": f"{usage.cost_usd:.4f}",
                    "blocked": usage.blocked_after,
                }
                for usage in recent_usage
            ],
            "cache_stats": cache_stats,
            "system_info": system_info,
        }
        
        return templates.TemplateResponse("admin.html", context)
        
    except Exception as e:
        logger.error(f"Error in admin dashboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}