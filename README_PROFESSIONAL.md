# RANGO: The Ultimate RAG Pipeline Optimizer & Benchmarking Lab

## Overview

RANGO is a comprehensive platform designed to evaluate, optimize, and compare multiple Retrieval-Augmented Generation (RAG) strategies. It allows developers to move beyond vibes-based development by providing empirical data on RAG performance across different indexing and retrieval parameters.

## Core Features

### Multi-Pipeline Benchmarking

Automatically builds and tests four distinct RAG archetypes (Balanced, Fastest, Accurate, DeepSearch) for every document. Each pipeline is optimized for specific use cases and evaluated against consistent performance metrics.

### Advanced Scoring Engine

A proprietary algorithm ranks responses based on:
- Relevance: 35%
- Groundedness: 35%
- Quality: 15%
- Efficiency: 15%

### Hybrid Indexing

Supports two indexing strategies:
- **Vector Database**: Standard ChromaDB integration for semantic similarity search
- **Page Index**: Hierarchical tree-based indexing for complex document traversal and structured navigation

### Real-time Analytics

Track comprehensive metrics including:
- Token usage per query
- USD cost estimation
- Per-stage latency breakdown (Embedding, Retrieval, LLM, Smart Extract)
- Pipeline performance comparison

### Multi-Model Support

Provider-agnostic integration with:
- OpenAI (GPT-4, GPT-3.5-turbo)
- Ollama (local model deployment)
- Custom OpenAI-compatible API endpoints

### Exportable Intelligence

Generate detailed comparison reports in multiple formats:
- PDF with formatted analysis and charts
- CSV for spreadsheet analysis
- JSON for programmatic access
- TXT for documentation

## Technology Stack

### Frontend

```
React (Vite)
TailwindCSS/Vanilla CSS
Chart.js
Lucide React
Supabase Auth
```

### Backend

```
FastAPI (Python)
LangChain
ChromaDB
PyMuPDF
Pydantic
```

### Database & Storage

```
Supabase (PostgreSQL)
Supabase Storage
Local Chroma Collections
```

## RAG Pipelines

RANGO evaluates four distinct RAG pipeline configurations:

| Pipeline | Focus | Chunk Size | Top-K | Use Case |
|----------|-------|-----------|-------|----------|
| Balanced (MMR) | Diversity & Accuracy | 800 | 6 | General-purpose queries |
| Fastest (Similarity) | Low Latency | 500 | 4 | Real-time applications |
| Accurate (Similarity+) | High Recall | 900 | 8 | Comprehensive answers |
| DeepSearch (MMR+) | Complex Queries | 1200 | 10 | Multi-faceted questions |

## Architecture

### Design Pattern

Decoupled Frontend/Backend with Service-Oriented Logic

### Authentication

JWT validation via Supabase JWKS with role-based access control

### Retrieval Flow

```
Document Input
    ↓
Text Chunking
    ↓
Embedding Generation
    ↓
Vector Store Indexing
    ↓
Multi-Strategy Retrieval (4 pipelines)
    ↓
Composite Scoring
    ↓
LLM Response Generation
    ↓
Smart Extraction & Export
```

## Setup Instructions

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Configure environment variables in `.env`:

```
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
OPENAI_API_KEY=your_openai_api_key
```

Start the backend server:

```bash
python main.py
```

### Frontend Setup

```bash
cd frontend
npm install
```

Configure environment variables in `.env`:

```
VITE_SUPABASE_URL=your_supabase_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

Start the development server:

```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

## Directory Structure

### Backend Organization

**backend/core/**
Core RAG pipeline logic, scoring engine, and pipeline preset configurations

**backend/services/**
Analytics computation, batch evaluation workflows, and storage management

**backend/routes/**
Modular API endpoints organized by feature domain

**backend/models.py**
Pydantic data models for request/response validation

**backend/dependencies.py**
Dependency injection and middleware configuration

### Frontend Organization

**frontend/src/components/**
Reusable UI components for data visualization and interactive features

**frontend/src/App.jsx**
Main application shell with routing logic and state management

**frontend/public/**
Static assets including logo and favicons

## Key Features in Detail

### Chat Mode

Interactive mode for streaming RAG conversations with real-time analytics on retrieved documents and response quality.

### Fast Mode

Single-pipeline quick analysis optimized for low-latency responses with focus on speed.

### Compare Mode

Side-by-side comparison of all four RAG pipelines with winner analysis and performance metrics.

### Image Mode

Vision-capable analysis supporting image uploads and visual document understanding.

### Custom Pipeline Configuration

Fine-grained control over retrieval parameters:
- Chunk size: 256-2048 tokens
- Overlap percentage: 0-50%
- Top-K documents: 1-20

### Leaderboard & Analytics

Historical performance tracking with per-query metrics, cost analysis, and pipeline efficiency rankings.

## API Endpoints

Core endpoints (examples):

```
POST /api/chat              Chat interaction endpoint
POST /api/ask              Single-query evaluation
POST /api/compare          Multi-pipeline comparison
POST /api/upload           Document upload handler
GET  /api/analytics        Performance metrics
GET  /api/leaderboard      Historical rankings
```

## Database Schema

Key tables managed via Supabase PostgreSQL:

- `collections`: Document collections and metadata
- `chunks`: Processed text chunks with embeddings
- `evaluations`: Query results and scoring data
- `users`: User profiles and settings
- `analytics`: Aggregated performance metrics

## Performance Considerations

- Vector embeddings cached in ChromaDB for sub-second retrieval
- Batch evaluation support for bulk processing
- Smart extraction caching to reduce redundant LLM calls
- PDF streaming for large document handling

## Contributing

Contributions are welcome. Please ensure:
- Code follows PEP 8 style guidelines (Python)
- Frontend code uses established component patterns
- Changes include relevant tests
- Documentation is updated accordingly

## License

Proprietary - All rights reserved

## Support

For issues, feature requests, or questions, please contact the development team or open an issue in the repository.

---

**Last Updated**: April 2026
**Version**: 1.0.0
