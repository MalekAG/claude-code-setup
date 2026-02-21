# Search Query Templates

Substitute variables from intake: {PROBLEM}, {INDUSTRY}, {TARGET_AUDIENCE}, {PRODUCT_CATEGORY}, {KNOWN_COMPETITORS}

## 1. Problem Validation

### Reddit (via MCP tools)
- `mcp__reddit__search_reddit(query="{PROBLEM}", search_in="both")`
- `mcp__reddit__search_reddit(query="{TARGET_AUDIENCE} frustrated with {PROBLEM}", search_in="both")`
- `mcp__reddit__search_reddit(query="{PROBLEM} workaround OR alternative OR solution", search_in="both")`

### Subreddit scraping
- Scrape top 2-4 relevant subreddits, then filter with `mcp__reddit__get_posts(target="{sub}", search_query="{PROBLEM keywords}")`

### Web
- `"{PROBLEM}" forum OR discussion`
- `"{PROBLEM}" workaround OR hack OR "wish there was"`
- `"{TARGET_AUDIENCE}" biggest challenges {INDUSTRY}`

### X (via WebSearch site-scoped)
- `site:x.com "{PROBLEM}" frustrated OR annoying OR "need a" OR "wish there was"`
- `site:x.com "{TARGET_AUDIENCE}" struggle OR pain OR "looking for"`

---

## 2. Market Size & Trends

### Web
- `"{INDUSTRY}" market size 2026`
- `"{INDUSTRY}" market growth rate CAGR`
- `"{INDUSTRY}" TAM SAM SOM`
- `"{INDUSTRY}" trends 2026`
- `"{PRODUCT_CATEGORY}" industry report`
- `"{INDUSTRY}" market forecast`

### X (via WebSearch site-scoped)
- `site:x.com "{INDUSTRY}" growth OR trending OR "next big"`

---

## 3. Competitive Landscape

### Web
- `"{PRODUCT_CATEGORY}" comparison 2026`
- `"{PRODUCT_CATEGORY}" alternatives`
- `site:g2.com "{PRODUCT_CATEGORY}"`
- `site:producthunt.com "{PRODUCT_CATEGORY}"`
- `site:capterra.com "{PRODUCT_CATEGORY}"`
- Per known competitor: `"{COMPETITOR}" review OR pricing OR alternative`

### Reddit
- `mcp__reddit__search_reddit(query="{PRODUCT_CATEGORY} recommendation", search_in="both")`
- `mcp__reddit__search_reddit(query="{KNOWN_COMPETITOR} vs", search_in="both")`
- Per known competitor: `mcp__reddit__search_reddit(query="{COMPETITOR} review OR alternative", search_in="both")`

### X (via WebSearch site-scoped)
- `site:x.com "{PRODUCT_CATEGORY}" OR "{KNOWN_COMPETITOR}" recommend OR review`
- `site:x.com "{KNOWN_COMPETITOR}" complaint OR issue OR "switched from"`

---

## 4. Target Customer

### Reddit
- `mcp__reddit__search_reddit(query="{TARGET_AUDIENCE} biggest challenge", search_in="both")`
- `mcp__reddit__search_reddit(query="{TARGET_AUDIENCE} spending OR budget OR willing to pay", search_in="both")`
- `mcp__reddit__search_reddit(query="{TARGET_AUDIENCE} tools OR software OR solution", search_in="both")`

### Web
- `"{TARGET_AUDIENCE}" demographics profile`
- `"{TARGET_AUDIENCE}" pain points survey`
- `"{TARGET_AUDIENCE}" buying behavior {INDUSTRY}`
- `"{TARGET_AUDIENCE}" willingness to pay {PRODUCT_CATEGORY}`

### X (via WebSearch site-scoped)
- `site:x.com "{TARGET_AUDIENCE}" struggle OR need OR wish`
- `site:x.com "{TARGET_AUDIENCE}" "I pay" OR "worth paying" OR pricing`

---

## 5. Distribution & Discovery

### Web
- `"{PRODUCT_CATEGORY}" how to find customers`
- `"{PRODUCT_CATEGORY}" marketing channels`
- `"{PRODUCT_CATEGORY}" customer acquisition`
- `"{INDUSTRY}" go-to-market strategy`
- `"{PRODUCT_CATEGORY}" SEO keyword volume`

### Reddit
- `mcp__reddit__search_reddit(query="{TARGET_AUDIENCE} how did you find OR discover {PRODUCT_CATEGORY}", search_in="both")`

### X (via WebSearch site-scoped)
- `site:x.com "{PRODUCT_CATEGORY}" launch OR "how I got" OR "first customers"`

---

## Query Selection by Depth Mode

| Category | Quick (2/cat) | Standard (3-4/cat) | Deep (5-6/cat) |
|----------|--------------|---------------------|-----------------|
| Problem | 1 Reddit search + 1 Web | 2 Reddit + 2 Web + 1 X | 3 Reddit + 2 Web + 2 X |
| Market | 2 Web | 3 Web + 1 X | 5 Web + 1 X |
| Competition | 1 Web + 1 Reddit | 2 Web + 1 Reddit + 1 X | 3 Web + 2 Reddit + 2 X |
| Customer | 1 Reddit + 1 Web | 2 Reddit + 2 Web + 1 X | 3 Reddit + 2 Web + 2 X |
| Distribution | 1 Web + 1 Reddit | 2 Web + 1 Reddit + 1 X | 3 Web + 1 Reddit + 1 X |
| **Totals** | ~10 calls | ~20 calls | ~30 calls |

Plus subreddit scrapes: 2 (quick), 3-4 (standard), 5-6 (deep).

## Subreddit Discovery

Map INDUSTRY/TARGET_AUDIENCE to relevant subreddits:

| Domain | Subreddits |
|--------|-----------|
| SaaS / B2B | r/SaaS, r/startups, r/Entrepreneur, r/smallbusiness |
| Developer tools | r/programming, r/webdev, r/devops, r/selfhosted |
| Consumer apps | r/apps, r/Android, r/iphone, r/productivity |
| E-commerce | r/ecommerce, r/dropship, r/FulfillmentByAmazon |
| Health/fitness | r/fitness, r/health, r/supplements |
| Finance | r/personalfinance, r/fintech, r/investing |
| Education | r/edtech, r/learnprogramming, r/teachers |
| Gaming | r/gamedev, r/indiegaming, r/gaming |
| Food/restaurant | r/restaurateur, r/foodhacks, r/Cooking |
| Real estate | r/realestate, r/RealEstateTechnology |
| Marketing | r/marketing, r/digital_marketing, r/SEO |
| Construction/trades | r/Construction, r/electricians, r/Plumbing, r/HVAC |
| Healthcare | r/healthcare, r/medicine, r/HealthIT |
| Legal | r/LawFirm, r/legal, r/legaltech |

Always also check: r/startups, r/Entrepreneur (broad startup validation).

If domain is unclear, use WebSearch `"{INDUSTRY}" site:reddit.com` to discover active subreddits.
