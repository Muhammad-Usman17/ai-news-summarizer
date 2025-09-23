# AI News Summarizer with Multi-Agent Intelligence

A next-generation AI-powered news analysis platform featuring collaborative AI agents, historical data processing, and real-time insights. Built with modern microservices architecture and advanced LLM capabilities.

## ✨ Key Features

### 🤖 **Multi-Agent Collaboration**

- **4 Specialized AI Agents** working together through AutoGen conversations
- **NewsumMarizer**: Creates comprehensive article summaries
- **NewsAnalyst**: Provides deep market and trend analysis
- **QualityReviewer**: Reviews and improves content quality
- **WorkflowCoordinator**: Orchestrates final polished output

### 📅 **Historical Data Processing**

- **Time-Travel News Analysis**: Process news from any historical date
- **Date-Aware Filtering**: Smart timeline filtering by published dates
- **Temporal Workflows**: Robust workflow orchestration with date parameters

### 🎯 **Advanced Analytics**

- **Impact Assessment**: AI-powered evaluation of news significance
- **Trend Analysis**: Multi-article pattern recognition
- **Market Insights**: Financial and business impact evaluation
- **Real-time Streaming**: Live updates via Server-Sent Events

### 🌐 **Modern Frontend**

- **Interactive Timeline**: Date-picker with historical news browsing
- **Real-time Dashboard**: Live job monitoring and results
- **Responsive Design**: Tailwind CSS with modern UI components
- **Workflow Controls**: Easy switching between traditional and multi-agent processing

## 🏗️ Architecture

- **FastAPI**: High-performance REST API with async support
- **Temporal**: Workflow orchestration with historical date handling
- **PostgreSQL**: Advanced relational database with JSON querying
- **Redis Streams**: Real-time event streaming and pub/sub
- **Groq AI**: Ultra-fast LLM inference with multiple model support
- **AutoGen**: Multi-agent conversation framework
- **React + TypeScript**: Modern frontend with type safety
- **Docker**: Containerized microservices architecture

## 🚀 Quick Start

### Development Setup

1. **Clone and setup**:

   ```bash
   git clone <repository>
   cd ai-news-summarizer
   make dev-setup
   ```

2. **Start dependencies**:

   ```bash
   make dev-up
   ```

3. **Configure Environment**:

   ```bash
   # Copy example environment file
   cp .env.example .env

   # Add your Groq API key to .env
   GROQ_API_KEY=your_groq_api_key_here
   ```

4. **Run services locally** (in separate terminals):

   ```bash
   # Terminal 1: API Service
   make dev-run-api

   # Terminal 2: Temporal Worker
   make dev-run-temporal

   # Terminal 3: Frontend (optional)
   cd frontend && pnpm install && pnpm start
   ```

5. **Test the system**:

   ```bash
   # Traditional workflow
   curl -X POST http://localhost:8000/news/run

   # Multi-agent workflow
   curl -X POST http://localhost:8000/news/multi-agent

   # Historical date processing
   curl -X POST "http://localhost:8000/news/run?target_date=2025-09-20"

   # Access Web UI
   open http://localhost:3000
   ```

### Production Deployment

```bash
# Build and deploy production services
make prod-build
make prod-up

# Access services
# API: http://localhost/news/
# Grafana: http://localhost/grafana/ (admin/admin)
# Jaeger: http://localhost/jaeger/
# Temporal: http://localhost/temporal/
```

## 📡 API Endpoints

### 🔄 Workflow Endpoints

- `POST /news/run` - Traditional news workflow
- `POST /news/multi-agent` - Multi-agent collaborative workflow
- `POST /news/run?target_date=YYYY-MM-DD` - Historical date processing

### 📊 Data & Analytics

- `GET /news/timeline` - Combined timeline of articles, summaries, and analyses
- `GET /news/timeline?date=YYYY-MM-DD` - Date-filtered timeline
- `GET /news/articles` - Raw news articles with metadata
- `GET /news/summaries` - AI-generated summaries
- `GET /news/analyses` - Market and trend analyses

### 🚀 Job Management

- `GET /news/stream/{job_id}` - Real-time job updates (SSE)
- `GET /news/jobs/{job_id}` - Job status and progress
- `GET /news/jobs/{job_id}/result` - Complete job results
- `GET /news/jobs` - List recent jobs with filtering

### 🔧 System Endpoints

- `GET /health` - System health check
- `GET /metrics` - Prometheus metrics
- `POST /news/sync-data` - Database synchronization

### 🎯 Example Usage

```bash
# 1. Start a multi-agent workflow with historical date
RESPONSE=$(curl -X POST "http://localhost:8000/news/multi-agent?target_date=2025-09-20")
JOB_ID=$(echo $RESPONSE | jq -r '.job_id')

# 2. Stream real-time updates
curl -N http://localhost:8000/news/stream/$JOB_ID

# 3. Get timeline for specific date
curl "http://localhost:8000/news/timeline?date=2025-09-20" | jq '.'

# 4. Get job results with multi-agent analysis
curl http://localhost:8000/news/jobs/$JOB_ID/result | jq '.multi_agent_results'

# 5. Sync database and get latest counts
curl -X POST http://localhost:8000/news/sync-data | jq '.data_counts'
```

## 🔄 Workflow Processes

### 🤖 Multi-Agent Collaborative Workflow

1. **Smart Scraping**: RSS feed processing with published date extraction
2. **Agent Collaboration**: 4 AI agents working through AutoGen conversations
   - **NewsumMarizer** → Creates initial summary
   - **NewsAnalyst** → Provides market analysis
   - **QualityReviewer** → Reviews and improves quality
   - **WorkflowCoordinator** → Produces final polished output
3. **Database Integration**: Proper foreign key relationships and data integrity
4. **Real-time Streaming**: Live updates via Redis Streams

### 📰 Traditional Workflow

1. **Article Extraction**: Multi-source RSS processing
2. **Groq Summarization**: Ultra-fast LLM summarization
3. **Trend Analysis**: Cross-article pattern recognition
4. **Impact Assessment**: Business and market impact evaluation

### 📅 Historical Processing

- **Exact Date Matching**: Only processes articles published on the exact target date
- **Strict Date Filtering**: Rejects articles without clear published dates for historical requests
- **Multiple Date Sources**: Checks published_parsed, updated_parsed, and created_parsed from RSS feeds
- **Published Date Priority**: Uses actual article publish times over scrape times
- **Temporal Orchestration**: Robust workflow management with date parameter flow

## 🛠️ Available Commands

```bash
# Development
make dev-setup      # Setup development environment
make dev-up         # Start dependencies
make dev-down       # Stop dependencies
make dev-run-api    # Run API service locally
make dev-run-worker # Run Celery worker locally
make dev-run-temporal # Run Temporal worker locally

# Production
make prod-build     # Build containers
make prod-up        # Start production services
make prod-down      # Stop production services
make prod-logs      # Show logs

# Database
make db-upgrade     # Run migrations
make db-downgrade   # Rollback migrations

# Quality & Testing
make test           # Run tests
make lint           # Run linting
make format         # Format code

# Monitoring
make monitor        # Open monitoring dashboards
make clean          # Clean up containers and volumes
```

## 🔧 Configuration

Environment variables in `.env`:

```bash
# Core Configuration
ENVIRONMENT=development
DATABASE_URL=postgresql://newsuser:newspassword@localhost:5432/newsdb
REDIS_URL=redis://localhost:6379/0

# AI & LLM Configuration
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-70b-versatile
GROQ_FALLBACK_MODEL=llama-3.1-8b-instant

# News Sources (RSS Feeds)
RSS_FEEDS=https://feeds.bbci.co.uk/news/rss.xml,https://techcrunch.com/feed/,https://feeds.feedburner.com/oreilly/radar

# Temporal Workflow Engine
TEMPORAL_HOST=localhost:7233
TEMPORAL_NAMESPACE=default

# Multi-Agent Configuration
AUTOGEN_CACHE_SEED=42
AGENT_TIMEOUT=120
MAX_CONVERSATION_TURNS=8

# Observability & Monitoring
JAEGER_ENDPOINT=http://localhost:14268/api/traces
PROMETHEUS_ENABLED=true
LOGGING_LEVEL=INFO
STRUCTURED_LOGGING=true

# Performance Tuning
MAX_CONCURRENT_JOBS=5
ARTICLE_PROCESSING_TIMEOUT=300
DATABASE_POOL_SIZE=10
```

## 📊 Monitoring & Observability

### Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Jaeger**: http://localhost:16686
- **Prometheus**: http://localhost:9090
- **Temporal Web**: http://localhost:8080

### Metrics

- Request/response times
- Job success/failure rates
- LLM response times
- Articles processed
- System resource usage

### Logs

Structured JSON logs with correlation IDs for distributed tracing.

## 🤖 AI Agent System

### 🔍 **ScraperAgent** - Intelligent News Extraction

- **Multi-Source RSS Processing**: BBC, TechCrunch, O'Reilly Radar
- **Strict Date Filtering**: Only fetches articles published exactly on target date
- **Historical Data Support**: Target-date aware scraping with precise date matching
- **Content Extraction**: Full article text with metadata preservation
- **Smart Date Parsing**: Multiple RSS date field fallbacks (published_parsed, updated_parsed, created_parsed)
- **Database Integration**: Proper ID management for foreign key relationships

### 📝 **NewsumMarizer** - Content Summarization Specialist

- **Concise Summarization**: Creates clear, digestible summaries
- **Key Point Extraction**: Bullet-point format for quick scanning
- **Context Preservation**: Maintains important details and nuance
- **Multi-Language Support**: Handles various content types

### 📊 **NewsAnalyst** - Market Intelligence Expert

- **Impact Assessment**: Evaluates business and market implications
- **Trend Analysis**: Identifies patterns across multiple articles
- **Risk Evaluation**: Assesses potential short and long-term effects
- **Industry Insights**: Specialized analysis for different sectors

### 🔎 **QualityReviewer** - Content Quality Assurance

- **Accuracy Review**: Validates information consistency
- **Completeness Check**: Ensures comprehensive coverage
- **Improvement Suggestions**: Recommends enhancements
- **Bias Detection**: Identifies potential content bias

### 🎯 **WorkflowCoordinator** - Final Output Orchestration

- **Content Integration**: Merges insights from all agents
- **Format Standardization**: Creates consistent output structure
- **Quality Finalization**: Produces polished final deliverables
- **Conversation Management**: Orchestrates multi-agent discussions

### 🔄 **MultiAgentProcessor** - Collaboration Engine

- **AutoGen Integration**: Manages agent conversations and interactions
- **Concurrent Processing**: Handles multiple articles simultaneously
- **Error Handling**: Robust fallback mechanisms for reliability
- **Performance Optimization**: Efficient resource utilization

## 🔒 Security & Production

- Non-root container users
- Environment-based configuration
- Health checks and graceful shutdowns
- Rate limiting and timeouts
- Nginx reverse proxy with SSL support

## 🧪 Development

### 📁 Project Structure

```
ai-news-summarizer/
├── app/
│   ├── agents/                    # 🤖 AI Agent System
│   │   ├── scraper_agent.py      # News extraction & RSS processing
│   │   ├── summarizer_agent.py   # Content summarization
│   │   ├── analyst_agent.py      # Market analysis & insights
│   │   ├── multi_agent_processor.py # AutoGen orchestration
│   │   └── simple_multi_agent.py # Lightweight agent coordination
│   ├── config/                   # ⚙️ Configuration Management
│   │   ├── settings.py           # Environment & app settings
│   │   ├── database.py          # PostgreSQL connection & models
│   │   ├── logging.py           # Structured logging setup
│   │   └── telemetry.py         # Observability configuration
│   ├── models/                   # 🗄️ Database Models
│   │   └── news.py              # Articles, summaries, analyses, jobs
│   ├── services/                 # 🔌 External Service Integrations
│   │   ├── groq_client.py       # Groq AI LLM integration
│   │   ├── groq_autogen_client.py # AutoGen + Groq integration
│   │   ├── redis_stream.py      # Real-time event streaming
│   │   ├── temporal_client.py   # Workflow orchestration
│   │   ├── metrics.py           # Prometheus metrics
│   │   └── tracing.py           # Distributed tracing
│   ├── workflows/                # 📋 Temporal Workflows
│   │   ├── news_workflow.py     # Traditional processing workflow
│   │   ├── multi_agent_workflow.py # Multi-agent collaboration
│   │   └── temporal_worker.py   # Temporal worker configuration
│   └── main.py                  # 🚀 FastAPI application & API routes
├── frontend/                     # 🌐 React Frontend
│   ├── src/
│   │   ├── components/          # UI components (Timeline, Settings, etc.)
│   │   ├── api.ts              # Backend API integration
│   │   ├── types.ts            # TypeScript type definitions
│   │   └── App.tsx             # Main application component
│   ├── package.json            # Dependencies & scripts
│   └── tailwind.config.js      # Tailwind CSS configuration
├── observability/               # 📊 Monitoring & Observability
│   ├── grafana/                # Dashboards & data sources
│   ├── prometheus.yml          # Metrics collection config
│   └── loki.yml               # Log aggregation config
├── docker/                     # 🐳 Container Configuration
│   └── temporal/              # Temporal server configuration
├── alembic/                   # 🗃️ Database Migrations
│   └── versions/              # Migration history
├── tests/                     # 🧪 Test Suite
├── docker-compose.dev.yml     # Development environment
├── docker-compose.prod.yml    # Production deployment
├── Makefile                   # 🛠️ Development automation
└── README.md                  # 📖 This comprehensive guide
```

### 🔧 Adding New Features

#### **New AI Agent**

1. Create agent class in `app/agents/new_agent.py`
2. Implement `async def run()` method
3. Add to multi-agent processor participants
4. Update AutoGen conversation flow

#### **New Workflow**

1. Define workflow in `app/workflows/new_workflow.py`
2. Register activities and workflows in `temporal_worker.py`
3. Add API endpoint in `main.py`
4. Update frontend API client

#### **Database Schema Changes**

1. Create migration: `alembic revision --autogenerate -m "description"`
2. Review generated migration in `alembic/versions/`
3. Apply: `make db-upgrade`
4. Update models in `app/models/`

#### **Frontend Enhancement**

1. Add new components in `frontend/src/components/`
2. Update type definitions in `types.ts`
3. Extend API client in `api.ts`
4. Update main application in `App.tsx`

## 📈 Scaling

- **Horizontal**: Scale Celery workers
- **Vertical**: Increase container resources
- **Database**: PostgreSQL connection pooling
- **Cache**: Redis clustering
- **LLM**: Multiple Ollama instances

## 🐛 Troubleshooting

### 🔧 Common Issues & Solutions

#### **🤖 AI & LLM Issues**

- **Groq API errors**: Verify `GROQ_API_KEY` in `.env` file
- **Multi-agent failures**: Check AutoGen conversation parameters and model availability
- **Timeout errors**: Increase `AGENT_TIMEOUT` and `ARTICLE_PROCESSING_TIMEOUT`

#### **🗄️ Database Issues**

- **Connection refused**: Ensure PostgreSQL is running via `make dev-up`
- **Foreign key violations**: Check article ID flow from scraper to processors
- **Migration failures**: Reset with `make db-downgrade` then `make db-upgrade`

#### **🔄 Workflow Issues**

- **Temporal connection**: Verify Temporal server at `localhost:7233`
- **Historical dates not working**: Check target_date parameter flow through workflow chain
- **Job stuck in 'started'**: Monitor workflow logs and check for activity failures

#### **🌐 Frontend Issues**

- **API connection**: Verify backend running on `localhost:8000`
- **Date picker issues**: Check date format (YYYY-MM-DD) and timezone handling
- **Real-time updates**: Ensure Redis streams and SSE connections are working

### 🐛 Debug Commands

```bash
# Service Health Checks
make dev-logs                                    # View all service logs
curl http://localhost:8000/health                # API health check
curl http://localhost:8000/metrics               # Prometheus metrics

# Database Debugging
docker exec -it ai-news-summarizer_postgres_1 psql -U newsuser -d newsdb
make db-upgrade                                  # Apply pending migrations
SELECT * FROM news_jobs ORDER BY created_at DESC LIMIT 5;

# Temporal Workflow Debugging
curl http://localhost:8080                       # Temporal Web UI
docker logs ai-news-summarizer_temporal_1       # Temporal server logs

# Multi-Agent System Testing
curl -X POST "http://localhost:8000/news/multi-agent?target_date=2025-09-20"
curl -N http://localhost:8000/news/stream/{job_id} # Real-time updates

# Frontend Development
cd frontend && pnpm dev                          # Development server
pnpm build && pnpm preview                      # Production build test

# Redis & Streaming
redis-cli -h localhost -p 6379 monitor          # Monitor Redis commands
curl -N http://localhost:8000/news/stream/test  # Test SSE connection
```

## 📄 License

MIT License - see LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Run tests: `make test`
4. Submit pull request

---

## 🚀 Recent Updates & Features

### ✅ **Latest Enhancements (v2.0)**

- **Multi-Agent Collaboration**: 4 specialized AI agents working through AutoGen
- **Historical Data Processing**: Target any date for news analysis
- **Enhanced Timeline**: Smart date filtering with published date priority
- **Foreign Key Integrity**: Proper database relationships and data consistency
- **Real-time Frontend**: Interactive React dashboard with live updates
- **Groq Integration**: Ultra-fast LLM inference replacing local Ollama
- **Improved Error Handling**: Robust fallback mechanisms and retry logic

### 🔮 **Roadmap**

- [ ] **Advanced Analytics Dashboard**: Trend visualization and insights
- [ ] **Multi-Language Support**: International news sources and processing
- [ ] **Sentiment Analysis**: Emotional tone analysis of news content
- [ ] **API Rate Limiting**: Enhanced security and usage controls
- [ ] **Webhook Notifications**: External system integration capabilities
- [ ] **Mobile App**: Native mobile application for news consumption

---

Built with ❤️ using **FastAPI** • **Temporal** • **Groq AI** • **AutoGen** • **PostgreSQL** • **React** • **TypeScript**

_Transforming news consumption through collaborative AI intelligence_
