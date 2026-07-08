from typing import Optional
from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

app = FastAPI(title="Orders API")

# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================================
# PART 1 - IDEMPOTENT ORDER CREATION
# ==========================================================

# Stores:
# {
#     "my-key": {"id": 1}
# }
idempotency_store = {}

next_order_id = 1


@app.post("/orders", status_code=201)
def create_order(idempotency_key: str = Header(alias="Idempotency-Key")):
    global next_order_id

    # If this key already exists,
    # return the existing order.
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    # Otherwise create a new order
    order = {
        "id": next_order_id
    }

    idempotency_store[idempotency_key] = order
    next_order_id += 1

    return order


# ==========================================================
# PART 2 - CURSOR PAGINATION
# ==========================================================

TOTAL_ORDERS = 58

catalog = [
    {
        "id": i
    }
    for i in range(1, TOTAL_ORDERS + 1)
]


@app.get("/orders")
def list_orders(limit: int = 10, cursor: Optional[str] = None):
    # Cursor is simply the starting index
    start = int(cursor) if cursor else 0

    items = catalog[start:start + limit]

    if start + limit < len(catalog):
        next_cursor = str(start + limit)
    else:
        next_cursor = None

    return {
        "items": items,
        "next_cursor": next_cursor
    }


# ==========================================================
# PART 3 - RATE LIMITING
# ==========================================================

RATE_LIMIT = 18
WINDOW = 10  # seconds

# Example:
# {
#    "alice":[timestamp1,timestamp2],
#    "bob":[timestamp1]
# }
client_requests = {}


@app.middleware("http")
async def rate_limit(request: Request, call_next):

    client_id = request.headers.get("X-Client-Id", "anonymous")

    now = time.time()

    if client_id not in client_requests:
        client_requests[client_id] = []

    # Remove timestamps older than WINDOW seconds
    client_requests[client_id] = [
        t for t in client_requests[client_id]
        if now - t < WINDOW
    ]

    # Limit reached
    if len(client_requests[client_id]) >= RATE_LIMIT:

        retry_after = WINDOW - (now - client_requests[client_id][0])

        return JSONResponse(
            status_code=429,
            content={
                "detail": "Too Many Requests"
            },
            headers={
                "Retry-After": str(max(1, int(retry_after) + 1))
            }
        )

    # Record this request
    client_requests[client_id].append(now)

    response = await call_next(request)
    return response


# ==========================================================
# HEALTH CHECK
# ==========================================================

@app.get("/")
def root():
    return {
        "message": "Orders API is running."
    }