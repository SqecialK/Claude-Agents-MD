"""Detects which automation solution category a job posting describes.

Categories are matched by keyword against the combined job title +
description. The first matching category wins; if nothing matches, the
"Workflow Automation" category is returned as the default.
"""

from typing import TypedDict


class Solution(TypedDict):
    name: str
    explanation: str
    steps: list
    mermaid: str


_AI_LEAD_GEN: Solution = {
    "name": "AI Lead Generation",
    "explanation": (
        "Pull contacts from a source like Apollo, enrich and score them, "
        "then run automated, personalized outreach through an AI agent."
    ),
    "steps": [
        "Pull contacts from Apollo / LinkedIn Sales Navigator",
        "Enrich and score leads against your ICP",
        "Send personalized outreach with an AI agent (e.g. Lindy)",
        "Sync replies and pipeline into your CRM",
    ],
    "mermaid": """flowchart TB
    subgraph INPUT["DATA SOURCES"]
        A1[Apollo.io<br/>Contact Database]
        A2[LinkedIn<br/>Sales Navigator]
    end

    subgraph ENRICH["AI ENRICHMENT"]
        B1[Company Research<br/>Revenue, Size, Industry]
        B2[Lead Scoring<br/>ICP Match Score]
    end

    subgraph OUTREACH["AUTOMATED OUTREACH"]
        C1[AI Agent<br/>Personalized Emails]
        C2[Multi-Channel<br/>Email + LinkedIn + Call]
    end

    subgraph CRM["CRM & ANALYTICS"]
        D1[CRM Sync]
        D2[Pipeline Dashboard]
    end

    A1 --> B1
    A2 --> B1
    B1 --> B2
    B2 --> C1
    C1 --> C2
    C2 --> D1
    D1 --> D2

    style INPUT fill:#E3F2FD,stroke:#1976D2
    style ENRICH fill:#E8F5E9,stroke:#388E3C
    style OUTREACH fill:#FFF3E0,stroke:#F57C00
    style CRM fill:#ECEFF1,stroke:#546E7A""",
}

_EMAIL_AUTOMATION: Solution = {
    "name": "Email Automation",
    "explanation": (
        "Build a segmented drip sequence that sends the right email at the "
        "right time based on how each contact behaves."
    ),
    "steps": [
        "Import and segment your contact list",
        "Build the drip sequence with branching logic",
        "Trigger sends based on opens, clicks, and replies",
        "Track performance on a live dashboard",
    ],
    "mermaid": """flowchart TB
    subgraph INPUT["CONTACT LIST"]
        A1[CRM / CSV Import]
        A2[Signup Forms]
    end

    subgraph SEGMENT["SEGMENTATION"]
        B1[Tagging Rules]
        B2[Audience Segments]
    end

    subgraph SEQUENCE["DRIP SEQUENCE"]
        C1[Email 1: Intro]
        C2[Branch on Open/Click]
        C3[Follow-up Emails]
    end

    subgraph ANALYTICS["PERFORMANCE"]
        D1[Open/Click Tracking]
        D2[Reply Dashboard]
    end

    A1 --> B1
    A2 --> B1
    B1 --> B2
    B2 --> C1
    C1 --> C2
    C2 --> C3
    C3 --> D1
    D1 --> D2

    style INPUT fill:#E3F2FD,stroke:#1976D2
    style SEGMENT fill:#F3E5F5,stroke:#8E24AA
    style SEQUENCE fill:#E8F5E9,stroke:#388E3C
    style ANALYTICS fill:#FFF3E0,stroke:#F57C00""",
}

_AI_RECEPTIONIST: Solution = {
    "name": "AI Receptionist",
    "explanation": (
        "Deploy an AI agent across chat, SMS, and voice that answers "
        "questions, qualifies leads, and books appointments 24/7."
    ),
    "steps": [
        "Connect inbound channels (chat, SMS/WhatsApp, phone)",
        "Recognize intent and qualify the lead",
        "Answer FAQs or escalate to a human",
        "Auto-book appointments and alert the sales team",
    ],
    "mermaid": """flowchart TB
    subgraph CHANNELS["INBOUND"]
        CH1[Website Chat]
        CH2[SMS/WhatsApp]
        CH3[Phone/Voice]
    end

    subgraph AI["AI ENGINE"]
        A1[Intent Recognition]
        A2[Lead Qualification]
        A3[Response Generation]
    end

    subgraph OUTPUT["ACTIONS"]
        O1[Answer FAQs]
        O2[Book Appointments]
        O3[Alert Sales Team]
    end

    CH1 --> A1
    CH2 --> A1
    CH3 --> A1
    A1 --> A2
    A2 --> A3
    A3 --> O1
    A3 --> O2
    A3 --> O3

    style CHANNELS fill:#E3F2FD,stroke:#1976D2
    style AI fill:#E8F5E9,stroke:#388E3C
    style OUTPUT fill:#FFF3E0,stroke:#F57C00""",
}

_LEAD_AUTOMATION: Solution = {
    "name": "Lead Automation",
    "explanation": (
        "Score inbound leads automatically, nurture them with the right "
        "content, and keep the CRM pipeline current without manual entry."
    ),
    "steps": [
        "Capture leads from forms and integrations",
        "Score leads against fit and intent criteria",
        "Nurture with automated follow-up sequences",
        "Keep CRM stages and pipeline in sync",
    ],
    "mermaid": """flowchart TB
    subgraph CAPTURE["LEAD CAPTURE"]
        A1[Web Forms]
        A2[Ad / Landing Page Leads]
    end

    subgraph SCORE["SCORING"]
        B1[Fit Score<br/>Firmographic Match]
        B2[Intent Score<br/>Engagement Signals]
    end

    subgraph NURTURE["NURTURE"]
        C1[Automated Follow-ups]
        C2[Sales Handoff Rules]
    end

    subgraph CRM["CRM SYNC"]
        D1[Pipeline Stage Updates]
        D2[Reporting Dashboard]
    end

    A1 --> B1
    A2 --> B1
    B1 --> B2
    B2 --> C1
    C1 --> C2
    C2 --> D1
    D1 --> D2

    style CAPTURE fill:#E3F2FD,stroke:#1976D2
    style SCORE fill:#F3E5F5,stroke:#8E24AA
    style NURTURE fill:#E8F5E9,stroke:#388E3C
    style CRM fill:#ECEFF1,stroke:#546E7A""",
}

_SOCIAL_AUTOMATION: Solution = {
    "name": "Social Automation",
    "explanation": (
        "Plan, generate, and schedule social content across platforms from "
        "a single content calendar, with performance tracked automatically."
    ),
    "steps": [
        "Plan content in a shared calendar",
        "Generate drafts and visuals with AI",
        "Auto-schedule and publish across platforms",
        "Track engagement and repurpose top performers",
    ],
    "mermaid": """flowchart TB
    subgraph PLAN["CONTENT PLANNING"]
        A1[Content Calendar]
        A2[Topic / Trend Research]
    end

    subgraph CREATE["AI CREATION"]
        B1[Draft Generation]
        B2[Visual / Video Assets]
    end

    subgraph PUBLISH["SCHEDULING"]
        C1[Auto-Schedule Queue]
        C2[Multi-Platform Publish]
    end

    subgraph ANALYZE["ANALYTICS"]
        D1[Engagement Tracking]
        D2[Repurpose Top Posts]
    end

    A1 --> B1
    A2 --> B1
    B1 --> B2
    B2 --> C1
    C1 --> C2
    C2 --> D1
    D1 --> D2

    style PLAN fill:#E3F2FD,stroke:#1976D2
    style CREATE fill:#F3E5F5,stroke:#8E24AA
    style PUBLISH fill:#E8F5E9,stroke:#388E3C
    style ANALYZE fill:#FFF3E0,stroke:#F57C00""",
}

_WORKFLOW_AUTOMATION: Solution = {
    "name": "Workflow Automation",
    "explanation": (
        "Connect your existing tools with an automation platform so data "
        "moves between them without manual copy-paste."
    ),
    "steps": [
        "Map the current manual process",
        "Connect source and destination tools",
        "Build the automated workflow with error handling",
        "Monitor runs and alert on failures",
    ],
    "mermaid": """flowchart TB
    subgraph TRIGGER["TRIGGERS"]
        A1[Form / App Event]
        A2[Scheduled Trigger]
    end

    subgraph BUILD["AUTOMATION PLATFORM"]
        B1[Zapier / Make / n8n]
        B2[Data Mapping & Logic]
    end

    subgraph CONNECT["CONNECTED TOOLS"]
        C1[CRM / Sheets]
        C2[Notifications: Email/Slack]
    end

    subgraph MONITOR["MONITORING"]
        D1[Run Logs]
        D2[Failure Alerts]
    end

    A1 --> B1
    A2 --> B1
    B1 --> B2
    B2 --> C1
    B2 --> C2
    C1 --> D1
    C2 --> D1
    D1 --> D2

    style TRIGGER fill:#E3F2FD,stroke:#1976D2
    style BUILD fill:#E8F5E9,stroke:#388E3C
    style CONNECT fill:#FFF3E0,stroke:#F57C00
    style MONITOR fill:#ECEFF1,stroke:#546E7A""",
}

# Order matters: first keyword match wins. Workflow Automation is the
# fallback and is intentionally not matched by keyword here.
_CATEGORY_KEYWORDS = [
    (_AI_LEAD_GEN, ("apollo", "lindy", "outreach", "lead gen", "prospecting", "cold outreach")),
    (_EMAIL_AUTOMATION, ("email sequence", "drip", "email campaign", "cold email", "newsletter automation")),
    (_AI_RECEPTIONIST, ("chatbot", "receptionist", "customer service", "voice agent", "virtual assistant", "answering service")),
    (_LEAD_AUTOMATION, ("lead scoring", "crm", "nurtur", "pipeline automation")),
    (_SOCIAL_AUTOMATION, ("social media", "content calendar", "social scheduling", "content automation", "posting schedule")),
]


def identify_solution(job_title: str, job_description: str) -> Solution:
    """Detect the solution category for a job from its title + description."""
    combined = f"{job_title or ''} {job_description or ''}".lower()
    for solution, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in combined for keyword in keywords):
            return solution
    return _WORKFLOW_AUTOMATION
