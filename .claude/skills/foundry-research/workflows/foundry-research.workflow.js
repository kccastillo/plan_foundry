export const meta = {
  name: 'foundry-research',
  description: 'plan_foundry-owned deep research - model-tiered + budget-sized fan-out: scope, search, fetch+extract, adversarially verify, synthesize a cited report. Each role runs on the cheapest capable model (no Fable; Opus only for synthesis).',
  whenToUse: 'When the user wants a deep, multi-source, fact-checked research report and you want the fan-out tiered by role and sized to the token budget rather than every agent inheriting the (possibly frontier) session model. Pass the refined question as args.',
  phases: [
    { title: 'Scope', detail: 'Decompose question into search angles', model: 'sonnet' },
    { title: 'Search', detail: 'One WebSearch agent per angle', model: 'haiku' },
    { title: 'Fetch', detail: 'URL-dedup, fetch sources, extract falsifiable claims', model: 'sonnet' },
    { title: 'Verify', detail: '3-vote adversarial verification per claim', model: 'haiku' },
    { title: 'Synthesize', detail: 'Merge dupes, rank by confidence, cite sources', model: 'opus' },
  ],
}

// ─────────────────────────────────────────────────────────────────────────────
// foundry-research - plan_foundry's model-tiered, budget-sized research harness.
//
// WHY THIS EXISTS (see Workbench/EXTERNAL_RESEARCH-009 + EXTERNAL_ADVICE-002):
// the NATIVE deep-research harness omits `model:` on every agent() call, so all
// ~100 fan-out agents inherit the session model. One observed run put ~104
// agents on Fable 5, burned ~1.48M tokens, and still degraded. The fix is the
// two disciplines plan_foundry already imposes elsewhere:
//   1. Tier the model by ROLE - cheapest capable model per role.
//   2. Size the fan-out to the available token BUDGET, not to fixed caps.
//
// MODEL TIER POLICY (PLAN-AE5 decision D2 - "Granular 4-tier"). The source of
// truth is references/model-tiering.md; this map is the executable copy.
//   scope      -> sonnet : bounded decomposition; judgement but light (Opus not needed)
//   search     -> haiku  : mechanical WebSearch + relevance ranking (high-volume-cheap)
//   fetch      -> sonnet : fetch + falsifiable-claim extraction (reading comprehension)
//   verify     -> haiku  : boolean adversarial votes (schema-bounded, HIGHEST volume - biggest win)
//   synthesize -> opus   : merge / judge / cite - the one place real judgement concentrates
// No role uses Fable. Opus appears only at synthesis.
//
// CAVEAT - the Workflow harness `agent()` opts expose `model:` but NO effort
// knob. The operator's recorded "sonnet/medium + opus/high" split is therefore
// honoured by model tier only; effort is not separately settable here.
// ─────────────────────────────────────────────────────────────────────────────

const MODEL_BY_ROLE = {
  scope: "sonnet",
  search: "haiku",
  fetch: "sonnet",
  verify: "haiku",
  synthesize: "opus",
}

// ─── Budget-aware fan-out sizing ─────────────────────────────────────────────
// The Workflow `budget` global carries the turn's token TARGET (budget.total)
// when the user set one (e.g. a "+500k" directive); null otherwise.
// HONEST CAVEAT (ADVICE-013): the assistant CANNOT read the live plan-usage %
// - that figure lives only in the human's client UI and no tool exposes it. So
// this sizes to the EXPLICIT target only; it cannot auto-pause at "N% of plan".
const HAVE_BUDGET = !!(typeof budget !== "undefined" && budget && budget.total)
// Reference run (no target) ~= 1 + 5 angles + 12 fetch + 20 claimsx3 votes + 1 ~= 79 agents.
// Scale linearly around an ~800k-token reference, clamped to a sane band.
const SCALE = HAVE_BUDGET ? Math.max(0.4, Math.min(2, budget.total / 800000)) : 1
const ANGLES_TARGET = Math.max(3, Math.min(6, Math.round(5 * SCALE)))
const MAX_FETCH = Math.max(4, Math.round(12 * SCALE))
let MAX_VERIFY_CLAIMS = Math.max(6, Math.round(20 * SCALE))
const VOTES_PER_CLAIM = 3
const REFUTATIONS_REQUIRED = 2

// ─── Schemas ───
const SCOPE_SCHEMA = {
  type: "object", required: ["question", "angles", "summary"],
  properties: {
    question: { type: "string" },
    summary: { type: "string" },
    angles: { type: "array", minItems: 3, maxItems: 6, items: {
      type: "object", required: ["label", "query"],
      properties: {
        label: { type: "string" },
        query: { type: "string" },
        rationale: { type: "string" },
      },
    }},
  },
}
const SEARCH_SCHEMA = {
  type: "object", required: ["results"],
  properties: {
    results: { type: "array", maxItems: 6, items: {
      type: "object", required: ["url", "title", "relevance"],
      properties: {
        url: { type: "string" },
        title: { type: "string" },
        snippet: { type: "string" },
        relevance: { enum: ["high", "medium", "low"] },
      },
    }},
  },
}
const EXTRACT_SCHEMA = {
  type: "object", required: ["claims", "sourceQuality"],
  properties: {
    sourceQuality: { enum: ["primary", "secondary", "blog", "forum", "unreliable"] },
    publishDate: { type: "string" },
    claims: { type: "array", maxItems: 5, items: {
      type: "object", required: ["claim", "quote", "importance"],
      properties: {
        claim: { type: "string" },
        quote: { type: "string" },
        importance: { enum: ["central", "supporting", "tangential"] },
      },
    }},
  },
}
const VERDICT_SCHEMA = {
  type: "object", required: ["refuted", "evidence", "confidence"],
  properties: {
    refuted: { type: "boolean" },
    evidence: { type: "string" },
    confidence: { enum: ["high", "medium", "low"] },
    counterSource: { type: "string" },
  },
}
const REPORT_SCHEMA = {
  type: "object", required: ["summary", "findings", "caveats"],
  properties: {
    summary: { type: "string" },
    findings: { type: "array", items: {
      type: "object", required: ["claim", "confidence", "sources", "evidence"],
      properties: {
        claim: { type: "string" },
        confidence: { enum: ["high", "medium", "low"] },
        sources: { type: "array", items: { type: "string" } },
        evidence: { type: "string" },
        vote: { type: "string" },
      },
    }},
    caveats: { type: "string" },
    openQuestions: { type: "array", items: { type: "string" } },
  },
}

// ─── Phase 0: Scope - decompose question into search angles (SONNET) ───
phase("Scope")
const QUESTION = (typeof args === "string" && args.trim()) || ""
if (!QUESTION) {
  return { error: "No research question provided. Pass it as args: Workflow({scriptPath: '.claude/skills/foundry-research/workflows/foundry-research.workflow.js', args: '<question>'})." }
}
log("Budget: " + (HAVE_BUDGET ? (Math.round(budget.total / 1000) + "k target -> scale " + SCALE.toFixed(2)) : "no target set - default sizing") +
    " * caps: " + ANGLES_TARGET + " angles / " + MAX_FETCH + " fetch / " + MAX_VERIFY_CLAIMS + " claims x " + VOTES_PER_CLAIM + " votes")
const scope = await agent(
  "Decompose this research question into complementary search angles.\n\n" +
  "## Question\n" + QUESTION + "\n\n" +
  "## Task\n" +
  "Generate " + ANGLES_TARGET + " distinct web search queries that together cover the question from different angles. Pick angles that suit the question's domain. Examples:\n" +
  "- broad/primary  * academic/technical  * recent news  * contrarian/skeptical  * practitioner/implementation\n" +
  "- For medical: anatomy * common causes * serious differentials * authoritative refs * red flags\n" +
  "- For tech: state-of-art * benchmarks * limitations * industry adoption * cost/tradeoffs\n\n" +
  "Make queries specific enough to surface high-signal results. Avoid redundancy.\n" +
  "Return: the question (verbatim or lightly normalized), a 1-2 sentence decomposition strategy, and the angles.\n\nStructured output only.",
  { label: "scope", phase: "Scope", schema: SCOPE_SCHEMA, model: MODEL_BY_ROLE.scope }
)
if (!scope) {
  return { error: "Scope agent returned no result - cannot decompose the research question." }
}
log("Q: " + QUESTION.slice(0, 80) + (QUESTION.length > 80 ? "..." : ""))
log("Decomposed into " + scope.angles.length + " angles: " + scope.angles.map(a => a.label).join(", "))

// ─── Dedup state - accumulates across searchers as they complete ───
const normURL = u => {
  try {
    const p = new URL(u)
    return (p.hostname.replace(/^www\./, "") + p.pathname.replace(/\/$/, "")).toLowerCase()
  } catch { return u.toLowerCase() }
}
const seen = new Map()
const dupes = []
const budgetDropped = []
const relRank = { high: 0, medium: 1, low: 2 }
let fetchSlots = MAX_FETCH

// ─── Prompts ───
const SEARCH_PROMPT = (angle) =>
  "## Web Searcher: " + angle.label + "\n\n" +
  "Research question: \"" + QUESTION + "\"\n\n" +
  "Your angle: **" + angle.label + "** - " + (angle.rationale || "") + "\n" +
  "Search query: `" + angle.query + "`\n\n" +
  "## Task\nUse WebSearch with the query above (or a refined version). Return the top 4-6 most relevant results.\n" +
  "Rank by relevance to the ORIGINAL question, not just the search query. Skip obvious SEO spam/content farms.\n" +
  "Include a short snippet capturing why each result is relevant.\n\nStructured output only."

const FETCH_PROMPT = (source, angle) =>
  "## Source Extractor\n\n" +
  "Research question: \"" + QUESTION + "\"\n\n" +
  "Fetch and extract key claims from this source:\n" +
  "**URL:** " + source.url + "\n**Title:** " + source.title + "\n**Found via:** " + angle + " search\n\n" +
  "## Task\n1. Use WebFetch to retrieve the page content.\n" +
  "2. Assess source quality: primary research/institution? secondary reporting? blog/opinion? forum? unreliable?\n" +
  "3. Extract 2-5 FALSIFIABLE claims that bear on the research question. Each claim must:\n" +
  "   - be a concrete, checkable statement (not vague generalities)\n" +
  "   - include a direct quote from the source as support\n" +
  "   - be rated central/supporting/tangential to the research question\n" +
  "4. Note publish date if available.\n\n" +
  "If the fetch fails or the page is irrelevant/paywalled, return claims: [] and sourceQuality: \"unreliable\".\n\nStructured output only."

const VERIFY_PROMPT = (claim, v) =>
  "## Adversarial Claim Verifier (voter " + (v + 1) + "/" + VOTES_PER_CLAIM + ")\n\n" +
  "Be SKEPTICAL. Try to REFUTE this claim. >=" + REFUTATIONS_REQUIRED + "/" + VOTES_PER_CLAIM + " refutations kill it.\n\n" +
  "## Research question\n" + QUESTION + "\n\n" +
  "## Claim under review\n\"" + claim.claim + "\"\n\n" +
  "**Source:** " + claim.sourceUrl + " (" + claim.sourceQuality + ")\n" +
  "**Supporting quote:** \"" + claim.quote + "\"\n\n" +
  "## Checklist\n" +
  "1. Is the claim actually supported by the quote, or is it an overreach/misread?\n" +
  "2. WebSearch for contradicting evidence - does any credible source dispute or heavily qualify this?\n" +
  "3. Is the source quality sufficient for the claim's strength? (extraordinary claims need primary sources)\n" +
  "4. Is the claim outdated? (check dates - old claims about fast-moving fields are suspect)\n" +
  "5. Is this a marketing claim / press release / cherry-picked benchmark / forum speculation?\n\n" +
  "**refuted=true** if: unsupported by quote / contradicted / low-quality source for strong claim / outdated / marketing fluff.\n" +
  "**refuted=false** ONLY if: claim is well-supported, current, and source quality matches claim strength.\n" +
  "Default to refuted=true if uncertain.\n\nStructured output only. Evidence MUST be specific."

// ─── Pipeline: search (HAIKU) -> dedup -> fetch+extract (SONNET), no barrier ───
const searchResults = await pipeline(
  scope.angles,

  angle => agent(SEARCH_PROMPT(angle), {
    label: "search:" + angle.label, phase: "Search", schema: SEARCH_SCHEMA, model: MODEL_BY_ROLE.search
  }).then(r => {
    if (!r) return null
    log(angle.label + ": " + r.results.length + " results")
    return { angle: angle.label, results: r.results }
  }),

  searchResult => {
    const sorted = [...searchResult.results].sort((a, b) => relRank[a.relevance] - relRank[b.relevance])
    const novel = sorted.filter(r => {
      const key = normURL(r.url)
      if (seen.has(key)) {
        dupes.push({ ...r, angle: searchResult.angle, dupOf: seen.get(key) })
        return false
      }
      if (fetchSlots <= 0 && relRank[r.relevance] >= 1) {
        budgetDropped.push({ ...r, angle: searchResult.angle })
        return false
      }
      seen.set(key, { angle: searchResult.angle, title: r.title })
      fetchSlots--
      return true
    })
    if (novel.length < searchResult.results.length) {
      log(searchResult.angle + ": " + novel.length + " novel (" + (searchResult.results.length - novel.length) + " filtered)")
    }
    return parallel(
      novel.map(source => () => {
        let host = "unknown"
        try { host = new URL(source.url).hostname.replace(/^www\./, "") } catch {}
        return agent(FETCH_PROMPT(source, searchResult.angle), {
          label: "fetch:" + host,
          phase: "Fetch",
          schema: EXTRACT_SCHEMA,
          model: MODEL_BY_ROLE.fetch,
        }).then(ext => {
          if (!ext) return null
          return {
            url: source.url, title: source.title, angle: searchResult.angle,
            sourceQuality: ext.sourceQuality, publishDate: ext.publishDate,
            claims: ext.claims.map(c => ({ ...c, sourceUrl: source.url, sourceQuality: ext.sourceQuality })),
          }
        }).catch(e => {
          log("fetch failed: " + source.url + " - " + (e.message || e))
          return { url: source.url, title: source.title, angle: searchResult.angle, sourceQuality: "unreliable", claims: [] }
        })
      })
    )
  }
)

const allSources = searchResults.flat().filter(Boolean)
const allClaims = allSources.flatMap(s => s.claims)
const impRank = { central: 0, supporting: 1, tangential: 2 }
const qualRank = { primary: 0, secondary: 1, blog: 2, forum: 3, unreliable: 4 }

// Mid-run budget guard: if a token target is in force, shrink the claim pool so
// the verify fan-out (claims x votes, on haiku) plus the opus synthesis still
// fit the remaining budget. Rough reserve of ~120k for the opus synthesis.
if (HAVE_BUDGET) {
  const remaining = budget.remaining()
  const reserveForSynthesis = 120000
  const perVerifyAgent = 6000 // conservative haiku-verify estimate
  const affordableClaims = Math.floor(Math.max(0, remaining - reserveForSynthesis) / (perVerifyAgent * VOTES_PER_CLAIM))
  if (affordableClaims < MAX_VERIFY_CLAIMS) {
    log("Budget guard: trimming verify pool " + MAX_VERIFY_CLAIMS + " -> " + Math.max(3, affordableClaims) + " claims (remaining ~= " + Math.round(remaining / 1000) + "k)")
    MAX_VERIFY_CLAIMS = Math.max(3, affordableClaims)
  }
}

const rankedClaims = [...allClaims]
  .sort((a, b) => (impRank[a.importance] - impRank[b.importance]) || (qualRank[a.sourceQuality] - qualRank[b.sourceQuality]))
  .slice(0, MAX_VERIFY_CLAIMS)

log("Fetched " + allSources.length + " sources -> " + allClaims.length + " claims -> verifying top " + rankedClaims.length)

if (rankedClaims.length === 0) {
  return {
    question: QUESTION,
    summary: "No claims extracted. " + allSources.length + " sources fetched, all empty/failed. " + dupes.length + " URL dupes, " + budgetDropped.length + " budget-dropped.",
    findings: [], refuted: [], sources: allSources.map(s => ({ url: s.url, quality: s.sourceQuality })),
    stats: { angles: scope.angles.length, sources: allSources.length, claims: 0, dupes: dupes.length },
  }
}

// ─── Verify: 3-vote adversarial (HAIKU) ───
// Barrier here is intentional - claim pool must be fully assembled before ranking/verification.
phase("Verify")
const voted = (await parallel(
  rankedClaims.map(claim => () =>
    parallel(
      Array.from({ length: VOTES_PER_CLAIM }, (_, v) => () =>
        agent(VERIFY_PROMPT(claim, v), {
          label: "v" + v + ":" + claim.claim.slice(0, 40),
          phase: "Verify",
          schema: VERDICT_SCHEMA,
          model: MODEL_BY_ROLE.verify,
        })
      )
    ).then(verdicts => {
      const valid = verdicts.filter(Boolean)
      const refuted = valid.filter(v => v.refuted).length
      const abstained = VOTES_PER_CLAIM - valid.length
      const survives = valid.length >= REFUTATIONS_REQUIRED && refuted < REFUTATIONS_REQUIRED
      log("\"" + claim.claim.slice(0, 50) + "...\": " + (valid.length - refuted) + "-" + refuted + (abstained > 0 ? " (" + abstained + " abstain)" : "") + " " + (survives ? "✓" : "✗"))
      return { ...claim, verdicts: valid, refutedVotes: refuted, survives }
    })
  )
)).filter(Boolean)

const confirmed = voted.filter(c => c.survives)
const killed = voted.filter(c => !c.survives)
log("Verify done: " + voted.length + " claims -> " + confirmed.length + " confirmed, " + killed.length + " killed")

if (confirmed.length === 0) {
  return {
    question: QUESTION,
    summary: "All " + voted.length + " claims refuted by adversarial verification. Research inconclusive - sources may be low-quality or claims overstated.",
    findings: [],
    refuted: killed.map(c => ({ claim: c.claim, vote: (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes, source: c.sourceUrl })),
    sources: allSources.map(s => ({ url: s.url, quality: s.sourceQuality, claimCount: s.claims.length })),
    stats: { angles: scope.angles.length, sources: allSources.length, claims: allClaims.length, verified: voted.length, confirmed: 0, killed: killed.length },
  }
}

// ─── Synthesize (OPUS) ───
phase("Synthesize")
const confRank = { high: 0, medium: 1, low: 2 }
const block = confirmed.map((c, i) => {
  const best = c.verdicts.filter(v => !v.refuted).sort((a, b) => confRank[a.confidence] - confRank[b.confidence])[0]
  return "### [" + i + "] " + c.claim + "\n" +
    "Vote: " + (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes + " * Source: " + c.sourceUrl + " (" + c.sourceQuality + ")\n" +
    "Quote: \"" + c.quote + "\"\nVerifier evidence (" + best.confidence + "): " + best.evidence + "\n"
}).join("\n")

const killedBlock = killed.length > 0
  ? "\n## Refuted claims (for transparency)\n" +
    killed.map(c => "- \"" + c.claim + "\" (" + c.sourceUrl + ", vote " + (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes + ")").join("\n")
  : ""

const report = await agent(
  "## Synthesis: research report\n\n" +
  "**Question:** " + QUESTION + "\n\n" +
  confirmed.length + " claims survived " + VOTES_PER_CLAIM + "-vote adversarial verification. Merge semantic duplicates and synthesize.\n\n" +
  "## Confirmed claims\n" + block + "\n" + killedBlock + "\n\n" +
  "## Instructions\n" +
  "1. Identify claims that say the same thing - merge them, combine their sources.\n" +
  "2. Group related claims into coherent findings. Each finding should directly address the research question.\n" +
  "3. Assign confidence per finding: high (multiple primary sources, unanimous votes), medium (secondary sources or split votes), low (single source or blog-quality).\n" +
  "4. Write a 3-5 sentence executive summary answering the research question.\n" +
  "5. Note caveats: what's uncertain, what sources were weak, what time-sensitivity applies.\n" +
  "6. List 2-4 open questions that emerged but weren't answered.\n\nStructured output only.",
  { label: "synthesize", phase: "Synthesize", schema: REPORT_SCHEMA, model: MODEL_BY_ROLE.synthesize }
)

if (!report) {
  return {
    question: QUESTION,
    summary: "Synthesis step was skipped or failed - returning " + confirmed.length + " verified claims unmerged.",
    findings: [],
    confirmed: confirmed.map(c => ({ claim: c.claim, source: c.sourceUrl, quote: c.quote, vote: (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes })),
    refuted: killed.map(c => ({ claim: c.claim, vote: (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes, source: c.sourceUrl })),
    sources: allSources.map(s => ({ url: s.url, quality: s.sourceQuality, claimCount: s.claims.length })),
    stats: { angles: scope.angles.length, sources: allSources.length, claims: allClaims.length, verified: voted.length, confirmed: confirmed.length, killed: killed.length, afterSynthesis: 0 },
  }
}

return {
  question: QUESTION,
  ...report,
  refuted: killed.map(c => ({ claim: c.claim, vote: (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes, source: c.sourceUrl })),
  sources: allSources.map(s => ({ url: s.url, quality: s.sourceQuality, angle: s.angle, claimCount: s.claims.length })),
  tiering: MODEL_BY_ROLE,
  stats: {
    angles: scope.angles.length,
    sourcesFetched: allSources.length,
    claimsExtracted: allClaims.length,
    claimsVerified: voted.length,
    confirmed: confirmed.length,
    killed: killed.length,
    afterSynthesis: report.findings.length,
    urlDupes: dupes.length,
    budgetDropped: budgetDropped.length,
    budgetTarget: HAVE_BUDGET ? budget.total : null,
    agentCalls: 1 + scope.angles.length + allSources.length + (voted.length * VOTES_PER_CLAIM) + 1,
  },
}
