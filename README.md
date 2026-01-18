# Prediction Market Dashboard

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
uv run python -m uvicorn  app.main:app --reload
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
