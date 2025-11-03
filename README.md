# Travel Assistant Chatbot 🌍✈️
Github repo:
https://github.com/lapikuhu/LLM_powered_travel-assistant_demo

A simple city-trip itinerary generator via chat interface, built with FastAPI and powered by OpenAI's GPT models. This application creates personalized day-by-day travel itineraries by integrating with OpenTripMap for points of interest and providing hotel recommendations.

__NOTE__:  The core of the repo was built iteratively with agentic Copilot using a design brief and a specs file (included in the spec_folder) prescribing the architecture, the functionality and the stack as a proof-of-concept of the methodology. Manual code review, corrections and debugging were of course implemented. As of 31/10/2025, API responses are still empty. 

## Features

- 💬 **Chat Interface**: Server-rendered chat with no JavaScript required
- 💬 **Chat Interface**: Server-rendered chat with no JavaScript required (optional City/Country fields)
- 🏛️ **POI Integration**: Real-time data from OpenTripMap API
- 🏨 **Hotel Recommendations**: Static stub provider with optional RapidAPI integration
- 💰 **Spend Cap Management**: Built-in $10 monthly LLM spend limit with graceful degradation
- 📊 **Admin Dashboard**: Cost monitoring, usage tracking, and system health
- 📱 **Itinerary Export**: JSON export for saved itineraries
- 🗄️ **Smart Caching**: API response caching for improved performance
- 🔒 **Security**: HTTP Basic auth for admin, IP hashing for privacy

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, Alembic
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **LLM**: OpenAI GPT-4 with function calling
- **APIs**: OpenTripMap (POIs), RapidAPI Hotels (optional)
- **Frontend**: Jinja2 templates, pure CSS (no JavaScript)
- **Deployment**: Docker, Docker Compose

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd travel-assistant
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here
OPENTRIPMAP_API_KEY=your_opentripmap_api_key_here
ADMIN_PASSWORD=your_secure_password_here
SECRET_KEY=your_secret_key_here
IP_HASH_SALT=your_salt_here

# Optional
RAPIDAPI_KEY=your_rapidapi_key_here
RAPIDAPI_HOTELS_ENABLED=true
```

### 4. Initialize Database

```bash
alembic upgrade head
python scripts/seed_stub_hotels.py
```

## Docker Deployment


# With PostgreSQL
docker-compose --profile postgres up -d
docker run -p 8000:8000 --env-file .env travel-assistant
```

## API Keys Setup
1. Visit [OpenAI Platform](https://platform.openai.com/)
2. Create an account and add billing
3. Generate an API key
4. Add to `.env` as `OPENAI_API_KEY`

### OpenTripMap API Key (Required)
1. Visit [OpenTripMap](https://opentripmap.io/)
2. Sign up for a free account
3. Get your API key from the dashboard
4. Add to `.env` as `OPENTRIPMAP_API_KEY`

### RapidAPI Hotels (Optional)
1. Visit [RapidAPI](https://rapidapi.com/)
2. Subscribe to a hotel API (e.g., Booking.com)
3. Get your RapidAPI key
4. Add to `.env` and set `RAPIDAPI_HOTELS_ENABLED=true`

*Note: Without RapidAPI, the app uses static stub hotel data for major European cities.*

## Usage

### Creating an Itinerary

1. **Visit the home page** at `http://localhost:8000`
2. **Fill in the chat form** with your travel details:
   - City and Country (optional, helps with accuracy)
   - Travel dates
   - Budget tier (budget/mid/premium)
   - Your message describing what you want to do

3. **Chat with the assistant** to refine your itinerary:
   - "I want to visit Athens for 3 days with a mid-range budget"
   - "Add more museums to day 2"
   - "Find hotels near the city center"

4. **Export your itinerary** as JSON once it's finalized

### Admin Dashboard

Visit `http://localhost:8000/admin` (credentials from `.env`) to monitor:

- **Spend tracking**: Monthly costs vs. budget cap
- **Token usage**: Prompt/completion tokens by day
- **API cache**: Hit ratios and provider statistics  
- **Recent activity**: LLM calls and error logs
- **System health**: Configuration and status

### Budget Tiers

- **Budget** (€0-80/night): Free activities, budget accommodations, local food
- **Mid-range** (€80-150/night): Mix of paid attractions, mid-range hotels
- **Premium** (€150+/night): High-end experiences, luxury accommodations

## Spend Cap Management

The application enforces a $10 monthly spend limit on OpenAI API calls:

- **Monitoring**: Real-time cost tracking in admin dashboard
- **Alerts**: Warnings at 80% usage, blocking at 100%
- **Graceful degradation**: Fallback responses when capped
- **Reset**: Automatic monthly reset
## Architecture

### Components

- **Web Backend**: FastAPI routes, Jinja2 templates
### Data Flow

```
User Input → FastAPI → LLM Orchestrator → [Tool Actions] → Database → Response
                           ↓
                    OpenTripMap/Hotels APIs
```

### Database Schema

- **Sessions**: Anonymous user sessions with IP hashing
- **Messages**: Chat history with token/cost tracking
- **Itineraries**: Saved trip plans with days and items
- **Places/Hotels**: Normalized POI and accommodation data
- **Cache**: API response caching with TTL
- **Ledger**: LLM usage tracking for spend cap

## API Endpoints

- `POST /chat` - Process chat message
- `GET /api/v1/itineraries/{id}` - Export itinerary JSON
- `GET /admin` - Admin dashboard (HTTP Basic auth)
- `GET /health` - Health check

#### POST /chat form fields

The server expects standard form fields from the chat page:

- `message` (required): User message
- `city` (optional): Destination city
- `country` (optional): Destination country
- `start_date` (optional, YYYY-MM-DD)
- `end_date` (optional, YYYY-MM-DD)
- `budget_tier` (optional: `budget` | `mid` | `premium`, defaults to `mid`)

## Development

### Project Structure

```
travel-assistant/
├── app/
│   ├── db/                    # Database models and migrations
│   ├── orchestration/         # LLM orchestrator and spend cap
│   ├── providers/             # External API integrations
│   ├── repositories/          # Data access layer
│   ├── web/                   # FastAPI routes and templates
│   └── main.py               # Application entry point
├── tests/                     # Test suites
├── scripts/                   # Utility scripts
└── docker-compose.yml        # Container orchestration
```

### Running Tests

```bash
pytest tests/
```

### Code Quality

```bash
# Format code
black app/ tests/

# Lint code
ruff check app/ tests/

# Type checking
mypy app/
```
# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | SQLite | Database connection string |
| `OPENAI_API_KEY` | Yes | - | OpenAI API key |
| `RAPIDAPI_KEY` | No | - | RapidAPI key for hotels |
| `RAPIDAPI_HOTELS_ENABLED` | No | false | Enable RapidAPI hotels |
| `ADMIN_USERNAME` | No | admin | Admin dashboard username |
| `ADMIN_PASSWORD` | Yes | - | Admin dashboard password |
| `SECRET_KEY` | Yes | - | Security secret |
| `IP_HASH_SALT` | Yes | - | Salt for IP hashing |

### Supported Cities

The static hotel provider includes data for:
- Athens, Greece
- Paris, France  
- London, United Kingdom
- Rome, Italy
- Madrid, Spain
- Berlin, Germany
- Amsterdam, Netherlands
- Prague, Czech Republic
- Vienna, Austria
- Barcelona, Spain

*OpenTripMap supports worldwide POI data.*

## Troubleshooting

### Common Issues

**"Import errors" during development**
- Install dependencies: `pip install -r requirements.txt`
- Check Python path: `export PYTHONPATH=$PWD`

**Database errors**
- Run migrations: `alembic upgrade head`
- Check database URL in `.env`
- Ensure write permissions for SQLite file

**API key errors**
- Verify keys are set in `.env`
- Check key validity on provider websites
- Monitor rate limits in admin dashboard

**Spend cap reached**
- Check admin dashboard for usage
- Adjust `MONTHLY_SPEND_CAP_USD` if needed
- Wait for monthly reset or clear ledger for testing

### Logs and Monitoring

- Application logs: `uvicorn app.main:app --log-level info`
- Admin dashboard: Real-time metrics and recent activity
- Health check: `GET /health` endpoint

## Production Deployment

### Security Checklist

- [ ] Change default admin password
- [ ] Use strong secret keys  
- [ ] Enable HTTPS/TLS
- [ ] Use PostgreSQL for database
- [ ] Set up proper logging
- [ ] Monitor spend limits
- [ ] Regular security updates

### Performance Optimization

- Use PostgreSQL instead of SQLite
- Configure reverse proxy (nginx)
- Set up Redis for caching
- Monitor API rate limits
- Optimize database indexes

### Scaling Considerations

- Horizontal scaling with load balancer
- Separate database server
- API gateway for rate limiting
- Monitoring with Prometheus/Grafana

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Run quality checks (`black`, `ruff`, `pytest`)
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
- Check the [troubleshooting section](#troubleshooting)
- Review logs in admin dashboard
- Open an issue with detailed error information

---
