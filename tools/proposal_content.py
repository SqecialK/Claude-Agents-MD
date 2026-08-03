"""Renders the cover letter and VSL script for a job proposal.

Both are generated deterministically from fixed templates plus the
solution category detected by ``tools.solution_identifier`` — no LLM call
is required.
"""

from tools.solution_identifier import Solution

LOOM_PLACEHOLDER = "[ADD YOUR LOOM RECORDING LINK HERE]"

BIO = (
    "Matt Kerkhoff is a sales professional based in Louisville, KY, with 15+ years of "
    "experience across medical device sales, enterprise B2B payments, and specialty "
    "consumer sales. At American Express, Global Commercial Services, he served as "
    "Manager of Business Development (Global), driving full-cycle new client "
    "acquisition for enterprise accounts ($300M–$1.5B in revenue) selling B2B "
    "payment solutions across Kentucky, Ohio, West Virginia, and Virginia; he closed "
    "5 new enterprise accounts generating $18.62M in Billed Charge Volume against a "
    "$19M goal (98% attainment) in his first full year, with $92M in identified "
    "pipeline, and signings including The NOCO Company ($7.6M) and Prolink Staffing "
    "($8.5M). Before that, he spent 6 years at OrthoSensor as the company's first "
    "field rep hired, covering a territory from New York to South Dakota, landing his "
    "first surgeon within 2 months and running cases within 3, and helping lead the "
    "pre- and post-market launch of VERASENSE and OrthoLogIQ prior to the company's "
    "acquisition by Stryker in 2021. He also sold Quill Barbed Suture at Surgical "
    "Specialties for two years, achieving over 75% adoption in trial cases, and held "
    "additional orthopedic capital equipment and implant sales roles at Zimmer "
    "Biomet, OrthAlign, and Stryker Orthopaedics, including OEM distributor "
    "recruitment and management across the Eastern and Midwest U.S. He currently "
    "owns Derby City Specialists, LLC, an independent consulting and capital "
    "equipment resale practice, and holds Series 6 and Series 63 licenses along with "
    "12+ years of Salesforce and 8+ years of SaaS sales experience."
)

COVER_LETTER_TEMPLATE = """Hi! I'm confident I'm the best fit to build your {system_description}.

Just recorded a quick 2-minute video walking you through exactly how I'd approach it: {loom_link}

{bio}

I'd love to learn more about what you're building and see how we can make it more efficient with AI.

Matt K."""


def extract_system_description(job_title: str, solution: Solution) -> str:
    """Build the short phrase used in the cover letter's opening line."""
    return f"{solution['name']} system"


def render_cover_letter(job_title: str, solution: Solution, loom_link: str = LOOM_PLACEHOLDER) -> str:
    """Render the fixed cover letter template for a detected solution."""
    system_description = extract_system_description(job_title, solution)
    return COVER_LETTER_TEMPLATE.format(
        system_description=system_description,
        loom_link=loom_link,
        bio=BIO,
    )


def _extract_pain_point(job_description: str) -> str:
    """Pull a short, human-readable snippet to reference as the pain point."""
    text = " ".join((job_description or "").split())
    if not text:
        return "getting this handled manually is eating up your time"
    for sentence in text.split(". "):
        sentence = sentence.strip().rstrip(".")
        if len(sentence) >= 25:
            return sentence[:160]
    return text[:160]


def generate_vsl_script(job_title: str, job_description: str, solution: Solution) -> str:
    """Generate a ~60-second, conversational VSL script for Loom."""
    pain_point = _extract_pain_point(job_description)
    steps = solution["steps"]
    steps_line = "; then ".join(steps[:3]).lower()

    return f"""Hey, thanks for checking out my proposal for "{job_title}".

I read through what you're dealing with, and it sounds like {pain_point}. That's exactly the kind of problem I like solving.

Here's how I'd approach it: {steps_line}.

I put together a quick infographic that shows the whole flow step by step, so you can see exactly where each piece fits before we ever get on a call.

If this looks like a good match, let's hop on a quick call this week and I'll walk you through the details and answer any questions."""
