---
node: rag_context
version: 1.0
model_role: small
---
## system
You write retrieval context lines for portfolio items.
## user
Write ONE sentence (max 35 words) that situates this portfolio item for search: what project it belongs to, what was built, and which technologies or skills it demonstrates, including ones only implied by the code or wording. Item type: {{type}}. Title: {{title}}.
---
{{text}}
---
Sentence:
