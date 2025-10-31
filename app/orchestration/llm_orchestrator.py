"""LLM Orchestrator for handling chat and tool actions.
This is the main orchestration layer that manages LLM calls,
tool executions and fallbacks, and itinerary creation."""

import json
import re
import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple
import httpx
from sqlalchemy.orm import Session as DBSession

from app.config import Settings
from app.orchestration.spend_cap import SpendCapManager
from app.orchestration.actions_schema import (
    SearchPOIsAction, SearchHotelsAction, FinalizeItineraryAction,
    ActionResult, TOOL_SCHEMA
)
from app.providers.opentripmap_client import OpenTripMapClient
from app.providers.hotels.static_stub import StaticStubHotelProvider
from app.providers.hotels.rapid_hotels import RapidAPIHotelProvider
from app.repositories.sessions import SessionRepository
from app.repositories.messages import MessageRepository
from app.repositories.itineraries import ItineraryRepository
from app.utils.tokens import estimate_tokens

logger = logging.getLogger(__name__)

class LLMOrchestrator:
    """Orchestrates LLM calls and tool actions for travel planning."""
    
    def __init__(self, settings: Settings, db: DBSession):
        self.settings = settings
        self.db = db
        self.spend_cap = SpendCapManager(settings, db)
        
        # Initialize providers
        self.opentripmap = OpenTripMapClient(settings, db)
        
        # Hotel provider selection
        if settings.rapidapi_hotels_enabled and settings.rapidapi_key:
            self.hotel_provider = RapidAPIHotelProvider(settings, db)
        else:
            self.hotel_provider = StaticStubHotelProvider(db)
        
        # Repositories
        self.session_repo = SessionRepository(db)
        self.message_repo = MessageRepository(db)
        self.itinerary_repo = ItineraryRepository(db)
        
        # OpenAI client
        self.openai_client = httpx.Client(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=60.0
        )
    
    async def process_chat_message(self,
                                    session_id: str,
                                    user_message: str,
                                    destination: Optional[str] = None,
                                    start_date: Optional[str] = None,
                                    end_date: Optional[str] = None,
                                    budget_tier: Optional[str] = None,
                                ) -> Dict[str, Any]:
                                    
        """
        Process a chat message and return the assistant's response.
        Args:
            session_id (str): User session ID.
            user_message (str): Message from the user.
            destination (Optional[str]): Destination city.
            start_date (Optional[str]): Start date in YYYY-MM-DD format.
            end_date (Optional[str]): End date in YYYY-MM-DD format.
            budget_tier (Optional[str]): Budget tier: 'budget', 'mid', or 'premium'.
        Returns:
            Dict with keys: 'response', 'success', 'spend_capped', 'itinerary_id'
        """
        # Check spend cap
        if self.spend_cap.is_spend_cap_exceeded():
            fallback_response = self.spend_cap.get_fallback_response()
            # Store the user message and fallback response
            self.message_repo.create_message(
                session_id,
                "user",
                user_message,
                tokens_in=estimate_tokens(user_message),
            )
            self.message_repo.create_message(
                session_id,
                "assistant",
                fallback_response,
                tokens_out=estimate_tokens(fallback_response),
            )
            
            return {
                "response": fallback_response,
                "success": False,
                "spend_capped": True,
                "itinerary_id": None
            }
        
        try:
            # Store user message with estimated input tokens for display
            self.message_repo.create_message(
                session_id,
                "user",
                user_message,
                tokens_in=estimate_tokens(user_message),
            )
            
            # Get conversation history
            messages = self._build_conversation_context(
                session_id, user_message, destination, start_date, end_date, budget_tier
            )
            
            # Make LLM call (pass form context so fallback preserves it)
            response = await self._call_llm_with_tools(
                messages,
                session_id,
                destination=destination,
                start_date=start_date,
                end_date=end_date,
                budget_tier=budget_tier,
            )
            
            if not response["success"]:
                error_msg = "I encountered an error processing your request. Please try again."
                self.message_repo.create_message(session_id, "assistant", error_msg)
                return {
                    "response": error_msg,
                    "success": False,
                    "spend_capped": False,
                    "itinerary_id": None
                }
            
            assistant_message = response["content"]
            itinerary_id = response.get("itinerary_id")
            
            # Store assistant message
            self.message_repo.create_message(
                session_id=session_id,
                role="assistant",
                content=assistant_message,
                tokens_in=response.get("prompt_tokens"),
                tokens_out=response.get("completion_tokens"),
                cost_usd=response.get("cost_usd"),
            )
            
            return {
                "response": assistant_message,
                "success": True,
                "spend_capped": False,
                "itinerary_id": itinerary_id
            }
            
        except Exception as e:
            logger.error(f"Error processing chat message: {e}")
            error_msg = "I encountered an unexpected error. Please try again."
            
            try:
                self.message_repo.create_message(
                    session_id,
                    "assistant",
                    error_msg,
                    tokens_out=estimate_tokens(error_msg),
                )
            except Exception:
                pass  # Don't fail if we can't store the error message
            
            return {
                "response": error_msg,
                "success": False,
                "spend_capped": False,
                "itinerary_id": None
            }
    
    def _build_conversation_context(self,
                                    session_id: str,
                                    current_message: str,
                                    destination: Optional[str] = None,
                                    start_date: Optional[str] = None,
                                    end_date: Optional[str] = None,
                                    budget_tier: Optional[str] = None,
                                ) -> List[Dict[str, str]]:
        """Build conversation context for LLM.
        Args:
            session_id (str): User session ID.
            current_message (str): Message from the user.
            destination (Optional[str]): Destination city.
            start_date (Optional[str]): Start date in YYYY-MM-DD format.
            end_date (Optional[str]): End date in YYYY-MM-DD format.
            budget_tier (Optional[str]): Budget tier: 'budget', 'mid', or 'premium'.
        Returns:
            List[Dict[str, str]]: List of messages for the LLM context.
        """
        
        # System prompt
        system_prompt = self._get_system_prompt()
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add context from form if provided
        context_parts = []
        if destination:
            context_parts.append(f"Destination: {destination}")
        if start_date and end_date:
            context_parts.append(f"Travel dates: {start_date} to {end_date}")
        if budget_tier:
            context_parts.append(f"Budget tier: {budget_tier}")
        
        if context_parts:
            context_message = "Travel planning context:\n" + "\n".join(context_parts)
            messages.append({"role": "system", "content": context_message})
        
        # Add recent conversation history (last 10 messages)
        recent_messages = self.message_repo.get_recent_messages(session_id, limit=10)
        for msg in reversed(recent_messages):  # Reverse to get chronological order
            if msg.role in ["user", "assistant"]:
                messages.append({"role": msg.role, "content": msg.content})
        
        # Finally add current message
        messages.append({"role": "user", "content": current_message})
        
        return messages
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for the travel assistant."""
        return """You are a helpful travel assistant that creates personalized city trip itineraries. 

Your capabilities:
- Search for points of interest (POIs) using search_pois action (this may return no results from APIs)
- Search for hotels using search_hotels action  
- Create and save complete itineraries using finalize_itinerary action

CRITICAL: You have extensive knowledge of major destinations. When API tools return no POI results, DO NOT STOP - instead, use your own knowledge to create excellent itineraries with famous attractions!

Guidelines:
- Always be helpful and enthusiastic about travel planning
- Ask clarifying questions if destination, dates, or budget are unclear
- Try using tools first, but don't let API failures stop you from creating great itineraries
- ALWAYS create detailed day-by-day itineraries, whether you get API data or not
- Use your extensive knowledge of popular destinations when APIs fail
- Consider the budget tier when making recommendations (budget/mid/premium)
- Include a mix of must-see attractions, local experiences, and practical information
- Always finalize the itinerary at the end so the user can export it

Budget tiers:
- Budget: Focus on free activities, budget accommodations (under €80/night), local food
- Mid: Mix of paid attractions, mid-range hotels (€80-150/night), good restaurants  
- Premium: High-end experiences, luxury hotels (€150+/night), fine dining

When creating itineraries:
1. Try search_pois to find attractions (but continue even if it returns no results)
2. Try search_hotels to find accommodations (but continue even if it returns no results)
3. Use your knowledge to create excellent recommendations with famous attractions and experiences
4. Organize into a logical day-by-day structure
5. Always use finalize_itinerary to save the complete plan

Your knowledge includes major attractions for popular destinations:
- Rome: Colosseum, Vatican City, Trevi Fountain, Spanish Steps, Pantheon, Roman Forum, Castel Sant'Angelo
- Paris: Eiffel Tower, Louvre, Notre-Dame, Arc de Triomphe, Champs-Élysées, Montmartre, Musée d'Orsay
- London: Big Ben, Tower of London, British Museum, Buckingham Palace, London Eye, Westminster Abbey
- Barcelona: Sagrada Familia, Park Güell, Las Ramblas, Gothic Quarter, Casa Batlló
- Amsterdam: Anne Frank House, Van Gogh Museum, Rijksmuseum, Jordaan District, Red Light District
- And many more for other cities worldwide!

IMPORTANT: Never say you "can't find POIs" and then stop. Always proceed to create itineraries using your knowledge!

Keep responses engaging and informative. Focus on creating memorable travel experiences!"""
    
    async def _call_llm_with_tools(self,
                                    messages: List[Dict[str, str]],
                                    session_id: str,
                                    *,
                                    destination: Optional[str] = None,
                                    start_date: Optional[str] = None,
                                    end_date: Optional[str] = None,
                                    budget_tier: Optional[str] = None,
                                ) -> Dict[str, Any]:
        """Make LLM call with tool support.
        messages (List[Dict[str, str]]): Conversation messages.
        session_id (str): User session ID.
        Returns:
            Dict[str, Any]: LLM response with content and usage info.
        """
        
        try:
            # Prepare request
            request_data = {
                "model": self.settings.openai_model,
                "messages": messages,
                "tools": [TOOL_SCHEMA],
                "tool_choice": "auto",
                "temperature": 0.7,
                "max_tokens": 1500,
            }
            
            # Make API call
            response = self.openai_client.post("/chat/completions", json=request_data)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract usage info
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            # Record usage
            self.spend_cap.record_llm_call(
                session_id=session_id,
                model=self.settings.openai_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            
            # Process response
            choice = data["choices"][0]
            message = choice["message"]
            
            # Check for tool calls
            if message.get("tool_calls"):
                return await self._handle_tool_calls(
                    message["tool_calls"],
                    session_id,
                    prompt_tokens,
                    completion_tokens,
                    destination=destination,
                    start_date=start_date,
                    end_date=end_date,
                    budget_tier=budget_tier,
                )
            
            # Some models may emit a pseudo tool call in plain text instead of tool_calls
            pseudo_calls = None
            preface_text = ""
            try:
                pseudo_calls, preface_text = self._parse_pseudo_tool_calls(message.get("content") or "")
            except Exception:
                pseudo_calls = None

            if pseudo_calls:
                result = await self._handle_tool_calls(
                    pseudo_calls,
                    session_id,
                    prompt_tokens,
                    completion_tokens,
                    destination=destination,
                    start_date=start_date,
                    end_date=end_date,
                    budget_tier=budget_tier,
                )
                # Preserve any friendly preface the model wrote before the tool call
                if preface_text.strip():
                    combined = preface_text.strip()
                    if result.get("content"):
                        combined += "\n\n" + result["content"]
                    result["content"] = combined
                return result

            # Regular response when there are no tools involved
            return {
                "success": True,
                "content": message.get("content", ""),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
            
        except httpx.HTTPError as e:
            logger.error(f"OpenAI API error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error in LLM call: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_tool_calls(self,
                                tool_calls: List[Dict[str, Any]],
                                session_id: str,
                                prompt_tokens: int,
                                completion_tokens: int,
                                *,
                                destination: Optional[str] = None,
                                start_date: Optional[str] = None,
                                end_date: Optional[str] = None,
                                budget_tier: Optional[str] = None,
                            ) -> Dict[str, Any]:
        """Handle tool calls from LLM. Called by _call_llm_with_tools.
        Handles failures in POI searches by continuing the conversation
        with LLM knowledge.
        Args:
            tool_calls (List[Dict[str, Any]]): List of tool calls from the LLM.
            session_id (str): The session ID for tracking.
            prompt_tokens (int): Number of prompt tokens used.
            completion_tokens (int): Number of completion tokens used.
        Returns:
            Dict[str, Any]: The response from handling tool calls.
        """
        
        results = []
        itinerary_id = None
        
        for tool_call in tool_calls:
            if tool_call["function"]["name"] == "execute_travel_action":
                try:
                    args = json.loads(tool_call["function"]["arguments"])
                    result = await self._execute_action(args, session_id)
                    results.append(result)
                    
                    # Check if this was a finalize_itinerary action
                    if result.action == "finalize_itinerary" and result.success:
                        itinerary_id = result.data.get("itinerary_id")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in tool call: {e}")
                    results.append(ActionResult(
                        action="unknown",
                        success=False,
                        error="Invalid tool call format"
                    ))
        
        # Determine if any tool failures should trigger fallback continuation
        poi_failed = any(
            r.action == "search_pois" and r.success and isinstance(r.data, dict) and r.data.get("count", 0) == 0
            for r in results
        )
        hotel_failed = any(
            r.action == "search_hotels" and r.success and isinstance(r.data, dict) and r.data.get("count", 0) == 0
            for r in results
        )
        itinerary_created = any(r.action == "finalize_itinerary" and r.success for r in results)

        # Generate response based on results
        response_content = self._generate_tool_response(results)
        
        # If tool response is empty OR hotel/POI search failed without itinerary, continue with LLM conversation
        if not response_content or ((poi_failed or hotel_failed) and not itinerary_created):
            logger.info("Tool response empty (POI search failed), continuing with LLM conversation")
            
            # Add the tool results and original form context to conversation as system messages
            tool_summary = self._generate_tool_summary_for_llm(results)
            
            # Continue the conversation by making another LLM call without tools.
            # This allows the LLM to proceed with its own knowledge.
            # Hacky.
            try:
                # Get original context
                original_messages = self.message_repo.get_recent_messages(session_id, limit=8)
                conversation_context = []
                
                # Add system prompt
                system_prompt = self._get_system_prompt()
                conversation_context.append({"role": "system", "content": system_prompt})

                # Include original form context so the model doesn't ask again
                context_parts: List[str] = []
                if destination:
                    context_parts.append(f"Destination: {destination}")
                if start_date and end_date:
                    context_parts.append(f"Travel dates: {start_date} to {end_date}")
                if budget_tier:
                    context_parts.append(f"Budget tier: {budget_tier}")
                if context_parts:
                    context_message = "Travel planning context:\n" + "\n".join(context_parts)
                    conversation_context.append({"role": "system", "content": context_message})

                # Summarize tool results for continuity
                conversation_context.append({
                    "role": "system",
                    "content": f"Tool results: {tool_summary}"
                })
                
                # Add recent history (excluding the most recent user message which is being processed)
                for msg in reversed(original_messages):
                    if msg.role in ["user", "assistant"]:
                        conversation_context.append({"role": msg.role, "content": msg.content})
                
                # Make LLM call without tools to continue the conversation
                request_data = {
                    "model": self.settings.openai_model,
                    "messages": conversation_context,
                    "temperature": 0.7,
                    "max_tokens": 1500,
                }
                
                response = self.openai_client.post("/chat/completions", json=request_data)
                response.raise_for_status()
                data = response.json()
                
                # Extract usage info
                usage = data.get("usage", {})
                follow_up_prompt_tokens = usage.get("prompt_tokens", 0)
                follow_up_completion_tokens = usage.get("completion_tokens", 0)
                
                # Record usage
                self.spend_cap.record_llm_call(
                    session_id=session_id,
                    model=self.settings.openai_model,
                    prompt_tokens=follow_up_prompt_tokens,
                    completion_tokens=follow_up_completion_tokens,
                )
                
                # Get the response
                choice = data["choices"][0]
                message = choice["message"]
                follow_up_content = message["content"]
                
                return {
                    "success": True,
                    "content": follow_up_content,
                    "prompt_tokens": prompt_tokens + follow_up_prompt_tokens,
                    "completion_tokens": completion_tokens + follow_up_completion_tokens,
                    "itinerary_id": itinerary_id,
                }
                
            except Exception as e:
                logger.error(f"Follow-up LLM call failed: {e}")
                # Fall back to default response
                response_content = "I'm ready to create a great itinerary for you! Please provide your travel dates and I'll design a detailed plan."
        
        return {
            "success": True,
            "content": response_content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "itinerary_id": itinerary_id,
        }
    
    async def _execute_action(self, args: Dict[str, Any], session_id: str) -> ActionResult:
        """Execute a travel action.
        Args:
            args (Dict[str, Any]): Action arguments.
            session_id (str): User session ID.
        Returns:
            ActionResult: The result of the action execution.
        """
        action_type = args.get("action")
        
        try:
            if action_type == "search_pois":
                return await self._search_pois_action(args)
            elif action_type == "search_hotels":
                return await self._search_hotels_action(args)
            elif action_type == "finalize_itinerary":
                return await self._finalize_itinerary_action(args, session_id)
            else:
                return ActionResult(
                    action=action_type or "unknown",
                    success=False,
                    error=f"Unknown action: {action_type}"
                )
                
        except Exception as e:
            logger.error(f"Error executing action {action_type}: {e}")
            return ActionResult(
                action=action_type or "unknown",
                success=False,
                error=str(e)
            )
    
    async def _search_pois_action(self, args: Dict[str, Any]) -> ActionResult:
        """Execute search_pois action with fallback to LLM knowledge.
        If POIS search fails (e.g. API error or no results), return 
        success=True and let LLM handle with its own knowledge.
        Args:
            args (Dict[str, Any]): Action arguments.
        Returns:
            ActionResult: The result of the POI search.
        """
        city = args.get("city", "")
        country = args.get("country")
        categories = args.get("categories", [])
        limit = args.get("limit", 20)
        
        if not city:
            return ActionResult(
                action="search_pois",
                success=False,
                error="City is required"
            )
        
        # Try to get POIs from external API first
        pois = []
        api_success = False
        
        # Convert categories to OpenTripMap format
        kinds = None
        if categories:
            # Map common categories to OpenTripMap kinds
            category_mapping = {
                "museums": "museums",
                "historic": "historic", 
                "restaurants": "foods",
                "parks": "natural",
                "attractions": "tourist_facilities",
                "shopping": "shops",
                "entertainment": "entertainment",
            }
            mapped_kinds = []
            for cat in categories:
                if cat.lower() in category_mapping:
                    mapped_kinds.append(category_mapping[cat.lower()])
            if mapped_kinds:
                kinds = ",".join(mapped_kinds)
        
        # Search using coordinates
        city_coords = self._get_city_coordinates(city, country)
        
        if city_coords:
            try:
                pois = await self.opentripmap.search_places_by_radius(
                    lat=city_coords["lat"],
                    lon=city_coords["lon"],
                    kinds=kinds,
                    limit=limit
                )
                if len(pois) > 0:
                    api_success = True
            except Exception as e:
                logger.warning(f"POI API failed for {city}: {e}")
        
        # Always return success - let LLM handle empty results with its own knowledge
        return ActionResult(
            action="search_pois",
            success=True,
            data={
                "city": city,
                "country": country,
                "categories": categories,
                "pois": pois,
                "count": len(pois),
                "api_success": api_success,
                "use_llm_knowledge": len(pois) == 0  # Signal to LLM to use its own knowledge
            }
        )
    
    async def _search_hotels_action(self, args: Dict[str, Any]) -> ActionResult:
        """Execute search_hotels action.
        Basic, no-fallback hotel search.
        Args:
            args (Dict[str, Any]): Action arguments.
        Returns:
            ActionResult: The result of the hotel search.
        """
        city = args.get("city", "")
        country = args.get("country")
        budget_tier = args.get("budget_tier", "mid")
        limit = args.get("limit", 10)
        
        if not city:
            return ActionResult(
                action="search_hotels",
                success=False,
                error="City is required"
            )
        
        hotels = await self.hotel_provider.search_hotels(
            city=city,
            country=country,
            budget_tier=budget_tier,
            limit=limit
        )
        
        return ActionResult(
            action="search_hotels",
            success=True,
            data={
                "city": city,
                "budget_tier": budget_tier,
                "hotels": hotels,
                "count": len(hotels)
            }
        )
    
    async def _finalize_itinerary_action(self, args: Dict[str, Any], session_id: str) -> ActionResult:
        """Execute finalize_itinerary action.
        Args:
            args (Dict[str, Any]): Action arguments.
            session_id (str): User session ID.
        Returns:
            ActionResult: The result of the itinerary finalization.
        """
        try:
            # Extract itinerary data
            city = args.get("city", "")
            country = args.get("country")
            start_date_str = args.get("start_date", "")
            end_date_str = args.get("end_date", "")
            budget_tier = args.get("budget_tier", "mid")
            days_data = args.get("days", [])
            
            if not all([city, start_date_str, end_date_str, days_data]):
                return ActionResult(
                    action="finalize_itinerary",
                    success=False,
                    error="Missing required fields: city, start_date, end_date, days"
                )
            
            # Parse dates
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            
            # Create itinerary
            itinerary = self.itinerary_repo.create_itinerary(
                session_id=session_id,
                city=city,
                country=country,
                start_date=start_date,
                end_date=end_date,
                budget_tier=budget_tier,
            )
            
            # Create days and items
            for day_data in days_data:
                day_index = day_data.get("day_index", 0)
                day_date_str = day_data.get("date", "")
                activities = day_data.get("activities", [])
                
                day_date = datetime.strptime(day_date_str, "%Y-%m-%d").date()
                
                # Create day
                day = self.itinerary_repo.create_day(
                    itinerary_id=str(itinerary.id),
                    day_index=day_index,
                    date_value=day_date,
                )
                
                # Create activities
                for activity in activities:
                    self.itinerary_repo.create_item(
                        day_id=str(day.id),
                        item_type=activity.get("type", "poi"),
                        start_time=activity.get("start_time"),
                        end_time=activity.get("end_time"),
                        notes=f"{activity.get('name', '')} - {activity.get('notes', '')}".strip(' -'),
                    )
            
            return ActionResult(
                action="finalize_itinerary",
                success=True,
                data={
                    "itinerary_id": str(itinerary.id),
                    "city": city,
                    "days_count": len(days_data)
                }
            )
            
        except ValueError as e:
            return ActionResult(
                action="finalize_itinerary",
                success=False,
                error=f"Invalid date format: {e}"
            )
        except Exception as e:
            logger.error(f"Error finalizing itinerary: {e}")
            return ActionResult(
                action="finalize_itinerary",
                success=False,
                error=str(e)
            )
    
    def _get_city_coordinates(self, city: str, country: Optional[str]) -> Optional[Dict[str, float]]:
        """Get approximate coordinates for a city.
        Args:
            city (str): City name.
            country (Optional[str]): Country name.
        Returns:
            Optional[Dict[str, float]]: Dictionary with 'lat' and 'lon' or None.
        """
        # Simplified city coordinate lookup for demo only
        # TODO: Integrate with a geocoding API for real data
        city_coords = {
            "athens": {"lat": 37.9755, "lon": 23.7348},
            "paris": {"lat": 48.8566, "lon": 2.3522},
            "london": {"lat": 51.5074, "lon": -0.1278},
            "rome": {"lat": 41.9028, "lon": 12.4964},
            "madrid": {"lat": 40.4168, "lon": -3.7038},
            "berlin": {"lat": 52.5200, "lon": 13.4050},
            "amsterdam": {"lat": 52.3676, "lon": 4.9041},
            "prague": {"lat": 50.0755, "lon": 14.4378},
            "vienna": {"lat": 48.2082, "lon": 16.3738},
            "barcelona": {"lat": 41.3851, "lon": 2.1734},
        }
        
        return city_coords.get(city.lower())
    
    def _generate_tool_summary_for_llm(self, results: List[ActionResult]) -> str:
        """Generate a concise summary of tool results for LLM continuation."""
        summaries = []
        
        for result in results:
            if result.action == "search_pois":
                data = result.data
                city = data.get("city", "")
                count = data.get("count", 0)
                
                if count == 0:
                    summaries.append(f"POI search for {city} returned no results from external APIs, but I have extensive knowledge of {city}'s attractions.")
                else:
                    summaries.append(f"Found {count} POIs in {city} from external data.")
            
            elif result.action == "search_hotels":
                data = result.data
                city = data.get("city", "")
                count = data.get("count", 0)
                tier = data.get("budget_tier", "mid")
                
                if count == 0:
                    summaries.append(f"Hotel search for {city} returned no results, but I can recommend excellent {tier}-tier accommodations.")
                else:
                    summaries.append(f"Found {count} {tier}-tier hotels in {city}.")
        
        if not summaries:
            return "Tool execution completed. Ready to proceed with itinerary creation."
        
        return " ".join(summaries) + " I'm ready to create a detailed itinerary."
    
    def _generate_tool_response(self, results: List[ActionResult]) -> str:
        """Generate response content based on tool results.
        Basic, fallback only for POI search failures.
        TODO: Expand fallback handling for hotels.
        Args:
            results (List[ActionResult]): List of action results.
        Returns:
            str: Response content for the user.
        """
        if not results:
            return "I couldn't execute the requested actions. Please try again."
        
        response_parts = []
        poi_search_failed = False
        
        for result in results:
            if not result.success:
                response_parts.append(f"❌ {result.action} failed: {result.error}")
                continue
            
            if result.action == "search_pois":
                data = result.data
                count = data.get("count", 0)
                city = data.get("city", "")
                use_llm_knowledge = data.get("use_llm_knowledge", False)
                
                if count > 0:
                    response_parts.append(
                        f"🏛️ Found {count} interesting places in {city}! "
                        f"I'll include the best ones in your itinerary."
                    )
                else:
                    # API returned no results - this is just informational for the user
                    poi_search_failed = True
                    # Don't add any message here - let the system handle it seamlessly
            
            elif result.action == "search_hotels":
                data = result.data
                count = data.get("count", 0)
                city = data.get("city", "")
                tier = data.get("budget_tier", "mid")
                
                if count > 0:
                    response_parts.append(
                        f"🏨 Found {count} {tier}-range hotels in {city}! "
                        f"I'll recommend the best options for your stay."
                    )
                else:
                    response_parts.append(f"I'll provide excellent hotel recommendations for {city} based on your {tier} budget.")
            
            elif result.action == "finalize_itinerary":
                data = result.data
                city = data.get("city", "")
                itinerary_id = data.get("itinerary_id", "")
                days_count = data.get("days_count", 0)
                
                response_parts.append(
                    f"✅ Perfect! I've created your {days_count}-day itinerary for {city}! "
                    f"You can export it as JSON using the link below or continue chatting to refine it."
                )
        
        # If POI search failed and no itinerary was created, return empty string
        # This will signal that the conversation should continue without a tool response
        if poi_search_failed and not any(r.action == "finalize_itinerary" for r in results):
            if not response_parts:  # Only POI search happened and failed
                return ""  # Empty response means continue with LLM generation
        
        return " ".join(response_parts) if response_parts else "Actions completed successfully!"
    
    def close(self):
        """Clean up resources."""
        try:
            self.openai_client.close()
            self.opentripmap.close()
            if hasattr(self.hotel_provider, 'close'):
                self.hotel_provider.close()
        except Exception:
            pass  # Ignore cleanup errors
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.close()
        except Exception:
            pass

    # ---------------------------
    # Helpers
    # ---------------------------
    def _parse_pseudo_tool_calls(self, content: str) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        """Parse pseudo tool calls embedded in assistant text.

        Expected format, possibly repeated:
        [some_action]
        { ...json... }

        Matches any square-bracketed tag that contains the word 'action' (case-insensitive),
        e.g., [execute_travel_action], [action], [customActionTag].

        Returns a tuple of (tool_calls, preface_text). `tool_calls` is a list in the
        same shape as OpenAI's tool_calls with function name and JSON string arguments.
        The `preface_text` is any content before the first pseudo call.
        """
        pattern = re.compile(r"\[[^\]]*action[^\]]*\]", re.IGNORECASE)
        first_match = pattern.search(content)
        if not first_match:
            return None, ""

        preface = content[:first_match.start()]
        calls: List[Dict[str, Any]] = []

        for m in pattern.finditer(content):
            # Find the start of JSON block after the tag
            brace_start = content.find("{", m.end())
            if brace_start == -1:
                continue
            # Extract balanced JSON braces
            depth = 0
            i = brace_start
            while i < len(content):
                ch = content[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        json_str = content[brace_start:i + 1]
                        calls.append({
                            "function": {
                                # Keep the single known function name the tool schema expects
                                "name": "execute_travel_action",
                                "arguments": json_str,
                            }
                        })
                        break
                i += 1
            # If braces never balanced, skip this match

        if not calls:
            return None, preface

        return calls, preface