# AgriAI — AI Agriculture / Environment Intelligence App

A full-stack Next.js 14 application built for the **AI Model Development Contest 2026** (Indian Servers — AI Agriculture / Environment Intelligence App category). It uses **Google Gemini** (image + text reasoning) and **Groq Llama 3** (fast text inference) to power crop disease detection, pest identification, soil health advisory, and a real-time chat assistant — backed by **MongoDB** for users and analysis history.

## ✨ Features

- **Crop Disease Detection** — Upload a photo, get instant diagnosis via Gemini Vision
- **Pest Identification** — Identify pests and get organic/chemical control advice
- **Soil Health Advisor** — Structured form-based soil assessment with AI recommendations
- **AI Advisory Chat** — Real-time chat powered by Groq (fast) or Gemini (deep reasoning)
- **Waste Segregation Assistant** — Photo-based waste sorting guidance
- **Authentication** — Email/password (NextAuth + bcrypt) and optional Google OAuth
- **Dashboard** — Analytics charts (Recharts): activity trends, severity breakdown, category distribution, recent analyses
- **History** — Filterable log of all past AI analyses, stored in MongoDB
- **Settings** — Farm profile, location, crop types, language preference

## 🧱 Tech Stack

| Layer       | Technology                              |
|-------------|------------------------------------------|
| Framework   | Next.js 14 (App Router, TypeScript)      |
| Styling     | Tailwind CSS                              |
| Database    | MongoDB + Mongoose                        |
| Auth        | NextAuth.js (Credentials + Google)        |
| AI (Vision) | Google Gemini 1.5 Flash                   |
| AI (Chat)   | Groq (Llama 3 70B / 8B)                   |
| Charts      | Recharts                                  |
| Icons       | Lucide React                              |

## 🚀 Getting Started

### 1. Install dependencies

```bash
npm install
```

### 2. Configure environment variables

Copy `.env.local.example` to `.env.local` and fill in your keys:

```bash
cp .env.local.example .env.local
```

| Variable | Description | Where to get it |
|---|---|---|
| `MONGODB_URI` | MongoDB connection string | [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) (free tier works) |
| `NEXTAUTH_SECRET` | Random secret for JWT signing | Run `openssl rand -base64 32` |
| `NEXTAUTH_URL` | Your app URL | `http://localhost:3000` for dev |
| `GEMINI_API_KEY` | Google Gemini API key | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `GROQ_API_KEY` | Groq API key | [Groq Console](https://console.groq.com/keys) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | (Optional) Google OAuth | [Google Cloud Console](https://console.cloud.google.com/) |

### 3. Run the development server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### 4. Build for production

```bash
npm run build
npm start
```

## 📂 Project Structure

```
src/
├── app/
│   ├── (auth)/
│   │   ├── login/          # Sign-in page
│   │   ├── register/       # Sign-up page
│   │   └── layout.tsx      # Shared auth visual layout
│   ├── api/
│   │   ├── auth/            # NextAuth + register routes
│   │   ├── analyze/          # Image/text AI analysis (Gemini + Groq)
│   │   ├── chat/              # AI advisory chat
│   │   ├── dashboard/         # Dashboard stats aggregation
│   │   ├── history/            # Analysis history with filters
│   │   └── profile/             # User profile CRUD
│   ├── dashboard/
│   │   ├── page.tsx          # Overview with charts
│   │   ├── scan/               # Crop scanner
│   │   ├── chat/                # AI advisor chat
│   │   ├── soil/                  # Soil health checker
│   │   ├── history/                # Analysis history
│   │   └── settings/                # Profile & preferences
│   ├── layout.tsx
│   ├── page.tsx              # Landing page
│   └── globals.css
├── components/
│   ├── landing/              # Marketing page sections
│   ├── auth/                  # Login/Register forms
│   ├── dashboard/              # Sidebar, charts, scanner, chat, etc.
│   └── ui/                       # Shared UI primitives
├── lib/
│   ├── mongodb.ts            # DB connection (cached)
│   ├── gemini.ts               # Gemini API wrapper
│   ├── groq.ts                  # Groq API wrapper
│   ├── auth.ts                   # Password hashing, JWT helpers
│   └── auth-options.ts            # NextAuth configuration
└── models/
    ├── User.ts                # User schema
    └── Analysis.ts             # Analysis history schema
```

## 🔑 Notes

- The `/dashboard/*` routes are protected via `middleware.ts` — unauthenticated users are redirected to `/login`.
- AI responses are parsed into structured fields (diagnosis, severity, confidence, treatment, prevention, expert advice) using regex on the model's structured output. The full raw response is also stored and viewable.
- For production, ensure `NEXTAUTH_URL` matches your deployed domain and `NEXTAUTH_SECRET` is a strong random value.
