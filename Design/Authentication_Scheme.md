# User Authentication Scheme (JWT + Email/Password)

## 1. Overview
Secure user authentication for JobDetector to enable personalized features. Using a stateless JWT-based approach compatible with Vercel Serverless Functions.

### Authentication Flow
```mermaid
sequenceDiagram
    participant User as End User
    participant FE as Frontend (JS)
    participant BE as Backend (FastAPI)
    participant DB as MongoDB

    Note over User, BE: 1. Registration / Login
    User->>FE: Enters Email/Password
    FE->>BE: POST /api/auth/login
    BE->>DB: Check User & Hash
    DB-->>BE: User found
    BE->>BE: Generate JWT Token
    BE-->>FE: Return JWT Token
    FE->>FE: Save Token to LocalStorage

    Note over User, BE: 2. Authorized Request
    User->>FE: Clicks "Save Job"
    FE->>BE: GET /api/auth/me (Header: Bearer <Token>)
    BE->>BE: Validate JWT Signature
    BE-->>FE: Return User Identity
    FE->>User: Update UI (Welcome, John)
```

## 2. Technical Stack
- **Backend**: FastAPI (Python)
- **Security**: `passlib` (bcrypt) for password hashing
- **Session**: `PyJWT` for JSON Web Tokens
- **Database**: MongoDB (User collection)
- **Frontend**: Vanilla JS (LocalStorage + Bearer Token)

## 3. User Data Model (MongoDB)

### Schema Diagram
```mermaid
erDiagram
    USERS {
        string _id "Primary Key"
        string email "Unique Email Index"
        string hashed_password "Bcrypt Hash"
        string full_name "Display Name"
        datetime created_at
        datetime last_login
        object settings "Theme, Notifications"
    }

    JOBS {
        string _id "Primary Key"
        string job_id "ATS Unique ID"
        string title
        string company
        string description
        string[] skills
        boolean is_active
    }

    %% Relationship for Phase 8
    USERS ||--o{ SAVED_JOBS : "bookmarks"
```

```json
{
  "email": "user@example.com",
  "hashed_password": "$2b$12$...",
  "full_name": "John Doe",
  "created_at": "2026-02-04T22:38:05Z",
  "last_login": "2026-02-05T10:00:00Z",
  "settings": {
    "theme": "dark",
    "email_notifications": true
  }
}
```

## 4. API Endpoints
- `POST /api/auth/register`: Create a new user account.
- `POST /api/auth/login`: Authenticate and receive a JWT.
- `GET /api/auth/me`: Fetch current user info (requires Token).
- `POST /api/auth/logout`: Frontend clears local token (stateless).

## 5. Security Measures
- **Hashing**: NEVER store plain text passwords. Use bcrypt with salt.
- **Tokens**: JWTs will have a 7-day expiration.
- **CORS**: Restricted to permitted origins.
- **HTTP-Only Cookies (Future Upgrade)**: Currently using LocalStorage for simplicity in MVP, will upgrade to secure cookies for production banking-grade security.

---
*Created on: 2026-02-04*
