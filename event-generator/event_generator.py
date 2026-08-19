"""
PLAN:

Make the event generator work in one of two ways:
Either it invokes an llm to generate a crisis feed, or it uses a pre-scripted feed. The latter is useful for demos and tests, while the former is useful for generating new scenarios.

For the llm approach, the generator will go through a fixed loop every 0.1 seconds or so:
3 customer events -> 1 press event -> [repeat]

The main difference between the press and customer events is that the press events are more detailed and grounded (assumed to always be real events). Whereas the customer events are more likely to be emotional or sensationalized.

[optional - USED via 6 stages] There exist a 'guiding hand' for the events that follows a pre scriped narrative. eg: start -> spread -> escalate -> lawsuits -> disease vanishes -> calm     (you could also let an llm create the narrative)

[optional - NOT USED] Use coded statistics to determine what the llm should produce. (prompt engineering)

Inside the generation loop:
- determine if to generate a 'customer' or 'press' event.
- run the statistics to create engineered prompt.
- invoke llm to generate event
- emit said event
"""


import time

from event_broker import Event

from langchain_nvidia_ai_endpoints import ChatNVIDIA

# The scripted mode. Twelve events - one customer, one press - through the six
# stages in order. It exists so /replay stays free and repeatable for debugging:
# same text every run, no API key, no network, no waiting. The LLM path below is
# the other mode, for generating fresh scenarios.
#
# Tags must match the ones generate() emits, or a subscriber that works against
# one mode silently receives nothing from the other.
CRISIS_FEED = [
    # 1. PRE-CRISIS
    ("customer", "Sarah picks up two cans of HappyTuna skipjack at GreenMart and serves them in a salad that evening. Her kids ask for seconds. She adds it to next week's list."),
    ("press", "Regional grocery trade weekly notes canned tuna volumes up 4% year on year, with HappyTuna among the three fastest-moving shelf brands in the western region. No safety concerns are mentioned anywhere in the report."),
    # 2. START
    ("customer", "A shopper posts a photo of a HappyTuna can whose seam looks slightly swollen. Two people reply that theirs looked the same. Most commenters tell her it is probably nothing and she should just return it."),
    ("press", "A county health department publishes its routine monthly notifiable-disease summary. Salmonella cases are listed at nine for the month against a five-year average of four. The summary offers no suspected source and attracts no coverage."),
    # 3. SPREAD
    ("customer", "A father reports his daughter was up all night with cramps and fever a day after a tuna sandwich. He has kept the empty can. The pediatric clinic tells him two other families described something similar this week."),
    ("press", "State epidemiologists confirm they are investigating a cluster of eleven salmonella cases across four counties. Interviews indicate a shared exposure to canned fish. Investigators say it is too early to name a product or a producer."),
    # 4. EXPOSURE
    ("customer", "A GreenMart shift supervisor says staff pulled several dented cases from a HappyTuna pallet last month and that nobody logged it. She is worried about what she may have put on the shelf and has stopped buying it for her own family."),
    ("press", "Laboratory testing links salmonella isolates from nineteen patients to a single strain. State officials confirm the strain was recovered from an opened HappyTuna can retained by an affected household. The finding is now public."),
    # 5. CRISIS
    ("customer", "A customer describes waiting ninety minutes on a support line before being disconnected. She wants to know whether the cans already in her pantry are safe and says nobody has been able to tell her."),
    ("press", "Two law firms announce they are reviewing claims on behalf of affected households. Three regional grocery chains confirm they have removed the product from shelves pending guidance. Case counts have flattened over the past nine days, with no new confirmed illnesses in the last four."),
    # 6. RESOLUTION
    ("customer", "A long-time buyer writes that she is glad the outbreak is over but has switched brands for now. She says she would consider coming back once there is a full account of what went wrong and what changed."),
    ("press", "Health authorities declare the outbreak over, with a final count of thirty-one confirmed cases and no fatalities. Investigators trace the contamination to a single cooling stage at one facility. Oversight bodies signal that inspection frequency for the category will be reviewed."),
]


def replay(event: Event, delay: float = 0.2):
    """Emits the scripted feed through the broker, one event at a time.

    The cheap counterpart to generate(): no LLM, so a debugging replay costs
    nothing and produces the same feed every time.
    """
    for tag, text in CRISIS_FEED:
        event.emit(tag, text)
        if delay:
            time.sleep(delay)


# Reads NVIDIA_API_KEY from the environment, which docker-compose fills from the
# repo-root .env via `env_file` - same as customer-agent and influencer-agent.
# Running outside Docker means putting it in the environment yourself.
llm = ChatNVIDIA(
    model="meta/llama-3.1-8b-instruct",
    temperature=0.7,
    # Default is 1024. Press events are the longest thing asked for (5-15 lines),
    # so this bounds a rambling response without truncating a well-behaved one.
    max_completion_tokens=400,
)
system_msg = ("You are an event generator."
              "Backstory: There is a tuna company called HappyTuna that is goes through a Salmonella outbreak crisis with their product."
              "There are 6 stages to this narrative, and they are as follows:"
              "1. PRE-CRISIS: The company is operating normally, and there are no known issues with the product. The product is being sold and enjoyed without incident."
              "2. START: Faint signs of a problem begin to appear, but the company is unaware of the issue. The product is still being sold and consumed."
              "3. SPREAD: Customers experience recurring issues with the product, and the company begins to receive complaints. The issue is still not fully understood, and the product continues to be sold."
              "4. EXPOSURE: Major bad experiences occur with customers, stores, factory workers, or the company's lab. The issue is now widely known, and the company is under scrutiny."
              "5. CRISIS: The public, authorities, and the company react to the crisis. The company may face lawsuits, recalls, and negative publicity. Whilst Salmonella spreads rapidly decreases in the background due to the company's efforts to contain it."
              "6. RESOLUTION: The Salmonella outbreak is fully contained, and the company takes steps to prevent future incidents. The company may face long-term consequences, but the crisis is resolved.")


def _invoke(messages):
    """One LLM call, retried on failure.

    The hosted endpoint stalls often enough that a single 60s read timeout would
    otherwise abort a whole 36-event run at, say, event 5. The client raises a
    plain Exception for HTTP errors, so there is no narrower type to catch here -
    a genuinely broken call (bad key, bad model name) just fails three times
    before it surfaces.
    """
    for attempt in range(1, 4):
        try:
            return llm.invoke(messages)
        except Exception as exc:
            if attempt == 3:
                raise
            print(f"  call failed ({exc}); retrying {attempt}/2")
            time.sleep(2)


def generate(event: Event ,delay: float = 0.1):
    """Emits the crisis feed through the broker, one event at a time.

    `delay` puts a pause between events so a live demo can be followed at
    reading speed; leave it at 0 for tests.
    """

    ## loop over all stages, in each one do  3 customer events -> 1 press event
    for i in range(6):
        for j in range(3):
            ## build 3 prompts for customer events
            stage = {0: "PRE-CRISIS", 1: "START", 2: "SPREAD", 3: "EXPOSURE", 4: "CRISIS", 5: "RESOLUTION"}
            customer_event_description = "Generate one plausible customer event that happens DURING THE " + stage[i] + " STAGE ONLY. The event should be 3-5 lines long, The event should be written in a way that is consistent with the narrative of the crisis. You MUST NOT invent actions on behalf of HappyTuna."

            messages = [
                ("system", system_msg),
                ("human", str(customer_event_description)),
            ]

            print("\n--- Customer event generation for stage "+ stage[i] + " ----")
            response = _invoke(messages)
            print(response.content)

            # emit response content to relevant event listeners
            event.emit("customer", response.content)
            
            if delay:
                time.sleep(delay)


        ## build one prompt for press event
        press_event_description = "Generate one plausible press event that happens DURING THE " + stage[i] + " STAGE ONLY. The event should be 5-15 lines long, The event should be written in a way that is consistent with the narrative of the crisis. You MUST NOT invent actions on behalf of HappyTuna."

        messages = [
            ("system", system_msg),
            ("human", str(press_event_description)),
        ]

        print("\n--- Press event generation for stage "+ stage[i] + " ----")
        response = _invoke(messages)
        print(response.content)

        # emit response content to relevant event listeners
        event.emit("press", response.content)
        
        if delay:
            time.sleep(delay)