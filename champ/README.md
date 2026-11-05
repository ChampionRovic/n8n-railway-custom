# Champ, the autonomous baby goat

Champ is a baby goat at At A Slant Farm who lives his own life and tells you about it. This folder is his brain.

The idea comes from Pino, an autonomous AI bird that lives in a 3D town on the web and took its creator 18 months. We are not cloning that. We are building the cheap version first to find out if the bit is funny, and only then building the version people can watch live.

## What is here

| File | What it is |
|---|---|
| `CHARACTER.md` | Who Champ is. His world, his voice, his running bits, his hard rules, his look. Edit this to change him. |
| `memory/champ.json` | What he remembers. Capped and fading, like Pino. The brain updates it. Don't hand-edit. |
| `brain.mjs` | Runs once a day. Reads the two files above, asks Claude what happened to Champ today, writes the post and updates memory. |
| `out/YYYY-MM-DD.json` | One file per day: the post, his mood, which library tags the media should match, and what changed. This is what n8n picks up. |
| `photos/` | Every unique photo from Donnie's "Goats" and "Farm" Google Photos albums at 1600px, plus `library.json`, which tags who is in each one (`champ`, `ghost`, `red-sweater`, `pigs`, ...) and lists the 79 videos by link. |

## Run it

```bash
cd champ
npm install
npm run dry      # no API call, canned day, proves the pipeline works
npm run day      # live. Needs ANTHROPIC_API_KEY in the environment.
```

The model defaults to Claude Opus 5.5. Override with `CHAMP_MODEL=claude-haiku-5-5` if you want to run him cheap. One post a day on Opus costs well under a dollar a month, so there is no reason to.

## How memory works

Every day each long-term memory loses one point of weight. Memories the day's events touched gain two. New memories enter at six. Anything that hits zero is forgotten, and only the strongest 24 survive. The last seven days are kept as a diary so he doesn't repeat himself. Relationships have a feeling and a strength that drift with events.

This is deliberately simple. It gives him continuity and the ability to forget, which is most of what makes a character feel alive.

## The plan

**Stage 1, now.** Brain plus one post a day to a test Instagram account through n8n. Goal is purely to see whether Champ is funny for two weeks straight. If he isn't, we stop here.

**Stage 2, only if stage 1 lands.** A live web page with a 2D pixel-art pasture where Champ wanders, climbs, screams, and reacts to things visitors leave for him. The brain ticks every minute or so instead of once a day. n8n clips what he did into reels. This is the "life of its own" part people actually share.

**Stage 3, maybe never.** 3D, like Pino. Only if there is an audience that justifies it.

## What Donnie needs to do before stage 1 can post

1. **Create the Instagram account.** The handle will need a tail; `champ` alone is taken everywhere. Something like `champthegoat` or `champatslant`. Make it a Business or Creator account so it can be posted to by API.
2. **Put an Anthropic API key into n8n** as a credential. The brain needs it.
3. ~~Pick the image approach.~~ Settled. Champ is a real goat and every post uses real footage from `photos/library.json`. The brain asks for media by tag; the pipeline picks a matching photo or video. Nothing is generated.

Once those three are answered, the n8n workflow is a schedule trigger, a step that runs the brain, a step that attaches the image, and the Instagram publish step. That gets built next.
