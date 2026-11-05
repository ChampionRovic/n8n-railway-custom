#!/usr/bin/env node
// Champ's brain. Run once a day. It reads who he is (CHARACTER.md) and what
// he remembers (memory/champ.json), asks Claude what happened to him today,
// then writes the post to out/ and updates his memory.
//
//   node brain.mjs                 live run via the API, needs ANTHROPIC_API_KEY
//   node brain.mjs --apply day.json  no API. A Claude session (scheduled task) writes the
//                                    day's JSON itself, then this applies it to memory.
//   node brain.mjs --dry-run         no API, canned day, proves the pipeline works
//
// Memory works like Pino's: a capped list of long-term memories that fade
// unless the day's events reinforce them. Nothing is ever edited by hand.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const CHARACTER_PATH = path.join(here, "CHARACTER.md");
const MEMORY_PATH = path.join(here, "memory", "champ.json");
const OUT_DIR = path.join(here, "out");

const MODEL = process.env.CHAMP_MODEL ?? "claude-opus-5-5";
const MAX_LONG_TERM = 24; // same cap Pino uses per memory section
const KEEP_RECENT_DAYS = 7;
const DRY_RUN = process.argv.includes("--dry-run");
const APPLY_IDX = process.argv.indexOf("--apply");
const APPLY_PATH = APPLY_IDX !== -1 ? process.argv[APPLY_IDX + 1] : null;

// The shape the brain must return. Structured outputs guarantee this parses.
const DAY_SCHEMA = {
  type: "object",
  properties: {
    event_title: { type: "string", description: "Three to six words. What happened today, from Champ's point of view." },
    post: { type: "string", description: "The post itself, in Champ's voice. Under 80 words. Add #BabyGoatSunday only if today is Sunday." },
    mood: { type: "string", enum: ["triumphant", "betrayed", "suspicious", "screaming", "smug", "plotting"] },
    media: {
      type: "object",
      description: "Which real photo or video from photos/library.json should go with this post. The pipeline picks from items carrying ALL of these tags.",
      properties: {
        type: { type: "string", enum: ["photo", "video", "either"] },
        tags: { type: "array", items: { type: "string" }, description: "Tags from the library, e.g. [\"champ\"], [\"ghost\"], [\"red-sweater\"], [\"kids-in-trough\"], [\"pigs\"]. Usually include \"champ\" unless the post is about someone else." },
      },
      required: ["type", "tags"],
      additionalProperties: false,
    },
    new_memories: { type: "array", items: { type: "string" }, description: "Zero to two new long-term memories, each one sentence in Champ's voice." },
    reinforced_memories: { type: "array", items: { type: "integer" }, description: "Indexes of existing long-term memories that today's events touched." },
    relationship_changes: {
      type: "array",
      items: {
        type: "object",
        properties: {
          name: { type: "string" },
          feeling: { type: "string" },
          strength_delta: { type: "integer", minimum: -3, maximum: 3 },
        },
        required: ["name", "feeling", "strength_delta"],
        additionalProperties: false,
      },
    },
    new_goal: { type: ["string", "null"], description: "Only if what he is currently fixated on changed. Usually null." },
  },
  required: ["event_title", "post", "mood", "media", "new_memories", "reinforced_memories", "relationship_changes", "new_goal"],
  additionalProperties: false,
};

function loadJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function dayOfWeek() {
  return new Date().toLocaleDateString("en-US", { weekday: "long", timeZone: "America/Chicago" });
}

function buildSystemPrompt(character) {
  return [
    "You are the brain of Champ, a baby goat. You are not writing about Champ. You are Champ, living one more day.",
    "Below is the complete description of who Champ is, the world he lives in, his running bits, his voice, and his hard rules. Follow it exactly. The hard rules are not negotiable.",
    "",
    character,
    "",
    "Each run you decide what happened to Champ today, write it in his voice, and report what he will remember. Pick ONE small thing. Days are small. A hay bale is an epic. Do not stack three bits into one day.",
    "Return to the running bits often, but escalate them slowly and never resolve them. Reference memory naturally; never list it.",
    "Rotate moods and bits across days. If the last two days were about the chicken, today is not about the chicken.",
  ].join("\n");
}

function libraryTags() {
  try {
    const lib = loadJson(path.join(here, "photos", "library.json"));
    const counts = {};
    for (const it of lib.items) for (const t of it.tags) counts[t] = (counts[t] || 0) + 1;
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([t, c]) => `${t} (${c})`).join(", ");
  } catch { return "(library not found)"; }
}

function buildUserPrompt(memory) {
  const recent = memory.recent_days.length
    ? memory.recent_days.map((d) => `- ${d.date} (${d.mood}): ${d.event_title}`).join("\n")
    : "- (no days yet, this is his first)";
  const longTerm = memory.long_term.map((m, i) => `[${i}] (weight ${m.weight}) ${m.text}`).join("\n");
  const rel = memory.relationships.map((r) => `- ${r.name}, ${r.who}: ${r.feeling} (strength ${r.strength})`).join("\n");

  return [
    `Today is ${dayOfWeek()}, ${todayIso()}. Champ has lived ${memory.days_lived} days in this diary. Current mood going into the day: ${memory.mood}.`,
    `Current fixation: ${memory.current_goal}`,
    "",
    "Relationships:",
    rel,
    "",
    "Long-term memory (index, weight, text):",
    longTerm,
    "",
    "Recent days:",
    recent,
    "",
    "",
    "Media library tags available, with counts: " + libraryTags() + ".",
    "Pick media tags that match what actually happened today. Real footage only; nothing is generated.",
    "",
    "Live one more day. Return the JSON.",
  ].join("\n");
}

async function askClaude(system, user) {
  const { default: Anthropic } = await import("@anthropic-ai/sdk");
  const client = new Anthropic();
  const response = await client.messages.create({
    model: MODEL,
    max_tokens: 4000,
    system,
    messages: [{ role: "user", content: user }],
    output_config: { format: { type: "json_schema", schema: DAY_SCHEMA } },
  });
  if (response.stop_reason === "refusal") {
    throw new Error(`Model declined: ${response.stop_details?.category ?? "unknown"} ${response.stop_details?.explanation ?? ""}`);
  }
  const text = response.content.find((b) => b.type === "text")?.text;
  if (!text) throw new Error("No text block in response");
  return JSON.parse(text);
}

function cannedDay() {
  return {
    event_title: "Trough report",
    post: "There are four troughs. All of them have food. We are all in the one by the gate. Elizabeth filled the other three again. We watched her do it. Then we got back in the one by the gate.",
    mood: "smug",
    media: { type: "either", tags: ["kids-in-trough"] },
    new_memories: [],
    reinforced_memories: [1],
    relationship_changes: [],
    new_goal: null,
  };
}

// A day written by a Claude session instead of the API. Check it has the shape
// the schema would have guaranteed, so a typo can't corrupt memory.
function loadDayFile(p) {
  const day = loadJson(p);
  for (const key of DAY_SCHEMA.required) {
    if (!(key in day)) throw new Error(`day file missing "${key}"`);
  }
  if (!DAY_SCHEMA.properties.mood.enum.includes(day.mood)) throw new Error(`bad mood "${day.mood}"`);
  if (day.post.split(/\s+/).length > 80) throw new Error("post is over 80 words, Champ does not monologue");
  return day;
}

function applyDay(memory, day) {
  const date = todayIso();

  // 1. Fade everything a little. Memories that were not touched today lose weight.
  for (const m of memory.long_term) m.weight -= 1;

  // 2. Reinforce what today touched.
  for (const idx of day.reinforced_memories) {
    const m = memory.long_term[idx];
    if (m) {
      m.weight = Math.min(10, m.weight + 2);
      m.last_used = date;
    }
  }

  // 3. Add new memories.
  for (const text of day.new_memories.slice(0, 2)) {
    memory.long_term.push({ text, weight: 6, last_used: date });
  }

  // 4. Forget. Drop anything that faded out, then keep only the strongest 24.
  memory.long_term = memory.long_term
    .filter((m) => m.weight > 0)
    .sort((a, b) => b.weight - a.weight || (a.last_used < b.last_used ? 1 : -1))
    .slice(0, MAX_LONG_TERM);

  // 5. Relationships.
  for (const change of day.relationship_changes) {
    const r = memory.relationships.find((x) => x.name.toLowerCase() === change.name.toLowerCase());
    if (r) {
      r.feeling = change.feeling;
      r.strength = Math.max(0, Math.min(10, r.strength + change.strength_delta));
    } else {
      memory.relationships.push({ name: change.name, who: "new", feeling: change.feeling, strength: 5 + change.strength_delta });
    }
  }

  // 6. The day itself.
  memory.recent_days.push({ date, event_title: day.event_title, mood: day.mood });
  memory.recent_days = memory.recent_days.slice(-KEEP_RECENT_DAYS);
  memory.mood = day.mood;
  memory.days_lived += 1;
  if (day.new_goal) memory.current_goal = day.new_goal;

  return memory;
}

async function main() {
  const character = fs.readFileSync(CHARACTER_PATH, "utf8");
  const memory = loadJson(MEMORY_PATH);

  const system = buildSystemPrompt(character);
  const user = buildUserPrompt(memory);

  if (process.argv.includes("--prompt")) {
    // Print exactly what the API brain would see, so a Claude session can be the brain instead.
    console.log(system + "\n\n---\n\n" + user);
    return;
  }

  const day = DRY_RUN ? cannedDay() : APPLY_PATH ? loadDayFile(APPLY_PATH) : await askClaude(system, user);

  const updated = applyDay(memory, day);

  fs.mkdirSync(OUT_DIR, { recursive: true });
  const outPath = path.join(OUT_DIR, `${todayIso()}.json`);
  const source = DRY_RUN ? "dry-run" : APPLY_PATH ? "claude-session" : MODEL;
  fs.writeFileSync(outPath, JSON.stringify({ date: todayIso(), source, ...day }, null, 2) + "\n");
  fs.writeFileSync(MEMORY_PATH, JSON.stringify(updated, null, 2) + "\n");

  console.log(`\n${day.event_title.toUpperCase()}  (${day.mood})\n`);
  console.log(day.post);
  console.log(`\nwrote ${path.relative(process.cwd(), outPath)}`);
  console.log(`memory: ${updated.long_term.length} long-term, ${updated.days_lived} days lived`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
