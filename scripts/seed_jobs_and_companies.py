"""
DataHire - Seed Companies, Taxonomy, and Job Postings
Populates high-quality, realistic tech companies, taxonomy roles, and published job postings.
"""

import sys
import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.user import User, UserRole, AuthProvider
from app.models.company import Company, company_taxonomy_domains
from app.models.employer import Employer
from app.models.taxonomy import TaxonomyDomain, TaxonomyJobRole, TaxonomySkill
from app.models.job import JobPosting, JobStatus
from app.models.meta import (
    MetaCountry, MetaState, MetaCity, MetaEmploymentType,
    MetaWorkMode, MetaSeniorityLevel, MetaCurrency, MetaIndustry,
    MetaCompanySize, MetaOrganizationType, MetaVisaStatus
)
from app.services.embedding_service import embedding_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Safe database URL adapter for psycopg
db_url = settings.DATABASE_URL
if db_url and db_url.startswith("postgresql://") and "+psycopg" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(db_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# 1. TAXONOMY SEED DATA
# ---------------------------------------------------------------------------
TAXONOMY_DATA = [
    {
        "domain": "Software Engineering",
        "slug": "software-engineering",
        "roles": [
            {
                "name": "Senior Backend Engineer (Python / FastAPI)",
                "slug": "senior-backend-engineer-python-fastapi",
                "aliases": ["Backend Engineer", "Senior Python Engineer", "API Engineer"],
                "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis", "REST APIs"],
                "optional_skills": ["Kafka", "Kubernetes", "AWS", "Celery", "GraphQL"],
            },
            {
                "name": "Staff Distributed Systems Engineer (Go / Rust)",
                "slug": "staff-distributed-systems-engineer-go-rust",
                "aliases": ["Staff Backend Engineer", "Systems Engineer", "Core Infra Engineer"],
                "required_skills": ["Go", "Distributed Systems", "gRPC", "PostgreSQL", "Microservices", "Kafka"],
                "optional_skills": ["Rust", "Kubernetes", "Raft", "High Throughput Systems", "Redis"],
            },
            {
                "name": "Lead Frontend Engineer (React / Next.js)",
                "slug": "lead-frontend-engineer-react-nextjs",
                "aliases": ["Frontend Architect", "Lead UI Engineer", "Senior React Developer"],
                "required_skills": ["React", "Next.js", "TypeScript", "Tailwind CSS", "State Management", "Performance Optimization"],
                "optional_skills": ["GraphQL", "Design Systems", "WebSockets", "Testing Library", "CI/CD"],
            },
            {
                "name": "Full Stack Engineer (Node.js / React)",
                "slug": "full-stack-engineer-node-react",
                "aliases": ["Full Stack Developer", "Software Engineer - Full Stack"],
                "required_skills": ["JavaScript", "TypeScript", "React", "Node.js", "PostgreSQL", "Tailwind CSS"],
                "optional_skills": ["Next.js", "Docker", "AWS", "Prisma", "Express"],
            },
            {
                "name": "Mobile Engineer (React Native / iOS)",
                "slug": "mobile-engineer-react-native-ios",
                "aliases": ["iOS Engineer", "Mobile App Developer", "Cross-Platform Engineer"],
                "required_skills": ["React Native", "TypeScript", "iOS", "Mobile Architecture", "REST APIs"],
                "optional_skills": ["Swift", "Android", "Redux", "App Store Deployment", "CI/CD"],
            },
        ]
    },
    {
        "domain": "Data Science & AI",
        "slug": "data-science-ai",
        "roles": [
            {
                "name": "Senior Machine Learning Engineer (LLMs & RAG)",
                "slug": "senior-ml-engineer-llms-rag",
                "aliases": ["AI Engineer", "GenAI Engineer", "LLM Specialist"],
                "required_skills": ["Python", "PyTorch", "Large Language Models (LLMs)", "RAG", "Vector Databases", "LangChain"],
                "optional_skills": ["Hugging Face", "LoRA/Fine-tuning", "vLLM", "Docker", "MLOps"],
            },
            {
                "name": "Staff Data Engineer (Spark & Snowflake)",
                "slug": "staff-data-engineer-spark-snowflake",
                "aliases": ["Data Architect", "Lead Data Platform Engineer"],
                "required_skills": ["Python", "SQL", "Apache Spark", "Snowflake", "Data Modeling", "Airflow"],
                "optional_skills": ["Kafka", "dbt", "AWS S3", "Delta Lake", "Trino"],
            },
            {
                "name": "Senior Applied Scientist (NLP & Search)",
                "slug": "senior-applied-scientist-nlp-search",
                "aliases": ["NLP Scientist", "AI Researcher", "Search Relevance Scientist"],
                "required_skills": ["Python", "NLP", "Information Retrieval", "Semantic Search", "PyTorch", "Vector Embeddings"],
                "optional_skills": ["Elasticsearch", "Transformers", "Milvus/Pinecone", "A/B Testing"],
            },
        ]
    },
    {
        "domain": "Cloud, DevOps & Infrastructure",
        "slug": "cloud-devops-infra",
        "roles": [
            {
                "name": "Staff Site Reliability Engineer (SRE / Platform)",
                "slug": "staff-sre-platform-engineer",
                "aliases": ["SRE Lead", "Principal Infrastructure Engineer", "DevOps Architect"],
                "required_skills": ["Kubernetes", "Terraform", "AWS", "Linux", "CI/CD", "Observability (Prometheus/Grafana)"],
                "optional_skills": ["Go", "ArgoCD", "Helm", "Multi-region Architecture", "Datadog"],
            },
            {
                "name": "DevSecOps & Cloud Security Engineer",
                "slug": "devsecops-cloud-security-engineer",
                "aliases": ["Security Engineer", "Application Security Specialist"],
                "required_skills": ["AWS Security", "Kubernetes Security", "IAM", "Vulnerability Management", "Terraform"],
                "optional_skills": ["SOC2 Compliance", "SAST/DAST", "SIEM", "Python", "Incident Response"],
            },
        ]
    },
    {
        "domain": "Product & Design",
        "slug": "product-design",
        "roles": [
            {
                "name": "Senior Product Manager (Developer Platform & APIs)",
                "slug": "senior-product-manager-developer-platform",
                "aliases": ["Technical Product Manager", "Platform PM"],
                "required_skills": ["Product Strategy", "API Design", "Developer Experience", "Roadmapping", "Agile"],
                "optional_skills": ["Data Analytics", "SQL", "User Research", "Go-To-Market"],
            },
            {
                "name": "Principal Product Designer (Design Systems & UX)",
                "slug": "principal-product-designer-design-systems",
                "aliases": ["Design Systems Lead", "Staff UX Designer", "UI/UX Lead"],
                "required_skills": ["Figma", "Design Systems", "User Research", "Interaction Design", "Prototyping"],
                "optional_skills": ["HTML/CSS", "Design Tokens", "Accessibility (WCAG)", "Information Architecture"],
            },
        ]
    }
]


# ---------------------------------------------------------------------------
# 2. COMPANIES SEED DATA
# ---------------------------------------------------------------------------
COMPANIES_DATA = [
    {
        "name": "Stripe",
        "slug": "stripe",
        "website": "https://stripe.com",
        "logo_url": "https://images.ctfassets.net/fzn2n1nzq965/3Aj8vVb2nYYkCO4y4S8i2q/73e13d508f7d98305c48b8160fc4585c/stripe-logo.png",
        "founded_year": 2010,
        "description": "Stripe builds economic infrastructure for the internet. Businesses of every size—from new startups to public companies—use our software to accept payments and manage their businesses online.",
        "zipcode": "94103",
        "office_landline_number": "+1-415-555-0101",
        "alternate_email": "jobs@stripe.com",
        "work_mobile_number": "+1-415-555-0102",
        "plan_tier": "enterprise",
        "city_name": "San Francisco",
        "industry_name": "Finance",
        "size_label": "1000+",
        "org_type_name": "Enterprise",
        "employer_email": "recruiter.stripe@datahire.ai",
        "employer_name": "Sarah Jenkins (Senior Talent Partner)"
    },
    {
        "name": "Scale AI",
        "slug": "scale-ai",
        "website": "https://scale.com",
        "logo_url": "https://assets-global.website-files.com/5f9a6572e09ff25d74268e64/63044a86b514d3f66810a08e_ScaleLogo.svg",
        "founded_year": 2016,
        "description": "Scale provides the data engine for leading AI applications and foundational model labs, transforming raw data into high-quality training and evaluation datasets for LLMs and autonomous systems.",
        "zipcode": "94107",
        "office_landline_number": "+1-415-555-0201",
        "alternate_email": "careers@scale.com",
        "work_mobile_number": "+1-415-555-0202",
        "plan_tier": "enterprise",
        "city_name": "San Francisco",
        "industry_name": "Information Technology",
        "size_label": "1000+",
        "org_type_name": "Product",
        "employer_email": "recruiter.scale@datahire.ai",
        "employer_name": "Alex Rivera (Lead Technical Recruiter)"
    },
    {
        "name": "Linear",
        "slug": "linear",
        "website": "https://linear.app",
        "logo_url": "https://linear.app/static/apple-touch-icon.png",
        "founded_year": 2019,
        "description": "Linear is a purpose-built tool for planning and building products. Streamline software projects, sprints, tasks, and bug tracking with high-performance craftsmanship.",
        "zipcode": "94105",
        "office_landline_number": "+1-415-555-0301",
        "alternate_email": "hiring@linear.app",
        "work_mobile_number": "+1-415-555-0302",
        "plan_tier": "startup",
        "city_name": "San Francisco",
        "industry_name": "Information Technology",
        "size_label": "51-200",
        "org_type_name": "Startup",
        "employer_email": "recruiter.linear@datahire.ai",
        "employer_name": "Karri Saarinen (Head of Product)"
    },
    {
        "name": "Supabase",
        "slug": "supabase",
        "website": "https://supabase.com",
        "logo_url": "https://supabase.com/brand-assets/supabase-logo-icon.png",
        "founded_year": 2020,
        "description": "Supabase is an open source Firebase alternative providing developers with a dedicated PostgreSQL database, Auth, realtime subscriptions, edge functions, and storage.",
        "zipcode": "94102",
        "office_landline_number": "+1-415-555-0401",
        "alternate_email": "careers@supabase.com",
        "work_mobile_number": "+1-415-555-0402",
        "plan_tier": "startup",
        "city_name": "San Francisco",
        "industry_name": "Information Technology",
        "size_label": "51-200",
        "org_type_name": "Product",
        "employer_email": "recruiter.supabase@datahire.ai",
        "employer_name": "Paul Copplestone (Engineering Director)"
    },
    {
        "name": "Datadog",
        "slug": "datadog",
        "website": "https://datadoghq.com",
        "logo_url": "https://img.logo.dev/datadoghq.com",
        "founded_year": 2010,
        "description": "Datadog is the essential observability and security platform for cloud applications, combining automated metrics, traces, and logs to provide end-to-end visibility across hybrid architectures.",
        "zipcode": "10018",
        "office_landline_number": "+1-212-555-0501",
        "alternate_email": "careers@datadoghq.com",
        "work_mobile_number": "+1-212-555-0502",
        "plan_tier": "enterprise",
        "city_name": "New York City",
        "industry_name": "Information Technology",
        "size_label": "1000+",
        "org_type_name": "SAAS",
        "employer_email": "recruiter.datadog@datahire.ai",
        "employer_name": "Elena Rostova (Global Talent Lead)"
    },
    {
        "name": "Figma",
        "slug": "figma",
        "website": "https://figma.com",
        "logo_url": "https://img.logo.dev/figma.com",
        "founded_year": 2012,
        "description": "Figma connects everyone in the design process so teams can deliver better products, faster. Over four million people worldwide collaborate in real-time with Figma and FigJam.",
        "zipcode": "94104",
        "office_landline_number": "+1-415-555-0601",
        "alternate_email": "careers@figma.com",
        "work_mobile_number": "+1-415-555-0602",
        "plan_tier": "enterprise",
        "city_name": "San Francisco",
        "industry_name": "Information Technology",
        "size_label": "1000+",
        "org_type_name": "Product",
        "employer_email": "recruiter.figma@datahire.ai",
        "employer_name": "Marcus Vance (Director of Design Recruiting)"
    },
    {
        "name": "Razorpay",
        "slug": "razorpay",
        "website": "https://razorpay.com",
        "logo_url": "https://img.logo.dev/razorpay.com",
        "founded_year": 2014,
        "description": "Razorpay is India's leading full-stack financial services and digital payments company, powering payments for millions of businesses, startups, and enterprises across the globe.",
        "zipcode": "560030",
        "office_landline_number": "+91-80-5555-0701",
        "alternate_email": "jobs@razorpay.com",
        "work_mobile_number": "+91-98800-55502",
        "plan_tier": "enterprise",
        "city_name": "Bengaluru",
        "industry_name": "Finance",
        "size_label": "1000+",
        "org_type_name": "Enterprise",
        "employer_email": "recruiter.razorpay@datahire.ai",
        "employer_name": "Pooja Sharma (Lead Tech Recruiter)"
    },
    {
        "name": "Postman",
        "slug": "postman",
        "website": "https://postman.com",
        "logo_url": "https://img.logo.dev/postman.com",
        "founded_year": 2014,
        "description": "Postman is an API platform for building and using APIs. Used by over 30 million developers and 500,000 organizations, Postman simplifies each step of the API lifecycle and streamlines collaboration.",
        "zipcode": "560001",
        "office_landline_number": "+91-80-5555-0801",
        "alternate_email": "careers@postman.com",
        "work_mobile_number": "+91-98800-55503",
        "plan_tier": "enterprise",
        "city_name": "Bengaluru",
        "industry_name": "Information Technology",
        "size_label": "201-1000",
        "org_type_name": "Product",
        "employer_email": "recruiter.postman@datahire.ai",
        "employer_name": "Rohan Deshmukh (Head of Talent Acquisition)"
    }
]


# ---------------------------------------------------------------------------
# 3. JOB POSTINGS SEED DATA
# ---------------------------------------------------------------------------
JOBS_DATA = [
    {
        "company_slug": "stripe",
        "title": "Senior Backend Engineer - Global Core Payments",
        "role_slug": "senior-backend-engineer-python-fastapi",
        "city_name": "San Francisco",
        "work_mode": "HYBRID",
        "seniority": "SENIOR",
        "employment_type": "FULL_TIME",
        "salary_min": 175000,
        "salary_max": 240000,
        "currency_code": "USD",
        "min_experience_years": 5,
        "max_experience_years": 10,
        "ai_score_threshold": 75,
        "extracted_skills": ["Python", "FastAPI", "PostgreSQL", "Distributed Systems", "Kafka", "Docker", "Redis", "Financial Systems"],
        "job_overview": "We are looking for a Senior Backend Engineer to join our Core Payments team. You will design, build, and scale mission-critical services that handle billions of dollars in daily transactions with 99.999% reliability.",
        "about_role": [
            "Architect high-throughput, low-latency microservices that power payment processing across 195+ countries.",
            "Work directly with banking rails, card networks, and local payment methods.",
            "Drive technical decisions on database sharding, fault tolerance, and zero-downtime deployments.",
            "Collaborate with security and risk engineering teams to protect transactions against fraud."
        ],
        "responsibilities": [
            "Design and implement resilient backend APIs in Python and Go capable of processing 10,000+ requests per second.",
            "Write comprehensive automated tests, load tests, and benchmarks for all critical payment paths.",
            "Optimize PostgreSQL queries, connection pooling, and caching architectures with Redis.",
            "Participate in high-priority on-call rotations and lead post-incident reviews with blameless culture.",
            "Mentor mid-level engineers and conduct thorough architecture design reviews."
        ],
        "requirements": [
            "5+ years of experience designing and operating backend services at scale.",
            "Deep proficiency in Python (FastAPI/Django) or Go, with strong concurrency fundamentals.",
            "Extensive experience with relational databases (PostgreSQL/MySQL), transactions (ACID), and data modeling.",
            "Familiarity with distributed message queues such as Apache Kafka or RabbitMQ.",
            "Strong understanding of idempotency, distributed locks, and fault-tolerant architecture."
        ],
        "benefits": [
            "Comprehensive health, dental, and vision insurance with 100% premium coverage for you and dependents.",
            "Competitive base salary with substantial equity grant and 401(k) matching up to 5%.",
            "Flexible PTO policy with recommended 4 weeks minimum off per year.",
            "$1,500 annual home office setup budget and monthly wellness stipend.",
            "$3,000 annual continuing education and conference allowance.",
            "Generous 16-week parental leave for all new parents."
        ]
    },
    {
        "company_slug": "stripe",
        "title": "Staff Distributed Systems Engineer - Storage Platform",
        "role_slug": "staff-distributed-systems-engineer-go-rust",
        "city_name": "San Francisco",
        "work_mode": "REMOTE",
        "seniority": "LEAD",
        "employment_type": "FULL_TIME",
        "salary_min": 220000,
        "salary_max": 310000,
        "currency_code": "USD",
        "min_experience_years": 8,
        "max_experience_years": 15,
        "ai_score_threshold": 80,
        "extracted_skills": ["Go", "Distributed Systems", "Raft", "PostgreSQL", "gRPC", "High Throughput Systems", "Linux", "Kubernetes"],
        "job_overview": "As a Staff Distributed Systems Engineer on the Storage Platform team, you will shape the next generation of Stripe's distributed stateful infrastructure, managing tens of petabytes with sub-millisecond guarantees.",
        "about_role": [
            "Lead technical strategy for Stripe's internal database virtualization and distributed consensus layers.",
            "Build robust replication, consensus, and disaster recovery engines in Go and Rust.",
            "Partner with infrastructure leadership to establish reliability benchmarks across global multi-region clusters."
        ],
        "responsibilities": [
            "Design consensus-driven storage engines using Raft and Paxos algorithms.",
            "Implement high-performance gRPC services and telemetry pipelines.",
            "Benchmark and optimize kernel-level I/O performance on high-end NVMe cloud hardware.",
            "Drive multi-quarter technical initiatives from RFC to global production rollout."
        ],
        "requirements": [
            "8+ years of experience building large-scale distributed systems and storage engines.",
            "Expert-level knowledge of Go or Rust, concurrency models, and memory management.",
            "Deep theoretical and practical grasp of CAP theorem, consensus protocols, and distributed transactions.",
            "Demonstrated track record of technical leadership across cross-functional engineering organizations."
        ],
        "benefits": [
            "Top-tier compensation package with meaningful public equity grant.",
            "Full remote flexibility with top-spec workstation hardware provided.",
            "401(k) retirement plan with instant employer matching.",
            "Full medical, dental, life, and vision coverage.",
            "Annual global company retreat and executive coaching budget."
        ]
    },
    {
        "company_slug": "scale-ai",
        "title": "Senior Machine Learning Engineer - LLM Evaluation & RLHF",
        "role_slug": "senior-ml-engineer-llms-rag",
        "city_name": "San Francisco",
        "work_mode": "HYBRID",
        "seniority": "SENIOR",
        "employment_type": "FULL_TIME",
        "salary_min": 185000,
        "salary_max": 260000,
        "currency_code": "USD",
        "min_experience_years": 4,
        "max_experience_years": 9,
        "ai_score_threshold": 75,
        "extracted_skills": ["Python", "PyTorch", "Large Language Models (LLMs)", "RLHF", "vLLM", "Hugging Face", "Vector Databases", "MLOps"],
        "job_overview": "Scale AI is seeking an exceptional Senior Machine Learning Engineer to power the frontier of model evaluation and RLHF. You will develop automated evaluation pipelines and fine-tuning harnesses utilized by the world's premier AI labs.",
        "about_role": [
            "Work alongside world-class researchers to build synthetic data generation and RLHF workflows.",
            "Deploy and serve open and proprietary LLMs at scale with ultra-low latency.",
            "Develop novel automated benchmarks to assess model alignment, reasoning capabilities, and hallucination reduction."
        ],
        "responsibilities": [
            "Build distributed training and evaluation workflows using PyTorch, DeepSpeed, and Ray.",
            "Optimize inference serving engines using vLLM, TensorRT-LLM, and speculative decoding.",
            "Collaborate with enterprise clients to customize foundation models for specialized domain applications.",
            "Publish technical papers and contribute to high-impact open-source evaluation harnesses."
        ],
        "requirements": [
            "4+ years of hands-on experience in machine learning with focus on NLP and Large Language Models.",
            "Strong software engineering foundations in Python, Docker, and cloud computing (AWS/GCP).",
            "Proven experience with fine-tuning techniques (LoRA, QLoRA) and RLHF / DPO pipelines.",
            "Familiarity with vector databases (Pinecone, Qdrant, Chroma) and retrieval architectures."
        ],
        "benefits": [
            "Competitive salary + early-stage high-growth equity grant.",
            "Unlimited PTO policy and flexible working arrangements.",
            "Free gourmet lunches, catered dinners, and premium snack bars in office.",
            "Comprehensive health, vision, and dental coverage.",
            "Access to thousands of GPUs for research and engineering experiments."
        ]
    },
    {
        "company_slug": "linear",
        "title": "Lead Frontend Engineer - Product & Web Application",
        "role_slug": "lead-frontend-engineer-react-nextjs",
        "city_name": "San Francisco",
        "work_mode": "REMOTE",
        "seniority": "LEAD",
        "employment_type": "FULL_TIME",
        "salary_min": 170000,
        "salary_max": 230000,
        "currency_code": "USD",
        "min_experience_years": 6,
        "max_experience_years": 12,
        "ai_score_threshold": 75,
        "extracted_skills": ["React", "TypeScript", "Next.js", "Tailwind CSS", "WebSockets", "State Management", "Performance Optimization", "Design Systems"],
        "job_overview": "Linear is looking for a Lead Frontend Engineer with an obsessive eye for detail and speed. You will build and evolve our flagship desktop and web client, celebrated worldwide for instantaneous interactions and 60 FPS performance.",
        "about_role": [
            "Shape the architecture of Linear's offline-first sync engine and real-time collaborative workspace.",
            "Pioneer new UX paradigms that eliminate loading states and make project management a joy.",
            "Maintain our bespoke design system and keyboard-first interaction models."
        ],
        "responsibilities": [
            "Develop lightning-fast UI components in React and TypeScript with zero-friction animations.",
            "Architect client-side caching, IndexedDB persistence, and optimistic state mutations.",
            "Profile web vitals, memory usage, and bundle sizes to ensure sub-50ms interaction latency.",
            "Collaborate closely with product design on micro-interactions and polish."
        ],
        "requirements": [
            "6+ years of specialized frontend engineering experience building rich, desktop-class web applications.",
            "Mastery of modern JavaScript, TypeScript, React internals, and DOM rendering mechanics.",
            "Proven track record of building local-first or real-time collaborative applications (WebSockets/WebRTC).",
            "Deep appreciation for software craft, typography, minimalism, and keyboard shortcuts."
        ],
        "benefits": [
            "Work from anywhere in the world with flexible asynchronous culture.",
            "Top-tier compensation and significant equity ownership.",
            "$3,000 remote workspace budget + $500 monthly work-from-anywhere stipend.",
            "Unlimited vacation with mandatory minimums.",
            "Full medical, dental, and vision insurance."
        ]
    },
    {
        "company_slug": "supabase",
        "title": "Senior Cloud Infrastructure & SRE Engineer",
        "role_slug": "staff-sre-platform-engineer",
        "city_name": "San Francisco",
        "work_mode": "REMOTE",
        "seniority": "SENIOR",
        "employment_type": "FULL_TIME",
        "salary_min": 160000,
        "salary_max": 220000,
        "currency_code": "USD",
        "min_experience_years": 5,
        "max_experience_years": 10,
        "ai_score_threshold": 70,
        "extracted_skills": ["Kubernetes", "AWS", "Terraform", "PostgreSQL", "Docker", "Linux", "Prometheus", "CI/CD"],
        "job_overview": "Join Supabase to help orchestrate millions of PostgreSQL databases worldwide. As a Senior SRE, you will maintain the reliability, automated recovery, and global deployment of our multi-cloud infrastructure.",
        "about_role": [
            "Automate provisioning, health checks, and autoscaling for over 1,000,000 active customer databases.",
            "Manage Kubernetes fleets spanning AWS, Fly.io, and bare metal across 20+ regions.",
            "Improve disaster recovery automation, multi-tenant network security, and point-in-time recovery."
        ],
        "responsibilities": [
            "Author infrastructure as code using Terraform and Pulumi.",
            "Build automated failover mechanisms for primary and replica database instances.",
            "Instrument deep observability across system metrics, query latency, and connection pools.",
            "Collaborate openly with the open-source community through GitHub issues and PRs."
        ],
        "requirements": [
            "5+ years operating production infrastructure on AWS or GCP at massive scale.",
            "Expert understanding of Kubernetes cluster administration, networking (CNI), and storage drivers (CSI).",
            "Solid experience tuning PostgreSQL parameters and understanding WAL replication.",
            "Proficiency in Go, Python, or Bash for robust tooling development."
        ],
        "benefits": [
            "100% remote-first company with teammates across 30+ countries.",
            "Stock options in one of the fastest-growing developer infrastructure platforms.",
            "Co-working space allowance and yearly technology upgrade budget.",
            "Comprehensive health coverage including mental health support.",
            "Flexible working hours tailored to your timezone."
        ]
    },
    {
        "company_slug": "datadog",
        "title": "Principal Cloud Security Architect",
        "role_slug": "devsecops-cloud-security-engineer",
        "city_name": "New York City",
        "work_mode": "HYBRID",
        "seniority": "LEAD",
        "employment_type": "FULL_TIME",
        "salary_min": 210000,
        "salary_max": 290000,
        "currency_code": "USD",
        "min_experience_years": 8,
        "max_experience_years": 15,
        "ai_score_threshold": 80,
        "extracted_skills": ["AWS Security", "Kubernetes Security", "IAM", "Vulnerability Management", "SOC2 Compliance", "Terraform", "Python", "Incident Response"],
        "job_overview": "Datadog is looking for a Principal Cloud Security Architect to protect our hyper-scale multi-cloud infrastructure. You will define threat models, architect zero-trust perimeters, and guide security posture across thousands of microservices.",
        "about_role": [
            "Establish zero-trust network boundaries, workload identity, and least-privilege IAM policies.",
            "Lead security reviews for new cloud native features processing trillions of telemetry events daily.",
            "Coordinate with compliance and red-team units to stay ahead of sophisticated adversaries."
        ],
        "responsibilities": [
            "Define cloud security architectures across AWS, Azure, and Google Cloud Platform.",
            "Develop automated security guardrails and policy-as-code using OPA / Gatekeeper.",
            "Direct threat modeling workshops with engineering teams across product lines.",
            "Lead critical security vulnerability triage and orchestrate rapid remediation."
        ],
        "requirements": [
            "8+ years in cloud security, DevSecOps, and enterprise security architecture.",
            "Deep technical knowledge of AWS IAM, KMS, Security Hub, and VPC networking.",
            "Hands-on expertise with container security, eBPF, and runtime threat detection.",
            "Relevant certifications (CISSP, CCSP, AWS Certified Security Specialty) preferred."
        ],
        "benefits": [
            "Competitive base + equity in a leading publicly traded SaaS enterprise.",
            "401(k) with company match and Employee Stock Purchase Plan (ESPP).",
            "Generous fitness reimbursement and wellness programs.",
            "Tuition assistance and ongoing professional development budget.",
            "World-class offices in central Manhattan with panoramic views and catered perks."
        ]
    },
    {
        "company_slug": "figma",
        "title": "Principal Product Designer - Core Design Systems",
        "role_slug": "principal-product-designer-design-systems",
        "city_name": "San Francisco",
        "work_mode": "HYBRID",
        "seniority": "LEAD",
        "employment_type": "FULL_TIME",
        "salary_min": 190000,
        "salary_max": 270000,
        "currency_code": "USD",
        "min_experience_years": 7,
        "max_experience_years": 14,
        "ai_score_threshold": 75,
        "extracted_skills": ["Figma", "Design Systems", "User Research", "Interaction Design", "Prototyping", "Design Tokens", "Accessibility (WCAG)"],
        "job_overview": "We're looking for a Principal Product Designer to lead Figma's own Design System. You will craft the foundation and components used by Figma's product designers and engineers, while setting the benchmark for the global design community.",
        "about_role": [
            "Evolve Figma's foundational design tokens, variables, typography, and interactive components.",
            "Bridge the gap between design and code, partnering directly with frontend platform engineers.",
            "Champion WCAG 2.2 accessibility and ergonomic interaction design across web and desktop apps."
        ],
        "responsibilities": [
            "Design flexible, accessible, multi-platform UI components in Figma.",
            "Create comprehensive documentation, usage guidelines, and contribution playbooks.",
            "Conduct usability studies with internal design teams and external creators.",
            "Advise executive product leadership on design consistency and brand evolution."
        ],
        "requirements": [
            "7+ years designing software products, with at least 3 years dedicated to enterprise design systems.",
            "Expert-level mastery of Figma, auto-layout, component properties, and variable tokens.",
            "Strong grasp of frontend web technologies (HTML, CSS, flexbox, CSS variables).",
            "Exceptional storytelling and cross-functional communication skills."
        ],
        "benefits": [
            "Generous equity grants and competitive salary.",
            "Comprehensive health, dental, and vision insurance.",
            "$2,000 annual learning & development stipend.",
            "Wellness benefits, gym stipend, and mental health resources.",
            "Flexible hybrid work environment in our vibrant downtown SF studio."
        ]
    },
    {
        "company_slug": "razorpay",
        "title": "Senior Full Stack Engineer - Banking & Payouts Platform",
        "role_slug": "full-stack-engineer-node-react",
        "city_name": "Bengaluru",
        "work_mode": "HYBRID",
        "seniority": "SENIOR",
        "employment_type": "FULL_TIME",
        "salary_min": 2800000,
        "salary_max": 4200000,
        "currency_code": "INR",
        "min_experience_years": 4,
        "max_experience_years": 8,
        "ai_score_threshold": 70,
        "extracted_skills": ["Node.js", "React", "TypeScript", "PostgreSQL", "Redis", "Docker", "REST APIs", "Microservices"],
        "job_overview": "Razorpay is looking for a Senior Full Stack Engineer to lead technical developments on RazorpayX, our automated business banking platform. You will build user-friendly interfaces and resilient banking integrations that power enterprise payroll and vendor payouts.",
        "about_role": [
            "Build scalable payout microservices processing over INR 10,000 Crore monthly.",
            "Design intuitive dashboard interfaces used by finance teams and startup founders.",
            "Integrate directly with real-time banking APIs (IMPS, NEFT, RTGS, UPI)."
        ],
        "responsibilities": [
            "Develop end-to-end features using Node.js (NestJS) on the backend and React/Next.js on the frontend.",
            "Optimize transaction processing workflows with asynchronous workers and Redis queues.",
            "Ensure 99.99% system availability through automated tests, monitoring, and alerting.",
            "Collaborate closely with product managers and compliance teams to roll out new financial products."
        ],
        "requirements": [
            "4+ years of full-stack engineering experience in high-growth technology environments.",
            "Strong command of TypeScript, Node.js, and React.",
            "Experience with PostgreSQL query tuning and transactional safety.",
            "Prior exposure to fintech, payment gateways, or banking integrations is a major plus."
        ],
        "benefits": [
            "Attractive salary + substantial Employee Stock Ownership Plan (ESOP).",
            "Comprehensive health insurance for employee, spouse, children, and parents.",
            "Flexible hybrid working model with state-of-the-art Bengaluru campus.",
            "Annual learning and certification allowances.",
            "Relocation assistance and home broadband reimbursements."
        ]
    },
    {
        "company_slug": "razorpay",
        "title": "Staff Data Engineer - Real-time Risk & Analytics",
        "role_slug": "staff-data-engineer-spark-snowflake",
        "city_name": "Bengaluru",
        "work_mode": "ONSITE",
        "seniority": "LEAD",
        "employment_type": "FULL_TIME",
        "salary_min": 3800000,
        "salary_max": 5500000,
        "currency_code": "INR",
        "min_experience_years": 7,
        "max_experience_years": 12,
        "ai_score_threshold": 75,
        "extracted_skills": ["Python", "SQL", "Apache Spark", "Kafka", "Snowflake", "Airflow", "Data Modeling", "AWS"],
        "job_overview": "Razorpay's Data Platform team is hiring a Staff Data Engineer to architect our next-gen real-time transaction intelligence pipeline. You will process terabytes of streaming payment events to detect anomalies and power analytics in real time.",
        "about_role": [
            "Architect petabyte-scale streaming and batch pipelines using Apache Spark, Kafka, and Snowflake.",
            "Enable fraud prevention algorithms to evaluate transactions in under 20 milliseconds.",
            "Define data governance, data lineage, and privacy standards for sensitive financial records."
        ],
        "responsibilities": [
            "Design and maintain scalable real-time streaming pipelines with Kafka and Spark Streaming.",
            "Build optimized data models and automated dbt transforms in Snowflake.",
            "Drive CI/CD for data pipelines and automated data quality checks.",
            "Mentor data engineers and lead platform architecture discussions."
        ],
        "requirements": [
            "7+ years of experience in data engineering and distributed computing.",
            "Deep expertise in Python, SQL, and Apache Spark.",
            "Hands-on experience architecting Kafka clusters and schema registries.",
            "Strong familiarity with modern cloud data warehouses like Snowflake, BigQuery, or Redshift."
        ],
        "benefits": [
            "Industry-leading compensation and wealth-creation ESOPs.",
            "Complete medical insurance coverage including OPD and dental benefits.",
            "Catered gourmet meals and snacks on campus.",
            "Wellness leave and paternity/maternity sabbaticals.",
            "Quarterly tech hackathons and innovation awards."
        ]
    },
    {
        "company_slug": "postman",
        "title": "Senior Product Manager - API Collaboration & Workspaces",
        "role_slug": "senior-product-manager-developer-platform",
        "city_name": "Bengaluru",
        "work_mode": "HYBRID",
        "seniority": "SENIOR",
        "employment_type": "FULL_TIME",
        "salary_min": 3200000,
        "salary_max": 4800000,
        "currency_code": "INR",
        "min_experience_years": 5,
        "max_experience_years": 9,
        "ai_score_threshold": 75,
        "extracted_skills": ["Product Strategy", "API Design", "Developer Experience", "Roadmapping", "Agile", "User Research", "Data Analytics"],
        "job_overview": "Postman is seeking a Senior Product Manager to spearhead API Collaboration and Team Workspaces. You will define the vision and execution for how engineering teams across the world design, share, and govern APIs together.",
        "about_role": [
            "Lead product direction for collaborative team workspaces used by 30+ million developers.",
            "Translate complex developer workflows into simple, elegant product experiences.",
            "Partner with engineering and UX to define quarterly OKRs and deliver high-impact product releases."
        ],
        "responsibilities": [
            "Define product requirements, user stories, and acceptance criteria.",
            "Engage directly with Fortune 500 engineering leaders to understand enterprise API governance needs.",
            "Analyze engagement telemetry, conversion funnels, and user feedback to inform roadmap priorities.",
            "Present product demos at global developer conferences and webinars."
        ],
        "requirements": [
            "5+ years of software product management experience, preferably in developer tools or B2B SaaS.",
            "Technical background or engineering degree with a solid understanding of APIs (REST, GraphQL, gRPC).",
            "Demonstrated success launching widely adopted products from discovery to scale.",
            "Data-driven mindset with proficiency in telemetry analysis tools (Mixpanel, Amplitude, SQL)."
        ],
        "benefits": [
            "Competitive pay with rewarding equity options.",
            "Full healthcare benefits for self and family.",
            "Hybrid flexible schedule with modern collaborative workspaces.",
            "Annual continuous learning grant and book allowance.",
            "Home office setup and monthly wellness allowances."
        ]
    },
    {
        "company_slug": "postman",
        "title": "Senior Backend Engineer - API Protocol Engine",
        "role_slug": "senior-backend-engineer-python-fastapi",
        "city_name": "Bengaluru",
        "work_mode": "HYBRID",
        "seniority": "SENIOR",
        "employment_type": "FULL_TIME",
        "salary_min": 2600000,
        "salary_max": 3800000,
        "currency_code": "INR",
        "min_experience_years": 4,
        "max_experience_years": 8,
        "ai_score_threshold": 70,
        "extracted_skills": ["Node.js", "Python", "FastAPI", "WebSockets", "Docker", "PostgreSQL", "REST APIs", "Microservices"],
        "job_overview": "Join Postman's Core Protocols team to build next-generation request execution engines. You will work on expanding Postman's protocol support across WebSocket, gRPC, MQTT, and event-driven architectures.",
        "about_role": [
            "Develop high-performance networking and protocol inspection libraries.",
            "Scale cloud-based collection runners executing millions of tests every hour.",
            "Contribute to open standards in the API landscape."
        ],
        "responsibilities": [
            "Write modular, clean, and tested code in Python and Node.js.",
            "Architect low-latency streaming infrastructure for real-time protocol monitoring.",
            "Benchmark and optimize network socket handling and serialization performance.",
            "Collaborate with security teams to ensure secure sandbox execution of user scripts."
        ],
        "requirements": [
            "4+ years of backend development experience building scalable services.",
            "Strong understanding of HTTP/2, HTTP/3, TCP/IP, and WebSocket protocols.",
            "Proficiency in Python (FastAPI/asyncio) or modern Node.js.",
            "Familiarity with containerization and Linux networking."
        ],
        "benefits": [
            "Competitive compensation package + ESOPs.",
            "Comprehensive health coverage including parents.",
            "Flexible work arrangements.",
            "Sponsored certifications and technical conference attendance.",
            "Catered lunches and office amenities."
        ]
    },
    {
        "company_slug": "scale-ai",
        "title": "Applied Scientist - Computer Vision & Multimodal AI",
        "role_slug": "senior-applied-scientist-nlp-search",
        "city_name": "San Francisco",
        "work_mode": "HYBRID",
        "seniority": "SENIOR",
        "employment_type": "FULL_TIME",
        "salary_min": 195000,
        "salary_max": 275000,
        "currency_code": "USD",
        "min_experience_years": 4,
        "max_experience_years": 9,
        "ai_score_threshold": 75,
        "extracted_skills": ["Python", "PyTorch", "Computer Vision", "Multimodal AI", "Transformers", "Vector Embeddings", "Deep Learning"],
        "job_overview": "Scale AI is seeking an Applied Scientist to pioneer multimodal foundation models. You will train vision-language models capable of understanding complex images, video, and 3D sensor streams with superhuman precision.",
        "about_role": [
            "Develop state-of-the-art vision-language pretraining and fine-tuning recipes.",
            "Enhance data annotation quality through automated AI labeling in the loop.",
            "Publish breakthrough findings at top-tier conferences (CVPR, NeurIPS, ICCV)."
        ],
        "responsibilities": [
            "Train large-scale multimodal models on massive cluster allocations.",
            "Design novel loss functions and attention mechanisms for dense visual reasoning.",
            "Deploy models to production inference endpoints with optimized latency.",
            "Mentor research interns and junior machine learning engineers."
        ],
        "requirements": [
            "MS or PhD in Computer Science, Machine Learning, or related quantitative field.",
            "Strong publication record or demonstrable production experience in computer vision / multimodal AI.",
            "Expert coding skills in Python and PyTorch.",
            "Experience with distributed GPU training frameworks."
        ],
        "benefits": [
            "Competitive compensation + significant equity.",
            "Relocation assistance to San Francisco.",
            "Full health, vision, and dental insurance.",
            "Generous GPU compute allocation for self-directed research.",
            "Daily catered meals and company events."
        ]
    }
]


# ---------------------------------------------------------------------------
# MAIN SEEDER FUNCTION
# ---------------------------------------------------------------------------
def run_seed():
    session = SessionLocal()
    logger.info("🚀 Starting Companies, Taxonomy, and Job Postings Seed...")

    try:
        # Step 0: Cache Metadata IDs
        logger.info("Fetching Meta tables...")
        countries = {c.name.lower(): c.id for c in session.query(MetaCountry).all()}
        cities = {c.name.lower(): c for c in session.query(MetaCity).all()}
        work_modes = {wm.name.upper(): wm.id for wm in session.query(MetaWorkMode).all()}
        seniorities = {sl.name.upper(): sl.id for sl in session.query(MetaSeniorityLevel).all()}
        emp_types = {et.name.upper(): et.id for et in session.query(MetaEmploymentType).all()}
        currencies = {c.code.upper(): c.id for c in session.query(MetaCurrency).all()}
        industries = {ind.name.lower(): ind.id for ind in session.query(MetaIndustry).all()}
        company_sizes = {cs.label: cs.id for cs in session.query(MetaCompanySize).all()}
        org_types = {ot.name.lower(): ot.id for ot in session.query(MetaOrganizationType).all()}
        visa_statuses = session.query(MetaVisaStatus).all()
        default_visa_id = visa_statuses[0].id if visa_statuses else None

        # Step 1: Seed Taxonomy Domains and Roles
        logger.info("Seeding Taxonomy Domains & Job Roles...")
        domain_cache = {}
        role_cache = {}

        for domain_data in TAXONOMY_DATA:
            d_name = domain_data["domain"]
            d_slug = domain_data["slug"]

            domain = session.query(TaxonomyDomain).filter(TaxonomyDomain.slug == d_slug).first()
            if not domain:
                try:
                    d_emb = embedding_service.get_embedding(d_name)
                except Exception as e:
                    logger.warning(f"Could not compute embedding for domain {d_name}: {e}")
                    d_emb = None

                domain = TaxonomyDomain(
                    name=d_name,
                    slug=d_slug,
                    embedding=d_emb,
                    is_active=True
                )
                session.add(domain)
                session.flush()
                logger.info(f"  + Added Taxonomy Domain: {d_name}")
            domain_cache[d_slug] = domain

            for r_data in domain_data["roles"]:
                r_name = r_data["name"]
                r_slug = r_data["slug"]

                role = session.query(TaxonomyJobRole).filter(TaxonomyJobRole.slug == r_slug).first()
                if not role:
                    try:
                        r_emb = embedding_service.get_embedding(f"{r_name} {' '.join(r_data['required_skills'])}")
                    except Exception as e:
                        logger.warning(f"Could not compute embedding for role {r_name}: {e}")
                        r_emb = None

                    role = TaxonomyJobRole(
                        domain_id=domain.id,
                        name=r_name,
                        slug=r_slug,
                        aliases=r_data["aliases"],
                        required_skills=r_data["required_skills"],
                        optional_skills=r_data.get("optional_skills", []),
                        embedding=r_emb,
                        is_active=True,
                        is_verified=True
                    )
                    session.add(role)
                    session.flush()
                    logger.info(f"    + Added Taxonomy Role: {r_name}")
                role_cache[r_slug] = role

        # Step 2: Seed Companies and Employers
        logger.info("Seeding Companies and Employers...")
        company_cache = {}

        for comp_data in COMPANIES_DATA:
            c_name = comp_data["name"]
            c_slug = comp_data["slug"]

            # Locate City, State, Country
            city_obj = cities.get(comp_data["city_name"].lower())
            city_id = city_obj.id if city_obj else None
            state_id = city_obj.state_id if city_obj else None
            country_id = city_obj.country_id if city_obj else None

            # Create or get Employer User
            emp_email = comp_data["employer_email"]
            user = session.query(User).filter(User.email == emp_email).first()
            if not user:
                user = User(
                    email=emp_email,
                    role=UserRole.EMPLOYER,
                    auth_provider=AuthProvider.LOCAL,
                    is_active=True,
                    is_verified=True
                )
                session.add(user)
                session.flush()

            # Create or get Company
            company = session.query(Company).filter(Company.name == c_name).first()
            if not company:
                company = Company(
                    name=c_name,
                    website=comp_data["website"],
                    logo_url=comp_data["logo_url"],
                    founded_year=comp_data["founded_year"],
                    description=comp_data["description"],
                    zipcode=comp_data["zipcode"],
                    office_landline_number=comp_data["office_landline_number"],
                    alternate_email=comp_data["alternate_email"],
                    work_mobile_number=comp_data["work_mobile_number"],
                    onboarding_step=4,
                    onboarding_completed=True,
                    plan_tier=comp_data["plan_tier"],
                    industry_id=industries.get(comp_data["industry_name"].lower()),
                    size_id=company_sizes.get(comp_data["size_label"]),
                    organization_type_id=org_types.get(comp_data["org_type_name"].lower()),
                    city_id=city_id,
                    state_id=state_id,
                    country_id=country_id,
                    is_active=True
                )
                session.add(company)
                session.flush()

                # Associate company to software & AI taxonomy domains
                for d_obj in domain_cache.values():
                    company.hiring_domains.append(d_obj)
                session.flush()

                logger.info(f"  + Added Company: {c_name}")
            company_cache[c_slug] = company

            # Create or link Employer profile
            employer = session.query(Employer).filter(Employer.user_id == user.id).first()
            if not employer:
                employer = Employer(
                    user_id=user.id,
                    company_id=company.id,
                    contact_person=comp_data["employer_name"],
                    phone=comp_data["work_mobile_number"]
                )
                session.add(employer)
                session.flush()

        # Step 3: Seed Job Postings
        logger.info("Seeding Job Postings...")
        now = datetime.now(timezone.utc)
        created_count = 0

        for j_data in JOBS_DATA:
            comp_slug = j_data["company_slug"]
            company = company_cache.get(comp_slug)
            if not company:
                logger.warning(f"Company {comp_slug} not found, skipping job {j_data['title']}")
                continue

            # Check if job already exists for this company
            existing_job = session.query(JobPosting).filter(
                JobPosting.company_id == company.id,
                JobPosting.title == j_data["title"]
            ).first()
            if existing_job:
                logger.info(f"  - Job already exists: {j_data['title']} ({company.name})")
                continue

            # Location details
            city_obj = cities.get(j_data["city_name"].lower())
            city_id = city_obj.id if city_obj else None
            state_id = city_obj.state_id if city_obj else None
            country_id = city_obj.country_id if city_obj else None

            # Role details
            role_slug = j_data["role_slug"]
            role_obj = role_cache.get(role_slug)
            role_id = role_obj.id if role_obj else None
            domain_id = role_obj.domain_id if role_obj else None

            # Compile full markdown description
            desc_lines = [
                f"# {j_data['title']}",
                f"**Company**: {company.name} | **Location**: {j_data['city_name']} ({j_data['work_mode'].capitalize()})",
                "",
                "## Job Overview",
                j_data["job_overview"],
                "",
                "## About the Role",
                "\n".join(f"- {item}" for item in j_data["about_role"]),
                "",
                "## Key Responsibilities",
                "\n".join(f"- {item}" for item in j_data["responsibilities"]),
                "",
                "## Qualifications & Requirements",
                "\n".join(f"- {item}" for item in j_data["requirements"]),
                "",
                "## Benefits & Perks",
                "\n".join(f"- {item}" for item in j_data["benefits"]),
            ]
            full_description = "\n".join(desc_lines)

            # Generate embedding for semantic matching
            emb_text = f"{j_data['title']} {j_data['job_overview']} {' '.join(j_data['extracted_skills'])}"
            try:
                job_emb = embedding_service.get_embedding(emb_text)
            except Exception as e:
                logger.warning(f"Could not compute embedding for {j_data['title']}: {e}")
                job_emb = None

            # Deadlines
            deadline = now + timedelta(days=45)

            job = JobPosting(
                company_id=company.id,
                title=j_data["title"],
                description=full_description,
                job_overview=j_data["job_overview"],
                about_role=j_data["about_role"],
                responsibilities=j_data["responsibilities"],
                requirements=j_data["requirements"],
                benefits=j_data["benefits"],
                extracted_skills=j_data["extracted_skills"],
                employment_type_id=emp_types.get(j_data["employment_type"], 1),
                seniority_level_id=seniorities.get(j_data["seniority"], 4),
                work_mode_id=work_modes.get(j_data["work_mode"], 1),
                city_id=city_id,
                state_id=state_id,
                country_id=country_id,
                salary_min=j_data["salary_min"],
                salary_max=j_data["salary_max"],
                currency_id=currencies.get(j_data["currency_code"], 1),
                min_experience_years=j_data["min_experience_years"],
                max_experience_years=j_data["max_experience_years"],
                taxonomy_domain_id=domain_id,
                taxonomy_job_role_id=role_id,
                ai_score_threshold=j_data["ai_score_threshold"],
                embedding=job_emb,
                include_cover_letter=True,
                cover_letter_required=False,
                must_be_authorized_to_work=True,
                requires_visa_sponsorship=default_visa_id,
                num_positions=1,
                status=JobStatus.PUBLISHED,
                is_active=True,
                start_date=now,
                application_deadline=deadline
            )
            session.add(job)
            created_count += 1
            logger.info(f"  + Added Job: {j_data['title']} at {company.name}")

        session.commit()
        logger.info(f"\n🎉 Successfully seeded {created_count} jobs across {len(company_cache)} companies!")

    except Exception as e:
        session.rollback()
        logger.error(f"❌ Seeding failed with error: {e}", exc_info=True)
        raise e
    finally:
        session.close()


if __name__ == "__main__":
    run_seed()
