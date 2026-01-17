# Prediction Market Dashboard

To do list:

[✅] Create basic front end and backend spine so a basic local copy can run

[✅] Create components with resizing widgets

[] Clearly define the FULL backend API

[✅] Implement news fetching from multiple sources

[] Implement market data fetching

[] Implement multiple forms of aggregation (agents, voting, etc)

[] Ensure these things are autoated via agents
  [] Taking in 'search' value and finding similar/more efficient things to search for based on sentiment
  [] Getting search results and aggregating the relevant ones
  [] Same with news
  [] Same with

[] Ensure there's a complete command palette

[] Implement user authentication and settings storage

[] Polish UI/UX design

[] Unit tests

[] Think of a better name for this project

## Requirements

- Make sure you have a correct version of Python installed
- uv: `pip install uv`
- bun: `https://bun.sh/`

Backend:

Download dependencies:

```bash
uv sync
```

Run development server:

(Make sure you navigate to the `backend/` directory first)

```bash
uv run fastapi dev main.py
```

Frontend:

(Make sure you navigate to the `frontend/` directory first)

To install dependencies:

```bash
bun install
```

To start a development server:

```bash
bun dev
```
