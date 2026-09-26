# OmniVision AI — Modern Sports Predictive Web Dashboard

High-performance, mobile-responsive web dashboard built with **React 18**, **TypeScript**, **Vite**, and **Tailwind CSS**.

## Features

- **Decoupled Architecture**: 0ms server latency, 0 cold starts. Consumes static JSON generated daily by the Python analytics pipeline.
- **Dual Sport Support**: Instant toggle between ⚽ Football (PitchVision) and 🎾 Tennis (CourtVision).
- **Interactive Value Betting**: Filter to "+EV Value Bets Only" with visual EV edge badges and Kelly criterion stakes.
- **Visual Probability Bars**: Side-by-side win probability breakdown with smooth gradients.
- **Verified Results Ledger**: Immutable, officially graded results table tracking Flat PnL, Kelly PnL, and ROI.
- **Mobile-First PWA Layout**: Designed for seamless usage on phones and tablets.

## Quick Start (Local Development)

```bash
cd web
npm install
npm run dev
```

App runs at `http://localhost:3000`.

## Production Build

```bash
cd web
npm run build
```

Generates optimized, minified production assets in `web/dist/`.

## 1-Click Free Deployment

### Vercel (Recommended)
1. Push your repository to GitHub.
2. Go to [Vercel](https://vercel.com) and import the repository.
3. Set **Root Directory** to `web`.
4. Build command: `npm run build`, Output directory: `dist`.
5. Deploy! Zero maintenance, 100% free forever.

### Cloudflare Pages
1. In Cloudflare Dashboard, go to **Workers & Pages** -> **Create application** -> **Pages**.
2. Connect your GitHub repository.
3. Build setting: Framework preset `Vite`, Root directory `web`, Output directory `dist`.
4. Deploy!

