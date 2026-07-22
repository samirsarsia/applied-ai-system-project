# PawPal+ Project Reflection

## 1. System Design

**Core user actions**

When I read the scenario, I boiled PawPal+ down to three things a user really
needs to do:

1. **Set up who the plan is for** — add themselves as the owner and add their
   pet(s), including basic info and any preferences. This is the starting point
   for everything else.

2. **Add the care tasks** — the walks, feedings, meds, grooming, and so on, with
   at least a duration and a priority. This is the pool of stuff the assistant
   gets to work with.

3. **Get today's plan** — ask PawPal+ to build a daily schedule, then see it laid
   out clearly with a short reason for why each task landed where it did.

Everything I built afterward traces back to one of these three actions.

**a. Initial design**

My first UML draft (`diagrams/uml_draft.mmd`) used four classes, and I tried to
give each one a single, obvious job.

**Task** is one piece of pet care — the walk, the feeding, the meds. It holds the
title, how long it takes, its priority, and an optional preferred time, plus two
small helpers: `priority_score()` for sorting and `fits_within()` to check it
against the time left. I made it a dataclass because it's really just a data
record.

**Pet** is the animal. It knows its name and species and keeps the list of its
own tasks (`add_task`, `remove_task`, `list_tasks`). Also a dataclass.

**Owner** is the person. It holds the name, how many minutes they have in the
day, their preferences, and the list of pets they're responsible for. Its whole
reason to exist is to capture the human side of the constraints — time and
preferences — and to own the pets. Dataclass again.

**Scheduler** is the odd one out, and on purpose. It's a plain class, not a
dataclass, because it's *behavior*, not data. It takes the owner and their pets
and turns all of that into an ordered plan (`sort_tasks`, `filter_tasks`,
`build_plan`). I kept the actual scheduling logic here, out of the data classes,
so the algorithm would be isolated and easy to test on its own.

The relationships are straightforward: an owner owns many pets, a pet has many
tasks, and the scheduler reads all of that to produce a plan. Early on I toyed
with separate `Plan` and `ScheduledTask` classes, but that felt like
over-engineering for this project, so I dropped them. `build_plan()` just returns
a list of dicts, which turned out to be easy both to show in Streamlit and to
assert on in tests.

**b. Design changes**

The design definitely changed once I started building. After I had the skeleton,
I asked my AI assistant to look over `pawpal_system.py` for missing
relationships or logic bottlenecks, and two of its points actually changed how I
built things.

The first was that my scheduler was ignoring a relationship I'd already put in
the model. I'd written `Scheduler(owner, pet, ...)`, which locks it to one pet —
even though an owner can have a whole list of them. So someone with a dog *and* a
cat couldn't get a single combined plan. I switched the scheduler to be
owner-scoped (`Scheduler(owner, ...)`) and added `collect_tasks()` to pull tasks
from every pet the owner has. That matches how a real owner thinks about their
day — the whole household, not one animal at a time — and I tagged each plan
entry with its pet so the output stays clear when tasks come from different pets.

The second was that I had no anchor for real clock times. `build_plan()` was
supposed to return start and end times, but nothing said when the day actually
starts, so those times were meaningless. I added a `day_start` parameter
(defaulting to `"08:00"`). I put it on the Scheduler rather than the Owner
because the start time feels like a property of the planning run, not of the
person.

I didn't take every suggestion, though. The review also wanted me to lock down
`priority` with an Enum right away, and while that's a reasonable idea, I didn't
want to complicate an empty skeleton for it. I came back to it later with a
shared `PRIORITY_ORDER` constant plus validation, which got me the safety without
the ceremony.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

The scheduler juggles a handful of constraints. The **time budget** is the big
one — `filter_tasks()` greedily drops anything that won't fit, so the plan never
promises more than the owner's available minutes. **Priority** (low/medium/high)
decides ordering: high-priority tasks go first so they never get squeezed out by
minor ones. **Duration** breaks ties — shorter tasks first, which quietly lets
more of them fit in the same window. On top of that, completed tasks get skipped,
preferred times feed the chronological view and conflict checks, and frequency
drives the recurring-task logic.

If I had to name what mattered most, it's time and priority. They map straight
onto the actual problem: a busy owner with not enough time who can't afford to
miss the important stuff. When something has to give, I wanted it to be a
low-priority task, never the medication. Preferred times and preferences are nice,
but they're secondary — I wasn't willing to trade away the guarantee that the
important tasks fit the budget just to honor a preferred slot. That priority
ranking is basically what shaped the whole greedy algorithm.

**b. Tradeoffs**

The clearest tradeoff is that `build_plan()` packs tasks back-to-back from the
day's start, ordered by priority and duration, instead of actually placing them
at their preferred times. Conflict detection *does* look at preferred times — it
flags overlapping slots through `detect_conflicts()` — but the plan itself still
just lines tasks up one after another. So PawPal+ can warn you that the 08:00
walk and the 08:00 vet call collide, and then turn around and schedule them
sequentially anyway, without pinning either one to 08:00 or resolving the clash.

I think that's a fair tradeoff here. The core promise is "fit the most important
care into the time I have today," and a busy owner mostly cares that nothing
important gets dropped and the total fits their day. A greedy priority fit does
that simply and predictably. Actually honoring every preferred time turns this
into a much harder scheduling problem — gaps, bumping lower-priority tasks,
deciding what happens when two things both insist on happening *right now*. By
splitting the cheap, useful part (detecting conflicts) from the genuinely hard
part (resolving them), I kept the tool understandable and still gave the owner
enough information to adjust things themselves. Real time-based placement is an
obvious next step, but I left it out on purpose rather than by accident.

There's a smaller tradeoff too: I kept `detect_conflicts()` as a plain indexed
loop instead of the denser one-liner comprehension the AI suggested. The
comprehension was arguably more "Pythonic," but it was harder to read, and since
both run the same speed, I'd rather have code I can actually follow when
something breaks.

---

## 3. AI Collaboration

**a. How you used AI**

I leaned on my AI assistant through the whole project, but in pretty different
ways at different stages. Early on it was a brainstorming partner — helping me
land on the four-class model and sketch the first UML from the scenario. Then it
became a scaffolder, turning that UML into class skeletons and dataclass stubs.
During implementation it helped me actually write the trickier bits, like
`sort_by_time()`, the `timedelta`-based `next_occurrence()`, and
`detect_conflicts()`. Later it flipped into more of a reviewer — I'd ask "how
could this be simpler?" or have it scan a file for problems — and finally it
helped me draft the test suite and think through edge cases.

A few features stood out as genuinely useful. Multi-file editing mattered when a
change spanned layers — adding recurrence touched both the model and the UI, and
having both updated together saved a lot of back-and-forth. Inline chat on a
single method was great for small, specific questions, like how to use a lambda
key to sort "HH:MM" strings. And the "review this whole file" prompts caught
things I just hadn't thought about. The biggest thing I learned about *prompting*
is that narrow, concrete questions worked way better than vague ones — "how
should the Scheduler get tasks from the owner's pets?" got me somewhere, while
"make this better" mostly didn't. Asking for a plan or a couple of options
*before* any code also helped, because it let me steer instead of just accepting
whatever came out first.

**b. Judgment and verification**

The clearest case where I didn't just take the AI's answer was
`detect_conflicts()`. It handed me a slick `zip(timed, timed[1:])` comprehension
that crammed the overlap check *and* the warning-message formatting into one
expression. It was clever, but honestly harder to read, and there was no speed
benefit — so I threw it out and wrote a plain loop with named variables
(`prev_start`, `prev_end`, and so on) instead. For me, code I can actually read
and debug beats code that's impressive to look at.

There was also the Enum suggestion from the skeleton review, which I didn't
reject so much as postpone — it was a good idea at the wrong time, so I came back
to it later as a shared `PRIORITY_ORDER` constant with validation.

As for trusting the output: I mostly didn't, at least not on sight. I ran
`main.py` after every feature to actually watch it behave, and I wrote tests that
pin down concrete outcomes — like a daily task completed today producing one due
tomorrow, computed with `timedelta` so the test doesn't break depending on what
day I run it. I deliberately checked the scary edges, like the month rollover
(Jan 31 → Feb 1) and an empty pet. And when the AI changed the Scheduler's
signature, I reran the full suite to make sure it hadn't quietly broken something
else.

---

## 4. Testing and Verification

**a. What you tested**

The suite lives in `tests/test_pawpal.py` and has 12 tests. It covers the basics
(marking a task complete flips its status, adding a task grows the pet's list),
sorting (chronological order, with untimed tasks pushed to the end), recurrence
(a finished daily task creates one for tomorrow, weekly jumps 7 days, and `once`
tasks don't repeat), conflict detection (overlaps get flagged, and
non-overlapping tasks *don't* trigger false alarms), filtering (by status and by
pet), and the empty-pet edge case where a pet with no tasks should just produce
an empty plan instead of crashing.

I focused there because those are the spots where the code could be wrong without
being obviously wrong — the date math is easy to get off by a day, sort ordering
is easy to reverse, and overlap detection is all about boundary conditions. The
tests also doubled as a safety net: when I refactored the Scheduler, they're what
told me I hadn't broken anything.

**b. Confidence**

I'd put myself at about a 4 out of 5. All 12 tests pass and they hit the core
behaviors and their main edges, so I genuinely trust the sorting, recurrence,
conflict, and filtering logic. I'm holding back that last point honestly, because
a couple of things still aren't tested directly — the budget filter dropping
over-budget tasks, and the gap I described in section 2b where conflicts get
detected but not resolved.

If I had more time, the next edge cases I'd write are: a budget too small to fit
anything at all, two tasks with identical priority *and* duration (to check the
ordering stays stable), a malformed `preferred_time`, a task that runs past
midnight, and a larger number of pets and tasks just to make sure performance
holds up.

---

## 5. Reflection

**a. What went well**

The thing I'm happiest with is how cleanly the logic layer
(`pawpal_system.py`) stayed separated from the UI (`app.py`). Because all the
real scheduling behavior lives in classes, the Streamlit app ended up being a
thin wrapper that just calls Scheduler methods — and the exact same logic gets
exercised by both `main.py` and the test suite. That separation paid off every
time I changed something. The recurrence feature also just came together nicely:
`next_occurrence()` uses `timedelta` so date rollovers work correctly, and
`Pet.complete_task()` ties "mark this done" to "make the next one" in a way that
feels natural.

Working in separate chat sessions for each phase helped more than I expected.
Keeping design, implementation, and testing in their own conversations meant each
one stayed on topic — when I was writing tests, that session was thinking about
edge cases, not re-arguing the class design from three phases ago. It also kept
old assumptions from bleeding into later steps, which made each phase easier to
frame.

**b. What you would improve**

Next time around, I'd make `build_plan()` actually respect preferred times
instead of stacking tasks back-to-back — basically turning conflict *detection*
into conflict *resolution*, where the scheduler bumps a lower-priority task or
suggests another slot. I'd also add per-pet time budgets, do something smarter
with owner preferences (like preferred parts of the day), and write tests for the
paths I flagged as untested in section 4b.

**c. Key takeaway**

The biggest thing I took away is what being the "lead architect" actually means
when you're working with a tool this capable. The AI is fantastic at cranking out
options, scaffolding, and boilerplate fast — but it doesn't own the design, and
it shouldn't. My job was to set the direction (four focused classes, logic split
from UI), make the calls it couldn't (readability over cleverness in
`detect_conflicts()`, holding the Enum for later, deciding *not* to build full
time-resolution), and check every suggestion by running and testing it rather
than trusting it. The rhythm that worked was AI proposes, I decide, tests
confirm. I moved quickly because the AI handled the grunt work, but the system
stayed coherent because I kept ownership of the architecture and treated whatever
it gave me as a draft to judge, not an answer to accept.
