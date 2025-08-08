# MAS Observe UI (Vercel + Together)
Create a Next.js app and wire these envs:
- NEXT_PUBLIC_CONTROL_URL=http://starlord:8088
- NEXT_PUBLIC_CONTROL_KEY=J3cSv/eWIZGNNKaTsnVOlxpYmSPboqLQ9n4LoyB7Hn0=
- TOGETHER_API_KEY=tgp_v1_peF7JytuY7bC2uMRmsZxglftyn4t2Py4YYXYqDwZzMk
Install: `npm i @ai-sdk/togetherai`
Add a page with buttons posting to /jobs/start,/jobs/pause,/qdrant/compact and a chat route using the Together provider.
Deploy with `vercel --prod`. In Vercel → AI tab → add **Together AI** provider.