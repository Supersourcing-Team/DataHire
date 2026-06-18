import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing. Add it to .env before running seed.py.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
session = SessionLocal()


def get_existing_id(query, params):
    return session.execute(text(query), params).scalar_one_or_none()


def insert_and_get_id(query, params):
    return session.execute(text(query), params).scalar_one()


def seed_currencies():
    currencies = [
        ("USD", "$", "US Dollar"),
        ("INR", "Rs", "Indian Rupee"),
        ("EUR", "EUR", "Euro"),
        ("GBP", "GBP", "British Pound"),
        ("JPY", "JPY", "Japanese Yen"),
    ]

    currency_ids = []

    for code, symbol, name in currencies:
        currency_id = get_existing_id(
            "SELECT id FROM meta_currencies WHERE code = :code",
            {"code": code},
        )

        if currency_id is None:
            currency_id = insert_and_get_id(
                """
                INSERT INTO meta_currencies (code, symbol, name, is_active)
                VALUES (:code, :symbol, :name, :is_active)
                RETURNING id
                """,
                {
                    "code": code,
                    "symbol": symbol,
                    "name": name,
                    "is_active": True,
                },
            )

        currency_ids.append({"id": currency_id, "code": code})

    print("Currencies seeded.")
    return currency_ids


def seed_countries():
    countries = [
        ("India", "IN", "INR"),
        ("United States", "US", "USD"),
        ("Germany", "DE", "EUR"),
        ("United Kingdom", "GB", "GBP"),
        ("Japan", "JP", "JPY"),
    ]

    country_ids = []

    for name, iso_code, currency_code in countries:
        country_id = get_existing_id(
            "SELECT id FROM meta_countries WHERE name = :name",
            {"name": name},
        )

        if country_id is None:
            country_id = insert_and_get_id(
                """
                INSERT INTO meta_countries (name, iso_code, currency_code, is_active)
                VALUES (:name, :iso_code, :currency_code, :is_active)
                RETURNING id
                """,
                {
                    "name": name,
                    "iso_code": iso_code,
                    "currency_code": currency_code,
                    "is_active": True,
                },
            )

        country_ids.append({"id": country_id, "name": name})

    print("Countries seeded.")
    return country_ids


def seed_states(country_ids):
    state_map = {
        "India": [
            ("Maharashtra", "MH"),
            ("Karnataka", "KA"),
            ("Delhi", "DL"),
        ],
        "United States": [
            ("California", "CA"),
            ("Texas", "TX"),
            ("New York", "NY"),
        ],
        "Germany": [
            ("Bavaria", "BY"),
            ("Berlin", "BE"),
            ("Hesse", "HE"),
        ],
        "United Kingdom": [
            ("England", "ENG"),
            ("Scotland", "SCT"),
            ("Wales", "WLS"),
        ],
        "Japan": [
            ("Tokyo", "TK"),
            ("Osaka", "OS"),
            ("Kyoto", "KY"),
        ],
    }

    states = []

    for country in country_ids:
        for name, code in state_map.get(country["name"], []):
            state_id = get_existing_id(
                """
                SELECT id
                FROM meta_states
                WHERE country_id = :country_id AND name = :name
                """,
                {"country_id": country["id"], "name": name},
            )

            if state_id is None:
                state_id = insert_and_get_id(
                    """
                    INSERT INTO meta_states (country_id, name, code, is_active)
                    VALUES (:country_id, :name, :code, :is_active)
                    RETURNING id
                    """,
                    {
                        "country_id": country["id"],
                        "name": name,
                        "code": code,
                        "is_active": True,
                    },
                )

            states.append(
                {
                    "id": state_id,
                    "country_id": country["id"],
                    "name": name,
                }
            )

    print("States seeded.")
    return states


def seed_cities(states):
    city_map = {
        "Maharashtra": ["Mumbai", "Pune", "Nagpur"],
        "Karnataka": ["Bengaluru", "Mysuru", "Mangaluru"],
        "Delhi": ["New Delhi", "Dwarka", "Rohini"],
        "California": ["San Francisco", "Los Angeles", "San Diego"],
        "Texas": ["Austin", "Dallas", "Houston"],
        "New York": ["New York City", "Buffalo", "Albany"],
        "Bavaria": ["Munich", "Nuremberg", "Augsburg"],
        "Berlin": ["Berlin"],
        "Hesse": ["Frankfurt", "Wiesbaden", "Darmstadt"],
        "England": ["London", "Manchester", "Birmingham"],
        "Scotland": ["Edinburgh", "Glasgow", "Aberdeen"],
        "Wales": ["Cardiff", "Swansea", "Newport"],
        "Tokyo": ["Shinjuku", "Shibuya", "Chiyoda"],
        "Osaka": ["Osaka", "Sakai", "Higashiosaka"],
        "Kyoto": ["Kyoto", "Uji", "Kameoka"],
    }

    for state in states:
        for city_name in city_map.get(state["name"], []):
            city_id = get_existing_id(
                """
                SELECT id
                FROM meta_cities
                WHERE state_id = :state_id
                    AND country_id = :country_id
                    AND name = :name
                """,
                {
                    "state_id": state["id"],
                    "country_id": state["country_id"],
                    "name": city_name,
                },
            )

            if city_id is None:
                session.execute(
                    text(
                        """
                        INSERT INTO meta_cities (state_id, country_id, name, is_active)
                        VALUES (:state_id, :country_id, :name, :is_active)
                        """
                    ),
                    {
                        "state_id": state["id"],
                        "country_id": state["country_id"],
                        "name": city_name,
                        "is_active": True,
                    },
                )

    print("Cities seeded.")


def seed_employment_types():
    employment_types = [
        "FULL_TIME",
        "PART_TIME",
        "CONTRACT",
        "INTERNSHIP",
        "FREELANCE",
    ]

    for name in employment_types:
        if get_existing_id(
            "SELECT id FROM meta_employment_types WHERE name = :name",
            {"name": name},
        ) is None:
            session.execute(
                text(
                    """
                    INSERT INTO meta_employment_types (name, is_active)
                    VALUES (:name, :is_active)
                    """
                ),
                {"name": name, "is_active": True},
            )

    print("Employment types seeded.")


def seed_work_modes():
    work_modes = ["REMOTE", "HYBRID", "ONSITE"]

    for name in work_modes:
        if get_existing_id(
            "SELECT id FROM meta_work_modes WHERE name = :name",
            {"name": name},
        ) is None:
            session.execute(
                text(
                    """
                    INSERT INTO meta_work_modes (name, is_active)
                    VALUES (:name, :is_active)
                    """
                ),
                {"name": name, "is_active": True},
            )

    print("Work modes seeded.")


def seed_work_statuses():
    work_statuses = [
        {"name": "Student", "is_active": True},
        {"name": "Fresher", "is_active": True},
        {"name": "Currently Working", "is_active": True},
        {"name": "Immediate Joiner", "is_active": True},
        {"name": "Freelancer", "is_active": True},
        {"name": "Laid off", "is_active": True},
        {"name": "career switcher men", "is_active": True},
        {"name": "career switcher women", "is_active": True},
    ]

    for work_status in work_statuses:
        columns = ", ".join(work_status.keys())
        values = ", ".join(f":{key}" for key in work_status.keys())
        update_columns = [key for key in work_status.keys() if key != "name"]

        if update_columns:
            update_clause = ", ".join(
                f"{column} = EXCLUDED.{column}" for column in update_columns
            )
            query = f"""
                INSERT INTO meta_work_statuses ({columns})
                VALUES ({values})
                ON CONFLICT (name) DO UPDATE
                SET {update_clause}
            """
        else:
            query = f"""
                INSERT INTO meta_work_statuses ({columns})
                VALUES ({values})
                ON CONFLICT (name) DO NOTHING
            """

        session.execute(text(query), work_status)

    print("Work statuses seeded.")


def seed_visa_statuses():
    visa_statuses = [
        "U.S. Citizen",
        "Green Card",
        "Student Visa (F-1 OPT/CPT)",
        "L-1 Visa",
        "O-1 Visa",
        "TN Visa",
        "H-1B Visa",
        "Need Sponsorship",
        "Other Work Visa",
    ]

    for name in visa_statuses:
        if get_existing_id(
            "SELECT id FROM meta_visa_statuses WHERE name = :name",
            {"name": name},
        ) is None:
            session.execute(
                text(
                    """
                    INSERT INTO meta_visa_statuses (name, is_active)
                    VALUES (:name, :is_active)
                    """
                ),
                {"name": name, "is_active": True},
            )

    print("Visa statuses seeded.")


def seed_company_sizes():
    company_sizes = [
        ("1-10", 1, 10),
        ("11-50", 11, 50),
        ("51-200", 51, 200),
        ("201-1000", 201, 1000),
        ("1000+", 1000, None),
    ]

    for label, min_employees, max_employees in company_sizes:
        if get_existing_id(
            "SELECT id FROM meta_company_sizes WHERE label = :label",
            {"label": label},
        ) is None:
            session.execute(
                text(
                    """
                    INSERT INTO meta_company_sizes (
                        label,
                        min_employees,
                        max_employees,
                        is_active
                    )
                    VALUES (
                        :label,
                        :min_employees,
                        :max_employees,
                        :is_active
                    )
                    """
                ),
                {
                    "label": label,
                    "min_employees": min_employees,
                    "max_employees": max_employees,
                    "is_active": True,
                },
            )

    print("Company sizes seeded.")


def seed_experience_brackets():
    brackets = [
        ("0-1 Years", 0, 1),
        ("1-3 Years", 1, 3),
        ("3-5 Years", 3, 5),
        ("5-10 Years", 5, 10),
        ("10+ Years", 10, None),
    ]

    for label, min_years, max_years in brackets:
        if get_existing_id(
            "SELECT id FROM meta_experience_brackets WHERE label = :label",
            {"label": label},
        ) is None:
            session.execute(
                text(
                    """
                    INSERT INTO meta_experience_brackets (
                        label,
                        min_years,
                        max_years,
                        is_active
                    )
                    VALUES (
                        :label,
                        :min_years,
                        :max_years,
                        :is_active
                    )
                    """
                ),
                {
                    "label": label,
                    "min_years": min_years,
                    "max_years": max_years,
                    "is_active": True,
                },
            )

    print("Experience brackets seeded.")


def seed_seniority_levels():
    levels = [
        "FRESHER",
        "JUNIOR",
        "MID_LEVEL",
        "SENIOR",
        "LEAD",
        "PRINCIPAL",
        "ARCHITECT",
    ]

    for name in levels:
        if get_existing_id(
            "SELECT id FROM meta_seniority_levels WHERE name = :name",
            {"name": name},
        ) is None:
            session.execute(
                text(
                    """
                    INSERT INTO meta_seniority_levels (name, is_active)
                    VALUES (:name, :is_active)
                    """
                ),
                {"name": name, "is_active": True},
            )

    print("Seniority levels seeded.")


def seed_organization_types():
    organization_types = [
       "Startup",
       "Product",
        "SAAS",
        "Enterprise",
        "Recruitment Agency"
    ]

    for name in organization_types:
        if get_existing_id(
            "SELECT id FROM meta_organization_types WHERE name = :name",
            {"name": name},
        ) is None:
            session.execute(
                text(
                    """
                    INSERT INTO meta_organization_types (name, is_active)
                    VALUES (:name, :is_active)
                    """
                ),
                {"name": name, "is_active": True},
            )

    print("Organization types seeded.")


def seed_education_levels():
    education_levels = [
        "HIGH_SCHOOL",
        "BACHELOR",
        "MASTER",
        "PHD",
        "DIPLOMA",
    ]

    for name in education_levels:
        if get_existing_id(
            "SELECT id FROM meta_education_levels WHERE name = :name",
            {"name": name},
        ) is None:
            session.execute(
                text(
                    """
                    INSERT INTO meta_education_levels (name, is_active)
                    VALUES (:name, :is_active)
                    """
                ),
                {"name": name, "is_active": True},
            )

    print("Education levels seeded.")


def seed_industries():
    industries = [
        "Information Technology",
        "Healthcare",
        "Finance",
        "Education",
        "Construction",
        "Retail",
        "Manufacturing",
        "Automobile",
        "Telecommunications",
        "Energy",
    ]

    for name in industries:
        if get_existing_id(
            "SELECT id FROM meta_industries WHERE name = :name",
            {"name": name},
        ) is None:
            session.execute(
                text(
                    """
                    INSERT INTO meta_industries (name, is_active)
                    VALUES (:name, :is_active)
                    """
                ),
                {"name": name, "is_active": True},
            )

    print("Industries seeded.")


def seed_subscription_plans(currency_ids):
    plans = [
        ("FREE", 0),
        ("BASIC", 9.99),
        ("PRO", 29.99),
        ("ENTERPRISE", 99.99),
    ]

    default_currency_id = next(
        currency["id"] for currency in currency_ids if currency["code"] == "USD"
    )

    for name, price in plans:
        features = {
            "job_post_limit": {
                "FREE": 1,
                "BASIC": 10,
                "PRO": 50,
                "ENTERPRISE": 9999,
            }[name],
            "resume_access": name != "FREE",
            "priority_support": name in {"PRO", "ENTERPRISE"},
            "analytics": name in {"BASIC", "PRO", "ENTERPRISE"},
        }

        if get_existing_id(
            "SELECT id FROM meta_subscription_plans WHERE name = :name",
            {"name": name},
        ) is None:
            session.execute(
                text(
                    """
                    INSERT INTO meta_subscription_plans (
                        name,
                        price,
                        currency_id,
                        features,
                        is_active
                    )
                    VALUES (
                        :name,
                        :price,
                        :currency_id,
                        CAST(:features AS JSONB),
                        :is_active
                    )
                    """
                ),
                {
                    "name": name,
                    "price": price,
                    "currency_id": default_currency_id,
                    "features": json.dumps(features),
                    "is_active": True,
                },
            )

    print("Subscription plans seeded.")


SEEDERS = {
    "currencies": seed_currencies,
    "countries": seed_countries,
    "employment_types": seed_employment_types,
    "work_modes": seed_work_modes,
    "work_statuses": seed_work_statuses,
    "visa_statuses": seed_visa_statuses,
    "company_sizes": seed_company_sizes,
    "experience_brackets": seed_experience_brackets,
    "seniority_levels": seed_seniority_levels,
    "organization_types": seed_organization_types,
    "education_levels": seed_education_levels,
    "industries": seed_industries,
}


def run_selected_seeders(only=None):
    if only:
        if only == "subscription_plans":
            currency_ids = seed_currencies()
            seed_subscription_plans(currency_ids)
            return

        if only == "states":
            country_ids = seed_countries()
            seed_states(country_ids)
            return

        if only == "cities":
            country_ids = seed_countries()
            states = seed_states(country_ids)
            seed_cities(states)
            return

        SEEDERS[only]()
        return

    currency_ids = seed_currencies()
    country_ids = seed_countries()
    states = seed_states(country_ids)

    seed_cities(states)
    seed_employment_types()
    seed_work_modes()
    seed_work_statuses()
    seed_visa_statuses()
    seed_company_sizes()
    seed_experience_brackets()
    seed_seniority_levels()
    seed_organization_types()
    seed_education_levels()
    seed_industries()
    seed_subscription_plans(currency_ids)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed DataHire metadata tables.")
    parser.add_argument(
        "--only",
        choices=[
            "currencies",
            "countries",
            "states",
            "cities",
            "employment_types",
            "work_modes",
            "work_statuses",
            "visa_statuses",
            "company_sizes",
            "experience_brackets",
            "seniority_levels",
            "organization_types",
            "education_levels",
            "industries",
            "subscription_plans",
        ],
        help="Run only one seeder. Dependency seeders are run automatically when required.",
    )
    args = parser.parse_args()

    print("Starting database seeding...\n")

    try:
        run_selected_seeders(args.only)

        session.commit()
        print("\nDatabase seeding completed successfully!")

    except Exception as e:
        session.rollback()
        print("\nSeeder failed!")
        print("All database changes rolled back automatically.\n")
        print("Error:")
        print(e)

    finally:
        session.close()
